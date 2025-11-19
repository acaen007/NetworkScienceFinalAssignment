# ManyWorlds: Exploring Scientific Knowledge Through Citation Networks

## Research Question

**How can citation network analysis reveal the intellectual structure and evolution of scientific fields, and how can we present these networks to make scientific knowledge more accessible and navigable?**

### Importance

Scientific knowledge is embedded in complex networks of citations, collaborations, and conceptual relationships. Traditional reading of papers is linear and time-intensive, making it difficult to understand:
- How ideas propagate through a field
- Which papers serve as critical bridges between research communities
- The evolution of scientific discourse over time
- Conflicting viewpoints and alternative perspectives on the same topic

By applying network science methods to bibliographic data, we can extract structural patterns that reveal the hidden organization of scientific knowledge. This has implications for:
- **Education**: Helping students understand how fields develop
- **Research**: Identifying gaps, influential works, and emerging trends
- **Science Communication**: Making complex research landscapes accessible to broader audiences

---

## Networks to be Extracted

### 1. **Citation Network (Primary)**
- **Nodes**: Scientific papers/publications
- **Edges**: Directed citations (Paper A → Paper B means A cites B)
- **Node Attributes**: Title, authors, publication year, venue, citation count, DOI
- **Analysis Focus**: 
  - Centrality measures (degree, betweenness, PageRank) to identify influential papers
  - Community detection to find research clusters
  - Temporal analysis of citation patterns
  - Path analysis to trace idea propagation

### 2. **Co-citation Network**
- **Nodes**: Papers
- **Edges**: Papers that are cited together (co-cited by the same papers)
- **Purpose**: Reveals conceptual similarity and research communities

### 3. **Author Collaboration Network** (Future Extension)
- **Nodes**: Researchers/authors
- **Edges**: Co-authorship relationships
- **Purpose**: Map social structure of scientific communities

### 4. **Bipartite Paper-Topic Network** (Future Extension)
- **Nodes**: Papers and Topics/Themes
- **Edges**: Papers connected to topics they address
- **Purpose**: Map thematic structure and interdisciplinary connections

---

## Datasets

### Primary Data Sources

1. **OpenAlex API**
   - Comprehensive bibliographic database with stable IDs
   - Provides: paper metadata, citation counts, referenced works, author information
   - Coverage: Strong for modern publications, DOI-based works
   - **Use**: Primary source for citation edges and node attributes

2. **Semantic Scholar API**
   - Enhanced coverage for arXiv-heavy fields and older papers
   - Provides: Additional references, paper embeddings, author networks
   - Coverage: Strong for physics, mathematics, computer science (especially pre-2000s)
   - **Use**: Fallback for reference expansion when OpenAlex coverage is sparse

### Data Collection Strategy

- **Seed Papers**: Start with landmark papers in a chosen domain (e.g., "The Large N Limit of Superconformal Field Theories and Supergravity" for string theory)
- **Breadth-First Crawl**: Recursively collect references up to depth 2-3
- **Normalization**: Map all papers to OpenAlex IDs for consistency
- **Output Formats**: CSV (nodes/edges), JSON (full graph), GraphML (for visualization tools)

### Example Domain

For initial analysis, we focus on **theoretical physics** (string theory, quantum gravity) because:
- Rich citation networks with clear historical evolution
- Mix of modern and classic papers (tests our dual-source approach)
- Well-documented intellectual lineages
- Clear examples of competing viewpoints

---

## Plan of Work

### Phase 1: Network Construction (Weeks 1-2)
**Objective**: Build citation networks from bibliographic data

**Tasks**:
1. Select 3-5 seed papers representing different perspectives/themes
2. Run reference crawler (existing `crawl_references.py` tool) for each seed
3. Merge networks, deduplicate nodes, validate edge directions
4. Export clean node/edge lists with metadata
5. **Deliverable**: Validated citation network dataset (CSV/GraphML)

**Team Assignment**: 
- Person A: Configure crawler, run data collection
- Person B: Data cleaning, deduplication, validation

### Phase 2: Network Analysis (Weeks 3-4)
**Objective**: Compute network metrics and identify structural patterns

**Tasks**:
1. Load network into analysis tool (NetworkX, igraph, or Gephi)
2. Compute centrality measures:
   - Degree centrality (most cited/citing papers)
   - Betweenness centrality (bridge papers)
   - PageRank (influence accounting for citation quality)
3. Community detection (modularity, Louvain algorithm)
4. Temporal analysis: citation patterns by publication year
5. Identify key papers, clusters, and structural holes
6. **Deliverable**: Analysis report with visualizations and key findings

**Team Assignment**:
- Person A: Centrality and influence analysis
- Person B: Community detection and clustering
- Person C: Temporal analysis and visualization

### Phase 3: Interpretation & Storytelling (Weeks 5-6)
**Objective**: Translate network structure into accessible narratives

**Tasks**:
1. Map network clusters to research themes/traditions
2. Identify "conflicting views" (papers in different communities on same topic)
3. Trace intellectual lineages (citation paths from foundational to recent work)
4. Create narrative summaries explaining network structure
5. Design user-facing visualizations (force-directed layouts, timeline views)
6. **Deliverable**: Interpretive document + visualization mockups

**Team Assignment**:
- Person A: Thematic mapping and conflict identification
- Person B: Lineage tracing and narrative writing
- Person C: Visualization design and mockups

### Phase 4: Interactive Presentation (Weeks 7-8)
**Objective**: Build web interface for exploring the network

**Tasks**:
1. Implement network visualization (D3.js, vis.js, or Cytoscape.js)
2. Add filtering (by year, author, community)
3. Create detail views for individual papers
4. Implement search and navigation features
5. Add "Views" content (interpretive summaries) linked to network nodes
6. **Deliverable**: Functional web prototype

**Team Assignment**:
- Person A: Backend API and data serving
- Person B: Frontend visualization and interaction
- Person C: Content integration and UX polish

### Phase 5: Documentation & Presentation (Week 9)
**Objective**: Prepare final deliverables

**Tasks**:
1. Write project report documenting methodology and findings
2. Create presentation slides
3. Record demo video of interactive prototype
4. **Deliverable**: Final report, presentation, demo

**Team Assignment**: All members contribute to documentation

---

## Expected Outcomes

1. **Network Dataset**: Clean citation network with 200-500 nodes (papers) and 300-800 edges (citations)
2. **Analysis Results**: Identification of influential papers, research communities, and structural patterns
3. **Interactive Prototype**: Web application allowing users to explore the network
4. **Insights**: Understanding of how citation networks reveal intellectual structure in the chosen domain

---

## Success Metrics

- **Network Quality**: High coverage of seed domain, minimal missing references
- **Analysis Depth**: Clear identification of communities, influential nodes, and temporal patterns
- **Usability**: Users can navigate network and understand relationships without domain expertise
- **Novelty**: Insights that wouldn't be obvious from reading papers individually

