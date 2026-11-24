# Public portfolio demo

The Docker image contains the Next.js public demo and an independent FastAPI app with three fixed, recorded examples. It does not run the owner API, use the Gemini provider, open the owner database, or accept arbitrary text. The UI deliberately labels recorded content. The normal local owner workspace is unchanged.

## Local container

From the repository root:

```sh
docker build -t aegis-demo:local .
bash deploy/smoke.sh aegis-demo:local
docker run --rm --memory=512m --memory-swap=512m -p 127.0.0.1:8080:10000 aegis-demo:local
```

Open http://127.0.0.1:8080. The smoke script checks both services, all demo examples, denial of the owner routes, non-root execution and an upper memory limit. It removes its test container on exit. It does not validate sustained traffic or Render's CPU limits.

## Render (existing project)

Production uses the existing Render Web Service. Promote main
through a validated pull request into deployment only after explicit
approval. Do not create a second service.

The service uses Docker, repository root, deployment branch,
./Dockerfile, Oregon, Free, health check `/api/demo/health`,
and auto-deploy **After CI Checks Pass**. Leave the Docker command and environment variables empty. Render supplies PORT. Do not enter any personal credentials, API keys or databases. The root render.yaml is an equivalent Blueprint reference; do not provision duplicate services with it.

Free instances may sleep, and their filesystem is ephemeral. This demo has no persistent state. Live cloud inference for public users is deliberately not enabled.

Guest workspace records are temporary. Private workspace APIs,
conversation history and Owner settings remain inaccessible
from the public runtime.

Local smoke testing does not constitute production promotion.
