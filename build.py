#!/usr/bin/env python3
"""Fetch OSM expressway candidates for Tokyo 23 wards + Mitaka/Musashino.
Research data only; NOT verified motorway entrances, exits, or driving directions.
No third-party dependencies. Output compatible with cockpit v6.14 import.
"""
import json, time, urllib.request, urllib.parse, datetime, math, pathlib, sys

NAMES = ['千代田区','中央区','港区','新宿区','文京区','台東区','墨田区','江東区','品川区','目黒区','大田区','世田谷区','渋谷区','中野区','杉並区','豊島区','北区','荒川区','板橋区','練馬区','足立区','葛飾区','江戸川区','三鷹市','武蔵野市']
ENDPOINTS = ['https://overpass.kumi.systems/api/interpreter','https://overpass.nchc.org.tw/api/interpreter','https://overpass-api.de/api/interpreter']
OUT = pathlib.Path('output'); OUT.mkdir(exist_ok=True)
CACHE = pathlib.Path('cache'); CACHE.mkdir(exist_ok=True)

def fetch(name):
    # Restrict by OSM administrative boundary area, not a guessed circle.
    query = ('[out:json][timeout:90];'
             f'area["name"="{name}"]["boundary"="administrative"]->.a;'
             '(node(area.a)["highway"="motorway_junction"];'
             'way(area.a)["highway"="motorway_link"]["name"];'
             'way(area.a)["highway"="motorway_link"]["ref"];);'
             'out center tags;')
    errors=[]
    for attempt in range(6):
        endpoint=ENDPOINTS[attempt%len(ENDPOINTS)]
        try:
            body=urllib.parse.urlencode({'data':query}).encode()
            req=urllib.request.Request(endpoint,data=body,headers={'User-Agent':'TokyoTaxiCockpitDBBuilder/1.0 (research; OSM attribution)','Content-Type':'application/x-www-form-urlencoded'})
            with urllib.request.urlopen(req,timeout=120) as res: data=json.load(res)
            if not isinstance(data.get('elements'),list):raise ValueError('No elements list')
            return data['elements'],endpoint
        except Exception as e:
            errors.append(str(e));time.sleep(min(3*(attempt+1),15))
    raise RuntimeError(' | '.join(errors[-3:]))

def point(el):
    if el.get('type')=='node':return (el.get('lat'),el.get('lon'))
    c=el.get('center') or {};return (c.get('lat'),c.get('lon'))

def main():
    status={}; all_records={}; source={}
    for name in NAMES:
        cache=CACHE/(name+'.json')
        try:
            if cache.exists():
                payload=json.loads(cache.read_text()); els=payload['elements']; endpoint=payload['source']
            else:
                els,endpoint=fetch(name)
                cache.write_text(json.dumps({'source':endpoint,'elements':els},ensure_ascii=False))
            for el in els:
                lat,lon=point(el)
                if isinstance(lat,(int,float)) and isinstance(lon,(int,float)):
                    all_records[f"{el.get('type')}:{el.get('id')}"]=el
            status[name]={'status':'fetched','raw_count':len(els),'source':endpoint}
        except Exception as e:
            status[name]={'status':'failed','error':str(e)[:300]}
        print(name,status[name]['status'],status[name].get('raw_count',''),flush=True)
    # Grid snapshots: every record assigned to a single 0.06-degree lat/lon tile;
    # 10km radius comfortably contains each tile. Original OSM IDs retained.
    tiles={}
    for el in all_records.values():
        lat,lon=point(el)
        iy=math.floor(lat/0.06);ix=math.floor(lon/0.06)
        tiles.setdefault((iy,ix),[]).append(el)
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    snapshots=[]
    for (iy,ix),els in sorted(tiles.items()):
        snapshots.append({'id':f'express-fullarea-20261029-{iy}-{ix}', 'kind':'express',
          'center':{'lat':(iy+0.5)*0.06,'lng':(ix+0.5)*0.06},'radius':10000,
          'createdAt':now,'elements':els})
    data={'format':'tokyo-taxi-geodata-v614','version':1,'exportedAt':now,'kind':'express','snapshots':snapshots}
    (OUT/'tokyo-express-25areas-import.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')))
    report={'generated_at':now,'target_areas':NAMES,'areas':status,'successful_areas':sum(v['status']=='fetched' for v in status.values()),'total_areas':25,'unique_osm_records':len(all_records),'snapshots':len(snapshots),'complete':all(v['status']=='fetched' for v in status.values()),'warning':'OSM candidates only. Access direction, ramp type and legality unverified. A fetched area may have zero matching records.'}
    (OUT/'coverage-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('DONE',report['successful_areas'],'/25',len(all_records),'records')
    if not report['complete']:sys.exit(2)
if __name__=='__main__':main()
