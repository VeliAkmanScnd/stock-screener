# TradeLABtr - auto-start + keep-alive for Windows VPS
# Admin PowerShell:
#   cd C:\Users\vakman\stock-screener
#   .\install-windows-task.ps1
#
# Creates:
#   TradeLABtr      — at logon / boot
#   TradeLABtrWatch — every 5 minutes if /healthz is down

param(
    [string]$TaskName = "TradeLABtr",
    [string]$WatchTaskName = "TradeLABtrWatch",
    [string]$WindowsUser = $env:USERNAME,
    [string]$WindowsPassword = "",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnsurePs1 = Join-Path $Root "scripts\ensure-tradelab-running.ps1"
$Bat = Join-Path $Root "start-tradelab.bat"
$ServiceBat = Join-Path $Root "start-tradelab-service.bat"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$PsExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

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
    $lnk.TargetPath = $ServiceBat
    $lnk.WorkingDirectory = $Root
    $lnk.WindowStyle = 7
    $lnk.Description = "TradeLABtr Stock Screener (keep-alive)"
    $lnk.Save()
    Write-Host "Installed Startup shortcut: $lnkPath"
}

function New-EnsureTask {
    param(
        [string]$Name,
        [string[]]$Schedule
    )
    cmd /c "schtasks /Delete /TN `"$Name`" /F >nul 2>&1" | Out-Null
    $tr = "`"$PsExe`" -NoProfile -ExecutionPolicy Bypass -File `"$EnsurePs1`" -Port $Port"
    $args = @(
        "/Create", "/TN", $Name, "/TR", $tr
    ) + $Schedule + @("/F")
    if ($WindowsPassword) {
        $args += @("/RU", $WindowsUser, "/RP", $WindowsPassword, "/RL", "HIGHEST")
    } else {
        $args += @("/RU", $WindowsUser, "/RL", "LIMITED")
    }
    & schtasks @args
    return ($LASTEXITCODE -eq 0)
}

if (-not (Test-Path $EnsurePs1)) { throw "Missing $EnsurePs1" }
if (-not (Test-Path $Bat)) { throw "Missing $Bat" }
if (-not (Test-Path $Python)) {
    throw "Missing $Python — run: python -m venv .venv ; .\.venv\Scripts\pip install -r requirements.txt"
}

$isAdmin = Test-IsAdmin
Write-Host "Running as admin: $isAdmin"
Write-Host "Repo: $Root"

$freePort = Join-Path $Root "scripts\free-listen-port.ps1"
if (Test-Path $freePort) {
    & $freePort -Port $Port
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$createdMain = $false
$createdWatch = $false

if ($isAdmin) {
    $svc = Get-Service -Name $TaskName -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Host "Removing old Windows service $TaskName ..."
        Stop-Service $TaskName -Force -ErrorAction SilentlyContinue
        cmd /c "sc delete $TaskName >nul 2>&1"
        Start-Sleep -Seconds 2
    }

    if ($WindowsPassword) {
        $createdMain = New-EnsureTask -Name $TaskName -Schedule @("/SC", "ONSTART")
    } else {
        $createdMain = New-EnsureTask -Name $TaskName -Schedule @("/SC", "ONLOGON")
    }
    if ($createdMain) {
        Write-Host "Scheduled task: $TaskName"
        & schtasks /Run /TN $TaskName | Out-Null
    } else {
        Write-Warning "Main task create failed — Startup folder fallback."
    }

    $createdWatch = New-EnsureTask -Name $WatchTaskName -Schedule @("/SC", "MINUTE", "/MO", "5")
    if ($createdWatch) {
        Write-Host "Watchdog task: $WatchTaskName (every 5 minutes)"
    } else {
        Write-Warning "Watchdog task create failed."
    }
} else {
    Write-Warning "Not admin — Startup folder only (no 5-min watchdog)."
    Write-Warning "Yonetici PowerShell ile tekrar calistirin: sag tik -> Run as administrator"
}

if (-not $createdMain) {
    Install-StartupShortcut
}

Write-Host "Starting now..."
& $EnsurePs1 -Port $Port
Start-Sleep -Seconds 4

$ok = $false
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:${Port}/healthz" -UseBasicParsing -TimeoutSec 5
    $ok = ($r.StatusCode -eq 200)
} catch {}

if ($ok) {
    Write-Host "OK - TradeLABtr listening on port $Port"
    Write-Host "Open http://127.0.0.1:$Port/login"
} else {
    Write-Warning "Not healthy yet. Check storage\watchdog.log and storage\server.log"
}

Write-Host ""
Write-Host "Keep-alive:"
Write-Host "  Her 5 dk /healthz kontrol; dusukse arka planda yeniden baslar."
Write-Host "  git pull sonrasi zorla yenile:  .\start-tradelab.bat"
Write-Host "  Simdi kontrol:  powershell -File .\scripts\ensure-tradelab-running.ps1"
Write-Host ""
Write-Host "  schtasks /Query /TN $TaskName /V /FO LIST"
Write-Host "  schtasks /Query /TN $WatchTaskName /V /FO LIST"
Write-Host "  curl http://127.0.0.1:$Port/healthz"
