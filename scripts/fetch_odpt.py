
import json
import os
import urllib.parse
import urllib.request

API_KEY = os.environ.get("ODPT_API_KEY")

if not API_KEY:
    raise RuntimeError("ODPT_API_KEY is not set")

params = urllib.parse.urlencode({
    "odpt:operator": "odpt.Operator:TokyoMetro",
    "acl:consumerKey": API_KEY,
})

url = (
    "https://api.odpt.org/api/v4/odpt:Railway?"
    + params
)

request = urllib.request.Request(url)

with urllib.request.urlopen(request, timeout=30) as response:
    data = json.load(response)

print("ODPT API connection successful")
print("Railway records:", len(data))
