#!/usr/bin/env python3
"""Research-only OSM way topology audit from stored evidence.

No new OSM API fetches. Shared nodes and directional topology are not
proof of legal driving access, turn permissions, or usable navigation.
"""
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path('data/tokyo_express_priority26_osm_api_evidence.json')
OUTPUT = Path('data/tokyo_express_remaining25_geometry_research.json')
SHIODOME_ID = 'node/31253688'


def normalize_node(value):
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    raise ValueError(f'Invalid OSM node identifier: {value!r}')


def directed_edges(nodes, oneway):
    """OSM-tag-indicated edge orientation, not a legally verified direction."""
    forward = list(zip(nodes, nodes[1:]))
    if oneway in ('yes', '1', 'true'):
        return forward, 'tag_forward'
    if oneway == '-1':
        return [(b, a) for a, b in forward], 'tag_reverse'
    if oneway in ('no', '0', 'false'):
        return forward + [(b, a) for a, b in forward], 'tag_bidirectional'
    return [], 'unknown_oneway_tag'


def main():
    data = json.loads(SOURCE.read_text(encoding='utf-8'))
    records = data.get('records')
    if not isinstance(records, list) or len(records) != 26:
        raise ValueError('Expected exactly 26 source records; refusing incomplete audit')
    ids = [r.get('osm_id') for r in records]
    if len(set(ids)) != 26 or ids.count(SHIODOME_ID) != 1:
        raise ValueError('Duplicate OSM IDs or Shiodome reference missing')

    out = []
    for rec in records:
        osm_id = rec.get('osm_id')
        if osm_id == SHIODOME_ID:
            continue
        if not isinstance(osm_id, str) or not osm_id.startswith('node/'):
            raise ValueError(f'Unexpected node identifier: {osm_id!r}')
        target = normalize_node(osm_id.split('/', 1)[1])
        raw_ways = rec.get('ways', [])
        if not isinstance(raw_ways, list):
            raise ValueError(f'Invalid ways for {osm_id}')

        ways = []
        node_to_ways = defaultdict(set)
        directed_by_way = {}
        for way in raw_ways:
            way_id = way.get('id')
            if not isinstance(way_id, int) or isinstance(way_id, bool):
                raise ValueError(f'Invalid way ID at {osm_id}')
            nodes = [normalize_node(n) for n in way.get('nodes', [])]
            tags = way.get('tags') or {}
            if not isinstance(tags, dict):
                raise ValueError(f'Invalid tags for way {way_id}')
            indices = [i for i, node in enumerate(nodes) if node == target]
            edges, direction_basis = directed_edges(nodes, tags.get('oneway'))
            directed_by_way[way_id] = set(edges)
            for node in nodes:
                node_to_ways[node].add(way_id)
            ways.append({
                'way_id': way_id,
                'highway': tags.get('highway'),
                'oneway': tags.get('oneway'),
                'target_indices': indices,
                'adjacent_nodes_in_stored_order': [
                    {'previous_node': nodes[i - 1] if i > 0 else None,
                     'next_node': nodes[i + 1] if i + 1 < len(nodes) else None}
                    for i in indices
                ],
                'node_count': len(nodes),
                'interpretation': 'Stored node order only; not a verified permitted driving direction',
                'tag_direction_basis': direction_basis,
                'has_target_node': bool(indices),
            })

        shared = [
            {'node_id': node, 'way_ids': sorted(way_ids)}
            for node, way_ids in node_to_ways.items() if len(way_ids) > 1
        ]
        shared.sort(key=lambda item: item['node_id'])
        target_way_ids = sorted(node_to_ways.get(target, set()))
        incoming_way_ids = sorted(
            wid for wid, edges in directed_by_way.items()
            if any(b == target for _, b in edges)
        )
        outgoing_way_ids = sorted(
            wid for wid, edges in directed_by_way.items()
            if any(a == target for a, _ in edges)
        )
        possible_transitions = [
            {'from_way_id': a, 'to_way_id': b, 'via_node_id': target,
             'interpretation': 'Tag-direction-compatible candidate only; turn legality unverified'}
            for a in incoming_way_ids for b in outgoing_way_ids if a != b
        ]
        out.append({
            'osm_id': osm_id,
            'name': rec.get('name'),
            'source_status': rec.get('status'),
            'parent_way_count': len(ways),
            'parent_ways': ways,
            'stored_topology': {
                'target_node_found_in_way_ids': target_way_ids,
                'shared_nodes_among_stored_ways': shared,
                'incoming_way_ids_by_oneway_tag': incoming_way_ids,
                'outgoing_way_ids_by_oneway_tag': outgoing_way_ids,
                'possible_directional_transitions_at_target': possible_transitions,
                'scope': 'Stored way-node memberships and oneway tags only',
            },
            'turn_restrictions_checked': False,
            'official_road_authority_checked': False,
            'surface_street_approach_verified': False,
            'legal_drivability_verified': False,
            'safe_for_turn_by_turn_navigation': False,
        })
    if len(out) != 25:
        raise ValueError('Expected exactly 25 remaining records')
    result = {
        'format': 'tokyo-express-remaining25-geometry-research-v2',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_file': str(SOURCE),
        'record_count': len(out),
        'verified_road_connections': 0,
        'safe_for_turn_by_turn_navigation': False,
        'limitations': [
            'Uses stored parent way node lists only; no new API retrieval',
            'Shared OSM nodes show mapped topology, not verified legal vehicle access',
            'Oneway tags suggest edge orientation but do not validate turning permissions',
            'No coordinate geometry, complete surrounding road network, or official rules checked',
            'Never use this output for turn-by-turn route guidance',
        ],
        'records': out,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {len(out)} research-only records to {OUTPUT}')
    print('Verified road connections: 0; turn-by-turn navigation: disabled')


if __name__ == '__main__':
    main()
