```bash
docker run \
    --restart always \
    --publish=7474:7474 --publish=7687:7687 \
    --env NEO4J_AUTH=neo4j/Shubhang07## \
    --volume=/Users/shubhang/dev/hackathon/india-innovates/neo4j-data:/data \
    neo4j:2026.01.4
```

```bash
docker run --name india-innovates-postgres -p 5432:5432 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=postgres \
  -d postgres
```

```bash
docker run --name india-innovates-redis -p 6379:6379 -d redis
```

```bash
docker run -d --name india-innovates-kafka -p 9092:9092 apache/kafka:latest
```


create .env in root 

and add variable 

```bash
GROQ_API_KEY=
```


# Setups to run

alembic upgrade head


# Agents to run in different terminal

```bash
uv run python -m scheduler.consumer
```

```bash
uv run python -m scheduler.producer
```

```bash
uv run python -m scheduler.signal_worker
```

```bash
uv run python -m scheduler.report_scheduler
```

# For weather agent run first run 

```bash
uv run python -m scheduler.weather_producer --bootstrap-normals
```

```bash
uv run python -m scheduler.weather_producer
```

# And Lastly

```bash
uv run main.py
```

----