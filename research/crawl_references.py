#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recursive Reference Crawler (OpenAlex + Semantic Scholar)
Version 1.4.1 — pooled, rate-limited, cached, instrumented parallel crawler

Builds a directed REFERENCES graph (citer -> cited) starting from a seed paper.
Primary expansion via OpenAlex; optional/fallback expansion via Semantic Scholar
for better coverage in arXiv-heavy domains. Normalizes nodes to OpenAlex IDs
where possible. Includes:

• Parallel mapping/fetching (--max-workers)
• Citation thresholding (--min-citations, --prune-below-threshold, --strict-threshold)
• Connection pooling + retries (requests.Session + HTTPAdapter)
• Polite rate limiter for OpenAlex (--oa-qps)
• Low-information title filtering to avoid noisy OA title searches
• Persistent S2→OA mapping cache (--map-cache-path)
• Logging (--verbose/--debug), per-layer progress (--progress), metrics JSON (--metrics-out)
• Per-layer effective parallelism estimate and total wall-clock time
• Optional GraphML and quick PNG layout (--graphml, --plot)
• Option to keep S2-only (unmapped) nodes with synthetic keys (--keep-unmapped)

Outputs:
- sources_nodes.csv
- sources_edges.csv
- graph.json
- [optional] graph.graphml
- [optional] graph.png
- .openalex_cache.json (OpenAlex work JSON cache)
- .map_cache.json (S2→OA mapping cache)
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import logging
from time import perf_counter
from statistics import mean
from collections import deque
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import requests
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
except Exception:
    class Retry:  # minimal shim
        def __init__(self, total=3, backoff_factor=0.3, status_forcelist=None):
            pass

# Optional progress bars
try:
    from tqdm import tqdm  # type: ignore
except Exception:
    tqdm = None

# ----------------------------------------------------------------------------- 
# Constants & headers
# -----------------------------------------------------------------------------
OPENALEX_BASE = "https://api.openalex.org"
SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"

HEADERS_OA = {"User-Agent": "ManyWorlds-ReferenceCrawler/1.4.1 (+https://example.org)"}
HEADERS_S2 = {"User-Agent": "ManyWorlds-ReferenceCrawler/1.4.1 (+https://example.org)"}

# ----------------------------------------------------------------------------- 
# Global metrics (thread-safe)
# -----------------------------------------------------------------------------
_METRICS_LOCK = Lock()
_METRICS = {
    "requests": {
        "openalex": {"ok": 0, "err": 0, "latencies": []},
        "s2": {"ok": 0, "err": 0, "latencies": []},
    },
    "layers": [],  # engine, depth, totals, secs, rps, work_secs, eff_parallelism
    "wall_clock_seconds": None,
}

# ----------------------------------------------------------------------------- 
# Connection pools (requests.Session) and rate limiter
# -----------------------------------------------------------------------------
OA_SESSION = requests.Session()
OA_SESSION.headers.update(HEADERS_OA)
try:
    OA_SESSION.mount(
        "https://",
        HTTPAdapter(
            pool_connections=100,
            pool_maxsize=100,
            max_retries=Retry(total=3, backoff_factor=0.3, status_forcelist=[429, 502, 503, 504]),
        ),
    )
except Exception:
    OA_SESSION.mount("https://", HTTPAdapter(pool_connections=100, pool_maxsize=100))

S2_SESSION = requests.Session()
S2_SESSION.headers.update(HEADERS_S2)
try:
    S2_SESSION.mount(
        "https://",
        HTTPAdapter(
            pool_connections=50,
            pool_maxsize=50,
            max_retries=Retry(total=2, backoff_factor=0.2, status_forcelist=[429, 502, 503, 504]),
        ),
    )
except Exception:
    S2_SESSION.mount("https://", HTTPAdapter(pool_connections=50, pool_maxsize=50))

# Polite rate limiter for OpenAlex
_RATELIMIT_LOCK = Lock()
_LAST_CALL_TS = 0.0
_OA_QPS = 3.0  # default, overridden via CLI

def _rate_limit(bucket: Optional[str]) -> None:
    """Simple limiter: enforce ~QPS for OpenAlex requests."""
    if bucket != "openalex":
        return
    global _LAST_CALL_TS
    with _RATELIMIT_LOCK:
        now = perf_counter()
        wait = max(0.0, (1.0 / max(_OA_QPS, 0.1)) - (now - _LAST_CALL_TS))
        if wait > 0:
            time.sleep(wait)
            now = perf_counter()
        _LAST_CALL_TS = now

# ----------------------------------------------------------------------------- 
# Utilities
# -----------------------------------------------------------------------------
def is_doi(s: str) -> bool:
    return bool(re.match(r"^10\.\d{4,9}/\S+$", s.strip(), re.IGNORECASE))

def extract_openalex_id(s: str) -> Optional[str]:
    s = s.strip()
    m = re.search(r"openalex\.org/(W\d+)", s, re.IGNORECASE)
    if m:
        return m.group(1)
    if re.match(r"^W\d+$", s, re.IGNORECASE):
        return s
    return None

def extract_s2_id(s: str) -> Optional[str]:
    s = s.strip()
    m = re.search(r"/paper/[^/]+/([0-9a-fA-F]{16,}|[A-Za-z0-9\-]+)$", s)
    if m:
        return m.group(1)
    if re.match(r"^[0-9a-fA-F]{16,}$", s) or re.match(r"^[A-Za-z0-9\-]{10,}$", s):
        return s
    return None

def normalize_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    doi = doi.strip()
    if doi.lower().startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]
    return doi

