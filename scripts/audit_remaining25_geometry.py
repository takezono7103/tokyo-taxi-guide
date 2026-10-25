#!/usr/bin/env python3
"""Research-only adjacency summary from previously saved OSM API evidence.
No driving legality, geometry coordinates, restrictions or routes are verified.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

SOURCE = Path('data/tokyo_express_priority26_osm_api_evidence.json')
OUTPUT = Path('data/tokyo_express_remaining25_geometry_research.json')
SHIODOME_ID = 'node/31253688'

def main():
    data = json.loads(SOURCE.read_text(encoding='utf-8'))
    records = data.get('records')
    if not isinstance(records, list) or len(records) != 26:
        raise ValueError('Expected exactly 26 source records; refusing incomplete audit')
    if sum(r.get('osm_id') == SHIODOME_ID for r in records) != 1:
        raise ValueError('Shiodome reference missing or duplicated')
    out = []
    for rec in records:
        if rec.get('osm_id') == SHIODOME_ID:
            continue
        osm_id = rec.get('osm_id', '')
        if not osm_id.startswith('node/'):
            raise ValueError('Unexpected node identifier')
        target = int(osm_id.split('/')[1])
        ways = []
        for way in rec.get('ways', []):
            nodes = way.get('nodes', [])
            tags = way.get('tags', {})
            indices = [i for i, node in enumerate(nodes) if node == target]
            ways.append({
                'way_id': way.get('id'),
                'highway': tags.get('highway'),
                'oneway': tags.get('oneway'),
                'target_indices': indices,
                'adjacent_nodes_in_stored_order': [
                    {'previous_node': nodes[i-1] if i > 0 else None,
                     'next_node': nodes[i+1] if i+1 < len(nodes) else None}
                    for i in indices
                ],
                'node_count': len(nodes),
                'interpretation': 'Stored node order only; not a verified permitted driving direction'
            })
        out.append({
            'osm_id': osm_id,
            'name': rec.get('name'),
            'source_status': rec.get('status'),
            'parent_way_count': len(ways),
            'parent_ways': ways,
            'turn_restrictions_checked': False,
            'official_road_authority_checked': False,
            'surface_street_approach_verified': False,
            'legal_drivability_verified': False,
            'safe_for_turn_by_turn_navigation': False,
        })
    if len(out) != 25:
        raise ValueError('Expected exactly 25 remaining records')
    result = {
        'format': 'tokyo-express-remaining25-geometry-research-v1',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_file': str(SOURCE),
        'record_count': len(out),
        'verified_road_connections': 0,
        'safe_for_turn_by_turn_navigation': False,
        'limitations': [
            'Uses stored parent way node lists only; no new API retrieval',
            'No coordinate geometry, intersection topology, turn restrictions or official road rules verified',
            'Adjacent OSM nodes do not prove legal vehicle access or allowed turns',
            'Never use this output for turn-by-turn route guidance',
        ],
        'records': out,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {len(out)} research-only records to {OUTPUT}')

if __name__ == '__main__':
    main()
