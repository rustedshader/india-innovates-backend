# Global Ontology Engine — Architecture Plan

## Vision

An AI-powered intelligence graph that ingests global news, extracts entities and their typed relationships, resolves them across sources, tracks temporal state changes, and enables conversational querying over the knowledge graph. The graph powers strategic Q&A, automated report generation, real-time anomaly detection, news prioritisation, and India-focused weather monitoring for decision-makers.

---

## Pipeline Architecture

The system runs as **six independent processes** (Docker-ready):

```
                           ┌──────────────┐
                           │  Redis       │  URL dedup + cluster centroids
                           │              │  + live-feed pub/sub + alerts
                           └──────┬───────┘
                                  │ SISMEMBER / SADD / PUBLISH
┌─────────────────────────────────┼───────────────────────────────────────┐
│  PRODUCER  (scheduler/producer.py)         every 30min (configurable)  │
│                                                                       │
│  RSS Feeds ──▶ Scraper ──▶ Extract full text ──▶ Publish to Kafka     │
└───────────────────────────────┬───────────────────────────────────────┘
                                │ Article JSON
                                ▼
                     ┌─────────────────────┐
                     │   Kafka Topic       │
                     │   india-innovates   │
                     └──────────┬──────────┘
                                │ consume (batched)
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  CONSUMER  (scheduler/consumer.py)                  runs continuously  │
│                                                                       │
│  Stage A: NewsPriorityAgent.process(batch)                            │
│  ┌───────────────────────────────────────────────────────────────┐     │
│  │  Embed (MiniLM) → Cluster (Redis) → Score (LLM) → Postgres  │     │
│  │  Returns high-importance subset (≥5.0 score)                  │     │
│  └───────────────────────┬───────────────────────────────────────┘     │
│                          ▼                                            │
│  Stage B: GraphBuilder.process_articles(high_importance_batch)         │
│  ┌───────────────────────────────────────────────────────────────┐     │
│  │              Extraction Agent (hybrid)                        │     │
│  │  GLiNER2 (NER+RE) ──▶ LLM Canonicalization ──▶ LLM Enrich   │     │
│  └───────────────────────┬───────────────────────────────────────┘     │
│                              ▼                                        │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐   │
│  │ Resolution Agent │──▶│ Temporal Agent   │──▶│ Batched UNWIND   │   │
│  │ (3-Tier Funnel)  │   │ (stub)           │   │ Neo4j + Postgres │   │
│  └──────────────────┘   └──────────────────┘   └──────────────────┘   │
│                                                                       │
│  Publish live-feed events for ALL articles → Redis pub/sub            │
└───────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  SIGNAL WORKER  (scheduler/signal_worker.py)          every 15min     │
│                                                                       │
│  Signal A: Entity mention spikes (Neo4j 7-day same-day baseline)      │
│  Signal B: New high-connectivity entities (Neo4j degree check)        │
│  Signal C: Topic cluster spikes (Postgres 7-day baseline)             │
│  → Save to Postgres (detected_signals) with 6h TTL                    │
└───────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  API SERVER  (main.py)                                                 │
│                                                                       │
│  /api/graph ──▶ Visualization (vis-network.js)                        │
│  /api/graph/stats ──▶ Aggregate graph counts by type                  │
│  /entities/{name}/timeline ──▶ Entity timeline with co-entities       │
│  /api/chat ──▶ Chat Agent (LangGraph Graph RAG)                       │
│  /api/reports ──▶ Domain intelligence reports                         │
│  /api/news ──▶ Prioritised article feed + trending topics             │
│  /api/signals ──▶ Real-time anomaly signals                           │
│  /api/weather/* ──▶ Weather monitoring (25 Indian cities)             │
│  /ws/live-feed ──▶ WebSocket real-time article stream                 │
│  / ──▶ Interactive vis-network.js frontend                            │
└───────────────────────────────────────────────────────────────────────┘
```

---

## Neo4j Schema

### Nodes

| Label    | Key Properties                                      |
|----------|-----------------------------------------------------|
| Entity   | name, type, first_seen, last_updated                |
| Event    | name, date, status (ongoing/concluded)              |
| Article  | url, title, source, pub_date                        |

### Entity Types

Person, Organization, Country, Location, Event, Policy, Technology, Economic_Indicator, Military_Asset, Resource

### Relationships

| Pattern                                    | Properties                                    |
|--------------------------------------------|-----------------------------------------------|
| (Entity)-[:RELATES_TO]->(Entity)           | type (verb phrase), since, confidence, causal, current |
| (Entity)-[:INVOLVED_IN]->(Event)           |                                               |
| (Article)-[:EVIDENCES]->(Entity)           |                                               |
| (Article)-[:EVIDENCES]->(Event)            |                                               |
| (Article)-[:EVIDENCES_REL]->(Entity)       | relation_type                                 |

Note: Entity-to-Entity relationships are stored as `:RELATES_TO` edges with a `type`
property holding the verb phrase (e.g. `r.type = "sanctions"`), NOT as dynamic
relationship types.

Relationship types are from a **fixed vocabulary** of 26 geopolitical relation types (extracted by GLiNER2):
- `sanctions`, `allied_with`, `opposes`, `trades_with`, `supplies_to`, `invaded`,
  `leads`, `founded`, `acquired`, `located_in`, `manufactures`, `funds`,
  `threatens`, `negotiates_with`, `member_of`, `disrupts`, `signed_agreement_with`,
  `deployed_to`, `develops`, `exports_to`, `imports_from`, `cooperates_with`,
  `competes_with`, `attacks`, `blocks`, `supports`

