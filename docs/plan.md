# Global Ontology Engine — Architecture Plan

## Vision

An AI-powered intelligence graph that ingests global news, extracts entities and their typed relationships, resolves them across sources, tracks temporal state changes, and enables conversational querying over the knowledge graph. The graph powers strategic Q&A and report generation for decision-makers.

---

## Pipeline Architecture

The system runs as **three independent processes** (Docker-ready):

```
                           ┌──────────────┐
                           │  Redis Set   │  URL dedup across processes
                           └──────┬───────┘
                                  │ SISMEMBER / SADD
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
│  GraphBuilder.process_articles(batch)                                  │
│  ┌───────────────────────────────────────────────────────────────┐     │
│  │              Extraction Agent (hybrid)                        │     │
│  │  GLiNER2 (NER+RE) ──▶ LLM Canonicalization ──▶ LLM Enrich   │     │
│  └───────────────────────────┬───────────────────────────────────┘     │
│                              ▼                                        │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐   │
│  │ Resolution Agent │──▶│ Temporal Agent   │──▶│ Batched UNWIND   │   │
│  │ (3-Tier Funnel)  │   │ (stub)           │   │ Neo4j + Postgres │   │
│  └──────────────────┘   └──────────────────┘   └──────────────────┘   │
└───────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  API SERVER  (main.py)                                                 │
│                                                                       │
│  Neo4j Graph ◀──── /api/graph ──▶ Visualization (vis-network.js)      │
│       │              (server-side filtering, batched source queries)   │
│       └──── /api/chat ──▶ Chat Agent (LangGraph Graph RAG)            │
│              │                    ▲                                    │
│              └── Postgres ────────┘  article full_text for context     │
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
2. Alias table: maintained in Postgres, seeded with common geopolitical aliases, grows over time
3. Acronym expansion: if both "NATO" and "North Atlantic Treaty Organization" exist → merge
4. LLM-provided aliases: extraction already provides aliases per entity

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

Stored in Postgres. Once resolved, never re-evaluated. New batches check table first (O(1) lookup).

### Bonus: Graph-Based Resolution

After all tiers, Neo4j structural similarity:
- Same type + 3+ shared neighbors + never co-occur in same article → likely same entity

---

## Stage 3: Temporal Agent

Attaches time dimension to entities and relationships.

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
│ Cypher Generator│  NL → Cypher using schema-aware prompt + query templates
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
- **Neighborhood auto-enrichment**: When initial Cypher returns thin results (just name/type),
  automatically fetches relationships, events, and source articles for mentioned entities
- **Article content retrieval**: After graph queries, fetches actual article text from Postgres
  to give the LLM deeper context for synthesis (not just titles/URLs from the graph)
- **Conversation history**: Supports follow-up questions with context from previous turns
- **Safety**: Read-only queries only, mutation keywords rejected
- **Provenance**: Source articles included in responses when available

### Endpoints

- `POST /api/chat` — JSON: `{question, history[]}` → `{answer, cypher, route}`
- `GET /chat` — Full chat UI with conversation history, typing indicators, Cypher display

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

Only Entity + Event nodes returned (no Article nodes — those are attached as `sources` metadata on click). Nodes ranked by degree (most-connected first).

### `/api/graph/stats` — Aggregate graph counts

Returns total entities, relationships, events, articles, and breakdown by entity type.

### Frontend

Filter toolbar with: search box, entity type dropdown, node limit slider (20–500), min connections slider (0–10). Graph re-renders on Apply.

---

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

### Full Orchestrator Pipeline (4 agents)

```
ReportOrchestrator.generate(domain, date_range)
    ├── Step 1: ReportAgent          → domain briefing
    ├── Step 2: IndiaImpactAgent     → India strategic analysis
    ├── Step 3: InferenceAgent       → causal chains, impact, weak links
    └── Step 4: Merge all → enriched report
```

---

## Stage 8: Dynamic Domain Weights — LLM-Driven Relevance Scoring

Replaces static `DOMAIN_CONFIG` entity-type filtering with adaptive, LLM-generated
weights that drift to match what the knowledge graph actually contains.

### Architecture

```
_collect_graph_data(domain, cutoff)
    ├── Check Postgres cache (domain_weight_cache table)
    │     HIT → use cached weights
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

## Implementation Phases

