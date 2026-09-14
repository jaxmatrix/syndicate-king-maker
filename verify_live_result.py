import json, urllib.request

req = urllib.request.Request("http://helix:8080/api/research-runs",
                             headers={"Host": "syndicate-app.jai.allr.work",
                                      "Accept": "application/json"})
with urllib.request.urlopen(req, timeout=20) as r:
    rows = json.loads(r.read().decode()).get("data", [])

done = [x for x in rows if str(x.get("status", "")).startswith("done:") and x.get("result")]
done.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
print("rows:", len(rows), "| completed:", len(done))

res = json.loads(done[0]["result"])
icp = res.get("icp_intelligence", {})
srcs = res.get("sources", [])
ids = {s["id"] for s in srcs}

print("\ncounts   :", res.get("counts"))
print("grounding:", res.get("grounding", {}).get("claims_kept"), "kept /",
      res.get("grounding", {}).get("claims_dropped"), "dropped")
print("model    :", icp.get("extraction", {}).get("model"))

print("\nCITED CLAIMS -> SOURCE URL")
bad = 0
for p in icp.get("pain_points", [])[:4]:
    ev = next((s for s in srcs if s["id"] == p.get("evidence_id")), None)
    ok = ev is not None
    bad += 0 if ok else 1
    print(f"  [{p.get('evidence_id')}] {p.get('claim','')[:78]}")
    print(f"       -> {ev['url'][:88] if ev else 'NO SOURCE (would be a bug)'}")

print("\ndemand signals:")
for d in res.get("demand_signals", [])[:3]:
    print(f"  - {d['claim'][:70]}")
    print(f"    {d['url'][:88]}")

print("\nRESULT:", "OK - all sampled claims have real sources" if bad == 0 else f"BUG: {bad} uncited")
