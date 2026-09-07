#!/usr/bin/env python3
"""Generate local secrets and n8n imports; never overwrite an existing .env."""
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]


def write(path, text):
    # Pin LF: Linux containers read these files and three are committed; Windows text mode would emit CRLF.
    path.write_text(text, newline='\n')


def read_env():
    result = {}
    for line in (ROOT / '.env').read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            key, value = line.split('=', 1)
            result[key] = value
    return result


def node(name, kind, parameters, x, y=0, version=1, **kwargs):
    return {'id': name.lower().replace(' ', '-'), 'name': name,
            'type': 'n8n-nodes-base.' + kind, 'typeVersion': version,
            'position': [x, y], 'parameters': parameters, **kwargs}


def http_node(name, path, x, timeout=2000, body=None):
    parameters = {'method': 'POST', 'url': 'http://analyzer:8000' + path,
                  'authentication': 'genericCredentialType', 'genericAuthType': 'httpHeaderAuth',
                  'options': {'timeout': timeout}}
    if body:
        parameters.update({'sendBody': True, 'specifyBody': 'json', 'jsonBody': body})
        parameters['options']['response'] = {'response': {'fullResponse': True, 'neverError': True}}
    return node(name, 'httpRequest', parameters, x, version=4.2,
                credentials={'httpHeaderAuth': {'id': 'zebraAnalyzerAuth', 'name': 'Zebra internal API'}})


def workflow(identifier, name, nodes):
    connections = {a['name']: {'main': [[{'node': b['name'], 'type': 'main', 'index': 0}]]}
                   for a, b in zip(nodes, nodes[1:])}
    return {'id': identifier, 'name': name, 'active': False, 'nodes': nodes,
            'connections': connections, 'settings': {'executionOrder': 'v1', 'timezone': 'Asia/Phnom_Penh'},
            'pinData': {}, 'tags': []}


def main():
    env_path = ROOT / '.env'
    if not env_path.exists():
        content = (ROOT / '.env.example').read_text()
        for key in ['POSTGRES_PASSWORD', 'N8N_ENCRYPTION_KEY', 'ANALYZER_TOKEN']:
            content = content.replace(f'{key}=GENERATE', f'{key}={secrets.token_hex(32)}')
        content = content.replace('WEBHOOK_PATH=GENERATE', 'WEBHOOK_PATH=gold-' + secrets.token_hex(24))
        if sys.platform == 'darwin':
            content = content.replace('OLLAMA_RUNTIME=docker', 'OLLAMA_RUNTIME=native')
            content = content.replace('COMPOSE_PROFILES=docker-ai', 'COMPOSE_PROFILES=')
            content = content.replace('OLLAMA_BASE_URL=http://ollama:11434', 'OLLAMA_BASE_URL=http://host.docker.internal:11435')
        write(env_path, content)
    env_path.chmod(0o600)
    env = read_env()
    if any(not env.get(key) or env[key] == 'GENERATE' for key in
           ['POSTGRES_PASSWORD', 'N8N_ENCRYPTION_KEY', 'ANALYZER_TOKEN', 'WEBHOOK_PATH']):
        raise SystemExit('Fill the required secrets in .env; an existing .env is never overwritten.')
    import re
    if not re.fullmatch(r'[a-zA-Z0-9_-]{20,100}', env['WEBHOOK_PATH']):
        raise SystemExit('WEBHOOK_PATH must contain 20-100 letters, numbers, underscores or hyphens.')
    local = ROOT / '.local'
    local.mkdir(exist_ok=True, mode=0o700)
    imports = local / 'import'
    imports.mkdir(exist_ok=True)
    workflows = [workflow('zebraIngestV1', 'Zebra 1 — TradingView intake', [
        node('TradingView Webhook', 'webhook', {'httpMethod': 'POST', 'path': env['WEBHOOK_PATH'],
              'responseMode': 'responseNode', 'options': {}}, 0, version=2,
              webhookId='cambotix-zebra-intake'),
        http_node('Validate and persist', '/signals', 260, body='={{ $json.body }}'),
        node('Acknowledge durable receipt', 'respondToWebhook', {'respondWith': 'json',
             'responseBody': '={{ $json.body }}', 'options': {'responseCode': '={{ $json.statusCode }}'}}, 520, version=1.4)
    ]), workflow('zebraAnalyzeV1', 'Zebra 2 — Rules and local AI', [
        node('Every 15 seconds', 'scheduleTrigger', {'rule': {'interval': [{'field': 'seconds', 'secondsInterval': 15}]}}, 0, version=1.2),
        http_node('Process one durable signal', '/process', 260, timeout=(int(env.get('AI_TIMEOUT_SECONDS', '120')) + 15) * 1000)
    ]), workflow('zebraNotifyV1', 'Zebra 3 — Telegram outbox', [
        node('Every 15 seconds', 'scheduleTrigger', {'rule': {'interval': [{'field': 'seconds', 'secondsInterval': 15}]}}, 0, version=1.2),
        http_node('Deliver one notification', '/notify', 260, timeout=20000)
    ])]
    write(imports / 'workflows.json', json.dumps(workflows, indent=2) + '\n')
    credential_path = imports / 'credentials.json'
    write(credential_path, json.dumps([{'id': 'zebraAnalyzerAuth', 'name': 'Zebra internal API',
       'type': 'httpHeaderAuth', 'data': {'name': 'X-Zebra-Token', 'value': env['ANALYZER_TOKEN']}}]))
    credential_path.chmod(0o600)
    # Public gateway only accepts the exact webhook; n8n editor and analyzer stay private.
    config = '''limit_req_zone $binary_remote_addr zone=signals:10m rate=2r/s;
server {
    listen 8080;
    server_tokens off;
    access_log off;
    client_max_body_size 16k;
    location = /health { return 200 'ok'; }
    location = /webhook/WEBHOOK_PATH {
        limit_except POST { deny all; }
        limit_req zone=signals burst=10 nodelay;
        limit_req_status 429;
        # Re-resolve n8n per request: a recreated container gets a new IP and a cached one returns 502.
        resolver 127.0.0.11 valid=30s ipv6=off;
        set $n8n_upstream http://n8n:5678;
        proxy_pass $n8n_upstream;
        proxy_connect_timeout 1s;
        proxy_read_timeout 2500ms;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    location / { return 404; }
}
'''.replace('WEBHOOK_PATH', env['WEBHOOK_PATH'])
    write(local / 'gateway.conf', config)
    write(local / 'webhook-url.txt', env['PUBLIC_WEBHOOK_URL'].rstrip('/') + '/webhook/' + env['WEBHOOK_PATH'] + '\n')
    # Committable templates contain placeholders only.
    for item in workflows:
        for entry in item['nodes']:
            if entry['type'].endswith('.webhook'):
                entry['parameters']['path'] = 'REPLACE_WITH_GENERATED_WEBHOOK_PATH'
        write(ROOT / 'n8n' / (item['id'] + '.json'), json.dumps(item, indent=2) + '\n')
    print('Prepared .env, private imports, gateway configuration, and n8n templates.')


if __name__ == '__main__':
    main()
