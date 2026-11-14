# One-time setup on the Windows PC: registers the scheduled task "Cambotix Zebra Feeder", which runs
# scripts\feeder_service.ps1 hidden at sign-in, so the MT5 feeder (and Docker Desktop) come back after every reboot.
# Rerun it to change options; it replaces the existing task.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1                    # local stack, XAUUSDc
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 -Symbol XAUUSDm
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 -Vps               # analyzer on the VPS
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 -Uninstall
param(
    [string]$Symbol = 'XAUUSDc',
    [string]$Models = 'classic,smc',
    [switch]$Vps,
    [switch]$Uninstall
)
$ErrorActionPreference = 'Stop'
$taskName = 'Cambotix Zebra Feeder'
$root = Split-Path -Parent $PSScriptRoot

function Stop-Feeders {
    # Stopping the task ends its PowerShell host but not the Python child; end both so no second feeder survives.
    Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -like '*feeder_service.ps1*' -or $_.CommandLine -like '*mt5_feeder.py*' } |
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
$arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$service`" -Symbol $Symbol -Models $Models"
if ($Vps) { $arguments += ' -Vps' }
$user = "$env:USERDOMAIN\$env:USERNAME"

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger.Delay = 'PT30S'
# No time limit, run on battery, and restart the service itself if PowerShell ever dies.
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
# Interactive: MetaTrader 5 is a desktop app and only talks to Python inside the signed-in session.
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
        -Description 'Cambotix Zebra: keeps scripts\mt5_feeder.py running (scripts\feeder_service.ps1).' | Out-Null
} catch {
    throw "Could not register the task ($($_.Exception.Message)). Rerun this from PowerShell opened as Administrator."
}
Start-ScheduledTask -TaskName $taskName
Start-Sleep 5
$state = (Get-ScheduledTask -TaskName $taskName).State
Write-Host "task '$taskName' installed and $state ($Symbol, models $Models$(if ($Vps) { ', VPS' }))."
Write-Host "It starts 30s after you sign in. Watch it with:"
Write-Host "  Get-Content `"$root\.local\feeder.log`" -Tail 30 -Wait"
