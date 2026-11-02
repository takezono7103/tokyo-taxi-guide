#!/usr/bin/env python3
"""Build ONE Tokyo municipal OSM reference JSON per run. Research data only.
No live traffic, legal road permission, or verified entrance locations implied.
"""
import argparse, json, pathlib, time, urllib.parse, urllib.request
AREAS = ['千代田区','中央区','港区','新宿区','文京区','台東区','墨田区','江東区','品川区','目黒区','大田区','世田谷区','渋谷区','中野区','杉並区','豊島区','北区','荒川区','板橋区','練馬区','足立区','葛飾区','江戸川区','三鷹市','武蔵野市']
ENDPOINTS=['https://overpass.kumi.systems/api/interpreter','https://overpass.private.coffee/api/interpreter','https://overpass-api.de/api/interpreter']
def fetch(q):
    data=urllib.parse.urlencode({'data':q}).encode()
    errors=[]
    for endpoint in ENDPOINTS:
        try:
            req=urllib.request.Request(endpoint,data=data,headers={'User-Agent':'TokyoTaxiOSMResearch/1.0 (manual GitHub Actions job)'})
            with urllib.request.urlopen(req,timeout=180) as r: return json.load(r)
        except Exception as e: errors.append(f'{endpoint}: {e}')
        time.sleep(2)
    raise RuntimeError('All Overpass endpoints failed: '+'; '.join(errors))
def main():
    p=argparse.ArgumentParser();p.add_argument('--area',required=True,choices=AREAS);p.add_argument('--out',default='data/areas');a=p.parse_args()
    # Search administrative relations directly. The previous area.tokyo query can
    # return zero because the Tokyo area resolution is not reliable across servers.
    query=f'''[out:json][timeout:160];relation["boundary"="administrative"]["admin_level"="8"]["name"="{a.area}"];out center tags;'''
    candidates=fetch(query).get('elements',[])
    # Only accept municipality relations with a representative point in Tokyo.
    # This is a sanity check, not an assertion of boundary/road accuracy.
    rels=[r for r in candidates if r.get('type')=='relation'
          and r.get('center') and 35.4 <= r['center']['lat'] <= 35.95
          and 139.25 <= r['center']['lon'] <= 140.1]
    if len(rels)!=1:
        raise RuntimeError(f'Expected exactly one Tokyo municipality named {a.area}; '
                           f'found {len(rels)} Tokyo candidates from {len(candidates)} relations. '
                           'No output written.')
    rel_id=rels[0]['id']; area_id=3600000000+rel_id
    q=f'''[out:json][timeout:180];area({area_id})->.target;(way(area.target)["highway"];node(area.target)["railway"~"^(station|halt|stop)$"];way(area.target)["railway"="station"];node(area.target)["highway"="motorway_junction"];);out center tags;'''
    elems=fetch(q).get('elements',[])
    roads=[];stations=[];facilities=[]
    for el in elems:
        tags=el.get('tags',{});kind=el['type'];coord={'lat':el.get('lat',el.get('center',{}).get('lat')),'lon':el.get('lon',el.get('center',{}).get('lon'))}
        if tags.get('highway') and kind=='way':
            roads.append({'osm_id':f'way/{el["id"]}','name':tags.get('name'),'highway':tags.get('highway'),'oneway':tags.get('oneway'),'access':tags.get('access'),'motor_vehicle':tags.get('motor_vehicle'),'motorcar':tags.get('motorcar'),'taxi':tags.get('taxi'),'bus':tags.get('bus'),'conditional':{k:v for k,v in tags.items() if 'conditional' in k},'reference_center':coord,'geometry_available':False})
            if tags.get('highway') in ('motorway_link','trunk_link') and tags.get('name'):
                facilities.append({'osm_id':f'way/{el["id"]}','name':tags['name'],'kind':'unclassified_candidate','reference_center':coord,'verification':'unverified'})
        if tags.get('railway') in ('station','halt','stop') and tags.get('name'):
            stations.append({'osm_id':f'{kind}/{el["id"]}','name':tags['name'],'reference_center':coord})
        if tags.get('highway')=='motorway_junction' and kind=='node':
            facilities.append({'osm_id':f'node/{el["id"]}','name':tags.get('name') or tags.get('ref'),'kind':'junction_candidate','reference_center':coord,'verification':'unverified'})
    obj={'schema':'tokyo-osm-reference-v1','area':a.area,'municipality_osm_relation':rel_id,'source':'OpenStreetMap via Overpass API','source_note':'OSM research only; geometry is not included; center coordinates are approximate; road permissions not verified','collected_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'counts':{'roads':len(roads),'stations':len(stations),'highway_candidates':len(facilities)},'roads':roads,'stations':stations,'highway_candidates':facilities}
    path=pathlib.Path(a.out)/(a.area+'.json');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Saved {path}: {obj["counts"]}')
if __name__=='__main__': main()
