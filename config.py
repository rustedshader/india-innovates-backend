from dotenv import load_dotenv
import os

load_dotenv()


POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DATABASE = os.getenv("POSTGRES_DATABASE", "postgres")

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "Shubhang07##"))

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "india-innovates")

SCRAPE_INTERVAL_SECONDS = int(os.getenv("SCRAPE_INTERVAL_SECONDS", "1800"))

KAFKA_BATCH_TIMEOUT_SECONDS = int(os.getenv("KAFKA_BATCH_TIMEOUT_SECONDS", "60"))
KAFKA_BATCH_MAX_SIZE = int(os.getenv("KAFKA_BATCH_MAX_SIZE", "50"))

REPORT_INTERVAL_SECONDS = int(os.getenv("REPORT_INTERVAL_SECONDS", "3600"))
REPORT_DATE_RANGE = os.getenv("REPORT_DATE_RANGE", "7d")

WEATHER_SCRAPE_INTERVAL_SECONDS = int(os.getenv("WEATHER_SCRAPE_INTERVAL_SECONDS", "21600"))
WEATHER_HISTORICAL_BACKFILL_YEARS = int(os.getenv("WEATHER_HISTORICAL_BACKFILL_YEARS", "5"))