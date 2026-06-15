# Starts the FastAPI backend on http://localhost:8000
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\backend"

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
}
& ".\.venv\Scripts\Activate.ps1"

Write-Host "Installing dependencies..." -ForegroundColor Cyan
pip install -q -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created backend\.env — add your OPENROUTER_API_KEY." -ForegroundColor Yellow
}

Write-Host "Starting API at http://localhost:8000 (docs at /docs)" -ForegroundColor Green
python -m app.main
