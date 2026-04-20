@echo off
echo ========================================================
echo Creating Deployment Package (Deploy Folder)
echo ========================================================

:: Create Deploy folder
if not exist "Deploy" mkdir "Deploy"

:: Copy Configuration and Environment files
echo Copying Configuration Files...
copy ".env" "Deploy\"
copy "requirements.txt" "Deploy\"
copy "requirements-api.txt" "Deploy\"

:: Copy Python Source Codes
echo Copying Source Codes...
copy "app.py" "Deploy\"
copy "api_server.py" "Deploy\"
copy "ocr_client.py" "Deploy\"
copy "thai_ocr_corrector.py" "Deploy\"

:: Copy Scripts
echo Copying Setup/Run Scripts...
copy "setup.bat" "Deploy\"
copy "run_services.bat" "Deploy\"

:: Copy Directories (using xcopy for folders)
echo Copying Directories...
xcopy "packages" "Deploy\packages" /E /I /Y
xcopy "thai_dict" "Deploy\thai_dict" /E /I /Y
xcopy "examples" "Deploy\examples" /E /I /Y

echo.
echo ========================================================
echo Deployment Package "Deploy" has been created successfully!
echo You can now ZIP the "Deploy" folder and move it to your Production Server.
echo ========================================================
