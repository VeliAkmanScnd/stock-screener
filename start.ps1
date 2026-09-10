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

Write-Host "Starting TradeLABtr on http://127.0.0.1:8000 (scheduled scans run while this window stays open)..."
& $python run.py
