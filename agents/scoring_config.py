"""Scoring configuration service with database-backed weights.

Provides configurable weights for:
- Domain multipliers (geopolitics, defense, etc.)
- Importance formula components (impact, novelty, india_relevance)
- Coverage bonus parameters (log_base, multiplier)

Supports:
- Database-backed configuration
- In-memory caching for performance
- Fallback to sensible defaults
- Version tracking for A/B testing and learning
"""

import logging
from typing import Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from models.scoring_weight import ScoringWeight

logger = logging.getLogger(__name__)


class ScoringConfig:
    """
    Scoring configuration service with database-backed weights.

    Provides configurable weights for importance scoring formulas,
    domain multipliers, and coverage bonus calculations.
    """

    def __init__(self, db_session: Session):
        self.db = db_session
        self._cache: Dict[str, float] = {}

    def get_domain_weight(self, domain: str) -> float:
        """
        Get domain multiplier weight.

        Args:
            domain: Domain name (geopolitics, defense, etc.)

        Returns:
            Domain weight multiplier (default: 1.0)
        """
        cache_key = f"domain_weight:{domain}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = self.db.execute(
            select(ScoringWeight).where(
                ScoringWeight.weight_type == "domain_multiplier",
                ScoringWeight.component_name == domain,
                ScoringWeight.active == True,
            ).order_by(ScoringWeight.version.desc()).limit(1)
        ).scalar_one_or_none()

        weight = result.weight_value if result else 1.0
        self._cache[cache_key] = weight
        return weight

    def get_formula_weights(self) -> Dict[str, float]:
        """
        Get importance formula component weights.

        Returns:
            Dict with keys: impact_score, novelty_score, india_relevance
            Defaults: {impact_score: 0.5, novelty_score: 0.2, india_relevance: 0.3}
        """
        cache_key = "formula_weights"
        if cache_key in self._cache:
            # Cache stores a single key, but we need to return the full dict
            # So we'll cache each component separately
            pass

        results = self.db.execute(
            select(ScoringWeight).where(
                ScoringWeight.weight_type == "importance_formula",
                ScoringWeight.active == True,
            ).order_by(ScoringWeight.version.desc())
        ).scalars().all()

        # Build dict from results
        weights = {}
        seen_components = set()
        for result in results:
            component = result.component_name
            if component not in seen_components:
                weights[component] = result.weight_value
                seen_components.add(component)
                self._cache[f"formula_weight:{component}"] = result.weight_value

        # Apply defaults if not found
        defaults = {
            "impact_score": 0.5,
            "novelty_score": 0.2,
            "india_relevance": 0.3,
        }
        for key, default_val in defaults.items():
            if key not in weights:
                weights[key] = default_val

        return weights

    def get_coverage_params(self) -> Dict[str, float]:
        """
        Get coverage bonus formula parameters.

        Returns:
            Dict with keys: log_base, multiplier
            Defaults: {log_base: 6.0, multiplier: 0.5}
        """
        results = self.db.execute(
            select(ScoringWeight).where(
                ScoringWeight.weight_type == "coverage_bonus",
                ScoringWeight.active == True,
            ).order_by(ScoringWeight.version.desc())
        ).scalars().all()

        params = {}
        seen_components = set()
        for result in results:
            component = result.component_name
            if component not in seen_components:
                params[component] = result.weight_value
                seen_components.add(component)

        # Apply defaults
        defaults = {
            "log_base": 6.0,
            "multiplier": 0.5,
        }
        for key, default_val in defaults.items():
            if key not in params:
                params[key] = default_val

        return params

    def get_all_domain_weights(self) -> Dict[str, float]:
        """
        Get all domain multiplier weights.

        Returns:
            Dict mapping domain names to weight multipliers
        """
        results = self.db.execute(
            select(ScoringWeight).where(
                ScoringWeight.weight_type == "domain_multiplier",
                ScoringWeight.active == True,
            ).order_by(ScoringWeight.version.desc())
        ).scalars().all()

        weights = {}
        seen_domains = set()
        for result in results:
            domain = result.component_name
            if domain not in seen_domains:
                weights[domain] = result.weight_value
                seen_domains.add(domain)

        return weights

    def clear_cache(self) -> None:
        """Clear the in-memory cache."""
        self._cache.clear()
        logger.debug("Scoring config cache cleared")
