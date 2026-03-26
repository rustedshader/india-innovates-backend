# Setup Guide

## 1. Docker Containers

```bash
# Neo4j (Knowledge Graph)
docker run \
    --restart always \
    --publish=7474:7474 --publish=7687:7687 \
    --env NEO4J_AUTH=neo4j/Shubhang07## \
    --volume=/Users/shubhang/dev/hackathon/india-innovates/neo4j-data:/data \
    neo4j:2026.01.4
```

```bash
# PostgreSQL
docker run --name india-innovates-postgres -p 5432:5432 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=postgres \
  -d postgres
```

```bash
# Redis
docker run --name india-innovates-redis -p 6379:6379 -d redis
```

```bash
# Kafka
docker run -d --name india-innovates-kafka -p 9092:9092 apache/kafka:latest
```

## 2. Environment Variables

Create `.env` in the backend root:

```bash
GROQ_API_KEY=your_key_here
```

## 3. Database Migrations

```bash
uv run alembic upgrade head
```

## 4. Run Everything (One Command)

```bash
./run_all.sh        # Starts all services + API server
./run_all.sh stop   # Stop all background services
```

This starts: Kafka producer, Kafka consumer, signal worker (includes disinfo detection), report scheduler, weather producer, and the API server.

Logs are written to `logs/` directory.

## 5. Run Services Individually

If you prefer running each service in a separate terminal:

```bash
# Kafka Producer (RSS scraper → Kafka)
uv run python -m scheduler.producer

# Kafka Consumer (Kafka → extraction pipeline → Neo4j + Postgres)
uv run python -m scheduler.consumer

# Signal Worker (anomaly detection + disinformation detection, every 15 min)
uv run python -m scheduler.signal_worker

# Report Scheduler (auto-generates domain intelligence reports)
uv run python -m scheduler.report_scheduler

# Weather Producer (weather data ingestion + anomaly detection)
uv run python -m scheduler.weather_producer

# API Server (FastAPI on port 8000)
uv run main.py
```

## 6. One-Time Setup (Weather)

Before the weather producer can detect anomalies, bootstrap 30-year climate normals:

```bash
uv run python -m scheduler.weather_producer --bootstrap-normals
```

Optional — backfill 5 years of historical weather data:

```bash
uv run python -m scheduler.weather_producer --backfill --years 5
```

## 7. API Endpoints

After starting the API server, view all endpoints at:

```
http://localhost:8000/docs
```

Key new endpoints:
- `POST /api/language/analyze` — Indic NLP text analysis
- `GET /api/timeline/{entity}` — Entity state history
- `POST /api/briefs/generate` — Intelligence brief generation
- `GET /api/briefs/sitrep` — Daily situation report