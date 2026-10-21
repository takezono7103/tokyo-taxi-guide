"""Fetch Tokyo Metro station timetables and extract last departures by calendar/direction."""
import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

KEY = os.environ.get('ODPT_API_KEY')
if not KEY:
    raise SystemExit('ODPT_API_KEY is missing')

params = urllib.parse.urlencode({'odpt:operator': 'odpt.Operator:TokyoMetro', 'acl:consumerKey': KEY})
url = 'https://api.odpt.org/api/v4/odpt:StationTimetable?' + params
request = urllib.request.Request(url, headers={'User-Agent': 'tokyo-taxi-guide/1.0'})
with urllib.request.urlopen(request, timeout=90) as response:
    tables = json.load(response)
if not isinstance(tables, list) or not tables:
    raise SystemExit('No station timetable data returned; existing output retained')


def minutes(time):
    try:
        h, m = map(int, time.split(':')[:2])
        if not 0 <= m < 60 or not 0 <= h <= 29:
            return -1
        return h * 60 + m + (1440 if h < 4 else 0)
    except (ValueError, AttributeError):
        return -1


def station_name(identifier):
    if isinstance(identifier, list):
        return [station_name(x) for x in identifier]
    if not isinstance(identifier, str):
        return None
    return identifier.split('.')[-1]

rows = []
for table in tables:
    if not isinstance(table, dict):
        continue
    variants = []
    if isinstance(table.get('odpt:stationTimetableObject'), list):
        variants.append((table.get('odpt:calendar', 'unknown'), table['odpt:stationTimetableObject']))
    for field, label in [('odpt:weekdays', 'Weekday'), ('odpt:saturdays', 'Saturday'), ('odpt:holidays', 'Holiday')]:
        if isinstance(table.get(field), list):
            variants.append((label, table[field]))
    for calendar, entries in variants:
        valid = [e for e in entries if isinstance(e, dict) and minutes(e.get('odpt:departureTime')) >= 0]
        if not valid:
            continue
        # Prefer explicitly marked final departures when supplied; otherwise last scheduled departure.
        marked = [e for e in valid if e.get('odpt:isLast') is True]
        last = max(marked or valid, key=lambda e: minutes(e['odpt:departureTime']))
        rows.append({
            'station_id': table.get('odpt:station'),
            'station': station_name(table.get('odpt:station')),
            'railway_id': table.get('odpt:railway'),
            'direction_id': table.get('odpt:railDirection'),
            'calendar_id': calendar,
            'departure_time': last['odpt:departureTime'],
            'destination_station_id': last.get('odpt:destinationStation'),
            'destination': station_name(last.get('odpt:destinationStation')),
            'explicit_last': last.get('odpt:isLast') is True,
            'source_updated': table.get('dc:date'),
        })
if not rows:
    raise SystemExit('No valid last departures; existing output retained')

result = {
    'schema_version': 1,
    'operator': 'TokyoMetro',
    'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
    'note': 'Scheduled final departures, not live train positions or destination arrival times. Verify calendar and current timetable before use.',
    'timetable_count': len(tables),
    'last_departure_count': len(rows),
    'last_trains': sorted(rows, key=lambda r: (str(r['station_id']), str(r['calendar_id']), str(r['direction_id']))),
}
output = Path('data/last_trains.json')
output.parent.mkdir(parents=True, exist_ok=True)
temporary = output.with_suffix('.json.tmp')
temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
temporary.replace(output)
print(f"Station timetables: {len(tables)}; final departure records: {len(rows)}")
print('Saved data/last_trains.json')
