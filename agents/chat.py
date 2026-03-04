"""LangGraph-based RAG chat agent for querying the knowledge graph.

Architecture:
  User question
       │
       ▼
  ┌─────────────┐
  │  Router LLM │  Decide: need graph query, or can answer directly?
  └──────┬──────┘
         │
    ┌────┴────┐
    ▼         ▼
 [cypher]  [answer]
    │
    ▼
 Neo4j query
    │
    ▼
 [synthesize]  ──▶  Final answer with citations
"""

from __future__ import annotations

import logging
import re
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph
from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_AUTH

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Neo4j schema description (injected into prompts so LLM knows the structure)
# ---------------------------------------------------------------------------

NEO4J_SCHEMA = """
Node labels and properties:
- (:Entity {name, type, first_seen, last_updated})
    type is one of: Person, Organization, Country, Location, Policy, Technology,
                    Economic_Indicator, Military_Asset, Resource
- (:Event {name, date, status})
    status is one of: ongoing, concluded, announced, rumored
- (:Article {url, title, source, pub_date})

Relationships:
- (Entity)-[:RELATES_TO {type, since, confidence, causal, current}]->(Entity)
    The `type` property holds the relation verb. Possible values:
    sanctions, allied_with, opposes, trades_with, supplies_to, invaded,
    leads, founded, acquired, located_in, manufactures, funds,
    threatens, negotiates_with, member_of, disrupts, signed_agreement_with,
    deployed_to, develops, exports_to, imports_from, cooperates_with,
    competes_with, attacks, blocks, supports
    `causal` is a boolean. `since` and `current` are optional.

- (Entity)-[:INVOLVED_IN]->(Event)
- (Article)-[:EVIDENCES]->(Entity)
- (Article)-[:EVIDENCES]->(Event)
- (Article)-[:EVIDENCES_REL {relation_type}]->(Entity)

IMPORTANT: Entity-to-Entity relationships are ALL stored as :RELATES_TO edges
with a `type` property. Do NOT use dynamic relationship types like [:sanctions].
Always filter with `r.type = "sanctions"` instead.
"""

CYPHER_SYSTEM = f"""You are a Neo4j Cypher expert for a geopolitical knowledge graph.

{NEO4J_SCHEMA}

Query patterns for common question types:

1. "Tell me about X" / "What do you know about X":
   Fetch the entity, all its relationships, connected entities, events, AND source articles:
   MATCH (e:Entity)
   WHERE toLower(e.name) CONTAINS toLower("X")
   OPTIONAL MATCH (e)-[r:RELATES_TO]->(t:Entity)
   OPTIONAL MATCH (e)<-[r2:RELATES_TO]-(s:Entity)
   OPTIONAL MATCH (e)-[:INVOLVED_IN]->(ev:Event)
   OPTIONAL MATCH (a:Article)-[:EVIDENCES]->(e)
   RETURN e.name AS entity, e.type AS type,
          collect(DISTINCT {{relation: r.type, target: t.name, target_type: t.type}}) AS outgoing,
          collect(DISTINCT {{relation: r2.type, source: s.name, source_type: s.type}}) AS incoming,
          collect(DISTINCT {{event: ev.name, date: ev.date, status: ev.status}}) AS events,
          collect(DISTINCT {{title: a.title, source: a.source, url: a.url, pub_date: a.pub_date}}) AS articles
   LIMIT 5

2. "How are X and Y related":
   MATCH (a:Entity), (b:Entity)
   WHERE toLower(a.name) CONTAINS toLower("X") AND toLower(b.name) CONTAINS toLower("Y")
   OPTIONAL MATCH p = (a)-[:RELATES_TO*1..3]-(b)
   RETURN a.name, b.name, [r IN relationships(p) | {{type: r.type, causal: r.causal}}] AS rels,
          [n IN nodes(p) | n.name] AS path
   LIMIT 10

3. "Who/what does X sanction/trade with/etc":
   MATCH (e:Entity)-[r:RELATES_TO]->(t:Entity)
   WHERE toLower(e.name) CONTAINS toLower("X") AND r.type = "sanctions"
   RETURN e.name, r.type, t.name, t.type
   LIMIT 25

4. "What events involve X":
   MATCH (e:Entity)-[:INVOLVED_IN]->(ev:Event)
   WHERE toLower(e.name) CONTAINS toLower("X")
   OPTIONAL MATCH (a:Article)-[:EVIDENCES]->(ev)
   RETURN ev.name, ev.date, ev.status, e.name,
          collect(DISTINCT a.title) AS source_articles
   LIMIT 25

Rules:
- Return ONLY a valid Cypher READ query (no mutations).
- Use case-insensitive matching with toLower() or CONTAINS for entity names.
- ALWAYS use :RELATES_TO with r.type for relationship filtering. Never use dynamic edge labels.
- For general "tell me about" questions, use pattern #1 to return full neighborhood.
- Always include source articles (via :EVIDENCES) when possible — users want provenance.
- Limit results to 25 rows unless the user asks for more.
- Always alias return columns clearly.
- If the question cannot be answered with a Cypher query, return exactly: NONE
- Do NOT wrap the query in markdown code fences.
"""

