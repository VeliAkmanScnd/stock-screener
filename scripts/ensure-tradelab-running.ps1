# Ensure TradeLABtr is listening. Safe to run every few minutes (watchdog).
# Does NOT kill a healthy process. For forced restart after git pull use start-tradelab.bat.
param(
    [int]$Port = 8000,
    [int]$WaitSeconds = 25
)

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
if (-not (Test-Path (Join-Path $Root "run.py"))) {
    $Root = $ScriptDir
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
$LogDir = Join-Path $Root "storage"
$WatchLog = Join-Path $LogDir "watchdog.log"
$HealthUrl = "http://127.0.0.1:${Port}/healthz"

function Write-Watch([string]$msg) {
    $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $msg
    Write-Host $line
    try {
        if (-not (Test-Path $LogDir)) {
            New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
        }
        Add-Content -Path $WatchLog -Value $line -Encoding UTF8
    } catch {}
}

function Test-Healthy {
    try {
        $r = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 4
        return ($r.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Test-PortListen {
    try {
        $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
        return [bool]$c
    } catch {
        $hit = netstat -ano | Select-String -Pattern ":$Port\s+.*LISTENING"
        return [bool]$hit
    }
}

if (-not (Test-Path $Python)) {
    Write-Watch "[HATA] venv python yok: $Python"
    exit 1
}

if (Test-Healthy) {
    Write-Watch "OK — TradeLABtr ayakta (healthz)."
    exit 0
}

if (Test-PortListen) {
    Write-Watch "OK — port $Port dinleniyor (healthz henuz hazir degil)."
    exit 0
}

Write-Watch "DOWN — baslatiliyor (HOST=0.0.0.0 PORT=$Port)..."

$env:HOST = "0.0.0.0"
$env:PORT = "$Port"
$env:PYTHONUNBUFFERED = "1"

$outLog = Join-Path $LogDir "service-stdout.log"
$errLog = Join-Path $LogDir "service-stderr.log"

try {
    Start-Process `
        -FilePath $Python `
        -ArgumentList @("-u", "run.py") `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog |
        Out-Null
} catch {
    Write-Watch "[HATA] Start-Process: $_"
    exit 1
}

$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    if (Test-Healthy) {
        Write-Watch "OK — TradeLABtr yeniden ayaga kalkti."
        exit 0
    }
}

if (Test-PortListen) {
    Write-Watch "UYARI — port acik ama healthz basarisiz; storage\server.log bakin."
    exit 0
}

Write-Watch "[HATA] Baslatma sonrasi healthz yok. storage\server.log / service-stderr.log"
exit 1
