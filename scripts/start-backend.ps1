param(
  [string]$DatabaseUrl = "sqlite:///./shravya.db"
)

$env:SHRAVYA_DATABASE_URL = $DatabaseUrl
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
