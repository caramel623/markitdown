# One-time setup: creates .\.venv, installs local markitdown + converters + PyQt6.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (Test-Path .\.venv\Scripts\python.exe) {
    $py = ".\.venv\Scripts\python.exe"
} else {
    python -m venv .venv
    $py = ".\.venv\Scripts\python.exe"
    & $py -m pip install -U pip
}

& $py -m pip install -e "packages\markitdown[docx,xlsx,xls,pptx,pdf,outlook]" PyQt6
Write-Output "`nSetup complete. Run the GUI with: .\run_gui.bat"
