#!/usr/bin/env python3
"""Inspect OSM geometry around Shiodome entrance. Research only, NOT navigation."""
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

NODE_ID = 31253688
BASE = 'https://api.openstreetmap.org/api/0.6'
OUT = Path('data/shiodome_connection_geometry_audit.json')

def fetch_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'TokyoTaxiGuideResearch/1.0 (OSM geometry audit)', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)

def main():
    node_response = fetch_json(f'{BASE}/node/{NODE_ID}.json')
    node = next(e for e in node_response['elements'] if e['type'] == 'node' and e['id'] == NODE_ID)
    ways_response = fetch_json(f'{BASE}/node/{NODE_ID}/ways.json')
    ways = [e for e in ways_response.get('elements', []) if e.get('type') == 'way']
    details = []
    for way in ways:
        ids = way.get('nodes', [])
        indices = [i for i, n in enumerate(ids) if n == NODE_ID]
        details.append({
            'way_id': way['id'], 'tags': way.get('tags', {}),
            'node_count': len(ids),
            'at_target': [{'index': i, 'previous_node': ids[i-1] if i else None,
                           'next_node': ids[i+1] if i+1 < len(ids) else None} for i in indices],
            'way_node_ids': ids,
        })
        time.sleep(0.2)
    report = {
        'format': 'shiodome-osm-geometry-research-v1',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'target': {'name': '汐留入口', 'osm_node_id': NODE_ID,
                   'lat': node.get('lat'), 'lon': node.get('lon'), 'tags': node.get('tags', {})},
        'parent_ways': details,
        'parent_way_count': len(details),
        'turn_restrictions_checked': False,
        'official_road_authority_checked': False,
        'legal_drivability_verified': False,
        'safe_for_turn_by_turn_navigation': False,
        'notes': [
            'Shared OSM nodes indicate mapped geometric topology only.',
            'Way direction and oneway tags alone do not prove legal turning access.',
            'Turn restriction relations, current traffic rules, and official road data require separate verification.',
            'Do not enable route guidance based on this report.'
        ]
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {OUT}; parent ways={len(details)}; navigation enabled=false')

if __name__ == '__main__':
    main()