Fixed types enable consistent querying and cross-article aggregation.

Every edge traces back to source articles via EVIDENCES. Click any entity/relationship → see all supporting articles.

---

## Stage 1: Extraction Agent (Hybrid GLiNER2 + LLM)

Three-phase extraction per article. GLiNER2 handles the mechanical extraction,
a lightweight LLM call canonicalizes entity names, and a second LLM call handles reasoning.

### Phase A: GLiNER2 — NER + Relation Extraction (~50ms/article, CPU)

- **Entity extraction**: 9 typed labels with descriptions (Person, Organization,
  Country, Location, Policy, Technology, Economic_Indicator, Military_Asset, Resource)
- **Relation extraction**: 26 geopolitical relation types with descriptions
- Combined schema, single forward pass, 205M params
- **Grounded in text spans** — zero hallucinated entity names
- Returns entities with confidence scores and relations as (head, tail) tuples

### Phase B: LLM — Entity Canonicalization + Type Correction (lightweight, ~500 tokens round-trip)

GLiNER2 is a span-matcher — it returns raw text spans verbatim ("Trump", "the US",
"PLA"). It **cannot reason** about canonical names or generate aliases. It also
misclassifies entity types at low confidence (e.g. "Dehradun" as Country, "US Senate" as Country).

This phase sends entity names **with GLiNER2 confidence scores** + article title to the LLM:
1. **Canonical names**: "Trump" → "Donald Trump", "the US" → "United States"
2. **Aliases**: "People's Republic of China" → aliases: ["PRC", "China"]
3. **Confidence-based type correction**: For entities where GLiNER2 confidence < 0.80,
   the LLM verifies and corrects the entity type (e.g. "Indian Ocean" Country→Location,
   "United States Senate" Country→Organization). High-confidence types are trusted
   unless clearly wrong.

Relation source/target names are updated to match the new canonical names.
This is a very cheap call — just a list of short names, no article text needed.

### Phase C: LLM — Events + Enrichment (reasoning tasks)

Given the canonicalized entities and relations, the LLM:
1. **Causal flags**: For each relation, is it cause-effect? ("because", "in response to")
2. **Temporal markers**: Attach dates/periods to relations ("2024-03", "ongoing")
3. **Event extraction**: Named events with status and involved entities (max 5)

This is a much simpler task — the LLM doesn't discover entities or relations,
it just reasons about them.

### Output

```python
class ExtractedEntity:
    name: str              # canonical name (from LLM Phase B)
    type: str              # entity type (corrected by LLM if low confidence)
    aliases: list[str]     # from LLM Phase B
    confidence: float      # GLiNER2 NER confidence (0.0–1.0)

class ArticleExtraction:
    entities: list[ExtractedEntity]     # from GLiNER2, canonicalized by LLM
    relations: list[ExtractedRelation]   # from GLiNER2 + LLM enrichment
    events: list[ExtractedEvent]         # from LLM
```

### Why hybrid?

| Aspect              | Before (LLM-only)       | After (GLiNER2 + LLM)         |
|---------------------|-------------------------|-------------------------------|
| Entity speed        | ~5s/article (LLM)       | ~50ms/article (GLiNER2)       |
| Entity grounding    | Hallucination-prone     | Text-span grounded            |
| Canonical names     | Good (LLM reasons)      | GLiNER2 raw spans → LLM canonicalization |
| Aliases             | Good (LLM generates)    | GLiNER2 can't → LLM generates |
| Type accuracy       | Good (LLM reasons)      | GLiNER2 confidence-gated → LLM corrects low-confidence types |
| Relation extraction | LLM (slow, inconsistent)| GLiNER2 (fast, fixed vocab)   |
| Events / causality  | LLM                     | LLM (focused, simpler prompt) |
| Total per article   | ~8s                     | ~3-4s (50ms + 2 LLM calls)   |

---

## Stage 2: Entity Resolution — 3-Tier Funnel

### Tier 1: Deterministic Normalization (O(N), no LLM)

1. Normalize: lowercase, strip punctuation, collapse whitespace
2. Alias table: maintained in Postgres (`entity_aliases`), seeded with common geopolitical aliases, grows over time
3. Acronym expansion: if both "NATO" and "North Atlantic Treaty Organization" exist → merge
4. LLM-provided aliases: extraction already provides aliases per entity
5. Context-type gating: aliases can be type-scoped (`context_type` column) — e.g. "Georgia" resolves to "Georgia (state)" only when type=Location

Note: Substring containment merging (e.g. "Trump" → "Donald Trump") was removed —
it caused false merges (e.g. "India" → "Indian Ocean"). Short-to-long name merging
is now handled by LLM canonicalization in Phase B, which has article context and
confidence scores to make correct decisions.

Handles ~60-70% of duplicates.

### Tier 2: Embedding Similarity + ANN (O(N log N), no LLM)

1. Embed entity names using sentence-transformers (`all-MiniLM-L6-v2`, 80MB, CPU)
2. Block by entity type first (only compare Person↔Person, etc.) — 8x reduction
3. FAISS ANN index per type block
4. Thresholds:
   - cosine > 0.95 → auto-merge
   - cosine 0.80-0.95 → candidate pair for Tier 3
   - cosine < 0.80 → different

### Tier 3: LLM Disambiguation (O(K), K << N)

Batch 20-30 candidate pairs per LLM call:
```
Which pairs refer to the same real-world entity?
1. "Bank of China" (Organization) vs "People's Bank of China" (Organization)
2. "Georgia" (Country) vs "Georgia" (Location)
...
```

