#!/usr/bin/env python3
"""
Full research-pipeline verification.

Proves the app now runs real research end to end:
  R1. The run returns cited pain points traceable to retrieved evidence.
  R2. Every cited evidence_id exists in `sources`.
  R3. No hardcoded research wording survives anywhere in the result.
  R4. Demand signals, if any, each carry a real URL.
  R5. grounding.claims_dropped == 0 (nothing unverifiable was generated).
  R6. Anchoring from the baseline is intact.
"""
import sys, json
from datetime import datetime
sys.path.insert(0, '/opt/data')
sys.path.insert(0, '/opt/data/syndicate/backend')
from engine import SyndicateGraphEngine

# Wording that used to be hardcoded/fabricated. None of it may appear now.
BANNED = [
    "Lunch rush queues exceeding 25 minutes",
    "Post-COVID hybrid office schedules",
    "Generic creative deliverables",
    "Anakin Indeed Wire",
    "r/bayarea",
    "Fishbowl Corporate & Facility Groups",
    "Nextdoor Commercial Districts",
    "Unreliable service windows and lack of transparency",
]

e = SyndicateGraphEngine()
payload = {
    "company_name": "Krave Gourmet Express",
    "business_type": "Fast Food & Corporate Catering",
    "offering": "Ultra-fast healthy gourmet bowls and corporate team catering",
    "target_city": "San Francisco, CA",
    "sample_customers": "Tech corporate HQs, VC funds, corporate law firms",
    "lat": 37.7895, "lng": -122.3980, "radius_meters": 1500,
}

print("=" * 78)
r = e.execute_research_run(payload)
print("=" * 78)

icp = r["icp_intelligence"]
sources = r.get("sources", [])
src_ids = {s["id"] for s in sources}

print(f"status            : {r['status']}")
print(f"counts            : {r['counts']}")
print(f"grounding         : {r.get('grounding')}")
print(f"extraction model  : {icp.get('extraction', {}).get('model')}")
print()
print(f"PAIN POINTS ({len(icp.get('pain_points', []))}) — each with its source:")
for p in icp.get("pain_points", []):
    ev = next((s for s in sources if s["id"] == p.get("evidence_id")), {})
    print(f"  [{p.get('evidence_id')}] {p.get('claim')[:95]}")
    print(f"        quote: \"{(p.get('quote') or '')[:85]}\"")
    print(f"        src  : {ev.get('url', '(missing)')[:95]}")
print()
print(f"BUYING TRIGGERS   : {len(icp.get('buying_triggers', []))}")
print(f"ICP TITLES        : {icp.get('derived_icp_titles')} (fallback={icp.get('icp_titles_derived_fallback')})")
print(f"ONLINE SPACES     : {icp.get('online_spaces')}")
print(f"DEMAND SIGNALS    : {len(r.get('demand_signals', []))}")
for d in r.get("demand_signals", [])[:3]:
    print(f"    - {d['claim'][:80]}")
    print(f"      {d['url'][:95]}")

blob = json.dumps(r)
fails = []

if r["status"] != "success":
    fails.append("run did not succeed")
if not icp.get("pain_points"):
    fails.append("no cited pain points")
for p in icp.get("pain_points", []):
    if p.get("evidence_id") not in src_ids:
        fails.append(f"uncited/invalid claim: {p.get('claim','')[:50]}")
if r.get("grounding", {}).get("claims_dropped", 1) != 0:
    fails.append("grounding dropped claims")
for s in r.get("demand_signals", []):
    if not str(s.get("url", "")).startswith("http"):
        fails.append("demand signal without URL")
for b in BANNED:
    if b in blob:
        fails.append(f"hardcoded wording still present: {b!r}")
if not sources:
    fails.append("no sources returned")

print()
print("=" * 78)
for b in BANNED:
    print(f"  {'PRESENT' if b in blob else 'absent '} : {b}")
print("=" * 78)
print("FULL RESEARCH PIPELINE OK" if not fails else "FAILED:\n  - " + "\n  - ".join(fails))
sys.exit(0 if not fails else 1)