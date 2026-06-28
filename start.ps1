# start.ps1 — one-command BACKEND launcher for the Collins Aerospace PoC (Windows / PowerShell).
#
# Brings the WHOLE backend up in Docker — you never run `python -m server.main` by hand.
# Then start the frontend separately:  cd frontend ; npm run dev   (Vite dev server on :5173).
#
#   ./start.ps1            full backend stack in Docker (build + up):
#                            • Neo4j        :7474 / :7687   (NextXR graph store)
#                            • Redis        :6379           (NextXR event bus)
#                            • Postgres     :5433           (AUTOMIND db)
#                            • Redis-AM     :6380           (AUTOMIND Celery broker)
#                            • NextXR API   :8000           (Digital Twin backend  ← frontend talks here)
#                            • AUTOMIND     :8001           (workflow engine)
#                            • GoalCert     :8002           (simulation engine)
#   ./start.ps1 -Build     force a clean rebuild of all images before starting
#   ./start.ps1 -Infra     databases only (Neo4j+Redis+Postgres+Redis-AM) — for running NextXR from the venv
#   ./start.ps1 -Local     databases + AUTOMIND + GoalCert in Docker, but run the NextXR
#                          backend locally from the venv (live code, hot edits) on :8000
#   ./start.ps1 -Down      stop and remove all PoC containers
#
# This is self-healing: it detects when Docker Desktop is down, starts it, and
# waits for the engine + Neo4j before bringing the stack up.

param(
    [switch]$Build,
    [switch]$Infra,
    [switch]$Local,
    [switch]$Down
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$ontology = Join-Path $root "nextxr-ontology"
$venvPy   = Join-Path $root ".venv\Scripts\python.exe"

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [ok] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [!!] $msg" -ForegroundColor Yellow }

function Test-DockerUp {
    try { docker ps *> $null; return $LASTEXITCODE -eq 0 } catch { return $false }
}

function Test-Port($port) {
    (Test-NetConnection -ComputerName localhost -Port $port -WarningAction SilentlyContinue).TcpTestSucceeded
}

# ── Tear-down shortcut ──────────────────────────────────────────────
if ($Down) {
    Write-Step "Stopping all PoC containers"
    Push-Location $root
    try { docker compose --profile full down } finally { Pop-Location }
    Write-Ok "Stack stopped"
    return
}

# ── 1. Ensure Docker Desktop is running ─────────────────────────────
Write-Step "Checking Docker"
if (Test-DockerUp) {
    Write-Ok "Docker daemon is running"
} else {
    Write-Warn "Docker daemon not responding — starting Docker Desktop"
    $dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerExe) {
        Start-Process $dockerExe
        Write-Host "  Waiting for Docker to become ready (up to 120s)..." -NoNewline
        $ready = $false
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Seconds 2
            Write-Host "." -NoNewline
            if (Test-DockerUp) { $ready = $true; break }
        }
        Write-Host ""
        if ($ready) { Write-Ok "Docker is ready" }
        else {
            Write-Warn "Docker did not come up in time."
            Write-Warn "Open Docker Desktop manually, wait for the whale icon to settle, then re-run ./start.ps1"
            return
        }
    } else {
        Write-Warn "Docker Desktop not found at $dockerExe — start Docker manually, then re-run."
        return
    }
}

# ── 2. Decide which services to bring up ────────────────────────────
# Default + -Local both need the infra; default + -Infra differ only in whether
# the app services (NextXR/AUTOMIND/GoalCert) are containerized.
$infraServices = @("neo4j", "redis", "postgres", "redis-am")

Push-Location $root
try {
    if ($Infra) {
        Write-Step "Starting infrastructure only (databases)"
        docker compose up -d @infraServices
    }
    elseif ($Local) {
        Write-Step "Starting databases + AUTOMIND + GoalCert in Docker (NextXR runs locally)"
        $buildArg = if ($Build) { "--build" } else { $null }
        docker compose --profile full up -d $buildArg @infraServices automind automind-worker goalcert
    }
    else {
        Write-Step "Starting the FULL backend stack in Docker"
        if ($Build) {
            Write-Host "  Rebuilding images (this can take a few minutes the first time)..."
            docker compose --profile full build
        }
        docker compose --profile full up -d
    }
} finally { Pop-Location }

