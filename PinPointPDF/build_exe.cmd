@echo off
setlocal
pushd "%~dp0"

set "PYTHON_EXE=..\PythonEnv\.venv311\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Missing build python: %PYTHON_EXE%
    popd
    exit /b 1
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

"%PYTHON_EXE%" -m PyInstaller --noconfirm PdfPinpoint.spec
set "ERR=%ERRORLEVEL%"
popd
exit /b %ERR%