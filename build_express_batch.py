#!/usr/bin/env python3
"""Tokyo expressway OSM candidate collector, five areas per batch.
Research-only; ramp access, direction and legality are NOT verified.
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

NAMES = ['千代田区','中央区','港区','新宿区','文京区','台東区','墨田区','江東区','品川区','目黒区','大田区','世田谷区','渋谷区','中野区','杉並区','豊島区','北区','荒川区','板橋区','練馬区','足立区','葛飾区','江戸川区','三鷹市','武蔵野市']
ENDPOINTS = ['https://overpass.kumi.systems/api/interpreter','https://overpass.nchc.org.tw/api/interpreter','https://overpass-api.de/api/interpreter']
OUT = pathlib.Path('output')
CACHE = pathlib.Path('cache')

def fetch(name):
    query = ('[out:json][timeout:75];'
             f'area["name"="{name}"]["boundary"="administrative"]->.a;'
             '(node(area.a)["highway"="motorway_junction"];'
             'way(area.a)["highway"="motorway_link"]["name"];'
             'way(area.a)["highway"="motorway_link"]["ref"];);'
             'out center tags;')
    errors = []
    for attempt in range(3):
        endpoint = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            req = urllib.request.Request(endpoint,
                data=urllib.parse.urlencode({'data': query}).encode(),
                headers={'User-Agent': 'TokyoTaxiCockpitDBBuilder/1.1 (OSM research)',
                         'Content-Type': 'application/x-www-form-urlencoded'})
            with urllib.request.urlopen(req, timeout=100) as response:
                data = json.load(response)
            if not isinstance(data.get('elements'), list):
                raise ValueError('Missing elements array')
            return data['elements'], endpoint
        except Exception as exc:
            errors.append(str(exc))
            time.sleep(2)
    raise RuntimeError(' | '.join(errors)[-300:])

def point(element):
    if element.get('type') == 'node':
        return element.get('lat'), element.get('lon')
    center = element.get('center') or {}
    return center.get('lat'), center.get('lon')

def write_results(batch, selected, status, records):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tiles = {}
    for element in records.values():
        lat, lon = point(element)
        iy, ix = math.floor(lat / 0.06), math.floor(lon / 0.06)
        tiles.setdefault((iy, ix), []).append(element)
    snapshots = [
        {'id': f'express-fullarea-b{batch}-{iy}-{ix}', 'kind': 'express',
         'center': {'lat': (iy + .5) * .06, 'lng': (ix + .5) * .06},
         'radius': 10000, 'createdAt': now, 'elements': elements}
        for (iy, ix), elements in sorted(tiles.items())
    ]
    data = {'format': 'tokyo-taxi-geodata-v614', 'version': 1,
            'exportedAt': now, 'kind': 'express', 'snapshots': snapshots}
    report = {'generated_at': now, 'batch': batch, 'target_areas': selected,
              'areas': status,
              'successful_areas': sum(v['status'] == 'fetched' for v in status.values()),
              'total_areas': len(selected), 'unique_osm_records': len(records),
              'snapshots': len(snapshots),
              'complete': all(v['status'] == 'fetched' for v in status.values()),
              'warning': 'OSM candidates only; access direction and legality unverified.'}
    OUT.mkdir(exist_ok=True)
    (OUT / f'tokyo-express-batch-{batch}-import.json').write_text(
        json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    (OUT / f'coverage-report-batch-{batch}.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'SAVED batch {batch}: {report["successful_areas"]}/{len(selected)} areas; {len(records)} unique records', flush=True)
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', type=int, choices=range(1, 6), required=True)
    args = parser.parse_args()
    selected = NAMES[(args.batch - 1) * 5:args.batch * 5]
    CACHE.mkdir(exist_ok=True)
    status, records = {}, {}
    for name in selected:
        cache = CACHE / (name + '.json')
        try:
            if cache.exists():
                payload = json.loads(cache.read_text(encoding='utf-8'))
                elements, endpoint = payload['elements'], payload['source']
            else:
                elements, endpoint = fetch(name)
                cache.write_text(json.dumps({'source': endpoint, 'elements': elements}, ensure_ascii=False), encoding='utf-8')
            for element in elements:
                lat, lon = point(element)
                if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                    records[f'{element.get("type")}:{element.get("id")}'] = element
            status[name] = {'status': 'fetched', 'raw_count': len(elements), 'source': endpoint}
        except Exception as exc:
            status[name] = {'status': 'failed', 'error': str(exc)[:300]}
        print(name, status[name]['status'], status[name].get('raw_count', ''), flush=True)
        write_results(args.batch, selected, status, records)
    if not all(value['status'] == 'fetched' for value in status.values()):
        sys.exit(2)

if __name__ == '__main__':
    main()