### Persistent Merge Table

Stored in Postgres (`entity_aliases` table). Once resolved, never re-evaluated. New batches check table first (O(1) lookup). Supports typed and untyped aliases via the `context_type` column.

### Bonus: Graph-Based Resolution

After all tiers, Neo4j structural similarity:
- Same type + 3+ shared neighbors + never co-occur in same article → likely same entity

---

## Stage 3: Temporal Agent

Attaches time dimension to entities and relationships.

**Current status: stub** — logs temporal markers from extraction but does not create state nodes.

Planned design:
- Uses article `pub_date` + any temporal markers from extraction
- Creates State nodes: `(Entity)-[:HAS_STATE {from, to}]->(State)`
- Detects state transitions (same entity, different state at different time)
- Marks relationships as `current: true/false`
- On new batches: retires old states rather than creating contradictions

Example:
```
(Oil Prices)-[:HAS_STATE {from: "2022-03", to: "2022-11"}]->(State {value: "plummeting"})
(Oil Prices)-[:HAS_STATE {from: "2025-09", to: null}]->(State {value: "skyrocketing"})
```

---

## Stage 4: Chat Agent — Graph RAG (LangGraph)

Conversational Q&A over the knowledge graph using natural language.

### Architecture (LangGraph state machine)

```
User question + history
       │
       ▼
   ┌────────┐
   │ Router │  LLM decides: needs graph data, or direct answer?
   └──┬──┬──┘
      │  │
  graph  direct
      │  │
      ▼  └──▶ Direct Answer (greetings, meta) ──▶ Response
┌────────────────┐
│ Cypher Generator│  NL → 1..N Cypher using schema-aware prompt + query templates
└───────┬────────┘
        ▼
┌────────────────┐
│ Cypher Executor │  Run on Neo4j, safety guards (read-only), 25 row limit
│                │  Auto neighborhood enrichment for thin results
│                │  Collects article URLs from raw records
└───────┬────────┘
        ▼
┌────────────────┐
│ Fetch Articles │  Looks up article full_text from Postgres (scraped_articles)
│                │  Truncates to 2000 chars/article, max 5 articles
└───────┬────────┘
        ▼
┌────────────────┐
│  Synthesizer   │  Graph data + article content → intelligence briefing
└───────┬────────┘
        ▼
     Response
```

### Key features

- **Schema-aware Cypher generation**: Prompt includes full Neo4j schema + query templates
  for common patterns ("tell me about X", "how are X and Y related", "what events involve X")
- **Multi-query decomposition**: Complex questions are decomposed into multiple independent
  Cypher queries via structured JSON output (CypherQueryPlan with list of CypherQuery)
- **Neighborhood auto-enrichment**: When initial Cypher returns thin results (just name/type),
  automatically fetches relationships, events, and source articles for mentioned entities
- **Article content retrieval**: After graph queries, fetches actual article text from Postgres
  to give the LLM deeper context for synthesis (not just titles/URLs from the graph)
- **Conversation history**: Supports follow-up questions with context from previous turns
- **Safety**: Read-only queries only, mutation keywords rejected
- **Provenance**: Source articles included in responses when available
- **Retry with backoff**: LLM calls use exponential backoff retry on transient errors

### Endpoints

- `POST /api/chat` — JSON: `{question, history[]}` → `{answer, cypher, route}`

---

## Stage 5: Graph Visualization API

### `/api/graph` — Filtered subgraph for vis-network.js

Server-side filtering to handle large graphs:

| Query Param       | Default | Description                                  |
|-------------------|---------|----------------------------------------------|
| `limit`           | 100     | Max entity/event nodes returned (1-1000)     |
| `min_connections`  | 1       | Hide entities with fewer relationships       |
| `entity_type`     | all     | Filter by type (comma-separated)             |
| `search`          | —       | Case-insensitive name search                 |
| `date_range`      | —       | Filter by article recency (7d, 30d, 1y, etc.)|

Only Entity + Event nodes returned (no Article nodes — those are attached as `sources` metadata on click). Nodes ranked by degree (most-connected first).

### `/api/graph/stats` — Aggregate graph counts

Returns total entities, relationships, events, articles, and breakdown by entity type.

### `/entities/{entity_name}/timeline` — Entity timeline

Returns a chronological timeline for a specific entity: events it's involved in, co-entities, and supporting articles. Supports `limit` and `offset` pagination.

### Frontend (`/`)

Interactive vis-network.js HTML UI served by `visualization.py`. Features:
- Filter toolbar: search box, entity type dropdown, node limit slider (20–500), min connections slider (0–10)
- Type-colored nodes with size proportional to degree
- Graph re-renders on Apply

---

## Stage 6: Multi-Agent Report Generation with India Impact Analysis

### Architecture (Multi-Agent Pipeline)

