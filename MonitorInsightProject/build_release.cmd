@echo off
setlocal
pushd "%~dp0"

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist release rmdir /s /q release

"..\PythonEnv\.venv311\Scripts\python.exe" -m PyInstaller --noconfirm MonitorInsight.spec
"..\PythonEnv\.venv311\Scripts\python.exe" -m PyInstaller --noconfirm MonitorInsightPortable.spec

mkdir release
mkdir release\OneFile
mkdir release\Portable
copy /y dist\MonitorInsight.exe release\OneFile\MonitorInsight.exe >nul
xcopy /e /i /y dist\MonitorInsightPortable release\Portable\MonitorInsightPortable >nul

powershell -NoProfile -Command "Compress-Archive -Path '.\release\OneFile\MonitorInsight.exe' -DestinationPath '.\release\MonitorInsight_OneFile.zip' -Force"
powershell -NoProfile -Command "Compress-Archive -Path '.\release\Portable\MonitorInsightPortable' -DestinationPath '.\release\MonitorInsight_Portable.zip' -Force"

popd
