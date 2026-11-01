#!/usr/bin/env python3
"""Extract OSM way geometries from a local Kanto PBF; experimental, not for routing."""
import json, os, sys, datetime
from pathlib import Path
import osmium

SOURCE=Path('data/chiyoda_oneway_merged_experimental.json')
PBF=Path(os.environ.get('OSM_PBF','/tmp/kanto.osm.pbf'))
OUT=Path('experimental/chiyoda_pbf_geometry')
OUT.mkdir(parents=True,exist_ok=True)
index=json.loads(SOURCE.read_text(encoding='utf-8'))
ways=index['oneway_ways']
target={int(x['osm_way_id']):x for x in ways}
if len(target)!=len(ways):
    raise RuntimeError('Duplicate way IDs in input')

class Extract(osmium.SimpleHandler):
    def __init__(self):
        super().__init__(); self.found={};self.invalid=[]
    def way(self,w):
        if w.id not in target:return
        try:
            coords=[[round(n.lon,7),round(n.lat,7)] for n in w.nodes]
            if len(coords)<2:raise ValueError('fewer than 2 nodes')
            src=target[w.id]
            self.found[w.id]={'type':'Feature','geometry':{'type':'LineString','coordinates':coords},'properties':{'osm_way_id':str(w.id),'oneway':src.get('oneway'),'highway':src.get('highway'),'name':src.get('name'),'junction':src.get('junction'),'pbf_oneway':w.tags.get('oneway'),'pbf_highway':w.tags.get('highway'),'pbf_name':w.tags.get('name')}}
        except Exception as e:self.invalid.append({'osm_way_id':str(w.id),'error':str(e)})

if not PBF.is_file():raise FileNotFoundError(PBF)
h=Extract();h.apply_file(str(PBF),locations=True,idx='flex_mem')
features=[h.found[i] for i in sorted(h.found)]
missing=sorted(set(target)-set(h.found))
conflicts=[{'osm_way_id':str(i),'indexed':target[i].get('oneway'),'pbf':h.found[i]['properties']['pbf_oneway']} for i in sorted(h.found) if target[i].get('oneway') != h.found[i]['properties']['pbf_oneway']]
(OUT/'chiyoda_geometry_experimental.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
report={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'input_count':len(target),'found_count':len(features),'missing_count':len(missing),'missing_osm_way_ids':[str(i) for i in missing],'invalid':h.invalid,'oneway_attribute_differences':conflicts,'warning':'Experimental OSM geometry only. No turn restrictions, conditional rules, or routing safety verification. Source OSM snapshots may differ.'}
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(f"RESULT: extracted={len(features)} / {len(target)}; missing={len(missing)}; invalid={len(h.invalid)}; oneway_differences={len(conflicts)}")
if not features:sys.exit('No target geometries found; see report')
