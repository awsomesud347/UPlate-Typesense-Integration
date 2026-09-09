# UPlate Search — Build Spec & Orchestration Plan

> **Local deltas from the original spec (agreed 9/8, hackathon night):**
> 1. **NL layer = Claude API** (`api/app/llm/`), not Typesense's NL Search Models API — Typesense's built-in NL feature doesn't take Anthropic as a provider, and we have Claude credits. Claude turns the sentence into `{filter_by, sort_by, intent}`; we AND our explicit hard-exclusion `filter_by` on top server-side, so the safety invariant is preserved identically.
> 2. **Typesense hosting:** Docker where available; on the Docker-less Windows machine, native Linux binary inside WSL2 (see README quickstart). Same port 8108 either way.
> 3. **Hackathon reality:** seed data is hardcoded/prefilled and labeled by provenance in the UI. Endpoints are real. Phases 0–5 are tonight's target, 6 if time allows.

---

## 1. Final product definition (decisions locked)

### The claim
Delivery apps index dishes but know nothing about what's in them. Campus nutrition apps know what's in the food but stop at the property line. Trackers know your goals but can't tell you where to eat. **We're the only thing holding nutrition, location, and personal targets in one query.**

### Core behaviors

**Situational natural-language search.** The hero query is not `"under 600 calories, no dairy"` — that's five checkboxes and a filter UI beats us. The hero query is **`"exam in an hour, don't want to crash"`**: a *situation* → a *nutritional strategy* → *real dishes near you*.

**Two constraint classes, never blurred.**
- **Preferences** (macros, cuisine, goals) — soft. Ranked, not filtered.
- **Exclusions** (allergens, religious, medical) — hard. Filtered, enforced *outside* the LLM's reach.

**Provenance is a shipped feature.** Four tiers: `OFFICIAL_FEED` > `CHAIN_PUBLISHED` > `CROWD_VERIFIED` > `ESTIMATED`. When a hard exclusion is active, items below the verification threshold are **withheld, not down-ranked**, and the count is shown: *"6 items hidden — allergen data unverified."*

> **The safety invariant:** the failure mode is always *"we didn't show you something safe,"* never *"we showed you something dangerous."*

**Reasoning trace on every search.** Interpreted strategy, filters applied, why each item cleared, provenance badge. Trust mechanism, not debug view.

**Item-level map.** Pins are dishes. Clustered by venue, top-N only.

**Designed empty state.** Nearest partial matches with exactly what fails.

### Out of scope for v1
Real ingestion, user accounts, multi-tenant beyond a config value, offline mode, ordering.

---

## 2. Repo layout

```
├── docker-compose.yml / docker-compose.test.yml
├── api/                            # Python. Backend dev + Typesense integration.
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py                 # FastAPI app, CORS, routers
│   │   ├── config.py               # pydantic-settings
│   │   ├── schemas/search.py       # THE CONTRACT — mirror in web/src/lib/types.ts
│   │   ├── routers/search.py
│   │   ├── llm/interpreter.py      # Claude: sentence → {intent, filters, sort}
│   │   ├── typesense/
│   │   │   ├── client.py           # admin client, backend-only
│   │   │   ├── schema.py           # FOOD_ITEMS_SCHEMA, versioned
│   │   │   └── query_builder.py    # THE core module — only place params are assembled
│   │   ├── constraints/
│   │   │   ├── exclusions.py       # allergens/diet → explicit filter_by fragments
│   │   │   ├── goals.py            # goal → precomputed axis (a dict, not if/elif)
│   │   │   └── provenance.py       # verification gate
│   │   └── ingest/
│   │       ├── derive.py           # precomputed ranking axes (pure functions)
│   │       ├── normalize.py        # raw row → doc; RAISES on missing allergens
│   │       └── pipeline.py         # blue/green alias swap
│   ├── scripts/bootstrap.py|reindex.py|prewarm.py
│   ├── data/seed/items.json
│   └── tests/unit|contract/
└── web/                            # React + Vite + TS. UI dev.
    └── src/
        ├── lib/api.ts|types.ts|fixtures.ts
        ├── components/  (SearchBar, ResultCard, ReasoningPanel, WithheldNotice,
        │                 EmptyState, ItemMap, PhoneFrame)
        └── hooks/
```

---

## 3. Data model

One collection, one document per dish. Schema lives in `api/app/typesense/schema.py`.

**GOTCHA — why precomputed fields exist:** Typesense `sort_by` does NOT support arithmetic. No `protein_g / calories`. `_eval()` only takes boolean filter expressions with custom scores. Every ratio/density/composite score MUST be computed at ingest in `derive.py` and stored as a plain numeric field. Wanting to compute in `sort_by` = signal you need a new derived field, not a cleverer query.

