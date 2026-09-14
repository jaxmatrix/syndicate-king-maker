# Decommission "Simulation" → Wire the Real Research Pipeline

> **For Allr:** Execute task-by-task. Commit after every task. This is the real application now —
> there is no simulator, no mock, and no fabricated field anywhere in the pipeline.

**Goal:** Remove the "simulation" framing from Syndicate entirely and replace every faked or
hardcoded research artefact with real, cited research that actually runs, so the application works
end-to-end as an autonomous commercial site-selection product.

**Architecture:** The engine becomes a 6-node evidence pipeline. Retrieval is real
(Anakin search + Reddit Wire reads + Google Places); reasoning is real
(DeepSeek v4.1 flash over retrieved evidence); and every claim carries a source URL so nothing can
be asserted without provenance. A validator drops any claim whose citation is not present in the
retrieved evidence set, which makes fabrication structurally impossible rather than merely
discouraged.

**Tech Stack:** Python 3.13 (`/opt/hermes/.venv/bin/python3`), Anakin MCP over stdio JSON-RPC,
OpenRouter (`deepseek/deepseek-v4.1-flash`), Google Places REST, FastAPI on :8090, single-file SPA
on Helix, Helix table-backed queue.

---

## Capability Audit (verified live, 2026-09-14)

Everything below was actually executed and returned data. The plan promises only this.

| Capability | Call | Verified result |
|---|---|---|
| Web/community search | `AnakinMCPClient.search()` | ✅ Real snippets, real subreddit names (`r/restaurantowners`), real URLs |
| Read a subreddit | Wire `rt_subreddit_posts` `{subreddit, limit}` | ✅ Real posts: `title`, `selftext`, `permalink`, `created_utc` |
| Other Reddit actions | `rt_subreddit_info`, `rt_search`, `rt_popular_subreddits` | ✅ Discovered in catalog (not yet exercised) |
| Job listings | Wire `act_jobs_lever_co_company_job_listings` `{company_slug}` | ⚠️ **Only** Lever-hosted companies (`netflix`/`stripe` → HTTP 404). Not a general job search |
| Building discovery | Places Nearby + haversine | ✅ Real anchored coordinates |
| Touchpoints | Places Nearby per site | ✅ Real |
| LLM extraction | OpenRouter `deepseek/deepseek-v4.1-flash` | ✅ `finish_reason=stop`, content present, 0 reasoning tokens, strict JSON with per-claim source+quote |
| ~~LLM~~ | `google/gemini-3.7-flash` | ❌ Reasoning model: `content: null`, `MAX_TOKENS` at 50. **Do not use** |
| ~~LLM~~ | `deepseek/deepseek-v4.1` (non-flash) | ❌ HTTP 400 — not available |

**Consequence for design:** there is no general-purpose job-search Wire action, so demand signals
must come from real *search* results, and the field must be **omitted when nothing real returns** —
never populated with an assumed string (which is exactly what the old `hiring_signals` did).

---

## Current State (the fake surface being removed)

`backend/engine.py` currently fabricates or hardcodes:

1. `run_icp_problem_mining()` — returns one of **three hardcoded pain-point lists** selected by a
   substring match on `business_type`. It calls Anakin search but **discards the result**, keeping
   only `len(...)` as `anakin_search_hits`.
2. `online_spaces` — hardcoded `["r/bayarea", "r/sanfrancisco", "LinkedIn Local SF B2B Network",
   "Fishbowl Corporate & Facility Groups", "Nextdoor Commercial Districts"]`. Hard-wired to SF while
   the product claims global coverage.
3. `buying_triggers` — three hardcoded strings.
4. `hiring_signals` — the literal string
   `"Active openings in Management, Ops, and Facilities detected via Anakin Indeed Wire"` attached to
   **every** building. No such call is ever made. This is a false claim shown to users.

`frontend/index.html` and `backend/{server,worker}.py`, `test_suite.py`, `CLAUDE.md`, `PLAN.md` all
carry "simulation" naming (`/api/simulate`, `/api/simulations`, `execute_syndicate_simulation`,
`triggerSimulation`, "Simulation complete!").

