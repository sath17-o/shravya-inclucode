# Shravya

Shravya is a Malayalam-first inclusive learning platform for Classes 5–10. This repository currently contains only the approved **Phase 1 foundation**: typed architecture, database schema, accessible application shell, deterministic Photosynthesis fixtures, and automated smoke tests.

It does not implement transcript processing, adaptive learning behaviour, generation, live providers, or a chatbot.

## Prerequisites

- Python 3.11 with the existing `.venv`
- Node.js 24.x and npm 11.x
- No Docker is required

## Local setup

```powershell
# Backend: install only into the existing virtual environment
.\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"

# Frontend
npm --prefix frontend install

# Copy the documented local configuration if needed
Copy-Item .env.example .env
```

## Commands

```powershell
# Database migration
$env:SHRAVYA_DATABASE_URL = "sqlite:///./shravya.db"
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head

# Backend
.\scripts\start-backend.ps1

# Frontend
npm --prefix frontend run dev

# Formatting and linting
.\.venv\Scripts\python.exe -m ruff format backend
.\.venv\Scripts\python.exe -m ruff check backend
npm --prefix frontend run lint

# Tests
.\.venv\Scripts\python.exe -m pytest backend
npm --prefix frontend run test

# Starts and stops Vite plus Playwright-managed Chromium automatically
npm --prefix frontend run test:e2e

# Install the exact browser used by the E2E command (once per environment)
npm --prefix frontend run test:e2e:install
```

## Contracts and schema notes

- Run `.\.venv\Scripts\python.exe scripts\export-openapi.py` after an approved API change. FastAPI remains the source of truth; a future TypeScript client must be generated from the committed OpenAPI snapshot.
- The migration is explicit and immutable. A lesson belongs only to a chapter, which belongs to a course-context version; this avoids a conflicting duplicate context reference on `Lesson`.
- SQLite foreign keys are enabled. Owned children cascade on deletion; historical artifact transcript links become `NULL` when the referenced transcript is deleted.

## Provider modes

`SHRAVYA_PROVIDER_MODE` accepts `live`, `cached`, or `demo`. Phase 1 exposes configuration only; no paid or external provider is called.

See [system overview](docs/architecture/system-overview.md) and [test strategy](docs/testing/test-strategy.md) for Phase 1 boundaries.
