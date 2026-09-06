#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exists=$(docker compose exec -T postgres psql -U zebra -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='zebra_tests'")
if [ "$exists" != "1" ]; then
  docker compose exec -T postgres createdb -U zebra zebra_tests
fi
tail -n +2 db/init.sql | docker compose exec -T postgres psql -U zebra -d zebra_tests -v ON_ERROR_STOP=1 >/dev/null
docker compose exec -T -e DB_NAME=zebra_tests analyzer python -m pytest -q -p no:cacheprovider tests