```
ReportOrchestrator.generate(domain, date_range)
    │
    ├── Step 1: ReportAgent.generate_with_context()
    │       ├── _get_domain_weights()   → Postgres cache / LLM / static fallback (Stage 8)
    │       ├── _collect_graph_data()   → Neo4j: scored domain entities, relations, events
    │       ├── _fetch_articles()       → Postgres: article full-text
    │       └── _synthesize()           → LLM: DomainBriefing
    │       → ReportResult(briefing, graph_data, articles)
    │
    ├── Step 2: IndiaImpactAgent.analyze()
    │       ├── _discover_india_entities()    → Neo4j traversal from India + seed set
    │       ├── _extract_india_subgraph()     → Filter graph data for India connections
    │       ├── _filter_india_articles()      → Filter articles by graph-discovered entities
    │       └── _build_compact_prompt()       → Token-budgeted LLM call (~3700 tokens)
    │       → IndiaImpactAnalysis
    │
    ├── Step 3: InferenceAgent.analyze()
    │       ├── _discover_causal_chains()     → Cypher: RELATES_TO*2..5, causal scoring
    │       ├── _propagate_impact()           → Cypher: BFS from events, 3 hops
    │       ├── _detect_weak_links()          → Cypher: bridge entities across domains
    │       └── _synthesize_narrative()       → LLM: analyst-readable narratives
    │       → InferenceAnalysis
    │
    └── Step 4: Merge briefing + india_impact + inference → enriched report
```

### Key Design Decisions

1. **ReportResult dataclass**: Clean separation between briefing output and intermediate
   data (graph_data, articles). No dict pollution.

2. **Graph-driven entity discovery**: India-connected entities found via Neo4j traversal
   (1-2 hops from India through RELATES_TO/PART_OF) + static seed set of well-known
   Indian entities. This catches metonyms (New Delhi, Modi, ISRO) without keyword grep.

3. **Context window safety**: IndiaImpactAgent receives a compact prompt with strict
   token budgets — briefing summary only, development titles as bullets, India subgraph
   (max 20 relations), and 5 India-relevant article excerpts (1500 chars each).

### IndiaImpactAnalysis Output

| Section                | Description                                        |
|------------------------|----------------------------------------------------|
| executive_summary      | 2-3 paragraph India-focused overview               |
| strategic_assessment   | Summary + implications for India                   |
| transparency_insights  | Governance and accountability observations         |
| national_advantages    | Opportunities India can leverage                   |
| risks                  | Threats to Indian interests with severity/mitigation|
| global_positioning     | India's position vs competitors, trajectory        |
| recommendations        | Actionable policy/strategy recommendations         |

### Endpoints

- `GET /api/reports` — List all domains + latest report timestamps
- `GET /api/reports/{domain}` — Retrieve specific domain report

---

## Stage 7: Inference Agent — Cross-Domain Chain Discovery

The system's core differentiator: discovers hidden multi-hop causal chains,
propagates impact from events, and identifies critical weak links.

### Design: Graph-first, LLM-last

Steps 1-3 are pure Cypher — fast, deterministic, provenance-tracked.
The LLM only enters at Step 4 to narrate the structured graph results.

```
InferenceAgent.analyze(report_result)
    ├── Step 1: Causal Chain Discovery (Cypher)
    │     RELATES_TO*2..5 traversal, causal=true filter, cross-domain scoring
    │     Score: Π(confidence) × log(evidence) × type_diversity
    │     → Top 5 chains: (Drought → TSMC → Lockheed → F-35)
    │
    ├── Step 2: Impact Propagation (Cypher)
    │     Recent Events → BFS through RELATES_TO*1..3
    │     → Per-event impact map with hop distances
    │
    ├── Step 3: Weak Link Detection (Cypher)
    │     Bridge entities connecting 2+ domain clusters
    │     with few connections (fragile single points of failure)
    │
    └── Step 4: LLM Narrative Synthesis (single call, ~3500 tokens)
          → Analyst-readable narratives per chain, impact, and weak link
```

### InferenceAnalysis Output

| Section              | Description                                         |
|----------------------|-----------------------------------------------------|
| executive_summary    | 2-3 paragraph overview of key inferences            |
| causal_chains        | Multi-hop chains with scores, narratives, sources   |
| impact_propagations  | Event → downstream entity cascades with hop distance|
| weak_links           | Bridge entities, domains bridged, risk narratives   |

---

## Stage 8: Dynamic Domain Weights — LLM-Driven Relevance Scoring

Replaces static `DOMAIN_CONFIG` entity-type filtering with adaptive, LLM-generated
weights that drift to match what the knowledge graph actually contains.

### Architecture

```
_collect_graph_data(domain, cutoff)
    ├── Check Postgres cache (domain_weight_cache table)
    │     HIT → use cached weights (1 row per domain per day)
    │     MISS ↓
    ├── Sample entity/relation types from Neo4j (~50ms)
    ├── LLM scores each type for domain relevance (structured output)
    ├── Cache to Postgres (1 row per domain per day)
    └── Cypher scored query: $type_weights[e.type] × 0.4 + avg($rel_weights[r.type]) × 0.6
```

**Key**: All scoring happens in Cypher via native map parameter lookups.
No data pulled to Python for filtering.

**Fallback chain**: `Postgres cache → LLM structured output → static DOMAIN_CONFIG`

---

## Stage 9: News Priority Pipeline — Cross-Batch Clustering + Importance Scoring

### Problem

Raw RSS feeds produce hundreds of articles per cycle. Most are noise (celebrity gossip,
local crime, sports) that would waste extraction compute and pollute the knowledge graph.
Additionally, duplicate stories from multiple sources need deduplication before extraction.

### Architecture

The `NewsPriorityAgent` runs inside the Kafka consumer **before** articles reach GraphBuilder:

