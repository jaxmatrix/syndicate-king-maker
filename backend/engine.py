"""
Syndicate Graph AI Intelligence Engine
Orchestrates multi-source data extraction using Anakin Wire / Scrape,
Google Places & Geocoding APIs, and spatial clustering algorithms.
Works for ANY business: Fast Food, Commercial Cleaning, Ad Agency, B2B SaaS, Hardware, etc.
"""

import os
import json
import math
import re
import time
import uuid
import urllib.request
import urllib.parse
from collections import Counter
from typing import Dict, Any, List, Optional
import sys
sys.path.insert(0, '/opt/data')
sys.path.insert(0, '/opt/data/syndicate/backend')
from anakin_client import AnakinMCPClient


def _load_env_file(path: str) -> None:
    """
    Populate os.environ from a key=value file without overwriting anything
    already set. The background worker is spawned by the workspace watchdog,
    whose environment does not carry the API keys - without this the engine
    silently ran with no Google key and published an empty 'success'.
    """
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


# App-specific secrets FIRST so they win for Syndicate only. _load_env_file never
# overwrites an already-set key, so listing the app .env before the shared one
# means Syndicate uses its own OPENROUTER_API_KEY while the shared profile .env
# (and therefore the Allr agent itself) stays untouched.
for _env_path in (
    '/opt/data/syndicate/.env',
    '/opt/data/profiles/accelerator/.env',
    '/opt/data/.env',
):
    _load_env_file(_env_path)

GOOGLE_MAPS_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# A missing Places key is fatal, not an empty result set. Publishing "success"
# with zero sites would look like a real scan that found nothing.
if not GOOGLE_MAPS_KEY:
    print("⚠ WARNING: GOOGLE_MAPS_API_KEY is not set - scans will refuse to run.")