SYNTHESIZE_SYSTEM = """You are a geopolitical intelligence analyst. Given a user's question and data retrieved from a knowledge graph, provide a clear, concise answer.

Rules:
- Base your answer ONLY on the provided graph data. Do not make up facts.
- If the data is empty or insufficient, say so honestly.
- Mention specific entities, relationships, and dates from the data.
- If source articles are available, reference them.
- Keep answers focused and structured. Use bullet points for lists.
- For complex questions, organize by theme or entity.
"""

ROUTER_SYSTEM = """You are a router for a geopolitical knowledge graph assistant.
Given a user message, decide whether it requires querying the Neo4j graph database
or can be answered directly (e.g. greetings, meta-questions about the system, clarifications).

The graph contains Entity nodes (persons, countries, organizations, locations, etc.),
Event nodes, Article nodes, and typed relationships between them.

Respond with exactly one word:
- "graph" if the question needs data from the knowledge graph
- "direct" if you can answer without querying (greetings, system questions, clarifications)
"""


# ---------------------------------------------------------------------------
# LangGraph State
# ---------------------------------------------------------------------------

class ChatState(TypedDict):
    """State flowing through the LangGraph."""
    messages: list                  # conversation history (HumanMessage / AIMessage)
    question: str                   # current user question
    route: str                      # "graph" or "direct"
    cypher: str                     # generated Cypher query
    graph_context: str              # raw results from Neo4j
    answer: str                     # final answer to return


# ---------------------------------------------------------------------------
# Graph Agent
# ---------------------------------------------------------------------------

