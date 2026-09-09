# UPlate Search — Build Spec & Cursor Orchestration README

> Every food app indexes restaurants. We index food.
>
> UPlate Search is a **unified item-level food index** — dining halls and off-campus restaurants in one collection — searched in plain English, filtered by constraints that are structurally impossible to loosen, and ranked by how well a dish fits *your* targets. Results land on a map pinned by dish, not by venue, and end in a logged meal.

**Stack: React + Vite (frontend) · FastAPI + Python (backend) · Typesense v30.x (self-hosted, Docker).**

> **Local deltas from this original spec (agreed 9/8, hackathon night):**
> 1. **NL layer = Claude API** (`api/app/llm/`), not Typesense's NL Search Models API — Typesense's built-in NL feature doesn't take Anthropic as a provider, and we have Claude credits. Claude turns the sentence into `{filter_by, sort_by, intent}`; we AND our explicit hard-exclusion `filter_by` on top server-side, so the safety invariant is preserved identically.
> 2. **Typesense hosting:** Docker where available; on the Docker-less Windows machine, native Linux binary inside WSL2 (see README quickstart). Same port 8108 either way.
> 3. **Hackathon reality:** seed data is hardcoded/prefilled and labeled by provenance in the UI. Endpoints are real. Phases 0–5 are tonight's target, 6 if time allows.

---

## 0. How to use this README with Cursor / Claude Code

This is a **phased, test-first build plan**. Do not paste the whole thing and say "build it." The search-quality work is subtle and an agent that races ahead will hand you something that returns plausible-looking results that are silently wrong — which in an app that filters allergens is the worst possible failure mode.

1. Work **one phase at a time**. Each phase has a **`TESTS`** block and a **`PROMPT`** block. Paste `TESTS` first, get red tests, then paste `PROMPT`.
2. After each phase, run the **`VERIFY`** checklist for real before moving on.
3. `git commit` after every green phase.
4. **`GOTCHA`** blocks get pasted verbatim alongside the prompt. Those are the things that are wrong in most Typesense tutorials, or that an LLM will confidently get backwards.

**Two-person split.** Backend phases (1, 2, 3, 4, 7-api, 8-api, 10, 11) are Python. Frontend phases (5, 6, 7-ui, 8-ui, 9) are React. Phase 0 sets up both. The **API contract in §5** is the handoff — agree on it before either side starts, or you'll spend the hackathon reconciling response shapes.

---

## 1. Final product definition (decisions locked)

### The claim
Delivery apps index dishes but know nothing about what's in them. Campus nutrition apps know what's in the food but stop at the property line. Trackers know your goals but can't tell you where to eat. **We're the only thing holding nutrition, location, and personal targets in one query.**

### Core behaviors

**Situational natural-language search.** The hero query is not `"under 600 calories, no dairy"` — that's five checkboxes and a filter UI beats us. The hero query is **`"exam in an hour, don't want to crash"`**: a *situation* → a *nutritional strategy* → *real dishes near you*. Three inference steps that no checkbox UI can express.

**Two constraint classes, never blurred.**
- **Preferences** (macros, cuisine, goals) — soft. Ranked, not filtered.
- **Exclusions** (allergens, religious, medical) — hard. Filtered, and enforced *outside* the LLM's reach (see §4).

**Provenance is a shipped feature, not a disclaimer.** Every item carries where its data came from. Four tiers: `OFFICIAL_FEED` > `CHAIN_PUBLISHED` > `CROWD_VERIFIED` > `ESTIMATED`. When a hard exclusion is active, items below the verification threshold are **withheld, not down-ranked**, and the count is shown: *"6 items hidden — allergen data unverified."*

> **The safety invariant, stated once:** the failure mode is always *"we didn't show you something safe,"* never *"we showed you something dangerous."* Every design decision in this document that looks overly conservative traces back to this line.

**Reasoning trace on every search.** The interpreted strategy, the filters applied, why each item cleared them, and its provenance badge. This is the trust mechanism, not a debug view.

**Item-level map.** Pins are dishes. Clustered by venue, top-N only.

**Designed empty state.** Sparse index means "no results" is the *common* case. It shows nearest partial matches with exactly what fails ("clears everything except 40g over your carb target") and offers the camera.

**Camera as coverage strategy.** Photo → CLIP resolves it to a structured item → similarity ranked in *nutrition* space. The photo is an **input modality, never the similarity space** (see §4). This is how the long tail gets covered when ingestion can't reach it.

### Out of scope for v1
Real ingestion (phase 11 stubs the adapters), user accounts, multi-tenant campus switching beyond a config value, offline mode, delivery/ordering integration.

---

## 2. Tech stack

| Concern | Choice | Why |
|---|---|---|
| Search engine | **Typesense v30.x, Docker** | Models run on-node; no GPU billing at this data size; no wifi dependency mid-demo |
| Backend | **FastAPI + Python 3.12** | Async-native (LLM + Typesense calls are I/O-bound); Pydantic validation is load-bearing for the safety layer; same language as the ingest pipeline |
| ASGI server | **uvicorn** | Standard, `--reload` in dev |
| Typesense client | **typesense-python** | Backend only. The browser never talks to Typesense directly |
| Validation | **Pydantic v2** | Request/response schemas are the API contract, enforced at runtime |
| Frontend | **React 18 + Vite + TypeScript** | No SSR need; two-process split matches the team split |
| UI | **Tailwind + shadcn/ui** | Fast; the design work lives in tokens, not components |
| Data fetching | **TanStack Query** | Caching, loading/error states, retries — all needed because NL search is slow |
| Map | **MapLibre GL + free tiles** | No API key, no billing surprise at 2am |
| Backend tests | **pytest + pytest-asyncio** | Contract tests hit a real Typesense |
| Frontend tests | **Vitest + Testing Library** | Unit/component |
| E2E | **Playwright** | Needed for map + voice paths |
| Test Typesense | **docker-compose.test.yml** | Search behavior tests must hit a real engine; mocking Typesense tests nothing |
| NL model | **Gemini or OpenAI via Typesense NL Search Models API** | Built-in since v29 — do not hand-roll this *(local delta: Claude API — see header)* |
| Text embeddings | **`ts/all-MiniLM-L12-v2`** (built-in, auto-embed) | Local, no per-index API cost |
| Image embeddings | **`ts/clip-vit-b-p32`** (built-in) | Local CLIP, phase 8 |

