@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"
set "BUILD_SCRIPT=%PROJECT_ROOT%build_packages.py"

if not exist "%PYTHON%" (
    echo Error: virtual-environment Python was not found at "%PYTHON%".
    exit /b 1
)

"%PYTHON%" "%BUILD_SCRIPT%" %*
exit /b %ERRORLEVEL%
