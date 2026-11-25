#!/usr/bin/env bash
set -euo pipefail

image="${1:-aegis-demo:local}"
name="aegis-public-smoke-$$"
work="$(mktemp -d)"
chmod 700 "$work"

origin="https://aegis-ai-369j.onrender.com"
host="aegis-ai-369j.onrender.com"

cleanup() {
  local rc=$?

  if (( rc != 0 )); then
    docker logs --tail 50 "$name" 2>/dev/null || true
  fi

  docker rm -f "$name" >/dev/null 2>&1 || true

  rm -f "$work/a.cookies" "$work/b.cookies" \
    "$work/a.headers" "$work/b.headers" "$work/body"

  rmdir "$work"
  exit "$rc"
}

trap cleanup EXIT

docker run -d \
  --name "$name" \
  --memory=512m \
  --memory-swap=512m \
  -e PORT=10000 \
  -e AEGIS_PUBLIC_ORIGIN="$origin" \
  -p 127.0.0.1::10000 \
  "$image" >/dev/null

port="$(docker port "$name" 10000/tcp | head -n 1)"
base="http://$port"

request() {
  curl -sS --max-time 20 \
    -H "Host: $host" \
    "$@"
}

status() {
  request \
    -o "$work/body" \
    -w '%{http_code}' \
    "$@"
}

ready=0

for (( i=0; i<60; i++ )); do
  if request -f "$base/api/demo/health" \
    >/dev/null 2>&1
  then
    ready=1
    break
  fi

  sleep 1
done

test "$ready" = 1

request -f "$base/api/demo/health" |
  python3 -c '
import json, sys
d = json.load(sys.stdin)
assert d == {"status": "ok", "mode": "public"}
'

echo "PASS: Shared backend health"

test "$(status "$base/")" = 200
grep -F 'Aegis' "$work/body" >/dev/null

echo "PASS: Application entry"

echo "===== ANONYMOUS ACCESS ====="

for path in \
  auth/session \
  agent/settings \
  agent/settings/providers \
  agent/settings/storage \
  agent/settings/audit \
  agent/conversations \
  agent/career/profile \
  agent/career/resumes \
  agent/career/sources \
  agent/career/jobs
do
  test "$(status "$base/api/$path")" = 401
  echo "PASS: Anonymous $path denied"
done

for workspace in \
  summary tasks jobs email calendar research coding browser memory approvals
do
  test "$(status "$base/api/agent/workspaces/$workspace")" = 401
done

echo "PASS: Anonymous workspace access denied"

test "$(status "$base/api/demo/example?id=search")" = 410

echo "PASS: Recorded responses retired"

echo "===== ORIGIN AND HOST PROTECTION ====="

test "$(status -X POST "$base/api/auth/guest")" = 403

test "$(status -X POST \
  -H 'Origin: https://example.invalid' \
  "$base/api/auth/guest")" = 403

test "$(curl -sS --max-time 10 \
  -o /dev/null -w '%{http_code}' \
  -H 'Host: example.invalid' \
  "$base/api/auth/session")" = 403

test "$(status -X POST \
  -H "Origin: $origin" \
  "$base/api/auth/login")" = 403

echo "PASS: Origin, host and Owner login protection"

echo "===== PUBLIC SESSION INPUT VALIDATION ====="

test "$(status -X POST \
  -H "Origin: $origin" \
  -H 'Content-Type: application/json' \
  --data '{}' \
  "$base/api/auth/guest")" = 422

test "$(status -X POST \
  -H "Origin: $origin" \
  "$base/api/auth/guest?unexpected=1")" = 422

echo "PASS: Unexpected session input rejected"

echo "===== CREATE TWO ISOLATED VISITOR SESSIONS ====="

for visitor in a b
do
  code="$(status -X POST \
    -H "Origin: $origin" \
    -c "$work/$visitor.cookies" \
    -D "$work/$visitor.headers" \
    "$base/api/auth/guest")"

  echo "Visitor $visitor session HTTP status: $code"
  test "$code" = 200

  python3 - "$work/body" "$work/$visitor.headers" <<'PY'
import json
import sys
from pathlib import Path

body = json.loads(Path(sys.argv[1]).read_text())

assert body == {"authenticated": True, "role": "guest"}

headers = Path(sys.argv[2]).read_text().lower()

cookie = next(
    line for line in headers.splitlines()
    if line.startswith("set-cookie: aegis_session=")
)

for attribute in (
    "httponly",
    "secure",
    "samesite=strict",
    "path=/",
):
    assert attribute in cookie, attribute
PY

done

# Use the HTTPS cookie explicitly for local transport.
# Never print session tokens.
cookie_for() {
  python3 - "$work/$1.headers" <<'COOKIEPY'
import re
import sys
from pathlib import Path

headers = Path(sys.argv[1]).read_text()

matches = re.findall(
    r"^set-cookie:\s*(aegis_session=[A-Za-z0-9_-]{43});",
    headers,
    re.IGNORECASE | re.MULTILINE,
)

assert len(matches) == 1
print(matches[0])
COOKIEPY
}

