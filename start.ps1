# TradeLABtr — start server (no manual venv activate needed)
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Virtual env not found. Run: python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
}

$portUsers = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($portUsers) {
    $pids = ($portUsers | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
    Write-Warning "Port 8000 is already in use (PID: $pids). Stop the other server first or scheduled scans will not run."
}

Write-Host "Starting TradeLABtr. VPS/LAN icin .env icinde HOST=0.0.0.0 olmali."
if (-not $env:HOST) { $env:HOST = "0.0.0.0" }
Write-Host "Bind http://$($env:HOST):$(if ($env:PORT) {$env:PORT} else {'8000'})"
& $python -u run.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "Sunucu kapandi (kod $LASTEXITCODE). storage\server.log dosyasina bakin."
    exit $LASTEXITCODE
}
