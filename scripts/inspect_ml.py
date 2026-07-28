"""Inspect the ML model, features, datasets, and their lineage in local DataHub."""
import json
import os
import urllib.request

import yaml

TOKEN = (yaml.safe_load(open(os.path.expanduser("~/.datahubenv"))).get("gms") or {}).get("token") or ""
GQL = "http://localhost:8081/api/graphql"

def q(query):
    req = urllib.request.Request(
        GQL, data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    return json.load(urllib.request.urlopen(req))

def search_urns(t, count=50):
    r = q(f'{{ search(input: {{type: {t}, query: "*", start:0, count:{count}}}) {{ searchResults {{ entity {{ urn }} }} }} }}')
    return [x["entity"]["urn"] for x in r["data"]["search"]["searchResults"]]

print("=== DATASETS (raw tables) ===")
for urn in search_urns("DATASET"):
    print(" ", urn)

print("\n=== ML FEATURE TABLES ===")
for urn in search_urns("MLFEATURE_TABLE"):
    print(" ", urn)

print("\n=== ML MODEL(S) + lineage ===")
for urn in search_urns("MLMODEL"):
    print(" MODEL:", urn)
    # relationships: what feeds this model
    query = f'''{{ mlModel(urn: "{urn}") {{
        name
        description
        properties {{ mlFeatures groups {{ urn }} }}
        features: relationships(input: {{types:["Consumes","TrainedBy","DerivedFrom","UsedBy","MemberOf","Produces"], direction: OUTGOING, start:0, count:50}}) {{
          relationships {{ type entity {{ urn type }} }}
        }}
        upstream: relationships(input: {{types:["Consumes","TrainedBy","DerivedFrom"], direction: INCOMING, start:0, count:50}}) {{
          relationships {{ type entity {{ urn }} }}
        }}
    }} }}'''
    r = q(query)
    print(json.dumps(r.get("data", {}).get("mlModel", {}), indent=2)[:1500])

print("\n=== a DATASET's schema (first dataset) ===")
ds = search_urns("DATASET")[0]
query = f'''{{ dataset(urn: "{ds}") {{
    name
    schemaMetadata {{ fields {{ fieldPath type nativeDataType description }} }}
}} }}'''
r = q(query)
print(json.dumps(r.get("data", {}).get("dataset", {}), indent=2)[:2000])
