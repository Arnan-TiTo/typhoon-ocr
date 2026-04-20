@echo off
setlocal
echo ========================================================
echo Setup Typhoon OCR System (Native Windows)
echo ========================================================

if defined PIP_NO_INDEX (
    echo.
    echo ERROR: PIP_NO_INDEX is set, so pip cannot download required packages like gradio.
    echo Run this in the same terminal first:
    echo   set PIP_NO_INDEX=
    echo.
    exit /b 1
)

if defined HTTP_PROXY goto :proxy_error
if defined HTTPS_PROXY goto :proxy_error
if defined ALL_PROXY goto :proxy_error
if defined GIT_HTTP_PROXY goto :proxy_error
if defined GIT_HTTPS_PROXY goto :proxy_error

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
exit /b 0

:proxy_error
echo.
echo ERROR: Proxy environment variables are set and may block pip downloads.
echo Clear them in the same terminal before running setup:
echo   set HTTP_PROXY=
echo   set HTTPS_PROXY=
echo   set ALL_PROXY=
echo   set GIT_HTTP_PROXY=
echo   set GIT_HTTPS_PROXY=
echo.
exit /b 1
