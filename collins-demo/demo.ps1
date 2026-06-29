# demo.ps1 — launcher for the Collins agentic-twin demo app (Windows / PowerShell).
#
# Prereq: the platforms are up in Docker  ->  ../start.ps1   (Neo4j + NextXR + AUTOMIND + GoalCert)
#
#   ./demo.ps1           start the orchestrator (BFF) on :8090, then print the web command
#   ./demo.ps1 -Web      also start the Vite web app (:5174) in a new window
#
# The orchestrator runs from the repo-root .venv and talks to the platforms;
# the web app talks only to the orchestrator. Set ANTHROPIC_API_KEY in
# collins-demo/orchestrator/.env to make the agent (scenario author + analysis) real.

param([switch]$Web)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot           # repo root
$demo = $PSScriptRoot
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
# NB: avoid a local named $web — PowerShell variables are case-insensitive, so
# it would collide with the [switch]$Web parameter.
$orch = Join-Path $demo "orchestrator"
$webDir = Join-Path $demo "web"

function Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }

if (-not (Test-Path $venvPy)) {
    Write-Host "  [!!] venv not found at .venv — run ../start.ps1 setup first" -ForegroundColor Yellow
    return
}

# Free :8090 (stale orchestrator)
Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { try { Stop-Process -Id $_ -Force } catch {} }

if (-not (Test-Path (Join-Path $orch ".env"))) {
    Write-Host "  [i] No orchestrator/.env — agent runs in deterministic stub mode." -ForegroundColor DarkGray
    Write-Host "      Copy orchestrator/.env.example to .env and add ANTHROPIC_API_KEY to enable Claude." -ForegroundColor DarkGray
}

if ($Web) {
    Step "Starting web app (Vite) on :5174 in a new window"
    if (-not (Test-Path (Join-Path $webDir "node_modules"))) {
        Push-Location $webDir; npm install; Pop-Location
    }
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$webDir'; npm run dev"
}

Step "Starting orchestrator on http://localhost:8090"
Write-Host "  -> Web UI:  http://localhost:5174" -ForegroundColor Green
if (-not $Web) {
    Write-Host "  Start the web app in another window:  cd collins-demo/web ; npm run dev" -ForegroundColor Cyan
}
Write-Host ""
Push-Location $orch
try { & $venvPy -m uvicorn main:app --port 8090 } finally { Pop-Location }
