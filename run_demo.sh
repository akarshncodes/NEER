#!/bin/bash
# NEER one-command demo launcher (Mac / Linux):   ./run_demo.sh
# Starts the REST API (port 8000) in the background and the dashboard (port 8501), and stops the API on exit.
cd "$(dirname "$0")"
echo "== NEER: installing / checking libraries =="
uv sync -q || { echo "uv sync failed (needs internet the first time)"; exit 1; }
echo "== Starting the REST API on http://localhost:8000 (docs: /docs) =="
uv run uvicorn neer.api.server:app --port 8000 --log-level warning &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT
sleep 2
echo "== Starting the dashboard on http://localhost:8501 =="
echo "   Open the first tab: '▶ Guided demo'. Press Ctrl+C here to stop everything."
uv run streamlit run neer/app/dashboard.py --server.port 8501
