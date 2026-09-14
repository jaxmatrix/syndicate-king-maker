# Syndicate: The King Maker — Architecture & Execution Blueprint

**Syndicate: The King Maker** is an autonomous, global B2B commercial site selection and physical market expansion engine. It converts high-level business criteria into high-probability physical presence hotspots across any city or commercial coordinate globally.

---

## 1. Core Architecture Stack

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              SYNDICATE COMMAND CENTER (UI)                             │
├──────────────────────────┬───────────────────────────────┬─────────────────────────────┤
│   LEFT PANEL (380px)     │       CENTER MAP CANVAS       │    RIGHT SIDEBAR (420px)    │
│  Business Profile & ICP  │  Global Tactical Dark Engine  │   Live Agent Execution Log  │
│                          │                               │              &              │
│  • Company & Offering    │  • Global Pin Drop Tool       │  • Queued (no SSE needed)   │
│  • Preset Archetypes     │  • Dynamic Radius Controller  │  • Multi-turn User Chat     │
│  • B2B Deal Constraints  │    (500m to 8,000m range)     │  • Live Mastra Agent         │
│  • Firebase Auth Status  │  • Anchored Building Pins     │  • Cited Evidence Panel     │
│  • Run Research Trigger  │  • Offline Touchpoint Pins    │  • Grounding Report          │
│                          │  • Centroid Hotspot Rings     │                             │
└──────────────────────────┴───────────────────────────────┴─────────────────────────────┘
                                           │
                                           │ REST + queue polling
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                   MASTRA AGENT & INTELLIGENCE RUNTIME LAYER  (LIVE)                    │
│                                                                                        │
│  Mastra King Maker Agent: `syndicate-king-maker`  (DeepSeek v4.1 flash via OpenRouter)  │
│  • System prompt: commercial site selection + spatial GTM research                     │
│  • Tools bound (ALL REAL CALLS - no synthesised data):                                 │
│    1. `anakin-search`        Anakin MCP search (web + Reddit), returns urls             │
│    2. `anakin-reddit-posts`  Anakin MCP reddit wire read, real posts + permalinks       │
│    3. `anakin-scrape`        Anakin MCP scrape, reads a source in full                  │
│    4. `google-places-nearby` Places Nearby, haversine-filtered to the radius            │
│    5. `google-geocode`       Geocoding API, name/address -> real coordinates            │
│  • Reached from the browser via `chat_bridge.ts` + the Helix /api/chat queue,           │
│    because a hosted browser cannot reach a localhost port.                              │
│  • Multi-turn: researches further on request and finds new customers after a scan       │
└────────────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────────────────┐
│              RESEARCH ENGINE (backend/engine.py) - evidence-bound, cited               │
│                                                                                        │
│  N1 collect_evidence()        Anakin search -> harvest subreddits -> scrape threads     │
│  N2 run_icp_extraction()      DeepSeek v4.1 over evidence[] ONLY, one citation/claim    │
│  N3 collect_demand_signals()  real hiring/expansion signals; [] when none found         │
│  N4 find_target_buildings()   Places Nearby + haversine; exact place coordinates        │
│  N5 find_touchpoints_...()    Places Nearby around the top sites                        │
│  N6 calculate_hotspot_...()   centroids of REAL member coordinates                      │
│  N7 validate_grounding()      drops any claim not traceable to retrieved evidence       │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Surfaces & Components to Build

### Surface 1: Global Map & Dynamic Spatial Pin Drop
- **Location Agnostic**: Any latitude/longitude on Earth can be analyzed (San Francisco, London, Tokyo, Singapore, Bangalore, Mumbai, New York, etc.).
- **Interactive Drop-Pin Mode**: Clicking "Drop Pin" activates a crosshair on the map. Placing or dragging the marker dynamically updates the center coordinates.
- **Dynamic Radius Controller**: An interactive slider (500m to 15,000m) with a live glowing catchment boundary on the map.

