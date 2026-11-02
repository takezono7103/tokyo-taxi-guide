#!/usr/bin/env python3
"""Experimental 25-area OSM extraction. Bounding boxes are APPROXIMATE, not municipal borders.
No road access or route safety is verified. Outputs are candidates, not validated facilities.
"""
import argparse, collections, datetime, json, os
from pathlib import Path
import osmium

# [south, west, north, east] rough research bounds; overlaps are intentional.
BOXES = {
'千代田区':[35.670,139.729,35.706,139.782], '中央区':[35.645,139.755,35.699,139.805],
'港区':[35.625,139.709,35.682,139.782], '新宿区':[35.675,139.673,35.735,139.744],
'文京区':[35.695,139.718,35.735,139.775], '台東区':[35.697,139.759,35.735,139.815],
'墨田区':[35.680,139.790,35.741,139.850], '江東区':[35.590,139.775,35.719,139.854],
'品川区':[35.587,139.694,35.640,139.777], '目黒区':[35.598,139.663,35.650,139.717],
'大田区':[35.522,139.667,35.622,139.790], '世田谷区':[35.603,139.582,35.687,139.691],
'渋谷区':[35.641,139.660,35.693,139.729], '中野区':[35.683,139.623,35.730,139.683],
'杉並区':[35.672,139.580,35.733,139.654], '豊島区':[35.715,139.681,35.750,139.750],
'北区':[35.735,139.697,35.801,139.775], '荒川区':[35.726,139.756,35.766,139.824],
'板橋区':[35.741,139.624,35.807,139.726], '練馬区':[35.716,139.572,35.777,139.683],
'足立区':[35.745,139.757,35.820,139.855], '葛飾区':[35.725,139.817,35.794,139.903],
'江戸川区':[35.635,139.830,35.755,139.925], '三鷹市':[35.668,139.535,35.715,139.594],
'武蔵野市':[35.691,139.539,35.730,139.593]
}

def memberships(lat,lon):
    return [name for name,(s,w,n,e) in BOXES.items() if s<=lat<=n and w<=lon<=e]

def feature(geometry,props):
    return {'type':'Feature','geometry':geometry,'properties':props}

class Collect(osmium.SimpleHandler):
    def __init__(self, max_features):
        super().__init__(); self.max_features=max_features
        self.data={name:{'stations':[],'highway_candidates':[],'oneway_roads':[]} for name in BOXES}
        self.seen={name:collections.defaultdict(set) for name in BOXES}
        self.stats=collections.Counter()
    def add(self,area,kind,identifier,obj):
        if identifier in self.seen[area][kind]:return
        if len(self.data[area][kind])>=self.max_features:
            self.stats['truncated_'+kind]+=1;return
        self.seen[area][kind].add(identifier);self.data[area][kind].append(obj)
    def node(self,n):
        if not n.location.valid():return
        tags=n.tags
        station=(tags.get('railway') in ('station','halt') or tags.get('public_transport')=='station')
        ramp=(tags.get('highway')=='motorway_junction')
        if not (station or ramp):return
        lat,lon=n.location.lat,n.location.lon
        for area in memberships(lat,lon):
            props={'osm_type':'node','osm_id':str(n.id),'name':tags.get('name',''),
                   'source':'OSM PBF','verified':False,'position_basis':'OSM node'}
            if station:self.add(area,'stations',('n',n.id),feature({'type':'Point','coordinates':[lon,lat]},dict(props,railway=tags.get('railway',''))))
            if ramp:self.add(area,'highway_candidates',('n',n.id),feature({'type':'Point','coordinates':[lon,lat]},dict(props,kind='unclassified',highway='motorway_junction',ref=tags.get('ref',''))))
    def way(self,w):
        highway=w.tags.get('highway','')
        oneway=w.tags.get('oneway','')
        ramp=highway in ('motorway_link','trunk_link')
        is_oneway=oneway in ('yes','1','true','-1')
        if not ramp and not is_oneway:return
        try:
            coords=[[round(n.lon,7),round(n.lat,7)] for n in w.nodes]
        except osmium.InvalidLocationError:
            self.stats['invalid_location']+=1;return
        if len(coords)<2:return
        # Representative coordinate is a midpoint of the way vertices, not an entrance point.
        lat=sum(p[1] for p in coords)/len(coords);lon=sum(p[0] for p in coords)/len(coords)
        areas=memberships(lat,lon)
        if not areas:return
        props={'osm_type':'way','osm_way_id':str(w.id),'name':w.tags.get('name',''),
               'ref':w.tags.get('ref',''),'highway':highway,'oneway':oneway,
               'source':'OSM PBF','verified':False}
        for area in areas:
            if ramp:
                # No inference of entrance/exit from motorway_link alone.
                p=dict(props,kind='unclassified',position_basis='mean of OSM way vertices',
                       note='Not verified entrance or exit; do not navigate to this point')
                self.add(area,'highway_candidates',('w',w.id),feature({'type':'Point','coordinates':[round(lon,7),round(lat,7)]},p))
            if is_oneway:
                self.add(area,'oneway_roads',('w',w.id),feature({'type':'LineString','coordinates':coords},props))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pbf',default=os.environ.get('OSM_PBF','/tmp/kanto.osm.pbf'))
    parser.add_argument('--output',default='experimental/tokyo_25areas_pbf')
    parser.add_argument('--max-per-category',type=int,default=50000)
    args=parser.parse_args()
    pbf=Path(args.pbf)
    if not pbf.is_file() or pbf.stat().st_size==0:raise SystemExit('PBF file missing or empty: '+str(pbf))
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    h=Collect(args.max_per_category)
    h.apply_file(str(pbf),locations=True,idx='flex_mem')
    summary={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'region_method':'APPROXIMATE bounding boxes, overlapping; NOT municipal administrative boundaries',
       'safety':'OSM reference only; no taxi access, turn restrictions, ramp entrance/exit or conditional rules verified',
       'regions':{},'warnings':dict(h.stats)}
    for area,categories in h.data.items():
        for kind,items in categories.items():
            name=f'{area}_{kind}.geojson'
            (out/name).write_text(json.dumps({'type':'FeatureCollection','features':items},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
        summary['regions'][area]={kind:len(items) for kind,items in categories.items()}
    (out/'report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print('RESULT: regions=',len(summary['regions']),'stations=',sum(x['stations'] for x in summary['regions'].values()),'highway_candidates=',sum(x['highway_candidates'] for x in summary['regions'].values()),'oneway_roads=',sum(x['oneway_roads'] for x in summary['regions'].values()))
    if not any(sum(x.values()) for x in summary['regions'].values()):raise SystemExit('No data extracted; inspect PBF and region bounds')

if __name__=='__main__':main()
