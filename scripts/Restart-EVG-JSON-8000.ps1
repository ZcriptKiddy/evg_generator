[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path  '..')).Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$logDirectory = Join-Path $projectRoot 'logs'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process -FilePath 'powershell.exe' `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $PSCommandPath)) `
        -Verb RunAs
    exit
}

$listeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
foreach ($listener in $listeners) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if (-not $process.CommandLine -or $process.CommandLine -notmatch '(?i)uvicorn\s+app\.main:app') {
        throw "El PID $($listener.OwningProcess) usa el puerto 8000, pero no corresponde a EVG_JSON. No se detuvo."
    }
    Stop-Process -Id $listener.OwningProcess -Force
}

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
Start-Process -FilePath $pythonExe `
    -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000') `
    -WorkingDirectory $projectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDirectory 'app.stdout.log') `
    -RedirectStandardError (Join-Path $logDirectory 'app.stderr.log')

foreach ($attempt in 1..30) {
    Start-Sleep -Milliseconds 500
    try {
        # La respuesta 401 confirma que esta ruta del backend nuevo ya está activa.
        Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/capabilities' -UseBasicParsing -ErrorAction Stop | Out-Null
    }
    catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 401) {
            Write-Host 'EVG_JSON reiniciado correctamente. El borrado de historial ya esta activo.' -ForegroundColor Green
            exit 0
        }
    }
}

throw 'EVG_JSON no confirmó la función de borrado del historial. Revise logs\app.stderr.log.'
