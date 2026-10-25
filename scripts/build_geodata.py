#!/usr/bin/env python3
"""Incremental OSM station and motorway junction collector for Tokyo 23 wards, Mitaka, Musashino."""
import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'data'
OUT.mkdir(parents=True, exist_ok=True)
NAMES = ['千代田区','中央区','港区','新宿区','文京区','台東区','墨田区','江東区','品川区','目黒区','大田区','世田谷区','渋谷区','中野区','杉並区','豊島区','北区','荒川区','板橋区','練馬区','足立区','葛飾区','江戸川区','三鷹市','武蔵野市']
ENDPOINTS = [
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass-api.de/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
]
RETRIES = 6
SOCKET_TIMEOUT = 75

def query(name, kind):
    # Tokyo wards are admin_level=7; cities may be admin_level=7 too. Check resolution explicitly.
    area = f'area["boundary"="administrative"]["name"="{name}"]["admin_level"="7"]->.a;'
    selector = '(nwr["railway"="station"](area.a);nwr["railway"="halt"](area.a);nwr["station"="subway"](area.a);)' if kind == 'station' else '(nwr["highway"="motorway_junction"](area.a);)'
    return '[out:json][timeout:45];' + area + '.a out count;' + selector + ';out center tags;'

def fetch(q, index):
    body = urllib.parse.urlencode({'data': q}).encode()
    problems = []
    for attempt in range(RETRIES):
        endpoint = ENDPOINTS[(index + attempt) % len(ENDPOINTS)]
        try:
            req = urllib.request.Request(endpoint, data=body, headers={'User-Agent': 'TokyoTaxiGeodataBuilder/2.0 (OpenStreetMap attribution)', 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=SOCKET_TIMEOUT) as response:
                result = json.load(response)
            if not isinstance(result.get('elements'), list):
                raise ValueError('Missing elements')
            return result
        except Exception as exc:
            problems.append(f'{endpoint}: {exc}')
            print('  retry/error:', problems[-1][:240], flush=True)
            time.sleep(min(8 * (attempt + 1), 30))
    raise RuntimeError(' | '.join(problems))

def read_old(kind):
    path = OUT / f'tokyo_{kind}_all.json'
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding='utf-8'))
            if old.get('kind') == kind and isinstance(old.get('regions'), list):
                return old
        except (OSError, ValueError):
            pass
    return {}

def save(kind, records, regions):
    ordered = [regions.get(n, {'name': n, 'status': 'pending'}) for n in NAMES]
    payload = {
        'format': 'tokyo-taxi-region-geodata-v1', 'kind': kind,
        'createdAt': dt.datetime.now(dt.timezone.utc).isoformat(),
        'source': 'OpenStreetMap contributors / Overpass API', 'license': 'ODbL 1.0',
        'coverageComplete': all(r['status'] == 'ok' for r in ordered),
        'regions': ordered, 'count': len(records), 'elements': list(records.values())
    }
    (OUT / f'tokyo_{kind}_all.json').write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return payload

def main():
    errors = []
    for kind in ('station', 'express'):
        old = read_old(kind)
        records = {e['osm_id']: e for e in old.get('elements', []) if 'osm_id' in e}
        regions = {r['name']: r for r in old.get('regions', []) if r.get('name') in NAMES}
        for i, name in enumerate(NAMES):
            if regions.get(name, {}).get('status') == 'ok':
                print('SKIP already saved', kind, name, flush=True)
                continue
            print('FETCH', kind, name, f'{i+1}/25', flush=True)
            try:
                result = fetch(query(name, kind), i)
                elements = result['elements']
                counts = [e for e in elements if e.get('type') == 'count']
                if not counts or not any(int(e.get('tags', {}).get('total', 0)) > 0 for e in counts):
                    raise RuntimeError('Administrative area unresolved')
                found = [e for e in elements if e.get('type') in ('node', 'way', 'relation')]
                for element in found:
                    pos = element if element.get('lat') is not None else element.get('center', {})
                    if pos.get('lat') is None or pos.get('lon') is None:
                        continue
                    key = f"{element['type']}/{element['id']}"
                    if key not in records:
                        records[key] = {'osm_id': key, 'lat': pos['lat'], 'lon': pos['lon'], 'name': element.get('tags', {}).get('name', ''), 'tags': element.get('tags', {}), 'municipalities': [name]}
                    elif name not in records[key]['municipalities']:
                        records[key]['municipalities'].append(name)
                regions[name] = {'name': name, 'fetched': len(found), 'status': 'ok'}
            except Exception as exc:
                message = str(exc)
                errors.append({'kind': kind, 'municipality': name, 'error': message})
                regions[name] = {'name': name, 'status': 'failed', 'error': message}
                print('FAILED', kind, name, message[:250], flush=True)
            save(kind, records, regions)
        print('SAVED', kind, 'records', len(records), flush=True)
    (OUT / 'collection_errors.json').write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Finished. Failed requests:', len(errors), flush=True)
    # Preserve partial results and error report so GitHub Actions can commit them.
    # coverageComplete remains false until all regions have succeeded.

if __name__ == '__main__':
    main()