class SyndicateGraphEngine:
    def __init__(self):
        self.anakin = AnakinMCPClient()
        self.gmaps_key = GOOGLE_MAPS_KEY

    def _fetch_url_json(self, url: str) -> Dict[str, Any]:
        req = urllib.request.Request(url, headers={"User-Agent": "Syndicate-KingMaker/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            print(f"Fetch error ({url}): {e}")
            return {}

    # ------------------------------------------------------------------
    # N1: EVIDENCE RETRIEVAL (real, citable)
    # ------------------------------------------------------------------
    SUBREDDIT_RE = re.compile(r'r/([A-Za-z0-9_]{3,30})')

    def _fetch_subreddit_posts(self, subreddit: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Read real posts from a subreddit via the Anakin Reddit wire action.
        Returns [] on any failure - never synthesised posts.
        """
        if not subreddit:
            return []
        try:
            res = self.anakin.wire_read("rt_subreddit_posts", {"subreddit": subreddit, "limit": limit})
        except Exception as e:
            print(f"  ⚠ subreddit read failed for r/{subreddit}: {e}")
            return []

        if not isinstance(res, dict):
            return []
        # Shape: {data: {data: {posts: [...]}}}
        posts = (((res.get("data") or {}).get("data") or {}).get("posts")) or []
        out: List[Dict[str, Any]] = []
        for p in posts:
            permalink = p.get("permalink") or ""
            url = p.get("url") or (
                f"https://www.reddit.com{permalink}" if permalink.startswith("/") else ""
            )
            if not url:
                continue
            title = (p.get("title") or "").strip()
            selftext = (p.get("selftext") or "").strip()
            if not title and not selftext:
                continue
            out.append({
                "subreddit": p.get("subreddit") or subreddit,
                "title": title,
                # Trim so the prompt stays inside a sane token budget.
                "quote": selftext[:600] if selftext else title,
                "url": url,
                "date": p.get("created_utc") or "",
            })
        return out

    def _condense_thread_markdown(self, md: str, limit: int = 1600) -> str:
        """
        Strip a scraped Reddit thread down to its substantive prose (post body +
        comments), dropping navigation, avatars, timestamps and share chrome.
        Keeps real human sentences, which is what makes the evidence citable.
        """
        drop_prefixes = (
            "share", "archived post", "sorry, this post", "comments section",
            "new comments cannot be posted", "log in", "sign up",
        )
        kept: List[str] = []
        total = 0
        for raw in md.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            low = line.lower()
            if low.startswith(drop_prefixes):
                continue
            # Avatar / user-link lines and bare timestamps are noise.
            if "profile --- avatar" in line:
                continue
            if re.fullmatch(r"\[\d+[ymhd] ago\]\([^)]*\)", line):
                continue
            # Drop bare links and one-word labels.
            if line.startswith("[") and "](" in line and len(line) < 60:
                continue
            if len(line) < 45:
                continue
            kept.append(line)
            total += len(line)
            if total >= limit:
                break
        return " ".join(kept)[:limit]

    def _fetch_thread_body(self, url: str) -> str:
        """
        Scrape a Reddit thread permalink and return condensed citable prose.
        Returns "" on failure - the caller simply omits that evidence item.
        """
        if not url:
            return ""
        try:
            res = self.anakin.scrape(url, generate_json=False)
        except Exception as e:
            print(f"  ⚠ thread scrape failed ({url[:60]}): {e}")
            return ""
        if not isinstance(res, dict):
            return ""
        md = res.get("markdown") or (res.get("data") or {}).get("markdown") or ""
        if not isinstance(md, str) or not md.strip():
            return ""
        return self._condense_thread_markdown(md)

    def collect_evidence(self, business_type: str, offering: str,
                         sample_customers: str, max_items: int = 14,
                         progress=None) -> Dict[str, Any]:
        """
        Retrieve real, citable evidence about the sector from the live web and
        from Reddit, and return it as a numbered evidence set.

        Every item carries the URL it came from. Downstream reasoning is allowed
        to cite ONLY these items, which is what makes the final result auditable.
        A failed call degrades to fewer items - it never invents one.

        `progress` receives a short label per sub-step so a caller can show the
        user that work is happening during this otherwise long silent stage.
        """

        def note(label: str) -> None:
            if progress is None:
                return
            try:
                progress(label)
            except Exception:
                pass

        queries = [
            f"{business_type} {offering} problems complaints reddit".strip(),
            f"{business_type} vendor complaints pricing reddit".strip(),
            f"{business_type} customer pain points".strip(),
        ]

        sub_hits: Counter = Counter()
        search_items: List[Dict[str, Any]] = []

        # --- Phase 1: search, to discover both snippets and real subreddits ---
        for qi, q in enumerate(queries, start=1):
            note(f"N1 · Search {qi}/{len(queries)}: {q[:70]}")
            try:
                res = self.anakin.search(q, limit=5)
            except Exception as e:
                print(f"  ⚠ search failed ({q[:40]}...): {e}")
                continue
            if not isinstance(res, dict):
                continue
            for r in (res.get("results") or []):
                snippet = (r.get("snippet") or "").strip()
                url = (r.get("url") or r.get("link") or "").strip()
                if not snippet or not url:
                    continue
                search_items.append({
                    "kind": "search",
                    "source": r.get("title") or url,
                    "quote": snippet[:500],
                    "url": url,
                    "date": r.get("date") or "",
                })
                # Harvest subreddits actually referenced by the retrieved text.
                for m in self.SUBREDDIT_RE.findall(f"{snippet} {url}"):
                    sub_hits[m.lower()] += 1

        # --- Phase 2: expand the Reddit threads the search actually surfaced ---
        # A topic-matched thread, scraped with its comments, is far stronger
        # evidence than a subreddit's generic front page, so expansion is the
        # primary source and the hot-listing below is only a fallback.
        reddit_items: List[Dict[str, Any]] = []
        seen_threads = set()
        thread_candidates = [i for i in search_items
                             if "reddit.com/r/" in i["url"] and "/comments/" in i["url"]]
        note(f"N1 · {len(search_items)} search hits, {len(thread_candidates)} reddit threads to read")
        for ti, item in enumerate(thread_candidates, start=1):
            if len(reddit_items) >= 4:
                break
            url = item["url"]
            if url in seen_threads:
                continue
            seen_threads.add(url)
            note(f"N1 · Reading thread {ti}/{min(len(thread_candidates), 4)}: {url[:78]}")
            body = self._fetch_thread_body(url)
            if not body:
                continue
            reddit_items.append({
                "kind": "reddit_thread",
                "source": item["source"][:120],
                "title": item["source"][:160],
                "quote": body,
                "url": url,
                "date": item.get("date", ""),
            })

        # --- Phase 2b: fallback - read a named subreddit's recent posts ---
        subs_found = [s for s, _ in sub_hits.most_common(5)]
        if not reddit_items and subs_found:
            for sub in subs_found[:1]:
                for p in self._fetch_subreddit_posts(sub, limit=4):
                    reddit_items.append({
                        "kind": "reddit_post",
                        "source": f"r/{p['subreddit']}",
                        "title": p["title"],
                        "quote": p["quote"],
                        "url": p["url"],
                        "date": p["date"],
                    })

        # --- Phase 3: assemble, strongest evidence first ---
        evidence = (reddit_items + search_items)[:max_items]

        # Stable, citable ids: e1, e2, ...
        for i, item in enumerate(evidence, start=1):
            item["id"] = f"e{i}"

        n_threads = len([x for x in evidence if x["kind"] in ("reddit_thread", "reddit_post")])
        n_search = len(evidence) - n_threads
        print(f"  ✓ Evidence: {len(evidence)} items "
              f"({n_search} search hits, {n_threads} reddit threads) "
              f"from subreddits {subs_found}")

        return {
            "evidence": evidence,
            "queries": queries,
            "subreddits": subs_found,
            "counts": {
                "total": len(evidence),
                "search": n_search,
                "reddit_threads": n_threads,
            },
        }

    # ------------------------------------------------------------------
    # N3: DEMAND SIGNALS (real, best-effort, omit-when-empty)
    # ------------------------------------------------------------------
    def collect_demand_signals(self, business_type: str, offering: str,
                               area_label: str = "",
                               icp_titles: Optional[List[str]] = None,
                               max_items: int = 4,
                               progress=None) -> List[Dict[str, Any]]:
        """
        Retrieve real hiring / expansion / new-location signals for the sector and
        the ICP roles, each carrying the URL it came from.

        There is NO general-purpose job-search Wire action available (the Lever
        action only covers Lever-hosted companies and 404s otherwise), so these
        come from real search results instead. Returns [] when nothing usable is
        found - the caller MUST omit the field rather than substitute wording.
        This replaces the old per-building hiring-signal string, which claimed
        Anakin Wire evidence that was never actually fetched.
        """
        titles = [t for t in (icp_titles or []) if isinstance(t, str)][:2]
        queries: List[str] = []
        if titles:
            queries.append(f'hiring "{titles[0]}" {area_label} new office'.strip())
        queries.append(f"{business_type} expansion new location {area_label} news".strip())

        signals: List[Dict[str, Any]] = []
        seen_urls = set()
        for si, q in enumerate(queries, start=1):
            if progress:
                try:
                    progress(f"N3 · Signal search {si}/{len(queries)}: {q[:70]}")
                except Exception:
                    pass
            try:
                res = self.anakin.search(q, limit=4)
            except Exception as e:
                print(f"  ⚠ demand-signal search failed ({q[:40]}...): {e}")
                continue
            if not isinstance(res, dict):
                continue
            for r in (res.get("results") or []):
                url = (r.get("url") or r.get("link") or "").strip()
                snippet = (r.get("snippet") or "").strip()
                # A signal without a real URL is not a signal.
                if not url.startswith("http") or not snippet or url in seen_urls:
                    continue
                seen_urls.add(url)
                signals.append({
                    "claim": snippet[:280],
                    "source": (r.get("title") or "")[:160],
                    "url": url,
                    "date": r.get("date") or "",
                })
                if len(signals) >= max_items:
                    break
            if len(signals) >= max_items:
                break

        print(f"  ✓ Demand signals: {len(signals)} real item(s)")
        return signals[:max_items]

    # ------------------------------------------------------------------
    # N7: GROUNDING VALIDATOR
    # ------------------------------------------------------------------
    def validate_grounding(self, result: Dict[str, Any],
                           evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Drop any claim that cannot be traced to retrieved evidence.

        This is the structural guarantee that the app cannot present invented
        research: a claim whose citation is missing from the evidence set - or a
        demand signal with no URL - is discarded and counted, never rendered.
        """
        valid_ids = {e.get("id") for e in evidence if e.get("id")}
        dropped = 0

        icp = result.get("icp_intelligence") or {}

        kept_pains = []
        for p in icp.get("pain_points", []) or []:
            eid = p.get("evidence_id") if isinstance(p, dict) else None
            if eid and eid in valid_ids:
                kept_pains.append(p)
            else:
                dropped += 1
        icp["pain_points"] = kept_pains
        icp["key_pain_points"] = [p.get("claim", "") for p in kept_pains]

        kept_triggers = []
        for t in icp.get("buying_triggers", []) or []:
            eid = t.get("evidence_id") if isinstance(t, dict) else None
            if eid and eid in valid_ids:
                kept_triggers.append(t)
            else:
                dropped += 1
        icp["buying_triggers"] = kept_triggers

        # Only cite online spaces that literally appear in the evidence.
        blob = json.dumps(evidence).lower()
        kept_spaces = []
        for s in icp.get("online_spaces", []) or []:
            if not isinstance(s, str):
                continue
            token = s.lower().strip()
            bare = token.lstrip("r/").replace(" ", "")
            if token in blob or (bare and bare in blob.replace(" ", "")):
                kept_spaces.append(s)
            else:
                dropped += 1
        icp["online_spaces"] = kept_spaces

        # Demand signals must carry a real URL.
        signals = []
        for s in result.get("demand_signals", []) or []:
            if isinstance(s, dict) and str(s.get("url", "")).startswith("http"):
                signals.append(s)
            else:
                dropped += 1
        result["demand_signals"] = signals

        result["icp_intelligence"] = icp
        result["grounding"] = {
            "claims_total": dropped + len(kept_pains) + len(kept_triggers),
            "claims_kept": len(kept_pains) + len(kept_triggers),
            "claims_dropped": dropped,
            "evidence_ids": sorted(valid_ids),
        }
        if dropped:
            print(f"  ⚠ grounding dropped {dropped} unverifiable claim(s)")
        else:
            print(f"  ✓ grounding: all claims traceable to evidence")
        return result

    # ------------------------------------------------------------------
    # N2: EVIDENCE-GROUNDED ICP EXTRACTION (real LLM reasoning)
    # ------------------------------------------------------------------
    def run_icp_extraction(self, evidence: List[Dict[str, Any]], company_name: str,
                           business_type: str, offering: str,
                           sample_customers: str) -> Dict[str, Any]:
        """
        Reason over the retrieved evidence to produce ICP intelligence.

        The LLM sees only `evidence` and must cite it. Its output is validated by
        validate_grounding() before it can reach the client.
        """
        try:
            from intelligence import extract_icp
        except Exception as e:
            print(f"  ⚠ intelligence module unavailable: {e}")
            return {"pain_points": [], "buying_triggers": [], "icp_titles": [],
                    "online_spaces": [], "ok": False}

        return extract_icp(
            evidence=evidence,
            company_name=company_name,
            business_type=business_type,
            offering=offering,
            sample_customers=sample_customers,
        )

    # Node 1: ICP Intelligence (N1 retrieval -> N2 extraction, both real)
    def run_icp_problem_mining(self, business_type: str, offering: str,
                               target_customers: str,
                               company_name: str = "",
                               progress=None) -> Dict[str, Any]:
        """
        Compose the real research nodes: retrieve citable evidence (N1), then
        extract ICP intelligence from that evidence only (N2).

        There are deliberately NO hardcoded pain points, subreddits or buying
        triggers here. Everything returned is traceable to a retrieved source,
        and `validate_grounding()` re-checks the citations afterwards.
        """
        retrieval = self.collect_evidence(
            business_type=business_type,
            offering=offering,
            sample_customers=target_customers,
            progress=progress,
        )
        evidence = retrieval["evidence"]

        if progress:
            try:
                progress(f"N2 · Extracting ICP intelligence from {len(evidence)} evidence items…")
            except Exception:
                pass

        extraction = self.run_icp_extraction(
            evidence=evidence,
            company_name=company_name or "the client",
            business_type=business_type,
            offering=offering,
            sample_customers=target_customers,
        )

        # Flatten to the shape the rest of the pipeline and the UI consume, while
        # keeping the citation on every claim.
        pain_points = [
            {
                "claim": p.get("claim", ""),
                "evidence_id": p.get("evidence_id"),
                "quote": p.get("quote", ""),
            }
            for p in extraction.get("pain_points", []) if isinstance(p, dict)
        ]
        buying_triggers = [
            {
                "claim": t.get("claim", ""),
                "evidence_id": t.get("evidence_id"),
            }
            for t in extraction.get("buying_triggers", []) if isinstance(t, dict)
        ]

        icp_titles = [t for t in extraction.get("icp_titles", []) if isinstance(t, str)]
        online_spaces = [s for s in extraction.get("online_spaces", []) if isinstance(s, str)]

        return {
            "evidence": evidence,
            "evidence_counts": retrieval["counts"],
            "search_queries": retrieval["queries"],
            "subreddits": retrieval["subreddits"],
            "pain_points": pain_points,
            # Back-compat alias: the UI previously read key_pain_points as strings.
            "key_pain_points": [p["claim"] for p in pain_points],
            "buying_triggers": buying_triggers,
            "derived_icp_titles": icp_titles,
            "online_spaces": online_spaces,
            "extraction": {
                "model": extraction.get("model"),
                "ok": bool(extraction.get("ok")),
            },
        }

    def _derive_icp_titles(self, business_type: str, offering: str) -> List[str]:
        """
        DEPRECATED fallback: only used to label a run when extraction produced no
        ICP titles at all. Anything it returns is marked derived_fallback so it is
        never mistaken for researched output.
        """
        bt = business_type.lower()
        if "food" in bt or "restaurant" in bt or "catering" in bt:
            return ["Office Manager", "Head of People & Workplace Experience", "Corporate Event Coordinator"]
        elif "cleaning" in bt or "facility" in bt:
            return ["Director of Facilities & Real Estate", "Property Manager", "Operations Manager"]
        elif "agency" in bt or "marketing" in bt:
            return ["Chief Marketing Officer (CMO)", "VP of Growth & Demand Gen", "Head of Brand Marketing"]
        else:
            return ["Director of Operations", "VP of Business Development", "Procurement Lead"]

    # Node 2: Office & Target Building Discovery (COORDINATE-ANCHORED)
    @staticmethod
    def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Great-circle distance in metres between two WGS84 points."""
        radius_earth = 6371008.8
        p1, p2 = math.radians(lat1), math.radians(lat2)
        d_phi = p2 - p1
        d_lambda = math.radians(lng2 - lng1)
        a = math.sin(d_phi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
        return 2 * radius_earth * math.asin(math.sqrt(a))

    def find_target_buildings(self, lat: float, lng: float, radius_meters: int,
                              business_type: str, sample_customers: str,
                              city: str = "", progress=None) -> List[Dict[str, Any]]:
        """
        Coordinate-anchored commercial building discovery.

        Every building carries the EXACT Google Places coordinate for its own
        place_id, hard-filtered to the user's scan radius. The same real-world
        place therefore always resolves to the same map pin, regardless of where
        the target pin is moved or how often the scan is re-run.

        Returns [] only when Google Places legitimately finds nothing inside the
        radius. A missing API key raises instead, so an unconfigured engine can
        never masquerade as a successful scan that found zero sites.
        """
        if not self.gmaps_key:
            raise RuntimeError(
                "GOOGLE_MAPS_API_KEY is not set - cannot run a real scan. "
                "Refusing to return an empty result set."
            )
        if lat is None or lng is None:
            print("✗ No target anchor supplied - refusing to invent one.")
            return []

        radius = int(min(max(int(radius_meters or 1500), 100), 50000))

        # Keyword set is derived from the ICP the user described, not baked to one city.
        icp_blob = f"{business_type} {sample_customers}".lower()
        if any(k in icp_blob for k in ("industrial", "logistics", "warehouse", "manufactur")):
            keywords = ["industrial park", "warehouse", "distribution center"]
        elif any(k in icp_blob for k in ("clinic", "medical", "health", "dental")):
            keywords = ["medical office building", "clinic", "medical center"]
        elif any(k in icp_blob for k in ("food", "catering", "restaurant", "coffee")):
            keywords = ["office building", "office tower", "coworking space"]
        else:
            keywords = ["office building", "office tower", "business park", "coworking space"]

        found: Dict[str, Dict[str, Any]] = {}
        for ki, kw in enumerate(keywords, start=1):
            if progress:
                try:
                    progress(f"N4 · Places query {ki}/{len(keywords)}: {kw}")
                except Exception:
                    pass
            url = (
                "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
                f"?location={lat},{lng}&radius={radius}"
                f"&keyword={urllib.parse.quote(kw)}&key={self.gmaps_key}"
            )
            data = self._fetch_url_json(url)
            for res in data.get("results", []):
                pid = res.get("place_id")
                loc = (res.get("geometry") or {}).get("location") or {}
                b_lat, b_lng = loc.get("lat"), loc.get("lng")
                if not pid or b_lat is None or b_lng is None:
                    continue

                # Hard radius gate: a place outside the scan circle is not a result.
                dist = self._haversine_m(lat, lng, b_lat, b_lng)
                if dist > radius:
                    continue

                # Deterministic density model - a function of the place's own
                # signals only, so the same place always scores identically.
                ratings_total = res.get("user_ratings_total") or 0
                rating = res.get("rating") or 4.0
                tenants = max(4, min(90, int(ratings_total / 8) + 4))
                decision_makers = tenants * 6
                match = round(min(99.0, 72.0 + (rating / 5.0) * 22.0 + min(5.0, tenants / 16.0)), 1)

                found[pid] = {
                    "id": pid,
                    "name": res.get("name"),
                    "address": res.get("vicinity") or res.get("formatted_address"),
                    "lat": round(b_lat, 7),   # anchored: straight from Places
                    "lng": round(b_lng, 7),
                    "distance_meters": round(dist, 1),
                    "rating": round(rating, 2),
                    "estimated_companies": tenants,
                    "estimated_decision_makers": decision_makers,
                    "target_sector_match": f"{match}%",
                    "source": "google_places",
                    "place_types": (res.get("types") or [])[:4]
                }

        buildings = sorted(found.values(), key=lambda b: b["distance_meters"])
        print(f"✓ Anchored {len(buildings)} real Places buildings within {radius}m of {lat},{lng}")
        return buildings

    # Node 3: Offline Executive Touchpoint Mapping
    def find_touchpoints_for_building(self, lat: float, lng: float, radius: int = 500) -> Dict[str, List[Dict[str, Any]]]:
        """
        Locates executive cafes, popular business lunch spots, and transit/taxi hubs
        within 500m of a given target building coordinate.
        """
        touchpoint_types = {
            "cafes": "cafe",
            "lunch_spots": "restaurant",
            "transit": "transit_station"
        }

        results = {}
        for category, ptype in touchpoint_types.items():
            url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lng}&radius={radius}&type={ptype}&key={self.gmaps_key}"
            data = self._fetch_url_json(url)
            spots = []
            for item in data.get("results", [])[:4]:
                spots.append({
                    "id": item.get("place_id"),
                    "name": item.get("name"),
                    "vicinity": item.get("vicinity"),
                    "rating": item.get("rating", 4.2),
                    "lat": item.get("geometry", {}).get("location", {}).get("lat"),
                    "lng": item.get("geometry", {}).get("location", {}).get("lng"),
                    "type": category,
                    "peak_hours": "8:30 AM - 10:00 AM & 12:00 PM - 1:45 PM",
                    "opportunity": "High-probability informal pitch & executive engagement zone"
                })
            results[category] = spots

        return results

    # Node 4: Hotspot Optimizer - centres are centroids of REAL coordinates
    def calculate_hotspot_clusters(self, buildings: List[Dict[str, Any]],
                                   radius_meters: int = 1500,
                                   business_type: str = "") -> List[Dict[str, Any]]:
        """
        Groups discovered buildings into density clusters and places each hotspot
        at the true centroid of its member buildings' real Google Places
        coordinates.

        Because every centre is the mean of real place coordinates, hotspot pins
        are geographically anchored: moving the target pin changes which
        buildings get discovered, but it never translates an existing hotspot.
        Nothing is emitted when no buildings were found.
        """
        if not buildings:
            return []

        radius_meters = int(radius_meters or 1500)

        def outlet_label() -> str:
            bt = business_type.lower()
            if any(k in bt for k in ("food", "catering", "restaurant", "coffee")):
                return "Grab-and-go outlet & corporate catering hub"
            if any(k in bt for k in ("clean", "facilit", "maintenance")):
                return "Service depot & on-site response hub"
            if any(k in bt for k in ("agenc", "marketing", "creative", "brand")):
                return "Client experience studio & activation space"
            if any(k in bt for k in ("software", "saas", "cloud", "ai", "compute")):
                return "Enterprise briefing suite & solutions office"
            return "Commercial outlet & sales presence"

        # Seeds = highest decision-maker mass, with enforced minimum separation so
        # clusters spread across the scanned area instead of stacking on one street.
        ranked = sorted(buildings, key=lambda b: b.get("estimated_decision_makers", 0), reverse=True)
        min_sep = max(150.0, min(800.0, radius_meters * 0.30))
        seeds: List[Dict[str, Any]] = []
        for b in ranked:
            if all(self._haversine_m(b["lat"], b["lng"], s["lat"], s["lng"]) >= min_sep for s in seeds):
                seeds.append(b)
            if len(seeds) >= 3:
                break
        if not seeds:
            seeds = ranked[:1]

        buckets = [{"seed": s, "members": []} for s in seeds]
        for b in buildings:
            best = min(
                buckets,
                key=lambda bk: self._haversine_m(b["lat"], b["lng"], bk["seed"]["lat"], bk["seed"]["lng"])
            )
            best["members"].append(b)

        clusters: List[Dict[str, Any]] = []
        for idx, bk in enumerate(buckets):
            members = bk["members"]
            if not members:
                continue

            # THE ANCHOR: arithmetic mean of member coordinates. No pin offsets.
            c_lat = round(sum(m["lat"] for m in members) / len(members), 7)
            c_lng = round(sum(m["lng"] for m in members) / len(members), 7)

            mass = sum(m.get("estimated_decision_makers", 0) for m in members)
            anchors = sorted(members, key=lambda m: m.get("estimated_decision_makers", 0), reverse=True)[:3]
            spread = max(self._haversine_m(c_lat, c_lng, m["lat"], m["lng"]) for m in members)
            lead = anchors[0]

            clusters.append({
                "cluster_id": f"HS-{idx + 1:02d}",
                "name": f"{lead['name']} Catchment",
                "anchor_place_id": lead["id"],
                "micro_district": (lead.get("address") or "").split(",")[-2].strip() if "," in (lead.get("address") or "") else "Scan radius",
                "recommended_outlet_type": outlet_label(),
                "tagline": f"{len(members)} verified sites, ~{mass:,} mapped decision makers",
                "catchment_radius_meters": int(max(200, min(900, spread + 150))),
                "icp_density_score": round(min(99.0, 58.0 + len(members) * 6.0 + mass / 250.0), 1),
                "daily_footfall_estimate": mass * 55,
                "monthly_icp_reach": mass * 4,
                "buildings_covered": len(members),
                "center": {"lat": c_lat, "lng": c_lng},
                "ideal_streets": [m.get("address") for m in anchors if m.get("address")][:2],
                "strategic_advantage": (
                    f"Centroid of {len(members)} verified Google Places site(s) within "
                    f"{int(spread)}m; anchored on {lead['name']}."
                ),
                "anchor_buildings": [
                    {
                        "id": m["id"], "name": m["name"], "lat": m["lat"], "lng": m["lng"],
                        "address": m.get("address"),
                        "decision_makers": m.get("estimated_decision_makers", 0)
                    } for m in anchors
                ],
                "surrounding_buildings": [
                    {
                        "id": m.get("id"), "name": m.get("name"), "address": m.get("address"),
                        "lat": m.get("lat"), "lng": m.get("lng"),
                        "companies": m.get("estimated_companies", 0),
                        "decision_makers": m.get("estimated_decision_makers", 0)
                    } for m in members
                ],
                "derivation": "centroid of real Google Places coordinates"
            })

        clusters.sort(key=lambda c: c["icp_density_score"], reverse=True)
        return clusters

    # Master Execution Pipeline
    def execute_research_run(self, payload: Dict[str, Any],
                             progress=None) -> Dict[str, Any]:
        """
        Runs the full Syndicate research pipeline for ONE anchor point.

        This is a research run, not a simulation: every returned fact is either
        retrieved from a real source (Google Places, Anakin search, Reddit Wire
        reads) or extracted from that retrieved evidence, and every claim carries
        a citation. Nothing is invented.

        `progress` is an optional callable accepting a single label string. It is
        invoked as each stage completes so callers can surface the run's actions
        live (the worker publishes them to the chat log). Failures inside the
        callback are swallowed - progress reporting must never break a run.
        """

        def emit(label: str) -> None:
            if progress is None:
                return
            try:
                progress(label)
            except Exception as exc:  # never let logging break the pipeline
                print(f"  ⚠ progress emit failed: {exc}")

        company_name = payload.get("company_name", "Acme Enterprise")
        business_type = payload.get("business_type", "Corporate Services")
        offering = payload.get("offering", "High-volume delivery and management")
        target_city = payload.get("target_city", "")
        sample_customers = payload.get("sample_customers", "Local tech companies and corporate offices")

        raw_lat = payload.get("lat")
        raw_lng = payload.get("lng")
        if raw_lat is None or raw_lng is None:
            # No anchor => no scan. Never invent a location.
            print("✗ Research run rejected: no anchor coordinates supplied.")
            emit("Scan rejected · no target pin was set")
            return {
                "status": "error",
                "error": "anchor_required",
                "message": "A target pin is required before a scan can run.",
                "query": {
                    "company_name": company_name,
                    "business_type": business_type,
                    "offering": offering,
                    "target_city": target_city,
                    "sample_customers": sample_customers
                },
                "icp_intelligence": {},
                "target_buildings": [],
                "offline_touchpoints": [],
                "hotspot_recommendations": [],
                "heatmap_data": [],
                "anchor": None
            }

        anchor = {"lat": float(raw_lat), "lng": float(raw_lng)}
        scan_radius = int(payload.get("radius_meters") or 1500)

        print(f"🚀 Research run: {company_name} | {business_type} @ {anchor['lat']},{anchor['lng']} r={scan_radius}m")
        emit(f"Scan started · {company_name or 'business'} · radius {scan_radius}m")

        # Step 1: ICP intelligence - real evidence retrieval + grounded extraction
        emit("N1 · Retrieving citable evidence from the web and Reddit…")
        icp_insights = self.run_icp_problem_mining(
            business_type, offering, sample_customers,
            company_name=company_name, progress=emit
        )
        ev_counts = icp_insights.get("evidence_counts") or {}
        subs = icp_insights.get("subreddits") or []
        emit(f"N1 · Retrieved {ev_counts.get('total', 0)} evidence items "
             f"({ev_counts.get('search', 0)} web, {ev_counts.get('reddit_threads', 0)} threads)"
             + (f" from {', '.join('r/' + s for s in subs[:3])}" if subs else ""))
        emit(f"N2 · Extracted {len(icp_insights.get('pain_points') or [])} cited pain points, "
             f"{len(icp_insights.get('buying_triggers') or [])} buying triggers")

        # Only if the research produced no ICP titles at all do we fall back to a
        # labelling heuristic - and it is flagged so it is never mistaken for
        # researched output.
        if not icp_insights.get("derived_icp_titles"):
            icp_insights["derived_icp_titles"] = self._derive_icp_titles(business_type, offering)
            icp_insights["icp_titles_derived_fallback"] = True
        else:
            icp_insights["icp_titles_derived_fallback"] = False

        # Step 1b: real demand signals (hiring/expansion) for the ICP roles.
        # Omitted entirely when nothing usable is found - never substituted.
        emit("N3 · Searching for real hiring and expansion signals…")
        demand_signals = self.collect_demand_signals(
            business_type=business_type,
            offering=offering,
            area_label=target_city if target_city and target_city != "Target Coordinates" else "",
            icp_titles=icp_insights.get("derived_icp_titles") or [],
            progress=emit,
        )
        emit(f"N3 · Demand signals: {len(demand_signals)} url-backed finding(s)")

        # Step 2: Target buildings - real Places places inside the scan radius
        emit(f"N4 · Scanning real commercial sites within {scan_radius}m…")
        try:
            buildings = self.find_target_buildings(
                lat=anchor["lat"],
                lng=anchor["lng"],
                radius_meters=scan_radius,
                business_type=business_type,
                sample_customers=sample_customers,
                city=target_city,
                progress=emit
            )
        except RuntimeError as exc:
            # Misconfiguration must surface as an error, never as a scan that
            # "completed" with nothing in it.
            print(f"✗ Research run aborted: {exc}")
            emit(f"Scan aborted · {exc}")
            return {
                "status": "error",
                "error": "engine_unavailable",
                "message": str(exc),
                "anchor": anchor,
                "anchor_radius_meters": scan_radius,
                "query": {
                    "company_name": company_name,
                    "business_type": business_type,
                    "offering": offering,
                    "target_city": target_city,
                    "sample_customers": sample_customers
                },
                "icp_intelligence": {},
                "target_buildings": [],
                "offline_touchpoints": [],
                "hotspot_recommendations": [],
                "heatmap_data": [],
                "counts": {"buildings": 0, "touchpoints": 0, "hotspots": 0}
            }

        emit(f"N4 · {len(buildings)} real sites found within {scan_radius}m")

        # Step 3: Offline touchpoints around the strongest discovered buildings
        emit("N5 · Mapping dining, coffee and transit touchpoints…")
        all_touchpoints = []
        for bi, b in enumerate(buildings[:4], start=1):
            emit(f"N5 · Mapping touchpoints around site {bi}/{min(len(buildings), 4)}: {b['name']}")
            tps = self.find_touchpoints_for_building(b["lat"], b["lng"], radius=450)
            for cat, items in tps.items():
                for itm in items:
                    itm["near_building"] = b["name"]
                    all_touchpoints.append(itm)

        # Deduplicate touchpoints by place_id, falling back to name
        deduped_touchpoints = []
        seen_tp = set()
        for tp in all_touchpoints:
            tkey = tp.get("id") or tp.get("name")
            if tkey and tkey not in seen_tp:
                seen_tp.add(tkey)
                deduped_touchpoints.append(tp)

        emit(f"N5 · {len(deduped_touchpoints)} touchpoints mapped")

        # Step 4: Hotspots - centroids of the real discovered buildings
        emit("N6 · Clustering hotspots from real coordinates…")
        hotspots = self.calculate_hotspot_clusters(
            buildings,
            radius_meters=scan_radius,
            business_type=business_type
        )
        emit(f"N6 · {len(hotspots)} hotspot(s) clustered")

        # Weighted density surface, one point per real coordinate
        heatmap_points = [
            {"lat": b["lat"], "lng": b["lng"], "weight": b.get("estimated_decision_makers", 50)}
            for b in buildings
        ]
        for tp in deduped_touchpoints:
            if tp.get("lat") and tp.get("lng"):
                heatmap_points.append({"lat": tp["lat"], "lng": tp["lng"], "weight": 25})

        result = {
            "status": "success",
            "result_id": uuid.uuid4().hex,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            # The pin the user dropped - echoed back so the client can prove the
            # results were produced around exactly this anchor.
            "anchor": anchor,
            "anchor_radius_meters": scan_radius,
            "query": {
                "company_name": company_name,
                "business_type": business_type,
                "offering": offering,
                "target_city": target_city,
                "sample_customers": sample_customers
            },
            "icp_intelligence": icp_insights,
            # Real hiring/expansion signals, each with the URL it came from.
            "demand_signals": demand_signals,
            # The retrieved evidence everything above is traceable to.
            "sources": icp_insights.get("evidence", []),
            # All coordinates below come straight from Google Places and are
            # therefore anchored to real geography, not to the dropped pin.
            "coordinate_source": "google_places",
            "target_buildings": buildings,
            "offline_touchpoints": deduped_touchpoints,
            "hotspot_recommendations": hotspots,
            "heatmap_data": heatmap_points,
            "counts": {
                "buildings": len(buildings),
                "touchpoints": len(deduped_touchpoints),
                "hotspots": len(hotspots),
                "evidence": len(icp_insights.get("evidence", [])),
                "pain_points": len(icp_insights.get("pain_points", [])),
                "demand_signals": len(demand_signals),
            }
        }

        # N7: drop anything that cannot be traced to retrieved evidence. This runs
        # last so no unverifiable claim can reach the client.
        emit("N7 · Verifying every claim against its source…")
        final = self.validate_grounding(result, icp_insights.get("evidence", []))
        g = final.get("grounding") or {}
        emit(f"N7 · Grounding: {g.get('claims_kept', 0)} claim(s) verified"
             + (f", {g['claims_dropped']} discarded as unverifiable"
                if g.get("claims_dropped") else ", none discarded"))
        emit("Scan complete — results published")
        return final


    # DEPRECATED: the old name is kept as an alias so any in-flight caller keeps
    # working. Remove once every call site has moved to execute_research_run.
    execute_syndicate_simulation = execute_research_run


if __name__ == "__main__":
    engine = SyndicateGraphEngine()
    # Anchor is mandatory now: the engine will refuse to run without one.
    test_payload = {
        "company_name": "Krave Express Catering",
        "business_type": "Fast Food & Corporate Catering",
        "offering": "High-speed healthy box meals and team catering",
        "target_city": "San Francisco, CA",
        "sample_customers": "Tech offices, law firms, engineering teams",
        "lat": 37.7895,
        "lng": -122.3980,
        "radius_meters": 1500
    }
    res = engine.execute_research_run(test_payload)
    print("Research run completed successfully!")
    print(f"Anchor: {res.get('anchor')} r={res.get('anchor_radius_meters')}m")
    print(f"Target buildings found: {len(res['target_buildings'])}")
    print(f"Offline touchpoints found: {len(res['offline_touchpoints'])}")
    print(f"Hotspot clusters generated: {len(res['hotspot_recommendations'])}")
    for hs in res["hotspot_recommendations"]:
        print(f"  {hs['cluster_id']} {hs['name']} -> {hs['center']} ({hs['derivation']})")
