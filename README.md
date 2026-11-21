# Aegis AI (working title)

A local-first personal agent with a separately deployed synthetic-data demo.

## Milestone 0: foundation

This starter contains a minimal FastAPI health endpoint and a pure, tested policy evaluator. No AI provider, credentials, personal data, file access, browser automation, authentication, persistence or action execution is enabled yet. The evaluator is not an operating-system sandbox or an enforcement gateway. Never expose this development backend publicly.

## Local development

Requires Python 3.11+. From the repository root:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
python -m uvicorn aegis.main:app --host 127.0.0.1 --port 8000
```

In a second terminal: `curl http://127.0.0.1:8000/health`.

Keep all real runtime data outside the repository, e.g. `~/Library/Application Support/AegisAI/`. Never commit keys, personal documents, screenshots, debug traces or private runtime files. Gitignore is a safety net, not a guarantee. See `docs/architecture.md`.
