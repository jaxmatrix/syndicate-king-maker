# CLAUDE.md — Syndicate: The King Maker

Project context for AI coding agents (Claude Code / Allr) working in this repository.

## What This Is

**Syndicate: The King Maker** — an autonomous, global B2B commercial site-selection and
physical market expansion platform. Users drop a pin anywhere on Earth, define a scan
radius, and the engine maps customer decision-maker density, offline executive
touchpoints, and top-3 physical outlet hotspots on a tactical dark Google Map.

Live deployments:
- App: https://syndicate-app.jai.allr.work (Helix, appId `cf126906-b884-47b3-a1d8-aec3b9d44dd3`, port 5020)
- UI Kit: https://syndicate-ui-kit.jai.allr.work

## Repository Layout

```
/opt/data/syndicate/
├── PLAN.md              # Architecture & execution blueprint (Milestones 1-5)
├── CLAUDE.md            # This file — project rules for AI agents
├── test_suite.py        # Python unittest suite (11 tests)
├── verify_anchoring.py  # proof: result pins never move with the anchor
├── verify_e2e.py        # proof: full queue round-trip
├── verify_research.py   # proof: cited claims, no hardcoded wording
├── verify_live_chat.py  # proof: live Mastra agent answers with real tool calls
├── helix_*.json         # Helix ops plans (routes, chat table)
├── backend/             # FastAPI + research engine (Python 3.13)
│   ├── engine.py        # SyndicateGraphEngine: research nodes N1-N7
│   ├── intelligence.py  # DeepSeek v4.1 evidence-grounded ICP extraction
│   ├── server.py        # FastAPI on :8090 (/api/research, /api/chat, /api/health, /api/config)
│   └── worker.py        # Helix queue daemon: polls /api/research-runs, runs engine
├── frontend/            # Single-file SPA (index.html) — deployable to Helix as static zip
│   └── index.html       # 3-column command center, Firebase auth, Google Maps JS
└── mastra/              # LIVE research agent (TypeScript, run with tsx)
    ├── env.ts           # loads the shared .env — import FIRST (ESM hoisting)
    ├── anakin_mcp.ts    # native MCP client over stdio to @anakin-io/mcp
    ├── tools_anakin.ts  # anakin-search / anakin-reddit-posts / anakin-scrape
    ├── google_maps.ts   # Places Nearby (haversine) + Geocoding
    ├── tools_maps.ts    # google-places-nearby / google-geocode
    ├── agent.ts         # syndicateKingMakerAgent (DeepSeek v4.1 via OpenRouter)
    ├── index.ts         # Mastra instance registration
    ├── chat_bridge.ts   # polls Helix /api/chat, runs the agent, writes replies
    ├── agent_test.ts    # proves the agent makes real tool calls
    └── tools_test.ts    # proves the MCP + Maps tools return real data
```

## Key Commands

```bash
# Run full verification suite (11 tests: anchoring, research, live agent)
npm --prefix /opt/data/syndicate/mastra run test

# Start backend (background)
/opt/hermes/.venv/bin/python3 /opt/data/syndicate/backend/server.py

# Start Helix queue worker (background)
/opt/hermes/.venv/bin/python3 /opt/data/syndicate/backend/worker.py

# Start the LIVE Mastra agent chat bridge (background)
cd /opt/data/syndicate/mastra && npx tsx chat_bridge.ts

# Prove the Mastra agent + its tools work (real calls)
cd /opt/data/syndicate/mastra && npx tsx tools_test.ts && npx tsx agent_test.ts

# Deploy frontend to Helix (zip contents, then update app)
python3 /opt/allr/skills/helix/scripts/helix_client.py zip /opt/data/syndicate/frontend /tmp/syndicate_app.zip
python3 /opt/allr/skills/helix/scripts/helix_client.py update cf126906-b884-47b3-a1d8-aec3b9d44dd3 /tmp/syndicate_app.zip "vN-message"

# Apply Helix resource changes (routes / tables) from a plan file
python3 /opt/allr/skills/helix/scripts/helix_client.py ops /opt/data/syndicate/helix_chat_table.json
```

## Architecture Invariants

1. **Backend runs on port 8090** (FastAPI + Uvicorn, venv: `/opt/hermes/.venv/bin/python3`).
   - `engine.py` imports `anakin_client` from `/opt/data` via `sys.path.insert(0, '/opt/data')`.
   - `engine.py` **self-loads `/opt/data/profiles/accelerator/.env`** at import. The worker is
     spawned by `workspace_watchdog.py`, whose environment has no API keys — without this the
     engine silently ran keyless and published an empty "success". Do not remove.
