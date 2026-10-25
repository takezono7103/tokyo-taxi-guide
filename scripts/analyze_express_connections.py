"""Offline, conservative OSM parent-way adjacency audit. NOT routing validation."""
import json
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data' / 'tokyo_express_priority26_osm_api_evidence.json'
OUTPUT = ROOT / 'data' / 'tokyo_express_priority26_connection_audit.json'

def main():
    data = json.loads(SOURCE.read_text(encoding='utf-8'))
    records = data.get('records', [])
    if len(records) != 26:
        raise ValueError(f'Expected 26 records, got {len(records)}')
    out = []
    for rec in records:
        node = int(str(rec['osm_id']).split('/')[-1])
        links = []
        for way in rec.get('ways', []):
            nodes = way.get('nodes', [])
            tags = way.get('tags', {})
            for idx, nid in enumerate(nodes):
                if nid != node:
                    continue
                oneway = tags.get('oneway', '')
                # Only interpret explicit yes / -1; other values remain unknown.
                prev_node = nodes[idx-1] if idx else None
                next_node = nodes[idx+1] if idx+1 < len(nodes) else None
                if oneway == 'yes':
                    incoming, outgoing = prev_node, next_node
                elif oneway == '-1':
                    incoming, outgoing = next_node, prev_node
                else:
                    incoming = outgoing = None
                links.append({'way_id': way.get('id'), 'highway': tags.get('highway'),
                              'oneway': oneway or None, 'previous_node': prev_node,
                              'next_node': next_node, 'incoming_node_candidate': incoming,
                              'outgoing_node_candidate': outgoing,
                              'interpretation': 'OSM way-node order only; not a validated maneuver'})
        out.append({'osm_id': rec['osm_id'], 'name': rec.get('name'),
                    'fetch_status': rec.get('status'), 'parent_way_count': len(rec.get('ways', [])),
                    'adjacency_candidates': links,
                    'road_connection_verified': False, 'turn_restrictions_checked': False,
                    'surface_road_checked': False, 'navigation_enabled': False})
    result = {'format': 'tokyo-express-priority26-connection-audit-v1',
              'generated_at_utc': datetime.now(timezone.utc).isoformat(),
              'source': SOURCE.name, 'records_count': len(out),
              'source_status_counts': dict(Counter(x.get('status', 'unknown') for x in records)),
              'verified_road_connections': 0,
              'safe_for_turn_by_turn_navigation': False,
              'limitations': ['Only locally supplied parent ways are inspected',
                              'Node coordinates, full network geometry and OSM restriction relations not checked',
                              'Adjacency candidates are not legal or drivable turn instructions',
                              'No surface road or official road authority verification'],
              'records': out}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'Analyzed {len(out)} records; navigation remains disabled; output={OUTPUT}')

if __name__ == '__main__':
    main()
