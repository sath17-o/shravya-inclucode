# Shared contracts

FastAPI/OpenAPI is the API source of truth. Run
`python scripts/export-openapi.py` after an approved API-contract change; the
committed `openapi.json` snapshot is checked by backend tests. A later frontend
client must be generated from that snapshot or the FastAPI OpenAPI endpoint,
never maintained as a contradictory handwritten schema.

This folder also contains fixture schemas. The deterministic Class 7
Photosynthesis fixture remains under `shared/fixtures`.
