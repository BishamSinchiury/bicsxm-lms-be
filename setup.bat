@echo off
setlocal EnableDelayedExpansion

:: ============================================================
::  Bicsxm LMS Backend — Windows Dev Setup (no Docker)
::  Run once (as Administrator) to install all dependencies.
::  Installs: Python 3.12, PostgreSQL 16, Redis, MongoDB 7
:: ============================================================

title Bicsxm LMS — Setup

echo.
echo  =====================================================
echo   Bicsxm LMS Backend ^| Windows Setup
echo  =====================================================
echo.

:: ── Require admin ────────────────────────────────────────────
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [ERROR] Please right-click setup.bat and choose "Run as administrator".
    pause & exit /b 1
)

:: ── Check winget ─────────────────────────────────────────────
winget --version >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [ERROR] winget is not installed.
    echo         Install it from the Microsoft Store: App Installer
    echo         https://www.microsoft.com/store/productId/9NBLGGH4NNS1
    pause & exit /b 1
)

:: ═══════════════════════════════════════════════════════════
:: STEP 1 — Python 3.12
:: ═══════════════════════════════════════════════════════════
echo [1/6] Python 3.12 ...
set "PYTHON_OK=0"
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do (
    echo %%v | findstr /R "^3\.12\." >nul && set "PYTHON_OK=1"
)
if "%PYTHON_OK%"=="0" (
    echo       Not found. Installing via winget ...
    winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
    if !errorLevel! NEQ 0 (
        echo [ERROR] Python installation failed. Get it from https://www.python.org/downloads/
        pause & exit /b 1
    )
    :: Add to PATH for this session
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
    echo       Python 3.12 installed.
) else (
    echo       OK — already installed.
)

:: ═══════════════════════════════════════════════════════════
:: STEP 2 — PostgreSQL 16
:: ═══════════════════════════════════════════════════════════
echo.
echo [2/6] PostgreSQL 16 ...
set "PG_BIN=C:\Program Files\PostgreSQL\16\bin"
set "PSQL_EXE=%PG_BIN%\psql.exe"
if not exist "%PSQL_EXE%" (
    echo       Not found. Installing via winget ...
    winget install --id PostgreSQL.PostgreSQL.16 -e --silent --accept-package-agreements --accept-source-agreements
    if !errorLevel! NEQ 0 (
        echo [ERROR] PostgreSQL installation failed.
        echo         Get it from https://www.postgresql.org/download/windows/
        pause & exit /b 1
    )
    echo       PostgreSQL 16 installed.
) else (
    echo       OK — already installed.
)
:: Make sure pg\bin is on PATH for this session
set "PATH=%PG_BIN%;%PATH%"

:: Start the service
sc query postgresql-x64-16 >nul 2>&1
if %errorLevel% EQU 0 (
    sc start postgresql-x64-16 >nul 2>&1
    echo       Service started (or already running).
) else (
    echo [WARN] Could not find postgresql-x64-16 service. Start PostgreSQL manually if needed.
)

:: ═══════════════════════════════════════════════════════════
:: STEP 3 — Redis (Memurai or tporadowski build)
:: ═══════════════════════════════════════════════════════════
echo.
echo [3/6] Redis ...
set "REDIS_OK=0"
where redis-server >nul 2>&1  && set "REDIS_OK=1"
where memurai-server >nul 2>&1 && set "REDIS_OK=1"
if exist "C:\Program Files\Redis\redis-server.exe" set "REDIS_OK=1"
if exist "C:\Program Files\Memurai\memurai-server.exe" set "REDIS_OK=1"

if "%REDIS_OK%"=="0" (
    echo       Not found. Installing Memurai (Redis-compatible) ...
    winget install --id Memurai.Memurai -e --silent --accept-package-agreements --accept-source-agreements
    if !errorLevel! NEQ 0 (
        echo       Memurai failed. Trying tporadowski Redis build ...
        winget install --id tporadowski.redis -e --silent --accept-package-agreements --accept-source-agreements
        if !errorLevel! NEQ 0 (
            echo [ERROR] Redis installation failed.
            echo         Download from https://github.com/tporadowski/redis/releases
            pause & exit /b 1
        )
    )
    echo       Redis installed.
) else (
    echo       OK — already installed.
)

