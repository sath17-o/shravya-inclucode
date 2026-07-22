# Shravya

Shravya is a Malayalam-first inclusive learning platform for Classes 5–10. This repository contains the approved foundation, teacher-guided curriculum context, deterministic Photosynthesis fixture, local speech-recognition foundation, and visible teacher/student judge flow.

It does not implement cloud STT, adaptive learning behaviour, generation, or a chatbot. Local transcription remains teacher-reviewed and is not presented as real-time or pre-benchmarked accuracy.

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
Push-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
Pop-Location

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

## Local transcription modes

- `SHRAVYA_PROVIDER_MODE=deterministic_demo` is the default offline judge fixture. It maps only the bundled WAV and is visibly labelled “not live STT.” Unknown audio fails closed and requires manual entry.
- `SHRAVYA_PROVIDER_MODE=local_faster_whisper` runs `faster-whisper==1.2.1` locally. The initial CPU defaults are `small`, `cpu`, `int8`, Malayalam (`ml`), beam size 5, VAD and word timestamps enabled. The first real request may download model weights; the automated suite never does.

The packaged audio decoder does not require a separately installed FFmpeg executable for this WAV-only proof. No classroom audio is sent to a cloud transcription service by this provider. Local processing still has ordinary device and storage risks, may take longer than the audio, and accuracy varies by speaker, language, noise, and selected model. Teacher review remains mandatory.

Never commit classroom recordings, consent material, ground truth, or benchmark output. Use the gitignored `.runtime/audio/real-classroom-proof/` area for local evidence.

### Local benchmark evidence

From `backend`, run the same local provider used by the application:

```powershell
..\.venv\Scripts\python.exe -m scripts.benchmark_local_stt `
  --audio ..\.runtime\audio\real-classroom-proof\recording.wav `
  --reference-text-file ..\.runtime\audio\real-classroom-proof\reference.txt `
  --terms-file ..\.runtime\audio\real-classroom-proof\terms.txt `
  --model small --device cpu --compute-type int8 --language ml --multilingual `
  --output-dir ..\.runtime\audio\real-classroom-proof\benchmark-output
```

The runner writes atomic `raw-transcript.txt`, `raw-provider-output.json`, `benchmark.json`, and `benchmark.csv` files. It reports raw STT metrics only; teacher-corrected text never contributes to WER, CER, or academic-term recall.
## Photosynthesis judge demo

From `backend`, first migrate the configured database, then create or restore the deterministic baseline:

```powershell
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m scripts.seed_photosynthesis_demo
..\.venv\Scripts\python.exe -m scripts.seed_photosynthesis_demo --reset
```

The baseline contains Class 7 Science with Approved context v1 and hidden Draft context v2. Use `POST /api/v1/teacher/contexts/{v2_id}/submit-for-review`, then `POST /api/v1/teacher/contexts/{v2_id}/approve`; `GET /api/v1/student/courses/{course_id}/lesson-overview` then changes from v1 to v2. Reset restores v1 visibility and the ready v1 artifact.

## Visible judge demo

Reset the backend from `backend`, then start the existing backend command and the frontend development server:

```powershell
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m scripts.seed_photosynthesis_demo --reset
cd ..
.\scripts\start-backend.ps1
npm --prefix frontend run dev
```

Open `/student` to view the currently approved lesson and `/teacher` to review, submit, and approve the newer classroom context. The role switcher is local demo navigation, not sign-in.
