# start.ps1 — ONE-COMMAND launcher for the Collins agentic digital-twin demo.
#
# Runs FULLY LOCAL — no Docker, no Neo4j, no separate backend. The orchestrator
# (:8090) runs the live-twin physics (Wire EDM, turbine) + the 3-tier behaviour
# rules + prediction engine IN-PROCESS, and the web app (:5173) talks only to it.
# This is deliberate: the demo can never be broken by Docker not starting.
#
#   ./start.ps1          start the web app (:5173) + orchestrator (:8090)
#   ./start.ps1 -Down    stop both
#
# Re-running ALWAYS kills the previous session first, so there is never a stale
# server or a drifting Vite port. The web app is locked to :5173.
#
# Prereqs: the Python venv at .venv, and (for real AI) ANTHROPIC_API_KEY in
# collins-demo/orchestrator/.env.  Internet is needed for the Claude + Tripo APIs.

param([switch]$Down)

$ErrorActionPreference = "Continue"
$root   = $PSScriptRoot
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
$orch   = Join-Path $root "collins-demo\orchestrator"
$webDir = Join-Path $root "collins-demo\web"

function Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  [ok] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [!!] $m" -ForegroundColor Yellow }

# Kill whatever is listening on a TCP port (clears stale servers / Vite).
function Stop-Port($port) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } catch {} }
}

# ── always kill the previous session ──
Step "Stopping any previous session"
Stop-Port 8090                                   # orchestrator
5173..5180 | ForEach-Object { Stop-Port $_ }      # Vite (current + any drifted)
Ok "previous orchestrator + web stopped"

if ($Down) { Ok "all stopped."; return }

if (-not (Test-Path $venvPy)) {
    Warn "Python venv not found at .venv"
    Write-Host "  Create it once:" -ForegroundColor Cyan
    Write-Host "      python -m venv .venv" -ForegroundColor Cyan
    Write-Host "      .\.venv\Scripts\python.exe -m pip install -r collins-demo\orchestrator\requirements.txt" -ForegroundColor Cyan
    return
}
if (-not (Test-Path (Join-Path $orch ".env"))) {
    Write-Host "  [i] No collins-demo/orchestrator/.env — agents run in deterministic stub mode." -ForegroundColor DarkGray
    Write-Host "      Copy .env.example to .env and add ANTHROPIC_API_KEY to enable Claude." -ForegroundColor DarkGray
}

# ── web app (Vite) locked to :5173 ──
Step "Web app (Vite) on http://localhost:5173"
if (-not (Test-Path (Join-Path $webDir "node_modules"))) {
    Write-Host "  Installing web dependencies (first run only)..." -ForegroundColor DarkGray
    Push-Location $webDir; npm install; Pop-Location
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", (
    "cd '$webDir'; `$host.UI.RawUI.WindowTitle='Web :5173'; npm run dev")
Ok "web app starting — http://localhost:5173"

# ── orchestrator (foreground; this window is the app's brain) ──
Step "Orchestrator on http://localhost:8090  (in-process twin engine — no Docker)"
Write-Host "  -> Open the demo:  http://localhost:5173" -ForegroundColor Green
Write-Host "  Stop everything:   ./start.ps1 -Down" -ForegroundColor DarkGray
Write-Host ""
Push-Location $orch
try { & $venvPy -m uvicorn main:app --port 8090 } finally { Pop-Location }
