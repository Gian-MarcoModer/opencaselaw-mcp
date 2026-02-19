#!/bin/bash
source ~/.nvm/nvm.sh 2>/dev/null || true
cd /home/clawdbot/.openclaw/workspace-artoo/caselaw-mcp-server
source .venv/bin/activate
# BASE_URL can be set externally; defaults handled in server.py
exec uvicorn server:app --host 0.0.0.0 --port 8090
