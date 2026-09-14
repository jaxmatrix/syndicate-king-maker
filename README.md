# Syndicate: The King Maker

A research platform for B2B commercial expansion and physical site selection.

Given a business profile and a target area, Syndicate gathers evidence about the sector,
identifies the organisations and locations that matter, and recommends where to establish a
commercial presence — with every conclusion traceable to a source.

**Live instance:** https://syndicate-app.jai.allr.work

---

## Capabilities

| Capability | Description |
|---|---|
| Sector evidence | Retrieves topical material from the live web and community forums, keeping the source of every item |
| ICP intelligence | Derives pain points, buying triggers, decision-maker titles and online communities from that evidence |
| Demand signals | Finds hiring and expansion activity relevant to the target profile |
| Site discovery | Locates real commercial properties within a chosen radius of any coordinate on Earth |
| Touchpoint mapping | Maps cafes, dining and transit points around the strongest sites |
| Hotspot scoring | Ranks clusters of real sites by decision-maker density and recommends outlet placement |
| Conversational research | An interactive agent that runs further research on request, using the same live data sources |

## How it works

A scan executes a sequence of research stages. Each stage either retrieves data from an external
source or derives its output from data already retrieved.

| Stage | Purpose | Source |
|---|---|---|
| **N1** Evidence retrieval | Search the sector, harvest the communities referenced, and read the relevant discussions in full | Anakin MCP |
| **N2** Grounded extraction | Derive ICP intelligence from the retrieved evidence only, citing an item per claim | DeepSeek v4.1 |
| **N3** Demand signals | Find hiring and expansion activity for the target roles | Anakin MCP |
| **N4** Site discovery | Locate commercial properties within the scan radius | Google Places |
| **N5** Touchpoints | Map dining, coffee and transit points around the top sites | Google Places |
| **N6** Hotspot clustering | Place each hotspot at the centroid of its member sites | Derived |
| **N7** Grounding validation | Discard any claim whose cited source is absent from the evidence | Derived |

## Design principles

1. **Grounded output.** Every claim names the source it came from. A claim that cannot be traced
   to retrieved evidence is discarded before it reaches the client.
2. **Deterministic geography.** Coordinates come from Google Places and are filtered to the scan
   radius. A given place always resolves to the same coordinate, so results are geographically
   stable and independent of which query surfaced them.
3. **Explicit absence.** When a data source yields nothing, the corresponding field is omitted
   rather than estimated.
4. **On-demand results.** Nothing is displayed until a scan is requested. Results are produced by
   the pipeline, never supplied by the client.
5. **Fail loudly.** A missing API key or absent scan anchor produces an explicit error rather than
   an empty result set.

## Architecture

```
Browser (single-file SPA)
   │  POST a pending row, then poll for its own id
   │  (the browser reaches the backend through the gateway, not a local port)
   ▼
Gateway API
   ├── /api/research-runs  →  research queue table
   └── /api/chat           →  chat queue table
   │
   ├── backend/worker.py        consumes the research queue → runs the research pipeline
   └── mastra/chat_bridge.ts    consumes the chat queue     → runs the agent
```

Both queues follow the same contract: a client writes a pending row carrying an id it generated,
the consumer executes the work, and the client polls for a completion record matching that id.

## Project layout

```
backend/
  engine.py          research stages N1-N7; evidence, sites, touchpoints, hotspots, grounding
  intelligence.py    evidence-grounded ICP extraction
  server.py          HTTP API
  worker.py          research queue consumer
frontend/
  index.html         single-file SPA: map, telemetry, cited evidence panel, agent chat
mastra/
  env.ts             environment loading (imported first)
  anakin_mcp.ts      MCP client (stdio) for the Anakin tool surface
  tools_anakin.ts    search, community reads, page scraping
  google_maps.ts     Places Nearby (radius-filtered) and Geocoding
  tools_maps.ts      agent-facing map tools
  agent.ts           the King Maker agent
  chat_bridge.ts     chat queue consumer
deploy.sh            builds and deploys the frontend with injected keys
test_suite.py        integration test suite
verify_*.py          focused verification scripts
```

## Getting started