# ── 3. Wait for Neo4j (every mode needs the graph store) ────────────
Write-Step "Waiting for Neo4j on :7687 (up to 60s)"
Write-Host "  " -NoNewline
for ($i = 0; $i -lt 30; $i++) {
    if (Test-Port 7687) { break }
    Start-Sleep -Seconds 2; Write-Host "." -NoNewline
}
Write-Host ""
if (Test-Port 7687) { Write-Ok "Neo4j is reachable" }
else { Write-Warn "Neo4j not reachable yet — give it another moment." }

# ── 4. Local mode: run the NextXR backend from the venv ─────────────
if ($Local) {
    if (-not (Test-Path $venvPy)) {
        Write-Warn "venv not found at .venv — create it with:  python -m venv .venv ; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
        return
    }
    Write-Step "Freeing port 8000 (kill stale local servers)"
    $pids = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
        try { taskkill /F /T /PID $procId *> $null; Write-Ok "killed stale server (PID $procId)" } catch {}
    }

    Write-Step "Starting the NextXR backend locally (venv)"
    Write-Host "  → NextXR API:  http://localhost:8000        (← the frontend talks here)" -ForegroundColor Green
    Write-Host "  → API docs:    http://localhost:8000/docs" -ForegroundColor Green
    Write-Host "  → AUTOMIND:    http://localhost:8001    GoalCert: http://localhost:8002" -ForegroundColor Green
    Write-Host "  Then run the frontend in another window:  cd frontend ; npm run dev" -ForegroundColor Cyan
    Write-Host ""
    $env:NEO4J_URI      = "bolt://localhost:7687"
    $env:NEO4J_USER     = "neo4j"
    $env:NEO4J_PASSWORD = "nextxr2026"
    $env:NXR_REDIS_URL  = "redis://localhost:6379/0"
    $env:AUTOMIND_URL   = "http://localhost:8001"
    $env:GOALCERT_URL   = "http://localhost:8002"
    Push-Location $ontology
    try { & $venvPy -m server.main } finally { Pop-Location }
    return
}

# ── 5. Containerized modes: wait for the NextXR API health ──────────
if (-not $Infra) {
    Write-Step "Waiting for the NextXR API on :8000 (up to 90s)"
    Write-Host "  " -NoNewline
    $healthy = $false
    for ($i = 0; $i -lt 45; $i++) {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/health" -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { $healthy = $true; break }
        } catch {}
        Start-Sleep -Seconds 2; Write-Host "." -NoNewline
    }
    Write-Host ""
    if ($healthy) { Write-Ok "NextXR backend is up" }
    else { Write-Warn "NextXR API not answering yet — check 'docker compose logs -f server'." }
}

# ── 6. Summary ──────────────────────────────────────────────────────
Write-Step "Backend is running in Docker"
docker compose --profile full ps
Write-Host ""
if ($Infra) {
    Write-Host "  Infra only. Run the NextXR backend with:  ./start.ps1 -Local" -ForegroundColor Cyan
} else {
    Write-Host "  → NextXR API:  http://localhost:8000        (← the frontend talks here)" -ForegroundColor Green
    Write-Host "  → API docs:    http://localhost:8000/docs" -ForegroundColor Green
    Write-Host "  → AUTOMIND:    http://localhost:8001        GoalCert: http://localhost:8002" -ForegroundColor Green
}
Write-Host ""
Write-Host "  Now start the frontend separately (Vite dev server → http://localhost:5173):" -ForegroundColor Cyan
Write-Host "      cd frontend ; npm run dev" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Stop everything with:  ./start.ps1 -Down" -ForegroundColor DarkGray