```
NewsPriorityAgent.process(batch: list[Article])
    │
    ├── Step 1: Embed article titles + descriptions (all-MiniLM-L6-v2)
    │
    ├── Step 2: Cluster against Redis-stored centroids (24h rolling window)
    │     cosine sim ≥ 0.82 → assign to existing cluster
    │     otherwise → create new cluster
    │
    ├── Step 3: Select best representative per cluster
    │     Score = credibility × log(content_length)
    │     Source credibility from Postgres (source_config) → Redis cache (1h TTL)
    │
    ├── Step 4: LLM scoring (structured output per representative)
    │     ArticleImportance schema:
    │       impact_score (0-10)      — structural scale of impact
    │       novelty_score (0-10)     — historical precedent level
    │       india_relevance (0-10)   — strategic impact on India
    │       domain                   — topic classification (17 standard domains)
    │       cluster_label            — 3-6 word topic label
    │
    ├── Step 5: Persist ALL articles to Postgres (with scores)
    │
    └── Return: articles with importance_score ≥ 5.0 → GraphBuilder
```

### Tuning Constants

| Constant                        | Value | Description                              |
|---------------------------------|-------|------------------------------------------|
| `CLUSTER_SIMILARITY_THRESHOLD`  | 0.82  | Cosine sim to join existing cluster      |
| `GRAPH_IMPORTANCE_THRESHOLD`    | 5.0   | Min score to forward to GraphBuilder     |
| `CLUSTER_TTL_SECONDS`           | 86400 | 24-hour rolling cluster window           |
| `DEFAULT_CREDIBILITY`           | 0.70  | For unknown news sources                 |

### Domain Classification

Standard domains: geopolitics, defense, economics, technology, energy, health, politics,
elections, crime, human_interest, environment, science, sports, education, infrastructure,
judiciary, diplomacy.

### Source Credibility

Per-source credibility scores stored in Postgres (`source_config` table) and cached in
Redis for 1 hour. Used for cluster representative selection (higher credibility sources
preferred) and overall scoring. Unknown sources default to 0.70.

---

## Stage 10: Signal / Anomaly Detection

### Problem

Decision-makers need to know when something unusual is happening — an entity suddenly
trending, a brand-new player appearing with high connectivity, or a topic cluster
experiencing abnormal growth. These signals complement the knowledge graph with
real-time alerting.

### Architecture

The `signal_worker.py` runs as a standalone background process every 15 minutes:

```
signal_worker.py (every 15 minutes)
    │
    ├── Signal A: Entity Mention Spikes (Neo4j)
    │     Compare today's entity-article count vs same-day 7-day baseline
    │     Laplace smoothing on denominator, skip thin-history entities
    │     Ratio ≥ 3.0 → medium; ≥ 5.0 → high severity
    │
    ├── Signal B: New High-Connectivity Entities (Neo4j)
    │     Entities first seen within 24h with ≥ 5 graph connections
    │     Uses first_seen + relationship scan (no full node scan)
    │
    ├── Signal C: Topic Cluster Spikes (Postgres)
    │     6-hour windows, compare against 7-day same-hour baseline
    │     Ratio ≥ 2.5 with min 3 current articles + min 3h cluster age
    │
    └── Persist to Postgres (detected_signals) with 6h TTL
        → Read by GET /api/signals (zero-computation endpoint)
```

### Design Choices Addressing Failure Modes

- **Same-day baseline** (not daily average): avoids time-of-day news-cycle bias
- **MIN_BASELINE_MENTIONS guard**: skips obscure entities with insufficient history
- **Laplace smoothing**: prevents division-by-zero and dampens small-number false positives
- **Minimum current-count guard**: a single article can never trigger a spike
- **Topic spike uses 6h windows** (not 2h): smooths over scraper batch cadence
- **Signal B uses relationship scan**: no `created_at` property scan avoids full index-less scans
- **IST normalization**: all time comparisons use UTC+5:30 to align with Indian news cycles

### Tuning Constants

| Constant                          | Value | Description                              |
|-----------------------------------|-------|------------------------------------------|
| `ENTITY_SPIKE_WINDOW_HOURS`       | 2     | Current window for entity counts         |
| `ENTITY_SPIKE_RATIO_THRESHOLD`    | 3.0   | Min smoothed ratio for spike signal      |
| `ENTITY_MIN_BASELINE_MENTIONS`    | 8     | Skip entities with thin history          |
| `ENTITY_MIN_CURRENT_MENTIONS`     | 3     | Min articles to fire (prevents noise)    |
| `LAPLACE_SMOOTH`                  | 1.0   | Denominator smoothing constant           |
| `NEW_ENTITY_LOOKBACK_HOURS`       | 24    | "New" entity window                      |
| `NEW_ENTITY_MIN_DEGREE`           | 5     | Min graph connections to be notable      |
| `TOPIC_SPIKE_WINDOW_HOURS`        | 6     | Wider window for topic cluster counts    |
| `TOPIC_SPIKE_RATIO_THRESHOLD`     | 2.5   | Min ratio for topic spike                |
| `TOPIC_MIN_CLUSTER_AGE_HOURS`     | 3     | Brand-new clusters can't "spike"         |
| `SIGNAL_TTL_HOURS`                | 6     | How long signals stay visible            |

### Endpoint

- `GET /api/signals?signal_type=&severity=&limit=` — Active signals from Postgres

---

## Stage 11: Live Feed — Real-Time Article Streaming

### Architecture

Articles ingested by the consumer are published to Redis pub/sub in real time.
The API server provides a WebSocket endpoint for frontend consumption.

- **Channel**: `india-innovates:live-feed`
- **Event payload**: `{url, title, source, thumbnail, pub_date, status, timestamp}`
- **Endpoint**: `/ws/live-feed` (WebSocket)

All articles are published (not just those forwarded to GraphBuilder), providing
a complete real-time view of the ingestion pipeline.

---