**Repo layout (monorepo, two apps):**
```
uplate-search/
├── docker-compose.yml              # Typesense + models volume
├── docker-compose.test.yml         # isolated Typesense for tests
│
├── api/                            # ← Python. Backend dev owns this.
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py                 # FastAPI app, CORS, routers
│   │   ├── config.py               # pydantic-settings, env
│   │   ├── schemas/
│   │   │   ├── search.py           # SearchRequest / SearchResponse / Hit / ReasoningTrace
│   │   │   ├── photo.py
│   │   │   └── log.py
│   │   ├── routers/
│   │   │   ├── search.py
│   │   │   ├── photo.py            # phase 8
│   │   │   └── log.py              # phase 7
│   │   ├── typesense/
│   │   │   ├── client.py           # admin client + scoped-key factory
│   │   │   ├── schema.py           # collection definitions, versioned
│   │   │   ├── query_builder.py    # THE core module — see §4
│   │   │   └── nl_model.py         # NL search model registration
│   │   ├── constraints/
│   │   │   ├── exclusions.py       # allergen/medical → filter_by fragments
│   │   │   ├── goals.py            # user targets → sort expressions
│   │   │   └── provenance.py       # verification thresholds
│   │   └── ingest/
│   │       ├── normalize.py        # raw item → indexed doc
│   │       ├── derive.py           # precomputed ranking axes
│   │       ├── pipeline.py         # blue/green alias swap
│   │       └── adapters/           # phase 11
│   ├── scripts/
│   │   ├── bootstrap.py            # create collections, register NL model, seed
│   │   ├── reindex.py
│   │   └── prewarm.py              # cache hero queries before demoing
│   ├── data/seed/                  # seeded items, provenance-labeled
│   └── tests/
│       ├── unit/
│       └── contract/               # against real Typesense
│
└── web/                            # ← React. Frontend dev owns this.
    ├── package.json
    ├── vite.config.ts
    ├── src/
    │   ├── main.tsx
    │   ├── App.tsx
    │   ├── lib/
    │   │   ├── api.ts              # typed fetch wrapper → FastAPI
    │   │   └── types.ts            # MIRRORS api/app/schemas — see §5
    │   ├── components/
    │   │   ├── SearchBar.tsx
    │   │   ├── ResultCard.tsx
    │   │   ├── ReasoningPanel.tsx
    │   │   ├── WithheldNotice.tsx
    │   │   ├── EmptyState.tsx
    │   │   ├── ItemMap.tsx         # phase 6
    │   │   └── PhoneFrame.tsx      # demo shell
    │   └── hooks/
    └── tests/
        ├── unit/
        └── e2e/
```

---

## 3. Data model

**One collection, one document per dish.** Not per restaurant. This is the whole product.

```python
FOOD_ITEMS_SCHEMA = {
    "name": "food_items_v1",             # aliased as 'food_items'
    "fields": [
        {"name": "name",         "type": "string"},
        {"name": "description",  "type": "string"},
        {"name": "venue_name",   "type": "string", "facet": True},
        {"name": "venue_id",     "type": "string", "facet": True},
        {"name": "source_type",  "type": "string", "facet": True},  # dining_hall | off_campus
        {"name": "campus_id",    "type": "string", "facet": True},  # multi-campus from day one
        {"name": "location",     "type": "geopoint"},

        # --- soft: ranking inputs ---
        {"name": "tags",         "type": "string[]", "facet": True},  # warm, fried, handheld...
        {"name": "calories",     "type": "int32",    "facet": True},
        {"name": "protein_g",    "type": "float"},
        {"name": "carbs_g",      "type": "float"},
        {"name": "fat_g",        "type": "float"},
        {"name": "fiber_g",      "type": "float"},
        {"name": "sodium_mg",    "type": "int32"},

        # --- hard: exclusion inputs ---
        {"name": "allergens",         "type": "string[]", "facet": True},
        {"name": "diet_flags",        "type": "string[]", "facet": True},
        {"name": "provenance",        "type": "string",   "facet": True},
        {"name": "allergen_verified", "type": "bool",     "facet": True},

        # --- precomputed ranking axes (see GOTCHA below) ---
        {"name": "protein_density", "type": "float"},   # protein_g per 100 kcal
        {"name": "satiety_score",   "type": "float"},   # protein + fiber weighted
        {"name": "glycemic_proxy",  "type": "float"},   # crash risk
        {"name": "is_warm",         "type": "bool"},

        # --- availability ---
        {"name": "available_from", "type": "int32"},    # minutes since midnight
        {"name": "available_to",   "type": "int32"},

        {"name": "embedding", "type": "float[]",
         "embed": {"from": ["name", "description", "tags", "venue_name"],
                   "model_config": {"model_name": "ts/all-MiniLM-L12-v2"}}},
    ],
    "default_sorting_field": "calories",
}
```

**GOTCHA — why the precomputed fields exist:**
```
Typesense sort_by does NOT support arbitrary arithmetic. There is no
sort_by: "protein_g / calories". _eval() takes boolean filter expressions with custom
scores — _eval([(tags:warm):3, (tags:soup):2]):desc — and that is the only computed-scoring
primitive available. Arbitrary computed weights has been an open feature request since 2022.

Therefore: every ratio, density, or composite score MUST be computed at INGEST time in
derive.py and stored as a plain numeric field. If you find yourself wanting to compute
something inside sort_by, that's a signal you need a new derived field and a reindex — not
a cleverer query.
```

