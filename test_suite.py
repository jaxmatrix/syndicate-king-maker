import unittest
import urllib.request
import json
import os

class TestSyndicateEndpoints(unittest.TestCase):
    def test_01_backend_health(self):
        req = urllib.request.Request("http://127.0.0.1:8090/api/health")
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
            self.assertEqual(data.get("status"), "online")
            self.assertTrue(data.get("anakin_active"))

    def test_02_global_research(self):
        payload = {
            "company_name": "Test Enterprise",
            "business_type": "Commercial Facilities",
            "offering": "Cleaning and management",
            "target_city": "Tokyo, Japan",
            "sample_customers": "Offices in Chiyoda",
            "lat": 35.6762,
            "lng": 139.6503,
            "radius_meters": 2000
        }
        req = urllib.request.Request(
            "http://127.0.0.1:8090/api/research",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=240) as r:
            data = json.loads(r.read().decode())
            self.assertEqual(data.get("status"), "success")
            self.assertGreaterEqual(len(data.get("hotspot_recommendations", [])), 1)
            self.assertGreater(len(data.get("target_buildings", [])), 0)

    def test_03_chat_endpoint(self):
        payload = {
            "message": "Why was Hotspot 1 chosen?",
            "context": {"company_name": "Test Enterprise", "target_city": "Tokyo"}
        }
        req = urllib.request.Request(
            "http://127.0.0.1:8090/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            self.assertIn("reply", data)
            self.assertEqual(data.get("agent"), "Mastra Syndicate King Maker")

    def test_04_live_helix_frontend(self):
        req = urllib.request.Request("http://helix:8080/", headers={"Host": "syndicate-app.jai.allr.work"})
        with urllib.request.urlopen(req, timeout=10) as r:
            self.assertEqual(r.status, 200)
            html = r.read().decode("utf-8")
            self.assertIn("SYNDICATE", html)
            self.assertIn("KING MAKER", html)
            self.assertIn("map-surface", html)
            self.assertIn("tab-telemetry", html)
            self.assertIn("chat-input", html)

    def test_05_anchor_immutability(self):
        """
        Result pins must be anchored to real geography: moving the target pin
        must never translate a result that both scans share.
        """
        def run(lat, lng):
            payload = {
                "company_name": "Anchor Test",
                "business_type": "Fast Food & Corporate Catering",
                "offering": "Corporate catering",
                "target_city": "Target Coordinates",
                "sample_customers": "Tech corporate HQs",
                "lat": lat, "lng": lng, "radius_meters": 2000
            }
            req = urllib.request.Request(
                "http://127.0.0.1:8090/api/research",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=200) as r:
                return json.loads(r.read().decode())

        a = run(37.7895, -122.3980)
        b = run(37.7930, -122.3990)   # moved anchor

        self.assertEqual(a.get("anchor"), {"lat": 37.7895, "lng": -122.3980})
        self.assertEqual(a.get("coordinate_source"), "google_places")
        ba = {x["id"]: x for x in a.get("target_buildings", [])}
        bb = {x["id"]: x for x in b.get("target_buildings", [])}
        self.assertGreater(len(ba), 0)

        shared = set(ba) & set(bb)
        moved = [k for k in shared
                 if ba[k]["lat"] != bb[k]["lat"] or ba[k]["lng"] != bb[k]["lng"]]
        self.assertEqual(moved, [], f"{len(moved)} shared pins moved with the anchor")

        # Hotspot centres must be centroids of their real member sites.
        for hs in a.get("hotspot_recommendations", []):
            ids = [m["id"] for m in hs.get("surrounding_buildings", []) if m.get("id")]
            pts = [ba[i] for i in ids if i in ba]
            if not pts:
                continue
            clat = sum(p["lat"] for p in pts) / len(pts)
            clng = sum(p["lng"] for p in pts) / len(pts)
            self.assertAlmostEqual(hs["center"]["lat"], clat, places=6)
            self.assertAlmostEqual(hs["center"]["lng"], clng, places=6)

    def test_06_anchor_required(self):
        """A scan with no anchor must be refused, never fabricated."""
        payload = {
            "company_name": "No Anchor",
            "business_type": "Fast Food & Corporate Catering",
            "offering": "Corporate catering",
            "target_city": "Target Coordinates",
            "sample_customers": "Tech corporate HQs"
        }
        req = urllib.request.Request(
            "http://127.0.0.1:8090/api/research",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode())
        self.assertEqual(data.get("status"), "error")
        self.assertEqual(data.get("error"), "anchor_required")
        self.assertEqual(data.get("target_buildings"), [])
        self.assertEqual(data.get("hotspot_recommendations"), [])

    def test_07_live_frontend_has_no_generator(self):
        """The deployed client must not contain a client-side result generator."""
        req = urllib.request.Request("http://helix:8080/", headers={"Host": "syndicate-app.jai.allr.work"})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8")
        self.assertNotIn("generateClientSideSimulation", html)
        self.assertNotIn("Client-side fallback generator", html)
        self.assertIn("centroid-anchored", html)
        self.assertIn("IDLE", html)


    def test_08_no_hardcoded_research(self):
        """The engine must contain no hardcoded research wording or stubs."""
        path = "/opt/data/syndicate/backend/engine.py"
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        banned = [
            "Lunch rush queues exceeding 25 minutes",
            "Post-COVID hybrid office schedules",
            "Generic creative deliverables",
            "Unreliable service windows and lack of transparency",
            "Anakin Indeed Wire",
            "r/bayarea",
            "Fishbowl Corporate & Facility Groups",
            "Nextdoor Commercial Districts",
            "hiring_signals",
        ]
        for b in banned:
            self.assertNotIn(b, src, f"hardcoded research artefact still present: {b!r}")
        # The real research nodes must exist.
        for fn in ["collect_evidence", "run_icp_extraction",
                   "collect_demand_signals", "validate_grounding"]:
            self.assertIn(f"def {fn}", src, f"missing research node: {fn}")

    def test_09_evidence_grounding(self):
        """Every returned claim must cite an evidence id present in `sources`."""
        payload = {
            "company_name": "Grounding Test",
            "business_type": "Commercial Office Cleaning",
            "offering": "Nightly janitorial and facilities services",
            "target_city": "San Francisco, CA",
            "sample_customers": "Property managers and office towers",
            "lat": 37.7895, "lng": -122.3980, "radius_meters": 1200,
        }
        req = urllib.request.Request(
            "http://127.0.0.1:8090/api/research",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=280) as r:
            data = json.loads(r.read().decode())

        self.assertEqual(data.get("status"), "success")
        sources = data.get("sources", [])
        src_ids = {s.get("id") for s in sources}
        self.assertGreater(len(sources), 0, "no evidence retrieved")

        icp = data.get("icp_intelligence", {})
        for p in icp.get("pain_points", []):
            self.assertIn(p.get("evidence_id"), src_ids,
                          f"claim cites a non-existent evidence id: {p.get('claim')}")
            self.assertTrue(p.get("quote"), "claim has no supporting quote")
        for t in icp.get("buying_triggers", []):
            self.assertIn(t.get("evidence_id"), src_ids)

        # The validator must not have had to discard anything it generated.
        self.assertEqual(data.get("grounding", {}).get("claims_dropped"), 0)

    def test_10_demand_signals_carry_urls(self):
        """Any demand signal present must carry a real url (omitted otherwise)."""
        req = urllib.request.Request(
            "http://127.0.0.1:8090/api/research",
            data=json.dumps({
                "company_name": "Signal Test",
                "business_type": "Enterprise B2B SaaS",
                "offering": "Cloud infrastructure",
                "target_city": "San Francisco, CA",
                "sample_customers": "VP Engineering at Series B startups",
                "lat": 37.7895, "lng": -122.3980, "radius_meters": 1000,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=280) as r:
            data = json.loads(r.read().decode())
        for s in data.get("demand_signals", []):
            self.assertTrue(str(s.get("url", "")).startswith("http"),
                            f"demand signal without a url: {s}")

    def test_11_live_agent_chat(self):
        """The live Mastra agent must answer through the chat queue."""
        import time as _t
        import uuid as _u
        tid = str(_u.uuid4())
        body = {
            "id": tid, "user_id": "test@suite", "message":
                "Name one real coworking space within 500m of 37.7895,-122.3980 and give its coordinates.",
            "context": "{}", "status": "pending",
            "created_at": _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime()),
        }
        req = urllib.request.Request(
            "http://helix:8080/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Host": "syndicate-app.jai.allr.work", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            self.assertEqual(r.status, 201)

        deadline = _t.time() + 300
        reply = None
        while _t.time() < deadline:
            _t.sleep(5)
            get = urllib.request.Request(
                "http://helix:8080/api/chat",
                headers={"Host": "syndicate-app.jai.allr.work", "Accept": "application/json"},
            )
            with urllib.request.urlopen(get, timeout=20) as r:
                rows = json.loads(r.read().decode()).get("data", [])
            mine = [x for x in rows if x.get("status") == f"replied:{tid}"]
            if mine and mine[0].get("reply"):
                reply = mine[0]
                break

        self.assertIsNotNone(reply, "live agent did not reply (is the chat bridge running?)")
        self.assertGreater(len(reply.get("reply", "")), 40)
        self.assertGreater(len(json.loads(reply.get("tool_calls") or "[]")), 0,
                           "agent replied without calling any tools")


if __name__ == "__main__":
    unittest.main()
