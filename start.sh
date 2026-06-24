#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  Anderson Report Automation – Linux/macOS Startup Script
#  Runs the FastAPI server directly (no Docker required)
# ─────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")/backend"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "[SETUP] Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate
source .venv/bin/activate

# Install / update dependencies
echo "[SETUP] Installing dependencies..."
pip install -r requirements.txt --quiet

# Create runtime directories
mkdir -p reports reports-pgta temp drafts/TERA drafts/PGTA uploads/pgta_cnv

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Anderson Report Automation"
echo " Server starting at http://0.0.0.0:8000"
echo " Press Ctrl+C to stop"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

uvicorn main:app --host 0.0.0.0 --port 8000
