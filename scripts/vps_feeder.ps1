# Run the MT5 feeder on this Windows PC against the analyzer on the VPS.
# Opens an SSH tunnel (127.0.0.1:18010 -> VPS 127.0.0.1:8010), keeps it alive, and runs scripts/mt5_feeder.py through it.
# Connection details and the VPS analyzer token come from .local/vps.env, written by scripts/deploy_vps.sh.
#
#   powershell -ExecutionPolicy Bypass -File scripts\vps_feeder.ps1                  # watch (default)
#   powershell -ExecutionPolicy Bypass -File scripts\vps_feeder.ps1 --once --dry-run # extra args go to the feeder
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$config = Join-Path $root '.local\vps.env'
if (-not (Test-Path $config)) { throw "Missing $config; run: bash scripts/deploy_vps.sh user@vps-host" }
$vps = @{}
foreach ($line in Get-Content $config) {
    if ($line -match '^([A-Z_]+)=(.*)$') { $vps[$Matches[1]] = $Matches[2] }
}
$localPort = $vps['TUNNEL_LOCAL_PORT']
$sshArgs = @('-N', '-p', $vps['VPS_SSH_PORT'], '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15',
             '-o', 'ServerAliveCountMax=3', '-o', 'BatchMode=yes',
             '-L', "127.0.0.1:${localPort}:127.0.0.1:$($vps['VPS_ANALYZER_PORT'])", $vps['VPS_HOST'])

# Reconnect the tunnel whenever it drops; the feeder backfills candles the analyzer missed once it is back.
$tunnel = Start-Job -ArgumentList (, $sshArgs) -ScriptBlock {
    param($sshArgs)
    while ($true) {
        & ssh.exe @sshArgs 2>&1 | ForEach-Object { "tunnel: $_" }
        "tunnel: disconnected, reconnecting in 5s"
        Start-Sleep 5
    }
}
try {
    $deadline = (Get-Date).AddSeconds(30)
    while ($true) {
        try {
            $health = Invoke-RestMethod "http://127.0.0.1:$localPort/health" -TimeoutSec 5
            Write-Host "VPS analyzer via tunnel: $($health.status)"
            break
        } catch {
            if ((Get-Date) -gt $deadline) {
                Receive-Job $tunnel | Write-Host
                throw "No analyzer at 127.0.0.1:$localPort through the tunnel to $($vps['VPS_HOST'])"
            }
            Start-Sleep 2
        }
    }
    $env:ZEBRA_ANALYZER_URL = $vps['ZEBRA_ANALYZER_URL']
    $env:ZEBRA_ANALYZER_TOKEN = $vps['ZEBRA_ANALYZER_TOKEN']
    $env:PYTHONUNBUFFERED = '1'
    & py (Join-Path $root 'scripts\mt5_feeder.py') @args
} finally {
    Receive-Job $tunnel -ErrorAction SilentlyContinue | Write-Host
    Stop-Job $tunnel
    Remove-Job $tunnel -Force
    Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" |
        Where-Object { $_.CommandLine -like "*127.0.0.1:${localPort}:*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
}
