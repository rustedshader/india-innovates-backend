#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# India Innovates — Run All Services
# ──────────────────────────────────────────────────────────────────────
# Usage:
#   chmod +x run_all.sh
#   ./run_all.sh          # Start everything
#   ./run_all.sh stop     # Kill all background processes
# ──────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

LOG_DIR="$SCRIPT_DIR/logs"
PID_FILE="$SCRIPT_DIR/.run_all_pids"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ── Stop command ─────────────────────────────────────────────────────
if [ "$1" = "stop" ]; then
    echo -e "${YELLOW}Stopping all services...${NC}"
    if [ -f "$PID_FILE" ]; then
        while read -r pid name; do
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid"
                echo -e "  ${RED}✗${NC} Stopped $name (PID $pid)"
            fi
        done < "$PID_FILE"
        rm -f "$PID_FILE"
    else
        echo "No PID file found. Nothing to stop."
    fi
    exit 0
fi

# ── Pre-flight checks ────────────────────────────────────────────────
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  India Innovates — Starting All Services${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""

# Check Docker containers
echo -e "${YELLOW}[1/7] Checking Docker containers...${NC}"
for container in india-innovates-postgres india-innovates-redis india-innovates-kafka; do
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${container}$"; then
        echo -e "  ${GREEN}✓${NC} $container is running"
    else
        echo -e "  ${RED}✗${NC} $container is NOT running"
        echo -e "  ${YELLOW}  Trying to start it...${NC}"
        docker start "$container" 2>/dev/null || echo -e "  ${RED}  Failed — run the Docker commands from docs/setup.md first${NC}"
    fi
done

# Check Neo4j (runs on custom port)
if docker ps 2>/dev/null | grep -q "neo4j"; then
    echo -e "  ${GREEN}✓${NC} Neo4j is running"
else
    echo -e "  ${RED}✗${NC} Neo4j is NOT running — start it from docs/setup.md"
fi
echo ""

# Check .env
if [ ! -f .env ]; then
    echo -e "${RED}[!] .env file not found — create it with GROQ_API_KEY=...${NC}"
    exit 1
fi

# ── Alembic migrations ───────────────────────────────────────────────
echo -e "${YELLOW}[2/7] Running Alembic migrations...${NC}"
uv run alembic upgrade head
echo -e "  ${GREEN}✓${NC} Database migrated"
echo ""

# ── Create log directory ─────────────────────────────────────────────
mkdir -p "$LOG_DIR"
> "$PID_FILE"  # clear PID file

# ── Helper to launch a background process ────────────────────────────
launch() {
    local name="$1"
    local cmd="$2"
    local log_file="$LOG_DIR/${name}.log"

    echo -e "${YELLOW}[Starting]${NC} $name"
    echo -e "  Command: $cmd"
    echo -e "  Log:     $log_file"

    eval "$cmd" > "$log_file" 2>&1 &
    local pid=$!
    echo "$pid $name" >> "$PID_FILE"
    echo -e "  ${GREEN}✓${NC} $name started (PID $pid)"
    echo ""
}

# ── Launch services ──────────────────────────────────────────────────

echo -e "${YELLOW}[3/7] Starting Kafka Producer (RSS scraper)...${NC}"
launch "producer" "uv run python -m scheduler.producer"

echo -e "${YELLOW}[4/7] Starting Kafka Consumer (extraction pipeline)...${NC}"
launch "consumer" "uv run python -m scheduler.consumer"

echo -e "${YELLOW}[5/7] Starting Signal Worker (anomaly detection)...${NC}"
launch "signal_worker" "uv run python -m scheduler.signal_worker"

echo -e "${YELLOW}[6/7] Starting Report Scheduler...${NC}"
launch "report_scheduler" "uv run python -m scheduler.report_scheduler"

echo -e "${YELLOW}[7/7] Starting Weather Producer...${NC}"
launch "weather_producer" "uv run python -m scheduler.weather_producer"

# ── Summary ──────────────────────────────────────────────────────────
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  All background services started!${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  Logs:     ${LOG_DIR}/"
echo -e "  PIDs:     ${PID_FILE}"
echo ""
echo -e "  ${YELLOW}To start the API server (foreground):${NC}"
echo -e "    uv run main.py"
echo ""
echo -e "  ${YELLOW}To stop all background services:${NC}"
echo -e "    ./run_all.sh stop"
echo ""
echo -e "  ${YELLOW}To tail all logs:${NC}"
echo -e "    tail -f ${LOG_DIR}/*.log"
echo ""

# ── Start API server in foreground ───────────────────────────────────
echo -e "${CYAN}Starting API server (foreground — Ctrl+C to stop everything)...${NC}"
echo ""

# Trap Ctrl+C to also stop background services
trap './run_all.sh stop; exit 0' INT TERM

uv run main.py
