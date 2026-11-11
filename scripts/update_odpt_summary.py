#!/usr/bin/env python3
"""Fetch ODPT on GitHub Actions, publish only minimal sanitized summary.
Never print, commit or serialize the access token.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen, Request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'odpt_train_summary.json'
API = 'https://api.odpt.org/api/v4/odpt:TrainInformation'

def get_name(value, limit=70):
    if isinstance(value, dict):
        value = value.get('ja') or value.get('en') or ''
    if not isinstance(value, str):
        return ''
    return ' '.join(value.split())[:limit]

def sanitize(row):
    return dict(
        operator=get_name(row.get('odpt:operator'), 70).replace('odpt.Operator:', ''),
        railway=get_name(row.get('odpt:railway'), 70).replace('odpt.Railway:', ''),
        message=get_name(row.get('odpt:trainInformationText') or row.get('odpt:trainInformationStatus'), 200),
        sourceUpdated=get_name(row.get('dc:date'), 45),
        validUntil=get_name(row.get('dct:valid'), 45),
    )

def main():
    key = os.environ.get('ODPT_ACCESS_TOKEN', '').strip()
    if not key:
        raise SystemExit('ODPT_ACCESS_TOKEN is not set (add it as a GitHub Actions secret).')
    args=urlencode({'acl:consumerKey': key})
    request=Request(API + '?' + args, headers={'Accept':'application/json','User-Agent':'TokyoTaxiCockpit/0.4.4'})
    # Do not log exceptions here: the URL contains the access token.
    try:
        with urlopen(request, timeout=20) as response:
            if response.status!=200: raise ValueError('Non-200')
            raw=response.read(1024*1024 + 1)
            if len(raw)>1024*1024:raise ValueError('Too large')
        rows=json.loads(raw)
        if not isinstance(rows, list):raise ValueError('Unexpected response')
        entries=[sanitize(r) for r in rows[:150] if isinstance(r,dict)]
        now=datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
        payload={'schema':1,'ok':True,'fetchedAt':now,'provider':'ODPT TrainInformation',
                 'note':'Provider coverage is limited. An empty result does not imply normal operation.',
                 'entries':entries}
        OUT.parent.mkdir(exist_ok=True,parents=True)
        OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('ODPT summary updated, entries:',len(entries))
    except Exception:
        # No token-containing URL or exception is printed.
        raise SystemExit('ODPT data fetch failed. Check API access and permissions without sharing keys.')

if __name__=='__main__':
    main()
