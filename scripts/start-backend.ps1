param(
  [string]$DatabaseUrl = "sqlite:///./shravya.db"
)

$backendDirectory = (Resolve-Path (Join-Path $PSScriptRoot "..\backend")).Path

Push-Location $backendDirectory
try {
  $env:SHRAVYA_DATABASE_URL = $DatabaseUrl
  & ..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
} finally {
  Pop-Location
}
