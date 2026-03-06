"""Multi-agent report orchestrator.

Coordinates ReportAgent (domain briefing) and IndiaImpactAgent (India
strategic analysis) to produce enriched intelligence reports.
"""

from __future__ import annotations

import logging

from agents.report import ReportAgent
from agents.india_impact import IndiaImpactAgent

logger = logging.getLogger(__name__)


class ReportOrchestrator:
    """Orchestrates multi-agent report generation.

    Pipeline:
        1. ReportAgent.generate_with_context() → domain briefing + raw data
        2. IndiaImpactAgent.analyze()           → India impact analysis
        3. Merge into unified report
    """

    def __init__(self, model: str = "openai/gpt-oss-20b"):
        self.report_agent = ReportAgent(model=model)
        self.india_impact_agent = IndiaImpactAgent(model=model)
        logger.info("ReportOrchestrator initialized (ReportAgent + IndiaImpactAgent)")

    def close(self):
        self.report_agent.close()
        self.india_impact_agent.close()

    def generate(self, domain: str, date_range: str = "7d") -> dict:
        """Generate an enriched domain report with India impact analysis.

        Args:
            domain: One of climate, defence, economics, geopolitics, society
            date_range: "7d", "30d", etc.

        Returns:
            Dict with all DomainBriefing fields + an 'india_impact' key
            containing the IndiaImpactAnalysis.
        """
        # Step 1: Domain briefing via ReportAgent
        logger.info(f"{'=' * 60}")
        logger.info(f"ORCHESTRATOR Step 1: ReportAgent — {domain.upper()} briefing")
        logger.info(f"{'=' * 60}")

        report_result = self.report_agent.generate_with_context(domain, date_range)

        # Step 2: India impact analysis
        logger.info(f"{'=' * 60}")
        logger.info(f"ORCHESTRATOR Step 2: IndiaImpactAgent — {domain.upper()} India analysis")
        logger.info(f"{'=' * 60}")

        try:
            india_impact = self.india_impact_agent.analyze(domain, report_result)
        except Exception as e:
            logger.error(f"IndiaImpactAgent failed for {domain}: {e}", exc_info=True)
            india_impact = {
                "executive_summary": f"India impact analysis unavailable for {domain}.",
                "strategic_assessment": {"summary": "", "implications": []},
                "transparency_insights": [],
                "national_advantages": [],
                "risks": [],
                "global_positioning": [],
                "recommendations": [],
            }

        # Step 3: Merge
        logger.info(f"{'=' * 60}")
        logger.info(f"ORCHESTRATOR Step 3: Merging report — {domain.upper()}")
        logger.info(f"{'=' * 60}")

        merged = {**report_result.briefing, "india_impact": india_impact}

        logger.info(f"Enriched {domain} report complete (india_impact included)")
        return merged
