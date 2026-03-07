# Open-Meteo Weather Integration Plan

## Goal

Use the [Open-Meteo API](https://open-meteo.com/) to ingest historical and real-time weather data for India, detect anomalies (heat waves, unusual rainfall, cold snaps, droughts), and feed those insights into the existing knowledge graph and reporting pipeline.

---

## 1. Why Open-Meteo?

| Feature | Detail |
|---|---|
| **Cost** | 100% free for non-commercial use, no API key required |
| **Historical data** | 1940–present via `archive-api.open-meteo.com` |
| **Forecast** | 7-day hourly/daily via `api.open-meteo.com` |
| **Climate normals** | 30-year baselines via `climate-api.open-meteo.com` |
| **Rate limits** | 10,000 requests/day (non-commercial) — more than enough |
| **Variables** | Temperature, precipitation, wind, humidity, soil moisture, UV, air quality, etc. |
| **Resolution** | ~11 km grid (ERA5-Land reanalysis for historical) |

---

## 2. India Station Grid — 25 Representative Cities

Cover all major climate zones (tropical wet, semi-arid, arid, alpine, coastal, continental):

| # | City | Lat | Lon | Climate Zone |
|---|---|---|---|---|
| 1 | Delhi | 28.6139 | 77.2090 | Semi-arid / extreme continental |
| 2 | Mumbai | 19.0760 | 72.8777 | Tropical wet (monsoon) |
| 3 | Chennai | 13.0827 | 80.2707 | Tropical wet-dry |
| 4 | Kolkata | 22.5726 | 88.3639 | Tropical wet-dry |
| 5 | Bangalore | 12.9716 | 77.5946 | Tropical savanna |
| 6 | Hyderabad | 17.3850 | 78.4867 | Semi-arid |
| 7 | Ahmedabad | 23.0225 | 72.5714 | Semi-arid / hot |
| 8 | Pune | 18.5204 | 73.8567 | Tropical wet-dry |
| 9 | Jaipur | 26.9124 | 75.7873 | Semi-arid |
| 10 | Lucknow | 26.8467 | 80.9462 | Humid subtropical |
| 11 | Bhopal | 23.2599 | 77.4126 | Humid subtropical |
| 12 | Patna | 25.6093 | 85.1376 | Humid subtropical |
| 13 | Guwahati | 26.1445 | 91.7362 | Subtropical / high rainfall |
| 14 | Bhubaneswar | 20.2961 | 85.8245 | Tropical wet-dry (cyclone zone) |
| 15 | Thiruvananthapuram | 8.5241 | 76.9366 | Tropical wet |
| 16 | Chandigarh | 30.7333 | 76.7794 | Humid subtropical |
| 17 | Dehradun | 30.3165 | 78.0322 | Subtropical / foothills |
| 18 | Srinagar | 34.0837 | 74.7973 | Humid continental / alpine |
| 19 | Leh | 34.1526 | 77.5771 | Cold desert / alpine |
| 20 | Jodhpur | 26.2389 | 73.0243 | Arid / hot desert |
| 21 | Nagpur | 21.1458 | 79.0882 | Tropical dry |
| 22 | Visakhapatnam | 17.6868 | 83.2185 | Tropical coastal |
| 23 | Shillong | 25.5788 | 91.8933 | Subtropical highland |
| 24 | Gangtok | 27.3389 | 88.6065 | Subtropical highland |
| 25 | Port Blair | 11.6234 | 92.7265 | Tropical / island |

> Open-Meteo supports **bulk multi-location requests** — all 25 can be fetched in a single call.

---

## 3. Weather Variables to Collect

### 3a. Daily Historical & Forecast Variables

```
temperature_2m_max, temperature_2m_min, temperature_2m_mean
apparent_temperature_max, apparent_temperature_min
precipitation_sum, rain_sum, snowfall_sum
precipitation_hours
wind_speed_10m_max, wind_gusts_10m_max
relative_humidity_2m_mean
soil_moisture_0_to_7cm_mean          # drought proxy
et0_fao_evapotranspiration           # drought/agriculture proxy
shortwave_radiation_sum              # solar irradiance
weathercode                          # WMO weather condition code
```

### 3b. Climate Normals (30-year baseline, 1991–2020)

Same variables as above — used as the **reference** for anomaly detection.

---

## 4. Architecture — How It Fits In

```
                          ┌─────────────────────┐
                          │  Open-Meteo APIs     │
                          │  (Historical/        │
                          │   Forecast/Climate)  │
                          └────────┬────────────┘
                                   │  HTTP JSON
                                   ▼
┌──────────────────────────────────────────────────────────┐
│                  WeatherScraper                          │
│  scrapers/weather.py                                     │
│                                                          │
│  • fetch_historical(city, start, end) → DataFrame        │
│  • fetch_forecast(city) → DataFrame                      │
│  • fetch_climate_normals(city) → DataFrame               │
│  • fetch_all_cities_daily() → Dict[city, DataFrame]      │
└────────┬─────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│              WeatherAnomalyDetector                       │
│  agents/weather_anomaly.py                               │
│                                                          │
│  Phase 1: Statistical anomaly detection                  │
│    • Z-score per variable against 30-yr climate normal   │
│    • Rolling window breach (3-day / 7-day extremes)      │
│    • Percentile rank (is today's temp in top 1%?)        │
│                                                          │
│  Phase 2: Classified anomaly events                      │
│    • Heat Wave: Tmax ≥ 40°C for ≥ 3 consecutive days    │
│      (or ≥ 37°C for coastal)                             │
│    • Cold Wave: Tmin ≤ 4°C for ≥ 3 days (plains)        │
│    • Extreme Rainfall: > 204.5 mm/day (IMD definition)   │
│    • Drought Signal: soil_moisture z-score < -1.5 AND    │
│      precip < 20th percentile for ≥ 14 days             │
│    • Cyclone Proxy: wind_gusts > 90 km/h + heavy rain    │
│      at coastal stations                                 │
│                                                          │
│  Phase 3: LLM narrative (reuse Groq/Ollama)             │
│    • Summarize anomalies into human-readable alerts      │
│    • Contextualize: "is this unprecedented?"             │
│    • Link to India impact: agriculture, infrastructure   │
└────────┬─────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│          Integration Points                               │
│                                                          │
│  A. Knowledge Graph (Neo4j)                              │
│     • New node: WeatherAnomaly {type, city, severity,    │
│       start_date, end_date, z_score, description}        │
│     • Relation: (WeatherAnomaly)-[:OCCURRED_AT]->(City)  │
│     • Relation: (WeatherAnomaly)-[:IMPACTS]->(Entity)    │
│       e.g. Agriculture Ministry, specific crop regions   │
│                                                          │
│  B. Climate Domain Reports                               │
│     • Feed into ReportAgent/IndiaImpactAgent as extra    │
│       context alongside news-extracted climate events    │
│     • "Climate" domain report merges news + weather data │
│                                                          │
│  C. PostgreSQL Storage                                   │
│     • New table: weather_observations                    │
│       (city, date, variable, value, z_score, percentile) │
│     • New table: weather_anomalies                       │
│       (city, type, severity, start, end, description)    │
│                                                          │
│  D. API Endpoints                                        │
│     • GET /api/weather/current — latest obs + anomalies  │
│     • GET /api/weather/trends?city=&var=&period=         │
│     • GET /api/weather/anomalies?type=&severity=         │
│     • WebSocket /ws/weather-alerts — real-time anomaly   │
│       push via Redis Pub/Sub                             │
│                                                          │
│  E. Live Feed                                            │
│     • Weather anomalies appear in /ws/live-feed alongside│
│       news articles (new event_type: "weather_anomaly")  │
└──────────────────────────────────────────────────────────┘
```

---

## 5. Implementation Steps

### Phase 1: Data Layer (Week 1)

#### Step 1.1 — `scrapers/weather.py`: WeatherScraper

```python
# Core class that wraps Open-Meteo API calls
# Uses openmeteo-requests + requests-cache for efficiency

ENDPOINTS = {
    "forecast": "https://api.open-meteo.com/v1/forecast",
    "historical": "https://archive-api.open-meteo.com/v1/archive",
    "climate": "https://climate-api.open-meteo.com/v1/climate",
}

class WeatherScraper:
    def __init__(self):
        self.session = requests_cache.CachedSession('.weather_cache', expire_after=3600)
        self.cities = INDIA_CITIES  # 25 cities from §2

    async def fetch_daily(self, lat, lon, start_date, end_date, endpoint="historical"):
        """Fetch daily weather data for a location and date range."""
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date,
            "end_date": end_date,
            "daily": ",".join(DAILY_VARIABLES),
            "timezone": "Asia/Kolkata",
        }
        # Returns pandas DataFrame with date index
        ...

    async def fetch_climate_normals(self, lat, lon):
        """Fetch 30-year climate normals (1991-2020) for baseline."""
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": "1991-01-01",
            "end_date": "2020-12-31",
            "models": "ERA5",
            "daily": ",".join(DAILY_VARIABLES),
        }
        # Aggregate into monthly normals: mean, std, percentiles (5th, 25th, 75th, 95th)
        ...

    async def fetch_all_cities(self, start_date, end_date):
        """Bulk fetch for all 25 cities. Open-Meteo supports multi-lat/lon."""
        # Single request with comma-separated lat/lon arrays
        ...
```

#### Step 1.2 — Database Models

**New Alembic migration:**

```python
# models/weather_observation.py
class WeatherObservation(Base):
    __tablename__ = "weather_observations"
    id = Column(Integer, primary_key=True)
    city = Column(String, index=True, nullable=False)
    date = Column(Date, index=True, nullable=False)
    temperature_max = Column(Float)
    temperature_min = Column(Float)
    temperature_mean = Column(Float)
    precipitation_sum = Column(Float)
    wind_speed_max = Column(Float)
    wind_gusts_max = Column(Float)
    humidity_mean = Column(Float)
    soil_moisture_mean = Column(Float)
    et0_evapotranspiration = Column(Float)
    weather_code = Column(Integer)
    # Anomaly scores (computed post-ingestion)
    temp_max_zscore = Column(Float)
    temp_min_zscore = Column(Float)
    precip_zscore = Column(Float)
    __table_args__ = (UniqueConstraint('city', 'date'),)


# models/weather_anomaly.py
class WeatherAnomalyRecord(Base):
    __tablename__ = "weather_anomalies"
    id = Column(Integer, primary_key=True)
    city = Column(String, index=True, nullable=False)
    anomaly_type = Column(String, nullable=False)  # heat_wave, cold_wave, extreme_rain, drought, cyclone_proxy
    severity = Column(String, nullable=False)       # warning, severe, extreme
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    peak_value = Column(Float)                      # e.g. max temp during heat wave
    z_score = Column(Float)                         # how many σ from normal
    description = Column(Text)                      # LLM-generated narrative
    detected_at = Column(DateTime, server_default=func.now())


# models/climate_normal.py
class ClimateNormal(Base):
    __tablename__ = "climate_normals"
    id = Column(Integer, primary_key=True)
    city = Column(String, nullable=False)
    month = Column(Integer, nullable=False)         # 1-12
    variable = Column(String, nullable=False)       # temperature_max, precipitation_sum, etc.
    mean = Column(Float, nullable=False)
    std = Column(Float, nullable=False)
    p5 = Column(Float)                              # 5th percentile
    p25 = Column(Float)
    p75 = Column(Float)
    p95 = Column(Float)
    __table_args__ = (UniqueConstraint('city', 'month', 'variable'),)
```

#### Step 1.3 — Config additions

```python
# config.py additions
WEATHER_SCRAPE_INTERVAL_SECONDS = int(os.getenv("WEATHER_SCRAPE_INTERVAL_SECONDS", "21600"))  # 6 hours
WEATHER_HISTORICAL_BACKFILL_YEARS = int(os.getenv("WEATHER_HISTORICAL_BACKFILL_YEARS", "5"))
```

---

### Phase 2: Anomaly Detection Engine (Week 2)

#### Step 2.1 — `agents/weather_anomaly.py`: WeatherAnomalyDetector

```python
class WeatherAnomalyDetector:
    """
    Statistical + rule-based anomaly detection for Indian weather data.
    Uses climate normals as baseline, IMD thresholds for event classification.
    """

    # === IMD-aligned thresholds ===
    HEAT_WAVE_RULES = {
        "plains": {"threshold": 40, "departure": 4.5, "consecutive_days": 3},
        "coastal": {"threshold": 37, "departure": 4.5, "consecutive_days": 3},
        "hills": {"threshold": 30, "departure": 5.0, "consecutive_days": 3},
    }
    COLD_WAVE_RULES = {
        "plains": {"threshold": 4, "departure": -4.5, "consecutive_days": 3},
    }
    EXTREME_RAINFALL_THRESHOLD = 204.5  # mm/day (IMD "extremely heavy")
    VERY_HEAVY_RAINFALL_THRESHOLD = 115.6  # mm/day
    DROUGHT_ZSCORE_THRESHOLD = -1.5      # soil moisture z-score
    DROUGHT_PRECIP_PERCENTILE = 20       # precip below 20th percentile
    DROUGHT_MIN_DAYS = 14
    CYCLONE_WIND_THRESHOLD = 90          # km/h

    def compute_anomaly_scores(self, observations_df, normals_df):
        """
        For each observation, compute:
        - z_score = (value - monthly_mean) / monthly_std
        - percentile_rank = where this value falls in the 30-yr distribution
        Returns DataFrame with added z_score and percentile columns.
        """
        ...

    def detect_heat_waves(self, city, observations_df, zone="plains"):
        """Sliding window: find runs of ≥3 days above threshold."""
        ...

    def detect_cold_waves(self, city, observations_df, zone="plains"):
        """Sliding window: find runs of ≥3 days below threshold."""
        ...

    def detect_extreme_rainfall(self, city, observations_df):
        """Single-day or multi-day extreme precipitation events."""
        ...

    def detect_drought_signals(self, city, observations_df, normals_df):
        """
        Compound index: soil_moisture z < -1.5 AND precip < p20
        sustained for ≥14 days.
        """
        ...

    def detect_cyclone_proxy(self, city, observations_df):
        """Coastal stations only: wind gusts > 90 km/h + heavy rain."""
        ...

    def detect_all_anomalies(self, city, observations_df, normals_df):
        """Run all detectors, deduplicate, rank by severity."""
        anomalies = []
        anomalies.extend(self.detect_heat_waves(city, observations_df))
        anomalies.extend(self.detect_cold_waves(city, observations_df))
        anomalies.extend(self.detect_extreme_rainfall(city, observations_df))
        anomalies.extend(self.detect_drought_signals(city, observations_df, normals_df))
        anomalies.extend(self.detect_cyclone_proxy(city, observations_df))
        return sorted(anomalies, key=lambda a: a.severity_rank, reverse=True)

    async def generate_narrative(self, anomalies, city):
        """
        LLM call: Given anomaly data, generate human-readable alert.
        Contextualizes with historical frequency and India impact.
        """
        ...
```

#### Step 2.2 — Trend Analysis Functions

```python
# In agents/weather_anomaly.py or a separate agents/weather_trends.py

class WeatherTrendAnalyzer:
    """Long-term trend analysis for Indian weather data."""

    def compute_annual_trends(self, city, variable, years=30):
        """
        Linear regression on annual means.
        Returns: slope (°C/decade or mm/decade), R², p-value, trend direction.
        Example: "Delhi Tmax has increased 0.3°C/decade since 1995 (p < 0.01)"
        """
        ...

    def compute_monsoon_analysis(self, city, years=10):
        """
        Monsoon-specific analysis (Jun-Sep):
        - Total monsoon rainfall vs normal
        - Onset date estimation (first week with >30mm)
        - Active/break spell detection
        - Dry day count within monsoon
        """
        ...

    def compute_extreme_frequency(self, city, variable, threshold, window_years=5):
        """
        Count days exceeding threshold per year.
        Detect if extreme events are becoming more frequent.
        Example: "Days above 45°C in Delhi: 2 (2015) → 8 (2025)"
        """
        ...

    def compute_seasonal_shift(self, city, years=20):
        """
        Detect if seasons are shifting:
        - First day above 35°C (summer onset)
        - Last day above 35°C (summer end)
        - First significant rain (monsoon proxy)
        - Winter cold days count
        """
        ...

    def compute_diurnal_range_trend(self, city, years=10):
        """
        Track (Tmax - Tmin) over time.
        Shrinking range can indicate urbanization / climate change.
        """
        ...
```

---

### Phase 3: Knowledge Graph Integration (Week 3)

#### Step 3.1 — Neo4j Weather Nodes & Relations

```cypher
// New node labels
CREATE (a:WeatherAnomaly {
    type: "heat_wave",
    city: "Delhi",
    severity: "extreme",
    start_date: date("2026-03-01"),
    end_date: date("2026-03-05"),
    peak_value: 47.2,
    z_score: 3.4,
    description: "Extreme heat wave in Delhi: 47.2°C peak, 3.4σ above normal..."
})

// Link to location entity (already in graph from news extraction)
MATCH (a:WeatherAnomaly {city: "Delhi"}), (e:Entity {name: "Delhi", type: "Location"})
CREATE (a)-[:OCCURRED_AT]->(e)

// Link to impacted entities (agriculture, health, infrastructure)
MATCH (a:WeatherAnomaly {type: "drought", city: "Nagpur"}),
      (e:Entity {name: "Agriculture Ministry"})
CREATE (a)-[:IMPACTS {impact_type: "crop_failure_risk"}]->(e)

// Temporal co-occurrence with news events
MATCH (a:WeatherAnomaly), (ev:Event)
WHERE a.start_date <= ev.date <= a.end_date
  AND ev.name CONTAINS a.city
CREATE (a)-[:COINCIDES_WITH]->(ev)
```

#### Step 3.2 — Enrich Climate Domain Reports

Update `agents/report.py` to pull weather anomaly data when `domain == "climate"`:

```python
# In ReportAgent._gather_domain_data() for climate domain:
# 1. Existing: Cypher query for climate-related news entities & relations
# 2. NEW: Query weather_anomalies table for active/recent anomalies
# 3. NEW: Query weather_observations for current conditions at key cities
# 4. Merge into context for LLM report generation
```

#### Step 3.3 — Cross-reference weather anomalies with news

When the consumer processes a news article about "heat wave" or "floods", try to match it to a detected weather anomaly:

```python
# In GraphBuilder.process_articles():
# After extraction, if any Event has weather-related keywords:
#   → Query weather_anomalies for same city + date range
#   → If match found, create EVIDENCES relationship between Article and WeatherAnomaly
#   → This grounds news reports in actual measured data
```

---

### Phase 4: Scheduler & API (Week 4)

#### Step 4.1 — Weather Producer

```python
# scheduler/weather_producer.py
class WeatherProducer:
    """Runs every 6 hours: fetch + analyze + store + alert."""

    async def run_cycle(self):
        scraper = WeatherScraper()
        detector = WeatherAnomalyDetector()

        # 1. Fetch latest daily data for all 25 cities (single bulk request)
        raw_data = await scraper.fetch_all_cities(
            start_date=(datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
            end_date=datetime.now().strftime("%Y-%m-%d"),
        )

        for city, df in raw_data.items():
            # 2. Load climate normals from Postgres (cached)
            normals = await self.get_normals(city)

            # 3. Compute z-scores and anomaly flags
            scored_df = detector.compute_anomaly_scores(df, normals)

            # 4. Upsert observations to Postgres
            await self.upsert_observations(city, scored_df)

            # 5. Detect anomalies
            anomalies = detector.detect_all_anomalies(city, scored_df, normals)

            # 6. Persist new anomalies
            new_anomalies = await self.save_new_anomalies(city, anomalies)

            # 7. Generate narratives for new anomalies
            for anomaly in new_anomalies:
                anomaly.description = await detector.generate_narrative(anomaly, city)

            # 8. Push to Neo4j graph
            await self.sync_anomalies_to_neo4j(new_anomalies)

            # 9. Publish alerts to Redis Pub/Sub for live feed
            for anomaly in new_anomalies:
                await self.publish_weather_alert(anomaly)

    async def backfill_historical(self, years=5):
        """One-time: fetch 5 years of historical data for trend analysis."""
        ...

    async def compute_climate_normals(self):
        """One-time: fetch 1991-2020 data and compute monthly stats."""
        ...
```

#### Step 4.2 — API Endpoints

```python
# api/routes/weather.py

@router.get("/weather/current")
async def get_current_weather():
    """Latest observations + anomaly flags for all 25 cities."""
    ...

@router.get("/weather/trends")
async def get_weather_trends(
    city: str,
    variable: str = "temperature_max",
    period: str = "5y",
):
    """
    Time-series data for a city and variable.
    Returns: {dates: [...], values: [...], normal: [...], z_scores: [...]}
    Supports chart rendering on frontend.
    """
    ...

@router.get("/weather/anomalies")
async def get_anomalies(
    anomaly_type: Optional[str] = None,
    severity: Optional[str] = None,
    city: Optional[str] = None,
    days: int = 30,
):
    """Filter anomalies by type, severity, city, recency."""
    ...

@router.get("/weather/monsoon")
async def get_monsoon_analysis(year: int = 2026):
    """
    Monsoon season analysis:
    - Cumulative rainfall vs normal curve
    - Active/break spells
    - City-by-city deficit/surplus
    """
    ...

@router.get("/weather/climate-trends")
async def get_climate_trends(city: str, variable: str = "temperature_max"):
    """
    Long-term (30yr) trend analysis:
    - Annual means with linear trend line
    - Extreme event frequency
    - Seasonal shift dates
    """
    ...
```

#### Step 4.3 — Live Feed Integration

```python
# In api/routes/live_feed.py — extend the existing WebSocket handler
# to also subscribe to weather alert channel:

# Redis channel: "india-innovates:weather-alerts"
# Event format:
{
    "event_type": "weather_anomaly",
    "anomaly_type": "heat_wave",
    "city": "Delhi",
    "severity": "extreme",
    "description": "Extreme heat wave in Delhi...",
    "peak_value": 47.2,
    "detected_at": "2026-03-07T12:00:00+05:30"
}
```

---

### Phase 5: LLM-Powered Climate Intelligence (Week 5)

#### Step 5.1 — Weather-Aware Chat

Extend `agents/chat.py` router to recognize weather questions and query both:
- Neo4j (WeatherAnomaly nodes, cross-referenced with news events)
- Postgres (raw observations, trend data)

Example queries the chat should handle:
- "Was this monsoon season normal?"
- "How has Delhi's temperature changed in the last 5 years?"
- "Are heat waves in Rajasthan becoming more frequent?"
- "What weather anomalies coincided with the crop failure news?"

#### Step 5.2 — Weather Context in India Impact Reports

Extend `agents/india_impact.py` to pull weather data for the "climate" domain:

```python
# When domain == "climate":
# 1. Pull active weather anomalies
# 2. Pull monsoon status
# 3. Pull trend data for key cities
# 4. Include in LLM context for India strategic assessment
#
# This means the IndiaImpactAgent can say things like:
# "Risk: Soil moisture in Maharashtra has been 1.8σ below normal for 21 days,
#  satellite-confirmed by Open-Meteo ERA5 data. This correlates with NDTV reports
#  of farmer distress in the region."
```

---

## 6. Dependencies to Add

```toml
# pyproject.toml additions
openmeteo-requests = "^1.3"     # Official Open-Meteo Python client
requests-cache = "^1.2"         # HTTP response caching
retry-requests = "^2.0"         # Auto-retry on transient failures
pandas = "^2.2"                 # DataFrame operations (likely already present)
scipy = "^1.14"                 # Statistical functions (z-score, percentile, linregress)
```

---

## 7. One-Time Bootstrap Steps

```bash
# 1. Compute climate normals (run once, ~25 API calls)
python -m scheduler.weather_producer --bootstrap-normals

# 2. Backfill 5 years of historical data (run once, ~25 API calls)
python -m scheduler.weather_producer --backfill --years 5

# 3. Run Alembic migration for new tables
alembic revision --autogenerate -m "add weather tables"
alembic upgrade head
```

---

## 8. Anomaly Detection — Decision Matrix

| Anomaly Type | Detection Method | IMD Threshold | Z-Score Trigger | Severity Levels |
|---|---|---|---|---|
| **Heat Wave** | 3-day sliding window on Tmax | Plains: 40°C / Coastal: 37°C / departure ≥4.5°C | ≥ 2.0σ | Warning → Severe (≥45°C) → Extreme (≥47°C) |
| **Cold Wave** | 3-day sliding window on Tmin | Plains: Tmin ≤ 4°C / departure ≤ -4.5°C | ≤ -2.0σ | Warning → Severe (≤2°C) → Extreme (≤0°C) |
| **Extreme Rain** | Single-day threshold | Very Heavy: 115.6mm / Extremely Heavy: 204.5mm | ≥ 2.5σ | Heavy → Very Heavy → Extremely Heavy |
| **Drought** | Compound: soil moisture + precip deficit | Soil moisture z < -1.5 AND precip < p20, ≥14 days | Compound | Moderate → Severe → Extreme |
| **Cyclone Proxy** | Wind gusts + precip at coastal stations | Gusts > 90 km/h + rain > 100mm | N/A (rule-based) | Warning → Severe → Extreme |
| **Unusual Warmth** | Daily/Weekly Tmax or Tmean anomaly | N/A | ≥ 1.5σ for Tmean | Notable → Unusual → Extreme |
| **Monsoon Deficit** | Cumulative Jun-Sep rainfall vs normal | < 80% of normal | ≤ -1.0σ cumulative | Deficit → Large Deficit → Drought |

---

## 9. Example Open-Meteo API Calls

### Fetch 7-day forecast for Delhi

```
GET https://api.open-meteo.com/v1/forecast?latitude=28.6139&longitude=77.2090&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean&timezone=Asia/Kolkata
```

### Fetch historical data (Jan 2025) for Delhi

```
GET https://archive-api.open-meteo.com/v1/archive?latitude=28.6139&longitude=77.2090&start_date=2025-01-01&end_date=2025-01-31&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,soil_moisture_0_to_7cm_mean&timezone=Asia/Kolkata
```

### Fetch climate normals for Delhi

```
GET https://climate-api.open-meteo.com/v1/climate?latitude=28.6139&longitude=77.2090&start_date=1991-01-01&end_date=2020-12-31&models=ERA5&daily=temperature_2m_max,precipitation_sum&timezone=Asia/Kolkata
```

---

## 10. File Structure (New Files)

```
scrapers/
  weather.py                    # WeatherScraper — API client
agents/
  weather_anomaly.py            # WeatherAnomalyDetector + WeatherTrendAnalyzer
models/
  weather_observation.py        # WeatherObservation ORM model
  weather_anomaly.py            # WeatherAnomalyRecord ORM model
  climate_normal.py             # ClimateNormal ORM model
scheduler/
  weather_producer.py           # Weather data ingestion scheduler
api/routes/
  weather.py                    # REST endpoints for weather data
alembic/versions/
  xxxx_add_weather_tables.py    # Migration for 3 new tables
```

---

## Summary

This plan adds a **ground-truth weather data layer** to the existing news-driven intelligence graph. The key design decisions are:

1. **Open-Meteo is perfect** — free, no auth, historical + forecast + climate normals, covers India well
2. **25 cities** cover all climate zones — enough for national analysis without hitting rate limits
3. **Statistical anomalies** (z-scores vs 30-yr normals) + **IMD rule-based thresholds** = dual detection
4. **Graph integration** links measured weather events to news-reported events — grounding journalism in data
5. **6-hour refresh cycle** balances freshness with API courtesy
6. **LLM narratives** turn raw numbers into actionable intelligence briefs
7. **Monsoon analysis** is India-specific and high-value for agriculture & infrastructure domains
