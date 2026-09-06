#!/usr/bin/env python3
"""Send clearly labeled SYNTHETIC BUY and SELL setups through gateway -> n8n -> rules -> local AI -> Telegram.
Unlike smoke.py this deliberately exercises the AI stage and, if enabled, Telegram. Event IDs start with
DEMO-SYNTHETIC so the journal and messages cannot be mistaken for market data. No orders exist in this system.

usage: python3 scripts/demo.py [SYMBOL] [classic|smc]
"""
import json
import sys
import time
import urllib.error
import urllib.request
from setup import read_env

env = read_env()
symbol = (sys.argv[1] if len(sys.argv) > 1 else 'XAUUSD').upper()
model = (sys.argv[2] if len(sys.argv) > 2 else 'classic').lower()
if symbol not in {s.strip().upper() for s in env.get('SYMBOLS', 'XAUUSD').split(',')}:
    raise SystemExit(f'{symbol} is not in SYMBOLS; add it to .env and run docker compose up -d analyzer')
if model not in ('classic', 'smc'):
    raise SystemExit('model must be classic or smc')
url = 'http://localhost:' + env['GATEWAY_PORT'] + '/webhook/' + env['WEBHOOK_PATH']
# Coherent hypothetical values around a gold reference price, scaled to the symbol; rules pass so the AI decides.
scale = {'XAUUSD': 3510.0, 'BTCUSD': 79800.0, 'BTCUSDT': 79800.0}.get(symbol, 100.0) / 3510.0
unscaled = {'rsi', 'adx', 'htf_bias', 'killzone', 'score', 'hit_rate', 'samples', 'daily_bias', 'h4_bias', 'swept_name', 'target_name'}
setups = {
    'classic': {
        'BUY_SETUP': {'price': 3512.4, 'ema20': 3508.9, 'ema50': 3503.2, 'ema200': 3481.7, 'rsi': 58.6, 'macd_hist': 1.8,
                      'adx': 27.8, 'atr': 4.4, 'swing_high': 3515.9, 'swing_low': 3498.3},
        'SELL_SETUP': {'price': 3468.2, 'ema20': 3474.6, 'ema50': 3481.9, 'ema200': 3503.4, 'rsi': 41.2, 'macd_hist': -1.7,
                       'adx': 26.4, 'atr': 4.6, 'swing_high': 3492.8, 'swing_low': 3465.0}},
    'smc': {
        'BUY_SETUP': {'price': 3513.5, 'atr': 4.2, 'htf_bias': 1, 'sweep_level': 3496.0, 'mss_level': 3512.0,
                      'fvg_top': 3509.0, 'fvg_bottom': 3505.0, 'ob_top': 3506.0, 'ob_bottom': 3503.0,
                      'range_high': 3540.0, 'range_low': 3496.0, 'entry': 3507.0, 'stop': 3495.6,
                      'target_liquidity': 3540.0, 'killzone': 'demo', 'score': 95, 'hit_rate': 0.58, 'samples': 24,
                      'daily_bias': 1, 'h4_bias': 1, 'pdh': 3540.0, 'pdl': 3496.0, 'pwh': 3580.0, 'pwl': 3450.0,
                      'asia_high': 3520.0, 'asia_low': 3500.0, 'swept_name': 'PDL', 'target_name': 'PDH'},
        'SELL_SETUP': {'price': 3506.5, 'atr': 4.2, 'htf_bias': -1, 'sweep_level': 3524.0, 'mss_level': 3508.0,
                       'fvg_top': 3515.0, 'fvg_bottom': 3511.0, 'ob_top': 3517.0, 'ob_bottom': 3514.0,
                       'range_high': 3524.0, 'range_low': 3480.0, 'entry': 3513.0, 'stop': 3524.42,
                       'target_liquidity': 3480.0, 'killzone': 'demo', 'score': 90, 'hit_rate': 0.5, 'samples': 12,
                       'daily_bias': -1, 'h4_bias': -1, 'pdh': 3524.0, 'pdl': 3480.0, 'pwh': 3560.0, 'pwl': 3440.0,
                       'asia_high': 3522.0, 'asia_low': 3505.0, 'swept_name': 'PDH', 'target_name': 'PDL'}},
}[model]
history = urllib.request.Request('http://localhost:' + env['ANALYZER_PORT'] + '/signals',
                                 headers={'X-Zebra-Token': env['ANALYZER_TOKEN']})
for direction, values in setups.items():
    stamp = int(time.time())
    payload = {'event_id': f'DEMO-SYNTHETIC-{model}-{symbol}-{stamp}-{direction}', 'symbol': symbol, 'timeframe': '15m',
               'bar_time': stamp, 'signal': direction, 'model': model,
               **{k: (v if k in unscaled else round(v * scale, 2)) for k, v in values.items()}}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            print(f"{direction} ({model}): HTTP {response.status} {json.load(response)['status']}")
    except urllib.error.HTTPError as error:
        raise SystemExit(f'{direction}: HTTP {error.code} {error.read().decode()[:200]}')
    started = time.monotonic()
    while time.monotonic() - started < 420:
        with urllib.request.urlopen(history, timeout=5) as response:
            record = next(item for item in json.load(response) if item['event_id'] == payload['event_id'])
        if record['status'] not in ('queued', 'processing') and record['notification_status'] != 'pending':
            break
        time.sleep(2)
    else:
        raise SystemExit(f'{direction}: no result within 420 seconds; inspect docker compose logs analyzer')
    analysis = record['analysis'] or {}
    print(f"  result: {record['status'].upper()} in {time.monotonic() - started:.0f}s | checks: {record['rule_reasons']} "
          f"| telegram: {record['notification_status']}")
    if analysis:
        print(f"  AI: {analysis['decision']} score {analysis['confidence']}/100, regime {analysis['market_regime']}, "
              f"quality {analysis['setup_quality']}")
        for reason in analysis['reasons']:
            print('   -', reason)
        print('   flags:', '; '.join(analysis['risk_flags']))
print('Synthetic demo only. Values are hypothetical; nothing was traded.')
