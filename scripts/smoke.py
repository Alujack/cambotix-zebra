#!/usr/bin/env python3
"""Real gateway -> n8n -> DB smoke test; deliberately rejected, never calls AI or Telegram."""
import json
import time
import urllib.error
import urllib.request
from setup import read_env

env = read_env()
if env.get('TELEGRAM_ENABLED', 'false').lower() == 'true':
    raise SystemExit('Smoke test requires TELEGRAM_ENABLED=false so it cannot send a real message.')
stamp = int(time.time())
payload = {'event_id': f'smoke-{stamp}', 'symbol': 'XAUUSD', 'timeframe': '15m', 'bar_time': stamp,
           'signal': 'BUY_SETUP', 'price': 3510.25, 'ema20': 3507.1, 'ema50': 3502.8, 'ema200': 3479.4,
           'rsi': 58.3, 'macd_hist': 2.1, 'adx': 5, 'atr': 4.2}
url = 'http://localhost:' + env['GATEWAY_PORT'] + '/webhook/' + env['WEBHOOK_PATH']


def post(data):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status, json.load(response), time.monotonic() - start
    except urllib.error.HTTPError as error:
        return error.code, json.load(error), time.monotonic() - start


code, body, elapsed = post(payload)
assert code == 202, (code, body)
assert elapsed < 3, elapsed
print(f'Persisted via n8n in {elapsed:.3f}s (HTTP 202)')
code, body, _ = post(payload)
assert code == 200 and body['status'] == 'duplicate', (code, body)
print('Duplicate correctly ignored')
code, body, _ = post({**payload, 'price': 9999})
assert code == 409, (code, body)
code, body, _ = post({**payload, 'adx': 'not a number'})
assert code == 422, (code, body)
print('Conflicting IDs and invalid input rejected')
request = urllib.request.Request('http://localhost:' + env['ANALYZER_PORT'] + '/signals',
                                 headers={'X-Zebra-Token': env['ANALYZER_TOKEN']})
for _ in range(25):
    with urllib.request.urlopen(request, timeout=5) as response:
        record = next(item for item in json.load(response) if item['event_id'] == payload['event_id'])
    if record['status'] == 'rejected':
        assert 'weak_trend' in record['rule_reasons'], record
        assert record['notification_status'] == 'disabled', record
        print('Scheduled worker rejected weak trend; audit history and disabled notification saved')
        break
    time.sleep(1)
else:
    raise SystemExit('Scheduled worker did not process the signal within 25 seconds')
print('PASS — no orders or Telegram messages sent')
