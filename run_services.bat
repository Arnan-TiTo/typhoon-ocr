@echo off
setlocal
set API_PORT=8000
set UI_PORT=7860
echo ========================================================
echo Starting Typhoon OCR System (Native Windows)
echo ========================================================

IF NOT EXIST "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)

netstat -ano | findstr ":%API_PORT%" | findstr "LISTENING" >nul
if %errorlevel% equ 0 (
    echo [INFO] Port %API_PORT% is already in use. Skipping API start.
    echo [INFO] If this is Typhoon OCR, Swagger should already be at http://localhost:%API_PORT%/docs
) else (
    echo Starting API Server on Port %API_PORT%...
    start "Typhoon OCR - API Server" cmd /k "call venv\Scripts\activate.bat && uvicorn api_server:app --host 0.0.0.0 --port %API_PORT%"
)

:: Wait a few seconds for the API to initialize
timeout /t 3 >nul

netstat -ano | findstr ":%UI_PORT%" | findstr "LISTENING" >nul
if %errorlevel% equ 0 (
    echo [INFO] Port %UI_PORT% is already in use. Skipping Gradio start.
    echo [INFO] Web UI may already be available at http://localhost:%UI_PORT%
) else (
    echo Starting Gradio Web UI on Port %UI_PORT%...
    start "Typhoon OCR - Web UI" cmd /k "call venv\Scripts\activate.bat && python app.py"
)

echo ========================================================
echo Processes started in separate windows!
echo - FastAPI Server: http://localhost:%API_PORT%
echo - Gradio Web UI:  http://localhost:%UI_PORT%
echo ========================================================
