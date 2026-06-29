#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  Collins Aerospace MRO PoC — Demo Launcher
#
#  Usage:
#    chmod +x demo.sh
#    ./demo.sh          # start everything
#    ./demo.sh stop     # tear down
#    ./demo.sh seed     # seed Melbourne HQ (cross-tenant, run once)
#    ./demo.sh status   # check what's running
# ═══════════════════════════════════════════════════════════════════

set -e
cd "$(dirname "$0")"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'
BOLD='\033[1m'

banner() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  Collins Aerospace MRO — PoC Demo${NC}"
    echo -e "${CYAN}  NextXR Digital Twin${NC} + ${PURPLE}AUTOMIND${NC} + ${GREEN}GoalCert${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"
    echo ""
}

# ── STOP ──
if [ "$1" = "stop" ]; then
    echo -e "${YELLOW}Stopping all services...${NC}"
    docker compose down 2>/dev/null || true
    pkill -f "server.main" 2>/dev/null || true
    echo -e "${GREEN}All stopped.${NC}"
    exit 0
fi

# ── STATUS ──
if [ "$1" = "status" ]; then
    echo -e "${BOLD}Docker containers:${NC}"
    docker compose ps 2>/dev/null || echo "  (docker compose not running)"
    echo ""
    echo -e "${BOLD}NextXR server:${NC}"
    curl -s http://localhost:8000/api/v1/health 2>/dev/null && echo "" || echo "  Not running"
    exit 0
fi

# ── SEED MELBOURNE HQ ──
if [ "$1" = "seed" ]; then
    echo -e "${CYAN}Seeding Melbourne HQ (cross-tenant intelligence)...${NC}"
    cd nextxr-ontology
    python -m scripts.seed_melbourne_hq
    exit 0
fi

# ── START ──
banner

# Step 1: Infrastructure
echo -e "${YELLOW}[1/4]${NC} Starting infrastructure (Neo4j + Redis)..."
docker compose up -d neo4j redis 2>&1 | grep -v "^$"

echo -e "${YELLOW}[2/4]${NC} Waiting for Neo4j to be healthy..."
for i in $(seq 1 30); do
    if docker compose exec -T neo4j cypher-shell -u neo4j -p nextxr2026 "RETURN 1" >/dev/null 2>&1; then
        echo -e "       ${GREEN}Neo4j ready.${NC}"
        break
    fi
    sleep 2
    echo -n "."
done

# Step 2: Install deps if needed
echo -e "${YELLOW}[3/4]${NC} Checking Python dependencies..."
cd nextxr-ontology
pip install -q -r ../requirements.txt 2>/dev/null || echo "       (install deps manually: pip install -r requirements.txt)"

# Step 3: Start NextXR server
echo -e "${YELLOW}[4/4]${NC} Starting NextXR server on port 8000..."
python -m server.main &
SERVER_PID=$!

# Wait for server
sleep 3
if curl -s http://localhost:8000/api/v1/health >/dev/null 2>&1; then
    echo -e "       ${GREEN}Server ready.${NC}"
else
    echo -e "       ${YELLOW}Server starting (may take a few more seconds)...${NC}"
    sleep 5
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Demo is ready!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${CYAN}NextXR Dashboard:${NC}  http://localhost:8000"
echo -e "  ${CYAN}Neo4j Browser:${NC}     http://localhost:7474"
echo -e "  ${CYAN}API Docs:${NC}          http://localhost:8000/docs"
echo ""
echo -e "  ${BOLD}Demo Script:${NC}"
echo -e "  ${YELLOW}1.${NC} Create twin → Twins panel → Create → 'Aerospace MRO Facility'"
echo -e "  ${YELLOW}2.${NC} Start feed  → LiveOps → Start (scripted mode)"
echo -e "  ${YELLOW}3.${NC} Watch       → Sensor cards light up, findings stream in"
echo -e "  ${YELLOW}4.${NC} Diagnose    → Incidents appear, diagnosis chain built"
echo -e "  ${YELLOW}5.${NC} GoalCert    → 'Launch Training Scenario' button appears"
echo -e "  ${YELLOW}6.${NC} Cross-tenant→ Switch to 'collins-melb-hq' (run ./demo.sh seed first)"
echo ""
echo -e "  ${PURPLE}Server PID: ${SERVER_PID}${NC} — stop with: ${BOLD}./demo.sh stop${NC}"
echo ""

# Keep running
wait $SERVER_PID
