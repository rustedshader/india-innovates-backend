from fastapi import APIRouter, Query
from neo4j import GraphDatabase
from config import NEO4J_URI, NEO4J_AUTH

router = APIRouter(prefix="/api")
driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)


@router.get("/graph")
def get_graph(
    limit: int = Query(100, ge=1, le=1000, description="Max entity/event nodes to return"),
    min_connections: int = Query(1, ge=0, description="Minimum relationships to include a node"),
    entity_type: str | None = Query(None, description="Filter by entity type (comma-separated, e.g. Country,Person)"),
    search: str | None = Query(None, description="Search for entity by name (case-insensitive)"),
):
    """Return a filtered subgraph for visualization.

    By default returns the top-N most-connected Entity and Event nodes
    (no Article nodes — they're only used for provenance on click).
    """
    with driver.session() as session:
        # Build the WHERE clauses dynamically
        where_clauses = []
        params: dict = {"limit": limit, "min_connections": min_connections}

        if entity_type:
            types = [t.strip() for t in entity_type.split(",") if t.strip()]
            where_clauses.append("e.type IN $entity_types")
            params["entity_types"] = types

        if search:
            where_clauses.append("toLower(e.name) CONTAINS toLower($search)")
            params["search"] = search

        where_str = " AND ".join(where_clauses)
        if where_str:
            where_str = "WHERE " + where_str

        # Step 1: Get top-N entities ranked by connection count
        entity_query = f"""
            MATCH (e:Entity)
            {where_str}
            OPTIONAL MATCH (e)-[r:RELATES_TO]-()
            WITH e, count(r) AS degree
            WHERE degree >= $min_connections
            ORDER BY degree DESC
            LIMIT $limit
            RETURN collect({{
                id: elementId(e),
                labels: labels(e),
                props: properties(e),
                degree: degree
            }}) AS entities
        """
        entity_result = session.run(entity_query, **params).single()
        entity_nodes = entity_result["entities"] if entity_result else []

        # Collect entity IDs for edge query
        entity_ids = [n["id"] for n in entity_nodes]

        if not entity_ids:
            return {"nodes": [], "edges": []}

        # Step 2: Get events connected to these entities
        event_result = session.run("""
            MATCH (e:Entity)-[:INVOLVED_IN]->(ev:Event)
            WHERE elementId(e) IN $entity_ids
            RETURN collect(DISTINCT {
                id: elementId(ev),
                labels: labels(ev),
                props: properties(ev),
                degree: 0
            }) AS events
        """, entity_ids=entity_ids).single()
        event_nodes = event_result["events"] if event_result else []

        # Step 3: Get edges between these nodes
        all_ids = entity_ids + [n["id"] for n in event_nodes]

        edge_result = session.run("""
            MATCH (a)-[r]->(b)
            WHERE elementId(a) IN $all_ids AND elementId(b) IN $all_ids
              AND type(r) IN ['RELATES_TO', 'INVOLVED_IN']
            RETURN collect(DISTINCT {
                from: elementId(a),
                to: elementId(b),
                type: type(r),
                props: properties(r)
            }) AS edges
        """, all_ids=all_ids).single()
        edges = edge_result["edges"] if edge_result else []

        # Step 4: Attach source articles to nodes (single batched query)
        all_nodes = entity_nodes + event_nodes

        # Deduplicate
        seen = set()
        unique_nodes = []
        for n in all_nodes:
            if n["id"] not in seen:
                seen.add(n["id"])
                unique_nodes.append(n)

        # Batch-fetch sources for all nodes in one query
        node_names = [
            {"name": n["props"].get("name", ""), "label": n["labels"][0]}
            for n in unique_nodes
        ]

        sources_result = session.run("""
            UNWIND $nodes AS node
            CALL {
                WITH node
                WITH node WHERE node.label = 'Entity'
                MATCH (a:Article)-[:EVIDENCES]->(e:Entity {name: node.name})
                RETURN node.name AS name, a.title AS title, a.url AS url,
                       a.source AS source, a.pub_date AS pub_date
                LIMIT 20
                UNION
                WITH node
                WITH node WHERE node.label = 'Event'
                MATCH (a:Article)-[:EVIDENCES]->(ev:Event {name: node.name})
                RETURN node.name AS name, a.title AS title, a.url AS url,
                       a.source AS source, a.pub_date AS pub_date
                LIMIT 20
            }
            RETURN name, collect({title: title, url: url, source: source, pub_date: pub_date}) AS sources
        """, nodes=node_names).data()

        # Build lookup: name -> sources
        sources_by_name = {r["name"]: r["sources"] for r in sources_result}

        for node in unique_nodes:
            name = node["props"].get("name", "")
            node["sources"] = sources_by_name.get(name, [])

    return {"nodes": unique_nodes, "edges": edges}


@router.get("/graph/stats")
def get_graph_stats():
    """Return aggregate stats about the graph (for display)."""
    with driver.session() as session:
        result = session.run("""
            MATCH (e:Entity)
            OPTIONAL MATCH (e)-[r:RELATES_TO]-()
            WITH e.type AS type, count(DISTINCT e) AS count, count(r) AS rels
            RETURN type, count, rels
            ORDER BY count DESC
        """).data()

        total_entities = sum(r["count"] for r in result)
        total_rels = sum(r["rels"] for r in result) // 2  # counted twice

        events = session.run("MATCH (ev:Event) RETURN count(ev) AS count").single()
        articles = session.run("MATCH (a:Article) RETURN count(a) AS count").single()

        return {
            "total_entities": total_entities,
            "total_relationships": total_rels,
            "total_events": events["count"] if events else 0,
            "total_articles": articles["count"] if articles else 0,
            "by_type": result,
        }
