# Elimina exclusivamente la tarea creada por install_task.ps1.

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$TaskName = 'EVG_JSON_KeepAlive_8000'

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Host "La tarea $TaskName no existe; no hay cambios que realizar."
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
Write-Host "Tarea $TaskName eliminada."
