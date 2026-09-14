#!/usr/bin/env python3
"""Ask the LIVE Mastra agent a research question through the Helix chat queue."""
import json, sys, time, uuid, urllib.request

HELIX = "http://helix:8080"
HDR = {"Host": "syndicate-app.jai.allr.work", "Content-Type": "application/json",
       "Accept": "application/json"}


def call(method, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{HELIX}/api/chat", data=data, method=method, headers=HDR)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


msg = sys.argv[1] if len(sys.argv) > 1 else (
    "Find real coworking spaces near 555 California Street, San Francisco, and tell me "
    "which single one you would pick as a first outlet and why. Cite your sources."
)
ctx = json.dumps({
    "anchor": {"lat": 37.7895, "lng": -122.3980},
    "business_type": "Fast Food & Corporate Catering",
    "icp_titles": ["Office Manager"],
    "hotspot": "Salesforce Tower Catchment",
    "note": "first scan already run; user wants to go further and find customers",
})

tid = str(uuid.uuid4())
created = call("POST", {
    "id": tid, "user_id": "live@test", "message": msg, "context": ctx,
    "status": "pending", "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
})
print("queued:", created.get("id"))

deadline = time.time() + 420
reply, calls = None, []
while time.time() < deadline:
    time.sleep(4)
    rows = call("GET").get("data", [])
    mine = [r for r in rows if r.get("status") == f"replied:{tid}"]
    mine.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    if mine and mine[0].get("reply"):
        reply = mine[0]["reply"]
        try:
            calls = json.loads(mine[0].get("tool_calls") or "[]")
        except Exception:
            calls = []
        break

print("=" * 78)
if not reply:
    print("TIMED OUT - no reply from the bridge")
    sys.exit(1)

print(f"TOOL CALLS ({len(calls)}):")
for c in calls:
    print(f"  - {c.get('tool')} {json.dumps(c.get('args', {}))[:110]}")
print("-" * 78)
print(reply[:2600])
print("=" * 78)
print("LIVE AGENT REPLIED" if calls else "AGENT REPLIED with no tool calls")
sys.exit(0)