**Why `glycemic_proxy` and `satiety_score` and not `goal_fit`:** goal fit depends on the *user's* targets, which vary per request and can't be precomputed. So we precompute a small set of **canonical, user-independent axes**, then compose them at query time via `sort_by` selection and `_eval` buckets keyed to the goal. Adding a goal = adding a composition rule in `goals.py`, not a reindex.

**Second collection (phase 8), separate on purpose:**
```python
FOOD_IMAGES_SCHEMA = {
    "name": "food_images_v1",
    "fields": [
        {"name": "item_id", "type": "string"},
        {"name": "image",   "type": "image", "store": False},
        {"name": "clip_embedding", "type": "float[]",
         "embed": {"from": ["image"],
                   "model_config": {"model_name": "ts/clip-vit-b-p32"}}},
    ],
}
```

**GOTCHA — do not merge these collections:**
```
1. CLIP's text encoder errors on long inputs (typesense issue #1870 — embedding a paragraph
   with ts/clip-vit-b-p32 throws, while MiniLM handles it fine). Item descriptions are
   paragraphs. Never put descriptions in a CLIP embed field.
2. Mixing a CLIP vector and a MiniLM vector in one collection gives you two float[] fields
   with different semantics; a vector_query naming the wrong one fails SILENTLY with
   plausible-but-garbage results.
3. store: False means Typesense generates the embedding then discards the image. Keep it
   False. You are not building an image host.
Resolve photo → item_id in food_images, then look the item up in food_items. Two hops,
zero ambiguity.
```

---

## 4. The query architecture (the part worth getting right)

Everything funnels through **one** function in `query_builder.py`:

```python
def build_search_request(inp: SearchInput, ctx: UserContext) -> dict:
    """Returns the Typesense multi_search body. The ONLY place query params are assembled."""
```

### The safety invariant, mechanized

Typesense's NL search ANDs the LLM-generated filter with any explicit `filter_by` you pass. From the docs: a generated `color:red && category:shirt && price:<50` combined with an explicit `in_stock:true` yields `in_stock:true && color:red && category:shirt && price:<50`.

**This is load-bearing.** It means:

```
hard exclusions   →  explicit filter_by  →  ANDed on top of whatever the LLM decides
soft preferences  →  the LLM's job + sort_by
```

The LLM **cannot widen the result set**. It can only narrow within what the explicit filter already permits. An allergen exclusion is not a prompt instruction the model might ignore — it is a boolean AND applied after the model is done. Every "what if the LLM hallucinates and shows me peanuts" question has the same answer: it structurally cannot.

Write this as a test in Phase 3 and never let it regress.

### Query composition

| Layer | Mechanism |
|---|---|
| Intent → structured params | `nl_query=true`, `nl_model_id=<model>` *(local: Claude in `app/llm/`)* |
| Reasoning trace | `nl_query_debug=true` → raw LLM response + generated params |
| Semantic + keyword blend | Hybrid: `query_by` includes text fields **and** `embedding`; fusion tunable via `alpha` in `vector_query` |
| Hard exclusions | explicit `filter_by`, ANDed (above) |
| Provenance gate | appended to the same explicit `filter_by` when any exclusion is active |
| Distance | `filter_by: location:(lat,lng, N mi)` |
| "Nearby is nearby" | `sort_by: location(lat,lng, precision: 1 mi):asc, <goal_axis>:desc` — buckets everything within a mile into a distance tie so goal fit breaks it |
| Goal ranking | precomputed axis fields + `_eval` buckets |
| Withheld count | `multi_search`: gated query + ungated count query in **one** request; diff the totals |
| Slang | Synonyms API — "gains" → protein, dish nicknames → menu names |
| Vector bloat | `exclude_fields: "embedding"` on every search, always |

**GOTCHA — NL search operational notes:**
```
- NL search requires registering a model FIRST via the NL Search Models API with your LLM
  provider key. It is not configured per-query. scripts/bootstrap.py does this, idempotently.
  (Local delta: Claude interpreter in app/llm/ — no Typesense NL model registration.)
- nl_query adds an LLM round-trip to every search. Latency is SECONDS, not the <50ms
  Typesense advertises for keyword search. Design the UI for it (Phase 5) and pre-warm the
  demo queries.
- It is nondeterministic. The same sentence can produce different filters across runs. Fine
  for soft preferences, unacceptable for exclusions — which is exactly why exclusions never
  go through it.
- On LLM failure the API degrades: it uses the raw query as q and returns an error field in
  the response. Handle that field explicitly. Do not assume success.
```

---

## 5. The API contract (agree on this before Phase 1)

This is the handoff between the two devs. Pydantic models in `api/app/schemas/` are the source of truth; `web/src/lib/types.ts` mirrors them.

```python
# api/app/schemas/search.py
class UserContext(BaseModel):
    lat: float
    lng: float
    campus_id: str
    now_minutes: int                       # minutes since local midnight
    exclude_allergens: list[str] = []      # HARD
    diet_flags: list[str] = []             # HARD
    goal: Literal["high_protein","sustained_energy","light","none"] = "none"
    radius_mi: float = 3.0

class SearchRequest(BaseModel):
    query: str                             # natural language
    context: UserContext

class ClearedConstraint(BaseModel):
    label: str                             # "dairy-free"
    passed: bool

class Hit(BaseModel):
    id: str
    name: str
    venue_name: str
    source_type: str
    distance_mi: float
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
    provenance: Literal["OFFICIAL_FEED","CHAIN_PUBLISHED","CROWD_VERIFIED","ESTIMATED"]
    allergen_verified: bool
    cleared: list[ClearedConstraint]
    lat: float
    lng: float

class ReasoningTrace(BaseModel):
    interpreted_intent: str                # "low-glycemic, moderate protein"
    generated_filters: str | None          # from the LLM
    explicit_filters: str                  # from US — the safety layer
    chosen_sort: str
    llm_error: str | None = None
    degraded: bool = False                 # true if we fell back to keyword search

class PartialMatch(BaseModel):
    hit: Hit
    fails: list[str]                       # ["40g over your carb target"]

class SearchResponse(BaseModel):
    hits: list[Hit]
    withheld_count: int
    reasoning: ReasoningTrace
    partial_matches: list[PartialMatch] = []   # populated when hits is empty
    took_ms: int
```

