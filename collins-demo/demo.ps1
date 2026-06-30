# demo.ps1 — one-command launcher for the Collins agentic-twin demo (Windows).
#
#   ./demo.ps1            start everything: Neo4j+Redis (Docker) + NextXR :8000
#                         + orchestrator :8090, then print the web command
#   ./demo.ps1 -Web       also start the Vite web app on :5174
#   ./demo.ps1 -Down      stop everything this script started (ports + containers)
#
# Re-running ALWAYS kills the previous session first, so there is never a stale
# server or a drifting Vite port. The web app is locked to :5174.

param([switch]$Web, [switch]$Down)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot           # repo root
$demo = $PSScriptRoot
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
$orch = Join-Path $demo "orchestrator"
$webDir = Join-Path $demo "web"
$nxrDir = Join-Path $root "nextxr-ontology"

function Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  [ok] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [!!] $m" -ForegroundColor Yellow }

# Kill whatever is listening on a TCP port (clears stale servers / Vite).
function Free-Port($port) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } catch {} }
}
function Test-Backend {
    try { return ((Invoke-WebRequest -Uri "http://localhost:8000/api/v1/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) }
    catch { return $false }
}

# ── kill any previous session (orchestrator + Vite range) ──
Step "Stopping any previous session"
Free-Port 8090                                   # orchestrator
5174..5180 | ForEach-Object { Free-Port $_ }      # Vite (current + any drifted)
Ok "previous orchestrator + web stopped"

if ($Down) {
    Step "Stopping NextXR + Docker"
    Free-Port 8000
    Push-Location $root; try { docker compose down 2>&1 | Out-Null } catch {} ; Pop-Location
    Ok "all stopped."
    return
}

if (-not (Test-Path $venvPy)) { Warn "venv not found at .venv — run ../start.ps1 setup first"; return }
if (-not (Test-Path (Join-Path $orch ".env"))) {
    Write-Host "  [i] No orchestrator/.env — agents run in deterministic stub mode (copy .env.example, add ANTHROPIC_API_KEY)." -ForegroundColor DarkGray
}

# ── bring up the NextXR backend — ALWAYS restart it fresh ──
# A stale NextXR left over from a previous session (running older code) is the
# usual cause of "Unknown template 'edm-machine'" / Wire EDM not loading. So we
# kill whatever is on :8000 and start a clean server every run.
Step "NextXR backend on :8000 (fresh restart)"
Free-Port 8000

$dockerOk = $true
try { docker ps *> $null; if ($LASTEXITCODE -ne 0) { $dockerOk = $false } } catch { $dockerOk = $false }
if (-not $dockerOk) { Warn "Docker Desktop does not appear to be running. Start it, then re-run ./demo.ps1." }

Push-Location $root; try { docker compose up -d neo4j redis 2>&1 | Out-Null } catch { Warn "docker compose up failed." } ; Pop-Location

Write-Host "  Waiting for Neo4j to be healthy (up to 80s)..." -ForegroundColor DarkGray
for ($i = 0; $i -lt 40; $i++) {
    $h = (docker inspect --format '{{.State.Health.Status}}' collins-neo4j 2>$null)
    if ($h -eq 'healthy') { break }
    Start-Sleep -Seconds 2
}

$cmd = "cd '$nxrDir'; " +
       "`$env:NEO4J_URI='bolt://localhost:7687'; `$env:NEO4J_USER='neo4j'; " +
       "`$env:NEO4J_PASSWORD='nextxr2026'; `$env:NXR_REDIS_URL='redis://localhost:6379/0'; " +
       "`$host.UI.RawUI.WindowTitle='NextXR :8000'; & '$venvPy' -m server.main"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd

Write-Host "  Waiting for NextXR on :8000 (up to 120s)..." -ForegroundColor DarkGray
$ready = $false
for ($i = 0; $i -lt 60; $i++) { if (Test-Backend) { $ready = $true; break }; Start-Sleep -Seconds 2 }
if ($ready) { Ok "NextXR backend is up (fresh)." }
else { Warn "NextXR didn't come up in time — check the 'NextXR :8000' window for the error." }

# ── web app (Vite) locked to :5174 ──
if ($Web) {
    Step "Web app (Vite) on :5174"
    if (-not (Test-Path (Join-Path $webDir "node_modules"))) { Push-Location $webDir; npm install; Pop-Location }
    $vcmd = "cd '$webDir'; `$host.UI.RawUI.WindowTitle='Web :5174'; npm run dev"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $vcmd
    Ok "web app starting — http://localhost:5174"
}

# ── orchestrator (foreground; this window is the BFF) ──
Step "Orchestrator on http://localhost:8090"
Write-Host "  -> Web UI:  http://localhost:5174" -ForegroundColor Green
if (-not $Web) { Write-Host "  Start the web app:  cd collins-demo/web ; npm run dev   (or re-run with -Web)" -ForegroundColor Cyan }
Write-Host "  Stop everything:  ./demo.ps1 -Down" -ForegroundColor DarkGray
Write-Host ""
Push-Location $orch
try { & $venvPy -m uvicorn main:app --port 8090 } finally { Pop-Location }
