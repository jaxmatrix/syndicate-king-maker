#!/usr/bin/env python3
"""
Verification: result pins must be geographically anchored.

Assertions:
  A1. Every returned coordinate is a real Google Places coordinate (not an offset).
  A2. Re-running the SAME anchor yields byte-identical coordinates (determinism).
  A3. Moving the anchor does NOT translate a result that both scans contain.
  A4. Hotspot centres are centroids of member buildings, not anchor offsets.
  A5. No anchor => no results (no fabricated fallback).
"""
import os
import sys
import json

sys.path.insert(0, '/opt/data')
sys.path.insert(0, '/opt/data/syndicate/backend')

from engine import SyndicateGraphEngine

BASE_PAYLOAD = {
    "company_name": "Krave Gourmet Express",
    "business_type": "Fast Food & Corporate Catering",
    "offering": "Ultra-fast healthy gourmet bowls and corporate catering.",
    "target_city": "Target Coordinates",
    "sample_customers": "Tech corporate HQs, VC funds, corporate law firms.",
}

ANCHOR_A = (37.7895, -122.3980)   # SF Financial District / SoMa
ANCHOR_B = (37.7930, -122.3990)   # ~400m north of A

failures = []
def check(cond, label, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"  [{detail}]" if detail else ""))
    if not cond:
        failures.append(label)

eng = SyndicateGraphEngine()
print(f"gmaps key present: {bool(eng.gmaps_key)}")
print("=" * 78)

# --- Run 1: anchor A ---
p = dict(BASE_PAYLOAD, lat=ANCHOR_A[0], lng=ANCHOR_A[1], radius_meters=2000)
r1 = eng.execute_syndicate_simulation(p)
b1 = {b["id"]: b for b in r1["target_buildings"]}
print(f"\nRun1 anchor={ANCHOR_A} buildings={len(b1)} touchpoints={len(r1['offline_touchpoints'])} hotspots={len(r1['hotspot_recommendations'])}")

# --- Run 2: SAME anchor A (determinism) ---
r2 = eng.execute_syndicate_simulation(p)
b2 = {b["id"]: b for b in r2["target_buildings"]}

check(len(b1) > 0, "A0. Real Places results returned", f"{len(b1)} buildings")

# A2: determinism of ANCHORING. The guarantee is: a given place_id always
# resolves to the same coordinate. (Google's nearby-search result SET has minor
# boundary jitter at the radius edge, so set drift is reported, not failed.)
shared_12 = set(b1) & set(b2)
mismatch_12 = [k for k in shared_12 if b1[k]["lat"] != b2[k]["lat"] or b1[k]["lng"] != b2[k]["lng"]]
drift = abs(len(set(b1)) - len(set(b2)))
check(len(shared_12) > 0, "A2a. Repeat run shares places", f"{len(shared_12)} shared")
check(len(mismatch_12) == 0,
      "A2b. Same anchor => same place always at the same coordinate (deterministic)",
      f"{len(mismatch_12)} mismatches")
print(f"INFO  A2c. Result-set drift between identical runs: {drift} place(s) "
      f"(Google ranking jitter at the radius edge)")

# A1: coordinates are real, not near-regular offsets from the anchor
offsets = [abs(b["lat"] - ANCHOR_A[0]) + abs(b["lng"] - ANCHOR_A[1]) for b in b1.values()]
rounded_offsets = [o for o in offsets if abs(o * 10000 - round(o * 10000)) < 1e-6 and o < 0.01]
check(len(offsets) > 1 and len(set(round(o, 7) for o in offsets)) > 1,
      "A1a. Offsets from anchor are varied (not synthetic constants)",
      f"{len(set(round(o,7) for o in offsets))} distinct")
check(len(rounded_offsets) == 0,
      "A1b. No coordinate sits on a round pin-relative offset", f"{len(rounded_offsets)} suspicious")

# --- Run 3: moved anchor B ---
p3 = dict(BASE_PAYLOAD, lat=ANCHOR_B[0], lng=ANCHOR_B[1], radius_meters=2000)
r3 = eng.execute_syndicate_simulation(p3)
b3 = {b["id"]: b for b in r3["target_buildings"]}
print(f"Run3 anchor={ANCHOR_B} buildings={len(b3)} hotspots={len(r3['hotspot_recommendations'])}")

# A3: THE ANCHORING TEST - shared places must not move when the pin moves
shared = set(b1) & set(b3)
moved = [k for k in shared if b1[k]["lat"] != b3[k]["lat"] or b1[k]["lng"] != b3[k]["lng"]]
check(len(shared) > 0, "A3a. Shared places exist across both anchors", f"{len(shared)} shared")
check(len(moved) == 0, "A3b. ANCHORED: moving the pin never moves a result pin",
      f"{len(moved)} moved of {len(shared)}")

# A4: hotspot centres are true centroids of their real member coordinates
for hs in r1["hotspot_recommendations"]:
    members = hs["surrounding_buildings"]
    ids = [m["id"] for m in members if m.get("id")]
    member_coords = [b1[i] for i in ids if i in b1]
    if not member_coords:
        continue
    clat = sum(m["lat"] for m in member_coords) / len(member_coords)
    clng = sum(m["lng"] for m in member_coords) / len(member_coords)
    ok = abs(clat - hs["center"]["lat"]) < 1e-5 and abs(clng - hs["center"]["lng"]) < 1e-5
    check(ok, f"A4. {hs['cluster_id']} centre is centroid of its {len(member_coords)} real members",
          f"{hs['center']}")
    check(hs.get("derivation") == "centroid of real Google Places coordinates",
          f"A4b. {hs['cluster_id']} declares real-coordinate derivation")
    # A4c: a centroid must not rest on a pin-relative offset
    doff = abs(hs["center"]["lat"] - ANCHOR_A[0]) + abs(hs["center"]["lng"] - ANCHOR_A[1])
    check(not (abs(doff * 10000 - round(doff * 10000)) < 1e-6 and doff < 0.01),
          f"A4c. {hs['cluster_id']} not on a pin-relative offset")

# A5: no anchor => no results
r5 = eng.execute_syndicate_simulation(dict(BASE_PAYLOAD))
check(r5["status"] == "error" and r5["target_buildings"] == []
      and r5["hotspot_recommendations"] == [],
      "A5. No anchor => zero fabricated results", f"status={r5['status']}")

print("=" * 78)
if failures:
    print(f"FAILED ({len(failures)}): " + "; ".join(failures))
    sys.exit(1)
print("ALL ANCHORING CHECKS PASSED")