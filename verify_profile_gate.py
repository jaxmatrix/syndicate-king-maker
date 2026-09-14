#!/usr/bin/env python3
"""Verify the queue path also refuses an incomplete profile."""
import json
import time
import urllib.request
import uuid

H = "http://helix:8080"
HDR = {"Host": "syndicate-app.jai.allr.work", "Content-Type": "application/json",
       "Accept": "application/json"}


def call(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{H}{path}", data=data, method=method, headers=HDR)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


tid = str(uuid.uuid4())
call("POST", "/api/research-runs", {
    "id": tid, "user_id": "gate@test", "company_name": "",
    "payload": json.dumps({
        "company_name": "", "business_type": "", "offering": "x",
        "target_city": "SF", "sample_customers": "",
        "lat": 37.7895, "lng": -122.3980, "radius_meters": 1500,
    }),
    "status": "pending",
    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
})
print("queued incomplete-profile request", tid[:8])

deadline = time.time() + 200
res = None
while time.time() < deadline:
    time.sleep(4)
    rows = call("GET", "/api/research-runs").get("data", [])
    for r in rows:
        if r.get("status") == f"done:{tid}" and r.get("result"):
            try:
                p = json.loads(r["result"])
            except Exception:
                continue
            if p.get("error") in ("profile_incomplete", "anchor_required"):
                res = p
                break
    if res:
        break

if not res:
    print("NO VERDICT - worker may not have picked it up")
    raise SystemExit(1)

print("status  :", res.get("status"))
print("error   :", res.get("error"))
print("message :", res.get("message"))
print("RESULT  :", "QUEUE PATH ALSO REFUSES INCOMPLETE PROFILE"
      if res.get("error") == "profile_incomplete" else "WRONG ERROR: " + str(res.get("error")))