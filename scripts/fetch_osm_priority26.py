#!/usr/bin/env python3
"""Fetch parent ways for 26 OSM nodes. Evidence only; never navigation."""
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'data' / 'tokyo_express_priority26_way_evidence.json'
OUTPUT = ROOT / 'data' / 'tokyo_express_priority26_osm_api_evidence.json'
BASE = 'https://api.openstreetmap.org/api/0.6/node/{}/ways.json'


def main():
    if not SOURCE.is_file():
        raise SystemExit(f'Missing input: {SOURCE}')
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    records = source.get('records', [])
    if len(records) != 26:
        raise SystemExit(f'Expected 26 records, found {len(records)}')
    output = {'format': 'tokyo-express-priority26-osm-api-evidence-v1',
              'generated_at_utc': datetime.now(timezone.utc).isoformat(),
              'source': SOURCE.name,
              'method': 'OSM standard API node/{id}/ways.json (parent ways only)',
              'verified_road_connections': 0,
              'safe_for_turn_by_turn_navigation': False,
              'records': []}
    for i, record in enumerate(records, 1):
        node_id = str(record.get('osm_id', '')).removeprefix('node/')
        if not node_id.isdigit():
            raise SystemExit(f'Invalid node id at index {i}: {node_id}')
        url = BASE.format(node_id)
        result = {'osm_id': 'node/' + node_id, 'name': record.get('name', ''),
                  'source_url': url, 'status': 'fetch_failed', 'ways': [],
                  'way_geometry_checked': False, 'surface_road_checked': False,
                  'turn_restrictions_checked': False, 'navigation_enabled': False}
        for attempt in range(1, 3):
            try:
                request = urllib.request.Request(url, headers={
                    'User-Agent': 'TokyoTaxiCockpitResearch/1.0 (OSM evidence; no routing)',
                    'Accept': 'application/json'})
                with urllib.request.urlopen(request, timeout=15) as response:
                    payload = json.load(response)
                result['ways'] = [{'id': way.get('id'), 'tags': way.get('tags', {}),
                                   'nodes': way.get('nodes', [])}
                                  for way in payload.get('elements', []) if way.get('type') == 'way']
                result['status'] = 'fetched'
                result.pop('error', None)
                break
            except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
                result['error'] = f'{type(exc).__name__}: {exc}'
                if attempt < 2:
                    time.sleep(2)
        output['records'].append(result)
        print(f"{i:02d}/26 {result['name']} status={result['status']} ways={len(result['ways'])}", flush=True)
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        output['summary'] = {
            'total': len(output['records']),
            'fetched': sum(r['status'] == 'fetched' for r in output['records']),
            'fetch_failed': sum(r['status'] == 'fetch_failed' for r in output['records'])}
        OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if i < len(records):
            time.sleep(1)
    print('SUMMARY', json.dumps(output['summary']), flush=True)


if __name__ == '__main__':
    main()
