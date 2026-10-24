#!/usr/bin/env python3
"""Tokyo 23 wards + Mitaka/Musashino OSM facility dataset builder.
Uses live Overpass data; does not fabricate records. Python stdlib only.
"""
import datetime as dt, json, os, pathlib, random, sys, time, urllib.parse, urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'data'; OUT.mkdir(exist_ok=True)
WARD_NAMES=['千代田区','中央区','港区','新宿区','文京区','台東区','墨田区','江東区','品川区','目黒区','大田区','世田谷区','渋谷区','中野区','杉並区','豊島区','北区','荒川区','板橋区','練馬区','足立区','葛飾区','江戸川区']
NAMES=WARD_NAMES+['三鷹市','武蔵野市']
ENDPOINTS=['https://overpass.kumi.systems/api/interpreter','https://overpass-api.de/api/interpreter','https://overpass.nchc.org.tw/api/interpreter']

# Query one exact administrative area at a time, rather than a bounding rectangle.
def query(name,kind):
    area=f'area["boundary"="administrative"]["admin_level"="7"]["name"="{name}"]->.a;'
    if kind=='station':
        selector='(nwr["railway"="station"](area.a);nwr["railway"="halt"](area.a);nwr["station"="subway"](area.a););'
    else:
        selector='(nwr["highway"="motorway_junction"](area.a););'
    return '[out:json][timeout:150];'+area+'(.a;);out count;'+selector+'out center tags;'

def fetch(q):
    body=urllib.parse.urlencode({'data':q}).encode()
    errors=[]
    for attempt in range(6):
        endpoint=ENDPOINTS[attempt%len(ENDPOINTS)]
        try:
            req=urllib.request.Request(endpoint,data=body,headers={'User-Agent':'TokyoTaxiGeodataBuilder/1.0 (OpenStreetMap attribution)','Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=190) as response:
                data=json.load(response)
            if not isinstance(data.get('elements'),list): raise ValueError('No elements array')
            return data
        except Exception as e:
            errors.append(f'{endpoint}: {e}')
            time.sleep(min(10*(attempt+1),45))
    raise RuntimeError('; '.join(errors))

def main():
    print('Fetching 25 municipalities x 2 kinds; can take several minutes.',flush=True)
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    errors=[]
    for kind in ('station','express'):
        merged={}; regions=[]
        for name in NAMES:
            print(kind,name,flush=True)
            try:
                data=fetch(query(name,kind))
                elements=data['elements']
                # The count result identifies the area query; zero matches is possible but not proof of completeness.
                area_count=[x for x in elements if x.get('type')=='count']
                if not area_count or not any(int(c.get('tags',{}).get('total',0)) > 0 for c in area_count): raise RuntimeError('Administrative area not resolved')
                records=[x for x in elements if x.get('type') in ('node','way','relation')]
                for x in records:
                    p=x if x.get('lat') is not None else x.get('center',{})
                    if p.get('lat') is None or p.get('lon') is None: continue
                    key=f"{x['type']}/{x['id']}"
                    if key not in merged:
                        merged[key]={'osm_id':key,'lat':p['lat'],'lon':p['lon'],'name':x.get('tags',{}).get('name',''), 'tags':x.get('tags',{}),'municipalities':[name]}
                    elif name not in merged[key]['municipalities']:
                        merged[key]['municipalities'].append(name)
                regions.append({'name':name,'fetched':len(records),'status':'ok'})
                time.sleep(2)
            except Exception as e:
                errors.append({'kind':kind,'municipality':name,'error':str(e)})
                regions.append({'name':name,'status':'failed','error':str(e)})
        payload={'format':'tokyo-taxi-region-geodata-v1','kind':kind,'createdAt':now,'source':'OpenStreetMap contributors / Overpass API','license':'ODbL 1.0','coverageComplete':all(r['status']=='ok' for r in regions),'regions':regions,'count':len(merged),'elements':list(merged.values())}
        path=OUT/f'tokyo_{kind}_all.json'
        path.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
        print('Saved',path,len(merged),'coverageComplete=',payload['coverageComplete'],flush=True)
    (OUT/'collection_errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2),encoding='utf-8')
    if errors:
        print('INCOMPLETE: inspect data/collection_errors.json and rerun',file=sys.stderr)
        sys.exit(1)

if __name__=='__main__':main()
