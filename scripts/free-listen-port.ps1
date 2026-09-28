# Stop whatever is listening on a TCP port so TradeLABtr can bind after git pull.
param(
    [Parameter(Mandatory = $true)]
    [int]$Port
)

$ErrorActionPreference = "Continue"

function Get-ListenPids([int]$PortNumber) {
    $pids = @()
    try {
        $conns = Get-NetTCPConnection -LocalPort $PortNumber -State Listen -ErrorAction Stop
        $pids = @($conns | Select-Object -ExpandProperty OwningProcess -Unique)
    } catch {
        $lines = netstat -ano | Select-String -Pattern ":$PortNumber\s+.*LISTENING"
        foreach ($line in $lines) {
            $parts = ($line.Line -split "\s+") | Where-Object { $_ -ne "" }
            if ($parts.Length -ge 5) {
                $pids += [int]$parts[-1]
            }
        }
        $pids = @($pids | Select-Object -Unique)
    }
    return $pids
}

$owned = Get-ListenPids $Port
if (-not $owned -or $owned.Count -eq 0) {
    Write-Host "Port $Port bos."
    exit 0
}

foreach ($procId in $owned) {
    if ($procId -le 4) { continue }
    $name = ""
    try {
        $name = (Get-Process -Id $procId -ErrorAction Stop).ProcessName
    } catch {
        Write-Host "Port $Port PID $procId (surec bulunamadi), atlaniyor."
        continue
    }
    $ok = @("python", "pythonw", "py") -contains $name.ToLower()
    if (-not $ok) {
        Write-Host "[HATA] Port $Port $name (PID $procId) tarafindan kullaniliyor. TradeLABtr bunu kapatmaz."
        Write-Host "        O programi kapatin veya .env icinde PORT degistirin."
        exit 1
    }
    Write-Host "Eski TradeLABtr kapatiliyor: $name PID $procId (port $Port)"
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}

$deadline = (Get-Date).AddSeconds(10)
do {
    Start-Sleep -Milliseconds 400
    $left = Get-ListenPids $Port
    $left = @($left | Where-Object { $_ -gt 4 })
    if ($left.Count -eq 0) {
        Write-Host "Port $Port serbest."
        exit 0
    }
} while ((Get-Date) -lt $deadline)

Write-Host "[HATA] Port $Port hala dolu. Gorev Yoneticisi'nden python.exe kapatin."
exit 1
