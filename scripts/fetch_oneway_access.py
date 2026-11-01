#!/usr/bin/env python3
"""Fetch OSM one-way and explicit vehicle access tags near Tokyo Station.
Research only: never infer permission to enter from missing OSM tags.
"""
import datetime
import math
import json
import sys
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

CENTER = (35.681236, 139.767125)
RADIUS = 850  # approximate study area; not Tokyo's 23 wards
# 3x3 overlapping smaller circles, to avoid one large Overpass query.
OFFSET_M = 380
TILE_RADIUS_M = 360
ENDPOINTS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
]
CACHE = pathlib.Path('data/oneway_access_tiles')
MAX_NEW_TILES = 1
SUBDIVISIONS = 2  # 2 x 2 smaller boxes per uncached parent tile
CURSOR = CACHE / "next_tile.json"
OUT = pathlib.Path('data/tokyo_oneway_access.json')


def centers():
    import math
    for y in (-1, 0, 1):
        for x in (-1, 0, 1):
            yield (CENTER[0] + y * OFFSET_M / 111_320,
                   CENTER[1] + x * OFFSET_M / (111_320 * math.cos(math.radians(CENTER[0]))))


def query(lat, lon, radius_m=TILE_RADIUS_M):
    # Bounding box is cheaper than a large around() spatial search.
    dy = radius_m / 111_320
    dx = radius_m / (111_320 * math.cos(math.radians(lat)))
    bbox = f"({lat-dy:.7f},{lon-dx:.7f},{lat+dy:.7f},{lon+dx:.7f})"
    # Query ways with the relevant tags. Never treat absence of a tag as permission.
    return (f'[out:json][timeout:14];('
            f'way[highway][oneway]{bbox};'
            f'way[highway][access]{bbox};'
            f'way[highway][vehicle]{bbox};'
            f'way[highway][motor_vehicle]{bbox};'
            f'way[highway][motorcar]{bbox};'
            f'way[highway]["oneway:conditional"]{bbox};'
            f'way[highway]["access:conditional"]{bbox};'
            f'way[highway]["vehicle:conditional"]{bbox};'
            f'way[highway]["motor_vehicle:conditional"]{bbox};'
            f'way[highway]["motorcar:conditional"]{bbox};'
            ');out tags geom;')


