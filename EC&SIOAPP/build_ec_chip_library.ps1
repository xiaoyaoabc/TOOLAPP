$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path (Split-Path $Root -Parent) "PythonEnv\.venv311\Scripts\python.exe"
$Entry = Join-Path $Root "ec_chip_app.py"
$Icon = Join-Path $Root "assets\app_icon.ico"

$Arguments = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", "ECChipLibrary",
    "--icon", $Icon,
    "--paths", $Root,
    "--hidden-import", "chip_library_app",
    "--hidden-import", "chip_library_builder",
    "--distpath", (Join-Path $Root "dist"),
    "--workpath", (Join-Path $Root "build"),
    "--specpath", $Root,
    "--add-data", "data;data",
    "--add-data", "PDF;PDF",
    $Entry
)

& $Python @Arguments
exit $LASTEXITCODE
