# EVG_JSON keepalive para el puerto TCP 8000.
# Comando detectado en README.md y run.bat:
# Ejecuta el modulo de la carpeta del proyecto indicada por $ProjectRoot.

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$LogDirectory = Join-Path $ProjectRoot 'logs'
$KeepAliveLog = Join-Path $LogDirectory 'keepalive.log'
$StdOutLog = Join-Path $LogDirectory 'app.stdout.log'
$StdErrLog = Join-Path $LogDirectory 'app.stderr.log'
$Port = 8000
$MutexName = 'Global\EVG_JSON_KeepAlive_8000'

function Write-KeepAliveLog {
    param([Parameter(Mandatory)][string]$Message)
    if (-not (Test-Path -LiteralPath $LogDirectory)) {
        New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    }
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'), $PID, $Message
    Add-Content -LiteralPath $KeepAliveLog -Value $line -Encoding UTF8
}

function Test-PortListening {
    try {
        return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop | Select-Object -First 1)
    }
    catch {
        # Alternativa compatible si Get-NetTCPConnection no esta disponible.
        try {
            $client = [System.Net.Sockets.TcpClient]::new()
            $async = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
            $connected = $async.AsyncWaitHandle.WaitOne(750, $false) -and $client.Connected
            if ($connected) { $client.EndConnect($async) }
            $client.Dispose()
            return $connected
        }
        catch {
            return $false
        }
    }
}

function Get-ExistingEvgProcess {
    # Detecta exactamente este proyecto y modulo, sin depender del nombre python.exe.
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match '(?i)uvicorn\s+app\.main:app' -and
        $_.ExecutablePath -and
        $_.ExecutablePath.Equals($PythonExe, [System.StringComparison]::OrdinalIgnoreCase)
    } | Select-Object -First 1
}

$createdNew = $false
$mutex = [System.Threading.Mutex]::new($false, $MutexName, [ref]$createdNew)
$hasMutex = $false

try {
    try {
        $hasMutex = $mutex.WaitOne(0, $false)
    }
    catch [System.Threading.AbandonedMutexException] {
        $hasMutex = $true
    }

    if (-not $hasMutex) {
        Write-KeepAliveLog 'Otra instancia de keepalive esta en ejecucion; no se duplica el trabajo.'
        exit 0
    }

    if (Test-PortListening) {
        Write-KeepAliveLog "El puerto $Port ya esta escuchando; no se requiere accion."
        exit 0
    }

    $existingProcess = Get-ExistingEvgProcess
    if ($existingProcess) {
        Write-KeepAliveLog "Ya existe el proceso EVG_JSON PID $($existingProcess.ProcessId); se espera que abra el puerto sin crear un duplicado."
        foreach ($attempt in 1..10) {
            Start-Sleep -Seconds 1
            if (Test-PortListening) {
                Write-KeepAliveLog "El proceso existente activo correctamente el puerto $Port."
                exit 0
            }
        }
        Write-KeepAliveLog "ERROR: el proceso EVG_JSON PID $($existingProcess.ProcessId) existe, pero el puerto $Port no esta escuchando."
        exit 1
    }

    if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
        throw "No existe el directorio del proyecto: $ProjectRoot"
    }
    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
        throw "No existe el Python del entorno virtual: $PythonExe"
    }

    Write-KeepAliveLog "Puerto $Port inactivo; iniciando EVG_JSON con el comando documentado."
    $arguments = @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$Port")
    $process = Start-Process -FilePath $PythonExe `
        -ArgumentList $arguments `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $StdOutLog `
        -RedirectStandardError $StdErrLog `
        -PassThru

    foreach ($attempt in 1..30) {
        Start-Sleep -Seconds 1
        if (Test-PortListening) {
            Write-KeepAliveLog "EVG_JSON iniciado correctamente; PID $($process.Id), puerto $Port activo."
            exit 0
        }
        if ($process.HasExited) {
            throw "EVG_JSON termino antes de abrir el puerto (codigo $($process.ExitCode)). Consulte $StdErrLog"
        }
    }

    throw "EVG_JSON no abrio el puerto $Port dentro de 30 segundos. Consulte $StdErrLog"
}
catch {
    try { Write-KeepAliveLog "ERROR: $($_.Exception.Message)" } catch {}
    exit 1
}
finally {
    if ($hasMutex) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
