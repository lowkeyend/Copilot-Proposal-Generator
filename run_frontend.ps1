# Starts the Next.js frontend on http://localhost:3000
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\frontend"

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing npm dependencies..." -ForegroundColor Cyan
    npm install
}
if (-not (Test-Path ".env.local")) {
    Copy-Item ".env.local.example" ".env.local"
}

Write-Host "Starting frontend at http://localhost:3000" -ForegroundColor Green
npm run dev
