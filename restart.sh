#!/usr/bin/env bash

# ==============================================================================
# 🧭 NORTHSTAR WORKSPACE LAUNCHER & WATCHDOG
# ==============================================================================

set -euo pipefail

# ANSI color codes for rich terminal styling
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

# Print Brand Banner
echo -e "${CYAN}${BOLD}"
echo " _   _  ____  ____  _____ _   _ ____ _____  _    ____  "
echo "| \ | |/ __ \|  _ \|_   _| | | / ___|_   _|/ \  |  _ \ "
echo "|  \| | |  | | |_) | | | | |_| \___ \ | | / _ \ | |_) |"
echo "| |\  | |__| |  _ <  | | |  _  |___) || |/ ___ \|  _ < "
echo "|_| \_|\____/|_| \_\ |_| |_| |_|____/ |_/_/   \_\_| \_\\"
echo -e "       🧭 Market Intelligence Workspace${NC}\n"

# ------------------------------------------------------------------------------
# Interactive Setup Function for missing keys
# ------------------------------------------------------------------------------
prompt_for_keys() {
    # Check if we are in an interactive terminal
    if [ ! -t 0 ]; then
        echo -e "${RED}${BOLD}❌ ERROR: Non-interactive execution and .env configuration is missing or invalid.${NC}"
        echo -e "${YELLOW}Please create a valid .env file manually before running in non-interactive mode.${NC}"
        exit 1
    fi
    
    echo -e "${YELLOW}No active configuration detected. Let's configure your workspace!${NC}"
    
    # Prompt for Gemini API Key
    local gemini_key=""
    while [ -z "$gemini_key" ] || [[ "$gemini_key" == *"your_gemini_api_key_here"* ]]; do
        echo -e -n "${BOLD}Enter your Google Gemini API Key${NC} (from https://aistudio.google.com/): "
        read -r gemini_key
        gemini_key=$(echo "$gemini_key" | xargs)
    done
    
    # Prompt for Parallel API Key (Optional)
    echo -e -n "${BOLD}Enter your Parallel Search API Key${NC} (Optional, press Enter to skip): "
    read -r parallel_key
    parallel_key=$(echo "$parallel_key" | xargs)
    
    # Create .env from template if missing
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
        else
            # Create a fallback template if .env.example is missing
            cat <<EOF > .env
GOOGLE_API_KEY=your_gemini_api_key_here
GOOGLE_MODEL=gemini-2.5-flash
PARALLEL_API_KEY=your_parallel_api_key_here
PARALLEL_SEARCH_MODE=basic
ADK_BACKEND=auto
EOF
        fi
        echo -e "${GREEN}Created .env file.${NC}"
    fi
    
    # Update keys safely using python3 (prevents sed cross-platform issues)
    python3 -c "
import sys
import re
content = open('.env').read()
content = re.sub(r'GOOGLE_API_KEY=.*', f'GOOGLE_API_KEY={sys.argv[1]}', content)
if sys.argv[2]:
    content = re.sub(r'PARALLEL_API_KEY=.*', f'PARALLEL_API_KEY={sys.argv[2]}', content)
open('.env', 'w').write(content)
" "$gemini_key" "$parallel_key"
    
    echo -e "${GREEN}✓ .env configuration updated successfully!${NC}\n"
}

# ------------------------------------------------------------------------------
# 1. Environment & Configuration Validations
# ------------------------------------------------------------------------------
echo -e "${BLUE}[1/4] Checking environment configurations...${NC}"

# Check for .env presence
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠ .env configuration file not found.${NC}"
    prompt_for_keys
fi

