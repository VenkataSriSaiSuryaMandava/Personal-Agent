FROM node:24-bookworm-slim AS frontend-build
WORKDIR /build/frontend
ENV NEXT_TELEMETRY_DISABLED=1 AEGIS_DOCKER_BUILD=1
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN mkdir -p public && npm run build

FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libstdc++6 libatomic1 tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin aegis
COPY --from=frontend-build /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/aegis ./backend/aegis
RUN python -m pip install --no-cache-dir ./backend
COPY --from=frontend-build --chown=aegis:aegis /build/frontend/.next/standalone /app/frontend
COPY --from=frontend-build --chown=aegis:aegis /build/frontend/.next/static /app/frontend/.next/static
COPY --from=frontend-build --chown=aegis:aegis /build/frontend/public /app/frontend/public
COPY --chmod=755 deploy/start.sh /app/start.sh
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AEGIS_PUBLIC_DEMO=1 AEGIS_LOCAL_BACKEND=0 AEGIS_RUNTIME_MODE=public AEGIS_AI_ENABLED=0 HOME=/home/aegis
USER aegis
EXPOSE 10000
ENTRYPOINT ["/usr/bin/tini", "--", "/app/start.sh"]
