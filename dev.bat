@echo off
setlocal EnableDelayedExpansion

:: ============================================================
::  Bicsxm LMS Backend — Start All Dev Services
::
::  Run every time you want to develop. Checks all requirements,
::  then starts:
::    1. PostgreSQL service
::    2. MongoDB (with replica set rs0)
::    3. Redis
::    4. Django dev server  (http://127.0.0.1:8000)
::    5. Celery worker      (separate window)
::
::  Press Ctrl+C to stop the Django server (this window).
::  Close the Celery window to stop that worker.
:: ============================================================

title Bicsxm LMS — Dev Server

:: ── Redis install path (taizod1024.redis-windows-fork via winget) ───
set "REDIS_DIR=C:\Users\princess nona\AppData\Local\Microsoft\WinGet\Packages\taizod1024.redis-windows-fork_Microsoft.Winget.Source_8wekyb3d8bbwe\Redis-8.10.2-Windows-x64-msys2"
set "REDIS_SERVER=%REDIS_DIR%\redis-server.exe"
set "REDIS_CLI=%REDIS_DIR%\redis-cli.exe"

:: ── Locate PostgreSQL bin (supports v16 and v17) ─────────────
set "PG_BIN="
if exist "C:\Program Files\PostgreSQL\17\bin\psql.exe" set "PG_BIN=C:\Program Files\PostgreSQL\17\bin"
if exist "C:\Program Files\PostgreSQL\16\bin\psql.exe" set "PG_BIN=C:\Program Files\PostgreSQL\16\bin"

:: ── Locate MongoDB bin (supports v7 and v8) ──────────────────
set "MONGO_BIN="
if exist "C:\Program Files\MongoDB\Server\8.0\bin\mongod.exe" set "MONGO_BIN=C:\Program Files\MongoDB\Server\8.0\bin"
if exist "C:\Program Files\MongoDB\Server\7.0\bin\mongod.exe" set "MONGO_BIN=C:\Program Files\MongoDB\Server\7.0\bin"

set "MONGO_DATA=C:\data\db"
set "MONGO_LOG=C:\data\mongod.log"

:: ── Use venv python directly (avoids activation / exec policy) ─
set "VENV_PYTHON=.venv\Scripts\python.exe"
set "VENV_CELERY=.venv\Scripts\celery.exe"

:: Add pg + mongo to PATH for psql / mongosh commands
if defined PG_BIN    set "PATH=%PG_BIN%;%PATH%"
if defined MONGO_BIN set "PATH=%MONGO_BIN%;%PATH%"

echo.
echo  =====================================================
echo   Bicsxm LMS Backend ^| Dev Server
echo  =====================================================
echo.

:: ═══════════════════════════════════════════════════════════
::  PRE-FLIGHT CHECKS
:: ═══════════════════════════════════════════════════════════
echo  Checking requirements ...
echo.
set "ERRORS=0"

:: .venv
if exist "%VENV_PYTHON%" (
    echo   [OK] .venv\Scripts\python.exe
) else (
    echo   [MISSING] .venv not found — run setup.bat first
    set "ERRORS=1"
)

:: .env
if exist ".env" (
    echo   [OK] .env
) else (
    echo   [MISSING] .env — run setup.bat first
    set "ERRORS=1"
)

:: PostgreSQL
if defined PG_BIN (
    echo   [OK] PostgreSQL  (%PG_BIN%)
) else (
    echo   [MISSING] PostgreSQL binary not found — run setup.bat first
    set "ERRORS=1"
)

:: MongoDB
if defined MONGO_BIN (
    echo   [OK] MongoDB  (%MONGO_BIN%)
) else (
    echo   [MISSING] MongoDB binary not found — run setup.bat first
    set "ERRORS=1"
)

:: Redis
if exist "%REDIS_SERVER%" (
    echo   [OK] Redis  (%REDIS_DIR%)
) else (
    echo   [MISSING] Redis not found — run setup.bat first
    set "ERRORS=1"
)

echo.
if "%ERRORS%"=="1" (
    echo  [!] Requirements missing. Run setup.bat as Administrator first.
    pause & exit /b 1
)
echo  All requirements satisfied. Starting services ...
echo.

:: ═══════════════════════════════════════════════════════════
::  1. POSTGRESQL SERVICE
:: ═══════════════════════════════════════════════════════════
echo  [1/5] PostgreSQL service ...
set "PG_STARTED=0"
for %%V in (17 16) do (
    if "%PG_STARTED%"=="0" (
        sc query postgresql-x64-%%V >nul 2>&1
        if !errorLevel! EQU 0 (
            sc start postgresql-x64-%%V >nul 2>&1
            echo        postgresql-x64-%%V started (or already running).
            set "PG_STARTED=1"
        )
    )
)
if "%PG_STARTED%"=="0" (
    echo  [WARN] No recognised pg service found. Ensure PostgreSQL is running.
)

:: ═══════════════════════════════════════════════════════════
::  2. MONGODB — ensure db dir exists, start mongod, init rs0
:: ═══════════════════════════════════════════════════════════
echo.
echo  [2/5] MongoDB (replSet rs0) ...
if not exist "%MONGO_DATA%" mkdir "%MONGO_DATA%"

tasklist /FI "IMAGENAME eq mongod.exe" 2>nul | find /I "mongod.exe" >nul
if %errorLevel% NEQ 0 (
    echo        Starting mongod in background ...
    start "MongoDB" /MIN "%MONGO_BIN%\mongod.exe" --replSet rs0 --bind_ip_all --dbpath "%MONGO_DATA%" --logpath "%MONGO_LOG%"
    echo        Waiting for mongod to be ready ...
    timeout /t 6 /nobreak >nul
) else (
    echo        mongod already running.
)

:: Initiate replica set (idempotent)
where mongosh >nul 2>&1
if %errorLevel% EQU 0 (
    mongosh --quiet --eval "try { rs.status().ok } catch(e) { rs.initiate({_id:'rs0',members:[{_id:0,host:'127.0.0.1:27017'}]}); }" >nul 2>&1
    echo        Replica set rs0 ready.
) else (
    echo  [WARN] mongosh not found — skipping rs.initiate(). Install MongoDB Shell.
)

:: ═══════════════════════════════════════════════════════════
::  3. REDIS
:: ═══════════════════════════════════════════════════════════
echo.
echo  [3/5] Redis ...
netstat -an 2>nul | findstr ":6379 " | findstr "LISTENING" >nul
if %errorLevel% EQU 0 (
    echo        Already listening on port 6379.
) else (
    echo        Starting redis-server ...
    start "Redis" /MIN "%REDIS_SERVER%"
    timeout /t 3 /nobreak >nul
    "%REDIS_CLI%" ping >nul 2>&1
    if !errorLevel! EQU 0 (
        echo        Redis started and responding.
    ) else (
        echo  [WARN] Redis may not have started. Check manually.
    )
)

:: ═══════════════════════════════════════════════════════════
::  4. ENSURE DATABASE EXISTS + RUN MIGRATIONS
:: ═══════════════════════════════════════════════════════════
echo.
echo  [4/5] Database + migrations ...

:: Create the lms database if it doesn't exist
set "PGPASSWORD=postgres"
"%PG_BIN%\psql.exe" -U postgres -h 127.0.0.1 -tc "SELECT 1 FROM pg_database WHERE datname='lms';" 2>nul | findstr "1" >nul
if %errorLevel% NEQ 0 (
    "%PG_BIN%\psql.exe" -U postgres -h 127.0.0.1 -c "CREATE DATABASE lms;" >nul 2>&1
    echo        Database 'lms' created.
) else (
    echo        Database 'lms' already exists.
)

:: Run migrations using venv python (no activation needed)
set "DJANGO_SETTINGS_MODULE=config.settings.dev"
"%VENV_PYTHON%" manage.py migrate --noinput
if %errorLevel% NEQ 0 (
    echo  [WARN] Migrations had issues — check output above.
) else (
    echo        Migrations up to date.
)

:: ═══════════════════════════════════════════════════════════
::  5. CELERY WORKER (new window)
:: ═══════════════════════════════════════════════════════════
echo.
echo  [5/5] Celery worker (opening new window) ...
start "Celery Worker" cmd /k "title Celery Worker && set DJANGO_SETTINGS_MODULE=config.settings.dev && .venv\Scripts\celery.exe -A config worker -l info --concurrency=2 -P threads"
echo        Celery started.

:: ═══════════════════════════════════════════════════════════
::  DJANGO DEV SERVER (this window)
:: ═══════════════════════════════════════════════════════════
echo.
echo  =====================================================
echo   Starting Django dev server ...
echo   API:       http://127.0.0.1:8000/
echo   Swagger:   http://127.0.0.1:8000/api/schema/swagger-ui/
echo   Press Ctrl+C to stop.
echo  =====================================================
echo.

"%VENV_PYTHON%" manage.py runserver

endlocal
