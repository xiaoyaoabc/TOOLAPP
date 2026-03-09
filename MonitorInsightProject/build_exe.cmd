@echo off
setlocal
pushd "%~dp0"
"..\PythonEnv\.venv311\Scripts\python.exe" -m PyInstaller --noconfirm MonitorInsight.spec
popd
