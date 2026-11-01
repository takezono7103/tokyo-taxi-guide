#!/usr/bin/env python3
"""Fetch OSM one-way and explicit vehicle access tags near Tokyo Station.
Research only: never infer permission to enter from missing OSM tags.
"""
import datetime
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

CENTER = (35.681236, 139.767125)
RADIUS = 850  # overall approximate study area, not Tokyo's 23 wards
# 3x3 overlapping smaller circles, to avoid one large Overpass query.
OFFSET_M = 380
TILE_RADIUS_M = 360
ENDPOINTS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
]
CACHE = pathlib.Path('data/oneway_access_tiles')
MAX_NEW_TILES = 3
OUT = pathlib.Path('data/tokyo_oneway_access.json')


def centers():
    import math
    for y in (-1, 0, 1):
        for x in (-1, 0, 1):
            yield (CENTER[0] + y * OFFSET_M / 111_320,
                   CENTER[1] + x * OFFSET_M / (111_320 * math.cos(math.radians(CENTER[0]))))


def query(lat, lon):
    return (f'[out:json][timeout:20];'
            f'way(around:{TILE_RADIUS_M},{lat:.7f},{lon:.7f})[highway]'
            '[~"^(oneway|access|vehicle|motor_vehicle|motorcar|oneway:conditional|access:conditional|vehicle:conditional|motor_vehicle:conditional|motorcar:conditional)$"~"."];'
            'out tags geom;')


def fetch_tile(lat, lon, index):
    failures = []
    for endpoint in ENDPOINTS:
        try:
            req = urllib.request.Request(
                endpoint,
                data=urllib.parse.urlencode({'data': query(lat, lon)}).encode('utf-8'),
                headers={'User-Agent': 'TokyoTaxiCockpitOSMResearch/0.2 (GitHub Actions; public OSM data)',
                         'Content-Type': 'application/x-www-form-urlencoded'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=26) as resp:
                payload = json.load(resp)
            if not isinstance(payload, dict) or not isinstance(payload.get('elements'), list):
                raise ValueError('No valid elements array in Overpass response')
            print(f'TILE {index}/9 OK: {len(payload["elements"])} ways; {endpoint}', flush=True)
            return payload['elements'], endpoint
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            reason = f'{endpoint}: {type(exc).__name__}: {exc}'
            failures.append(reason)
            print(f'TILE {index}/9 FAILED: {reason}', flush=True)
    raise RuntimeError(f'Tile {index}/9 failed at all endpoints: ' + '; '.join(failures))


def make_item(el):
    if el.get('type') != 'way':
        return None
    tags = el.get('tags') or {}
    coords = [[p['lat'], p['lon']] for p in el.get('geometry', []) if 'lat' in p and 'lon' in p]
    if len(coords) < 2:
        return None
    oneway = str(tags.get('oneway', '')).lower()
    direction = ('forward' if oneway in ('yes', '1', 'true') else
                 'reverse' if oneway == '-1' else 'unknown')
    fields = ('access', 'vehicle', 'motor_vehicle', 'motorcar',
              'oneway:conditional', 'access:conditional', 'vehicle:conditional',
              'motor_vehicle:conditional', 'motorcar:conditional')
    access = {k: tags[k] for k in fields if k in tags}
    if direction == 'unknown' and not access:
        return None
    return {'osm_type': 'way', 'osm_id': el['id'], 'name': tags.get('name', ''),
            'highway': tags.get('highway', ''), 'oneway': oneway,
            'direction': direction, 'access_tags': access, 'geometry': coords}


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    temp.replace(path)


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    coords = list(centers())
    completed = 0
    attempts = 0
    for i, (lat, lon) in enumerate(coords, 1):
        path = CACHE / f'tile_{i:02d}.json'
        if path.exists():
            try:
                saved = json.loads(path.read_text(encoding='utf-8'))
                if (saved.get('tile') == i and saved.get('lat') == round(lat, 7)
                        and saved.get('lon') == round(lon, 7)
                        and isinstance(saved.get('elements'), list)):
                    completed += 1
                    print(f'TILE {i}/9 CACHED: {len(saved["elements"])} ways', flush=True)
                    continue
            except (OSError, ValueError):
                pass
        if attempts >= MAX_NEW_TILES:
            continue
        attempts += 1
        try:
            elements, endpoint = fetch_tile(lat, lon, i)
        except Exception as exc:
            print(f'TILE {i}/9 PENDING: {exc}', flush=True)
            continue
        save_json(path, {'tile': i, 'lat': round(lat, 7), 'lon': round(lon, 7),
                         'endpoint': endpoint, 'elements': elements})
        completed += 1
    print(f'PROGRESS: {completed}/9 tiles cached. Attempted {attempts} new tiles.', flush=True)
    if completed != 9:
        print('INCOMPLETE: existing published JSON is unchanged. Run workflow again.', flush=True)
        return
    unique = {}
    endpoints_used = set()
    for i, (lat, lon) in enumerate(coords, 1):
        payload = json.loads((CACHE / f'tile_{i:02d}.json').read_text(encoding='utf-8'))
        if payload.get('tile') != i or payload.get('lat') != round(lat, 7) or payload.get('lon') != round(lon, 7):
            raise RuntimeError(f'Invalid tile {i}; existing JSON unchanged')
        endpoints_used.add(payload['endpoint'])
        for el in payload['elements']:
            item = make_item(el)
            if item:
                unique[item['osm_id']] = item
    if not unique:
        raise RuntimeError('No matching roads; existing JSON unchanged')
    items = [unique[k] for k in sorted(unique)]
    output = {
        'schema_version': 1,
        'source': 'OpenStreetMap via Overpass API',
        'fetched_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'endpoint': ', '.join(sorted(endpoints_used)),
        'center_lat': CENTER[0], 'center_lon': CENTER[1], 'radius_m': RADIUS,
        'count': len(items),
        'notice': ('OSM reference only; tags may be incomplete. Do not infer road-entry signs '
                   'or unrestricted travel from this dataset. 3x3 tile sampling near Tokyo Station.'),
        'roads': items,
    }
    save_json(OUT, output)
    print(f'COMPLETE: {len(items)} unique roads; output={OUT}', flush=True)


if __name__ == '__main__':
    main()
