#!/usr/bin/env bash
set -euo pipefail
# Public container is intentionally incapable of running private mode.
unset GEMINI_API_KEY GROQ_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY
unset AEGIS_GATEWAY_TOKEN AEGIS_OWNER_PASSWORD
export AEGIS_DEMO_MODE=1
export AEGIS_GATEWAY_TOKEN="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export AEGIS_INTERNAL_BACKEND_URL=http://127.0.0.1:8000
export AEGIS_PUBLIC_DEMO=1 AEGIS_LOCAL_BACKEND=0 AEGIS_CLOUD_ENABLED=0 AEGIS_CUSTOM_CLOUD_ENABLED=0 AEGIS_UNLIMITED_AI=0
export AEGIS_RUNTIME_MODE=public
export AEGIS_AI_ENABLED=0
export PORT="${PORT:-10000}"
export NODE_OPTIONS="--max-old-space-size=256"
backend_pid=""
frontend_pid=""
cleanup() {
  if [[ -n "$frontend_pid" ]]; then kill "$frontend_pid" 2>/dev/null || true; fi
  if [[ -n "$backend_pid" ]]; then kill "$backend_pid" 2>/dev/null || true; fi
  wait || true
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
python -m uvicorn aegis.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log &
backend_pid=$!
cd /app/frontend
HOSTNAME=0.0.0.0 node server.js &
frontend_pid=$!
# If either service exits, stop the container rather than serving a broken app.
wait -n "$backend_pid" "$frontend_pid" || true
exit 1
