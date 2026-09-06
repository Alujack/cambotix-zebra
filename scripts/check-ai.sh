#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Synthetic data only: no database writes, notifications, or orders.
docker compose exec -T analyzer python - <<'PY'
import json
import time
from app.domain import Signal
from app.main import classify

signal = Signal.model_validate({
    'event_id': 'synthetic-ai-check', 'symbol': 'XAUUSD', 'timeframe': '15m',
    'bar_time': int(time.time()), 'signal': 'BUY_SETUP', 'price': 3510.25,
    'ema20': 3507.1, 'ema50': 3502.8, 'ema200': 3479.4,
    'rsi': 58.3, 'macd_hist': 2.1, 'adx': 29.4, 'atr': 4.2,
})
started = time.monotonic()
result = classify(signal)
print(json.dumps(result.model_dump(), indent=2))
print(f'PASS: local model returned valid structured analysis in {time.monotonic()-started:.1f}s')
print('Synthetic example only. Nothing saved, sent, or traded.')
PY
