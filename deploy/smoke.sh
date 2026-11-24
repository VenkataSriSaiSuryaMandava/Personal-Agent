#!/usr/bin/env bash
set -euo pipefail
image="${1:-aegis-demo:local}"
name="aegis-demo-smoke-$$"
cleanup() {
  local rc=$?
  if (( rc != 0 )); then docker logs "$name" 2>/dev/null || true; fi
  docker rm -f "$name" >/dev/null 2>&1 || true
  exit "$rc"
}
trap cleanup EXIT

docker run -d --name "$name" --memory=512m --memory-swap=512m -e PORT=10000 -p 127.0.0.1::10000 "$image" >/dev/null
port="$(docker port "$name" 10000/tcp | head -n 1)"
base="http://$port"
ready=0
for (( i=0; i<60; i++ )); do
  if curl -fsS --max-time 3 "$base/api/demo/health" >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
if (( ready == 0 )); then echo 'Demo health check failed' >&2; exit 1; fi
curl -fsS --max-time 10 "$base/" | grep -F 'Your command center.' >/dev/null
curl -fsS --max-time 10 "$base/" | grep -F 'Sign in as Owner to use AI' >/dev/null
for id in search systems project; do
  curl -fsS --max-time 10 "$base/api/demo/example?id=$id" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["mode"]=="recorded_demo" and d["prompt"] and d["answer"]'
done
status() { curl -sS --max-time 10 -o /dev/null -w '%{http_code}' -X "$1" "$base$2"; }
test "$(status GET '/api/demo/example?id=invalid')" = 400
test "$(status GET '/api/demo/example?id=search&id=project')" = 400
for path in /api/agent/status /api/auth/session /api/agent/settings /api/agent/settings/providers /api/agent/settings/storage /api/agent/settings/audit; do test "$(status GET "$path")" = 403; done
for path in /api/agent/chat /api/agent/inference /api/agent/conversation /api/auth/login /api/auth/logout; do test "$(status POST "$path")" = 403; done
test "$(status POST '/api/demo/example')" = 405
test "$(status PATCH '/api/agent/settings')" = 403
test "$(status POST '/api/agent/settings/reset')" = 403
# Private app source, key and gateway token must not be present in the runtime.
docker exec "$name" sh -c 'test ! -e /app/demo/aegis && test -z "${GEMINI_API_KEY:-}" && test -z "${AEGIS_GATEWAY_TOKEN:-}" && test "$(id -u)" != 0'
test "$(docker inspect --format '{{.State.OOMKilled}}' "$name")" = false
docker stats --no-stream --format 'Memory usage: {{.MemUsage}}' "$name"
echo 'Public demo smoke checks passed.'
