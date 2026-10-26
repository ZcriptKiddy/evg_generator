# Instala de forma idempotente la tarea de mantenimiento de EVG_JSON.
# Requiere una consola elevada porque registra una tarea ejecutada como SYSTEM.

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$TaskName = 'EVG_JSON_KeepAlive_8000'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$KeepAliveScript = Join-Path $PSScriptRoot 'keepalive.ps1'
$LogDirectory = Join-Path $ProjectRoot 'logs'
$KeepAliveLog = Join-Path $LogDirectory 'keepalive.log'
$InstallLog = Join-Path $LogDirectory 'install_task.log'
$Port = 8000

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-PortListening {
    try {
        return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop | Select-Object -First 1)
    }
    catch {
        try {
            $client = [System.Net.Sockets.TcpClient]::new()
            $async = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
            $connected = $async.AsyncWaitHandle.WaitOne(750, $false) -and $client.Connected
            if ($connected) { $client.EndConnect($async) }
            $client.Dispose()
            return $connected
        }
        catch { return $false }
    }
}

# Solicita UAC solo cuando hace falta. La consola elevada se mantiene oculta.
if (-not (Test-Administrator)) {
    try {
        $elevatedArguments = @(
            '-NoProfile',
            '-ExecutionPolicy', 'Bypass',
            '-File', ('"{0}"' -f $PSCommandPath)
        )
        $elevated = Start-Process -FilePath 'powershell.exe' `
            -ArgumentList $elevatedArguments `
            -Verb RunAs `
            -WindowStyle Hidden `
            -Wait `
            -PassThru
        exit $elevated.ExitCode
    }
    catch {
        throw "No se obtuvo elevacion administrativa: $($_.Exception.Message)"
    }
}

if (-not (Test-Path -LiteralPath $KeepAliveScript -PathType Leaf)) {
    throw "No existe el script keepalive: $KeepAliveScript"
}
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
if (-not (Test-Path -LiteralPath $KeepAliveLog)) {
    New-Item -ItemType File -Path $KeepAliveLog -Force | Out-Null
}
Start-Transcript -LiteralPath $InstallLog -Append -Force | Out-Null
trap {
    try {
        Add-Content -LiteralPath $InstallLog -Value ("ERROR: {0}" -f $_.Exception.Message) -Encoding UTF8
    } catch {}
    try { Stop-Transcript | Out-Null } catch {}
    exit 1
}

# Retira tareas heredadas relacionadas. Se revisan nombre, ruta y acciones.
$legacyPattern = '(?i)EVG_JSON'
Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
    $actionText = ($_.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments) $($_.WorkingDirectory)" }) -join ' '
    $haystack = "$($_.TaskPath)$($_.TaskName) $actionText"
    $_.TaskName -ne $TaskName -and $haystack -match $legacyPattern
} | ForEach-Object {
    Write-Host "Eliminando tarea heredada: $($_.TaskPath)$($_.TaskName)"
    Unregister-ScheduledTask -TaskName $_.TaskName -TaskPath $_.TaskPath -Confirm:$false -ErrorAction Stop
}

# La repeticion sin elemento Duration es indefinida segun el esquema de Task Scheduler.
$startBoundary = (Get-Date).AddMinutes(1).ToString('s')
$escapedScript = [Security.SecurityElement]::Escape($KeepAliveScript)
$escapedProject = [Security.SecurityElement]::Escape($ProjectRoot)
$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Mantiene EVG_JSON escuchando en 127.0.0.1:8000.</Description></RegistrationInfo>
  <Triggers>
    <BootTrigger><Enabled>true</Enabled></BootTrigger>
    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>
    <CalendarTrigger>
      <Repetition><Interval>PT37M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>$startBoundary</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoProfile -ExecutionPolicy Bypass -File &quot;$escapedScript&quot;</Arguments>
      <WorkingDirectory>$escapedProject</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

# Register-ScheduledTask -Force crea o actualiza la definicion con el mismo nombre.
Register-ScheduledTask -TaskName $TaskName -Xml $taskXml -Force | Out-Null
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
if ($task.State -eq 'Disabled') { throw "La tarea $TaskName quedo deshabilitada." }

# Validacion real: ejecutar ahora y esperar a que keepalive confirme el puerto.
Start-ScheduledTask -TaskName $TaskName
$deadline = (Get-Date).AddSeconds(45)
do {
    Start-Sleep -Seconds 1
    $validationTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    if ((Test-PortListening) -and $validationTask.State -ne 'Running') { break }
} while ((Get-Date) -lt $deadline)

if (-not (Test-PortListening)) {
    $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
    throw "La tarea se registro, pero el puerto $Port no quedo activo. LastTaskResult=$($info.LastTaskResult). Consulte $KeepAliveLog"
}

# Espera adicional para detectar eliminaciones por politicas locales o software de seguridad.
Start-Sleep -Seconds 5
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName
if ($task.State -eq 'Running' -or $info.LastTaskResult -ne 0) {
    throw "La tarea no termino correctamente. Estado=$($task.State), LastTaskResult=$($info.LastTaskResult). Consulte $KeepAliveLog"
}

# Audita la definicion exportada desde el mismo contexto elevado que puede leer la ACL de SYSTEM.
[xml]$registeredXml = Export-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$namespace = [System.Xml.XmlNamespaceManager]::new($registeredXml.NameTable)
$namespace.AddNamespace('t', 'http://schemas.microsoft.com/windows/2004/02/mit/task')
$registeredAction = $registeredXml.SelectSingleNode('//t:Actions/t:Exec', $namespace)
$bootCount = $registeredXml.SelectNodes('//t:BootTrigger', $namespace).Count
$logonCount = $registeredXml.SelectNodes('//t:LogonTrigger', $namespace).Count
$registeredInterval = $registeredXml.SelectSingleNode('//t:CalendarTrigger/t:Repetition/t:Interval', $namespace).InnerText
$registeredDuration = $registeredXml.SelectSingleNode('//t:CalendarTrigger/t:Repetition/t:Duration', $namespace)
$expectedArguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $KeepAliveScript

if ($registeredAction.Command -ne 'powershell.exe' -or
    $registeredAction.Arguments -ne $expectedArguments -or
    $bootCount -ne 1 -or
    $logonCount -ne 1 -or
    $registeredInterval -ne 'PT37M' -or
    $null -ne $registeredDuration) {
    throw 'La tarea se registro, pero su definicion exportada no coincide con la configuracion requerida.'
}

Write-Host "Tarea $TaskName instalada y validada. Puerto $Port activo. Ultimo resultado: $($info.LastTaskResult)"
Write-Host "Auditoria: SYSTEM/Highest, oculta, Boot=$bootCount, Logon=$logonCount, repeticion=$registeredInterval sin duracion."
Write-Host "Accion: $($registeredAction.Command) $($registeredAction.Arguments)"
Stop-Transcript | Out-Null
