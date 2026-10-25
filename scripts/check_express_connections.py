#!/usr/bin/env python3
"""OSM road-way membership audit; NOT a routing or road-safety certification."""
import json, pathlib, urllib.parse, urllib.request, time
BASE=pathlib.Path(__file__).resolve().parent
SOURCE=BASE.parent/'data'/'tokyo_express_priority26_connection_audit.json'
OUTPUT=BASE.parent/'data'/'tokyo_express_priority26_way_evidence.json'
records=json.loads(SOURCE.read_text(encoding='utf-8'))['records']
results=[]
for index, rec in enumerate(records, 1):
    node_id=int(rec['osm_id'].split('/')[-1])
    query=f'[out:json][timeout:35];node({node_id})->.n;way(bn.n)[highway];out tags;'
    url='https://overpass.kumi.systems/api/interpreter'
    row={'osm_id':rec['osm_id'],'name':rec['name'],'osm_node_url':rec['osm_node_url'], 'query':query,'way_geometry_checked':False,'surface_road_checked':False,'turn_restrictions_checked':False,'navigation_enabled':False}
    try:
        request=urllib.request.Request(url,data=urllib.parse.urlencode({'data':query}).encode(),headers={'User-Agent':'TokyoTaxiCockpitResearch/1.0 (manual audit)'})
        with urllib.request.urlopen(request,timeout=55) as response: payload=json.load(response)
        ways=[{'id':w['id'],'tags':w.get('tags',{}),'url':f"https://www.openstreetmap.org/way/{w['id']}"} for w in payload.get('elements',[]) if w['type']=='way']
        row['adjacent_ways']=ways
        row['status']='way_tags_retrieved' if ways else 'no_adjacent_highway_ways_found'
        row['note']='同じOSMノードを共有する道路wayの属性のみ取得。道路の全形状・方向・交差点規制・通行可否は未検証。'
    except Exception as exc:
        row['status']='fetch_failed';row['error']=str(exc)[:250]
    results.append(row)
    print(f'{index}/{len(records)} {rec["name"]}: {row["status"]}',flush=True)
    time.sleep(1)
output={'format':'tokyo-express-priority26-way-evidence-v1','source':SOURCE.name,'method':'Overpass node -> parent highway ways; tags only','verified_road_connections':0,'safe_for_turn_by_turn_navigation':False,'records':results}
OUTPUT.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved:',OUTPUT)
