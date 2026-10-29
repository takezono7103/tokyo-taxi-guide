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
        endpoint = ENDPOINTS[i % len(ENDPOINTS)]
        try:
            request = urllib.request.Request(
                endpoint, data=urllib.parse.urlencode({'data': query}).encode(),
                headers={'User-Agent': 'TokyoTaxiCockpitDBBuilder/1.2 (OSM research)',
                         'Content-Type': 'application/x-www-form-urlencoded'})
            with urllib.request.urlopen(request, timeout=65) as response:
                payload = json.load(response)
            if not isinstance(payload.get('elements'), list):
                raise ValueError('No elements array')
            return payload['elements'], endpoint
        except Exception as exc:
            errors.append(f'{endpoint}: {exc}')
            time.sleep(2)
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


def fetch_tile(name, bbox, cache_key):
    cache_path = CACHE / f'{name}_{cache_key}.json'
    if cache_path.exists():
        saved = json.loads(cache_path.read_text(encoding='utf-8'))
        if isinstance(saved.get('elements'), list):
            return saved['elements'], saved.get('source', 'cache')
    elements, source = overpass(tile_query(name, bbox))
    cache_path.write_text(json.dumps({'source': source, 'bbox': bbox,
                                     'elements': elements}, ensure_ascii=False), encoding='utf-8')
    return elements, source


def split(bbox, divisions):
    s,w,n,e = bbox
    for row in range(divisions):
        for col in range(divisions):
            yield row, col, (s+(n-s)*row/divisions, w+(e-w)*col/divisions,
                             s+(n-s)*(row+1)/divisions, w+(e-w)*(col+1)/divisions)


def collect(name, records):
    bbox = municipality_bbox(name)
    failed = []
    successes = 0
    # 2x2 first, then subdivide only failed cells into 2x2 more (effective 4x4).
    for row, col, bounds in split(bbox, 2):
        key = f'grid2_{row}_{col}'
        try:
            elements, source = fetch_tile(name, bounds, key)
            successes += 1
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
                    for el in elements:
                        lat, lon = point(el)
                        if isinstance(lat,(int,float)) and isinstance(lon,(int,float)):
                            records[f'{el.get("type")}:{el.get("id")}'] = el
                    print(name, sub_key, 'fetched', len(elements), flush=True)
                except Exception as sub_exc:
                    failed.append({'tile': sub_key, 'bbox': sub_bounds,
                                   'error': str(sub_exc)[-300:]})
                    print(name, sub_key, 'failed', flush=True)
    return successes, failed


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
            successes, failures = collect(name, records)
            status[name] = {'status': 'fetched' if not failures else 'partial',
                            'successful_tiles': successes, 'failed_tiles': failures}
        except Exception as exc:
            status[name] = {'status': 'failed', 'error': str(exc)[-300:]}
        print(name, status[name]['status'], flush=True)
        # Preserve all completed tiles even when subsequent tiles fail.
        write_results('retry', selected, status, records)
    if any(v['status'] != 'fetched' for v in status.values()):
        sys.exit(2)

if __name__ == '__main__':
    main()
