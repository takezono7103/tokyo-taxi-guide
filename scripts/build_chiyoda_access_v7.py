
#!/usr/bin/env python3
"""OSM PBFから千代田区一方通行データへ通行規制タグを追加するテスト"""
import json
import re
import sys
from pathlib import Path

try:
    import osmium
except ImportError:
    sys.exit("先に pip install osmium を実行してください")

if len(sys.argv) != 3:
    sys.exit("使い方: python build_chiyoda_access_v7.py v5.html input.osm.pbf")

html = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r"const DATA=(\{.*?\});const map=", html)

if not match:
    sys.exit("HTML内の道路データが見つかりません")

data = json.loads(match.group(1))
ids = {int(f["properties"]["osm_way_id"]) for f in data["features"]}

keys = [
    "access", "vehicle", "motor_vehicle", "motorcar",
    "taxi", "bus", "psv", "service",
    "access:conditional", "vehicle:conditional",
    "motor_vehicle:conditional", "motorcar:conditional",
    "taxi:conditional", "oneway:conditional",
    "oneway:taxi", "oneway:psv"
]

class Extract(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.tags = {}

    def way(self, way):
        if way.id in ids:
            self.tags[way.id] = {
                key: way.tags[key]
                for key in keys
                if key in way.tags
            }

extractor = Extract()
extractor.apply_file(sys.argv[2], locations=False)

for feature in data["features"]:
    props = feature["properties"]
    props.update(extractor.tags.get(int(props["osm_way_id"]), {}))

html = (
    html[:match.start(1)]
    + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    + html[match.end(1):]
)

html = html.replace(
    "車道優先テスト v5",
    "通行規制データ確認テスト v7"
)

html = html.replace(
    "施設アクセス道路も表示</label><span id=\"status\">",
    "施設アクセス道路も表示</label>"
    "<label><input type=\"checkbox\" id=\"accessOnly\">"
    "規制タグのある道路のみ</label><span id=\"status\">"
)

html = html.replace(
    "const visible=f=>",
    """const accessKeys=['access','vehicle','motor_vehicle','motorcar','taxi','bus','psv','service','access:conditional','vehicle:conditional','motor_vehicle:conditional','motorcar:conditional','taxi:conditional','oneway:conditional','oneway:taxi','oneway:psv'];
const hasAccess=p=>accessKeys.some(k=>p[k]!==undefined);
const accessVisible=p=>!document.getElementById('accessOnly').checked||hasAccess(p);
const accessText=p=>accessKeys.filter(k=>p[k]!==undefined).map(k=>k+'='+p[k]).join(' / ')||'規制タグ未収録';
const visible=f=>"""
)

html = html.replace(
    "if(!includeRoad(q)||(!motor&&isMotor(q))",
    "if(!includeRoad(q)||!accessVisible(q)||(!motor&&isMotor(q))"
)

html = html.replace(
    "if(!includeRoad(p))continue;",
    "if(!includeRoad(p)||!accessVisible(p))continue;"
)

html = html.replace(
    "+'<br>oneway: '+p.oneway).addTo(roads)",
    "+'<br>oneway: '+p.oneway+'<br>OSMタグ: '+accessText(p)+'<br>通行可否は未確認').addTo(roads)"
)

html = html.replace(
    "document.getElementById('service').onchange=draw;",
    "document.getElementById('service').onchange=draw;document.getElementById('accessOnly').onchange=draw;"
)

output = Path("chiyoda_oneway_v7_access_test.html")
output.write_text(html, encoding="utf-8")

print("対象道路:", len(ids))
print("PBFで照合できた道路:", len(extractor.tags))
print("出力:", output)

