Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt
$env:PYTHONPATH = $PSScriptRoot
.\.venv\Scripts\python make_icon.py
.\.venv\Scripts\python -m PyInstaller --noconfirm --onefile --windowed --name InputSwitch `
    --icon assets\app.ico --exclude-module PySide6.QtNetwork --exclude-module PySide6.QtQml `
    --exclude-module PySide6.QtQuick --exclude-module PySide6.QtPdf --exclude-module PySide6.QtSvg `
    run.py
Write-Host "Pronto: dist\InputSwitch.exe"
