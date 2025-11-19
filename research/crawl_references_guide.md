# crawl_references.py — Deep Reference Tracing (Design & Operator's Guide)

**Version:** v1.4.x line  
**Maintainers:** you 🙂  
**Purpose:** Given a seed paper, build a recursive graph of its sources ("references of references"), enriched with metadata, and export it as CSV + JSON, optionally rendering a PNG network diagram.

## 0) TL;DR (How to run)

### Basic (depth 1, OpenAlex only)
```bash
python crawl_references.py "The Large N Limit of Superconformal Field Theories and Supergravity" -d 1
```

### Deep, fast, and polite: OpenAlex + Semantic Scholar, parallel, pruned
```bash
python crawl_references.py "The Large N Limit of Superconformal Field Theories and Supergravity" \
  -d 2 --source both \
  --max-workers 12 --oa-qps 12 --s2-qps 3 \
  --min-citations 50 --prune-below-threshold \
  --png-out graph.png --dot-out graph.dot \
  --debug --progress --metrics-out crawl_metrics.json
```

### Outputs (in the working directory unless changed):
- **sources_nodes.csv** — node table (papers)
- **sources_edges.csv** — edges (citations)
- **graph.json** — full graph (nodes + edges)
- **(optional) graph.dot + graph.png** — Graphviz diagram
- **(optional) crawl_metrics.json** — performance + throughput metrics

## 1) High-Level Flow

### Seed Resolution
The script takes a seed reference (title, DOI, or OpenAlex ID) and resolves it to a canonical OpenAlex work ID (OA), optionally also a Semantic Scholar paper ID (S2).
- Prefers DOI lookup
- Falls back to title search (and title+year if nudged by S2)
- Contains heuristics to avoid wasted calls (e.g., "journal-only" strings)

### Layered Expansion (BFS by depth)
We build the graph by layers:
- **L0:** the seed
- **L1:** seed's references
- **L2:** references of L1, etc.

At each layer, references are fetched (OpenAlex and/or S2), filtered, mapped, and optionally expanded to the next layer.

### Mapping (S2 → OpenAlex)
Many references come from S2 with partial metadata. We map them to OpenAlex IDs using:
- DOI (exact), then DOI fuzzy, then title, then title+year
- ArXiv normalization and journal-only filtering reduce noise

### Pruning
References below a citations threshold (e.g., `--min-citations 50`) can be skipped entirely (no expansion and optionally no node). This saves time and avoids low-signal nodes.

### Parallelism + Rate-Limiting
All mapping/fetching tasks run with a thread pool (`--max-workers`). QPS caps per API keep you polite and avoid 429s.

### Export
We write:
- Nodes/edges CSV
- JSON graph (for programmatic downstream)
- Optional rendered graph (DOT/PNG)

### Metrics + Logs
We measure per-API latencies, errors, throughput per layer, effective parallelism, and wall time. Logs help you understand what each worker is doing.

## 2) Data Sources

### OpenAlex
- Workhorse for canonical IDs and metadata (title, year, venue, authors, citation counts, retraction status)
- **Endpoints:** `/works`, `/works/{id}`
- **Access:** no key required. A mailto query param is set when provided (`--mailto` or env var) to be a good citizen
- **QPS:** controlled by `--oa-qps`

### Semantic Scholar (S2 Graph API)
- Rich reference lists (often better coverage for older literature)
- **Endpoint:** `/graph/v1/paper/{paperId}?fields=references.paperId,references.title,references.year,references.externalIds,references.authors`
- **Access:** key optional; unauthenticated works but is rate-limited
- **QPS/timeouts:** controlled by `--s2-qps`, `--s2-timeout`, retries/backoff flags

**Why both?** S2 is great for who cites whom; OpenAlex is great for normalized identifiers + metadata. We combine them.

## 3) CLI Flags (Most-used)

### Core
- **SEED** (positional): title, DOI, or OpenAlex ID
- `-d, --depth N`: reference depth to explore (0 = seed only)
- `--source {openalex|s2|both}`: where to expand references from
- `--min-citations K`: drop refs with < K citations
- `--prune-below-threshold`: prune low-citation refs entirely (no node, no expansion)
- `--keep-unmapped`: keep S2-only nodes when OA mapping fails (coverage > speed)