### Surface 2: Live Right Sidebar (Agent Telemetry + Chat Console)
- **Tab A: Live Agent Telemetry** (real nodes, real counts):
  - Step 1: Ingest business parameters and deal profile.
  - Step 2: Retrieve citable evidence (Anakin search + scraped Reddit threads).
  - Step 2b: Grounded extraction of ICP pain points, triggers and online spaces.
  - Step 2c: Real hiring/expansion demand signals (omitted when none are found).
  - Step 3: Scan Google Places within the radius for real sites.
  - Step 4: Map offline touchpoints (executive coffee, business dining, transit).
  - Step 5: Cluster hotspots as centroids of real member coordinates.
  - Sources: the evidence list with clickable urls, plus a grounding report.
- **Tab B: Interactive Agent Chat Room**:
  - Powered by the LIVE Mastra King Maker Agent (real Anakin MCP + Google Maps tools).
  - The user can ask it to research further: *"Find coworking spaces near 555 California"*,
    *"Who else in this radius could buy from us?"*, *"Which source contradicts this claim?"*.
  - The agent performs real tool calls and reports the urls and coordinates it actually found.

### Surface 3: Mastra Agent Framework
- Configured with typed tool schemas and a tailored system persona:
  - Role: Senior Commercial Real Estate Strategist, B2B Growth Architect, and Spatial GTM Lead.
  - Incorporates Anakin's network-layer Wire data and Google Places coordinates.

---

## 3. Milestones & Implementation Checklist

- [x] **Milestone 1**: Project workspace + blueprint reference.
- [x] **Milestone 2**: Mastra King Maker Agent — LIVE, with real Anakin MCP + Google Maps tools.
- [x] **Milestone 3**: 3-column UI with global pin drop, radius slider, telemetry + chat.
- [x] **Milestone 4**: Backend wired through the Helix queue (research runs + agent chat);
      no simulation, no fabricated data, every claim cited.
- [x] **Milestone 5**: Tested (11-test suite + 4 verification scripts) and deployed to Helix
      (`https://syndicate-app.jai.allr.work`).

## 4. Standing Invariants (do not regress)

1. **No invented data.** Every claim traces to a retrieved source; `validate_grounding()`
   enforces it and `N3` omits rather than estimates.
2. **No pre-baked results.** Nothing renders until the operator runs a scan, and there is no
   client-side result generator.
3. **Anchored pins.** Result coordinates come from Google Places and never inherit the
   dropped pin's position.
4. **Real tool calls only.** If a tool call fails, the UI says so rather than substituting
   plausible wording.

## 5. Open Items

- The Helix `delete` handler 500s (`ERR_INVALID_ARG_TYPE`), so historical queue rows cannot
  be purged from the app. The client only ever renders rows matching its own task id, so this
  is cosmetic; a platform fix is needed for a true purge.
- Demand-signal quality varies: some hits are career/listing pages rather than specific
  postings. They are real and URL-backed, but precision could improve with a
  listing-specific source.
- Deprecated aliases (`/api/simulate`, `/api/simulations`) are still live. Delete after one
  deploy cycle.
- **Research runs are slow (~1–4 min).** The main cause is the Python Anakin client
  (`/opt/data/anakin_client.py`): it spawns a fresh `npx @anakin-io/mcp` subprocess for
  *every* tool call, and a run makes ~7 (3 searches + 4 thread scrapes). Reusing one
  persistent MCP stdio process — as the Node bridge already does with `anakin_mcp.ts` —
  is the obvious optimisation and would cut both latency and npx overhead.
- **The queue never clears `pending` rows.** Completion is published as a new row
  (`status: done:<id>`), not an update to the original, and the Helix `update`/`delete`
  handlers are unavailable/broken. The worker therefore uses a freshness window
  (`SYNDICATE_PENDING_MAX_AGE_S`, default 1800s) so a restart never re-runs the historical
  backlog. A true fix needs an update route.
- Duplicate concurrent workers remain possible (the watchdog revives one while a manual one
  runs). Harmless for correctness — the client takes the newest successful row for its own
  task id — but it doubles compute. Consider a lock.
