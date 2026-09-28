# TradeLABtr — start server (no manual venv activate needed)
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Virtual env not found. Run: python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
}

$port = if ($env:PORT) { [int]$env:PORT } else { 8000 }
$freePort = Join-Path $PSScriptRoot "scripts\free-listen-port.ps1"
if (Test-Path $freePort) {
    & $freePort -Port $port
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$env:HOST = "0.0.0.0"
Write-Host "Starting TradeLABtr. Tarayici: http://127.0.0.1:${port}/login"
Write-Host "Bind http://$($env:HOST):$port"
& $python -u run.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "Sunucu kapandi (kod $LASTEXITCODE). storage\server.log dosyasina bakin."
    exit $LASTEXITCODE
}