### Performance
- `--max-workers N`: number of threads (typical: 8–16)
- `--oa-qps X.Y`: OpenAlex queries per second cap (start 6–12)
- `--s2-qps X.Y`: S2 queries per second cap (start 2–4)
- `--s2-timeout SECS`, `--s2-retries N`, `--s2-backoff S`, `--s2-jitter R`

### UX / Output
- `--debug`: verbose per-request logging (thread-tagged)
- `--progress`: live progress bars for each layer
- `--metrics-out FILE`: dump a JSON performance report
- `--png-out FILE`, `--dot-out FILE`: render a Graphviz diagram
- `--outdir DIR`: redirect CSV/JSON/PNG outputs to a folder

### Networking etiquette
- `--mailto you@domain.tld`: passed to OpenAlex as `mailto=...`
- **(Optional)** `S2_API_KEY` env var if you have one

## 4) Outputs (Schemas)

### 4.1 sources_nodes.csv

Columns (stable core; additional fields may appear as the script evolves):

| column | type | description |
|--------|------|-------------|
| openalex_id | string | W######### (or empty if S2-only and unmapped) |
| doi | string | DOI URL if known |
| title | string | Paper/book title |
| publication_year | int | Year |
| host_venue | string | Journal/venue (if available) |
| type | string | article, book, dataset, etc. |
| authors | string | Comma-separated author names |
| cited_by_count | int | OpenAlex citation count |
| is_retracted | bool | From OpenAlex |
| source | string | openalex or s2 (if --keep-unmapped) |
| s2_id | string | Semantic Scholar ID (if available) |

**Tip:** exact headers: open the file; we keep backwards compatibility but add fields as features grow.

### 4.2 sources_edges.csv

| column | type | description |
|--------|------|-------------|
| src_openalex | string | Citing paper (OpenAlex ID or S2 synth key) |
| dst_openalex | string | Cited paper (OpenAlex ID or S2 synth key) |
| depth | int | Edge layer (1 means seed → its refs) |
| src_s2 | string | Optional, if --keep-unmapped |
| dst_s2 | string | Optional, if --keep-unmapped |

### 4.3 graph.json

Lightweight structure you can feed to notebooks/visualizers:

```json
{
  "nodes": [{"id":"W4249956767","title":"...", "year":1998, ...}, ...],
  "edges": [{"src":"W424...","dst":"W2054...","depth":1}, ...],
  "meta": {"seed":"...", "depth":2, "generated_at":"..."}
}
```

### 4.4 graph.dot + graph.png

DOT is the Graphviz source; PNG is an automatically rendered layout.
- Node labels default to a short title/year
- Layout uses sfdp (good for larger graphs)

## 5) Internals & Key Components

### 5.1 Scheduler & Concurrency
- A `ThreadPoolExecutor` drives parallel fetch/mapping tasks
- A token bucket per API enforces QPS caps (`--oa-qps`, `--s2-qps`)
- **Retries:** HTTP status-based (429/5xx) with exponential backoff + jitter
- **Effective parallelism** is computed per layer as:
  ```
  eff_parallelism = sum(task_durations) / wall_clock_seconds_for_layer
  ```
  Logged as `eff_parallelism≈7.5` etc.

### 5.2 Layered Expansion (BFS)

For depth = D:
- **L0:** seed
- For each Lk (k < D):
  - Fetch references (S2 and/or OpenAlex)
  - Normalize/clean each reference (try DOI, arXiv, title)
  - Prune (by citations threshold)
  - Map to OA and enqueue survivors for next layer

A layer completes when all mapped refs have been processed.

**Log anatomy** (examples you saw):
```
INFO [MainThread] [S2 L1] refs=40 kept=10 pruned=30 expanded=7 in 7.90s (eff_parallelism≈7.0)
```

- **refs:** references encountered in that wave
- **kept:** survived pruning and mapping
- **pruned:** removed (citation threshold, low-info, etc.)
- **expanded:** how many of the kept were expanded (i.e., fetched at next layer)
- **in 7.90s:** wall time for that wave
- **eff_parallelism≈7.0:** realized speedup vs single-thread

### 5.3 Mapping (S2 → OpenAlex)

Order of attempts (short-circuits on success):
1. **Exact DOI:** `GET /works?filter=doi:<doi>`
2. **DOI fuzzy:** `GET /works?search=<doi>`
3. **Title:** `GET /works?search=<title>`
4. **Title+Year:** `GET /works?search="<title> <year>"`

