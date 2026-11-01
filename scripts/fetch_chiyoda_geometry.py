#!/usr/bin/env python3
"""Read-only experimental OSM way geometry fetch. Does not change production files."""
import json, os, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

src = Path('data/chiyoda_oneway_merged_experimental.json')
outdir = Path('experimental/chiyoda_geometry')
outdir.mkdir(parents=True, exist_ok=True)
records = json.loads(src.read_text(encoding='utf-8'))['oneway_ways']
by_id = {int(x['osm_way_id']): x for x in records}
ids = sorted(by_id)
chunk_size = 40
batch = int(os.getenv('GEOM_BATCH', '0'))
start = batch * chunk_size
subset = ids[start:start+chunk_size]
if not subset:
 raise SystemExit(f'Invalid batch {batch}: total {len(ids)}, size {chunk_size}')
url = 'https://overpass.kumi.systems/api/interpreter'
query = '[out:json][timeout:90];way(id:' + ','.join(map(str, subset)) + ');out geom;'
result = None
for attempt in range(4):
 try:
  request = urllib.request.Request(url, data=urllib.parse.urlencode({'data':query}).encode(), headers={'User-Agent':'TokyoTaxiChiyodaGeometryExperimental/1.0 (GitHub Actions)', 'Accept':'application/json'})
  with urllib.request.urlopen(request, timeout=115) as response:
   result = json.load(response)
  break
 except (urllib.error.URLError, TimeoutError, ValueError) as e:
  print(f'Attempt {attempt+1}/4 failed: {e}', flush=True)
  if attempt < 3: time.sleep(15*(attempt+1))
if result is None: raise SystemExit('All attempts failed; no output written')
found = {}
for item in result.get('elements', []):
 if item.get('type') != 'way': continue
 ident = item.get('id')
 geom = item.get('geometry', [])
 if ident in by_id and len(geom) >= 2:
  found[ident] = {'osm_way_id':str(ident), 'oneway':by_id[ident]['oneway'], 'highway':by_id[ident].get('highway'), 'name':by_id[ident].get('name'), 'geometry':[[pt['lon'],pt['lat']] for pt in geom]}
missing = [str(x) for x in subset if x not in found]
payload = {'purpose':'EXPERIMENTAL VISUALIZATION ONLY - NOT FOR ROUTING','batch':batch,'requested':len(subset),'found':len(found),'missing_ids':missing,'features':list(found.values()),'osm_base_timestamp':result.get('osm3s',{}).get('timestamp_osm_base')}
file = outdir/f'geometry_batch_{batch:03d}.json'
file.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
print(f'BATCH {batch}; REQUESTED {len(subset)}; FOUND {len(found)}; MISSING {len(missing)}; OUTPUT {file}',flush=True)
if missing: print('Missing IDs:', ','.join(missing), flush=True)
