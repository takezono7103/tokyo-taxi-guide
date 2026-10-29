#!/usr/bin/env python3
"""Retry unresolved OSM tiles in four quadrants; candidates are not verified access."""
import json, pathlib, sys, time, urllib.request, urllib.parse
ROOT=pathlib.Path(__file__).resolve().parents[1]
INPUT=ROOT/'data/remaining-failed-tiles.json'
CACHE=ROOT/'cache/adachi_remaining'
OUT=ROOT/'output'
ENDPOINTS=['https://overpass.kumi.systems/api/interpreter','https://overpass-api.de/api/interpreter','https://overpass.private.coffee/api/interpreter']

def save(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(path)

def query(b):
    s,w,n,e=b
    return f'''[out:json][timeout:25];(node["highway"="motorway_junction"]({s},{w},{n},{e});way["highway"="motorway_link"]["name"]({s},{w},{n},{e});way["highway"="motorway_link"]["ref"]({s},{w},{n},{e}););out center tags;'''

def fetch(b):
    failures=[]
    for url in ENDPOINTS:
        try:
            req=urllib.request.Request(url,data=urllib.parse.urlencode({'data':query(b)}).encode(),headers={'User-Agent':'TokyoTaxiCockpit-OSMResearch/1.0','Content-Type':'application/x-www-form-urlencoded'})
            with urllib.request.urlopen(req,timeout=32) as response: payload=json.load(response)
            if not isinstance(payload.get('elements'),list): raise ValueError('missing elements')
            return payload['elements'],url
        except Exception as exc:
            failures.append(f'{url}: {str(exc)[:130]}')
    raise RuntimeError(' | '.join(failures))

def quadrants(b):
    s,w,n,e=b; mlat=(s+n)/2; mlon=(w+e)/2
    return [[s,w,mlat,mlon],[s,mlon,mlat,e],[mlat,w,n,mlon],[mlat,mlon,n,e]]

def main():
    pending=json.loads(INPUT.read_text(encoding='utf-8'))
    remaining={area:[] for area in pending}; results={area:{} for area in pending}
    records={}; new=0; cached=0
    # Read previous output if present, to avoid dropping already collected elements.
    prior=OUT/'newly-fetched-osm-elements.json'
    if prior.exists():
        try:
            for el in json.loads(prior.read_text(encoding='utf-8')).get('elements',[]):
                if el.get('type') in ('node','way') and el.get('id') is not None:
                    records[f"{el['type']}:{el['id']}"]=el
        except (ValueError,OSError): pass
    def checkpoint():
        save(OUT/'remaining-failed-tiles.json',remaining)
        save(OUT/'newly-fetched-osm-elements.json',{'elements':list(records.values()),'warning':'OSM candidates; not verified access or legal driving directions'})
        save(OUT/'retry-report.json',{'areas':results,'new_subtiles':new,'cached_subtiles':cached,'remaining_subtiles':sum(map(len,remaining.values())),'complete':not any(remaining.values())})
    for area,tiles in pending.items():
        for item in tiles:
            tile=item['tile']; bbox=item['bbox']
            for i,subbox in enumerate(quadrants(bbox)):
                sub=f'{tile}_q{i}'; cache=CACHE/f'{area}_{sub}.json'
                try:
                    if cache.exists():
                        data=json.loads(cache.read_text(encoding='utf-8'))
                        if data.get('bbox')!=subbox or not isinstance(data.get('elements'),list): raise ValueError('invalid cache')
                        elements=data['elements']; source='cache'; cached+=1
                    else:
                        elements,source=fetch(subbox)
                        save(cache,{'bbox':subbox,'elements':elements,'source':source}); new+=1
                    for el in elements:
                        if el.get('type') in ('node','way') and el.get('id') is not None:
                            records[f"{el['type']}:{el['id']}"]=el
                    results[area][sub]={'status':'cached' if source=='cache' else 'fetched','count':len(elements)}
                    print(area,sub,results[area][sub],flush=True)
                except Exception as exc:
                    remaining[area].append({'tile':sub,'bbox':subbox,'error':str(exc)[-400:]})
                    results[area][sub]={'status':'failed'}
                    print(area,sub,'FAILED',str(exc)[-150:],flush=True)
                checkpoint()
    print('SUMMARY',json.dumps({'new_subtiles':new,'cached_subtiles':cached,'remaining':sum(map(len,remaining.values()))}),flush=True)
    return 0 if not any(remaining.values()) else 2

if __name__=='__main__': sys.exit(main())
