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
if [ "$runtime" = "native" ]; then
  OLLAMA_HOST=127.0.0.1:11435 .local/ollama/bin/ollama pull "$model"
else
  docker compose exec -T ollama ollama pull "$model"
fi
python3 scripts/status.py
