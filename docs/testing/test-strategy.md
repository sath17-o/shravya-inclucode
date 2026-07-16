# Test strategy

## Backend

- pytest covers enum/presentation separation, UUID creation, uniqueness constraints, typed health response, typed error response, and a clean SQLite Alembic migration.
- Tests use only in-memory or temporary SQLite databases.
- No external or paid providers are registered or called.

## Frontend

- Vitest and Testing Library cover skip-link keyboard focus, language selection, Malayalam-first bilingual text, long-text wrapping container, keyboard trust-panel expansion, and text-labelled buttons.
- Playwright and axe-core exercise: launch → role switch → language switch → Learning Preferences → Trust panel.

## Future phases

Every deterministic service requires unit tests. Every provider call is mocked in tests. P0 implementation tests must prove the central quality/stale policy blocks unsafe downstream behaviour.