2. **Helix queue pattern**: The public frontend CANNOT reach `127.0.0.1:8090` from a remote
   browser (ERR_CONNECTION_REFUSED). Browser → Helix `/api/simulations` (same origin) →
   `worker.py` daemon polls, executes, writes `done:<taskId>` records back.
   The **client generates its own `taskId`** and polls for `done:<its own id>`; it takes the
   newest successful row, so a racing duplicate worker can never surface an empty result.
3. **Auth gate (Google-only auth)**: `triggerSimulation()` AND `sendChatMessage()` must
   check `currentUser || guestModeAllowed` and open the auth modal otherwise. Google
   Sign-In is the only real provider (email/password auth removed 2026-09-14); first-time
   Google sign-ins get a profile step (company + use case → Firestore `users/{uid}`).
   Guest mode is an explicit, session-only escape hatch (in-memory flag — resets on
   reload). Guest sessions are tagged `guest:<uuid8>` in `guestSessionId`.
4. **Map engine dual-path**: Try Google Maps JS API first (`loading=async`), register
   `window.gm_authFailure` → auto-failover to Leaflet + CartoDB Dark Matter tiles.
   NEVER use `google.maps.visualization.HeatmapLayer` (decommissioned 2026) — use the
   radial glow circle overlay pattern instead.
5. **Helix deploys are synchronous** (~60s); never retry while one is in flight.
   Zip the directory *contents*, not the directory.
6. **NO PRE-BAKED RESULTS — nothing renders until the operator runs a scan.**
   - There is deliberately **no startup scan**: `onGoogleMapsReady()` must NOT call
     `triggerSimulation()`, and neither may `continueAsGuest()`.
   - There is deliberately **no client-side result generator** (the old
     `generateClientSideSimulation()` is deleted). If the worker cannot be reached the UI
     reports failure — it never fabricates pins.
   - Sidebar telemetry starts at `IDLE — NO SCAN RUN` / "Awaiting run."
   - Sample input (preset chips, default field values) is intentionally kept.
7. **RESULT PINS ARE GEOGRAPHICALLY ANCHORED.** Moving the target pin must never move a
   result pin.
   - `find_target_buildings()` is **coordinate-driven**: it uses Places Nearby Search around
     `(lat, lng)` hard-filtered by haversine to the scan radius, and stores the exact
     `geometry.location` per `place_id`. The same place always resolves to the same pin.
   - `calculate_hotspot_clusters()` derives every hotspot centre as the **centroid of its
     member buildings' real coordinates** — never `anchor + delta`.
   - A scan with no anchor is refused (`status: error`, `anchor_required`).
   - Dragging/placing the pin calls `markResultsStale()` (status → `ANCHOR MOVED — RESCAN`)
     and does **not** re-run the engine.
8. **A missing `GOOGLE_MAPS_API_KEY` is fatal, not empty.** `find_target_buildings()` raises;
   `execute_syndicate_simulation()` returns `error: engine_unavailable`. A keyless engine can
   never publish a "success" with zero sites.

## Verification

```bash
# Project suite (11 tests) — needs backend + worker + chat bridge running
npm --prefix /opt/data/syndicate/mastra run test

# Anchoring proof: shared pins must not move when the anchor moves
/opt/hermes/.venv/bin/python3 /opt/data/syndicate/verify_anchoring.py

# End-to-end proof through the real Helix queue path
/opt/hermes/.venv/bin/python3 /opt/data/syndicate/verify_e2e.py

# Research-pipeline proof: cited claims, no hardcoded wording, real sources
/opt/hermes/.venv/bin/python3 /opt/data/syndicate/verify_research.py

# Live Mastra agent: real tool calls through the chat queue
/opt/hermes/.venv/bin/python3 /opt/data/syndicate/verify_live_chat.py
cd /opt/data/syndicate/mastra && npx tsx agent_test.ts && npx tsx tools_test.ts
```

## The Research Pipeline (real, evidence-bound)

There is no simulator. `execute_research_run()` runs six research nodes plus a validator:

```
N1 collect_evidence()          Anakin search -> subreddits -> scrape the Reddit threads
                               found, into evidence[] = {id,kind,source,quote,url,date}
N2 run_icp_extraction()        DeepSeek v4.1 flash reasons over evidence[] ONLY;
  (backend/intelligence.py)    returns pain_points/buying_triggers/icp_titles/online_spaces
N3 collect_demand_signals()    real hiring/expansion signals, each with a url;
                               returns [] when nothing real is found (field is then omitted)
N4 find_target_buildings()     Places Nearby + haversine radius, exact place coordinates
N5 find_touchpoints_for_building()  Places Nearby around the top sites
N6 calculate_hotspot_clusters()     centroids of real member coordinates
N7 validate_grounding()        drops any claim whose evidence_id is absent, any online
                               space not present in the evidence, any signal without a url
```

