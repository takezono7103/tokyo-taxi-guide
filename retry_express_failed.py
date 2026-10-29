#!/usr/bin/env python3
"""Retry selected OSM areas; preserve partial results and report failures."""
import argparse, datetime, json, pathlib, sys
from build_express_batch import NAMES, CACHE, OUT, fetch, point, write_results

p = argparse.ArgumentParser()
p.add_argument('--areas', required=True, help='Comma-separated municipality names')
a = p.parse_args()
selected = list(dict.fromkeys(x.strip() for x in a.areas.split(',') if x.strip()))
if not selected or any(x not in NAMES for x in selected):
    p.error('Provide municipality names from the supported 25 areas')
CACHE.mkdir(exist_ok=True)
status, records = {}, {}
for name in selected:
    try:
        cache = CACHE / (name + '.json')
        if cache.exists():
            payload = json.loads(cache.read_text(encoding='utf-8'))
            elements, endpoint = payload['elements'], payload['source']
        else:
            elements, endpoint = fetch(name)
            cache.write_text(json.dumps({'source': endpoint, 'elements': elements}, ensure_ascii=False), encoding='utf-8')
        for el in elements:
            lat, lon = point(el)
            if isinstance(lat, (int,float)) and isinstance(lon,(int,float)):
                records[f'{el.get("type")}:{el.get("id")}'] = el
        status[name] = {'status':'fetched','raw_count':len(elements),'source':endpoint}
    except Exception as exc:
        status[name] = {'status':'failed','error':str(exc)[:300]}
    print(name, status[name]['status'], status[name].get('raw_count',''), flush=True)
    write_results('retry', selected, status, records)
if any(v['status']=='failed' for v in status.values()):
    sys.exit(2)