session_a="$(cookie_for a)"
session_b="$(cookie_for b)"

test -n "$session_a"
test -n "$session_b"
test "$session_a" != "$session_b"

echo "PASS: Independent HTTPS-only session cookies"

echo "===== AUTHENTICATED REAL WORKSPACES ====="

for session in "$session_a" "$session_b"
do
  for path in \
    auth/session \
    agent/settings \
    agent/settings/providers \
    agent/settings/storage \
    agent/settings/audit \
    agent/conversations \
    agent/career/profile \
    agent/career/resumes \
    agent/career/sources \
    agent/career/jobs
  do
    test "$(status \
      -H "Cookie: $session" \
      "$base/api/$path")" = 200
  done

  for workspace in \
    summary tasks jobs email calendar research coding browser memory approvals
  do
    test "$(status \
      -H "Cookie: $session" \
      "$base/api/agent/workspaces/$workspace")" = 200
  done
done

echo "PASS: Both sessions access real backend services"

echo "===== CROSS-VISITOR RECORD ISOLATION ====="

task_url="$base/api/agent/workspaces/tasks"

test "$(status -X POST \
  -H "Origin: $origin" \
  -H "Cookie: $session_a" \
  -H 'Content-Type: application/json' \
  --data '{"title":"Synthetic isolation test","status":"todo"}' \
  "$task_url")" = 200

test "$(status \
  -H "Cookie: $session_a" \
  "$task_url")" = 200

grep -F 'Synthetic isolation test' "$work/body" >/dev/null

test "$(status \
  -H "Cookie: $session_b" \
  "$task_url")" = 200

if grep -F 'Synthetic isolation test' "$work/body" >/dev/null
then
  echo "Cross-session data exposure detected" >&2
  exit 1
fi

echo "PASS: Visitor records are isolated"

echo "===== PUBLIC AI RESTRICTION ====="

for endpoint in chat inference conversation
do
  for payload in '{}' '{"message":"Synthetic test"}'
  do
    code="$(status -X POST \
      -H "Origin: $origin" \
      -H "Cookie: $session_a" \
      -H 'Content-Type: application/json' \
      --data "$payload" \
      "$base/api/agent/$endpoint")"

    echo "AI endpoint $endpoint: HTTP $code"
    test "$code" = 403

    python3 - "$work/body" <<'POLICYPY'
import json
import sys
from pathlib import Path

body = json.loads(Path(sys.argv[1]).read_text())

assert body["detail"] == "AI is disabled in this deployment"
POLICYPY
  done
done

echo "PASS: Public AI endpoints denied"

test "$(status \
  -H "Cookie: $session_a" \
  "$base/api/agent/settings")" = 200

python3 - "$work/body" <<'PY'
import json
import sys
from pathlib import Path

d = json.loads(Path(sys.argv[1]).read_text())

for field in ("cloud_enabled", "retain_conversations"):
    assert d["settings"][field] is False
    assert field not in d["editable_fields"]
PY

echo "PASS: AI preferences locked"

echo "===== PUBLIC DATABASE METADATA ====="

test "$(status \
  -H "Cookie: $session_a" \
  "$base/api/agent/settings/storage")" = 200

python3 - "$work/body" <<'PY'
import json
import sys
from pathlib import Path

d = json.loads(Path(sys.argv[1]).read_text())

assert d["schema_version"] == 8
assert d["integrity"] == "ok"
assert d["local_only"] is False
PY

echo "PASS: Shared database schema and public metadata"

echo "===== SESSION REVOCATION ====="

test "$(status -X POST \
  -H "Origin: $origin" \
  -H "Cookie: $session_a" \
  "$base/api/auth/logout")" = 200

test "$(status \
  -H "Cookie: $session_a" \
  "$task_url")" = 401

test "$(status \
  -H "Cookie: $session_b" \
  "$task_url")" = 200

test "$(status -X POST \
  -H "Origin: $origin" \
  -H "Cookie: $session_b" \
  "$base/api/auth/logout")" = 200

echo "PASS: Logout revokes only the selected session"

echo "===== CONTAINER SECURITY ====="

docker exec "$name" sh -c '
  test "$(id -u)" != 0
  test -z "${GEMINI_API_KEY:-}"
  test -z "${GROQ_API_KEY:-}"
  test -z "${AEGIS_OWNER_PASSWORD:-}"
  test ! -e "$HOME/Library/Application Support/AegisAI/aegis.sqlite3"
'

test "$(docker inspect \
  --format '{{.State.OOMKilled}}' "$name")" = false

test "$(docker inspect \
  --format '{{.State.Running}}' "$name")" = true

docker stats --no-stream \
  --format 'Memory usage: {{.MemUsage}}' "$name"

echo "PASS: Non-root runtime and resource checks"
echo "All public runtime smoke checks passed."
