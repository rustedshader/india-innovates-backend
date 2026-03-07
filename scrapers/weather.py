"""Weather data scraper using the Open-Meteo API.

Open-Meteo provides free weather data with no API key required:
  - Historical daily data: archive-api.open-meteo.com
  - 7-day forecast: api.open-meteo.com
  - 30-year climate normals: climate-api.open-meteo.com
"""

import logging
from dataclasses import dataclass
from datetime import date

import numpy as np
import openmeteo_requests
import requests_cache
from retry_requests import retry
import pandas as pd

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# India city grid — 25 cities covering all major climate zones
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class City:
    name: str
    lat: float
    lon: float
    zone: str  # climate classification for threshold selection


INDIA_CITIES: list[City] = [
    City("Delhi", 28.6139, 77.2090, "plains"),
    City("Mumbai", 19.0760, 72.8777, "coastal"),
    City("Chennai", 13.0827, 80.2707, "coastal"),
    City("Kolkata", 22.5726, 88.3639, "plains"),
    City("Bangalore", 12.9716, 77.5946, "plains"),
    City("Hyderabad", 17.3850, 78.4867, "plains"),
    City("Ahmedabad", 23.0225, 72.5714, "plains"),
    City("Pune", 18.5204, 73.8567, "plains"),
    City("Jaipur", 26.9124, 75.7873, "plains"),
    City("Lucknow", 26.8467, 80.9462, "plains"),
    City("Bhopal", 23.2599, 77.4126, "plains"),
    City("Patna", 25.6093, 85.1376, "plains"),
    City("Guwahati", 26.1445, 91.7362, "plains"),
    City("Bhubaneswar", 20.2961, 85.8245, "coastal"),
    City("Thiruvananthapuram", 8.5241, 76.9366, "coastal"),
    City("Chandigarh", 30.7333, 76.7794, "plains"),
    City("Dehradun", 30.3165, 78.0322, "hills"),
    City("Srinagar", 34.0837, 74.7973, "hills"),
    City("Leh", 34.1526, 77.5771, "hills"),
    City("Jodhpur", 26.2389, 73.0243, "plains"),
    City("Nagpur", 21.1458, 79.0882, "plains"),
    City("Visakhapatnam", 17.6868, 83.2185, "coastal"),
    City("Shillong", 25.5788, 91.8933, "hills"),
    City("Gangtok", 27.3389, 88.6065, "hills"),
    City("Port Blair", 11.6234, 92.7265, "coastal"),
]

CITY_BY_NAME: dict[str, City] = {c.name: c for c in INDIA_CITIES}

# Daily variables requested from Open-Meteo
DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "precipitation_hours",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "relative_humidity_2m_mean",
    "soil_moisture_0_to_7cm_mean",
    "et0_fao_evapotranspiration",
    "shortwave_radiation_sum",
    "weather_code",
]

# Mapping from Open-Meteo variable names to our DB column names
VARIABLE_TO_COLUMN = {
    "temperature_2m_max": "temperature_max",
    "temperature_2m_min": "temperature_min",
    "temperature_2m_mean": "temperature_mean",
    "apparent_temperature_max": "apparent_temperature_max",
    "apparent_temperature_min": "apparent_temperature_min",
    "precipitation_sum": "precipitation_sum",
    "rain_sum": "rain_sum",
    "snowfall_sum": "snowfall_sum",
    "precipitation_hours": "precipitation_hours",
    "wind_speed_10m_max": "wind_speed_max",
    "wind_gusts_10m_max": "wind_gusts_max",
    "relative_humidity_2m_mean": "humidity_mean",
    "soil_moisture_0_to_7cm_mean": "soil_moisture_mean",
    "et0_fao_evapotranspiration": "et0_evapotranspiration",
    "shortwave_radiation_sum": "shortwave_radiation_sum",
    "weather_code": "weather_code",
}

# Endpoints
HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CLIMATE_URL = "https://climate-api.open-meteo.com/v1/climate"


