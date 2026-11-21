from fastapi import FastAPI

app = FastAPI(title="Aegis AI", version="0.1.0", docs_url=None, redoc_url=None)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0", "stage": "foundation"}
