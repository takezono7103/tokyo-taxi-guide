#!/usr/bin/env python3
"""Retry Tokyo expressway OSM candidates with persistent successful tile cache.
Results are research candidates, NOT verified access points or legal directions.
"""
import argparse
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request
from build_express_batch import NAMES, CACHE, OUT, ENDPOINTS, point, write_results

FALLBACK_BBOX = {'足立区': [35.7200, 139.6900, 35.8500, 139.8900]}

def atomic_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)

def overpass(query, attempts=2):
    errors = []
    for i in range(attempts):
        endpoint = ENDPOINTS[i % len(ENDPOINTS)]
        try:
            req = urllib.request.Request(endpoint,
                data=urllib.parse.urlencode({'data': query}).encode(),
                headers={'User-Agent': 'TokyoTaxiCockpitDBBuilder/1.3 (OSM research)',
                         'Content-Type': 'application/x-www-form-urlencoded'})
            with urllib.request.urlopen(req, timeout=35) as resp:
                payload = json.load(resp)
            if not isinstance(payload.get('elements'), list):
                raise ValueError('Missing elements array')
            return payload['elements'], endpoint
        except Exception as exc:
            errors.append(f'{endpoint}: {exc}')
            time.sleep(1 + i)
    raise RuntimeError(' | '.join(errors)[-500:])

def municipality_bbox(name):
    q = ('[out:json][timeout:35];'
         f'relation["name"="{name}"]["boundary"="administrative"]'
         '(35.45,139.35,36.05,140.15);out bb;')
    elements, _ = overpass(q)
    boxes = [e['bounds'] for e in elements if e.get('type') == 'relation' and 'bounds' in e]
    if not boxes:
        raise RuntimeError('Municipality bbox not found')
    b = min(boxes, key=lambda x: (x['maxlat']-x['minlat'])*(x['maxlon']-x['minlon']))
    return [b['minlat'], b['minlon'], b['maxlat'], b['maxlon']]

def read_bbox(name):
    p = CACHE / f'{name}_bbox.json'
    if p.exists():
        try:
            b = json.loads(p.read_text(encoding='utf-8'))
            if len(b) == 4 and all(isinstance(x, (float, int)) for x in b):
                return b
        except (OSError, ValueError, TypeError):
            pass
    if name in FALLBACK_BBOX:
        b = FALLBACK_BBOX[name]
        print(name, 'fallback envelope (NOT verified boundary)', flush=True)
    else:
        b = municipality_bbox(name)
    atomic_json(p, b)
    return b

def tile_query(name, b):
    s,w,n,e = b
    return ('[out:json][timeout:45];'
            f'area["name"="{name}"]["boundary"="administrative"]->.a;'
            f'(node(area.a)({s:.6f},{w:.6f},{n:.6f},{e:.6f})["highway"="motorway_junction"];'
            f'way(area.a)({s:.6f},{w:.6f},{n:.6f},{e:.6f})["highway"="motorway_link"]["name"];'
            f'way(area.a)({s:.6f},{w:.6f},{n:.6f},{e:.6f})["highway"="motorway_link"]["ref"];);'
            'out center tags;')

def split(b):
    s,w,n,e = b
    mlat, mlon = (s+n)/2, (w+e)/2
    return [(0,0,[s,w,mlat,mlon]), (0,1,[s,mlon,mlat,e]),
            (1,0,[mlat,w,n,mlon]), (1,1,[mlat,mlon,n,e])]

def fetch(name, b, key):
    p = CACHE / f'{name}_{key}.json'
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data.get('elements'), list):
                return data['elements'], 'cache'
        except (OSError, ValueError, TypeError):
            print(name, key, 'invalid cache; refetching', flush=True)
    elements, source = overpass(tile_query(name, b))
    atomic_json(p, {'source': source, 'bbox': b, 'elements': elements})
    return elements, source

def collect(name, records, max_depth):
    root = read_bbox(name)
    failed, status = [], {}
    counts = {'cached': 0, 'fetched': 0}
    def visit(b, key, depth):
        try:
            elements, source = fetch(name, b, key)
            counts['cached' if source == 'cache' else 'fetched'] += 1
            status[key] = {'status': 'cached' if source == 'cache' else 'fetched',
                           'count': len(elements)}
            for el in elements:
                lat, lon = point(el)
                if isinstance(lat, (int,float)) and isinstance(lon, (int,float)):
                    records[f'{el.get("type")}:{el.get("id")}'] = el
            print(name, key, status[key]['status'], len(elements), flush=True)
        except Exception as exc:
            if depth < max_depth:
                print(name, key, 'failed; subdividing', str(exc)[-100:], flush=True)
                status[key] = {'status': 'subdivided'}
                for row, col, sub in split(b):
                    visit(sub, f'{key}_sub_{row}_{col}', depth+1)
            else:
                failed.append({'tile': key, 'bbox': b, 'error': str(exc)[-300:]})
                status[key] = {'status': 'failed', 'error': str(exc)[-200:]}
                print(name, key, 'FAILED (uncovered)', flush=True)
    for row, col, b in split(root):
        visit(b, f'grid2_{row}_{col}', 0)
    return counts, failed, status

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--areas', required=True)
    parser.add_argument('--max-depth', type=int, default=2, choices=[0,1,2,3],
                        help='Additional subdivisions after initial 2x2; default 2')
    args = parser.parse_args()
    selected = list(dict.fromkeys(x.strip() for x in args.areas.split(',') if x.strip()))
    if not selected or any(x not in NAMES for x in selected):
        parser.error('Specify supported municipality names')
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    records, statuses = {}, {}
    for name in selected:
        try:
            counts, failures, tiles = collect(name, records, args.max_depth)
            statuses[name] = {'status': 'partial' if failures else 'fetched',
                              'successful_tiles': sum(counts.values()),
                              'cached_tiles': counts['cached'],
                              'new_tiles': counts['fetched'],
                              'failed_tiles': failures, 'tiles': tiles}
        except Exception as exc:
            statuses[name] = {'status': 'failed', 'error': str(exc)[-300:],
                              'failed_tiles': []}
        print(name, statuses[name]['status'], flush=True)
        atomic_json(OUT / 'remaining-failed-tiles.json',
                    {k: v.get('failed_tiles', []) for k,v in statuses.items()
                     if v.get('failed_tiles')})
        write_results('retry', selected, statuses, records)
    print('SUMMARY', json.dumps({k: v['status'] for k,v in statuses.items()},
                                ensure_ascii=False), flush=True)
    if any(v['status'] != 'fetched' for v in statuses.values()):
        sys.exit(2)

if __name__ == '__main__':
    main()
