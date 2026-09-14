"""Diagnose the Anakin key and time each MCP operation.

Confirms the key works, and measures per-call cost to locate the scan bottleneck.
Prints no secrets.
"""
import sys
import time

sys.path.insert(0, '/opt/data')
sys.path.insert(0, '/opt/data/syndicate/backend')
import engine  # loads .env (syndicate first, then shared)
import os
from anakin_client import AnakinMCPClient

key = os.environ.get("ANAKIN_API_KEY", "")
print("ANAKIN_API_KEY present:", bool(key), "| length:", len(key))

client = AnakinMCPClient()
print("client base_url:", getattr(client, "base_url", "n/a"))
print("client mcp_pkg  :", getattr(client, "mcp_package", getattr(client, "package", "n/a")))

print("\n--- 1. search (times a full subprocess round trip) ---")
t0 = time.time()
try:
    res = client.search("corporate catering complaints reddit", limit=3)
    n = len((res or {}).get("results") or [])
    print(f"  results: {n}  elapsed: {time.time() - t0:.1f}s")
    for r in ((res or {}).get("results") or [])[:2]:
        print("   -", str(r.get("title"))[:60])
        print("     ", str(r.get("url"))[:80])
except Exception as e:
    print(f"  FAILED after {time.time() - t0:.1f}s: {type(e).__name__}: {e}")

print("\n--- 2. second identical search (is anything cached?) ---")
t0 = time.time()
try:
    res = client.search("corporate catering complaints reddit", limit=3)
    n = len((res or {}).get("results") or [])
    print(f"  results: {n}  elapsed: {time.time() - t0:.1f}s")
except Exception as e:
    print(f"  FAILED after {time.time() - t0:.1f}s: {type(e).__name__}: {e}")

print("\n--- 3. reddit wire read ---")
t0 = time.time()
try:
    res = client.wire_read("rt_subreddit_posts", {"subreddit": "restaurantowners", "limit": 2})
    posts = (((res or {}).get("data") or {}).get("data") or {}).get("posts") or []
    print(f"  posts: {len(posts)}  elapsed: {time.time() - t0:.1f}s")
except Exception as e:
    print(f"  FAILED after {time.time() - t0:.1f}s: {type(e).__name__}: {e}")

print("\n--- 4. scrape a page ---")
t0 = time.time()
try:
    res = client.scrape("https://www.reddit.com/r/restaurantowners/comments/1c0efr1/corporate_catering")
    md = (res or {}).get("markdown") or ""
    print(f"  markdown chars: {len(md)}  elapsed: {time.time() - t0:.1f}s")
except Exception as e:
    print(f"  FAILED after {time.time() - t0:.1f}s: {type(e).__name__}: {e}")

print("\nDONE")