def fetch_tile(lat, lon, index, radius_m=TILE_RADIUS_M):
    failures = []
    for endpoint in ENDPOINTS:
        try:
            req = urllib.request.Request(
                endpoint,
                data=urllib.parse.urlencode({'data': query(lat, lon, radius_m)}).encode('utf-8'),
                headers={'User-Agent': 'TokyoTaxiCockpitOSMResearch/0.2 (GitHub Actions; public OSM data)',
                         'Content-Type': 'application/x-www-form-urlencoded'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.load(resp)
            if not isinstance(payload, dict) or not isinstance(payload.get('elements'), list):
                raise ValueError('No valid elements array in Overpass response')
            print(f'TILE {index} OK: {len(payload["elements"])} ways; {endpoint}', flush=True)
            return payload['elements'], endpoint
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            reason = f'{endpoint}: {type(exc).__name__}: {exc}'
            failures.append(reason)
            print(f'TILE {index} FAILED: {reason}', flush=True)
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


def subtiles(lat, lon):
    # Four equal boxes exactly cover the parent box. Parent cache remains valid.
    shift = TILE_RADIUS_M / 2
    radius = TILE_RADIUS_M / 2
    for dy_sign, dx_sign in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        sublat = lat + dy_sign * shift / 111_320
        sublon = lon + dx_sign * shift / (111_320 * math.cos(math.radians(lat)))
        yield sublat, sublon, radius


def valid_cache(path, tile, lat, lon, part=None):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if (data.get('tile') == tile and data.get('lat') == round(lat, 7)
                and data.get('lon') == round(lon, 7)
                and isinstance(data.get('elements'), list)
                and (part is None or data.get('part') == part)):
            return data
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return None


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    coords = list(centers())
    completed = 0
    attempts = 0
    # Persist a cursor so an unavailable first tile cannot starve the rest.
    try:
        start = int(json.loads(CURSOR.read_text(encoding='utf-8')).get('next', 1))
    except (OSError, ValueError, TypeError, AttributeError):
        start = 1
    start = max(1, min(9, start))
    # Process at most one new small tile per run, so progress is resumable.
    # A pre-existing complete tile_XX.json is never overwritten.
    for offset in range(9):
        i = (start - 1 + offset) % 9 + 1
        lat, lon = coords[i - 1]
        path = CACHE / f'tile_{i:02d}.json'
        parent = valid_cache(path, i, lat, lon)
        if parent:
            completed += 1
            print(f'TILE {i}/9 CACHED: {len(parent["elements"])} ways', flush=True)
            continue

        parts = list(subtiles(lat, lon))
        part_data = []
        for j, (slat, slon, radius) in enumerate(parts, 1):
            subpath = CACHE / f'tile_{i:02d}_part_{j:02d}.json'
            cached = valid_cache(subpath, i, slat, slon, j)
            if cached:
                part_data.append(cached)
                print(f'TILE {i}/9 PART {j}/4 CACHED: {len(cached["elements"])} ways', flush=True)
                continue
            if attempts >= MAX_NEW_TILES:
                continue
            attempts += 1
            try:
                elements, endpoint = fetch_tile(slat, slon, f'{i}/9 PART {j}/4', radius)
            except Exception as exc:
                print(f'TILE {i}/9 PART {j}/4 PENDING: {exc}', flush=True)
            else:
                cached = {'tile': i, 'part': j, 'lat': round(slat, 7),
                          'lon': round(slon, 7), 'endpoint': endpoint,
                          'elements': elements}
                save_json(subpath, cached)
                part_data.append(cached)
            # Advance to the next parent only once this parent is complete;
            # otherwise the same parent is revisited next run.
            save_json(CURSOR, {'next': i})

        if len(part_data) == 4:
            merged = {}
            for part in part_data:
                for element in part['elements']:
                    if element.get('type') == 'way' and 'id' in element:
                        merged[element['id']] = element
            endpoint_names = sorted({part['endpoint'] for part in part_data})
            save_json(path, {'tile': i, 'lat': round(lat, 7),
                             'lon': round(lon, 7),
                             'endpoint': ', '.join(endpoint_names),
                             'elements': list(merged.values())})
            completed += 1
            save_json(CURSOR, {'next': i % 9 + 1})
            print(f'TILE {i}/9 COMPLETE: {len(merged)} unique ways from 4 parts', flush=True)
        if attempts >= MAX_NEW_TILES:
            # Keep run short; still commit any new cached partial files.
            break
    # Recount all complete parents (including ones after the cursor).
    completed = sum(bool(valid_cache(CACHE / f'tile_{i:02d}.json', i, *coords[i-1]))
                    for i in range(1, 10))
    parts_cached = sum(1 for i, (lat, lon) in enumerate(coords, 1)
                       for j, (slat, slon, _) in enumerate(subtiles(lat, lon), 1)
                       if valid_cache(CACHE / f'tile_{i:02d}_part_{j:02d}.json', i, slat, slon, j))
    print(f'SUBTILE PROGRESS: {parts_cached} cached small parts; '
          f'{completed}/9 complete parent tiles.', flush=True)
    print(f'PROGRESS: {completed}/9 tiles cached. Attempted {attempts} new tiles.', flush=True)
    if completed != 9:
        print('INCOMPLETE: existing published JSON is unchanged.', flush=True)
        if completed == 0 and parts_cached == 0:
            print('ERROR: No cached OSM data and fetch failed.', flush=True)
            sys.exit(2)
        print('PARTIAL: saved tiles will be committed; rerun later for remaining tiles.', flush=True)
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
