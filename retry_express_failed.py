#!/usr/bin/env python3
"""Retry selected Tokyo municipalities in smaller tiles; preserve successful tiles.
OSM candidates only. Access directions and legality remain unverified.
"""
import argparse
import datetime
import json
import math
import pathlib
import sys
import time
import urllib.parse
import urllib.request
from build_express_batch import NAMES, CACHE, OUT, ENDPOINTS, point, write_results


def overpass(query, attempts=3):
    errors = []
    for i in range(attempts):
        endpoint = ENDPOINTS[(i + 1) % len(ENDPOINTS)]
        try:
            request = urllib.request.Request(
                endpoint, data=urllib.parse.urlencode({'data': query}).encode(),
                headers={'User-Agent': 'TokyoTaxiCockpitDBBuilder/1.2 (OSM research)',
                         'Content-Type': 'application/x-www-form-urlencoded'})
            with urllib.request.urlopen(request, timeout=40) as response:
                payload = json.load(response)
            if not isinstance(payload.get('elements'), list):
                raise ValueError('No elements array')
            return payload['elements'], endpoint
        except Exception as exc:
            errors.append(f'{endpoint}: {exc}')
            time.sleep(1 + i)
    raise RuntimeError(' | '.join(errors)[-500:])


def municipality_bbox(name):
    # Resolve an administrative boundary. Restrict to Tokyo vicinity to avoid namesakes.
    query = ('[out:json][timeout:35];'
             f'relation["name"="{name}"]["boundary"="administrative"]'
             '(35.45,139.35,36.05,140.15);out bb;')
    elements, _ = overpass(query)
    boxes = [e['bounds'] for e in elements if e.get('type') == 'relation' and 'bounds' in e]
    if not boxes:
        raise RuntimeError('Municipality boundary bbox not found; no coverage assumed')
    # Smallest matching administrative boundary is generally the ward/city.
    b = min(boxes, key=lambda x: (x['maxlat']-x['minlat'])*(x['maxlon']-x['minlon']))
    return b['minlat'], b['minlon'], b['maxlat'], b['maxlon']


def tile_query(name, bbox):
    s,w,n,e = bbox
    return ('[out:json][timeout:45];'
            f'area["name"="{name}"]["boundary"="administrative"]->.a;'
            f'(node(area.a)({s:.6f},{w:.6f},{n:.6f},{e:.6f})["highway"="motorway_junction"];'
            f'way(area.a)({s:.6f},{w:.6f},{n:.6f},{e:.6f})["highway"="motorway_link"]["name"];'
            f'way(area.a)({s:.6f},{w:.6f},{n:.6f},{e:.6f})["highway"="motorway_link"]["ref"];);'
            'out center tags;')


def atomic_json(path, obj):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


# Conservative search envelope for Adachi; NOT a verified administrative boundary.
# Municipality area filter in tile_query excludes neighboring areas.
FALLBACK_BBOX = {'足立区': [35.7200, 139.6900, 35.8500, 139.8900]}


def read_cached_bbox(name):
    path = CACHE / f'{name}_bbox.json'
    if path.exists():
        try:
            b = json.loads(path.read_text(encoding='utf-8'))
            if len(b) == 4 and all(isinstance(x, (int, float)) for x in b):
                return b
        except (OSError, ValueError, TypeError):
            pass
    if name in FALLBACK_BBOX:
        b = FALLBACK_BBOX[name]
        print(name, 'using conservative fallback search envelope (not verified boundary)', flush=True)
    else:
        b = municipality_bbox(name)
    atomic_json(path, b)
    return b


def fetch_tile(name, bbox, cache_key):
    cache_path = CACHE / f'{name}_{cache_key}.json'
    if cache_path.exists():
        saved = json.loads(cache_path.read_text(encoding='utf-8'))
        if isinstance(saved.get('elements'), list):
            return saved['elements'], saved.get('source', 'cache')
    elements, source = overpass(tile_query(name, bbox))
    atomic_json(cache_path, {'source': source, 'bbox': bbox, 'elements': elements})
    return elements, source


def split(bbox, divisions):
    s,w,n,e = bbox
    for row in range(divisions):
        for col in range(divisions):
            yield row, col, (s+(n-s)*row/divisions, w+(e-w)*col/divisions,
                             s+(n-s)*(row+1)/divisions, w+(e-w)*(col+1)/divisions)


def collect(name, records):
    bbox = read_cached_bbox(name)
    failed = []
    successes = 0
    tile_status = {}
    # Start directly in 2x2 tiles, bypassing whole-ward fetch.
    # Successful tiles (including empty ones) are persisted and reused.
    # A failed tile is subdivided once more into 2x2.
    for row, col, bounds in split(bbox, 2):
        key = f'grid2_{row}_{col}'
        try:
            elements, source = fetch_tile(name, bounds, key)
            successes += 1
            tile_status[key] = {'status': 'fetched', 'count': len(elements)}
            for el in elements:
                lat, lon = point(el)
                if isinstance(lat,(int,float)) and isinstance(lon,(int,float)):
                    records[f'{el.get("type")}:{el.get("id")}'] = el
            print(name, key, 'fetched', len(elements), flush=True)
        except Exception as exc:
            print(name, key, 'failed; subdividing', str(exc)[-120:], flush=True)
            for sr, sc, sub_bounds in split(bounds, 2):
                sub_key = f'{key}_sub_{sr}_{sc}'
                try:
                    elements, source = fetch_tile(name, sub_bounds, sub_key)
                    successes += 1
                    tile_status[sub_key] = {'status': 'fetched', 'count': len(elements)}
                    for el in elements:
                        lat, lon = point(el)
                        if isinstance(lat,(int,float)) and isinstance(lon,(int,float)):
                            records[f'{el.get("type")}:{el.get("id")}'] = el
                    print(name, sub_key, 'fetched', len(elements), flush=True)
                except Exception as sub_exc:
                    failed.append({'tile': sub_key, 'bbox': sub_bounds,
                                   'error': str(sub_exc)[-300:]})
                    tile_status[sub_key] = {'status': 'failed', 'error': str(sub_exc)[-200:]}
                    print(name, sub_key, 'failed', flush=True)
    return successes, failed, tile_status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--areas', required=True, help='Comma-separated municipality names')
    args = parser.parse_args()
    selected = list(dict.fromkeys(x.strip() for x in args.areas.split(',') if x.strip()))
    if not selected or any(x not in NAMES for x in selected):
        parser.error('Specify municipality names from the supported 25 areas')
    CACHE.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    records, status = {}, {}
    for name in selected:
        try:
            successes, failures, tile_status = collect(name, records)
            status[name] = {'status': 'fetched' if not failures else 'partial',
                            'successful_tiles': successes, 'failed_tiles': failures, 'tiles': tile_status}
        except Exception as exc:
            status[name] = {'status': 'failed', 'error': str(exc)[-300:]}
        print(name, status[name]['status'], flush=True)
        atomic_json(OUT / 'remaining-failed-tiles.json', {k: v.get('failed_tiles', []) for k,v in status.items() if v.get('failed_tiles')})
        # Preserve all completed tiles even when subsequent tiles fail.
        write_results('retry', selected, status, records)
    if any(v['status'] != 'fetched' for v in status.values()):
        sys.exit(2)

if __name__ == '__main__':
    main()