**Frontend can build against this from day one** with a stub endpoint returning fixture data — Phase 5 does not need Phase 4 finished.

---

## 6. Build phases

> Format per phase: **GOAL → TESTS (write first, watch them fail) → PROMPT → GOTCHA → VERIFY**
> Tag: `[BE]` = Python, `[FE]` = React, `[BOTH]`.

---

### Phase 0 — Repo, Typesense, both apps talking `[BOTH]`

**GOAL:** FastAPI and React both running, CORS working, one passing contract test proving Python can reach Typesense, and one passing E2E proving React can reach FastAPI.

**TESTS:**
```
api/tests/contract/test_connection.py — write BEFORE any app code:
- health check returns ok
- create a throwaway collection, index one doc, retrieve by id, delete the collection
Uses a REAL Typesense from docker-compose.test.yml. No mocks. If this suite is green, every
later contract test is trustworthy.

web/tests/e2e/smoke.spec.ts:
- the app loads and successfully calls GET /api/health on the FastAPI backend, rendering
  the result. This test failing on CORS is the single most common phase-0 outcome — it
  should fail that way FIRST, then pass.
```

**PROMPT:**
```
Set up a monorepo with the exact structure in README §2.

BACKEND (api/):
- Python 3.12, pyproject.toml with: fastapi, uvicorn[standard], typesense, pydantic,
  pydantic-settings, pytest, pytest-asyncio, httpx.
- app/main.py: FastAPI app with CORSMiddleware allowing http://localhost:5173, all methods
  and headers. Add GET /api/health.
- app/config.py: pydantic-settings reading TYPESENSE_ADMIN_API_KEY, TYPESENSE_HOST,
  TYPESENSE_PORT, NL_LLM_API_KEY, NL_LLM_PROVIDER, ALLOWED_ORIGINS.
- app/typesense/client.py exporting:
    admin_client()  — uses the admin key, server-side only
    generate_scoped_search_key(filters) — scoped, search-only (used in phase 10)
  The admin key must never leave the backend process.
- pytest fixture that spins up docker-compose.test.yml, waits for /health, tears down after.

FRONTEND (web/):
- Vite + React 18 + TypeScript + Tailwind + shadcn/ui + TanStack Query.
- src/lib/api.ts: typed fetch wrapper reading VITE_API_URL, with an error path that
  surfaces non-2xx responses rather than swallowing them.
- A placeholder page that calls /api/health and displays the status.
- Playwright configured to run both servers.

ROOT:
- docker-compose.yml running typesense/typesense:30.2 with a NAMED VOLUME for /data
  (models download here and are large — a tmpfs means re-downloading CLIP every restart),
  --enable-cors, and the api key from env.
- docker-compose.test.yml: same image, different port and volume.
- .env.example for both apps.
- A Makefile or npm script that starts Typesense + uvicorn + vite together.
```

**GOTCHA:**
```
Vite dev runs on :5173, FastAPI on :8000 — every frontend call is cross-origin by
definition. Without CORSMiddleware the request fails in a way that looks like a network
error in the browser but shows a normal 200 in the uvicorn log. If the frontend "can't
reach the backend" but the backend logs look fine, it is CORS. Every time.

Do NOT ship allow_origins=["*"]. Read it from config so prod can be restricted.
```

**VERIFY:**
- `docker compose up -d` → `curl localhost:8108/health` ok
- `pytest` → connection contract tests green
- `npm run dev` in web/ → placeholder shows backend health as ok
- `npm run test:e2e` → smoke passes
- `grep -r "ADMIN" web/dist/` returns nothing

---

### Phase 1 — Schema, derived fields, seed pipeline `[BE]`

**GOAL:** `food_items` exists, seeded, every derived field correct. Blue/green from day one.

**TESTS:**
```
api/tests/unit/test_derive.py — pure functions, no Typesense:
- protein_density: 30g protein / 500 kcal → 6.0 per 100kcal
- protein_density with 0 calories → 0.0, no ZeroDivisionError
- glycemic_proxy: high-carb low-fiber scores higher than low-carb high-fiber
- satiety_score is monotonic in both protein and fiber
- is_warm derives True from tags containing warm/hot/soup, False otherwise
- normalize() RAISES on a doc missing the allergens key entirely, rather than defaulting
  to []. An empty allergen list means "verified none" — absence must never silently
  become safety-clearing.

api/tests/contract/test_schema.py:
- bootstrap creates the collection; alias 'food_items' points to v1
- reindex creates v2 and swaps the alias with zero downtime: searches issued against the
  alias DURING the swap return results from exactly one version, never 0 results
- every seeded doc round-trips: fields in == fields out
```

**PROMPT:**
```
Implement app/typesense/schema.py with FOOD_ITEMS_SCHEMA exactly per README §3.

app/ingest/derive.py: pure functions for each derived field, exported individually, matching
the unit tests. No I/O, no Typesense imports in this module.

app/ingest/normalize.py: raw seed row → indexed document. It must RAISE on a missing
allergens key — never default it. Missing allergen data means provenance ESTIMATED and
allergen_verified False, never an empty allergen list.

app/ingest/pipeline.py — blue/green, always:
  1. create food_items_v{N+1}
  2. bulk import in batches
  3. upsert alias 'food_items' → v{N+1}
  4. drop v{N-1}, keeping one previous version for rollback
Never mutate a live collection in place.

data/seed/: ~150 items — a Purdue dining hall set and an off-campus set, spread across all
four provenance tiers, real coordinates around West Lafayette. Include deliberate edge cases:
zero-calorie item, unverified-allergen item, one available only 11:00–14:00, several
near-duplicates across venues.

scripts/bootstrap.py creates + seeds. scripts/reindex.py does a full rebuild + swap.
```