## Stage 12: Weather Pipeline (Open-Meteo → Anomaly Detection)

### Architecture

```
WeatherProducer (scheduler/weather_producer.py)
    │
    ├── WeatherScraper (scrapers/weather.py)
    │     ├── fetch_historical()     → EC_Earth3P_HR climate archive
    │     ├── fetch_forecast()       → 7-day weather forecast
    │     └── fetch_climate_normals() → 30-year monthly baselines (1991–2020)
    │     25 Indian cities, 16 weather variables
    │
    ├── WeatherAnomalyDetector (agents/weather_anomaly.py)
    │     ├── compute_anomaly_scores()  → z-scores against climate normals
    │     ├── detect_heat_waves()       → IMD: Tmax > 40°C for ≥3 consecutive days
    │     ├── detect_cold_waves()       → IMD: Tmin < 4°C for ≥3 consecutive days
    │     ├── detect_extreme_rainfall() → IMD: ≥204.5 mm/day
    │     ├── detect_droughts()         → Soil moisture z-score < -1.5 for ≥14 days
    │     └── detect_cyclone_proxies()  → Wind speed ≥ 90 km/h + sustained rain
    │
    └── WeatherTrendAnalyzer
          ├── Annual trend (linear regression)
          ├── Monsoon analysis (Jun–Sep rainfall patterns)
          └── Extreme frequency tracking
```

### Data Storage

| Table                  | Contents                                         |
|------------------------|--------------------------------------------------|
| `weather_observations` | 25 cities × daily: 16 weather vars + z-scores    |
| `weather_anomalies`    | Detected events: heat wave, cold wave, drought, etc. |
| `climate_normals`      | 30-year monthly baselines: mean, std, percentiles |

### Endpoints

| Endpoint                            | Description                                    |
|-------------------------------------|------------------------------------------------|
| `GET /api/weather/cities`           | List 25 monitored Indian cities                |
| `GET /api/weather/current`          | Latest observation + anomaly flags for all cities |
| `GET /api/weather/trends/{city}`    | Trend analysis (7d, 30d, 1y, 5y periods)      |
| `GET /api/weather/{city}/anomalies` | Detected weather anomalies for a city          |
| `GET /api/weather/monsoon`          | Monsoon season analysis (rainfall deficit, etc.)|

### Bootstrap Commands

```bash
# Compute 30-year climate normals (one-time, ~2-5 min)
uv run python -m scheduler.weather_producer --bootstrap-normals

# Backfill N years of historical observations (optional)
uv run python -m scheduler.weather_producer --backfill --years 5
```

---

## Stage 13: News API — Prioritised Article Access

### Endpoints

| Endpoint                | Query Params                                          | Description                                    |
|-------------------------|-------------------------------------------------------|------------------------------------------------|
| `GET /api/news`         | page, per_page, source, domain, min_score, from_date, to_date, q | Paginated, filterable articles sorted by importance then recency |
| `GET /api/news/top`     | limit, hours                                          | Top N articles by importance in last N hours   |
| `GET /api/news/topics`  | hours, limit                                          | Trending topic clusters with article counts    |
| `GET /api/news/sources` | —                                                     | Active news sources with article counts + avg importance |

All endpoints read from Postgres (`scraped_articles` table with priority columns added
by the NewsPriorityAgent). Zero computation at request time.

---

## Implementation Phases

| Phase | Scope                                              | Status      |
|-------|----------------------------------------------------|-------------|
| 1     | Extraction Agent with typed relations + temporal   | ✅ Done      |
| 2     | Entity Resolution (Tier 1 + 2 + 3)                | ✅ Done      |
| 3     | Neo4j schema + graph builder                       | ✅ Done      |
| 4     | API + graph visualization                          | ✅ Done      |
| 5     | Chat Agent — Graph RAG (LangGraph)                 | ✅ Done      |
| 5b    | Chat: Article content fetching from Postgres       | ✅ Done      |
| 6     | Kafka pipeline (producer + consumer)               | ✅ Done      |
| 7     | Graph visualization scaling (server-side filter)   | ✅ Done      |
| 8     | Temporal Agent with state tracking                 | Stub        |
| 9     | Inference Agent — cross-domain chain discovery     | ✅ Done      |
| 10    | Multi-agent report generation + India impact       | ✅ Done      |
| 11    | Dynamic domain weights (LLM-driven scoring)        | ✅ Done      |
| 12    | Weather pipeline (Open-Meteo ingest + anomalies)   | ✅ Done      |
| 13    | News priority pipeline (clustering + LLM scoring)  | ✅ Done      |
| 14    | Signal / anomaly detection worker                  | ✅ Done      |
| 15    | Live feed (WebSocket + Redis pub/sub)              | ✅ Done      |
| 16    | News API (paginated articles, topics, sources)     | ✅ Done      |
| 17    | Source credibility system (Postgres + Redis cache) | ✅ Done      |
| 18    | Entity timeline API                                | ✅ Done      |
| 19    | Interactive vis-network.js frontend                | ✅ Done      |

---

## Running the System

The system comprises **6 independent processes** plus required infrastructure services.
Each process can run in its own terminal or Docker container.

### 0. Prerequisites — Infrastructure Services

These must be running before any application process starts:

