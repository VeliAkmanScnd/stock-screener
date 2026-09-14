# TradeLABtr - auto-start installer for Windows VPS
# Run in PowerShell:
#   cd C:\Users\vakman\stock-screener
#   .\install-windows-task.ps1
#
# Prefer Admin PowerShell for Task Scheduler.
# If Access Denied, script falls back to Startup folder (no admin needed).

param(
    [string]$TaskName = "TradeLABtr",
    [string]$WindowsUser = $env:USERNAME,
    [string]$WindowsPassword = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Bat = Join-Path $Root "start-tradelab.bat"
$Python = Join-Path $Root ".venv\Scripts\python.exe"

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Install-StartupShortcut {
    $startup = [Environment]::GetFolderPath("Startup")
    $lnkPath = Join-Path $startup "TradeLABtr.lnk"
    $w = New-Object -ComObject WScript.Shell
    $lnk = $w.CreateShortcut($lnkPath)
    $lnk.TargetPath = $Bat
    $lnk.WorkingDirectory = $Root
    $lnk.WindowStyle = 7
    $lnk.Description = "TradeLABtr Stock Screener"
    $lnk.Save()
    Write-Host "Installed Startup shortcut: $lnkPath"
    return $lnkPath
}

if (-not (Test-Path $Bat)) {
    throw "Missing start-tradelab.bat at $Bat"
}
if (-not (Test-Path $Python)) {
    throw "Missing venv python at $Python. Run: python -m venv .venv then pip install -r requirements.txt"
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

$isAdmin = Test-IsAdmin
Write-Host "Running as admin: $isAdmin"

$createdTask = $false
if ($isAdmin) {
    # Remove old Windows service if present
    $svc = Get-Service -Name $TaskName -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Host "Removing old Windows service $TaskName ..."
        Stop-Service $TaskName -Force -ErrorAction SilentlyContinue
        cmd /c "sc delete $TaskName >nul 2>&1"
        Start-Sleep -Seconds 2
    }

    cmd /c "schtasks /Delete /TN `"$TaskName`" /F >nul 2>&1"

    $tr = "`"$Bat`""
    if ($WindowsPassword) {
        & schtasks /Create /TN $TaskName /TR $tr /SC ONSTART /RU $WindowsUser /RP $WindowsPassword /RL HIGHEST /F
    } else {
        & schtasks /Create /TN $TaskName /TR $tr /SC ONLOGON /RU $WindowsUser /RL LIMITED /F
    }

    if ($LASTEXITCODE -eq 0) {
        $createdTask = $true
        Write-Host "Scheduled task created: $TaskName"
        & schtasks /Run /TN $TaskName
    } else {
        Write-Warning "schtasks Create failed (exit $LASTEXITCODE). Falling back to Startup folder."
    }
} else {
    Write-Warning "Not admin. Skipping schtasks; using Startup folder instead."
    Write-Warning "Tip: Right-click PowerShell -> Run as administrator, then re-run this script for a scheduled task."
}

if (-not $createdTask) {
    Install-StartupShortcut | Out-Null
    Write-Host "Starting now via bat..."
    Start-Process -FilePath $Bat -WorkingDirectory $Root -WindowStyle Minimized
}

Start-Sleep -Seconds 4

$ok = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($ok) {
    Write-Host "OK - TradeLABtr listening on port 8000"
    Write-Host "Open http://127.0.0.1:8000  or  http://10.255.7.55:8000"
} else {
    Write-Warning "Port 8000 not listening yet. Try: start-tradelab.bat manually"
}

Write-Host ""
Write-Host "Useful commands:"
Write-Host "  schtasks /Run /TN $TaskName"
Write-Host "  schtasks /End /TN $TaskName"
Write-Host "  schtasks /Query /TN $TaskName /V /FO LIST"
Write-Host "  Startup folder: shell:startup"