**Heuristics:**
- Skip "journal-only" strings (e.g., "Phys. Rev. Lett", "Nucl. Phys. B", roman numerals, etc.)
- Normalize arXiv: `hep-th/9709099` → `arXiv:hep-th/9709099`
- Cache hits/misses by DOI, S2 ID, and lowercased title (prevents repeated API calls)

**What does `OA:∅` mean?**  
A mapping attempt yielded an empty set (OpenAlex had no match). You'll still keep the S2 node if you passed `--keep-unmapped`.

### 5.4 Pruning

Two independent stages:

1. **Pre-mapping S2 prune (optional)**  
   If S2 provides citationCount, refs below `--min-citations` can be removed before any OpenAlex calls (saves time).

2. **Post-mapping OA prune**  
   After mapping to OA, we retrieve `cited_by_count` and prune those below the threshold if `--prune-below-threshold` is on.

`--min-citations` sets the numeric threshold; `--prune-below-threshold` turns pruning on. Without the latter, low-citation nodes are kept but not expanded.

## 6) Logging Guide (What those lines mean)

### Per-request debug
```
DEBUG [ThreadPoolExecutor-5_3] GET openalex https://api.openalex.org/works 200 in 1.662s
```
The worker thread made a call; status and latency logged.

### Backoff
```
INFO [ThreadPoolExecutor-31_7] Backoff openalex 429 (attempt 2)
```
Rate limit or transient; we paused and will retry with exponential backoff + jitter.

### S2→OA map
```
DEBUG [ThreadPoolExecutor-7_2] [L1] map S2→OA done in 0.748s — OA:∅ — Black and super p-branes in diverse dimensions
```
Attempted mapping for a single S2 ref; `OA:∅` = OpenAlex match not found.

### Layer summary
```
INFO [MainThread] [S2 L1] refs=40 kept=10 pruned=30 expanded=6 in 3.18s (eff_parallelism≈7.8)
```
See section 5.2.

### Metrics block
```
INFO [MainThread] [metrics] openalex ok=98 err=0 avg=1.366s p50=1.574s p95=1.818s
```
Aggregated latencies & success/error counts per service. Full JSON is in `crawl_metrics.json` if you specified `--metrics-out`.

## 7) Performance Tuning

- **Workers:** `--max-workers 8–16` is usually the sweet spot on a laptop
- **QPS caps:**
  - **OpenAlex:** start at `--oa-qps 8–12` (watch for 429s; if none, you can bump slightly)
  - **S2:** `--s2-qps 2–4` to avoid long tails + retries
- **Prune early:** the higher your `--min-citations`, the fewer low-signal nodes and less mapping work
- **Avoid low-info searches:** the strengthened journal-only detector saves calls
- **Keep S2-only nodes** when you want coverage (`--keep-unmapped`), skip them for speed

## 8) Typical Workflows

### Fast overview, shallow depth
```bash
python crawl_references.py "..." -d 1 --source both --max-workers 10 --oa-qps 10 --min-citations 20 \
  --prune-below-threshold --progress --debug
```

### Paper-quality figure (graph image)
```bash
python crawl_references.py "..." -d 2 --source both \
  --png-out refs.png --dot-out refs.dot
```
Open `refs.png`. Use DOT (`refs.dot`) for custom layouts downstream.

### Benchmarking
```bash
python crawl_references.py "..." -d 2 --source both \
  --max-workers 12 --oa-qps 12 --s2-qps 3 \
  --metrics-out crawl_metrics.json --debug
```
Inspect `crawl_metrics.json` for latency histograms and `eff_parallelism`.

## 9) Troubleshooting & FAQ

**"Why do I see many `OA:∅`?"**  
Old references (90s HEP) often list venues or arXiv IDs. We now skip low-info titles and normalize arXiv, but some items genuinely don't map. Use `--keep-unmapped` if you need coverage.

**"S2 400: unrecognized fields"**  
Use fields exactly as:
```
references.paperId,references.title,references.year,references.externalIds,references.authors
```
Older `references.authors.name` causes 400; avoid it.

**"I hit OpenAlex 429s."**  
Lower `--oa-qps` or add `--delay` if you've customized the token bucket. Make sure you pass `--mailto`.

**"Graph is too dense / too sparse."**  
Raise/lower `--min-citations`. Consider `-d 1` for legible figures, `-d 2` for analysis.

**"PNG missing or empty."**  
Ensure `graph.json` has nodes/edges. Check Graphviz is available in your environment if using system dot; otherwise the script's pure-Python rendering path will be used (slower for huge graphs).

