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
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
    'https://overpass.nchc.org.tw/api/interpreter',
    'https://overpass-api.de/api/interpreter',
]
OUT = pathlib.Path('data/tokyo_oneway_access.json')


def centers():
    import math
    for y in (-1, 0, 1):
        for x in (-1, 0, 1):
            yield (CENTER[0] + y * OFFSET_M / 111_320,
                   CENTER[1] + x * OFFSET_M / (111_320 * math.cos(math.radians(CENTER[0]))))


def query(lat, lon):
    return (f'[out:json][timeout:35];'
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
            with urllib.request.urlopen(req, timeout=48) as resp:
                payload = json.load(resp)
            if not isinstance(payload, dict) or not isinstance(payload.get('elements'), list):
                raise ValueError('No valid elements array in Overpass response')
            print(f'TILE {index}/9 OK: {len(payload["elements"])} ways; {endpoint}', flush=True)
            return payload['elements'], endpoint
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            reason = f'{endpoint}: {type(exc).__name__}: {exc}'
            failures.append(reason)
            print(f'TILE {index}/9 FAILED: {reason}', flush=True)
            time.sleep(1)
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


def main():
    unique = {}
    endpoints_used = set()
    # If any tile fails, raise before writing; existing data stays intact.
    for i, (lat, lon) in enumerate(centers(), 1):
        elements, endpoint = fetch_tile(lat, lon, i)
        endpoints_used.add(endpoint)
        for el in elements:
            item = make_item(el)
            if item:
                unique[item['osm_id']] = item
    if not unique:
        raise RuntimeError('No matching roads; refusing to overwrite saved JSON')
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
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(output, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(OUT)
    print(f'OK: {len(items)} unique roads; one-way '
          f'{sum(x["direction"] != "unknown" for x in items)}; output={OUT}', flush=True)


if __name__ == '__main__':
    main()
