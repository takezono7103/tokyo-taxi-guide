#!/usr/bin/env python3
"""Read-only, small-batch OSM geometry diagnostic; never writes production data."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SOURCE = Path('data/chiyoda_oneway_merged_experimental.json')
OUT = Path('experimental/chiyoda_geometry')
OUT.mkdir(parents=True, exist_ok=True)
records = json.loads(SOURCE.read_text(encoding='utf-8'))['oneway_ways']
by_id = {int(item['osm_way_id']): item for item in records}
ids = sorted(by_id)
chunk_size = 5  # First verify five IDs; do not launch all batches yet.
batch = int(os.environ.get('GEOM_BATCH', '0'))
if batch < 0:
    raise SystemExit('Batch must be non-negative')
subset = ids[batch * chunk_size:(batch + 1) * chunk_size]
if not subset:
    raise SystemExit(f'Batch {batch} out of range ({len(ids)} ways, {chunk_size} per batch)')

query = '[out:json][timeout:25];way(id:' + ','.join(map(str, subset)) + ');out geom;'
endpoints = [
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass-api.de/api/interpreter',
]
result = None
errors = []
for endpoint in endpoints:
    try:
        print(f'Endpoint: {endpoint}; batch={batch}; IDs={len(subset)}', flush=True)
        request = urllib.request.Request(
            endpoint,
            data=urllib.parse.urlencode({'data': query}).encode('utf-8'),
            headers={'User-Agent': 'TokyoTaxiChiyodaGeometryExperimental/2.0', 'Accept': 'application/json'},
        )
        with urllib.request.urlopen(request, timeout=35) as response:
            result = json.load(response)
        if not isinstance(result, dict) or not isinstance(result.get('elements'), list):
            raise ValueError('Invalid Overpass JSON response')
        break
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        errors.append(f'{endpoint}: {exc}')
        print(f'Endpoint failed: {exc}', flush=True)
        time.sleep(2)
if result is None:
    raise SystemExit('Both endpoints failed; no output written. ' + ' | '.join(errors))

found = {}
for item in result['elements']:
    if item.get('type') != 'way':
        continue
    way_id = item.get('id')
    geom = item.get('geometry') or []
    if way_id in by_id and len(geom) >= 2:
        found[way_id] = {
            'osm_way_id': str(way_id),
            'oneway': by_id[way_id]['oneway'],
            'highway': by_id[way_id].get('highway'),
            'name': by_id[way_id].get('name'),
            'geometry': [[p['lon'], p['lat']] for p in geom],
        }
missing = [str(x) for x in subset if x not in found]
payload = {
    'purpose': 'EXPERIMENTAL VISUALIZATION ONLY - NOT FOR ROUTING',
    'batch': batch,
    'chunk_size': chunk_size,
    'requested': len(subset),
    'found': len(found),
    'missing_ids': missing,
    'features': list(found.values()),
    'osm_base_timestamp': result.get('osm3s', {}).get('timestamp_osm_base'),
}
output = OUT / f'geometry_batch_{batch:03d}.json'
output.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(f'RESULT: ok; BATCH: {batch}; REQUESTED: {len(subset)}; FOUND: {len(found)}; MISSING: {len(missing)}', flush=True)
print(f'OUTPUT: {output}', flush=True)