## 10) Design Choices (Why we did it this way)

- **Hybrid S2 + OpenAlex** to balance coverage (references) and normalization (metadata)
- **BFS by depth** makes expansion predictable and metrics meaningful per layer
- **Aggressive caching & heuristics** (DOI-first, title+year fallback, skip journal-only strings) to cut wasted calls
- **Polite QPS controls** with backoff/jitter to play nicely with public APIs
- **Self-instrumentation** (metrics + eff_parallelism) so you can see parallel speedups and bottlenecks

## 11) Extending the Script

- **Add sources:** Crossref, arXiv, INSPIRE-HEP for even better legacy HEP coverage
- **Enrich nodes:** abstracts, fields of study, affiliations, OA PDFs
- **Export adapters:** Gephi (GEXF), Cytoscape (CX), Neo4j importers
- **Ranking:** weighted edges by recency/venue; centrality metrics on output

## 12) Known Limitations

- Legacy & ambiguous refs (e.g., venue-only strings) will never map perfectly
- Citation counts differ between providers; we standardize on OpenAlex where possible
- ArXiv → DOI is incomplete in public APIs for older items
- Rendering large graphs as PNG is best-effort; use DOT + Gephi for >5k nodes

## 13) Glossary of Log Terms

- **`OA:W#########`** — OpenAlex work id found
- **`OA:∅`** — No OpenAlex match
- **`Backoff openalex 429 (attempt N)`** — rate limited; retry with backoff+jitter
- **`[S2 Lk] refs=K kept=A pruned=B expanded=C`** — layer summary for S2-sourced expansion
- **`eff_parallelism≈X.Y`** — realized speedup for that wave (sum task time / wall time)
- **`requests.openalex ok=... err=... avg=... p50=... p95=...`** — service-level performance stats

## 14) Reproducibility Notes

- The script emits version and generated_at in `graph.json`
- Record command-line and env (especially `--mailto`, `S2_API_KEY`)
- API responses shift over time; pin depth, threshold, and sources for consistent shape

## 15) Safety & Etiquette

- Provide a mailto to OpenAlex
- Keep QPS within reasonable limits; increase gradually while monitoring 429s
- Respect robots/ToS of upstream APIs; cache locally where permitted

## 16) Appendix — Reading crawl_metrics.json

Example shape:

```json
{
  "requests": {
    "openalex": { "ok": 98, "err": 0, "latencies": [ "... seconds ..." ] },
    "s2":       { "ok": 15, "err": 4, "latencies": [ "... seconds ..." ] }
  },
  "layers": [
    {
      "engine": "s2",
      "depth": 0,
      "total_refs": 46,
      "kept": 14,
      "pruned": 32,
      "expanded": 14,
      "seconds": 3.79,
      "refs_per_sec": 12.15,
      "work_secs": 28.43,
      "eff_parallelism": 7.51
    }
  ],
  "wall_clock_seconds": 53.47
}
```

- **latencies** are per-call durations; use to eyeball tails
- **work_secs** sums task durations in the wave; divided by seconds yields effective parallelism
- **refs_per_sec** = `total_refs / seconds` → throughput per wave
- Compare runs (different workers/QPS) by `wall_clock_seconds` and `err` counts

## 17) Example Commands (Copy/Paste)

### Maximum coverage at depth 2; keep S2-only nodes; save PNG
```bash
python crawl_references.py "The Large N Limit of Superconformal Field Theories and Supergravity" \
  -d 2 --source both \
  --max-workers 12 --oa-qps 10 --s2-qps 3 \
  --keep-unmapped \
  --png-out refs.png --dot-out refs.dot \
  --progress --metrics-out crawl_metrics.json
```

### Speed run; prune aggressively; rich logs
```bash
python crawl_references.py "The Large N Limit of Superconformal Field Theories and Supergravity" \
  -d 2 --source both \
  --max-workers 12 --oa-qps 12 --s2-qps 3 \
  --min-citations 50 --prune-below-threshold \
  --debug --progress --metrics-out crawl_metrics.json
```

### Quiet, shallow
```bash
python crawl_references.py "The Large N Limit of Superconformal Field Theories and Supergravity" -d 1
```

---

**Happy tracing!** If you're extending the mapper or adding a new provider, keep an eye on: DOI-first, skip low-info, title+year fallback, and caching. Those four rules carry most of the performance and quality.