Requires Python 3.11+, Node.js 18+, and API credentials for OpenRouter, Google Maps and Anakin.

```bash
# 1. Configure
cp .env.example .env          # then fill in the keys

# 2. API
python3 backend/server.py

# 3. Research queue consumer
python3 backend/worker.py

# 4. Agent bridge
cd mastra && npm install && npx tsx chat_bridge.ts
```

The frontend is a static directory and can be served by any web host. `deploy.sh` builds it with
the keys injected from `.env` and publishes it to the configured host.

## Configuration

| Variable | Required | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | yes | Grounded extraction and the research agent |
| `GOOGLE_MAPS_API_KEY` | yes | Places Nearby and Geocoding; site discovery cannot run without it |
| `ANAKIN_API_KEY` | yes | Evidence retrieval and demand signals |
| `SYNDICATE_LLM_MODEL` | no | Extraction model. Defaults to `deepseek/deepseek-v4.1-flash`. Must be a non-reasoning model, since reasoning models return empty content and break structured output. |
| `SYNDICATE_WORKER_CONCURRENCY` | no | Concurrent research runs. Defaults to `3`. |
| `SYNDICATE_PENDING_MAX_AGE_S` | no | Age beyond which a pending request is no longer claimed. Defaults to `1800`. |
| `HELIX_GATEWAY_URL` | no | Gateway base URL for the queue consumers. |

Frontend keys are placeholders in the repository and are injected at deploy time by `deploy.sh`.

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Service status and credential availability |
| `/api/config` | GET | Client-facing runtime configuration |
| `/api/research` | POST | Run the full research pipeline for one anchor |
| `/api/chat` | POST | Query the research agent |

**Research request body**

```json
{
  "company_name": "string",
  "business_type": "string",
  "offering": "string",
  "target_city": "string",
  "sample_customers": "string",
  "lat": 37.7895,
  "lng": -122.398,
  "radius_meters": 1500
}
```

`lat`, `lng` and `radius_meters` define the scan area. Omitting the coordinates returns an
`anchor_required` error.

**Response highlights**

| Field | Contents |
|---|---|
| `sources` | The retrieved evidence, each with an id and a URL |
| `icp_intelligence` | Pain points, buying triggers and communities, each citing a source id |
| `demand_signals` | Hiring and expansion findings, each with a URL |
| `target_buildings` | Discovered sites with coordinates, addresses and distances |
| `offline_touchpoints` | Mapped dining, coffee and transit points |
| `hotspot_recommendations` | Ranked clusters with centroid coordinates |
| `grounding` | Claim counts kept and discarded, plus the valid source ids |
| `counts` | Totals per category |

## Verification

```bash
python3 test_suite.py          # integration suite: geography, grounding, agent
python3 verify_anchoring.py    # coordinate stability across differing scan anchors
python3 verify_e2e.py          # full queue round-trip
python3 verify_research.py     # cited claims and source integrity
python3 verify_live_chat.py    # the agent answers using real tool calls

cd mastra
npx tsx tools_test.ts          # verifies each tool returns real data
npx tsx agent_test.ts          # verifies the agent invokes tools rather than answering from memory
```

The suite and the research verification scripts require the API, the queue consumer and the agent
bridge to be running.

## Operational notes

- **Scan duration.** A full scan typically takes one to four minutes. Evidence retrieval dominates:
  the Anakin client starts a separate MCP subprocess per tool call, and a scan makes several.
  Reusing a single long-lived MCP process would reduce both latency and process overhead.
- **Queue records.** Completion is published as a new record rather than mutating the original, so
  original pending records persist. Consumers therefore only claim requests newer than
  `SYNDICATE_PENDING_MAX_AGE_S`, and clients match results by the id they generated.
- **Google Maps requirement.** Site discovery is entirely dependent on the Places API. A scan
  without credentials returns an explicit error instead of an empty result.
- **Demand-signal precision.** Results are real and URL-backed, but a keyword search can surface
  general careers pages alongside specific postings.
- **Single storefront.** The SPA ships as one HTML file with no build step, by design.

## License

MIT — see [LICENSE](LICENSE).