@echo off
REM Anderson Report Automation - Package Script
REM Creates a ZIP of this folder ready to hand off to IT.
REM
REM Usage:  Double-click package.bat
REM Output: anderson-report-automation.zip  (saved one folder up, inside dist\)

setlocal

REM Go up one level to the dist\ folder
cd /d "%~dp0.."

echo.
echo Creating ZIP package...
powershell -Command "Compress-Archive -Path '.\anderson-report-automation\*' -DestinationPath '.\anderson-report-automation.zip' -Force"

echo.
echo Done!
echo ZIP saved at:  dist\anderson-report-automation.zip
echo.
echo Give that ZIP file to IT for deployment.
echo.

endlocal
pause
