#!/usr/bin/env python3
"""Fetch real OSM restriction relations; never fabricate records or overwrite on failure."""
import json, os, pathlib, time, urllib.parse, urllib.request
from datetime import datetime, timezone

# Tokyo Station, approx. 500m bbox. Expand after validation.
S,W,N,E=35.676745,139.76159,35.685727,139.77266
query=f'[out:json][timeout:50];relation["type"="restriction"]({S},{W},{N},{E});out body geom;'
servers=['https://overpass.kumi.systems/api/interpreter','https://overpass-api.de/api/interpreter','https://overpass.private.coffee/api/interpreter']
errors=[]
for endpoint in servers:
    try:
        req=urllib.request.Request(endpoint,data=urllib.parse.urlencode({'data':query}).encode(),headers={'User-Agent':'TokyoTaxiCockpitRestrictionUpdater/0.1 (OSM attribution included)','Content-Type':'application/x-www-form-urlencoded'},method='POST')
        with urllib.request.urlopen(req,timeout=75) as resp:
            data=json.load(resp)
        elements=data.get('elements')
        if not isinstance(elements,list):raise ValueError('Missing elements array')
        relations=[r for r in elements if r.get('type')=='relation' and r.get('tags',{}).get('type')=='restriction' and isinstance(r.get('members'),list)]
        if not relations:raise ValueError('0 restrictions returned; refusing to overwrite existing file')
        located=sum(any(m.get('role')=='via' and (('lat' in m and 'lon' in m) or m.get('geometry')) for m in r['members']) for r in relations)
        if located==0:raise ValueError('No via coordinates; refusing to overwrite')
        output={'version':1,'source':'OpenStreetMap / Overpass API','license':'ODbL - © OpenStreetMap contributors','fetchedAt':datetime.now(timezone.utc).isoformat(),'area':'Tokyo Station approx 500m','bbox':[S,W,N,E],'resultCount':len(relations),'elements':relations}
        dest=pathlib.Path('data/tokyo_turn_restrictions.json');dest.parent.mkdir(parents=True,exist_ok=True)
        temp=dest.with_suffix('.json.tmp');temp.write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8');temp.replace(dest)
        print(f'OK: {len(relations)} relations; {located} located; endpoint={endpoint}; output={dest}')
        break
    except Exception as ex:
        errors.append(f'{endpoint}: {ex}')
        print('FAILED:',errors[-1],flush=True)
        time.sleep(2)
else:
    raise SystemExit('All servers failed; no file was changed.\n'+'\n'.join(errors))
