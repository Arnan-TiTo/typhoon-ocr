@echo off
echo ========================================================
echo Setup Typhoon OCR System (Native Windows)
echo ========================================================

echo 1. Creating Virtual Environment (venv)...
python -m venv venv

echo.
echo 2. Activating Virtual Environment and Installing Dependencies...
call venv\Scripts\activate

echo [Installing UI Requirements]
pip install -r requirements.txt

echo [Installing API Requirements]
pip install -r requirements-api.txt

echo [Installing Local Typhoon OCR Package]
pip install -e ./packages/typhoon_ocr

echo.
echo ========================================================
echo Setup Completed!
echo.
echo NOTE for Windows Users: 
echo You must install "poppler" manually for PDF processing.
echo 1. Download poppler for Windows (e.g., from https://github.com/oschwartz10612/poppler-windows/releases)
echo 2. Extract it to a folder (e.g., C:\poppler)
echo 3. Add C:\poppler\bin to your System Environment Variables (PATH)
echo ========================================================
pause
