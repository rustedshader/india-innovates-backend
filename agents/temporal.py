"""Temporal Agent — attaches time dimension to entities and relationships.

Runs after entity resolution. Uses article pub_date + temporal markers
from extraction to create State nodes and track state transitions.

Phase 5 implementation — currently a passthrough that attaches timestamps.
"""

import logging

from graphs.schemas import ArticleExtraction

logger = logging.getLogger(__name__)


class TemporalAgent:
    """Attaches temporal metadata. Full state-tracking in Phase 5."""

    def process(
        self, extractions: list[tuple[object, ArticleExtraction]]
    ) -> list[tuple[object, ArticleExtraction]]:
        """For now: log temporal markers found. Full implementation later."""
        temporal_rels = 0
        events = 0
        for article, extraction in extractions:
            for rel in extraction.relations:
                if rel.temporal:
                    temporal_rels += 1
            events += len(extraction.events)

        logger.info(
            f"Temporal scan: {temporal_rels} relations with timestamps, "
            f"{events} events across {len(extractions)} articles"
        )
        return extractions
