#!/usr/bin/env python3
import json
import sys
import urllib.request
from setup import read_env

env = read_env()
print('n8n editor: http://localhost:' + env['N8N_PORT'])
print('Private TradingView URL: .local/webhook-url.txt')
print('Mode: signal analysis / manual review (no trading execution)')
print('Telegram enabled: ' + env.get('TELEGRAM_ENABLED', 'false'))
try:
    response = urllib.request.urlopen('http://localhost:' + env['ANALYZER_PORT'] + '/health', timeout=5)
    print('Analyzer:', json.load(response)['status'])
except Exception:
    print('Analyzer unavailable; inspect docker compose ps and docker compose logs analyzer')
    sys.exit(1)
