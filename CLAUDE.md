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
├── test_suite.py        # Python unittest suite (4 tests, all passing)
├── backend/             # FastAPI + Graph AI engine (Python 3.13)
│   ├── engine.py        # SyndicateGraphEngine: Anakin Wire + Google Places + Voronoi clustering
│   ├── server.py        # FastAPI app on :8090 (/api/health, /api/simulate, /api/chat, /api/config)
│   └── worker.py        # Helix queue daemon: polls /api/simulations, runs engine, writes results
├── frontend/            # Single-file SPA (index.html) — deployable to Helix as static zip
│   └── index.html       # 3-column command center, Firebase auth, Google Maps JS + Leaflet fallback
└── mastra/              # Mastra TypeScript agent definitions
    ├── agent.ts         # syndicateKingMakerAgent + 4 typed tools (createTool/zod)
    ├── index.ts         # Mastra instance registration
    └── package.json     # `npm run test` → runs ../test_suite.py
```

## Key Commands

```bash
# Run full verification suite (backend health, global sim, chat, live Helix frontend)
npm --prefix /opt/data/syndicate/mastra run test

# Start backend (background)
/opt/hermes/.venv/bin/python3 /opt/data/syndicate/backend/server.py

# Start Helix queue worker (background)
/opt/hermes/.venv/bin/python3 /opt/data/syndicate/backend/worker.py

# Deploy frontend to Helix (zip contents, then update app)
python3 /opt/allr/skills/helix/scripts/helix_client.py zip /opt/data/syndicate/frontend /tmp/syndicate_app.zip
python3 /opt/allr/skills/helix/scripts/helix_client.py update cf126906-b884-47b3-a1d8-aec3b9d44dd3 /tmp/syndicate_app.zip "vN-message"

# Direct Anakin MCP client helper (used by engine.py; lives at /opt/data/anakin_client.py)
python3 /opt/data/anakin_client.py
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
# Project suite (7 tests) — needs backend + worker running
npm --prefix /opt/data/syndicate/mastra run test

# Anchoring proof: shared pins must not move when the anchor moves
/opt/hermes/.venv/bin/python3 /opt/data/syndicate/verify_anchoring.py

# End-to-end proof through the real Helix queue path
/opt/hermes/.venv/bin/python3 /opt/data/syndicate/verify_e2e.py
```

## API Surface (backend/server.py)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Status: `{status, gmaps_active, anakin_active}` |
| `/api/config` | GET | Returns `{google_maps_key}` from env |
| `/api/simulate` | POST | Full 5-node graph simulation. Body: company_name, business_type, offering, target_city, sample_customers, lat, lng, radius_meters, user_id |
| `/api/chat` | POST | Mastra agent multi-turn reasoning. Body: {message, context, user_id} |

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
