# TradeLABtr — Windows Task Scheduler installer (run in Admin PowerShell on VPS)
# Usage:
#   cd C:\Users\vakman\stock-screener
#   .\install-windows-task.ps1
# Or with password:
#   .\install-windows-task.ps1 -WindowsPassword "YourWindowsPassword"

param(
    [string]$TaskName = "TradeLABtr",
    [string]$WindowsUser = $env:USERNAME,
    [string]$WindowsPassword = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Bat = Join-Path $Root "start-tradelab.bat"
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Bat)) {
    throw "Missing start-tradelab.bat at $Bat"
}
if (-not (Test-Path $Python)) {
    throw "Missing venv python at $Python — run: python -m venv .venv ; .\.venv\Scripts\pip install -r requirements.txt"
}

# Free port 8000 if something already listens
$listeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($listeners) {
    $pids = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
    Write-Warning "Port 8000 in use by PID(s): $($pids -join ', '). Stop those processes first (Ctrl+C on run.py), then re-run this script."
    foreach ($procId in $pids) {
        try {
            $p = Get-Process -Id $procId -ErrorAction Stop
            Write-Host "  PID $procId = $($p.ProcessName)"
        } catch {}
    }
    exit 1
}

# Remove old NSSM service if present
$svc = Get-Service -Name $TaskName -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "Removing old Windows service $TaskName ..."
    Stop-Service $TaskName -Force -ErrorAction SilentlyContinue
    sc.exe delete $TaskName | Out-Null
    Start-Sleep -Seconds 2
}

# Remove existing scheduled task
schtasks /Delete /TN $TaskName /F 2>$null | Out-Null

$tr = "`"$Bat`""
if ($WindowsPassword) {
    schtasks /Create /TN $TaskName /TR $tr /SC ONSTART /RU $WindowsUser /RP $WindowsPassword /RL HIGHEST /F
} else {
    # Runs as current user at logon (no password prompt in this script)
    schtasks /Create /TN $TaskName /TR $tr /SC ONLOGON /RL HIGHEST /F
}

if ($LASTEXITCODE -ne 0) {
    throw "schtasks /Create failed (exit $LASTEXITCODE)"
}

schtasks /Run /TN $TaskName
Start-Sleep -Seconds 3

$ok = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($ok) {
    Write-Host "OK — TradeLABtr listening on port 8000"
    Write-Host "Open http://127.0.0.1:8000  or  http://10.255.7.55:8000"
} else {
    Write-Warning "Task started but port 8000 not listening yet. Check Task Scheduler history or run start-tradelab.bat manually."
}

Write-Host ""
Write-Host "Useful commands:"
Write-Host "  schtasks /Run /TN $TaskName"
Write-Host "  schtasks /End /TN $TaskName"
Write-Host "  schtasks /Query /TN $TaskName /V /FO LIST"
