#!/usr/bin/env python3
"""Make offline, source-attributed road tiles from a clipped OpenStreetMap PBF."""
import argparse, collections, datetime, json, math, pathlib
import osmium

P = argparse.ArgumentParser()
P.add_argument('pbf'); P.add_argument('--out', default='data')
a=P.parse_args(); dest=pathlib.Path(a.out);dest.mkdir(parents=True,exist_ok=True)
# Bounding box approximates 23 wards and adds some buffer; not municipal boundary polygon.
S,N,W,E = 35.49,35.85,139.54,139.96
step=.02
skip={'footway','path','cycleway','steps','pedestrian','service','bridleway','corridor','construction','proposed'}
tiles=collections.defaultdict(lambda:{'roads':[],'intersections':[]})
counts=collections.Counter()
def tk(lat,lon):
    return f'{int(math.floor((lat-S)/step))}_{int(math.floor((lon-W)/step))}'
def within(lat,lon):return S<=lat<=N and W<=lon<=E
class Extract(osmium.SimpleHandler):
 def node(self,n):
  if not n.location.valid():return
  lat,lon=n.location.lat,n.location.lon
  if not within(lat,lon):return
  name=n.tags.get('name:ja') or n.tags.get('name');high=n.tags.get('highway','')
  if name and (high in ('traffic_signals','crossing','mini_roundabout') or n.tags.get('junction')):
   tiles[tk(lat,lon)]['intersections'].append({'id':int(n.id),'name':name,'lat':round(lat,7),'lon':round(lon,7)})
   counts['named_nodes']+=1
 def way(self,w):
  name=w.tags.get('name:ja') or w.tags.get('name'); kind=w.tags.get('highway','')
  if not name or not kind or kind in skip:return
  points=[]
  for node in w.nodes:
   if node.location.valid():
    lat,lon=node.location.lat,node.location.lon
    points.append({'lat':round(lat,7),'lon':round(lon,7)})
  if len(points)<2:return
  if not any(within(pt['lat'],pt['lon']) for pt in points):return
  road={'id':int(w.id),'name':name,'geometry':points}
  keys=set()
  for p in points:
   if within(p['lat'],p['lon']): keys.add(tk(p['lat'],p['lon']))
  for key in keys:tiles[key]['roads'].append(road)
  counts['named_ways']+=1
Extract().apply_file(a.pbf,locations=True)
manifest={'source':'OpenStreetMap contributors / Geofabrik Kantō extract','license':'ODbL 1.0','generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bounds':[S,W,N,E],'step':step,'tiles':{},'counts':dict(counts)}
for key,record in tiles.items():
 if not record['roads'] and not record['intersections']:continue
 path=dest/f'{key}.json';path.write_text(json.dumps(record,ensure_ascii=False,separators=(',',':')))
 manifest['tiles'][key]={'roads':len(record['roads']),'intersections':len(record['intersections'])}
(dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')))
print('Wrote',len(manifest['tiles']),'tiles',dict(counts))
