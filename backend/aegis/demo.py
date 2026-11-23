"""Independent public demo ASGI app. No owner routes, database or model calls."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(
    title="Aegis public demo",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

EXAMPLES = {
    "search": {
        "prompt": "Compare binary and linear search.",
        "answer": """## Binary search vs. linear search

Linear search checks items one by one. Binary search repeatedly halves a sorted search space.

| Feature | Linear search | Binary search |
|---|---|---|
| Sorted input required | No | Yes |
| Worst-case time | O(n) | O(log n) |
| Extra space (iterative) | O(1) | O(1) |

### Python example

```python
def binary_search(values, target):
    left, right = 0, len(values) - 1
    while left <= right:
        mid = (left + right) // 2
        if values[mid] == target:
            return mid
        if values[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1
```

Use linear search for small or unsorted collections. Use binary search for sorted arrays when efficient lookup matters.""",
    },
    "systems": {
        "prompt": "Explain distributed systems with an example.",
        "answer": """## Distributed systems

A distributed system uses multiple networked computers to cooperate on a common task.

### Example: an online store

1. A frontend receives customer requests.
2. An inventory service tracks products.
3. An order service coordinates purchases.
4. A message queue decouples slower background work.

### Key trade-offs

- **Scalability:** add capacity as demand grows.
- **Reliability:** handle partial failures and retries.
- **Consistency:** decide how services coordinate shared state.
- **Observability:** use logs, metrics and traces to understand failures.

Design around network failures rather than assuming every remote call succeeds.""",
    },
    "project": {
        "prompt": "Plan a fictional software project.",
        "answer": """## Project plan: fictional task tracker

**Goal:** deliver a small task management application in four weeks.

| Week | Milestone | Deliverable |
|---|---|---|
| 1 | Design | API contract and wireframes |
| 2 | Foundation | Task API and storage |
| 3 | Interface | Dashboard and filters |
| 4 | Release | Tests, deployment and documentation |

### Acceptance criteria

- Users can create and complete tasks.
- Invalid requests are rejected safely.
- CI tests run before merging changes.
- The release includes a reproducible deployment procedure.

Keep optional notifications and collaboration out of the first release.""",
    },
}


def reply(body: dict, status: int = 200):
    return JSONResponse(body, status_code=status, headers={
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })


@app.get("/health")
def health():
    return reply({"status": "ok", "mode": "public_demo"})


@app.get("/example")
def example(request: Request):
    params = list(request.query_params.multi_items())
    if len(params) != 1 or params[0][0] != "id":
        return reply({"detail": "Unknown demo example"}, 400)
    result = EXAMPLES.get(params[0][1])
    if result is None:
        return reply({"detail": "Unknown demo example"}, 400)
    return reply({"mode": "recorded_demo", **result})
