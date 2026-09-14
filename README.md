# Syndicate: The King Maker

Autonomous B2B commercial expansion and physical site-selection research. Given a business
profile and a target area, Syndicate retrieves real evidence about the sector, finds the
companies and locations that matter, and recommends where to open an outlet — with every
claim traceable to a source.

**Live:** https://syndicate-app.jai.allr.work

---

## What it actually does

There is **no simulator**. A research run executes a real pipeline:

| Node | Purpose |
|---|---|
| **N1** Evidence retrieval | Anakin MCP search → harvest referenced subreddits → scrape the real Reddit threads |
| **N2** Grounded extraction | DeepSeek v4.1 flash reasons over the retrieved evidence **only**, citing an id per claim |
| **N3** Demand signals | Real hiring/expansion signals with URLs; omitted entirely when none are found |
| **N4** Site discovery | Google Places Nearby, haversine-filtered to the scan radius |
| **N5** Touchpoints | Places Nearby for executive coffee / dining / transit around top sites |
| **N6** Hotspot clustering | Centroids of the **real** member coordinates |
| **N7** Grounding validator | Discards any claim whose citation is absent from the evidence |

### Standing invariants

1. **No invented data.** Every claim traces to a retrieved source; N7 enforces it and N3 omits
   rather than estimates.
2. **No pre-baked results.** Nothing renders until you run a scan. There is no client-side
   result generator.
3. **Anchored pins.** Result coordinates come from Google Places and never inherit the dropped
   pin's position — moving the pin does not move a single result.
4. **Real tool calls only.** If a tool fails, the UI says so rather than substituting plausible
   wording.

---

## Architecture

```
Browser (single-file SPA on Helix)
   │  POST pending row + poll for its own id  (a hosted browser cannot reach localhost)
   ▼
Helix API  ──  /api/research-runs → simulations table
           └─  /api/chat          → chat_messages table
   │
   ├── backend/worker.py      Python queue daemon → engine.py research pipeline
   └── mastra/chat_bridge.ts  Node queue daemon  → Mastra agent (real tool calls)
```

## Layout

```
backend/
  engine.py        research nodes N1-N7 (evidence, sites, touchpoints, hotspots, grounding)
  intelligence.py  DeepSeek v4.1 evidence-grounded ICP extraction
  server.py        FastAPI on :8090 (/api/research, /api/chat, /api/health, /api/config)
  worker.py        queue daemon, thread-pooled
frontend/
  index.html       single-file SPA, Google Maps, telemetry + cited evidence panel
mastra/
  anakin_mcp.ts    native MCP client over stdio to @anakin-io/mcp
  tools_anakin.ts  anakin-search / anakin-reddit-posts / anakin-scrape
  google_maps.ts   Places Nearby (haversine) + Geocoding
  tools_maps.ts    google-places-nearby / google-geocode
  agent.ts         King Maker agent (DeepSeek v4.1 via OpenRouter)
  chat_bridge.ts   polls the Helix chat queue and runs the agent
```

## Setup

```bash
# 1. secrets
cp .env.example .env            # then fill in the keys

# 2. backend
python3 backend/server.py       # :8090
python3 backend/worker.py       # queue daemon

# 3. agent bridge
cd mastra && npm install && npx tsx chat_bridge.ts

# 4. frontend — any static host; this project deploys to Helix
```

### Required keys

| Key | Used for |
|---|---|
| `OPENROUTER_API_KEY` | N2 extraction and the Mastra agent |
| `GOOGLE_MAPS_API_KEY` | Places Nearby + Geocoding |
| `ANAKIN_API_KEY` | Anakin MCP (search, scrape, reddit wire) |

## Verification

```bash
python3 test_suite.py            # 11 tests: anchoring, grounding, live agent
python3 verify_anchoring.py      # proof: shared result pins never move with the anchor
python3 verify_e2e.py            # proof: full queue round-trip
python3 verify_research.py       # proof: cited claims, no hardcoded wording
python3 verify_live_chat.py      # proof: the agent answers with real tool calls
cd mastra && npx tsx tools_test.ts && npx tsx agent_test.ts
```

## Known limitations

- **Runs take 1–4 minutes.** The Anakin client spawns a fresh `npx` MCP subprocess per tool
  call (~7 per run). Reusing one persistent MCP process — as the Node side already does — is
  the obvious optimisation.
- **Queue rows are append-only.** Completion is published as a new row, so the original stays
  `pending`; the worker uses a freshness window to avoid re-running history.
- Demand-signal precision varies; some hits are career pages rather than specific postings.
  They are real and URL-backed.
- Requires a map/Places key to produce sites at all — a keyless engine errors rather than
  returning an empty "success".

## License

MIT — see [LICENSE](LICENSE).