class WeatherScraper:
    """Fetches weather data from Open-Meteo APIs."""

    def __init__(self) -> None:
        cache_session = requests_cache.CachedSession(
            ".weather_cache", expire_after=3600
        )
        retry_session = retry(cache_session, retries=3, backoff_factor=0.5)
        self.om = openmeteo_requests.Client(session=retry_session)

    # ── Single-city fetchers ─────────────────────────────────────────

    def fetch_historical(
        self, city: City, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Fetch daily historical weather for one city.

        Args:
            city: City object with lat/lon.
            start_date: ISO date string (YYYY-MM-DD).
            end_date: ISO date string (YYYY-MM-DD).

        Returns:
            DataFrame indexed by date with one column per variable.
        """
        return self._fetch_daily(city, start_date, end_date, HISTORICAL_URL)

    def fetch_forecast(self, city: City) -> pd.DataFrame:
        """Fetch 7-day forecast for one city."""
        responses = self.om.weather_api(
            FORECAST_URL,
            params={
                "latitude": city.lat,
                "longitude": city.lon,
                "daily": DAILY_VARIABLES,
                "timezone": "Asia/Kolkata",
            },
        )
        return self._parse_daily_response(responses[0])

    def fetch_climate_normals(
        self, city: City, start_year: int = 1991, end_year: int = 2020
    ) -> pd.DataFrame:
        """Fetch long-term daily data for computing climate normals.

        Uses the climate API (EC_Earth3P_HR model) for temperature, precipitation,
        and wind. Soil moisture is not available in the climate API, so normals
        for that variable will be absent unless backfilled via the archive API.

        Returns a raw DataFrame of daily values spanning the given years.
        Caller should aggregate into monthly stats.
        """
        climate_vars = [
            "temperature_2m_max",
            "temperature_2m_min",
            "temperature_2m_mean",
            "precipitation_sum",
            "wind_speed_10m_max",
        ]
        responses = self.om.weather_api(
            CLIMATE_URL,
            params={
                "latitude": city.lat,
                "longitude": city.lon,
                "start_date": f"{start_year}-01-01",
                "end_date": f"{end_year}-12-31",
                "models": "EC_Earth3P_HR",
                "daily": climate_vars,
            },
        )
        return self._parse_daily_response(responses[0], variables=climate_vars)

    # ── Bulk multi-city fetchers ─────────────────────────────────────

    def fetch_all_cities_historical(
        self, start_date: str, end_date: str
    ) -> dict[str, pd.DataFrame]:
        """Fetch historical data for all 25 cities.

        Open-Meteo supports bulk requests with arrays of lat/lon.
        Returns dict mapping city name to DataFrame.
        """
        lats = [c.lat for c in INDIA_CITIES]
        lons = [c.lon for c in INDIA_CITIES]

        responses = self.om.weather_api(
            HISTORICAL_URL,
            params={
                "latitude": lats,
                "longitude": lons,
                "start_date": start_date,
                "end_date": end_date,
                "daily": DAILY_VARIABLES,
                "timezone": "Asia/Kolkata",
            },
        )

        result = {}
        for i, city in enumerate(INDIA_CITIES):
            try:
                result[city.name] = self._parse_daily_response(responses[i])
            except Exception as e:
                logger.error(f"Failed to parse response for {city.name}: {e}")
        return result

    def fetch_all_cities_forecast(self) -> dict[str, pd.DataFrame]:
        """Fetch 7-day forecast for all 25 cities in one bulk request."""
        lats = [c.lat for c in INDIA_CITIES]
        lons = [c.lon for c in INDIA_CITIES]

        responses = self.om.weather_api(
            FORECAST_URL,
            params={
                "latitude": lats,
                "longitude": lons,
                "daily": DAILY_VARIABLES,
                "timezone": "Asia/Kolkata",
            },
        )

        result = {}
        for i, city in enumerate(INDIA_CITIES):
            try:
                result[city.name] = self._parse_daily_response(responses[i])
            except Exception as e:
                logger.error(f"Failed to parse forecast for {city.name}: {e}")
        return result

    # ── Climate normals computation ──────────────────────────────────

    def compute_monthly_normals(self, daily_df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate daily data into monthly normals with statistics.

        Args:
            daily_df: DataFrame with date index and weather variable columns.

        Returns:
            DataFrame with columns: month, variable, mean, std, p5, p25, p75, p95
        """
        daily_df = daily_df.copy()
        daily_df["month"] = daily_df.index.month

        records = []
        variables = [
            "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
            "precipitation_sum", "wind_speed_10m_max", "soil_moisture_0_to_7cm_mean",
        ]

        for var in variables:
            if var not in daily_df.columns:
                continue
            for month in range(1, 13):
                monthly_data = daily_df.loc[daily_df["month"] == month, var].dropna()
                if len(monthly_data) < 10:
                    continue
                records.append({
                    "month": month,
                    "variable": VARIABLE_TO_COLUMN.get(var, var),
                    "mean": float(monthly_data.mean()),
                    "std": float(monthly_data.std()),
                    "p5": float(np.percentile(monthly_data, 5)),
                    "p25": float(np.percentile(monthly_data, 25)),
                    "p75": float(np.percentile(monthly_data, 75)),
                    "p95": float(np.percentile(monthly_data, 95)),
                })

        return pd.DataFrame(records)

    # ── Internal helpers ─────────────────────────────────────────────

    def _fetch_daily(
        self, city: City, start_date: str, end_date: str, url: str
    ) -> pd.DataFrame:
        responses = self.om.weather_api(
            url,
            params={
                "latitude": city.lat,
                "longitude": city.lon,
                "start_date": start_date,
                "end_date": end_date,
                "daily": DAILY_VARIABLES,
                "timezone": "Asia/Kolkata",
            },
        )
        return self._parse_daily_response(responses[0])

    @staticmethod
    def _parse_daily_response(
        response, variables: list[str] | None = None
    ) -> pd.DataFrame:
        """Parse an openmeteo_requests daily response into a clean DataFrame.

        Args:
            response: Single response object from openmeteo_requests.
            variables: Ordered list of variable names that were requested.
                       Must match the order passed to the API so indices align.
                       Defaults to DAILY_VARIABLES (the full 16-variable list).
        """
        if variables is None:
            variables = DAILY_VARIABLES

        daily = response.Daily()

        dates = pd.date_range(
            start=pd.to_datetime(daily.Time(), unit="s", utc=True),
            end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
            freq=pd.DateOffset(seconds=daily.Interval()),
            inclusive="left",
        )

        data: dict[str, list] = {"date": dates}
        for i, var_name in enumerate(variables):
            try:
                values = daily.Variables(i).ValuesAsNumpy()
                col_name = VARIABLE_TO_COLUMN.get(var_name, var_name)
                data[col_name] = values
            except Exception:
                pass

        df = pd.DataFrame(data)
        df = df.set_index("date")
        return df