| Phase | Scope                                            | Status      |
|-------|--------------------------------------------------|-------------|
| 1     | Extraction Agent with typed relations + temporal | ✅ Done      |
| 2     | Entity Resolution (Tier 1 + 2 + 3)              | ✅ Done      |
| 3     | Neo4j schema + graph builder                     | ✅ Done      |
| 4     | API + graph visualization                        | ✅ Done      |
| 5     | Chat Agent — Graph RAG (LangGraph)               | ✅ Done      |
| 5b    | Chat: Article content fetching from Postgres     | ✅ Done      |
| 6     | Kafka pipeline (producer + consumer)             | ✅ Done      |
| 7     | Graph visualization scaling (server-side filter) | ✅ Done      |
| 8     | Temporal Agent with state tracking               | Stub        |
| 9     | Inference Agent — cross-domain chain discovery   | ✅ Done      |
| 10    | Multi-agent report generation + India impact     | ✅ Done      |
| 11    | Dynamic domain weights (LLM-driven scoring)      | ✅ Done      |

---

## Running the System

Three independent processes, each suitable for its own Docker container:

```bash
# Terminal 1: API server
uv run uvicorn main:app --reload

# Terminal 2: Kafka producer (scrapes every 30min)
python -m scheduler.producer

# Terminal 3: Kafka consumer (processes batches)
python -m scheduler.consumer

# Terminal 4: Report scheduler (generates reports every hour)
python -m scheduler.report_scheduler
```

### Configuration (config.py / environment variables)

| Variable                     | Default           | Description                              |
|------------------------------|-------------------|------------------------------------------|
| `KAFKA_BOOTSTRAP_SERVERS`    | `localhost:9092`  | Kafka broker address                     |
| `KAFKA_TOPIC`                | `india-innovates` | Topic for article messages               |
| `SCRAPE_INTERVAL_SECONDS`    | `1800` (30min)    | How often the producer scrapes RSS feeds |
| `KAFKA_BATCH_TIMEOUT_SECONDS`| `60`              | Consumer waits this long to fill a batch |
| `KAFKA_BATCH_MAX_SIZE`       | `50`              | Max articles per consumer batch          |
| `REDIS_HOST`                 | `localhost`       | Redis host for URL dedup set             |
| `REDIS_PORT`                 | `6379`            | Redis port                               |
| `REPORT_INTERVAL_SECONDS`    | `3600` (1hr)      | How often reports are regenerated        |
| `REPORT_DATE_RANGE`          | `7d`              | Date window for report data              |

---

## File Structure

```
agents/
    extraction.py           # Stage 1: Per-article entity/relation extraction
    resolution.py           # Stage 2: 3-tier entity resolution funnel
    temporal.py             # Stage 3: Temporal state tracking
    chat.py                 # Stage 4: LangGraph chat agent (Graph RAG + article fetching)
    report.py               # Stage 6+8: Domain briefing agent + dynamic domain weights
    india_impact.py         # Stage 6: India strategic impact analysis agent
    report_orchestrator.py  # Stage 6: Multi-agent orchestrator (4-agent pipeline)
    inference.py            # Stage 7: Causal chain discovery, impact propagation, weak links
graphs/
    schemas.py              # Pydantic models for all stages
    prompts.py              # LLM prompt templates
    graph_builder.py        # Orchestrates pipeline (process_articles), saves to Neo4j
scheduler/
    producer.py             # Kafka producer: periodic RSS scraping → publish
    consumer.py             # Kafka consumer: batch consume → process_articles pipeline
    report_scheduler.py     # Report scheduler: periodic multi-agent report generation
api/
    __init__.py             # FastAPI app
    routes/
        graph.py            # /api/graph endpoint
        chat.py             # /api/chat endpoint (conversational Q&A)
        reports.py          # /api/reports endpoint (domain reports + India impact)
        live_feed.py        # /api/live-feed endpoint (SSE + WebSocket)
        visualization.py    # / graph viz + /chat chat UI
scrapers/
    news_rss.py             # RSS scraper (title dedup, max_per_feed)
models/
    database.py             # SQLAlchemy engine
    scraped_article.py      # Article dedup table
    entity_alias.py         # Persistent merge table
    domain_report.py        # Generated report storage
    domain_weight_cache.py  # Stage 8: Daily cached LLM-generated domain weights
docs/
    plan.md                 # This file
    architecture.dot        # Graphviz source → .png/.svg
alembic/                    # Database migrations
alembic.ini
config.py                   # All config: DB, Neo4j, Redis, Kafka, scrape intervals
main.py
```