---

## Target Research Pipeline

```
  N1  Evidence retrieval   (REAL)   Anakin search → subreddits → rt_subreddit_posts
        │                           → evidence[]: {id,url,title,quote,date,source}
        ▼
  N2  ICP extraction       (REAL)   DeepSeek v4.1 flash over evidence[] ONLY
        │                           → pain_points[{claim,source,quote}], buying_triggers[],
        │                             icp_titles[], online_spaces[]
        ▼
  N3  Demand signals       (REAL)   Anakin search for hiring/expansion intent in the area
        │                           → signals[] with url; EMPTY when nothing real returns
        ▼
  N4  Site discovery       (REAL)   Places Nearby + haversine radius        [already anchored]
        ▼
  N5  Touchpoints          (REAL)   Places Nearby around top sites          [already anchored]
        ▼
  N6  Hotspot centroids    (REAL)   Centroid of real member coordinates     [already anchored]

  N7  Validator            (GUARD)  Drop any N2 claim whose source is not in evidence[].
                                    Drop any N3 signal without a URL.
```

**Invariant that makes fabrication impossible:** `N7` re-checks every generated claim against the
retrieved evidence. A claim with no matching source is discarded, not rendered. Combined with N3's
omit-when-empty rule, no field in the result can contain unbacked text.

---

## Naming Contract (decide once, apply everywhere)

| Old | New |
|---|---|
| `execute_syndicate_simulation()` | `execute_research_run()` |
| `triggerSimulation()` (JS) | `runResearchScan()` (JS) |
| `simulation` table / `/api/simulations` | keep table name (`research_runs` would need a Helix migration); add `/api/research-runs` routes, keep old paths as aliases |
| `/api/simulate` (FastAPI) | `/api/research` (keep `/api/simulate` as alias for one cycle) |
| "Simulation complete!" | "Research run complete." |
| `status: done:<id>` | unchanged (queue mechanics are correct) |

> Table rename is deliberately **out of scope**: the Helix `database` resource declares tables and a
> rename risks the queue. Add the new route paths first, migrate callers, remove aliases later.

---

## Tasks

### Task 1 — Rename `execute_syndicate_simulation` → `execute_research_run`

**Files:** modify `backend/engine.py` (pipeline method + `__main__` block), `backend/worker.py:81`

**Steps:**
1. Rename the method; keep a thin `execute_syndicate_simulation = execute_research_run` alias with a
   `# DEPRECATED` comment so any in-flight caller keeps working.
2. Update `worker.py` call site.
3. Verify: `python3 -c "from engine import SyndicateGraphEngine; print(hasattr(SyndicateGraphEngine,'execute_research_run'))"`
4. Commit: `refactor(engine): rename simulation pipeline to research run`

### Task 2 — Add an evidence-retrieval node (N1) with real Reddit reads

**Files:** modify `backend/engine.py`

**Steps:**
1. Add `AnakinMCPClient.wire_read` already exists — add `reddit_posts(subreddit, limit)` convenience.
2. New method `collect_evidence(business_type, offering, sample_customers, limit=12) -> dict`:
   - For 3 sector-shaped queries, call `self.anakin.search(q, limit=5)`.
   - Harvest `results[].snippet`, `.url`, `.title`; extract subreddit names via regex
     `r/([A-Za-z0-9_]+)` against snippets **and** URLs.
   - Take the top 2 subreddits by hit count, call `rt_subreddit_posts` (`limit=5`), and append real
     posts (`title`, `selftext` trimmed, `permalink` → absolute, `created_utc`).
   - Emit `evidence: [{id, source, title, quote, url, date}]`, each with a stable `id` (`e1`, `e2`…).
   - **Never** invent a subreddit: if search returns none, `evidence` is short and N2 says so.
3. Guard: wrap each network call; a failure degrades to fewer evidence items, never fake ones.
4. Verify: run the node alone and print `len(evidence)`, plus 2 real URLs.
5. Commit: `feat(research): real evidence retrieval from search + subreddit Wire reads`