:: ═══════════════════════════════════════════════════════════
:: STEP 4 — MongoDB 7 + mongosh
:: ═══════════════════════════════════════════════════════════
echo.
echo [4/6] MongoDB 7 ...
set "MONGO_BIN=C:\Program Files\MongoDB\Server\7.0\bin"
set "MONGOD_EXE=%MONGO_BIN%\mongod.exe"
if not exist "%MONGOD_EXE%" (
    echo       Not found. Installing MongoDB via winget ...
    winget install --id MongoDB.Server -e --silent --accept-package-agreements --accept-source-agreements
    if !errorLevel! NEQ 0 (
        echo [ERROR] MongoDB installation failed.
        echo         Download from https://www.mongodb.com/try/download/community
        pause & exit /b 1
    )
    echo       MongoDB installed.
) else (
    echo       OK — already installed.
)
set "PATH=%MONGO_BIN%;%PATH%"

:: Install mongosh if missing
where mongosh >nul 2>&1
if %errorLevel% NEQ 0 (
    echo       Installing mongosh ...
    winget install --id MongoDB.Shell -e --silent --accept-package-agreements --accept-source-agreements
    set "PATH=C:\Program Files\mongosh;%PATH%"
)

:: Ensure data directory exists
if not exist "C:\data\db" mkdir "C:\data\db"

:: ═══════════════════════════════════════════════════════════
:: STEP 5 — Python virtual env + pip packages
:: ═══════════════════════════════════════════════════════════
echo.
echo [5/6] Python virtual environment ^& packages ...
if not exist ".venv" (
    python -m venv .venv
    echo       Created .venv\
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if %errorLevel% NEQ 0 (
    echo [ERROR] pip install failed. See output above.
    pause & exit /b 1
)
echo       All packages installed.

:: ═══════════════════════════════════════════════════════════
:: STEP 6 — .env + DB + migrations
:: ═══════════════════════════════════════════════════════════
echo.
echo [6/6] Environment ^& database setup ...

:: Generate .env if missing
if not exist ".env" (
    copy ".env.example" ".env" >nul
    :: Generate a real SECRET_KEY using Python
    for /f "delims=" %%s in ('python -c "import secrets; print(secrets.token_urlsafe(50))"') do set "SECRET_KEY=%%s"
    :: Replace the placeholder in .env (PowerShell makes this easy)
    powershell -Command "(Get-Content .env) -replace 'change-me-to-a-random-string', '!SECRET_KEY!' | Set-Content .env"
    echo       .env created with a generated DJANGO_SECRET_KEY.
    echo.
    echo  *** ACTION REQUIRED ***
    echo  Open .env and set these values before running the server:
    echo    JWT_SIGNING_KEY_ADMIN, JWT_SIGNING_KEY_TEACHER, JWT_SIGNING_KEY_STUDENT
    echo    OTP_HMAC_SECRET
    echo    POSTGRES_PASSWORD  (if you changed it from the default "postgres")
    echo  ***********************
    echo.
) else (
    echo       .env already exists — skipping.
)

:: Create PostgreSQL database
set "PGPASSWORD=postgres"
"%PSQL_EXE%" -U postgres -h 127.0.0.1 -tc "SELECT 1 FROM pg_database WHERE datname='lms';" 2>nul | findstr /C:"1" >nul
if %errorLevel% NEQ 0 (
    "%PSQL_EXE%" -U postgres -h 127.0.0.1 -c "CREATE DATABASE lms;" >nul 2>&1
    echo       Database 'lms' created.
) else (
    echo       Database 'lms' already exists.
)

:: Run migrations
set DJANGO_SETTINGS_MODULE=config.settings.dev
python manage.py migrate --noinput
if %errorLevel% NEQ 0 (
    echo [WARN] Migrations failed. Fix .env settings then run:
    echo        .venv\Scripts\activate ^&^& python manage.py migrate
)

echo.
echo  =====================================================
echo   Setup complete!
echo   Now run:  dev.bat   to start all services.
echo  =====================================================
echo.
pause
endlocal
