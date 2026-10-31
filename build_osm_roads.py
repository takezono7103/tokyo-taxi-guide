import argparse,json,time,urllib.parse,urllib.request,sys
from pathlib import Path
P=argparse.ArgumentParser();P.add_argument('--lat',type=float,required=True);P.add_argument('--lon',type=float,required=True);P.add_argument('--radius',type=int,default=1000);P.add_argument('--output',default='osm_roads_test.geojson');a=P.parse_args()
if not 100<=a.radius<=1500: sys.exit('radius must be 100..1500')
if not 20<=a.lat<=46 or not 122<=a.lon<=154: sys.exit('Coordinates must be within Japan test bounds')
q=f'''[out:json][timeout:35];way(around:{a.radius},{a.lat},{a.lon})["highway"]["name"];out geom;'''
servers=['https://overpass.kumi.systems/api/interpreter','https://overpass.private.coffee/api/interpreter','https://overpass-api.de/api/interpreter']
result=None
for server in servers:
 try:
  req=urllib.request.Request(server,data=urllib.parse.urlencode({'data':q}).encode(),headers={'User-Agent':'TokyoTaxiCockpitRoadDBTest/1.0 (GitHub Actions)','Content-Type':'application/x-www-form-urlencoded'},method='POST')
  with urllib.request.urlopen(req,timeout=55) as r: result=json.load(r)
  if not isinstance(result.get('elements'),list): raise ValueError('No elements')
  print('Success:',server,'elements:',len(result['elements']));break
 except Exception as e: print('Failed:',server,type(e).__name__,str(e)[:160]);time.sleep(2)
if result is None: sys.exit('All Overpass endpoints failed; no file created')
features=[]
for x in result['elements']:
 tags=x.get('tags',{});points=x.get('geometry',[])
 if len(points)<2 or not tags.get('name'):continue
 coords=[[p['lon'],p['lat']] for p in points if 'lon' in p and 'lat' in p]
 if len(coords)<2:continue
 features.append({'type':'Feature','properties':{'name':tags['name'],'ref':tags.get('ref',''),'highway':tags.get('highway',''),'osm_id':x['id']},'geometry':{'type':'LineString','coordinates':coords}})
if not features:sys.exit('No named roads found; no file created')
output={'type':'FeatureCollection','features':features}
Path(a.output).write_text(json.dumps(output,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
print('Saved',a.output,'features',len(features))
