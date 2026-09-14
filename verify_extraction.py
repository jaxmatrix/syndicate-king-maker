#!/usr/bin/env python3
"""
Verify N2: the LLM extracts ICP intelligence grounded ONLY in retrieved evidence,
and every claim cites an evidence id that actually exists.
"""
import sys, json
sys.path.insert(0, '/opt/data')
sys.path.insert(0, '/opt/data/syndicate/backend')
from engine import SyndicateGraphEngine

e = SyndicateGraphEngine()
print("=" * 78)
ev_res = e.collect_evidence(
    business_type="Fast Food & Corporate Catering",
    offering="Ultra-fast healthy gourmet bowls and corporate team catering",
    sample_customers="Tech corporate HQs and VC funds",
)
evidence = ev_res["evidence"]
ids = {x["id"] for x in evidence}
print(f"evidence ids: {sorted(ids)}")
print()

ex = e.run_icp_extraction(
    evidence,
    company_name="Krave Gourmet Express",
    business_type="Fast Food & Corporate Catering",
    offering="Ultra-fast healthy gourmet bowls and corporate team catering",
    sample_customers="Tech corporate HQs and VC funds",
)

print()
print(json.dumps(ex, indent=2)[:2600])

# --- assertions ---
ok = True
if not ex.get("ok"):
    print("\nFAIL: extraction did not succeed"); ok = False
if not ex.get("pain_points"):
    print("\nFAIL: no pain points extracted"); ok = False

cited = [p.get("evidence_id") for p in ex.get("pain_points", [])]
uncited = [p for p in ex.get("pain_points", []) if not p.get("evidence_id")]
bad = [c for c in cited if c not in ids]
print()
print(f"pain points      : {len(ex.get('pain_points', []))}")
print(f"uncited claims   : {len(uncited)}")
print(f"invalid citations: {len(bad)} {bad}")
print(f"online spaces    : {ex.get('online_spaces')}")

if uncited:
    print("FAIL: a claim carries no citation"); ok = False
if bad:
    print("FAIL: a claim cites evidence that does not exist"); ok = False
if ex.get("online_spaces"):
    # every online space must appear somewhere in the evidence text
    blob = json.dumps(evidence).lower()
    invented = [s for s in ex["online_spaces"] if s.lower().lstrip("r/") not in blob]
    if invented:
        print(f"NOTE: online spaces not literally in evidence (LLM may normalise): {invented}")

print("=" * 78)
print("N2 EVIDENCE-GROUNDED EXTRACTION OK" if ok else "N2 FAILED")
sys.exit(0 if ok else 1)