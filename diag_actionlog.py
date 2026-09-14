#!/usr/bin/env python3
"""Submit a scan and print the live action log, with timings."""
import json
import time
import urllib.request
import uuid

HELIX = "http://helix:8080"
HDR = {"Host": "syndicate-app.jai.allr.work", "Content-Type": "application/json",
       "Accept": "application/json"}


def call(method, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{HELIX}/api/research-runs", data=data, method=method, headers=HDR)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


payload = {
    "company_name": "Action Log Test",
    "business_type": "Fast Food & Corporate Catering",
    "offering": "Healthy grab-and-go bowls and corporate team catering",
    "target_city": "San Francisco, CA",
    "sample_customers": "Tech offices and law firms",
    "lat": 37.7895, "lng": -122.3980, "radius_meters": 1500,
}
tid = str(uuid.uuid4())
t0 = time.time()
call("POST", {
    "id": tid, "user_id": "actionlog@test", "company_name": payload["company_name"],
    "payload": json.dumps(payload), "status": "pending",
    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
})
print(f"queued {tid[:8]} at t=0.0s\n")

seen = set()
done = None
deadline = time.time() + 700
while time.time() < deadline:
    time.sleep(3)
    rows = call("GET").get("data", [])
    for r in rows:
        if r.get("status") == f"progress:{tid}" and r.get("result") not in seen:
            seen.add(r["result"])
            print(f"  t={time.time()-t0:6.1f}s  {r['result']}")
    mines = [r for r in rows if r.get("status") == f"done:{tid}"]
    mines.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    for r in mines:
        try:
            p = json.loads(r.get("result") or "{}")
        except Exception:
            continue
        if p.get("status") == "success":
            done = p
            break
    if done:
        break

elapsed = time.time() - t0
print()
if not done:
    print(f"NO RESULT after {elapsed:.0f}s")
    raise SystemExit(1)

c = done.get("counts", {})
print(f"COMPLETED in {elapsed:.0f}s")
print(f"  actions logged : {len(seen)}")
print(f"  counts         : {c}")
print(f"  grounding      : {done.get('grounding', {}).get('claims_kept')} kept / "
      f"{done.get('grounding', {}).get('claims_dropped')} dropped")
print(f"  within 10-min UI deadline: {'YES' if elapsed < 600 else 'NO'}")
