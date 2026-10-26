param([string]$Python = 'python', [string]$PackageManager = 'npm')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
function Check-Exit([string]$Task) { if ($LASTEXITCODE -ne 0) { throw "$Task failed (exit $LASTEXITCODE)." } }
if (!(Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    & $Python -m venv .venv
    Check-Exit 'Virtual environment creation'
}
& '.venv\Scripts\python.exe' -m pip install -r backend\requirements.txt
Check-Exit 'Python dependency installation'
Push-Location frontend
try {
    & $PackageManager install
    Check-Exit 'Frontend dependency installation'
    & $PackageManager run build
    Check-Exit 'Frontend build'
} finally { Pop-Location }
& '.venv\Scripts\python.exe' -m tests.samples
Check-Exit 'Sample generation'
Write-Host 'Ready. Run .\start.ps1 and visit http://127.0.0.1:8000'
