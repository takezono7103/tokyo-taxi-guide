#!/usr/bin/env python3
"""Fetch OSM one-way and explicit vehicle access tags around Tokyo Station.
OSM data is advisory and not a substitute for posted traffic signs.
"""
import json, urllib.request, urllib.parse, datetime, pathlib, sys, time

CENTER=(35.681236,139.767125)
RADIUS=850
ENDPOINTS=['https://overpass.kumi.systems/api/interpreter','https://overpass-api.de/api/interpreter','https://overpass.nchc.org.tw/api/interpreter']
QUERY=f'''[out:json][timeout:65];
way(around:{RADIUS},{CENTER[0]},{CENTER[1]})[highway][~"^(oneway|access|vehicle|motor_vehicle|motorcar|oneway:conditional|access:conditional|vehicle:conditional|motor_vehicle:conditional|motorcar:conditional)$"~"."];
out tags geom;'''


def get_data():
    errors=[]
    for endpoint in ENDPOINTS:
        try:
            body=urllib.parse.urlencode({'data':QUERY}).encode()
            req=urllib.request.Request(endpoint,data=body,headers={'User-Agent':'TokyoTaxiCockpitOSMResearch/0.1 (GitHub Actions; public OSM data)','Content-Type':'application/x-www-form-urlencoded'})
            with urllib.request.urlopen(req,timeout=85) as response:
                data=json.load(response)
            if not isinstance(data.get('elements'),list):
                raise ValueError('missing elements')
            return data,endpoint
        except Exception as exc:
            errors.append(f'{endpoint}: {type(exc).__name__}: {exc}')
            print('FAILED:',errors[-1],flush=True)
            time.sleep(2)
    raise RuntimeError('All Overpass endpoints failed: '+'; '.join(errors))


def main():
    data,endpoint=get_data()
    items=[]
    for el in data['elements']:
        if el.get('type')!='way': continue
        tags=el.get('tags') or {}
        coords=[[p['lat'],p['lon']] for p in el.get('geometry',[]) if 'lat' in p and 'lon' in p]
        if len(coords)<2: continue
        oneway=tags.get('oneway','').lower()
        # Do not infer direction from highway=roundabout unless explicitly marked.
        direction='forward' if oneway in ('yes','1','true') else 'reverse' if oneway=='-1' else 'unknown'
        access={k:v for k,v in tags.items() if k in ('access','vehicle','motor_vehicle','motorcar','oneway:conditional','access:conditional','vehicle:conditional','motor_vehicle:conditional','motorcar:conditional')}
        if direction=='unknown' and not access: continue
        items.append({'osm_type':'way','osm_id':el['id'],'name':tags.get('name',''),
                      'highway':tags.get('highway',''),'oneway':oneway,'direction':direction,
                      'access_tags':access,'geometry':coords})
    if not items:
        raise RuntimeError('No matching roads; refusing to overwrite any saved JSON')
    output={'schema_version':1,'source':'OpenStreetMap via Overpass API',
            'fetched_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'endpoint':endpoint,'center_lat':CENTER[0],'center_lon':CENTER[1],
            'radius_m':RADIUS,'count':len(items),
            'notice':'OSM reference only; tags may be incomplete. Do not infer road-entry signs or unrestricted travel from this dataset.',
            'roads':items}
    path=pathlib.Path('data/tokyo_oneway_access.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(output,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(f'OK: {len(items)} roads; one-way {sum(x["direction"]!="unknown" for x in items)}; endpoint={endpoint}; output={path}')

if __name__=='__main__':
    main()