### Task 3 — Add the LLM extraction node (N2) on DeepSeek v4.1 flash

**Files:** create `backend/intelligence.py`; modify `backend/engine.py`

**Steps:**
1. `backend/intelligence.py` exposing `extract_icp(evidence, company, business_type, offering) -> dict`.
   - Model **`deepseek/deepseek-v4.1-flash`** (do NOT use gemini-3.7-flash: it returns null content).
   - Read `OPENROUTER_API_KEY` via the existing `.env` loader in `engine.py`.
   - `response_format={"type":"json_object"}`, `max_tokens=1600`, `temperature=0.2`.
   - Prompt: "Use ONLY the numbered EVIDENCE. Cite the evidence id for every claim. Return strict
     JSON `{pain_points:[{claim,evidence_id,quote}], buying_triggers:[{claim,evidence_id}],
     icp_titles:[...], online_spaces:[...]}`. If the evidence does not support a field, return an
     empty array — do not guess."
   - Tolerate: `content: null`, non-JSON, HTTP failure → return `{}` and let the caller degrade.
2. Wire into the engine as `run_icp_extraction(evidence, ...)`.
3. Verify: feed the probe evidence used during recon; expect ≥2 pain points each carrying an
   `evidence_id` that exists in the input.
4. Commit: `feat(research): DeepSeek v4.1 evidence-grounded ICP extraction`

### Task 4 — Delete the hardcoded ICP/pain/online-space lists

**Files:** modify `backend/engine.py` (`run_icp_problem_mining`)

**Steps:**
1. Remove the three hardcoded `pain_points` lists, the hardcoded `online_spaces`, and the hardcoded
   `buying_triggers`.
2. Replace `run_icp_problem_mining` with a thin composition of N1 + N2 that returns
   `{evidence, pain_points, buying_triggers, icp_titles, online_spaces, evidence_count}`.
3. `_derive_icp_titles` may stay as a fallback **only** when extraction returns no titles, and must
   be labelled `derived_fallback: true` in the payload.
4. Verify: `grep -n "r/bayarea\|Fishbowl\|ridiculous fees\|Nextdoor Commercial" backend/engine.py` → no matches.
5. Commit: `refactor(research): remove hardcoded pain points, subreddits and triggers`

### Task 5 — Real demand signals (N3), omit-when-empty

**Files:** modify `backend/engine.py`; modify `backend/worker.py` only if payload shape changes

**Steps:**
1. New `collect_demand_signals(business_type, offering, area_label) -> list`:
   - Anakin search for `"<business_type>" hiring OR expanding OR "new office" <area_label>`
     and an ICP-role variant.
   - Keep only items with a real `url`; shape `{claim, url, date, source}`.
   - Return `[]` when nothing usable — and the caller must omit the field rather than substitute text.
2. If a result names a Lever-hosted company, optionally enrich via
   `act_jobs_lever_co_company_job_listings {company_slug}`; treat 404 as "no data", never as failure
   of the run.
3. **Delete** the fabricated per-building `hiring_signals` string entirely.
4. Verify: `grep -n "Anakin Indeed Wire" backend/engine.py` → no matches.
5. Commit: `feat(research): real demand signals; drop fabricated hiring_signals`

### Task 6 — Provenance validator (N7)

**Files:** modify `backend/engine.py`

**Steps:**
1. `validate_grounding(result, evidence) -> result`:
   - Drop any `pain_points`/`buying_triggers` entry whose `evidence_id` is missing from `evidence`.
   - Drop any `demand_signals` entry lacking `url`.
   - Attach `grounding: {claims_total, claims_kept, claims_dropped}`.
2. Call it last in `execute_research_run`; add `sources` (= the evidence list) to the payload.
3. Verify: inject a fake claim with `evidence_id: "e999"` → it must be dropped and counted.
4. Commit: `feat(research): grounding validator — no claim without a real source`

### Task 7 — API rename with backwards-compatible alias

**Files:** modify `backend/server.py`; new Helix ops file `helix_research_route.json`; deploy

