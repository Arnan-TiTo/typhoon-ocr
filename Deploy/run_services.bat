@echo off
echo ========================================================
echo Starting Typhoon OCR System (Native Windows)
echo ========================================================

IF NOT EXIST "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)

:: Start the FastAPI Server in a new window
echo Starting API Server on Port 8000...
start "Typhoon OCR - API Server" cmd /k "call venv\Scripts\activate && uvicorn api_server:app --host 0.0.0.0 --port 8000"

:: Wait a few seconds for the API to initialize
timeout /t 3 >nul

:: Start the Gradio Web UI in a new window
echo Starting Gradio Web UI on Port 7860...
start "Typhoon OCR - Web UI" cmd /k "call venv\Scripts\activate && python app.py"

echo ========================================================
echo Processes started in separate windows!
echo - FastAPI Server: http://localhost:8000
echo - Gradio Web UI:  http://localhost:7860
echo ========================================================