**GOTCHA:**
```
Typesense generates embeddings ON THE NODE at index time, CPU-bound. At 150 docs this is
seconds. At scale it has been reported to take 30–40 minutes for ~700K records AND to leave
the node unresponsive to search queries during ingestion.

That is exactly why the pipeline is blue/green from PHASE 1 rather than retrofitted at
phase 10 — you build the new version on the side and swap an alias, so the live index never
goes dark. Do not "simplify" this to an in-place upsert because the dataset is small today.
```

**VERIFY:**
- `python scripts/bootstrap.py` → 150 docs indexed
- Unit + contract tests green
- Run `reindex.py` while curling the alias in a loop → never a 404, never an empty result set
- Spot-check three docs via the Typesense API: derived fields present and sane

---

### Phase 2 — Search core: hybrid, filters, geo `[BE]`

**GOAL:** `build_search_request` handles structured input correctly. No LLM yet — prove retrieval works before adding a nondeterministic layer on top.

**TESTS:**
```
api/tests/contract/test_search_core.py, against the seeded index:
- keyword: "chicken" returns chicken items, ranked
- semantic: "something warm and comforting" returns soups/stews even though neither word
  appears in those docs. THIS IS THE HYBRID PROOF — if it fails, query_by is missing the
  embedding field.
- alpha tuning: raising the keyword weight measurably reorders a known query
- filter: calories:<600 excludes everything over
- geo: a 1-mile radius from a campus point excludes a known item 3 miles out
- geo bucketing: with precision:1mi + sort by protein_density desc, a higher-protein item
  0.9mi away outranks a lower-protein item 0.2mi away (proves the distance tie works)
- exclude_fields: no response ever contains a raw embedding array
- availability: an item outside available_from/to is filtered when now_minutes is passed
```

**PROMPT:**
```
Implement app/typesense/query_builder.py exporting build_search_request(inp, ctx).

For this phase, input is STRUCTURED only (no natural language). Produce Typesense params:
  - query_by covering name, description, tags, venue_name AND embedding (hybrid)
  - vector_query with a tunable alpha, defaulting keyword-leaning
  - filter_by composed from structured constraints + campus_id + availability window
  - sort_by: location(lat,lng, precision: 1 mi):asc, then the goal axis desc
  - exclude_fields: 'embedding'

app/constraints/goals.py maps goal → precomputed axis:
  high_protein → protein_density desc
  sustained_energy → glycemic_proxy asc
  light → calories asc
  none → _text_match desc
Store this as a DICT, not if/elif chains — new goals must be data, not control flow.

Wire app/routers/search.py to call it. Make the contract tests pass.
```

**GOTCHA:**
```
Hybrid search only happens if the embedding field is listed in query_by ALONGSIDE the text
fields. List only text fields and you get pure keyword search that looks fine on easy queries
and silently fails every semantic one. The "warm and comforting" test exists to catch exactly
this — do not weaken it.

During hybrid search, _text_match in sort_by refers to the FUSED score, not the keyword
score. Don't try to sort on them separately.
```

**VERIFY:**
- All search-core contract tests green
- `curl` the endpoint with a semantic query; eyeball that results are sane
- Deliberately remove `embedding` from `query_by` → the "warm and comforting" test fails. Put it back. Now you know the test has teeth.

---

### Phase 3 — The safety layer `[BE]`

**GOAL:** Hard/soft separation, provenance gating, withheld counts. The phase that makes the product defensible.

**TESTS:**
```
api/tests/contract/test_safety.py — the most important suite in the repo:
- an item containing peanuts NEVER appears when peanuts are excluded, across 20 varied
  phrasings of the same query
- an item with allergen_verified=False NEVER appears when ANY exclusion is active, even if
  its allergen list does not contain the excluded allergen
- with NO exclusions active, unverified items DO appear (the gate is conditional, not global)
- withheld_count is exact: seed a known set, assert it equals the docs removed by the
  provenance gate specifically, not by other filters
- the gated query and the ungated count query arrive in ONE multi_search request
- the explicit filter_by string is never empty when exclusions are present (a bug here
  would silently disable the entire safety layer)
```

**PROMPT:**
```
Implement app/constraints/exclusions.py and app/constraints/provenance.py.

exclusions.py: maps allergen/religious/medical exclusions to filter_by fragments. Allergens
negate against allergens[]. Diet flags require presence in diet_flags[]. These fragments are
ALWAYS ANDed and ALWAYS passed as the explicit filter_by — never merged into query text,
never left to an LLM.

provenance.py: exports the verification threshold. When ANY hard exclusion is active, append
allergen_verified:true to the explicit filter_by. When none is active, omit it.

Extend query_builder to use multi_search:
  search 1 = the fully gated query
  search 2 = the same query with the provenance gate removed, per_page 0, for its found count
withheld_count = ungated_found - gated_found.

Populate Hit.cleared and Hit.provenance per README §5 — the UI renders these; the API
produces them now.
```

**GOTCHA:**
```
allergen_verified=False must gate an item OUT even when its allergen list looks clean.
"We have no verified data about this item" and "this item verifiably contains no peanuts"
are completely different claims. An app that conflates them is how someone gets hurt.

If an agent "optimizes" this by only checking the allergen array, revert it. The failure mode
we accept is a smaller result set. The failure mode we never accept is a confident-looking
result that was never verified.
```

**VERIFY:**
- Full safety suite green
- Query with a peanut exclusion → withheld_count > 0, response explains it
- Manually add a doc with `allergens: []` and `allergen_verified: False` → hidden under exclusion, visible without
- **Read the generated `filter_by` string by hand.** If you can't read it and confirm correctness, the composition is too clever — simplify it.

---

### Phase 4 — Natural language + reasoning trace `[BE]`

**GOAL:** The hero query works. `"exam in an hour, don't want to crash"` returns real dishes with a visible interpretation.

