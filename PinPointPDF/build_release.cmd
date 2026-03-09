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
if exist release rmdir /s /q release

"%PYTHON_EXE%" -m PyInstaller --noconfirm PdfPinpoint.spec
if errorlevel 1 goto :fail

"%PYTHON_EXE%" -m PyInstaller --noconfirm PdfPinpointPortable.spec
if errorlevel 1 goto :fail

mkdir release
mkdir release\OneFile
mkdir release\Portable
copy /y dist\PdfPinpoint.exe release\OneFile\PdfPinpoint.exe >nul
xcopy /e /i /y dist\PdfPinpointPortable release\Portable\PdfPinpointPortable >nul
if errorlevel 1 goto :fail

powershell -NoProfile -Command "Compress-Archive -Path '.\release\OneFile\PdfPinpoint.exe' -DestinationPath '.\release\PdfPinpoint_OneFile.zip' -Force"
if errorlevel 1 goto :fail
powershell -NoProfile -Command "Compress-Archive -Path '.\release\Portable\PdfPinpointPortable' -DestinationPath '.\release\PdfPinpoint_Portable.zip' -Force"
if errorlevel 1 goto :fail

echo [OK] Release created under %CD%\release
popd
exit /b 0

:fail
set "ERR=%ERRORLEVEL%"
popd
exit /b %ERR%