"""Quick census of what's in the local DataHub graph."""
import json, urllib.request, yaml, os

TOKEN = (yaml.safe_load(open(os.path.expanduser("~/.datahubenv"))).get("gms") or {}).get("token") or ""
GQL = "http://localhost:8081/api/graphql"

TYPES = ["DATASET", "DASHBOARD", "CHART", "DATA_FLOW", "DATA_JOB",
         "MLMODEL", "MLMODEL_GROUP", "MLFEATURE", "MLFEATURE_TABLE",
         "MLPRIMARY_KEY", "CORP_USER", "TAG", "GLOSSARY_TERM", "CONTAINER"]

def q(query):
    req = urllib.request.Request(
        GQL,
        data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
    )
    return json.load(urllib.request.urlopen(req))

print("=== entity census ===")
for t in TYPES:
    query = f'{{ search(input: {{type: {t}, query: "*", start: 0, count: 0}}) {{ total }} }}'
    try:
        r = q(query)
        total = r.get("data", {}).get("search", {}).get("total")
        if total is None:
            total = f"(err: {json.dumps(r.get('errors',[])[:1])[:80]})"
        print(f"  {t:20s} {total}")
    except Exception as e:
        print(f"  {t:20s} EXC {e}")
