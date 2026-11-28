# One-time setup on the Windows PC: registers the scheduled task "Cambotix Zebra Feeder", which runs
# scripts\feeder_service.ps1 hidden at sign-in, so the MT5 feeder (and Docker Desktop) come back after every reboot.
# Rerun it to change options; it replaces the existing task.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1                    # local stack, XAUUSDm (CRT)
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 -Vps               # analyzer on the VPS
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 -Uninstall
# A second symbol gets its own task and log, next to the first (here the ICT model on EURUSD):
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 -Symbol EURUSDm -Models ict `
#       -TaskName 'Cambotix Zebra Feeder EURUSD' -LogName feeder-eurusd.log
# Chart-only feeders take a comma list (no signals; -Models is ignored):
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 -Script chart_feeder.py `
#       -Symbol "GBPUSDc,USDJPYc,AUDUSDc,USDCADc,USDCHFc,NZDUSDc" -TaskName 'Cambotix Zebra Feeder FX' -LogName feeder-fx.log
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 -Script binance_feeder.py `
#       -Symbol "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT" -TaskName 'Cambotix Zebra Feeder Binance' -LogName feeder-binance.log
# Reinstalling stops only the feeders of -Symbol; to move a task to another symbol, -Uninstall it with the old one first.
param(
    [string]$Symbol = 'XAUUSDm',
    [string]$Models = 'crt',
    [ValidateSet('mt5_feeder.py', 'chart_feeder.py', 'binance_feeder.py')]
    [string]$Script = 'mt5_feeder.py',
    [string]$TaskName = 'Cambotix Zebra Feeder',
    [string]$LogName = 'feeder.log',
    [switch]$Vps,
    [switch]$Uninstall
)
$ErrorActionPreference = 'Stop'
# cmd.exe keeps single quotes, so -TaskName 'A B' arrives as "'A" plus leftover words; refuse instead of making a stray task.
if ($args.Count -gt 0 -or $TaskName -match "['`"]") {
    throw "Unexpected arguments: $($args -join ' ') (TaskName=$TaskName). Run this from PowerShell, not cmd.exe, or use double quotes."
}
$taskName = $TaskName
$root = Split-Path -Parent $PSScriptRoot

function Stop-Feeders {
    # Stopping the task ends its PowerShell host but not the Python child; end both so no second feeder survives.
    # Only this symbol's feeders: another symbol's task (gold next to EURUSD) keeps running.
    Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -like '*feeder_service.ps1*' -or $_.CommandLine -match '(mt5|chart|binance)_feeder\.py' } |
        Where-Object { $_.CommandLine -match "(?i)--?symbols?\s+$([regex]::Escape($Symbol))(\s|$)" } |
        Where-Object { $_.ProcessId -ne $PID } |
        ForEach-Object {
            Write-Host "stopping $($_.Name) $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "removed the existing task '$taskName'"
}
Stop-Feeders
if ($Uninstall) { return }

if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Windows Python launcher "py" not found; install Python 3.12 from python.org' }
if (-not $Vps -and -not (Test-Path (Join-Path $root '.env'))) { throw "Missing $root\.env; run bash scripts/start.sh first" }
if ($Vps -and -not (Test-Path (Join-Path $root '.local\vps.env'))) { throw "Missing $root\.local\vps.env; run bash scripts/deploy_vps.sh first" }

$service = Join-Path $PSScriptRoot 'feeder_service.ps1'
$arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$service`" -Script $Script -Symbol $Symbol -Models $Models -LogName $LogName"
if ($Vps) { $arguments += ' -Vps' }
$user = "$env:USERDOMAIN\$env:USERNAME"

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger.Delay = 'PT30S'
# Watchdog: twice on 2026-11-26/27 every feeder host was killed at once (exit 0xC000013A, a console close) and the
# task's restart setting does not count that as a failure, so the feeds stayed down for hours. Starting the task every
# 5 minutes brings a dead service back; while one runs, the new copy exits at once (IgnoreNew, and the per-log mutex).
$watchdog = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
# No time limit, run on battery, and restart the service itself if PowerShell ever dies.
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
# Interactive: MetaTrader 5 is a desktop app and only talks to Python inside the signed-in session.
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($trigger, $watchdog) -Settings $settings -Principal $principal `
        -Description "Cambotix Zebra: keeps scripts\$Script running (scripts\feeder_service.ps1)." | Out-Null
} catch {
    throw "Could not register the task ($($_.Exception.Message)). Rerun this from PowerShell opened as Administrator."
}
Start-ScheduledTask -TaskName $taskName
Start-Sleep 5
$state = (Get-ScheduledTask -TaskName $taskName).State
Write-Host "task '$taskName' installed and $state ($Script $Symbol$(if ($Script -eq 'mt5_feeder.py') { ", models $Models" })$(if ($Vps) { ', VPS' }))."
Write-Host "It starts 30s after you sign in. Watch it with:"
Write-Host "  Get-Content `"$root\.local\$LogName`" -Tail 30 -Wait"
