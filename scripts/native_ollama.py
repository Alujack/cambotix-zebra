#!/usr/bin/env python3
"""Install a verified, project-local macOS Ollama and start it on loopback."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.33.3'
LOCAL = ROOT / '.local' / 'ollama'


def running():
    try:
        with urllib.request.urlopen('http://127.0.0.1:11435/api/version', timeout=2) as response:
            return bool(json.load(response).get('version'))
    except Exception:
        return False


def main():
    if sys.platform != 'darwin':
        raise SystemExit('Native installer is for macOS. Use OLLAMA_RUNTIME=docker elsewhere.')
    LOCAL.mkdir(parents=True, exist_ok=True)
    binary = LOCAL / 'bin' / 'ollama'
    if not binary.exists():
        archive = LOCAL / 'ollama-darwin.tgz'
        base = f'https://github.com/ollama/ollama/releases/download/v{VERSION}/'
        if not archive.exists():
            subprocess.run(['curl', '-fL', '--retry', '3', base + archive.name, '-o', str(archive)], check=True)
        checksums = urllib.request.urlopen(base + 'sha256sum.txt', timeout=30).read().decode()
        expected = next(line.split()[0] for line in checksums.splitlines() if line.split()[-1].lstrip('*./') == archive.name)
        digest = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
        if digest != expected:
            archive.unlink()
            raise SystemExit('Ollama archive checksum mismatch; run again to download a fresh copy.')
        with tarfile.open(archive) as bundle:
            bundle.extractall(LOCAL / 'bin', filter='data')
        archive.unlink()
    if running():
        print('Native Ollama is already listening on localhost:11435.')
        return
    env = {**os.environ, 'OLLAMA_HOST': '127.0.0.1:11435', 'OLLAMA_MODELS': str(LOCAL / 'models'),
           'OLLAMA_NUM_PARALLEL': '1', 'OLLAMA_MAX_LOADED_MODELS': '1'}
    with (LOCAL / 'server.log').open('ab') as log:
        process = subprocess.Popen([str(binary), 'serve'], cwd=LOCAL / 'bin', env=env,
                                    stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    (LOCAL / 'server.pid').write_text(str(process.pid))
    for _ in range(30):
        if running():
            print('Native Ollama started on localhost:11435; files and models stay in .local/ollama.')
            return
        if process.poll() is not None:
            raise SystemExit('Native Ollama failed; inspect .local/ollama/server.log.')
        time.sleep(1)
    raise SystemExit('Native Ollama did not become ready; inspect .local/ollama/server.log.')


if __name__ == '__main__':
    main()
