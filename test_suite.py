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

    def test_02_global_simulation(self):
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


if __name__ == "__main__":
    unittest.main()
