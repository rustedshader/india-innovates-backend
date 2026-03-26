"""City metadata lookup service with geocoding fallback."""

import logging
from typing import Optional, Dict
from sqlalchemy import select
from sqlalchemy.orm import Session
from geopy.geocoders import Nominatim
from rapidfuzz import fuzz

from models.city_metadata import CityMetadata

logger = logging.getLogger(__name__)


class CityNotFoundError(Exception):
    """Raised when a city cannot be found in database or via geocoding."""

    pass


class CityService:
    """
    City metadata lookup service.

    Provides city information with fallback hierarchy:
    1. Database exact match
    2. Database fuzzy match
    3. External geocoding API
    4. Raise CityNotFoundError
    """

    def __init__(self, db_session: Session):
        self.db = db_session
        self.geocoder = Nominatim(user_agent="india-innovates")
        self._cache: Dict[str, Dict] = {}

    def get_city_metadata(self, city_name: str) -> Dict:
        """
        Get city metadata with fallback hierarchy.

        Args:
            city_name: Name of the city to lookup

        Returns:
            Dict with keys: city_name, latitude, longitude, zone, state, elevation_meters, is_india_seed

        Raises:
            CityNotFoundError: If city cannot be found
        """
        # Check cache first
        if city_name in self._cache:
            logger.debug(f"City '{city_name}' found in cache")
            return self._cache[city_name]

        # 1. Exact match in database
        result = self.db.execute(
            select(CityMetadata).where(CityMetadata.city_name.ilike(city_name))
        ).scalar_one_or_none()

        if result:
            metadata = {
                "city_name": result.city_name,
                "latitude": result.latitude,
                "longitude": result.longitude,
                "zone": result.zone,
                "state": result.state,
                "elevation_meters": result.elevation_meters,
                "is_india_seed": result.is_india_seed,
            }
            self._cache[city_name] = metadata
            logger.info(f"City '{city_name}' found via exact match")
            return metadata

        # 2. Fuzzy match in database
        all_cities = self.db.execute(select(CityMetadata)).scalars().all()

        best_match = None
        best_score = 0
        for city in all_cities:
            score = fuzz.ratio(city_name.lower(), city.city_name.lower())
            if score > best_score:
                best_score = score
                best_match = city

        if best_score >= 85:  # 85% similarity threshold
            metadata = {
                "city_name": best_match.city_name,
                "latitude": best_match.latitude,
                "longitude": best_match.longitude,
                "zone": best_match.zone,
                "state": best_match.state,
                "elevation_meters": best_match.elevation_meters,
                "is_india_seed": best_match.is_india_seed,
            }
            self._cache[city_name] = metadata
            logger.info(
                f"City '{city_name}' found via fuzzy match to '{best_match.city_name}' "
                f"(score: {best_score})"
            )
            return metadata

        # 3. External geocoding API fallback
        metadata = self._geocode_city(city_name)
        if metadata:
            # Store in database for future use
            self._store_city(metadata)
            self._cache[city_name] = metadata
            logger.info(f"City '{city_name}' found via geocoding API")
            return metadata

        # 4. Not found - raise error
        raise CityNotFoundError(
            f"City '{city_name}' not found in database or geocoding API"
        )

    def _geocode_city(self, city_name: str) -> Optional[Dict]:
        """Use external geocoding API to find city."""
        try:
            location = self.geocoder.geocode(f"{city_name}, India", timeout=10)
            if not location:
                logger.warning(f"Geocoding returned no results for '{city_name}'")
                return None

            # Infer zone based on latitude
            lat = location.latitude
            zone = self._infer_zone(lat, elevation=None)

            metadata = {
                "city_name": city_name,
                "latitude": location.latitude,
                "longitude": location.longitude,
                "zone": zone,
                "state": None,
                "elevation_meters": None,
                "is_india_seed": False,
            }
            logger.info(f"Geocoded '{city_name}' to lat={lat}, lon={location.longitude}, zone={zone}")
            return metadata

        except Exception as e:
            logger.error(f"Geocoding failed for '{city_name}': {e}")
            return None

    def _infer_zone(self, latitude: float, elevation: Optional[float]) -> str:
        """
        Infer geographic zone from coordinates.

        Rules:
        - elevation > 1000m -> hills
        - latitude < 20 -> coastal (southern coast)
        - latitude > 30 -> hills (northern hills)
        - otherwise -> plains
        """
        if elevation and elevation > 1000:
            return "hills"
        if latitude < 20:
            return "coastal"  # Southern coast
        if latitude > 30:
            return "hills"  # Northern hills
        return "plains"

    def _store_city(self, metadata: Dict) -> None:
        """Store newly discovered city in database."""
        try:
            new_city = CityMetadata(
                city_name=metadata["city_name"],
                country="India",
                latitude=metadata["latitude"],
                longitude=metadata["longitude"],
                zone=metadata["zone"],
                state=metadata["state"],
                elevation_meters=metadata["elevation_meters"],
                is_india_seed=False,
            )
            self.db.add(new_city)
            self.db.commit()
            logger.info(f"Stored new city '{metadata['city_name']}' in database")
        except Exception as e:
            self.db.rollback()
            logger.warning(f"Failed to store city '{metadata['city_name']}': {e}")

    def clear_cache(self) -> None:
        """Clear the in-memory cache."""
        self._cache.clear()
        logger.debug("City service cache cleared")