def _percentile(vals: List[float], p: float) -> Optional[float]:
    if not vals:
        return None
    vals = sorted(vals)
    k = max(0, min(len(vals)-1, int(round((p/100.0)*(len(vals)-1)))))
    return float(vals[k])

# Low-information title filter (avoid noisy OA title searches)
GENERIC_TITLE_PAT = re.compile(
    r"(?i)\b("
    r"preprint|proceedings|proc\.|"
    r"phys\.?\s*rev\.?(?:\s*lett\.?)?|"
    r"phys\.?\s*lett\.?(?:\s*[ab])?|"
    r"mod\.?\s*phys\.?\s*lett\.?|"
    r"ann\.?\s*phys\.?|"
    r"nucl\.?\s*phys\.?(?:\s*[ab])?|"
    r"class\.?\s*quant\.?\s*grav\.?|"
    r"(?:commun|comm)\.?\s*math\.?\s*phys\.?|"
    r"int\.?\s*j\.?|jhep|j\.?\s*phys\.?"
    r")\b"
)
ARXIV_ID_PAT = re.compile(r"(?i)^\s*(?:hep-(?:th|ph)|gr-qc|astro-ph|cond-mat)/\d{7}\s*$")

def is_low_info_title(t: Optional[str]) -> bool:
    if not t:
        return True
    if ARXIV_ID_PAT.match(t.strip()):
        return True
    words = re.findall(r"\w+", t)
    if GENERIC_TITLE_PAT.search(t) and len(words) <= 4:
        return True
    return len(words) < 3

# ----------------------------------------------------------------------------- 
# HTTP helpers with instrumentation
# -----------------------------------------------------------------------------
def safe_get(
    url: str,
    params: dict = None,
    headers: dict = None,
    retries: int = 4,
    backoff: float = 1.5,
    bucket: str = None,
    logger: logging.Logger = None,
) -> Any:
    last_err = None
    session = OA_SESSION if bucket == "openalex" else S2_SESSION
    for attempt in range(retries):
        t0 = perf_counter()
        try:
            _rate_limit(bucket)
            resp = session.get(url, params=params, headers=headers, timeout=30)
            dt = perf_counter() - t0
            ok = (resp.status_code == 200)
            with _METRICS_LOCK:
                if bucket:
                    (_METRICS["requests"][bucket]["ok" if ok else "err"]) += 1
                    _METRICS["requests"][bucket]["latencies"].append(dt)
            if ok:
                if logger and logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"GET {bucket or ''} {url} {resp.status_code} in {dt:.3f}s")
                return resp.json()
            if resp.status_code in (429, 503, 502, 504):
                if logger and logger.isEnabledFor(logging.INFO):
                    logger.info(f"Backoff {bucket or ''} {resp.status_code} (attempt {attempt+1})")
                time.sleep((backoff ** attempt) + 0.5)
                continue
            last_err = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        except requests.RequestException as e:
            dt = perf_counter() - t0
            with _METRICS_LOCK:
                if bucket:
                    _METRICS["requests"][bucket]["err"] += 1
                    _METRICS["requests"][bucket]["latencies"].append(dt)
            last_err = e
        time.sleep(backoff ** attempt)
    raise last_err if last_err else RuntimeError("Unknown network error")

def oa_get(path: str, params: dict = None, email: Optional[str] = None, logger: logging.Logger = None) -> Any:
    params = dict(params or {})
    if email:
        params["mailto"] = email
    return safe_get(f"{OPENALEX_BASE}{path}", params=params, headers=HEADERS_OA, bucket="openalex", logger=logger)

def s2_get(path: str, params: dict = None, logger: logging.Logger = None) -> Any:
    return safe_get(f"{SEMANTIC_SCHOLAR_BASE}{path}", params=params, headers=HEADERS_S2, bucket="s2", logger=logger)

# ----------------------------------------------------------------------------- 
# Data model
# -----------------------------------------------------------------------------
@dataclass
class WorkNode:
    openalex_id: Optional[str]
    doi: Optional[str]
    title: Optional[str]
    publication_year: Optional[int]
    host_venue: Optional[str]
    type: Optional[str]
    authors: Optional[str]
    cited_by_count: Optional[int]
    is_retracted: Optional[bool]
    source: Optional[str] = None
    s2_paper_id: Optional[str] = None

    @staticmethod
    def from_openalex_json(j: dict, source: str = "openalex") -> "WorkNode":
        host = j.get("host_venue") or {}
        authorships = j.get("authorships") or []
        authors = ", ".join(
            [a.get("author", {}).get("display_name", "") for a in authorships if a.get("author")]
        ) or None
        return WorkNode(
            openalex_id=(j.get("id") or "").split("/")[-1] if j.get("id") else None,
            doi=j.get("doi") or None,
            title=j.get("title") or None,
            publication_year=j.get("publication_year") or None,
            host_venue=(host.get("display_name") or None),
            type=j.get("type") or None,
            authors=authors,
            cited_by_count=j.get("cited_by_count") or 0,
            is_retracted=j.get("is_retracted") or False,
            source=source,
        )

# ----------------------------------------------------------------------------- 
# Mapping cache (S2 -> OA) — persistent across runs
# -----------------------------------------------------------------------------
_MAP_CACHE: Dict[str, Optional[str]] = {}
_MAP_CACHE_LOCK = Lock()
_MAP_CACHE_PATH = ".map_cache.json"

