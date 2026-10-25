#!/usr/bin/env python3
"""Bounded OSM parent-way evidence collection. NOT a navigation safety check.
Place this file in scripts/check_express_connections.py in the GitHub repository.
"""
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'data' / 'tokyo_express_priority26_connection_audit.json'
OUTPUT = ROOT / 'data' / 'tokyo_express_priority26_way_evidence.json'
ENDPOINTS = (
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass-api.de/api/interpreter',
)
BATCH_SIZE = 5
HTTP_TIMEOUT_SECONDS = 12


def save(records):
    statuses = {}
    for r in records:
        statuses[r['status']] = statuses.get(r['status'], 0) + 1
    obj = {
        'format': 'tokyo-express-priority26-way-evidence-v2',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'source': SOURCE.name,
        'method': 'Overpass parent highway ways by OSM node IDs; node membership and tags only',
        'summary': statuses,
        'verified_road_connections': 0,
        'safe_for_turn_by_turn_navigation': False,
        'records': records,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUTPUT.with_suffix('.json.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(OUTPUT)


def fetch(ids):
    csv = ','.join(str(n) for n in ids)
    query = f'[out:json][timeout:10];node(id:{csv})->.n;way(bn.n)[highway];out body;'
    errors = []
    for endpoint in ENDPOINTS:
        try:
            request = urllib.request.Request(
                endpoint,
                data=urllib.parse.urlencode({'data': query}).encode('utf-8'),
                headers={'User-Agent': 'TokyoTaxiCockpitResearch/2.0', 'Accept': 'application/json'},
            )
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                payload = json.load(response)
            if not isinstance(payload.get('elements'), list):
                raise ValueError('Overpass response missing elements list')
            return payload['elements'], endpoint, errors
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            errors.append(f'{endpoint}: {type(exc).__name__}: {str(exc)[:160]}')
    return None, None, errors


def main():
    inputs = json.loads(SOURCE.read_text(encoding='utf-8'))['records']
    results = []
    for start in range(0, len(inputs), BATCH_SIZE):
        batch = inputs[start:start + BATCH_SIZE]
        ids = [int(r['osm_id'].split('/')[-1]) for r in batch]
        print(f'Batch {start // BATCH_SIZE + 1}: {len(batch)} nodes', flush=True)
        ways, endpoint, errors = fetch(ids)
        for rec, node_id in zip(batch, ids):
            row = {
                'osm_id': rec['osm_id'],
                'name': rec['name'],
                'osm_node_url': rec['osm_node_url'],
                'way_geometry_checked': False,
                'surface_road_checked': False,
                'turn_restrictions_checked': False,
                'navigation_enabled': False,
            }
            if ways is None:
                row['status'] = 'fetch_failed'
                row['errors'] = errors
            else:
                matching = [w for w in ways if w.get('type') == 'way' and node_id in w.get('nodes', [])]
                row['adjacent_ways'] = [
                    {'id': w['id'], 'tags': w.get('tags', {}),
                     'url': f'https://www.openstreetmap.org/way/{w["id"]}'}
                    for w in matching
                ]
                row['status'] = 'way_tags_retrieved' if matching else 'no_adjacent_highway_ways_found'
                row['endpoint'] = endpoint
            row['note'] = 'OSMノード共有wayの属性のみ。道路接続・進入方向・交通規制・実際の通行可否は未検証。'
            results.append(row)
            print(f'  {len(results)}/{len(inputs)} {rec["name"]}: {row["status"]}', flush=True)
        save(results)  # checkpoint even when every endpoint failed
        time.sleep(1)
    print('SUMMARY:', json.loads(OUTPUT.read_text(encoding='utf-8'))['summary'], flush=True)
    print('Saved:', OUTPUT, flush=True)


if __name__ == '__main__':
    main()