**TESTS:**
```
api/tests/contract/test_nl_search.py:
- nl_query on a simple query produces a non-empty generated filter
- THE SAFETY INVARIANT: the final applied filter CONTAINS our exclusion fragment, even when
  the LLM returns something bizarre. Assert on the applied filter, not on the LLM output.
- an LLM failure (mock a 500 from the provider) sets reasoning.llm_error and
  reasoning.degraded=True and falls back to keyword search rather than raising
- nl_query_debug output is captured into ReasoningTrace
- HERO QUERY INVARIANTS (not strict equality — the LLM is nondeterministic): for each of 3
  hero queries assert the right axis was chosen, the exclusion survived, the radius is sane
```

**PROMPT:**
```
app/typesense/nl_model.py: register an NL search model via the NL Search Models API at
bootstrap. Idempotent — check for an existing model before creating.
(Local delta: implement app/llm/interpreter.py with Claude instead.)

Extend build_search_request to accept a natural-language query. When present:
  - set nl_query=true, nl_model_id, query_by
  - STILL pass hard exclusions + the provenance gate as explicit filter_by
  - set nl_query_debug in development only
Return a ReasoningTrace per README §5.

Write the NL model's context so it knows the schema fields and the situational mappings:
exam/tired/crash → glycemic_proxy asc + moderate protein; post-workout → protein_density
desc; etc. Keep these mappings in ONE module so they're editable without touching query code.

Add a query cache (in-process TTL, 10 min) keyed on normalized query + context, so repeated
demo queries don't re-hit the LLM. scripts/prewarm.py populates it.
```

**GOTCHA:**
```
Do NOT put allergen or dietary exclusions into the NL model's prompt and rely on it to
generate the right filter. It will USUALLY work, which is worse than never working, because
you will stop checking. Exclusions go in explicit filter_by only. The LLM interprets VIBES;
it does not enforce SAFETY.

The cache is not an optimization, it is demo insurance. Hackathon wifi plus an LLM round-trip
on stage is how a demo dies.
```

**VERIFY:**
- `"exam in an hour, don't want to crash"` → low-glycemic, moderate-protein items
- `"my friend has a nut allergy and I'm vegetarian, find somewhere we can both eat"` → both constraints applied, unverified items withheld
- Kill your internet mid-query → degrades to keyword search, `degraded=True`, no crash
- Run the same hero query 5 times → stable results, **identical** safety filter every time even if the LLM's contribution varies

---

### Phase 5 — The UI `[FE]`

**GOAL:** The demo-able interface. Search, results, reasoning, empty state. **Can start as soon as §5's contract is agreed — stub the endpoint with fixtures, don't wait for Phase 4.**

**TESTS:**
```
web/tests/unit/ (Vitest + Testing Library), against fixture SearchResponse objects:
- ResultCard renders provenance badge TEXT (not just color) and cleared-constraint chips
- WithheldNotice renders only when withheld_count > 0, with the exact number
- EmptyState renders partial_matches with their specific fails[], never a bare "no results"
- ReasoningPanel distinguishes generated_filters (model) from explicit_filters (us)
- degraded=True renders a visible notice

web/tests/e2e/search.spec.ts:
- typing a hero query and submitting renders results
- a loading state appears within 100ms of submit (NL search takes seconds — the UI must
  never look frozen)
- axe scan passes on the results page; full keyboard path from input to first result
```

**PROMPT:**
```
Build the search UI per README §7 design tokens. Mirror the §5 Pydantic models into
src/lib/types.ts exactly — field names identical, no renaming at the boundary.

- SearchBar: single input, no filter chips by default. Constraints live in a profile drawer
  (allergies, diet, goals) because they're persistent, not per-query.
- Loading: use TanStack Query. NL search takes seconds — render "reading your request"
  immediately, then the interpreted intent as soon as the trace returns, then results.
  Never a blank spinner.
- ResultCard: name, venue, distance, key macros, provenance badge, cleared chips
  ("dairy-free ✓ · 32g protein ✓").
- ReasoningPanel: collapsible; shows interpreted_intent, filters from the model vs filters
  from us. Design it as a feature, not a debug view.
- WithheldNotice: "6 items hidden — allergen data unverified", expandable to one sentence
  of policy.
- EmptyState: render partial_matches with each item's specific failure. Camera entry point
  (stubbed until phase 8).
- PhoneFrame: a ~390px centered device shell used for the demo. Build the app responsive;
  the frame is a presentation wrapper, not a second layout.

Accessibility is judged AND real: full keyboard path, labeled controls, no color-only
meaning (provenance badges need text).
```

**VERIFY:**
- Unit + E2E green
- Run the hero query at 390px width — this gets demoed on a laptop but judged on whether it looks like a real product
- Stop the backend → the error path is legible, not a stack trace
- Tab through the entire flow without a mouse

---

### Phase 6 — Item-level map `[FE]`

**GOAL:** The screenshot judges remember. Pins are dishes.

**TESTS:**
```
web/tests/e2e/map.spec.ts:
- results render as pins; pin count matches top-N, not total result count
- multiple items at one venue cluster into ONE marker with a count badge
- clicking a cluster expands to that venue's item list
- map and list stay in sync: a new search updates both
- pin popups show the ITEM, not the venue
```

**PROMPT:**
```
Add MapLibre GL with free raster tiles. Render the top 12 ranked results as pins.

Cluster by venue_id — a venue with 6 matching dishes is ONE marker showing "6", expanding to
the dish list on click. Do not render every matching item as its own pin.

At phone width, use a bottom-sheet layout: map full-bleed, results as a draggable sheet over
it. Side-by-side does not fit 390px and the sheet is the correct mobile pattern anyway.

Selecting a pin highlights the matching result card and vice versa. Add a campus-boundary
overlay toggle so the on/off-campus story is visible at a glance — that's the pitch made
visual.
```

**GOTCHA:**
```
Clustering is not polish. The single most likely on-stage failure for this feature is 40 pins
stacked on one coordinate because a dining hall has 40 matching dishes. Build clustering in
the same commit as the pins, not after.
```

**VERIFY:**
- Query broadly enough to match many items at one venue → one clustered marker, correct count
- Cross-campus query → pins on both sides of the boundary overlay
- Screenshot it. If it doesn't look like the pitch, fix it now.

---

