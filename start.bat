@echo off
REM start.bat — double-click launcher for the Collins Aerospace PoC backend (Windows).
REM Delegates to start.ps1, which starts Docker Desktop if needed and brings the
REM WHOLE backend up in containers (Neo4j + Redis + Postgres + NextXR + AUTOMIND + GoalCert).
REM
REM After this finishes, start the frontend separately:  cd frontend ^&^& npm run dev
REM
REM Usage from a terminal:
REM   start.bat            full backend stack in Docker
REM   start.bat -Build     force a clean rebuild of all images
REM   start.bat -Infra     databases only (run NextXR from the venv)
REM   start.bat -Local     databases + AUTOMIND + GoalCert in Docker, NextXR from the venv
REM   start.bat -Down      stop and remove all containers
powershell -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
pause
