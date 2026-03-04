from fastapi import APIRouter
from neo4j import GraphDatabase
from config import NEO4J_URI, NEO4J_AUTH

router = APIRouter(prefix="/api")
driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)


@router.get("/graph")
def get_graph():
    with driver.session() as session:
        result = session.run("""
            MATCH (n)-[r]-()
            WITH DISTINCT n
            OPTIONAL MATCH (n)-[r]->(m)
            RETURN collect(DISTINCT {
                id: elementId(n), labels: labels(n), props: properties(n)
            }) AS nodes,
            collect(DISTINCT {
                from: elementId(n), to: elementId(m), type: type(r), props: properties(r)
            }) AS edges
        """)
        record = result.single()

        seen = set()
        nodes = []
        for n in record["nodes"]:
            if n["id"] not in seen:
                seen.add(n["id"])
                nodes.append(n)

        edges = [e for e in record["edges"] if e["to"] is not None]
        seen_edges = set()
        unique_edges = []
        for e in edges:
            key = (e["from"], e["to"], e["type"])
            if key not in seen_edges:
                seen_edges.add(key)
                unique_edges.append(e)

        # For each Entity node, attach source articles that EVIDENCES it
        for node in nodes:
            if "Entity" in node["labels"]:
                sources = session.run("""
                    MATCH (a:Article)-[:EVIDENCES]->(e:Entity {name: $name})
                    RETURN a.title AS title, a.url AS url, a.source AS source, a.pub_date AS pub_date
                """, name=node["props"].get("name")).data()
                node["sources"] = sources
            elif "Event" in node["labels"]:
                sources = session.run("""
                    MATCH (a:Article)-[:EVIDENCES]->(ev:Event {name: $name})
                    RETURN a.title AS title, a.url AS url, a.source AS source, a.pub_date AS pub_date
                """, name=node["props"].get("name")).data()
                node["sources"] = sources

    return {"nodes": nodes, "edges": unique_edges}
