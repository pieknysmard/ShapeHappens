$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (!(Test-Path -LiteralPath '.venv\Scripts\python.exe') -or !(Test-Path -LiteralPath 'frontend\dist\index.html')) {
    throw 'Run .\setup.ps1 first. Python 3.11+ and Node.js 20.19+ are required.'
}
Write-Host 'ShapeHappens Generator: http://127.0.0.1:8000 (Ctrl+C to stop)'
& '.venv\Scripts\python.exe' -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