```bash
# PostgreSQL (default: localhost:5432)
# If using Homebrew on macOS:
brew services start postgresql@17
# Or via Docker:
# docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=password postgres:17

# Redis (default: localhost:6379)
brew services start redis
# Or: docker run -d --name redis -p 6379:6379 redis:7

# Neo4j (default: neo4j://localhost:7687)
# Desktop: open Neo4j Desktop → start your database
# Or: docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5

# Apache Kafka (default: localhost:9092)
# If using Homebrew:
brew services start kafka
# Or via Docker (with KRaft, no Zookeeper):
# docker run -d --name kafka -p 9092:9092 apache/kafka:latest
```

Create the Kafka topic (only once):
```bash
# Homebrew Kafka:
/opt/homebrew/opt/kafka/bin/kafka-topics --create --topic india-innovates --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1 2>/dev/null || true
```

### 1. Install Dependencies & Run Migrations

```bash
# Install all Python dependencies (uses uv, not pip)
uv sync

# Apply database migrations (creates all Postgres tables)
uv run alembic upgrade head
```

### 2. One-Time Weather Bootstrap (run before first weather cycle)

```bash
# Step A: Compute 30-year climate normals for all 25 Indian cities
# Uses the Open-Meteo Climate API (EC_Earth3P_HR model, 1991-2020)
# Takes ~2-5 min (25 cities × 30 years of data)
uv run python -m scheduler.weather_producer --bootstrap-normals

# Step B (optional): Backfill N years of historical daily observations
# Default is 5 years; adjust with --years
uv run python -m scheduler.weather_producer --backfill --years 5
```

### 3. Start All Processes

Open **6 terminals**, each from the project root:

```bash
# ── Terminal 1: API Server ──────────────────────────────────────────
# FastAPI with hot-reload. Serves all REST + WebSocket endpoints.
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
# API docs: http://localhost:8000/docs
# Graph viz: http://localhost:8000/
# Chat UI:   http://localhost:8000/chat

# ── Terminal 2: News Producer (Kafka) ───────────────────────────────
# Scrapes RSS feeds every 30min, publishes articles to Kafka.
uv run python -m scheduler.producer

# ── Terminal 3: News Consumer (Kafka) ───────────────────────────────
# Consumes article batches from Kafka. Runs NewsPriorityAgent first
# (embed → cluster → LLM score → persist ALL to Postgres), then
# forwards high-importance articles (≥5.0) to GraphBuilder for
# extraction (GLiNER2 NER → LLM canonicalization → LLM enrichment →
# entity resolution → Neo4j + Postgres storage).
# Publishes live-feed events for ALL articles to Redis.
uv run python -m scheduler.consumer

# ── Terminal 4: Report Scheduler ────────────────────────────────────
# Generates multi-agent intelligence reports every hour across all
# domains (geopolitics, defense, economics, technology, energy, etc.).
# Each report runs: ReportAgent → IndiaImpactAgent → InferenceAgent.
uv run python -m scheduler.report_scheduler

# ── Terminal 5: Weather Producer ────────────────────────────────────
# Fetches weather data for 25 Indian cities every 6 hours from
# Open-Meteo, computes z-scores against climate normals, detects
# anomalies (heat waves, cold waves, extreme rain, droughts, cyclone
# proxies), stores to Postgres, publishes alerts to Redis.
uv run python -m scheduler.weather_producer

# ── Terminal 6: Signal Worker ───────────────────────────────────────
# Detects anomalies every 15 minutes: entity mention spikes (Neo4j
# 7-day baseline), new high-connectivity entities, topic cluster
# spikes (Postgres baseline). Persists detected signals with 6h TTL.
uv run python -m scheduler.signal_worker
```

### Quick-Start (minimal — just API + weather)

If you only want to explore the weather features without the full news pipeline:

```bash
# Ensure Postgres and Redis are running, then:
uv sync
uv run alembic upgrade head
uv run python -m scheduler.weather_producer --bootstrap-normals
uv run python -m scheduler.weather_producer --once       # single fetch cycle
uv run uvicorn main:app --reload                         # start API
# Visit http://localhost:8000/docs → try /api/weather/* endpoints
```

### One-Off Commands