### Phase 7 — Log the meal `[BOTH]`

**GOAL:** Search ends in a logged meal. Closes the loop that makes this an ecosystem feature, not a search toy.

**TESTS:**
```
api/tests/contract/test_log.py:
- logging an item persists it against a day and updates running macro totals
- logging the same item twice creates two entries, not an idempotent no-op
- macros are SNAPSHOTTED at log time: a later reindex changing an item's nutrition must NOT
  retroactively alter past logs
- remaining targets are returned and reflect logged entries

web/tests/e2e/log.spec.ts:
- one tap from a result card to logged, with visible confirmation and updated totals
```

**PROMPT:**
```
BACKEND: minimal tracker with SQLModel + SQLite. Endpoints: POST /api/log,
GET /api/log/today. Keep the interface narrow (log_item, get_day_totals,
get_remaining_targets) so it can be swapped for UPlate's real API later without touching
the UI.

CRITICAL: snapshot the item's nutrition values INTO the log row. Never store only an item_id
and join at read time — item data is mutable via reindex and a user's food history must be
immutable.

Feed remaining targets back INTO UserContext so ranking adapts: if they've hit protein for
the day, protein_density stops being the ranking axis. This is the ecosystem argument made
real — search that knows what you already ate.

FRONTEND: one-tap log from ResultCard, optimistic update via TanStack Query, a day-totals
strip at the top of results.
```

**VERIFY:**
- Log a meal → totals update → rerun the same search → ranking has shifted
- Reindex with modified nutrition for a logged item → the historical log row is unchanged
- **This is the checkpoint where the product is genuinely useful. Ship-to-yourself.**

---

### Phase 8 — Camera (coverage strategy) `[BOTH]`

**GOAL:** Photo → structured item → nutritionally comparable options nearby. Including for items not in the index.

**TESTS:**
```
api/tests/contract/test_image_search.py:
- indexing an image doc generates clip_embedding and does NOT persist the base64 image
- a photo of a known seeded dish resolves to that item as the top match
- similarity by document id returns other items, ranked
- CRITICAL: similarity results are ranked by NUTRITION proximity, not CLIP distance. Seed a
  fried chicken and a grilled chicken item with near-identical appearance and very different
  macros. A photo of grilled chicken must NOT return fried chicken as the top "similar"
  result. If it does, the pipeline is wrong.
- an unrecognized photo returns a low-confidence ESTIMATED result, never a confident match
```

**PROMPT:**
```
Add FOOD_IMAGES_SCHEMA per README §3 with ts/clip-vit-b-p32.

app/routers/photo.py implements the flow as TWO DISTINCT STAGES:
  Stage 1 (RECOGNITION): base64 photo → CLIP similarity against food_images → candidate
    item_ids with confidence. Below threshold → return an ESTIMATED-provenance synthetic
    item rather than a confident wrong match.
  Stage 2 (SIMILARITY): take the resolved item's STRUCTURED attributes (macros, tags) and
    run the EXISTING food_items ranker to find comparable nearby options.

The photo is an input modality. It is never the similarity space.

FRONTEND: camera capture, a confirmation step showing what we think it is with an EDITABLE
nutrition estimate, then comparable-items results. Label estimates clearly as estimates.
```

**GOTCHA:**
```
Visual similarity is not nutritional similarity, and here that is not a nuance — it is a
correctness bug. Grilled and fried chicken are near-identical to CLIP. So are full-fat and
nonfat yogurt, regular and diet soda, a dressed and undressed salad. Returning CLIP neighbors
directly as "similar items" in a nutrition app means confidently returning worse-than-random
matches to people making medical decisions.

CLIP resolves WHAT IT IS. Nutrition-space ranking decides WHAT'S COMPARABLE. Two stages,
always, no shortcuts.
```

**VERIFY:**
- Photo a seeded dish → correct identification
- Photo something not in the index → low-confidence estimate path, clearly labeled, still returns useful comparables
- Run the fried/grilled chicken test manually and read the output yourself

---

### Phase 9 — Voice `[FE]`

**GOAL:** Query by voice. A dining hall is loud and your hands are full of a tray.

**TESTS:**
```
web/tests/e2e/voice.spec.ts:
- a recorded audio fixture produces a transcription and results
- mic permission denial degrades to text input with a clear message, no dead end
- the transcript is shown and EDITABLE before search runs
```

**PROMPT:**
```
Add voice capture using Typesense's built-in voice search (Whisper transcription), proxied
through a FastAPI endpoint — the browser never holds a Typesense key.

Always display the transcript and let the user correct it. In a loud room transcription will
be wrong sometimes; a silently wrong query returning confident results is worse than a
visible one the user can fix.

Full keyboard and screen-reader parity — voice is an additional path, never the only path to
any function.
```

**VERIFY:**
- Works in an actually noisy room, not a quiet one
- Deny mic permission → graceful text fallback
- Screen reader announces the transcript

---

### Phase 10 — Scale `[BE]`

**GOAL:** Multi-campus, safe ingest at volume, observability. Nothing user-visible; everything that makes it real.

**TESTS:**
```
api/tests/contract/test_scale.py:
- scoped search keys enforce campus_id: a key scoped to campus A cannot retrieve campus B
  documents even with an explicit filter attempting to
- alias swap under concurrent load: 500 queries during a reindex → zero errors, zero empty
  result sets
- ingest of 50k synthetic docs completes; search latency during ingest is recorded
- analytics captures no-hits queries with analytics_tag
```

**PROMPT:**
```
1. Scoped API keys per campus: generate_scoped_search_key embeds a campus_id filter so a
   tenant's key structurally cannot read another's data. Enforce server-side; never trust a
   client-supplied campus_id.
2. Harden the blue/green pipeline: batched imports with configurable batch size, retry on
   partial failure, and an ingest report (docs in / indexed / rejected + why). Rejected docs
   go to a dead-letter file — never silently dropped.
3. Wire Typesense search analytics with analytics_tag set to the campus. No-hits queries are
   your coverage-gap roadmap — they tell you exactly which food people want that you lack.
4. Structured logging per search: latency split between LLM time and Typesense time, so you
   know which half to optimize.
5. Load test with 50k synthetic docs; write the actual numbers into this README.
```