def _load_map_cache(path: str):
    global _MAP_CACHE
    try:
        with open(path, "r", encoding="utf-8") as f:
            _MAP_CACHE = json.load(f)
    except Exception:
        _MAP_CACHE = {}

def _save_map_cache(path: str):
    try:
        with _MAP_CACHE_LOCK:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(_MAP_CACHE, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _map_cache_get(key: str) -> Optional[Optional[str]]:
    with _MAP_CACHE_LOCK:
        return _MAP_CACHE.get(key)

def _map_cache_set(key: str, val: Optional[str], path: str):
    with _MAP_CACHE_LOCK:
        _MAP_CACHE[key] = val
    _save_map_cache(path)

# ----------------------------------------------------------------------------- 
# Resolvers (OA + S2)
# -----------------------------------------------------------------------------
def oa_resolve_seed(ref: str, email: Optional[str], logger: logging.Logger = None) -> str:
    w = extract_openalex_id(ref)
    if w:
        return w
    if is_doi(ref):
        data = oa_get("/works", {"filter": f"doi:{ref}", "per_page": 1}, email=email, logger=logger)
        results = data.get("results") or []
        if not results:
            raise ValueError(f"No OpenAlex work found for DOI: {ref}")
        return results[0]["id"].split("/")[-1]
    data = oa_get("/works", {"search": ref, "per_page": 5, "sort": "relevance_score:desc"}, email=email, logger=logger)
    results = data.get("results") or []
    if not results:
        raise ValueError(f"No OpenAlex work found for title search: {ref}")
    results.sort(key=lambda r: (r.get("relevance_score", 0), r.get("cited_by_count", 0)), reverse=True)
    return results[0]["id"].split("/")[-1]

def oa_fetch_work(openalex_id: str, email: Optional[str], logger: logging.Logger = None) -> dict:
    return oa_get(f"/works/{openalex_id}", {}, email=email, logger=logger)

def s2_find_seed(ref: str, email: Optional[str], logger: logging.Logger = None) -> Optional[str]:
    s2id = extract_s2_id(ref)
    if s2id:
        return s2id
    if is_doi(ref):
        try:
            j = s2_get(f"/paper/DOI:{ref}", {"fields": "paperId"}, logger=logger)
            return j.get("paperId")
        except Exception:
            pass
    oid = extract_openalex_id(ref)
    if oid or ref.lower().startswith("http"):
        try:
            w = oa_fetch_work(oid or oa_resolve_seed(ref, email, logger=logger), email, logger=logger)
            doi = normalize_doi(w.get("doi"))
            if doi:
                j = s2_get(f"/paper/DOI:{doi}", {"fields": "paperId"}, logger=logger)
                return j.get("paperId")
        except Exception:
            pass
    try:
        j = s2_get("/paper/search", {
            "query": ref, "fields": "paperId,year,citationCount,title", "limit": 5
        }, logger=logger)
        results = j.get("data") or []
        if not results:
            return None
        results.sort(key=lambda r: (r.get("citationCount", 0), r.get("year", 0)), reverse=True)
        return results[0].get("paperId")
    except Exception:
        return None

def s2_fetch_refs(paper_id: str, logger: logging.Logger = None) -> List[dict]:
    """
    NOTE: S2 Graph API does not support nested selectors like references.authors.name.
    Request references.authors and read names locally if needed.
    """
    if not paper_id:
        return []
    j = s2_get(f"/paper/{paper_id}", params={
        "fields": (
            "references.paperId,"
            "references.title,"
            "references.year,"
            "references.externalIds,"
            "references.authors"
        )
    }, logger=logger)
    return (j or {}).get("references") or []

def map_s2_ref_to_openalex(ref: dict, email: Optional[str], logger: logging.Logger, map_cache_path: str) -> Optional[str]:
    ext = ref.get("externalIds") or {}
    doi = normalize_doi(ext.get("DOI"))
    arx = ext.get("ArXiv")
    title = ref.get("title")
    s2id = ref.get("paperId") or ext.get("CorpusId")

    # Cache keys in order of reliability
    if doi:
        key = f"DOI:{doi}"
        cached = _map_cache_get(key)
        if cached is not None:
            return cached
        try:
            data = oa_get("/works", {"filter": f"doi:{doi}", "per_page": 1}, email=email, logger=logger)
            res = data.get("results") or []
            out = res[0]["id"].split("/")[-1] if res else None
            _map_cache_set(key, out, map_cache_path)
            return out
        except Exception:
            _map_cache_set(key, None, map_cache_path)
            return None

    if arx:
        key = f"ARXIV:{arx}"
        cached = _map_cache_get(key)
        if cached is not None:
            return cached
        try:
            data = oa_get("/works", {"search": arx, "per_page": 3}, email=email, logger=logger)
            res = data.get("results") or []
            out = res[0]["id"].split("/")[-1] if res else None
            _map_cache_set(key, out, map_cache_path)
            return out
        except Exception:
            _map_cache_set(key, None, map_cache_path)
            return None

    if s2id:
        key = f"S2:{s2id}"
        cached = _map_cache_get(key)
        if cached is not None:
            return cached

    # Title fallback (avoid low-info titles)
    if title and not is_low_info_title(title):
        tkey = f"TITLE:{title.strip().lower()[:200]}"
        cached = _map_cache_get(tkey)
        if cached is not None:
            return cached
        try:
            data = oa_get("/works", {"search": title, "per_page": 3}, email=email, logger=logger)
            res = data.get("results") or []
            out = res[0]["id"].split("/")[-1] if res else None
            _map_cache_set(tkey, out, map_cache_path)
            if s2id:
                _map_cache_set(f"S2:{s2id}", out, map_cache_path)
            return out
        except Exception:
            _map_cache_set(tkey, None, map_cache_path)
            if s2id:
                _map_cache_set(f"S2:{s2id}", None, map_cache_path)
            return None

    if s2id:
        _map_cache_set(f"S2:{s2id}", None, map_cache_path)
    return None

# ----------------------------------------------------------------------------- 
# Threshold helpers
# -----------------------------------------------------------------------------
def passes_threshold_from_oa_json(work_json: dict, min_citations: int, strict: bool) -> bool:
    c = work_json.get("cited_by_count")
    if c is None:
        return not strict
    try:
        return int(c) >= int(min_citations)
    except Exception:
        return not strict

# ----------------------------------------------------------------------------- 
# Crawlers (OpenAlex-only + S2-backed), with parallelization and instrumentation
# -----------------------------------------------------------------------------
def crawl_references_openalex(
    seed_id: str,
    depth: int,
    email: Optional[str],
    delay: float,
    cache_path: Optional[str],
    max_workers: int,
    min_citations: int,
    prune_below: bool,
    strict_threshold: bool,
    logger: logging.Logger,
    progress: bool,
) -> Tuple[Dict[str, WorkNode], List[Tuple[str, str]]]:

    nodes: Dict[str, WorkNode] = {}
    edges: List[Tuple[str, str]] = []

    cache_oa: Dict[str, dict] = {}
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_oa = json.load(f)
        except Exception:
            cache_oa = {}
    cache_lock = Lock()

    def oa_get_or_fetch(oid: str) -> dict:
        with cache_lock:
            d = cache_oa.get(oid)
        if d is not None:
            return d
        d = oa_fetch_work(oid, email, logger=logger)
        with cache_lock:
            cache_oa[oid] = d
            if cache_path:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(cache_oa, f)
        return d

    # seed
    d0 = oa_get_or_fetch(seed_id)
    nodes[seed_id] = WorkNode.from_openalex_json(d0, source="openalex")

    seen: Set[str] = {seed_id}
    q = deque([(seed_id, 0)])

    while q:
        cur, d = q.popleft()
        if d >= depth:
            continue

        cur_data = oa_get_or_fetch(cur)
        refs = cur_data.get("referenced_works") or []
        child_ids = [r.split("/")[-1] for r in refs if isinstance(r, str) and r.split("/")[-1].startswith("W")]
        if not child_ids:
            if delay > 0:
                time.sleep(delay)
            continue

        layer_start = perf_counter()
        n_total = len(child_ids)
        n_kept = n_pruned = n_expanded = 0
        work_secs_sum = 0.0

        def timed_fetch(oid: str):
            t0 = perf_counter()
            data = oa_get_or_fetch(oid)
            return data, (perf_counter() - t0)

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            future_map = {ex.submit(timed_fetch, cid): cid for cid in child_ids}
            iterator = as_completed(future_map)
            if progress and tqdm is not None:
                iterator = tqdm(iterator, total=n_total, desc=f"OA L{d} refs", leave=False)

            to_expand: List[str] = []
            for fut in iterator:
                cid = future_map[fut]
                try:
                    cjson, elapsed = fut.result()
                except Exception as e:
                    if logger.isEnabledFor(logging.INFO):
                        logger.info(f"[L{d}] OA child {cid} failed: {e}")
                    continue

                work_secs_sum += elapsed
                if logger.isEnabledFor(logging.DEBUG):
                    title = (cjson.get("title") or "")[:60]
                    logger.debug(f"[L{d}] OA child {cid} fetched in {elapsed:.3f}s — {title}")

                keep = passes_threshold_from_oa_json(cjson, min_citations, strict_threshold)
                if not keep and prune_below:
                    n_pruned += 1
                    continue

                n_kept += 1
                if cid not in nodes:
                    nodes[cid] = WorkNode.from_openalex_json(cjson, source="openalex")

                edges.append((cur, cid))

                if keep and cid not in seen:
                    n_expanded += 1
                    to_expand.append(cid)

        for cid in to_expand:
            seen.add(cid)
            q.append((cid, d + 1))

        layer_dt = perf_counter() - layer_start
        eff_parallelism = (work_secs_sum / layer_dt) if layer_dt > 0 else None
        with _METRICS_LOCK:
            _METRICS["layers"].append({
                "engine": "openalex",
                "depth": d,
                "total_refs": n_total,
                "kept": n_kept,
                "pruned": n_pruned,
                "expanded": n_expanded,
                "seconds": layer_dt,
                "refs_per_sec": (n_total / layer_dt) if layer_dt > 0 else None,
                "work_secs": work_secs_sum,
                "eff_parallelism": eff_parallelism,
            })
        if logger.isEnabledFor(logging.INFO):
            logger.info(f"[OA L{d}] refs={n_total} kept={n_kept} pruned={n_pruned} expanded={n_expanded} "
                        f"in {layer_dt:.2f}s (eff_parallelism≈{eff_parallelism and f'{eff_parallelism:.1f}' or 'n/a'})")

        if delay > 0:
            time.sleep(delay)

    return nodes, edges


def crawl_references_via_s2(
    seed_oa_id: str,
    seed_s2_id: str,
    depth: int,
    email: Optional[str],
    delay: float,
    cache_path: Optional[str],
    keep_unmapped: bool,
    max_workers: int,
    min_citations: int,
    prune_below: bool,
    strict_threshold: bool,
    logger: logging.Logger,
    progress: bool,
    map_cache_path: str,
) -> Tuple[Dict[str, WorkNode], List[Tuple[str, str]]]:

    nodes: Dict[str, WorkNode] = {}
    edges: List[Tuple[str, str]] = []

    cache_oa: Dict[str, dict] = {}
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_oa = json.load(f)
        except Exception:
            cache_oa = {}
    cache_lock = Lock()

    def oa_get_or_fetch(oid: str) -> dict:
        with cache_lock:
            d = cache_oa.get(oid)
        if d is not None:
            return d
        d = oa_fetch_work(oid, email, logger=logger)
        with cache_lock:
            cache_oa[oid] = d
            if cache_path:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(cache_oa, f)
        return d

    # Seed node
    seed_json = oa_get_or_fetch(seed_oa_id)
    seed_node = WorkNode.from_openalex_json(seed_json, source="mixed")
    seed_node.s2_paper_id = seed_s2_id
    nodes[seed_oa_id] = seed_node

    seen_keys: Set[str] = {seed_oa_id}  # keys can be OA IDs or S2 synthetic keys
    q = deque([(seed_oa_id, seed_s2_id, 0)])

    while q:
        cur_key, cur_s2, d = q.popleft()
        if d >= depth:
            continue

        try:
            s2_refs = s2_fetch_refs(cur_s2, logger=logger) if cur_s2 else []
        except Exception as e:
            if logger.isEnabledFor(logging.WARNING):
                logger.warning(f"[warn] S2 ref fetch failed for {cur_s2}: {e}")
            s2_refs = []

        layer_start = perf_counter()
        n_total = len(s2_refs)
        n_kept = n_pruned = n_expanded = 0
        work_secs_sum = 0.0

        def worker(ref: dict):
            t0 = perf_counter()
            title = (ref.get("title") or "")[:80]
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"[L{d}] map S2→OA start — {title}")

            cited_oa = map_s2_ref_to_openalex(ref, email, logger=logger, map_cache_path=map_cache_path)
            cited_s2 = ref.get("paperId") or (ref.get("externalIds") or {}).get("CorpusId")

            # Mapped to OA?
            if cited_oa:
                try:
                    cjson = oa_get_or_fetch(cited_oa)
                except Exception as e:
                    if logger.isEnabledFor(logging.INFO):
                        logger.info(f"[L{d}] OA fetch failed for {cited_oa}: {e}")
                    cjson = None
                    cited_oa = None

                dt = perf_counter() - t0
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"[L{d}] map S2→OA done in {dt:.3f}s — OA:{cited_oa or '∅'} — {title}")

                if cited_oa and cjson:
                    keep = passes_threshold_from_oa_json(cjson, min_citations, strict_threshold)
                    if not keep and prune_below:
                        # prune entirely
                        return (None, None, None, True, False, False, None, None, dt)
                    # expand if meets threshold
                    expand = keep
                    return (cited_oa, cjson, cited_s2, True, True, expand, None, None, dt)

            # Unmapped to OA
            dt = perf_counter() - t0
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"[L{d}] map S2→OA done in {dt:.3f}s — OA:∅ — {title}")

            if strict_threshold:
                return (None, None, None, False, False, False, None, None, dt)
            if not keep_unmapped:
                return (None, None, None, False, False, False, None, None, dt)

            # keep as S2-only node with synthetic key (carry title/year for node enrichment)
            synth_key = f"S2:{cited_s2}" if cited_s2 else f"S2-TITLE:{title}"
            s2_title = ref.get("title")
            s2_year = ref.get("year")
            return (synth_key, None, cited_s2, False, True, True, s2_title, s2_year, dt)

        keep_targets: List[
            Tuple[str, Optional[dict], Optional[str], bool, bool, bool, Optional[str], Optional[int], float]
        ] = []
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(worker, r) for r in s2_refs]
            iterator = as_completed(futures)
            if progress and tqdm is not None:
                iterator = tqdm(iterator, total=n_total, desc=f"S2 L{d} refs", leave=False)
            for fut in iterator:
                res = fut.result()
                keep_targets.append(res)  # append all, including pruned, so we can count n_pruned

        for target_key, oa_json, next_s2, mapped_to_oa, keep, expand, s2_title, s2_year, elapsed in keep_targets:
            work_secs_sum += elapsed

            if not keep:
                n_pruned += 1
                continue

            # Create/update node
            if mapped_to_oa and oa_json is not None:
                if target_key not in nodes:
                    node = WorkNode.from_openalex_json(oa_json, source="mixed")
                    node.s2_paper_id = next_s2
                    nodes[target_key] = node
            else:
                # S2-only node (synthetic)
                if target_key not in nodes:
                    nodes[target_key] = WorkNode(
                        openalex_id=None,
                        doi=None,
                        title=s2_title,
                        publication_year=s2_year,
                        host_venue=None,
                        type=None,
                        authors=None,
                        cited_by_count=None,
                        is_retracted=None,
                        source="s2",
                        s2_paper_id=next_s2
                    )

            # Add edge
            if target_key is not None:
                edges.append((cur_key, target_key))
                n_kept += 1

                if expand and target_key not in seen_keys:
                    n_expanded += 1
                    seen_keys.add(target_key)
                    q.append((target_key, next_s2 or "", d + 1))

        layer_dt = perf_counter() - layer_start
        eff_parallelism = (work_secs_sum / layer_dt) if layer_dt > 0 else None
        with _METRICS_LOCK:
            _METRICS["layers"].append({
                "engine": "s2",
                "depth": d,
                "total_refs": n_total,
                "kept": n_kept,
                "pruned": n_pruned,
                "expanded": n_expanded,
                "seconds": layer_dt,
                "refs_per_sec": (n_total / layer_dt) if layer_dt > 0 else None,
                "work_secs": work_secs_sum,
                "eff_parallelism": eff_parallelism,
            })
        if logger.isEnabledFor(logging.INFO):
            logger.info(f"[S2 L{d}] refs={n_total} kept={n_kept} pruned={n_pruned} expanded={n_expanded} "
                        f"in {layer_dt:.2f}s (eff_parallelism≈{eff_parallelism and f'{eff_parallelism:.1f}' or 'n/a'})")

        if delay > 0:
            time.sleep(delay)

    return nodes, edges

