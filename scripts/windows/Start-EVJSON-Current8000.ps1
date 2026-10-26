$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location -LiteralPath $ProjectRoot
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (!(Test-Path $PythonExe)) { $PythonExe = "python" }
& $PythonExe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
