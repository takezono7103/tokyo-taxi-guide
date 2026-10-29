#!/usr/bin/env python3
"""Fetch only unresolved OSM candidate tiles. Does not certify road access."""
import json, os, pathlib, time, urllib.request, urllib.parse, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
INPUT=ROOT/'data/remaining-failed-tiles.json'
CACHE=ROOT/'cache/adachi_remaining'
OUT=ROOT/'output'
ENDPOINTS=['https://overpass.kumi.systems/api/interpreter','https://overpass-api.de/api/interpreter','https://overpass.private.coffee/api/interpreter']

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)

def query(b):
    s,w,n,e=b
    # BBOX-only: no costly global administrative-area resolution.
    return f'''[out:json][timeout:25];(node["highway"="motorway_junction"]({s},{w},{n},{e});way["highway"="motorway_link"]["name"]({s},{w},{n},{e});way["highway"="motorway_link"]["ref"]({s},{w},{n},{e}););out center tags;'''

def fetch(b):
    failures=[]
    for url in ENDPOINTS:
        try:
            req=urllib.request.Request(url,data=urllib.parse.urlencode({'data':query(b)}).encode(),headers={'User-Agent':'TokyoTaxiCockpit-OSMResearch/1.0','Content-Type':'application/x-www-form-urlencoded'})
            with urllib.request.urlopen(req,timeout=32) as r: payload=json.load(r)
            if not isinstance(payload.get('elements'),list):raise ValueError('missing elements')
            return payload['elements'],url
        except Exception as e:
            failures.append(f'{url}: {str(e)[:130]}')
    raise RuntimeError(' | '.join(failures))

def main():
    pending=json.loads(INPUT.read_text(encoding='utf-8'))
    records={}; remaining={}; results={}; fetched=0; cached=0
    for area,tiles in pending.items():
        remaining[area]=[]; results[area]={}
        for item in tiles:
            tile=item['tile']; bbox=item['bbox']; cache=CACHE/f'{area}_{tile}.json'
            try:
                if cache.exists():
                    data=json.loads(cache.read_text(encoding='utf-8'))
                    if data.get('bbox') != bbox or not isinstance(data.get('elements'),list):raise ValueError('invalid cache')
                    elements=data['elements']; source='cache'; cached+=1
                else:
                    elements,source=fetch(bbox)
                    save(cache,{'bbox':bbox,'elements':elements,'source':source});fetched+=1
                for el in elements:
                    if el.get('type') in ('node','way') and el.get('id') is not None:
                        records[f"{el['type']}:{el['id']}"]=el
                results[area][tile]={'status':'cached' if source=='cache' else 'fetched','count':len(elements)}
                print(area,tile,results[area][tile],flush=True)
            except Exception as e:
                remaining[area].append({'tile':tile,'bbox':bbox,'error':str(e)[-400:]})
                results[area][tile]={'status':'failed'}
                print(area,tile,'FAILED',str(e)[-150:],flush=True)
            # Save checkpoint even if next request fails or job is interrupted.
            save(OUT/'remaining-failed-tiles.json',remaining)
            save(OUT/'newly-fetched-osm-elements.json',{'elements':list(records.values()),'warning':'OSM candidates; not verified access or legal driving directions'})
            save(OUT/'retry-report.json',{'areas':results,'new_tiles':fetched,'cached_tiles':cached,'remaining_tiles':sum(map(len,remaining.values())),'complete':sum(map(len,remaining.values()))==0})
    print('SUMMARY',json.dumps({'new_tiles':fetched,'cached_tiles':cached,'remaining':sum(map(len,remaining.values()))}),flush=True)
    return 0 if not any(remaining.values()) else 2

if __name__=='__main__':sys.exit(main())
