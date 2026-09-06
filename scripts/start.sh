#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/setup.py
runtime=$(python3 -c 'from scripts.setup import read_env; print(read_env().get("OLLAMA_RUNTIME", "docker"))')
if [ "$runtime" = "native" ]; then
  python3 scripts/native_ollama.py
fi
docker compose up -d --build --wait
if [ ! -f .local/workflows-installed ]; then
  docker compose exec -T -u root n8n n8n import:credentials --input=/imports/credentials.json
  docker compose exec -T -u root n8n n8n import:workflow --input=/imports/workflows.json
  for workflow in zebraIngestV1 zebraAnalyzeV1 zebraNotifyV1; do
    docker compose exec -T -u root n8n n8n publish:workflow --id="$workflow"
  done
  published=$(docker compose exec -T postgres psql -U zebra -d n8n -tAc 'SELECT count(*) FROM workflow_entity WHERE id IN ('"'zebraIngestV1','zebraAnalyzeV1','zebraNotifyV1'"') AND "activeVersionId" IS NOT NULL')
  if [ "$published" != "3" ]; then
    echo 'Workflow publishing did not complete. Review the n8n import output.' >&2
    exit 1
  fi
  docker compose restart n8n
  docker compose up -d --wait
  touch .local/workflows-installed
fi
rm -f .local/import/credentials.json
model=$(python3 -c 'from scripts.setup import read_env; print(read_env()["OLLAMA_MODEL"])')
case "$runtime" in
  native) OLLAMA_HOST=127.0.0.1:11435 .local/ollama/bin/ollama pull "$model" ;;
  docker) docker compose exec -T ollama ollama pull "$model" ;;
  external)
    # An Ollama this project does not manage (e.g. the Ollama for Windows app on the Docker host).
    # Pull through the analyzer container so reachability is proven from where inference will run.
    docker compose exec -T analyzer python - <<'PY'
import json
import os
import urllib.error
import urllib.request

base, model = os.environ['OLLAMA_BASE_URL'].rstrip('/'), os.environ['OLLAMA_MODEL']
request = urllib.request.Request(base + '/api/pull', data=json.dumps({'model': model, 'stream': True}).encode(),
                                 headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(request, timeout=120) as response:
        last = None
        for line in response:
            event = json.loads(line)
            if event.get('error'):
                raise SystemExit(f"Ollama could not pull {model}: {event['error']}")
            text = event.get('status', '')
            if event.get('total'):
                text += f" {100 * event.get('completed', 0) // event['total'] // 10 * 10}%"
            if text != last:
                print(text, flush=True)
                last = text
except (urllib.error.URLError, OSError) as error:
    raise SystemExit(f'Ollama at {base} is not reachable from Docker ({error}). Start Ollama on the host or fix '
                     'OLLAMA_BASE_URL (Docker Desktop: http://host.docker.internal:11434).')
print(f'{model} is available at {base}.')
PY
    ;;
  *) echo "Unknown OLLAMA_RUNTIME '$runtime' (expected native, docker, or external)." >&2; exit 1 ;;
esac
python3 scripts/status.py
