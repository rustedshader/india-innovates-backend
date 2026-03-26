"""Weather threshold lookup service with database-backed configuration.

Provides weather anomaly thresholds with fallback hierarchy:
1. City-specific + season
2. City-specific (any season)
3. Zone-specific + season
4. Zone-specific (any season)
5. Raise error (no silent defaults)
"""

import logging
from typing import Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from models.weather_threshold import WeatherThreshold

logger = logging.getLogger(__name__)


class WeatherThresholdService:
    """
    Weather threshold lookup with database-backed configuration.

    Provides thresholds for heat waves, cold waves, rainfall, etc.
    with proper fallback hierarchy and no silent defaults.
    """

    def __init__(self, db_session: Session):
        self.db = db_session
        self._cache: Dict[str, Dict] = {}

    def get_threshold(
        self,
        city: Optional[str],
        zone: str,
        threshold_type: str,
        season: Optional[str] = None,
    ) -> Dict[str, float]:
        """
        Get weather threshold with fallback hierarchy.

        Args:
            city: City name (optional)
            zone: Geographic zone (plains, coastal, hills)
            threshold_type: Type of threshold (heat_wave_temp, cold_wave_temp, etc.)
            season: Season (winter, summer, monsoon, post_monsoon) - optional

        Returns:
            Dict with keys: threshold_value, departure_value, consecutive_days

        Raises:
            ValueError: If threshold cannot be found in any fallback level
        """
        # Generate cache key
        cache_key = f"{city}:{zone}:{threshold_type}:{season}"
        if cache_key in self._cache:
            logger.debug(f"Threshold cache hit: {cache_key}")
            return self._cache[cache_key]

        # Fallback hierarchy
        threshold = None

        # 1. City-specific + season
        if city and season:
            threshold = self._query_threshold(city, None, season, threshold_type)
            if threshold:
                logger.debug(f"Threshold found: city={city}, season={season}")

        # 2. City-specific (any season)
        if not threshold and city:
            threshold = self._query_threshold(city, None, None, threshold_type)
            if threshold:
                logger.debug(f"Threshold found: city={city}, any season")

        # 3. Zone-specific + season
        if not threshold and season:
            threshold = self._query_threshold(None, zone, season, threshold_type)
            if threshold:
                logger.debug(f"Threshold found: zone={zone}, season={season}")

        # 4. Zone-specific (any season)
        if not threshold:
            threshold = self._query_threshold(None, zone, None, threshold_type)
            if threshold:
                logger.debug(f"Threshold found: zone={zone}, any season")

        # 5. Not found - raise error
        if not threshold:
            raise ValueError(
                f"No threshold found for: city={city}, zone={zone}, "
                f"type={threshold_type}, season={season}"
            )

        # Cache and return
        self._cache[cache_key] = threshold
        return threshold

    def _query_threshold(
        self,
        city: Optional[str],
        zone: Optional[str],
        season: Optional[str],
        threshold_type: str,
    ) -> Optional[Dict[str, float]]:
        """Query database for threshold with specific criteria."""
        query = select(WeatherThreshold).where(
            WeatherThreshold.threshold_type == threshold_type,
            WeatherThreshold.active == True,
        )

        # Add city filter
        if city:
            query = query.where(WeatherThreshold.city == city)
        else:
            query = query.where(WeatherThreshold.city.is_(None))

        # Add zone filter
        if zone:
            query = query.where(WeatherThreshold.zone == zone)

        # Add season filter
        if season:
            query = query.where(WeatherThreshold.season == season)
        else:
            query = query.where(WeatherThreshold.season.is_(None))

        # Order by specificity (prefer city over zone, season over null)
        query = query.order_by(
            WeatherThreshold.city.desc().nullslast(),
            WeatherThreshold.season.desc().nullslast(),
        ).limit(1)

        result = self.db.execute(query).scalar_one_or_none()

        if result:
            return {
                "threshold_value": result.threshold_value,
                "departure_value": result.departure_value or 0.0,
                "consecutive_days": result.consecutive_days or 1,
            }

        return None

    def get_heat_wave_threshold(
        self,
        city: Optional[str],
        zone: str,
        season: Optional[str] = None,
    ) -> Dict[str, float]:
        """Convenience method for heat wave thresholds."""
        return self.get_threshold(city, zone, "heat_wave_temp", season)

    def get_cold_wave_threshold(
        self,
        city: Optional[str],
        zone: str,
        season: Optional[str] = None,
    ) -> Dict[str, float]:
        """Convenience method for cold wave thresholds."""
        return self.get_threshold(city, zone, "cold_wave_temp", season)

    def get_rainfall_threshold(
        self,
        city: Optional[str],
        zone: str,
        season: Optional[str] = None,
    ) -> Dict[str, float]:
        """Convenience method for extreme rainfall thresholds."""
        return self.get_threshold(city, zone, "extreme_rain", season)

    def get_all_thresholds_for_city(
        self,
        city: str,
        zone: str,
        season: Optional[str] = None,
    ) -> Dict[str, Dict[str, float]]:
        """
        Get all thresholds for a city.

        Returns:
            Dict mapping threshold_type to threshold values
        """
        threshold_types = [
            "heat_wave_temp",
            "cold_wave_temp",
            "extreme_rain",
            "very_heavy_rain",
            "heavy_rain",
            "drought_soil_z",
            "cyclone_wind",
        ]

        thresholds = {}
        for threshold_type in threshold_types:
            try:
                thresholds[threshold_type] = self.get_threshold(
                    city, zone, threshold_type, season
                )
            except ValueError:
                # Threshold not found, skip
                pass

        return thresholds

    def clear_cache(self) -> None:
        """Clear the in-memory cache."""
        self._cache.clear()
        logger.debug("Weather threshold cache cleared")