class GraphChatAgent:
    """LangGraph agent that answers questions using the Neo4j knowledge graph."""

    def __init__(self, model: str = "openai/gpt-oss-20b"):
        self.llm = ChatGroq(model_name=model, temperature=0, max_tokens=2048)
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        self.graph = self._build_graph()

    def close(self):
        self.driver.close()

    # --- Node functions ---

    def _route_node(self, state: ChatState) -> ChatState:
        """Decide whether we need a graph query or can answer directly."""
        messages = [
            SystemMessage(content=ROUTER_SYSTEM),
            HumanMessage(content=state["question"]),
        ]
        resp = self.llm.invoke(messages)
        route = resp.content.strip().lower()
        if "graph" in route:
            state["route"] = "graph"
        else:
            state["route"] = "direct"
        logger.debug(f"Router: {state['route']} for question: {state['question']}")
        return state

    def _generate_cypher_node(self, state: ChatState) -> ChatState:
        """Generate a Cypher query from the user question."""
        # Include recent conversation for context
        history = _format_history(state["messages"][-6:])  # last 3 turns
        messages = [
            SystemMessage(content=CYPHER_SYSTEM),
        ]
        if history:
            messages.append(HumanMessage(content=f"Conversation so far:\n{history}\n\nNew question: {state['question']}"))
        else:
            messages.append(HumanMessage(content=state["question"]))

        resp = self.llm.invoke(messages)
        cypher = resp.content.strip()

        # Strip markdown code fences if LLM wraps them anyway
        cypher = re.sub(r"^```(?:cypher)?\s*", "", cypher)
        cypher = re.sub(r"\s*```$", "", cypher)

        state["cypher"] = cypher
        logger.info(f"Generated Cypher: {cypher}")
        return state

    def _execute_cypher_node(self, state: ChatState) -> ChatState:
        """Execute Cypher against Neo4j and store results."""
        cypher = state.get("cypher", "")

        if not cypher or cypher.upper() == "NONE":
            state["graph_context"] = ""
            state["route"] = "direct"  # fallback to direct answer
            return state

        # Safety: reject mutations
        upper = cypher.upper()
        if any(kw in upper for kw in ["CREATE", "MERGE", "DELETE", "SET ", "REMOVE ", "DROP "]):
            state["graph_context"] = "[Query rejected: only read queries are allowed]"
            return state

        try:
            with self.driver.session() as session:
                result = session.run(cypher)
                records = [dict(r) for r in result]

            if not records:
                state["graph_context"] = "The query returned no results."
            else:
                context = _format_records(records, cypher)

                # --- Neighborhood enrichment ---
                # If result is thin (few rows, few columns, looks like just entity
                # info), auto-fetch the full neighborhood for richer answers.
                if _is_thin_result(records):
                    entity_names = _extract_entity_names(records)
                    if entity_names:
                        extra = self._fetch_neighborhood(session, entity_names)
                        if extra:
                            context += "\n\n--- Additional context (entity neighborhood) ---\n" + extra

                state["graph_context"] = context

            logger.info(f"Cypher returned {len(records)} rows")
        except Exception as e:
            logger.error(f"Cypher execution failed: {e}")
            state["graph_context"] = f"Query failed with error: {e}"

        return state

    def _fetch_neighborhood(self, session, entity_names: list[str]) -> str:
        """Fetch relationships, events, and articles for a list of entity names."""
        all_lines = []
        for name in entity_names[:3]:  # cap at 3 entities
            try:
                result = session.run("""
                    MATCH (e:Entity {name: $name})
                    OPTIONAL MATCH (e)-[r:RELATES_TO]->(t:Entity)
                    OPTIONAL MATCH (e)<-[r2:RELATES_TO]-(s:Entity)
                    OPTIONAL MATCH (e)-[:INVOLVED_IN]->(ev:Event)
                    OPTIONAL MATCH (a:Article)-[:EVIDENCES]->(e)
                    RETURN e.name AS entity, e.type AS type,
                           collect(DISTINCT {relation: r.type, target: t.name, target_type: t.type}) AS outgoing,
                           collect(DISTINCT {relation: r2.type, source: s.name, source_type: s.type}) AS incoming,
                           collect(DISTINCT {event: ev.name, date: ev.date, status: ev.status}) AS events,
                           collect(DISTINCT {title: a.title, source: a.source, url: a.url}) AS articles
                    LIMIT 1
                """, name=name)
                rec = result.single()
                if not rec:
                    continue

                lines = [f"\nEntity: {rec['entity']} ({rec['type']})"]

                outgoing = [r for r in rec["outgoing"] if r.get("target")]
                if outgoing:
                    lines.append("  Outgoing relationships:")
                    for r in outgoing:
                        lines.append(f"    → {r['relation']} → {r['target']} ({r.get('target_type', '')})")

                incoming = [r for r in rec["incoming"] if r.get("source")]
                if incoming:
                    lines.append("  Incoming relationships:")
                    for r in incoming:
                        lines.append(f"    ← {r['relation']} ← {r['source']} ({r.get('source_type', '')})")

                events = [e for e in rec["events"] if e.get("event")]
                if events:
                    lines.append("  Events:")
                    for e in events:
                        lines.append(f"    - {e['event']} (date: {e.get('date', '?')}, status: {e.get('status', '?')})")

                articles = [a for a in rec["articles"] if a.get("title")]
                if articles:
                    lines.append(f"  Source articles ({len(articles)}):")
                    for a in articles[:10]:
                        lines.append(f"    - \"{a['title']}\" ({a.get('source', '')})")

                if len(lines) > 1:  # more than just the header
                    all_lines.extend(lines)

            except Exception as e:
                logger.debug(f"Neighborhood fetch for '{name}' failed: {e}")

        return "\n".join(all_lines)

    def _synthesize_node(self, state: ChatState) -> ChatState:
        """Synthesize a natural-language answer from graph results."""
        messages = [
            SystemMessage(content=SYNTHESIZE_SYSTEM),
            HumanMessage(content=(
                f"User question: {state['question']}\n\n"
                f"Knowledge graph data:\n{state['graph_context']}"
            )),
        ]
        resp = self.llm.invoke(messages)
        state["answer"] = resp.content
        return state

    def _direct_answer_node(self, state: ChatState) -> ChatState:
        """Answer without querying the graph (greetings, meta questions, etc.)."""
        history = _format_history(state["messages"][-6:])
        messages = [
            SystemMessage(content=(
                "You are a helpful geopolitical intelligence assistant backed by a knowledge graph. "
                "Answer the user's message. If they're asking about the system, explain that you can "
                "answer questions about entities, relationships, events, and trends in the knowledge graph. "
                "Keep it concise."
            )),
        ]
        if history:
            messages.append(HumanMessage(content=f"Conversation:\n{history}\n\nUser: {state['question']}"))
        else:
            messages.append(HumanMessage(content=state["question"]))

        resp = self.llm.invoke(messages)
        state["answer"] = resp.content
        return state

    # --- Routing edge ---

    def _route_edge(self, state: ChatState) -> Literal["generate_cypher", "direct_answer"]:
        if state.get("route") == "graph":
            return "generate_cypher"
        return "direct_answer"

    # --- Build the graph ---

    def _build_graph(self) -> StateGraph:
        g = StateGraph(ChatState)

        # Nodes
        g.add_node("router", self._route_node)
        g.add_node("generate_cypher", self._generate_cypher_node)
        g.add_node("execute_cypher", self._execute_cypher_node)
        g.add_node("synthesize", self._synthesize_node)
        g.add_node("direct_answer", self._direct_answer_node)

        # Edges
        g.add_edge(START, "router")
        g.add_conditional_edges("router", self._route_edge)
        g.add_edge("generate_cypher", "execute_cypher")
        g.add_edge("execute_cypher", "synthesize")
        g.add_edge("synthesize", END)
        g.add_edge("direct_answer", END)

        return g.compile()

    # --- Public API ---

    def chat(self, question: str, history: list | None = None) -> dict:
        """Run the agent on a question. Returns dict with answer + metadata.

        Args:
            question: The user's question.
            history: List of {"role": "user"|"assistant", "content": "..."} dicts.

        Returns:
            {
                "answer": str,
                "cypher": str | None,
                "graph_context": str | None,
                "route": str,
            }
        """
        messages = []
        if history:
            for msg in history:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                else:
                    messages.append(AIMessage(content=msg["content"]))

        state: ChatState = {
            "messages": messages,
            "question": question,
            "route": "",
            "cypher": "",
            "graph_context": "",
            "answer": "",
        }

        result = self.graph.invoke(state)
        return {
            "answer": result["answer"],
            "cypher": result.get("cypher") or None,
            "graph_context": result.get("graph_context") or None,
            "route": result.get("route", ""),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_history(messages: list) -> str:
    """Format message list into a readable conversation string."""
    lines = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            lines.append(f"User: {msg.content}")
        elif isinstance(msg, AIMessage):
            lines.append(f"Assistant: {msg.content}")
    return "\n".join(lines)


def _format_neo4j_value(v) -> str:
    """Format a Neo4j value for display."""
    if v is None:
        return "null"
    if isinstance(v, dict):
        # Node or relationship properties
        parts = [f"{k}={_format_neo4j_value(val)}" for k, val in v.items()]
        return "{" + ", ".join(parts) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(_format_neo4j_value(i) for i in v) + "]"
    return str(v)


def _format_records(records: list[dict], cypher: str) -> str:
    """Format Neo4j records as readable text."""
    lines = []
    for i, rec in enumerate(records[:25]):
        parts = []
        for k, v in rec.items():
            parts.append(f"{k}: {_format_neo4j_value(v)}")
        lines.append(f"  {i+1}. {', '.join(parts)}")
    return f"Query: {cypher}\n\nResults ({len(records)} rows):\n" + "\n".join(lines)


def _is_thin_result(records: list[dict]) -> bool:
    """Check if query results are 'thin' — just entity name/type with no context."""
    if len(records) > 5:
        return False
    # Check if the result only has simple scalar values (no lists, no nested dicts)
    total_values = 0
    non_null_values = 0
    list_values = 0
    for rec in records:
        for v in rec.values():
            total_values += 1
            if v is not None:
                non_null_values += 1
            if isinstance(v, list) and len(v) > 0:
                list_values += 1
    # Thin if few columns, no list values (no aggregated data)
    return list_values == 0 and non_null_values <= 6


def _extract_entity_names(records: list[dict]) -> list[str]:
    """Extract entity name strings from query results."""
    names = []
    for rec in records:
        for k, v in rec.items():
            if isinstance(v, str) and k.lower() in ("name", "entity", "entity_name", "e.name"):
                names.append(v)
    return list(dict.fromkeys(names))  # dedup preserving order
