#!/usr/bin/env python3
import json
import urllib.request
from setup import read_env

env = read_env()
request = urllib.request.Request('http://localhost:' + env['ANALYZER_PORT'] + '/signals',
                                 headers={'X-Zebra-Token': env['ANALYZER_TOKEN']})
with urllib.request.urlopen(request, timeout=5) as response:
    print(json.dumps(json.load(response), indent=2))
