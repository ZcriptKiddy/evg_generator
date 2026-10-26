$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$StartScript = Join-Path $ProjectRoot "scripts\windows\Start-EVJSON-Current8000.ps1"
try {
  $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/login" -UseBasicParsing -TimeoutSec 5
  if ($response.StatusCode -lt 500) { exit 0 }
} catch {}
Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $StartScript) -WindowStyle Hidden