Precomputed axes (user-independent): `protein_density` (protein per 100kcal), `satiety_score`, `glycemic_proxy` (crash risk), `is_warm`. Goal fit is composed at query time from these + the user's goal — adding a goal = adding a `goals.py` entry, not a reindex.

---

## 4. Query architecture

Everything funnels through `build_search_request(inp, ctx)` in `query_builder.py` — the ONLY place search params are assembled.

```
hard exclusions   →  explicit filter_by  →  ANDed on top of whatever the LLM decides
soft preferences  →  the LLM's job + sort_by selection
```

The LLM **cannot widen the result set**. An allergen exclusion is a boolean AND applied after the model is done. Phase 3 tests this; it must never regress.

| Layer | Mechanism |
|---|---|
| Intent → params | Claude API (`app/llm/interpreter.py`), cached, degrades to keyword on failure |
| Semantic + keyword | Hybrid: `query_by` includes text fields **and** `embedding`; `alpha` in `vector_query` |
| Hard exclusions | explicit `filter_by`, ANDed |
| Provenance gate | `allergen_verified:true` appended when any exclusion active |
| Distance | `filter_by: location:(lat,lng, N mi)` |
| Nearby-is-nearby | `sort_by: location(lat,lng, precision: 1 mi):asc, <axis>:desc` |
| Withheld count | `multi_search`: gated + ungated-count queries in one request; diff totals |
| Vector bloat | `exclude_fields: embedding` on every search, always |

**GOTCHA — LLM layer:** never put exclusions in the prompt and rely on the model. It will *usually* work, which is worse than never working. Cache interpreted queries (TTL 10 min) — the cache is demo insurance, not an optimization. `scripts/prewarm.py` warms the hero queries.

---

## 5. API contract

Source of truth: `api/app/schemas/search.py` (Pydantic). Mirror: `web/src/lib/types.ts`. Identical field names, no renaming at the boundary. Change together or not at all. Fixtures for UI-without-backend: `web/src/lib/fixtures.ts`.

---

## 6. Phase order (tonight)

- **P0** ✅ scaffold: both apps run, CORS, stub `/api/search` serves fixtures
- **P1** `[TS]` schema + seed (~60 items, Purdue + off-campus, real WL coords, all 4 provenance tiers, edge cases: unverified allergens, zero-cal, time-windowed)
- **P2** `[TS]` hybrid search + filters + geo. Proof test: "something warm and comforting" returns soups without keyword overlap — if it fails, `query_by` is missing `embedding`
- **P3** `[BE]` safety layer: exclusions → explicit filter_by, provenance gate, withheld counts via multi_search
- **P4** `[BE]` Claude interpreter + reasoning trace + cache + prewarm + degrade path
- **P5** `[FE]` UI: SearchBar, loading states (LLM = seconds; interpreted intent renders before results), ResultCard w/ provenance badge + cleared chips, ReasoningPanel, WithheldNotice, EmptyState, PhoneFrame (~390px)
- **P6** `[FE]` (stretch) MapLibre item-pinned map, clustered by venue — clustering ships in the same commit as pins

**GOTCHA — safety, verbatim:** `allergen_verified=False` must gate an item OUT even when its allergen list looks clean. "No verified data" ≠ "verifiably contains none." If anyone optimizes this to only check the allergen array, revert it.

**GOTCHA — hybrid:** hybrid search only happens if `embedding` is in `query_by` alongside text fields. Text-only looks fine on easy queries and silently fails every semantic one.

---

## 7. Design tokens

```
background #FBFAF8 · surface #FFFFFF · surfaceMuted #F2F0EC
textPrimary #1C1B19 · textSecondary #6E6A63 · accent #3F6B4A · outline #E4E0D9

OFFICIAL_FEED   #3F6B4A  "Verified"
CHAIN_PUBLISHED #4A6B7C  "Published"
CROWD_VERIFIED  #8A7040  "Community"
ESTIMATED       #8A6A6A  "Estimated"   ← badges carry TEXT + color, never color alone
```

Inter/system font, tabular figures for macros. 150–250ms fades. Phone-first ~390px; `PhoneFrame` is a demo wrapper, not a second layout.

**NL latency rule:** every state between submit and results must be legible. The user should be able to tell we understood them before they can tell what we found.

---

## 8. Before the demo

1. `python scripts/prewarm.py` — cache hero queries
2. Rehearse: `"exam in an hour, don't want to crash"` and `"my friend has a nut allergy and I'm vegetarian, find somewhere we can both eat"`
3. Kill wifi once in rehearsal — confirm the degraded keyword path renders legibly