**GOTCHA:**
```
Embedding generation is CPU-bound and can make the node unresponsive during large ingests.
At scale, run ingest against a SEPARATE node or during low traffic, then swap the alias. This
is why blue/green was built in phase 1. If the load test shows latency spiking during ingest
on one node, that's expected — the fix is topology, not code.
```

**VERIFY:**
- Cross-tenant read attempt fails with a scoped key
- Reindex under load: zero errors
- Numbers written down, not just observed once

---

### Phase 11 — Real ingestion `[BE]`

**GOAL:** Replace seeded data. Where the pitch's central claim becomes true.

**TESTS:**
```
api/tests/contract/test_adapters.py, per adapter:
- a recorded real-world response fixture normalizes to a valid document
- a malformed/partial response produces a rejected doc WITH a reason, never a doc with
  silently missing allergen data
- provenance is assigned correctly per source
- an adapter that cannot determine allergens sets allergen_verified False, always
```

**PROMPT:**
```
Implement the adapter interface: fetch → parse → normalize → emit documents with provenance.
One adapter per source type in app/ingest/adapters/:

  1. DiningFeedAdapter — campus dining APIs. OFFICIAL_FEED, allergen_verified True.
  2. ChainAdapter — published chain nutrition data. CHAIN_PUBLISHED. VERIFY the actual
     availability and format of this data before building; do not assume it is
     machine-readable just because it is published.
  3. OcrMenuAdapter — menu images/PDFs for independents. ESTIMATED, allergen_verified
     ALWAYS False. This tier can never clear a hard exclusion, by design.
  4. CrowdCorrectionAdapter — user submissions that upgrade ESTIMATED → CROWD_VERIFIED after
     N corroborating reports. Define N and the conflict-resolution rule explicitly.

All adapters feed the same blue/green pipeline. Adding a source must never require touching
query code — if it does, the abstraction is wrong.
```

**GOTCHA:**
```
Coverage is a permanent problem, not a phase you finish. Anyone claiming they will fully
ingest the long tail of independent restaurants is wrong. That is WHY the camera exists
(phase 8) and why provenance + withheld-counts exist (phase 3) — the product is designed to
be honest and useful at partial coverage rather than to pretend at completeness.

Never let an adapter assign a provenance tier higher than its evidence supports in order to
make more items visible. That inverts the safety invariant.
```

**VERIFY:**
- One real dining feed ingesting end to end
- Malformed input → dead-letter entry with a reason, no bad doc in the index
- An OCR-sourced item can never surface under an allergen exclusion

---

## 7. Design system

Clean, appetizing, trustworthy. Health-adjacent — closer to a well-made utility than a social app.

**Principles:** generous whitespace, one accent, density that scales down to a phone. Provenance badges carry **text plus** color, never color alone.

**Light:**
```
background    #FBFAF8
surface       #FFFFFF
surfaceMuted  #F2F0EC
textPrimary   #1C1B19
textSecondary #6E6A63
accent        #3F6B4A   // deep green
outline       #E4E0D9
```

**Provenance palette** (must stay distinguishable in grayscale):
```
OFFICIAL_FEED   #3F6B4A  "Verified"
CHAIN_PUBLISHED #4A6B7C  "Published"
CROWD_VERIFIED  #8A7040  "Community"
ESTIMATED       #8A6A6A  "Estimated"
```

**Type:** one grotesque (Inter or system). Tabular figures for numbers — macros sit in columns and must align.

**Motion:** 150–250ms fades. The reasoning panel expands; it does not bounce.

**Layout:** phone-first, ~390px target. Map is full-bleed with results in a draggable bottom sheet. `PhoneFrame` is a demo wrapper around the same responsive app, not a separate layout.

**The NL latency rule:** every state between submit and results must be *legible*. Interpreted intent renders before results do. A user should be able to tell we understood them before they can tell what we found.

---

## 8. Local loop

```bash
docker compose up -d                            # Typesense + models volume

cd api
uv sync                                         # or: pip install -e .
uvicorn app.main:app --reload --port 8000
python scripts/bootstrap.py                     # collections, NL model, seed
pytest                                          # unit + contract

cd ../web
npm install
npm run dev                                     # :5173
npm test                                        # Vitest
npm run test:e2e                                # Playwright

python api/scripts/reindex.py                   # blue/green rebuild
python api/scripts/prewarm.py                   # cache hero queries before demoing
```

---

## 9. Fast path — hackathon only

Ship **Phases 0 → 5**, then **6** if there's time.

Seeded index, hybrid + NL search, the safety layer, and a UI that renders the reasoning. Phase 6's map is the best single visual and is cheap once 5 is done — take it if you have the hours.

**Parallelize:** agree on the §5 API contract in the first 15 minutes. Backend runs 1 → 2 → 3 → 4. Frontend runs 5 against fixtures immediately, integrates when Phase 4 lands. Neither person blocks on the other after Phase 0.

**Cut phase 8 (camera) from the demo even though it's the most exciting feature.** A shaky recognition demo next to a clean text-search demo costs more credibility than the extra feature earns. Pitch it as the coverage strategy; build it next week.

**Before you present:** run `prewarm.py`, and rehearse the two hero queries specifically. Nobody grades generality in 90 seconds, but a fumbled hero query kills the entire framing.

**One thing to check yourself:** verify UPlate's actual user numbers before putting them in the pitch. An App Store rating count is not a user count, and a judge who probes an inflated number costs you more than the claim was worth.

**One thing that needs a human, not a test:** Phase 4 encodes situational→nutritional mappings (exam → low glycemic, post-workout → high protein) in a prompt. That's effectively nutritional advice, drafted by an LLM rather than a nutritionist. Before this reaches real users, someone who actually knows nutrition should review that module — it's the one part of the system where being confidently wrong isn't caught by any test in this document.
