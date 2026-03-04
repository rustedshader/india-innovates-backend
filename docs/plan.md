# Global Ontology Engine — Architecture Plan

## Vision

An AI-powered intelligence graph that ingests global news, extracts entities and their typed relationships, resolves them across sources, tracks temporal state changes, and enables conversational querying over the knowledge graph. The graph powers strategic Q&A and report generation for decision-makers.

---

## Pipeline Architecture

```
RSS Feeds
    │
    ▼
┌──────────────┐
│   Scraper    │  Fetch RSS + extract full article text
└──────┬───────┘
       │ list[Article]
       ▼
┌───────────────────────────────────────────────────────────┐
│              Extraction Agent (hybrid)                     │
│                                                           │
│  ┌──────────────┐   ┌────────────────┐   ┌─────────────┐  │
│  │ GLiNER2(205M)│──▶│ LLM Canon-     │──▶│ LLM Enrich  │  │
│  │ • NER        │   │ icalization    │   │ • Events    │  │
│  │ • RE         │   │ • Canonical    │   │ • Causal    │  │
│  │ ~50ms CPU    │   │   names        │   │ • Temporal  │  │
│  │              │   │ • Aliases      │   │             │  │
│  └──────────────┘   └────────────────┘   └─────────────┘  │
│  Output: list[ArticleExtraction]                          │
└───────────────────────────┬───────────────────────────────┘
       │
       ▼
┌──────────────────┐
│ Resolution Agent │  Cross-article: deduplicate & merge entities
│  3-Tier Funnel   │  Tier 1: Deterministic normalization (O(N))
│                  │  Tier 2: Embedding similarity + ANN (O(N log N))
│                  │  Tier 3: LLM disambiguation (O(K), K << N)
└──────┬───────────┘
       │ resolved entities + merge table
       ▼
┌──────────────────┐
│ Temporal Agent   │  Attach timestamps, detect state changes, mark current vs historical
└──────┬───────────┘
       │
       ▼
    Neo4j Graph
       │
       ├──→ FastAPI /api/graph ──→ Visualization (vis-network.js)
       │
       └──→ FastAPI /api/chat  ──→ Chat UI (/chat)
                    │
              ┌─────┴──────┐
              │ Chat Agent  │  LangGraph: Router → Cypher Gen → Execute → Synthesize
              │ (Graph RAG) │  NL question → Cypher → Neo4j → NL answer
              └────────────┘
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
└───────┬────────┘
        ▼
┌────────────────┐
│  Synthesizer   │  Graph data → natural language intelligence briefing
└───────┬────────┘
        ▼
     Response
```

### Key features

- **Schema-aware Cypher generation**: Prompt includes full Neo4j schema + query templates
  for common patterns ("tell me about X", "how are X and Y related", "what events involve X")
- **Neighborhood auto-enrichment**: When initial Cypher returns thin results (just name/type),
  automatically fetches relationships, events, and source articles for mentioned entities
- **Conversation history**: Supports follow-up questions with context from previous turns
- **Safety**: Read-only queries only, mutation keywords rejected
- **Provenance**: Source articles included in responses when available

### Endpoints

- `POST /api/chat` — JSON: `{question, history[]}` → `{answer, cypher, route}`
- `GET /chat` — Full chat UI with conversation history, typing indicators, Cypher display

---

## Future: Inference Agent (Post-batch)

Runs after each batch on the updated graph.

1. **Path Discovery**: Multi-hop chains across domains
   - `(Drought in Taiwan) →[disrupts]→ (TSMC) →[supplies_chips_to]→ (Lockheed Martin) →[builds]→ (F-35)`
2. **Impact Propagation**: New event → traverse graph → find downstream affected entities
3. **Weak Link Detection**: High-centrality bridging nodes between domain subgraphs

---

## Future: Strategic Report Generation

1. Query: "Strategic assessment of semiconductor supply chains"
2. Graph traversal: Pull subgraph around target entities (2-3 hops)
3. Temporal filter: Only current states
4. LLM synthesis: Structured report with situation, key actors, risks, causal chains, monitoring targets

---

## Implementation Phases

| Phase | Scope                                            | Status      |
|-------|--------------------------------------------------|-------------|
| 1     | Extraction Agent with typed relations + temporal | ✅ Done      |
| 2     | Entity Resolution (Tier 1 + 2 + 3)              | ✅ Done      |
| 3     | Neo4j schema + graph builder                     | ✅ Done      |
| 4     | API + graph visualization                        | ✅ Done      |
| 5     | Chat Agent — Graph RAG (LangGraph)               | ✅ Done      |
| 6     | Temporal Agent with state tracking               | Partial     |
| 7     | Inference Agent for cross-domain chains          | Planned     |
| 8     | Strategic report generation endpoint             | Planned     |

---

## File Structure

```
agents/
    extraction.py       # Stage 1: Per-article entity/relation extraction
    resolution.py       # Stage 2: 3-tier entity resolution funnel
    temporal.py         # Stage 3: Temporal state tracking
    chat.py             # Stage 4: LangGraph chat agent (Graph RAG)
graphs/
    schemas.py          # Pydantic models for all stages
    prompts.py          # LLM prompt templates
    graph_builder.py    # Orchestrates pipeline, saves to Neo4j
api/
    __init__.py         # FastAPI app
    routes/
        graph.py        # /api/graph endpoint
        chat.py         # /api/chat endpoint (conversational Q&A)
        visualization.py # / graph viz + /chat chat UI
scrapers/
    news_rss.py         # RSS scraper (title dedup, max_per_feed)
models/
    database.py         # SQLAlchemy engine
    scraped_article.py  # Article dedup table
    entity_alias.py     # Persistent merge table
docs/
    plan.md             # This file
    architecture.dot    # Graphviz source → .png/.svg
config.py
main.py
```

