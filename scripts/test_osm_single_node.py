import json
import urllib.request
import urllib.error
from pathlib import Path

NODE_ID = '7022713621'
URL = f'https://api.openstreetmap.org/api/0.6/node/{NODE_ID}/ways.json'
OUTPUT = Path('osm_single_node_result.json')

result = {'node_id': NODE_ID, 'source_url': URL, 'status': 'fetch_failed', 'ways': [], 'navigation_enabled': False}
try:
    req = urllib.request.Request(URL, headers={'User-Agent': 'TokyoTaxiCockpitResearch/1.0'})
    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.load(response)
    result['ways'] = [x for x in data.get('elements', []) if x.get('type') == 'way']
    result['status'] = 'fetched'
except Exception as exc:
    result['error'] = f'{type(exc).__name__}: {exc}'

OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(f"status={result['status']} ways={len(result['ways'])}")
if 'error' in result:
    print(result['error'])
