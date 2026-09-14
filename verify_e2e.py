#!/usr/bin/env python3
"""
End-to-end test through the REAL production path:
  client -> Helix POST /api/simulations (pending) -> worker.py daemon
         -> engine -> Helix row status 'done:<taskId>' -> client poll

Proves both fixes on the live stack:
  E1. Nothing is pre-baked: a fresh client must create its own task id and the
      row only gains a result after the worker runs it.
  E2. The client can only ever see ITS OWN task result.
  E3. Result pins are anchored: moving the anchor does not move shared pins.
  E4. Hotspot centres equal the centroid of their member sites.
"""
import json
import sys
import time
import uuid
import urllib.request

HELIX = "http://helix:8080"
APP_HOST = "syndicate-app.jai.allr.work"
SLUG = "syndicate-app"


def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{HELIX}{path}", data=data, method=method,
                               headers={"Host": APP_HOST, "Content-Type": "application/json",
                                        "Accept": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as resp:
        return json.loads(resp.read().decode())


def rows():
    d = req("GET", "/api/simulations")
    return d if isinstance(d, list) else d.get("data", [])


def submit(anchor_lat, anchor_lng, radius=2000, label="E2E"):
    task_id = str(uuid.uuid4())
    payload = {
        "company_name": f"{label} Ventures",
        "business_type": "Fast Food & Corporate Catering",
        "offering": "Healthy gourmet bowls and corporate catering",
        "target_city": "Target Coordinates",
        "sample_customers": "Tech corporate HQs, VC funds, corporate law firms",
        "lat": anchor_lat, "lng": anchor_lng, "radius_meters": radius,
    }
    created = req("POST", "/api/simulations", {
        "id": task_id,
        "user_id": "e2e@test",
        "company_name": payload["company_name"],
        "payload": json.dumps(payload),
        "status": "pending",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    return task_id, created


def await_result(task_id, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        for r in rows():
            if r.get("status") == f"done:{task_id}" and r.get("result"):
                return json.loads(r["result"])
    return None


failures = []


def check(cond, label, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"  [{detail}]" if detail else ""))
    if not cond:
        failures.append(label)


print("=" * 78)
pre = rows()
print(f"rows in table before test: {len(pre)}")

# ---- E1: a fresh task starts as pending with NO result ----
tid_a, created_a = submit(37.7895, -122.3980, label="E2E-A")
check(created_a.get("id") == tid_a, "E1a. Client owns the task id",
      f"{created_a.get('id')}")
check(created_a.get("status") == "pending" and not created_a.get("result"),
      "E1b. New task is pending with NO result pre-attached",
      f"status={created_a.get('status')} result={created_a.get('result')}")

res_a = await_result(tid_a)
check(res_a is not None, "E1c. Worker executed the task through the queue")
if not res_a:
    print("FATAL: no result. Is the worker running?")
    sys.exit(1)

# ---- E2: result belongs to THIS task and this anchor ----
check(res_a.get("anchor", {}).get("lat") == 37.7895 and
      res_a.get("anchor", {}).get("lng") == -122.3980,
      "E2a. Result carries back the exact anchor it was computed for",
      f"{res_a.get('anchor')}")
check(res_a.get("coordinate_source") == "google_places",
      "E2b. Result declares Google Places as coordinate source")
check(len(res_a.get("target_buildings", [])) > 0,
      "E2c. Real sites returned", f"{len(res_a.get('target_buildings', []))} sites")

ba = {b["id"]: b for b in res_a["target_buildings"]}

# ---- E3: the anchoring test on the live stack ----
tid_b, _ = submit(37.7930, -122.3990, label="E2E-B")
res_b = await_result(tid_b)
check(res_b is not None, "E3a. Second scan at a moved anchor completed")
if res_b:
    bb = {b["id"]: b for b in res_b["target_buildings"]}
    shared = set(ba) & set(bb)
    moved = [k for k in shared if ba[k]["lat"] != bb[k]["lat"] or ba[k]["lng"] != bb[k]["lng"]]
    print(f"INFO  anchor A={res_a['anchor']} sites={len(ba)} | anchor B={res_b['anchor']} sites={len(bb)}")
    check(len(shared) > 0, "E3b. Both scans share real sites", f"{len(shared)} shared")
    check(len(moved) == 0,
          "E3c. ANCHORED (live): moving the pin moved ZERO result pins",
          f"{len(moved)} moved of {len(shared)}")

    # offsets must not be synthetic constants
    offs = {round(abs(b["lat"] - 37.7895) + abs(b["lng"] + 122.3980), 7) for b in ba.values()}
    check(len(offs) == len(ba) and len(offs) > 1,
          "E3d. Anchor offsets are all distinct (no synthetic offset geometry)",
          f"{len(offs)} distinct of {len(ba)}")

# ---- E4: hotspot centroids ----
for hs in res_a.get("hotspot_recommendations", []):
    ids = [m["id"] for m in hs.get("surrounding_buildings", []) if m.get("id")]
    pts = [ba[i] for i in ids if i in ba]
    if not pts:
        continue
    clat = sum(p["lat"] for p in pts) / len(pts)
    clng = sum(p["lng"] for p in pts) / len(pts)
    ok = abs(clat - hs["center"]["lat"]) < 1e-6 and abs(clng - hs["center"]["lng"]) < 1e-6
    check(ok, f"E4. {hs['cluster_id']} centre == centroid of its {len(pts)} real sites",
          f"{hs['center']}")

# ---- E5: a bogus task id can never surface a result ----
boolcheck = await_result("no-such-task-" + uuid.uuid4().hex, timeout=6)
check(boolcheck is None,
      "E5. A task id with no completion can NEVER render a result (no fallback data)")

print("=" * 78)
if failures:
    print(f"FAILED ({len(failures)}): " + "; ".join(failures))
    sys.exit(1)
print("ALL END-TO-END CHECKS PASSED ON THE LIVE STACK")