**Why fabrication is structurally impossible:** N7 re-checks every generated claim against
the retrieved evidence set and discards anything uncited, and N3 omits rather than fills.
The result payload carries `sources` (the evidence) and a `grounding` summary.

**Model choice:** `deepseek/deepseek-v4.1-flash` via OpenRouter. Do NOT switch to
`google/gemini-3.7-flash`: it is a reasoning model that returns `content: null` with the
budget spent on reasoning tokens, which breaks JSON extraction. Note that
deepseek-v4.1-flash ALSO spends reasoning tokens (observed 776–1471), so `max_tokens`
must cover reasoning + content combined or content comes back truncated.

## The Live Mastra Agent

`mastra/` is a real, running agent — not a stub. It exposes real tools:

| Tool | Implementation |
|---|---|
| `anakin-search` | Anakin MCP `search` over stdio (`anakin_mcp.ts`) |
| `anakin-reddit-posts` | Anakin MCP `wire_read_action` (`rt_subreddit_posts`) |
| `anakin-scrape` | Anakin MCP `scrape` |
| `google-places-nearby` | Places Nearby, haversine-filtered |
| `google-geocode` | Geocoding API |

`chat_bridge.ts` polls the Helix `/api/chat` queue, runs the agent, and writes the reply
back — the browser cannot reach a localhost port. Registered in `workspace_watchdog.py`
(`check_mastra_chat_bridge`) for auto-revival.

## API Surface (backend/server.py)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Status: `{status, gmaps_active, anakin_active}` |
| `/api/config` | GET | Returns `{google_maps_key}` from env |
| `/api/research` | POST | Full research run. Body: company_name, business_type, offering, target_city, sample_customers, lat, lng, radius_meters, user_id |
| `/api/simulate` | POST | DEPRECATED alias for `/api/research` |
| `/api/chat` | POST | Mastra agent multi-turn reasoning. Body: {message, context, user_id} |

Helix routes (same table, `/api/research-runs` is current, `/api/simulations` is a live alias):
`GET|POST /api/research-runs` → `simulations` table; `GET|POST /api/chat` → `chat_messages` table.

## Environment & Credentials

- `GOOGLE_MAPS_API_KEY` — in container env. Works for server-side Geocoding/Places REST.
  Maps JavaScript API enabled as of 2026-09-14; key is embedded in frontend loader.
- `ANAKIN_API_KEY` — configured in `/opt/data/config.yaml` under `mcp_servers.anakin`
  (stdio `npx @anakin-io/mcp@latest`). Client wrapper at `/opt/data/anakin_client.py`.
- Firebase config is embedded in `frontend/index.html` (project `intelligence-8c622`).
  Authorized domains must include `syndicate-app.jai.allr.work` and `allr.work`.
- **Google provider must stay enabled** in Firebase Console → Authentication →
  Sign-in method (project `intelligence-8c622`); without it the popup fails with
  `auth/operation-not-allowed`. Popup-blocked browsers fall back to
  `signInWithRedirect` automatically.
- **Firestore** stores registration profiles in `users/{uid}` (company, useCase,
  createdAt, lastSeenAt). Suggested rule: `match /users/{uid} { allow read, write:
  if request.auth.uid == uid; }`.
- Claude Code CLI is installed but UNAUTHENTICATED (needs ANTHROPIC_API_KEY or OAuth).

## Brand & Design Tokens

Material 3 Expressive, "Sovereign Gold on Obsidian" theme:
- Gold `#FFB84D` (primary/actions) · Radar Cyan `#4DEEEA` (spatial/touchpoints)
- Background `#100E0B` · Surface ladder `#0B0907 → #332D23`
- Fonts: Plus Jakarta Sans (UI), JetBrains Mono (data/meta)
- Full token spec: https://syndicate-ui-kit.jai.allr.work

## Known Pitfalls (Battle-Tested)

1. HeatmapLayer throws in Maps JS v3.65+ — use circle-glow overlays.
2. Google key without JS-API referrer permissions → InvalidKeyMapError → Leaflet fallback.
3. Helix API is same-origin only from the app domain; internal calls use
   `http://helix:8080` with `Host: syndicate-app.jai.allr.work` header.
4. When testing endpoints from inside this container, use `127.0.0.1:8090` directly.
5. Worker daemon is registered in `/opt/data/scripts/workspace_watchdog.py`
   (`check_syndicate_worker`) for auto-revival — do not remove.
6. **No startup scan, so no first-run auth interstitial.** The auth modal opens only when a
   product action is attempted (`triggerSimulation()` / `sendChatMessage()`) without a signed-in
   user or guest session. The app loads straight into a clean, idle state.
