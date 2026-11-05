#!/usr/bin/env bash
# Deploy the Docker stack to a Linux VPS over SSH. Run from this repository (Linux, macOS, WSL or Git Bash):
#
#   bash scripts/deploy_vps.sh user@vps-host [--dir cambotix-zebra] [--port 22] [--gpu] [--test]
#
# First run: installs Docker if missing, ships the committed code (git HEAD), creates the VPS .env from the local one
# with fresh secrets and VPS runtime settings, and runs scripts/start.sh there. Later runs ship new code and rerun
# start.sh; the VPS .env, database and n8n volumes are never overwritten.
#
# Requirements: an Ubuntu/Debian VPS with key-based SSH as root or a user with passwordless sudo; about 4 GB RAM.
# Nothing is published to the Internet: every port stays on the VPS loopback. The MT5 feeder on the Windows PC reaches
# the analyzer through an SSH tunnel (scripts/vps_feeder.ps1); the connection details land in .local/vps.env.
set -euo pipefail
cd "$(dirname "$0")/.."
# Git Bash would otherwise rewrite remote absolute paths into Windows paths.
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'

usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit "${1:-0}"; }
host='' dir='cambotix-zebra' port=22 gpu=0 run_tests=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) dir=$2; shift 2 ;;
    --port) port=$2; shift 2 ;;
    --gpu) gpu=1; shift ;;
    --test) run_tests=1; shift ;;
    -h|--help) usage ;;
    -*) echo "Unknown option $1" >&2; usage 1 ;;
    *) host=$1; shift ;;
  esac
done
[ -n "$host" ] || usage 1
case "$dir" in /*|*..*|*' '*) echo '--dir must be a relative path under the remote home directory, without spaces.' >&2; exit 1 ;; esac
[ -f .env ] || { echo 'No local .env; run python3 scripts/setup.py first so the VPS inherits your Telegram and rule settings.' >&2; exit 1; }

ssh_opts=(-p "$port" -o ServerAliveInterval=30 -o ConnectTimeout=15)
remote() { ssh "${ssh_opts[@]}" "$host" "$@"; }

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo 'WARNING: uncommitted changes are NOT deployed; only the committed HEAD is shipped.' >&2
fi
revision=$(git rev-parse --short HEAD)

echo "==> Checking SSH access to $host"
remote 'uname -sm; . /etc/os-release && echo "$PRETTY_NAME"' || { echo 'SSH failed. Set up key login first: ssh-copy-id '"$host" >&2; exit 1; }

echo '==> Installing Docker and Python on the VPS if missing'
remote 'bash -s' <<'SH'
set -euo pipefail
sudo_cmd=''; [ "$(id -u)" -eq 0 ] || sudo_cmd='sudo'
if ! command -v python3 >/dev/null; then
  $sudo_cmd apt-get update -qq && $sudo_cmd apt-get install -y -qq python3
fi
if ! $sudo_cmd docker compose version >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | $sudo_cmd sh
fi
$sudo_cmd systemctl enable --now docker >/dev/null
if [ "$(id -u)" -ne 0 ] && ! id -nG | tr ' ' '\n' | grep -qx docker; then
  $sudo_cmd usermod -aG docker "$(id -un)"
  echo "Added $(id -un) to the docker group."
fi
mem=$(awk '/MemTotal/ {print int($2/1024/1024+0.5)}' /proc/meminfo)
[ "$mem" -ge 4 ] || echo "WARNING: ${mem} GB RAM. CPU Ollama with qwen2.5:1.5b wants about 4 GB in total; add swap or use a larger plan."
docker compose version 2>/dev/null || $sudo_cmd docker compose version
SH

echo "==> Shipping commit $revision to ~/$dir"
git archive --format=tar HEAD | remote "mkdir -p ~/$dir && tar -x -m -C ~/$dir && echo $revision > ~/$dir/.deployed-revision"

if remote "test -f ~/$dir/.env"; then
  echo '==> Keeping the existing VPS .env'
else
  echo '==> Creating the VPS .env (fresh secrets, Docker Ollama, loopback-only ports)'
  python3 - "$gpu" <<'PY' | remote "umask 077 && cat > ~/$dir/.env"
import re
import secrets
import sys
from pathlib import Path

gpu = sys.argv[1] == '1'
fresh = {key: secrets.token_hex(32) for key in ('POSTGRES_PASSWORD', 'N8N_ENCRYPTION_KEY', 'ANALYZER_TOKEN')}
fresh |= {
    'WEBHOOK_PATH': 'gold-' + secrets.token_hex(24),
    'PUBLIC_WEBHOOK_URL': 'http://localhost:8787/',  # no TradingView webhook: signals arrive from the MT5 feeder
    'OLLAMA_RUNTIME': 'docker',
    'COMPOSE_PROFILES': 'docker-ai',
    'OLLAMA_BASE_URL': 'http://ollama:11434',
}
if gpu:
    fresh['COMPOSE_FILE'] = 'compose.yaml:compose.gpu.yaml'
seen, lines = set(), []
for line in Path('.env').read_text(encoding='utf-8').splitlines():
    match = re.match(r'([A-Z0-9_]+)=', line)
    key = match.group(1) if match else None
    if key == 'COMPOSE_FILE' and not gpu:
        continue  # the local GPU overlay would fail on a VPS without an NVIDIA driver
    if key in fresh:
        line = f'{key}={fresh[key]}'
        seen.add(key)
    lines.append(line)
lines += [f'{key}={value}' for key, value in fresh.items() if key not in seen]
print('\n'.join(lines))
PY
fi

echo '==> Starting the stack on the VPS (first run pulls images and ~1 GB of model weights)'
# sg picks up a docker group membership added moments ago, without a new login.
remote "cd ~/$dir && if docker info >/dev/null 2>&1; then bash scripts/start.sh; else sg docker -c 'bash scripts/start.sh'; fi"

if [ "$run_tests" = 1 ]; then
  echo '==> Running the test suite on the VPS'
  remote "cd ~/$dir && if docker info >/dev/null 2>&1; then bash scripts/test.sh; else sg docker -c 'bash scripts/test.sh'; fi"
fi

token=$(remote "grep -E '^ANALYZER_TOKEN=' ~/$dir/.env | cut -d= -f2-")
analyzer_port=$(remote "grep -E '^ANALYZER_PORT=' ~/$dir/.env | cut -d= -f2-")
mkdir -p .local
(
  umask 077
  cat > .local/vps.env <<EOF
# Written by scripts/deploy_vps.sh; read by scripts/vps_feeder.ps1. Contains the VPS analyzer token: keep private.
VPS_HOST=$host
VPS_SSH_PORT=$port
VPS_ANALYZER_PORT=${analyzer_port:-8010}
TUNNEL_LOCAL_PORT=18010
ZEBRA_ANALYZER_URL=http://127.0.0.1:18010
ZEBRA_ANALYZER_TOKEN=$token
EOF
)

cat <<EOF

Deployed $revision to $host:~/$dir

Next, on this Windows PC (MT5 logged in), stop any local feeder, then run in PowerShell:
  powershell -ExecutionPolicy Bypass -File scripts\\vps_feeder.ps1
That opens the SSH tunnel (localhost:18010 -> VPS analyzer) and runs the feeder against the VPS.

On the VPS:
  ssh -p $port $host 'cd $dir && docker compose ps && python3 scripts/status.py'
  ssh -p $port $host 'cd $dir && python3 scripts/track_record.py'
n8n editor (loopback only): ssh -p $port -N -L 5680:127.0.0.1:5680 $host, then http://localhost:5680
EOF
