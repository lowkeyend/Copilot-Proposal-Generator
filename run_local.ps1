# Starts backend and frontend on localhost for local-only development.
$ErrorActionPreference = "Stop"

Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\run_backend.ps1`""
Start-Sleep -Seconds 3
Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\run_frontend.ps1`""

Write-Host "Started backend and frontend. Open http://localhost:3000 in your browser." -ForegroundColor Green
