#!/usr/bin/env python3
"""Verify N1 evidence retrieval returns REAL, citable evidence."""
import sys
sys.path.insert(0, '/opt/data')
sys.path.insert(0, '/opt/data/syndicate/backend')
from engine import SyndicateGraphEngine

e = SyndicateGraphEngine()
res = e.collect_evidence(
    business_type="Fast Food & Corporate Catering",
    offering="Ultra-fast healthy gourmet bowls and corporate team catering",
    sample_customers="Tech corporate HQs and VC funds",
)

ev = res["evidence"]
print("=" * 78)
print(f"evidence items : {len(ev)}")
print(f"counts         : {res['counts']}")
print(f"subreddits     : {res['subreddits']}")

real_urls = [x for x in ev if x["url"].startswith("http")]
reddit_urls = [x for x in ev if "reddit.com" in x["url"]]
print(f"http urls      : {len(real_urls)}")
print(f"reddit urls    : {len(reddit_urls)}")
print()
for x in ev[:6]:
    print(f"[{x['id']}] kind={x['kind']} src={x['source'][:45]!r}")
    print(f"      url  = {x['url'][:95]}")
    print(f"      quote= {x['quote'][:110]!r}")
    print()

ok = True
if not ev:
    print("FAIL: no evidence retrieved"); ok = False
if any(not x["url"].startswith("http") for x in ev):
    print("FAIL: an evidence item has no real URL"); ok = False
if any(not x.get("id") for x in ev):
    print("FAIL: an evidence item has no citable id"); ok = False
if any(not x["quote"].strip() for x in ev):
    print("FAIL: an evidence item has an empty quote"); ok = False
print("=" * 78)
print("N1 EVIDENCE RETRIEVAL OK" if ok else "N1 FAILED")
sys.exit(0 if ok else 1)