# Load variables safely from .env (handling carriage returns, comments, and empty lines)
while IFS= read -r line || [ -n "$line" ]; do
    clean_line=$(echo "$line" | tr -d '\r' | xargs)
    [[ -z "$clean_line" ]] && continue
    [[ "$clean_line" =~ ^#.*$ ]] && continue
    export "$clean_line"
done < .env

# Validate GOOGLE_API_KEY presence or placeholder values
if [ -z "${GOOGLE_API_KEY:-}" ] || [[ "$GOOGLE_API_KEY" == *"your_gemini_api_key_here"* ]] || [[ "$GOOGLE_API_KEY" == "" ]]; then
    echo -e "${YELLOW}⚠ GOOGLE_API_KEY is missing or contains the default template value.${NC}"
    prompt_for_keys
    
    # Reload variables after interactive prompt update
    while IFS= read -r line || [ -n "$line" ]; do
        clean_line=$(echo "$line" | tr -d '\r' | xargs)
        [[ -z "$clean_line" ]] && continue
        [[ "$clean_line" =~ ^#.*$ ]] && continue
        export "$clean_line"
    done < .env
fi

# Inform user of active settings
ACTIVE_MODEL="${GOOGLE_MODEL:-gemini-2.5-flash}"
ADK_MODE="${ADK_BACKEND:-auto}"
echo -e "${GREEN}✓ Valid .env configuration found.${NC}"
echo -e "  - Model: ${MAGENTA}${ACTIVE_MODEL}${NC}"
echo -e "  - ADK Mode: ${MAGENTA}${ADK_MODE}${NC}"
if [ -n "${PARALLEL_API_KEY:-}" ] && [[ "$PARALLEL_API_KEY" != *"your_parallel_api_key_here"* ]]; then
    echo -e "  - Search Engine: ${GREEN}Parallel (Advanced Live Search Enabled)${NC}"
else
    echo -e "  - Search Engine: ${YELLOW}Heuristic Local Fallback Engine${NC}"
fi
echo ""

# ------------------------------------------------------------------------------
# 2. Host Dependency Validations & Daemon Startup
# ------------------------------------------------------------------------------
echo -e "${BLUE}[2/4] Verifying system dependencies...${NC}"

# Docker presence check
if ! command -v docker >/dev/null 2>&1; then
    echo -e "${RED}${BOLD}❌ ERROR: Docker client is required but not installed!${NC}" >&2
    exit 1
fi

# Detect compose command syntax
compose() {
    if docker compose version >/dev/null 2>&1; then
        docker compose "$@"
        return
    fi
    if command -v docker-compose >/dev/null 2>&1; then
        docker-compose "$@"
        return
    fi
    echo -e "${RED}${BOLD}❌ ERROR: Neither 'docker compose' nor 'docker-compose' is installed!${NC}" >&2
    exit 1
}

# Check if Docker daemon is active (works for Docker Desktop, Servers, etc.)
if docker info >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Docker daemon is active and running.${NC}"
else
    echo -e "${YELLOW}⚠ Docker daemon is not responding. Checking for Colima VM...${NC}"
    if command -v colima >/dev/null 2>&1; then
        if colima status 2>/dev/null | grep -qi "running"; then
            echo -e "${RED}❌ Docker is still not responding even though Colima is running.${NC}"
            echo -e "${YELLOW}Attempting Colima VM restart...${NC}"
            colima restart
        else
            echo -e "${YELLOW}Starting Colima VM...${NC}"
            colima start
        fi
        
        # Verify daemon after Colima startup
        if ! docker info >/dev/null 2>&1; then
            echo -e "${RED}${BOLD}❌ ERROR: Docker daemon failed to respond after starting Colima.${NC}" >&2
            exit 1
        fi
    else
        echo -e "${RED}${BOLD}❌ ERROR: Docker daemon is not running!${NC}" >&2
        echo -e "${YELLOW}Please start Docker Desktop, Colima, or your system Docker service.${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}✓ Docker environment is ready.${NC}\n"

# ------------------------------------------------------------------------------
# 3. Stack Initialization
# ------------------------------------------------------------------------------
echo -e "${BLUE}[3/4] Orchestrating Docker containers...${NC}"

echo -e "${YELLOW}Stopping active Northstar containers...${NC}"
compose down --remove-orphans

echo -e "${YELLOW}Building and starting Northstar stack...${NC}"
compose up --build -d
echo ""

# ------------------------------------------------------------------------------
# 4. Service Watchdog & Health Check
# ------------------------------------------------------------------------------
echo -e "${BLUE}[4/4] Monitoring stack startup health...${NC}"

# Resolve the host local network IP address robustly
LOCAL_IP=$(python3 -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0]); s.close()" 2>/dev/null || echo "127.0.0.1")

HEALTH_URL="http://${LOCAL_IP}:8000/health"
MAX_ATTEMPTS=30
DELAY=2
HEALTHY=false

echo -e "Polling ${CYAN}${HEALTH_URL}${NC} for health validation:"

for i in $(seq 1 $MAX_ATTEMPTS); do
    echo -ne "  [Attempt $i/$MAX_ATTEMPTS] Waiting for endpoint... \r"
    if curl -sf "$HEALTH_URL" >/dev/null; then
        HEALTHY=true
        echo -ne "\033[2K" # Clear the line
        break
    fi
    sleep $DELAY
done

if [ "$HEALTHY" = true ]; then
    echo -e "${GREEN}${BOLD}🚀 SUCCESS: Northstar is healthy and running!${NC}"
    echo -e "  - Workspace UI:  ${CYAN}${BOLD}http://${LOCAL_IP}:8000${NC}"
    echo -e "  - Health Check:  ${CYAN}http://${LOCAL_IP}:8000/health${NC}"
    echo -e "\nPress ${BOLD}Ctrl+C${NC} to release terminal control (service runs in background)."
    exit 0
else
    echo -e "\n\n${RED}${BOLD}❌ ERROR: Northstar failed to become healthy in time!${NC}" >&2
    echo -e "${YELLOW}Printing last 50 lines of docker logs...${NC}"
    compose logs --tail=50 || true
    exit 1
fi
