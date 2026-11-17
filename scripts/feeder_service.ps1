# Keeps the MT5 feeder running unattended: starts Docker Desktop if needed, waits for the analyzer,
# runs scripts/mt5_feeder.py and restarts it 30s after it exits for any reason. Output goes to .local\feeder.log.
# Normally started at sign-in by the scheduled task from scripts\install_autostart.ps1; it can also be run by hand.
#
#   powershell -ExecutionPolicy Bypass -File scripts\feeder_service.ps1                    # local stack
#   powershell -ExecutionPolicy Bypass -File scripts\feeder_service.ps1 -Vps               # VPS analyzer via scripts\vps_feeder.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\feeder_service.ps1 -Symbol EURUSDm -Models ict -LogName feeder-eurusd.log
# Each symbol runs its own service; give a second one its own -LogName so the two logs do not interleave.
param(
    [string]$Symbol = 'XAUUSDm',
    [string]$Models = 'crt',
    [string]$LogName = 'feeder.log',
    [switch]$Vps
)
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root '.local'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir $LogName

function Write-Log([string]$message) {
    if ((Test-Path $log) -and (Get-Item $log).Length -gt 10MB) { Move-Item -Force $log "$log.1" }
    Add-Content -Path $log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $message" -Encoding utf8
}

function Get-AnalyzerPort {
    $port = '8010'
    $envFile = Join-Path $root '.env'
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            if ($line -match '^\s*ANALYZER_PORT\s*=\s*(\d+)') { $port = $Matches[1] }
        }
    }
    $port
}

function Test-Analyzer([string]$port) {
    try { $null -ne (Invoke-RestMethod "http://127.0.0.1:$port/health" -TimeoutSec 5) } catch { $false }
}

function Start-DockerDesktop {
    if (Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue) { return }
    $exe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path $exe) {
        Write-Log 'Docker Desktop is not running; starting it'
        Start-Process $exe
    } else {
        Write-Log "Docker Desktop not found at $exe"
    }
}

$port = Get-AnalyzerPort
$feederArgs = @('--symbol', $Symbol, '--models', $Models)
$env:PYTHONUNBUFFERED = '1'
$target = if ($Vps) { 'VPS analyzer' } else { "local analyzer 127.0.0.1:$port" }
Write-Log "feeder service started: $Symbol, models $Models, $target"

while ($true) {
    if ($Vps) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'scripts\vps_feeder.ps1') @feederArgs *>&1 |
            ForEach-Object { Write-Log "$_" }
    } else {
        # After a reboot Docker and the containers take a minute or two; containers return on their own (restart: unless-stopped).
        $waited = 0
        while (-not (Test-Analyzer $port)) {
            if ($waited -eq 0) {
                Write-Log "waiting for the analyzer on 127.0.0.1:$port"
                Start-DockerDesktop
            }
            Start-Sleep 10
            $waited += 10
            if ($waited % 600 -eq 0) {
                Write-Log "analyzer still down after $($waited / 60) min; check Docker Desktop, or run: bash scripts/start.sh"
            }
        }
        Write-Log 'analyzer is up; starting feeder'
        & py (Join-Path $root 'scripts\mt5_feeder.py') @feederArgs *>&1 | ForEach-Object { Write-Log "$_" }
    }
    Write-Log "feeder exited (code $LASTEXITCODE); restarting in 30s"
    Start-Sleep 30
}
