#!/usr/bin/env python3
"""Incremental OSM one-way research near Tokyo Station.
Writes to separate cache/output; never changes existing access data.
Missing OSM tags do not mean a road is legally unrestricted.
"""
import datetime
import json
import math
import pathlib
import sys
import urllib.parse
import urllib.request

CENTER = (35.681236, 139.767125)
OFFSET_M = 380
TILE_RADIUS_M = 360
ENDPOINTS = [
    'https://overpass.private.coffee/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass-api.de/api/interpreter',
]
CACHE = pathlib.Path('data/oneway_only_tiles')
OUT = pathlib.Path('data/tokyo_oneway_only.json')
CURSOR = CACHE / 'next_tile.json'
MAX_NEW_PARTS = 1


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(path)


def read(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def centers():
    for y in (-1, 0, 1):
        for x in (-1, 0, 1):
            yield (CENTER[0] + y * OFFSET_M / 111320,
                   CENTER[1] + x * OFFSET_M / (111320 * math.cos(math.radians(CENTER[0]))))


def parts(lat, lon):
    # 2x2 boxes, each 180m half-width, cover one parent tile.
    shift = TILE_RADIUS_M / 2
    for sy, sx in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        yield (lat + sy * shift / 111320,
               lon + sx * shift / (111320 * math.cos(math.radians(lat))), shift)


def overpass_query(lat, lon, radius):
    dy = radius / 111320
    dx = radius / (111320 * math.cos(math.radians(lat)))
    bbox = f'({lat-dy:.7f},{lon-dx:.7f},{lat+dy:.7f},{lon+dx:.7f})'
    # One tag only: smaller query than 10 separate access/conditional searches.
    return f'[out:json][timeout:20];way[highway][oneway]{bbox};out geom;'


def fetch(lat, lon, radius, label):
    errors = []
    payload = urllib.parse.urlencode({'data': overpass_query(lat, lon, radius)}).encode()
    for endpoint in ENDPOINTS:
        try:
            req = urllib.request.Request(endpoint, data=payload, method='POST', headers={
                'User-Agent': 'TokyoTaxiCockpitOneWayResearch/0.4 (GitHub Actions)',
                'Content-Type': 'application/x-www-form-urlencoded',
            })
            with urllib.request.urlopen(req, timeout=22) as response:
                obj = json.load(response)
            elements = obj.get('elements')
            if not isinstance(elements, list):
                raise ValueError('invalid elements')
            print(f'{label} OK: {len(elements)} ways from {endpoint}', flush=True)
            return elements
        except (OSError, ValueError) as exc:
            msg = f'{endpoint}: {type(exc).__name__}: {exc}'
            errors.append(msg)
            print(f'{label} FAILED: {msg}', flush=True)
    print(f'{label} PENDING: all endpoints failed', flush=True)
    return None


def item(el):
    if el.get('type') != 'way' or not isinstance(el.get('id'), int):
        return None
    tags = el.get('tags') or {}
    raw = str(tags.get('oneway', '')).lower()
    if raw not in ('yes', '1', 'true', '-1', 'no', '0', 'false', 'reversible', 'alternating'):
        return None
    geom = [[p['lat'], p['lon']] for p in el.get('geometry', []) if 'lat' in p and 'lon' in p]
    if len(geom) < 2:
        return None
    direction = 'forward' if raw in ('yes', '1', 'true') else 'reverse' if raw == '-1' else 'not_fixed_oneway'
    return {'osm_type': 'way', 'osm_id': el['id'], 'name': tags.get('name', ''),
            'highway': tags.get('highway', ''), 'oneway': raw,
            'direction': direction, 'geometry': geom}


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    cs = list(centers())
    tasks = [(i, j, lat, lon, r) for i, (plat, plon) in enumerate(cs, 1)
             for j, (lat, lon, r) in enumerate(parts(plat, plon), 1)]
    state = read(CURSOR) or {}
    start = int(state.get('next', 0)) % len(tasks)
    attempts = 0
    for n in range(len(tasks)):
        idx = (start + n) % len(tasks)
        i, j, lat, lon, r = tasks[idx]
        path = CACHE / f'tile_{i:02d}_part_{j:02d}.json'
        cached = read(path)
        if isinstance(cached, dict) and cached.get('version') == 1 and isinstance(cached.get('elements'), list):
            continue
        if attempts >= MAX_NEW_PARTS:
            break
        attempts += 1
        elements = fetch(lat, lon, r, f'TILE {i}/9 PART {j}/4')
        if elements is not None:
            save(path, {'version': 1, 'tile': i, 'part': j, 'elements': elements})
        # Always advance after an attempt so one bad area does not block others.
        save(CURSOR, {'next': (idx + 1) % len(tasks)})
    cached = []
    for i, j, *_ in tasks:
        d = read(CACHE / f'tile_{i:02d}_part_{j:02d}.json')
        if isinstance(d, dict) and d.get('version') == 1 and isinstance(d.get('elements'), list):
            cached.append(d)
    print(f'PROGRESS: {len(cached)}/36 subtiles saved; {attempts} new attempts this run.', flush=True)
    if len(cached) != len(tasks):
        print('INCOMPLETE: existing published JSON files unchanged. Run workflow again later.', flush=True)
        return
    roads = {}
    for d in cached:
        for el in d['elements']:
            it = item(el)
            if it:
                roads[it['osm_id']] = it
    if not roads:
        print('ERROR: no usable OSM ways; output unchanged.', flush=True)
        sys.exit(2)
    output = {
        'schema_version': 1,
        'source': 'OpenStreetMap via Overpass API',
        'dataset': 'oneway_only',
        'fetched_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'center_lat': CENTER[0], 'center_lon': CENTER[1],
        'count': len(roads),
        'notice': 'Research only. Not a complete legal road restriction dataset. Missing tags do not imply permission. Always follow posted signs.',
        'roads': [roads[k] for k in sorted(roads)],
    }
    save(OUT, output)
    print(f'COMPLETE: {len(roads)} ways saved to {OUT}', flush=True)


if __name__ == '__main__':
    main()