```bash
# Run a single weather cycle without starting the loop:
uv run python -m scheduler.weather_producer --once

# Backfill weather with custom year range:
uv run python -m scheduler.weather_producer --backfill --years 10

# Reset Kafka topic and/or Redis state for clean test runs:
uv run python -m scripts.reset --redis --kafka

# Generate a new Alembic migration after model changes:
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

### Process Summary

| # | Process | Command | Schedule | Depends On |
|---|---------|---------|----------|------------|
| 1 | **API Server** | `uv run uvicorn main:app --reload` | Always on | Postgres, Neo4j, Redis |
| 2 | **News Producer** | `uv run python -m scheduler.producer` | Every 30 min | Kafka, Redis, Postgres |
| 3 | **News Consumer** | `uv run python -m scheduler.consumer` | Continuous | Kafka, Redis, Postgres, Neo4j |
| 4 | **Report Scheduler** | `uv run python -m scheduler.report_scheduler` | Every 1 hr | Postgres, Neo4j, Redis |
| 5 | **Weather Producer** | `uv run python -m scheduler.weather_producer` | Every 6 hr | Postgres, Redis |
| 6 | **Signal Worker** | `uv run python -m scheduler.signal_worker` | Every 15 min | Postgres, Neo4j, Redis |

### Configuration (config.py / environment variables)

All settings can be overridden via environment variables or a `.env` file.

| Variable                          | Default           | Description                              |
|-----------------------------------|-------------------|------------------------------------------|
| `POSTGRES_USER`                   | `postgres`        | PostgreSQL username                      |
| `POSTGRES_PASSWORD`               | `password`        | PostgreSQL password                      |
| `POSTGRES_HOST`                   | `localhost`       | PostgreSQL host                          |
| `POSTGRES_PORT`                   | `5432`            | PostgreSQL port                          |
| `POSTGRES_DATABASE`               | `postgres`        | PostgreSQL database name                 |
| `NEO4J_URI`                       | `neo4j://localhost:7687` | Neo4j Bolt URI                    |
| `NEO4J_USER`                      | `neo4j`           | Neo4j username                           |
| `NEO4J_PASSWORD`                  | *(set in config)* | Neo4j password                           |
| `REDIS_HOST`                      | `localhost`       | Redis host (dedup + pub/sub + clusters + alerts) |
| `REDIS_PORT`                      | `6379`            | Redis port                               |
| `KAFKA_BOOTSTRAP_SERVERS`         | `localhost:9092`  | Kafka broker address                     |
| `KAFKA_TOPIC`                     | `india-innovates` | Topic for article messages               |
| `SCRAPE_INTERVAL_SECONDS`         | `1800` (30 min)   | News RSS scrape frequency                |
| `KAFKA_BATCH_TIMEOUT_SECONDS`     | `60`              | Consumer waits this long to fill a batch |
| `KAFKA_BATCH_MAX_SIZE`            | `50`              | Max articles per consumer batch          |
| `REPORT_INTERVAL_SECONDS`         | `3600` (1 hr)     | Report generation frequency              |
| `REPORT_DATE_RANGE`               | `7d`              | Date window for report data              |
| `WEATHER_SCRAPE_INTERVAL_SECONDS` | `21600` (6 hr)    | Weather data fetch frequency             |
| `WEATHER_HISTORICAL_BACKFILL_YEARS`| `5`              | Default years for `--backfill`           |
| `SIGNAL_WORKER_INTERVAL_SECONDS`  | `900` (15 min)    | Signal detection frequency               |

---

## File Structure

```
agents/
    extraction.py           # Stage 1: Per-article entity/relation extraction (GLiNER2 + LLM)
    resolution.py           # Stage 2: 3-tier entity resolution funnel
    temporal.py             # Stage 3: Temporal state tracking (stub)
    chat.py                 # Stage 4: LangGraph chat agent (Graph RAG + article fetching)
    report.py               # Stage 6+8: Domain briefing agent + dynamic domain weights
    india_impact.py         # Stage 6: India strategic impact analysis agent
    report_orchestrator.py  # Stage 6: Multi-agent orchestrator (4-agent pipeline)
    inference.py            # Stage 7: Causal chain discovery, impact propagation, weak links
    news_priority.py        # Stage 9: Cross-batch topic clustering + LLM importance scoring
    weather_anomaly.py      # Stage 12: Statistical anomaly detection + trend analysis
graphs/
    schemas.py              # Pydantic models for all stages (extraction, resolution, temporal)
    prompts.py              # LLM prompt templates
    graph_builder.py        # Orchestrates pipeline (process_articles), saves to Neo4j
scheduler/
    producer.py             # Kafka producer: periodic RSS scraping → publish
    consumer.py             # Kafka consumer: priority scoring → extraction → Neo4j pipeline
    report_scheduler.py     # Report scheduler: periodic multi-agent report generation
    weather_producer.py     # Stage 12: Weather data ingestion + anomaly detection (6hr loop)
    signal_worker.py        # Stage 10: Entity/topic anomaly detection (15min loop)
api/
    __init__.py             # FastAPI app with all router registrations
    routes/
        graph.py            # /api/graph, /api/graph/stats, /entities/{name}/timeline
        chat.py             # /api/chat endpoint (conversational Q&A)
        reports.py          # /api/reports endpoint (domain reports + India impact)
        news.py             # /api/news, /api/news/top, /api/news/topics, /api/news/sources
        signals.py          # /api/signals endpoint (anomaly signals)
        live_feed.py        # /ws/live-feed (WebSocket + Redis pub/sub)
        weather.py          # /api/weather/* (cities, current, trends, anomalies, monsoon)
        visualization.py    # / graph viz (vis-network.js interactive frontend)
scrapers/
    news_rss.py             # RSS scraper (title dedup, max_per_feed)
    weather.py              # Stage 12: Open-Meteo API client (forecast, archive, climate)
models/
    database.py             # SQLAlchemy engine + Base + SessionLocal
    scraped_article.py      # Article storage + priority scoring columns
    entity_alias.py         # Persistent merge table with context-type gating
    source_config.py        # Per-source credibility scores (used by NewsPriorityAgent)
    detected_signal.py      # Anomaly signal records (entity_spike, new_entity, topic_spike)
    domain_report.py        # Generated report storage (JSON)
    domain_weight_cache.py  # Stage 8: Daily cached LLM-generated domain weights
    weather_observation.py  # Stage 12: Daily weather observations per city + z-scores
    weather_anomaly.py      # Stage 12: Detected anomaly event records
    climate_normal.py       # Stage 12: 30-year monthly baselines per city/variable
scripts/
    reset.py                # Utility: reset Kafka topic and/or Redis state (--redis, --kafka)
docs/
    plan.md                 # This file
    weather-plan.md         # Detailed weather integration plan (25 cities, anomaly rules, API details)
    architecture.dot        # Graphviz source → .png/.svg
alembic/                    # Database migrations
alembic.ini
config.py                   # All config: DB, Neo4j, Redis, Kafka, scrape intervals, weather, signals
main.py                     # Entry point (imports FastAPI app from api/)
pyproject.toml              # Dependencies managed via uv
```