**Steps:**
1. FastAPI: add `POST /api/research`; keep `/api/simulate` delegating to the same handler
   (deprecated).
2. Helix: add `/api/research-runs` (GET/POST) routes on the same table; keep `/api/simulations`.
3. Verify both paths return identical results.
4. Commit: `feat(api): /api/research with /api/simulate kept as a deprecated alias`

### Task 8 — Frontend: rename + surface real evidence

**Files:** modify `frontend/index.html`

**Steps:**
1. Rename `triggerSimulation` → `runResearchScan`, update all `onclick`s, and swap queue paths to
   `/api/research-runs`.
2. Telemetry: relabel steps to the real nodes and print real counts
   (evidence items, cited pain points, sites, touchpoints, hotspots). Add a **Sources** block listing
   real evidence URLs (clickable).
3. Remove "Simulation complete!" and every remaining "simulation" string.
4. Show `grounding.claims_dropped` when > 0 (transparency).
5. Verify: `node --check` on the extracted inline script; then browser-load the live app and confirm
   `currentSimData === null` and status `IDLE — NO SCAN RUN`.
6. Commit: `feat(ui): rename to research runs and surface cited evidence`

### Task 9 — Tests

**Files:** modify `test_suite.py`; add `verify_research.py`

**Steps:**
1. Add: `test_08_no_hardcoded_research` (grep-style assertion over the engine source).
2. Add: `test_09_evidence_grounding` (live run → every kept claim's `evidence_id` exists in `sources`).
3. Add: `test_10_demand_signals_omit_when_empty` (no `url`-less signal ever present).
4. `verify_research.py`: prints evidence count, cited pain points with quotes, and source URLs.
5. Verify: full suite green.
6. Commit: `test: grounding, no-hardcoded-research and demand-signal invariants`

### Task 10 — Docs + deploy

**Files:** modify `CLAUDE.md`, `PLAN.md`

**Steps:**
1. Replace the research-pipeline fake description with the real 6-node + validator design; document
   the DeepSeek model choice and the gemini null-content trap.
2. Deploy to Helix; report the version + URL.
3. Commit: `docs: real research pipeline; deploy v13`

---

## Files Likely To Change

```
backend/engine.py        rename, N1, N3, N6 validator, remove hardcoded lists
backend/intelligence.py  NEW — DeepSeek extraction
backend/server.py        /api/research (+ alias)
backend/worker.py        call-site rename
frontend/index.html      rename, evidence/sources UI
test_suite.py            +3 tests
verify_research.py       NEW — evidence provenance proof
helix_research_route.json NEW — Helix ops
CLAUDE.md, PLAN.md       docs
```

## Risks & Tradeoffs

- **Live-API dependence in tests.** N1/N3 hit real Anakin; the suite already tolerates network
  dependency, but grounding tests must assert *shape and provenance*, not specific counts, or they
  will flake on a quiet day. Unit-test N2 with a stubbed LLM response.
- **Latency.** N1 adds ~2 search calls + 2 subreddit reads (~15–25s observed). Acceptable for a
  research run; the queue already decouples it from the request. Per-run cost is a few Anakin credits
  plus ≤2k LLM tokens.
- **Subreddit quality.** A sector query can surface an off-topic subreddit. Mitigate by ranking by
  hit count and skipping subreddits whose name matches the sector poorly; never broaden beyond
  retrieved evidence.
- **Grounding validator is strict.** It may drop legitimate-but-uncited claims — that is the intended
  direction of failure, and `claims_dropped` makes it visible.
- **Open question:** whether to keep the deprecated aliases permanently or delete them after one
  deploy cycle. Plan assumes delete later; harmless to keep.

## Definition of Done

- `grep -rIi "simulation" backend/ frontend/ test_suite.py` returns nothing user-visible.
- No hardcoded pain points, subreddits, triggers, or the `hiring_signals` string anywhere.
- A live run returns pain points that each cite a real evidence URL, and `sources` is non-empty.
- Anchoring guarantees from the baseline are preserved (suite + `verify_anchoring.py` green).
- Every task landed as its own commit.