# ----------------------------------------------------------------------------- 
# Exporters
# -----------------------------------------------------------------------------
def write_csv_nodes(nodes: Dict[str, WorkNode], out_path: str):
    items = list(nodes.items())
    items.sort(key=lambda kv: str(kv[0]))
    fieldnames = [
        "key", "openalex_id", "doi", "title", "publication_year", "host_venue",
        "type", "authors", "cited_by_count", "is_retracted", "source", "s2_paper_id"
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for key, n in items:
            row = asdict(n)
            row = {"key": key, **row}
            w.writerow(row)

def write_csv_edges(edges: List[Tuple[str, str]], out_path: str):
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source_key", "target_key"])
        w.writerows(edges)

def write_json(nodes: Dict[str, WorkNode], edges: List[Tuple[str, str]], out_path: str):
    items = list(nodes.items())
    items.sort(key=lambda kv: str(kv[0]))
    data = {
        "nodes": [{"key": k, **asdict(v)} for k, v in items],
        "edges": [{"source": s, "target": t} for s, t in edges],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def write_graphml(nodes, edges, out_path):
    """
    Write a GraphML file that tools like Gephi/Cytoscape can ingest.
    GraphML is strict: no None values and consistent types per attribute.
    This function coerces/filters attributes to keep the writer happy.
    """
    import logging, networkx as nx

    log = logging.getLogger(__name__)

    # --- Define which attributes exist and what types they should be ---
    STRING_KEYS = {
        "id", "openalex_id", "s2_id", "doi", "title", "host_venue",
        "type", "authors", "source",
    }
    INT_KEYS = {"publication_year", "cited_by_count"}
    BOOL_KEYS = {"is_retracted"}

    EDGE_STRING_KEYS = set()   # if you ever add string edge attrs
    EDGE_INT_KEYS = {"depth"}  # current schema
    EDGE_BOOL_KEYS = set()

    # Helpers
    def _as_str(v):
        if v is None:
            return ""
        # forbid lists/dicts in GraphML
        if isinstance(v, (list, dict)):
            return ""
        return str(v)

    def _as_int(v):
        if v is None or v == "":
            return -1
        try:
            return int(v)
        except Exception:
            # last-resort: if it can't be parsed, mark as -1
            return -1

    def _as_bool(v):
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        # accept "true"/"false", "1"/"0"
        s = str(v).strip().lower()
        if s in {"1", "true", "yes", "y"}:
            return True
        if s in {"0", "false", "no", "n"}:
            return False
        return False

    def _clean_node_attrs(raw):
        """
        Return (node_id, attrs) with safe GraphML-friendly values.
        If node id can't be determined, return (None, None) to skip.
        """
        # pick a stable id
        nid = (
            raw.get("id")
            or raw.get("openalex_id")
            or (("S2:" + raw["s2_id"]) if raw.get("s2_id") else None)
        )
        if not nid:
            return None, None

        attrs = {}
        # strings
        for k in STRING_KEYS:
            if k in raw:
                attrs[k] = _as_str(raw.get(k))
        # ints
        for k in INT_KEYS:
            if k in raw:
                attrs[k] = _as_int(raw.get(k))
            else:
                # ensure consistent type across nodes
                attrs[k] = -1
        # bools
        for k in BOOL_KEYS:
            if k in raw:
                attrs[k] = _as_bool(raw.get(k))
            else:
                attrs[k] = False

        # Drop any unknown keys or complex types to avoid type conflicts
        return nid, attrs

    def _clean_edge_attrs(raw):
        """
        Return (src, dst, attrs) with safe types; skip edges with missing endpoints.
        """
        src = raw.get("src") or raw.get("src_openalex")
        dst = raw.get("dst") or raw.get("dst_openalex")
        if not src or not dst:
            return None, None, None

        # normalize S2-only endpoints if present in your graph as S2:... ids
        if src.startswith("W") is False and raw.get("src_s2") and not src.startswith("S2:"):
            src = "S2:" + raw["src_s2"]
        if dst.startswith("W") is False and raw.get("dst_s2") and not dst.startswith("S2:"):
            dst = "S2:" + raw["dst_s2"]

        attrs = {}
        for k in EDGE_STRING_KEYS:
            if k in raw:
                attrs[k] = _as_str(raw.get(k))
        for k in EDGE_INT_KEYS:
            if k in raw:
                attrs[k] = _as_int(raw.get(k))
            else:
                attrs[k] = -1
        for k in EDGE_BOOL_KEYS:
            if k in raw:
                attrs[k] = _as_bool(raw.get(k))
            else:
                attrs[k] = False
        return src, dst, attrs

    # Build a DiGraph (GraphML supports directed edges)
    G = nx.DiGraph()

    # (Optional) Graph-level metadata – must be strings/bools/ints only
    # If you have a global meta dict, coerce here similarly (no None!)
    # Example:
    # G.graph["seed"] = _as_str(meta.get("seed", ""))
    # G.graph["generated_at"] = _as_str(meta.get("generated_at", ""))

    # Add nodes
    skipped_nodes = 0
    for n in nodes:
        nid, attrs = _clean_node_attrs(n)
        if nid is None:
            skipped_nodes += 1
            continue
        G.add_node(nid, **attrs)
    if skipped_nodes:
        log.debug("GraphML: skipped %d nodes with no usable id", skipped_nodes)

    # Add edges
    skipped_edges = 0
    for e in edges:
        src, dst, attrs = _clean_edge_attrs(e)
        if src is None or dst is None:
            skipped_edges += 1
            continue
        G.add_edge(src, dst, **attrs)
    if skipped_edges:
        log.debug("GraphML: skipped %d edges with missing endpoints", skipped_edges)

    # Finally, write GraphML. If lxml is installed, NetworkX will use it automatically.
    try:
        nx.write_graphml(G, out_path)
    except Exception as ex:
        # Last-resort diagnostics: tell the user what to fix.
        log.error("Failed to write GraphML to %s: %s", out_path, ex)
        log.error(
            "Common causes: None values, mixed types for the same attribute, or list/dict values.\n"
            "Try installing lxml for a faster writer: `pip install lxml`."
        )
        raise


def quick_plot(nodes: Dict[str, WorkNode], edges: List[Tuple[str, str]], out_path: str):
    try:
        import networkx as nx
        import matplotlib.pyplot as plt
    except ImportError:
        print("networkx/matplotlib not installed; skipping plot.", file=sys.stderr)
        return
    G = nx.DiGraph()
    for key in nodes.keys():
        G.add_node(key)
    for s, t in edges:
        G.add_edge(s, t)
    plt.figure(figsize=(10, 10))
    pos = nx.spring_layout(G, k=0.4, seed=42)
    nx.draw_networkx_nodes(G, pos, node_size=40)
    nx.draw_networkx_edges(G, pos, arrows=False, width=0.5)
    ranked = sorted(nodes.items(), key=lambda kv: (kv[1].cited_by_count or 0), reverse=True)[:10]
    labels = {}
    for key, n in ranked:
        label = n.title or (n.openalex_id or key)
        if label and len(label) > 30:
            label = label[:30] + "…"
        labels[key] = label
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=7)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()

# ----------------------------------------------------------------------------- 
# CLI
# -----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Recursive reference crawler (OpenAlex + S2) — v1.4.1 pooled, rate-limited, cached, parallel.")
    ap.add_argument("reference", help="DOI, OpenAlex ID/URL, Semantic Scholar URL/ID, or title string")
    ap.add_argument("-d", "--depth", type=int, default=2, help="Reference depth (default: 2)")
    ap.add_argument("--email", default=os.getenv("OPENALEX_EMAIL"), help="Contact email for OpenAlex polite usage")
    ap.add_argument("--delay", type=float, default=0.2, help="Delay between BFS layers (seconds)")
    ap.add_argument("--cache", default=".openalex_cache.json", help="Path to JSON cache for OpenAlex ('' to disable)")
    ap.add_argument("--outprefix", default="sources", help="Prefix for output files")
    ap.add_argument("--graphml", action="store_true", help="Also write GraphML (requires networkx)")
    ap.add_argument("--plot", action="store_true", help="Also write quick PNG plot (requires networkx + matplotlib)")
    ap.add_argument("--source", choices=["auto", "openalex", "s2"], default="auto",
                    help="Reference expansion source: OpenAlex only, SemanticScholar (s2), or auto fallback")
    ap.add_argument("--keep-unmapped", action="store_true",
                    help="Keep unmapped S2 references as synthetic nodes (S2:*) instead of dropping them")
    ap.add_argument("--max-workers", type=int, default=8,
                    help="Max parallel worker threads for mapping/fetching (default: 8). Be polite!")
    ap.add_argument("--min-citations", type=int, default=0,
                    help="Minimum OpenAlex cited_by_count required to expand a node (default: 0)")
    ap.add_argument("--prune-below-threshold", action="store_true",
                    help="If set, nodes/edges below the threshold are removed entirely")
    ap.add_argument("--strict-threshold", action="store_true",
                    help="If set, drop nodes with unknown citation counts (e.g., S2-only or OA missing counts)")
    # Instrumentation
    ap.add_argument("--verbose", action="store_true", help="INFO logs")
    ap.add_argument("--debug", action="store_true", help="DEBUG logs with per-worker tasks")
    ap.add_argument("--progress", action="store_true", help="Show per-layer progress bars (requires tqdm)")
    ap.add_argument("--metrics-out", default="", help="Write crawl metrics to a JSON file at the end")
    # New: rate limiter & mapping cache path
    ap.add_argument("--oa-qps", type=float, default=3.0, help="Polite OpenAlex requests-per-second cap (default: 3.0)")
    ap.add_argument("--map-cache-path", default=".map_cache.json", help="Path to persistent S2→OA mapping cache")

    args = ap.parse_args()

    # Logging setup
    level = logging.WARNING
    if args.verbose:
        level = logging.INFO
    if args.debug:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(threadName)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("crawler")

    if args.progress and tqdm is None:
        logger.warning("--progress requested but tqdm is not installed; proceeding without progress bars.")

    if args.depth < 0:
        print("Depth must be >= 0", file=sys.stderr)
        sys.exit(2)
    cache_path = args.cache if args.cache else None

    # Configure rate limiter
    global _OA_QPS
    _OA_QPS = float(args.oa_qps) if args.oa_qps and args.oa_qps > 0 else 3.0
    logger.info(f"OpenAlex QPS cap set to {_OA_QPS:.2f}")

    # Load mapping cache
    global _MAP_CACHE_PATH
    _MAP_CACHE_PATH = args.map_cache_path
    _load_map_cache(_MAP_CACHE_PATH)

    # Wall clock start
    t_start = perf_counter()

    # Resolve OA seed
    try:
        seed_oa = oa_resolve_seed(args.reference, args.email, logger=logger)
    except Exception as e:
        print(f"Failed to resolve seed in OpenAlex: {e}", file=sys.stderr)
        sys.exit(1)

    # Decide source (auto fallback uses OA seed ref count)
    try:
        seed_work = oa_fetch_work(seed_oa, args.email, logger=logger)
    except Exception as e:
        print(f"Failed to fetch seed from OpenAlex: {e}", file=sys.stderr)
        sys.exit(1)
    oa_refs = seed_work.get("referenced_works") or []
    oa_ref_count = len(oa_refs)

    use_s2 = (args.source == "s2") or (args.source == "auto" and oa_ref_count < 10)
    seed_s2 = None
    if use_s2:
        seed_s2 = s2_find_seed(args.reference, args.email, logger=logger)
        if not seed_s2 and args.source == "s2":
            logger.warning("Could not find seed on Semantic Scholar; falling back to OpenAlex-only.")
            use_s2 = False

    # Crawl
    if use_s2:
        print(f"[info] Seed OA: {seed_oa} | Using Semantic Scholar expansion (seed S2: {seed_s2})")
        nodes, edges = crawl_references_via_s2(
            seed_oa_id=seed_oa,
            seed_s2_id=seed_s2 or "",
            depth=args.depth,
            email=args.email,
            delay=args.delay,
            cache_path=cache_path,
            keep_unmapped=args.keep_unmapped,
            max_workers=args.max_workers,
            min_citations=args.min_citations,
            prune_below=args.prune_below_threshold,
            strict_threshold=args.strict_threshold,
            logger=logger,
            progress=args.progress,
            map_cache_path=_MAP_CACHE_PATH
        )
    else:
        print(f"[info] Seed OA: {seed_oa} | Using OpenAlex-only (found {oa_ref_count} OA references on seed)")
        nodes, edges = crawl_references_openalex(
            seed_id=seed_oa,
            depth=args.depth,
            email=args.email,
            delay=args.delay,
            cache_path=cache_path,
            max_workers=args.max_workers,
            min_citations=args.min_citations,
            prune_below=args.prune_below_threshold,
            strict_threshold=args.strict_threshold,
            logger=logger,
            progress=args.progress
        )

    # Write outputs
    node_csv = f"{args.outprefix}_nodes.csv"
    edge_csv = f"{args.outprefix}_edges.csv"
    json_out = "graph.json"
    write_csv_nodes(nodes, node_csv)
    write_csv_edges(edges, edge_csv)
    write_json(nodes, edges, json_out)
    print(f"[done] Wrote {len(nodes)} nodes → {node_csv}")
    print(f"[done] Wrote {len(edges)} edges → {edge_csv}")
    print(f"[done] Wrote JSON graph → {json_out}")

    if args.graphml:
        graphml = "graph.graphml"
        write_graphml(nodes, edges, graphml)
        print(f"[done] Wrote GraphML → {graphml}")
    if args.plot:
        png = "graph.png"
        quick_plot(nodes, edges, png)
        print(f"[done] Wrote plot → {png}")

    # Wall clock end
    wall = perf_counter() - t_start
    with _METRICS_LOCK:
        _METRICS["wall_clock_seconds"] = wall

    # Metrics summary
    with _METRICS_LOCK:
        m = json.loads(json.dumps(_METRICS))  # shallow copy

    for bucket in ("openalex", "s2"):
        lat = m["requests"][bucket]["latencies"]
        if lat:
            logging.info(
                f"[metrics] {bucket} ok={m['requests'][bucket]['ok']} err={m['requests'][bucket]['err']} "
                f"avg={mean(lat):.3f}s p50={_percentile(lat,50):.3f}s p95={_percentile(lat,95):.3f}s"
            )
        else:
            logging.info(f"[metrics] {bucket} ok={m['requests'][bucket]['ok']} err={m['requests'][bucket]['err']}")

    if m["layers"]:
        logging.info("[metrics] layers summary:")
        for L in m["layers"]:
            rps = f"{L['refs_per_sec']:.1f}" if L["refs_per_sec"] is not None else "n/a"
            ep = f"{L['eff_parallelism']:.1f}" if L["eff_parallelism"] is not None else "n/a"
            logging.info(
                f" - {L['engine']} depth={L['depth']} refs={L['total_refs']} kept={L['kept']} "
                f"pruned={L['pruned']} expanded={L['expanded']} secs={L['seconds']:.2f} "
                f"rps={rps} eff_parallelism≈{ep}"
            )

    logging.info(f"[metrics] wall_clock_seconds={wall:.2f}")

    if args.metrics_out:
        try:
            with open(args.metrics_out, "w", encoding="utf-8") as f:
                json.dump(m, f, ensure_ascii=False, indent=2)
            logging.info(f"[metrics] wrote → {args.metrics_out}")
        except Exception as e:
            logging.warning(f"[metrics] failed to write {args.metrics_out}: {e}")

if __name__ == "__main__":
    main()
