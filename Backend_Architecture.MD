# UPlate Search — Backend Architecture & Build Spec (v2)

> Supersedes the backend sections of `Guidelines.MD`. Where the two disagree, **this document wins**.
> Frontend sections of `Guidelines.MD` (§7 design system, Phases 5/6/9-UI) remain valid.

**Stack: FastAPI + Python 3.12 · Typesense Cloud (v29.1) · SQLite for local state · React + Vite frontend.**

**No accounts, no auth, no registration.** One anonymous app. A search string goes in, ranked results come out. Every stateful feature below is served by a single implicit profile that exists from first boot.

---

## 0. Delta from `Guidelines.MD` — read this first

Claude Code: do not re-derive assumptions from the old spec. These are the changes.

| # | Old spec | This spec | Why |
|---|---|---|---|
| 1 | One collection (`food_items`) | Five collections (§3) | Map needs venues at rest; novelty needs history; RAG needs a corpus |
| 2 | Map is Phase 6, dish-pinned only | Map is the landing screen, venue-pinned at rest, dish-pinned after search | Actual user flow |
| 3 | Dining halls + off-campus unified, real ingestion in Phase 11 | **5 off-campus venues, hardcoded placeholder data in one JSON file. No ingestion pipeline, no adapters, no live sources.** | Hackathon data reality |
| 4 | Every query goes through `nl_query` | Query classifier picks 1 of 3 execution plans (§5.1) | Numeric queries must not touch an LLM |
| 5 | Typesense executes the LLM's query | **NL search is a parser only.** We validate and re-issue (§5.3) | v30 bug + filter-precedence hole + hybrid collapse |
| 6 | `sort_by` fixed server-side | Client `sort_override`, allowlisted | User wants "sort by low sodium" etc. |
| 7 | Ranking = goal axis | Ranking = hard filters + soft prefs + history targets + novelty | "Recommend something new" |
| 8 | Flat `hits` list | A distinguished, reasoned top set alongside the browsable remainder | "AI's top picks" |
| 8b | Frozen Pydantic wire contract in §5 | **Wire contract deliberately undecided.** Domain objects + a swappable serializer (§6) | Not yet agreed with frontend |
| 8c | User accounts, per-user context, multi-tenancy | **No auth, no registration, no `user_id` anywhere.** One implicit profile, seeded at bootstrap | Scope: search in, results out |
| 9 | Self-hosted Docker, built-in ML models | Typesense Cloud, embedder selected by env (§2) | Sponsor alignment + no laptop dependency |
| 10 | Phases 8 (camera), 10 (scale), 11 (ingestion) | **Cut.** Phase 9 (voice) optional | Under 5 hours of build time |
| 11 | Geo bucket `precision: 1 mi` | Geo is a filter only, never a `sort_by` slot | 5 venues, distance carries no ranking signal |
| 12 | `ingest/` with adapters, dead-letter, batching, blue/green at scale | `data/` loader: read one JSON file, validate, derive, index. ~60 lines | There is nothing to ingest from |

**Unchanged and non-negotiable:** the safety invariant. The only acceptable failure is showing too little. Hard exclusions are never the LLM's responsibility. `allergen_verified: false` gates an item out whenever any exclusion is active, even if its allergen list looks clean.

---

## 1. What the backend must serve

Three user flows. Every endpoint exists for one of them.

**Flow A — Browse (no query).** App opens. Map of West Lafayette with one pin per venue. Tapping a pin shows that venue's dishes. Zero LLM involvement, must be instant.

**Flow B — Search.** One text box. Input ranges from `"quick energy before an exam"` to `"600 cal, under 20g fat, under 800mg sodium, something dry I can eat walking"`. Returns AI top picks with reasons, plus the full ranked remainder, plus a reasoning trace, plus a withheld count.

**Flow C — Re-sort and log.** Client re-sorts the retrieved set by a named axis without re-running the LLM. Logging a dish appends to the single implicit profile's history, which changes future ranking (macros already consumed + novelty penalty on repeats). No sign-in gates any of this; the history is app state, not a user record.

---

## 2. Deployment: Typesense Cloud

### 2.1 Cluster configuration

Provision at https://cloud.typesense.org before writing code. Model download and cluster spin-up are on the critical path.

| Setting | Value | Reason |
|---|---|---|
| Typesense version | **29.1** | v30.0–30.2 have an open NL search regression (§10.1). Cloud supports version up/downgrade later under Cluster Configuration > Modify |
| RAM | 4 GB if `EMBEDDER=builtin`, 0.5–1 GB if `EMBEDDER=remote` | Built-in ML models need 2–6 GB **on top of** vector storage. Remote embedders need no extra RAM |
| vCPU | 2 minimum (Typesense requires 2) | |
| GPU Acceleration | Off | Only needed for large built-in-model workloads. ~100 docs embeds in seconds on CPU |
| High Availability | Off | Single node is fine for a demo |
| Region | Closest US region | |

Free tier is **720 hours + 10 GB bandwidth, once per account lifetime, on select configurations**. It does not replenish. Larger RAM configs may fall outside it — check the pricing calculator before launching, and shut the cluster down after the event.

### 2.2 The embedder switch

One env var decides the schema's `embed` block. Nothing else in the codebase knows the difference.

```python
# app/typesense/schema.py
EMBED_CONFIG = {
    "builtin": {"model_name": "ts/all-MiniLM-L12-v2"},
    "remote":  {"model_name": "openai/text-embedding-3-small",
                "api_key": settings.EMBEDDING_API_KEY},
}[settings.EMBEDDER]
```

- `builtin` — runs on the Typesense node, no per-call cost, needs the 4 GB config.
- `remote` — runs on OpenAI's servers, cheap small cluster, adds ~100ms to indexing and to each semantic query.

Default to `remote` for Cloud. Keep `builtin` working so a local Docker fallback is a one-line change.

### 2.3 Local fallback

Keep `docker-compose.yml` from the old spec, pinned to `typesense/typesense:29.1`, with a named volume. `scripts/bootstrap.py` must produce an identical index against either target. If venue wifi dies, you flip `TYPESENSE_HOST` to localhost and keep demoing.

### 2.4 Environment

```
TYPESENSE_HOST=xxxxx.a1.typesense.net
TYPESENSE_PORT=443
TYPESENSE_PROTOCOL=https
TYPESENSE_ADMIN_API_KEY=          # server-side only, never in web/
EMBEDDER=remote                    # remote | builtin
EMBEDDING_API_KEY=                 # only when EMBEDDER=remote
NL_LLM_PROVIDER=google             # google | openai
NL_LLM_API_KEY=
ALLOWED_ORIGINS=http://localhost:5173
```

`grep -r "ADMIN" web/dist/` must return nothing. The browser never talks to Typesense.

---

## 3. Collections

Create in this order. `food_items` references `venues`, so `venues` must exist first.

### 3.1 `venues_v1` (alias: `venues`)

Powers the resting map and JOINs.

```python
VENUES_SCHEMA = {
    "name": "venues_v1",
    "fields": [
        {"name": "id",          "type": "string"},
        {"name": "name",        "type": "string"},
        {"name": "kind",        "type": "string", "facet": True},   # dining_hall | off_campus
        {"name": "cuisine",     "type": "string[]", "facet": True},
        {"name": "location",    "type": "geopoint"},
        {"name": "open_from",   "type": "int32"},   # minutes since midnight
        {"name": "open_to",     "type": "int32"},
        {"name": "price_tier",  "type": "int32", "facet": True},    # 1-3
        {"name": "walk_minutes","type": "int32"},   # from campus centroid
        {"name": "item_count",  "type": "int32"},
    ],
    "default_sorting_field": "item_count",
}
```

### 3.2 `food_items_v1` (alias: `food_items`)

One document per dish. This is the product.

```python
FOOD_ITEMS_SCHEMA = {
    "name": "food_items_v1",
    "fields": [
        {"name": "name",        "type": "string"},
        {"name": "description", "type": "string"},

        # --- venue link (JOIN) ---
        {"name": "venue_id",    "type": "string", "reference": "venues.id"},
        {"name": "venue_name",  "type": "string", "facet": True},   # denormalized fallback
        {"name": "source_type", "type": "string", "facet": True},
        {"name": "location",    "type": "geopoint"},

        # --- soft: ranking inputs ---
        {"name": "tags",        "type": "string[]", "facet": True},
        {"name": "dish_family", "type": "string",   "facet": True},  # burger|bowl|noodle|salad|wrap|pizza|breakfast|dessert
        {"name": "texture",     "type": "string",   "facet": True},  # dry|wet|mixed  <- NEW
        {"name": "handheld",    "type": "bool",     "facet": True},
        {"name": "calories",    "type": "int32",    "facet": True},
        {"name": "protein_g",   "type": "float",    "facet": True},
        {"name": "carbs_g",     "type": "float",    "facet": True},
        {"name": "fat_g",       "type": "float",    "facet": True},
        {"name": "fiber_g",     "type": "float",    "facet": True},
        {"name": "sodium_mg",   "type": "int32",    "facet": True},
        {"name": "price_cents", "type": "int32",    "facet": True},

        # --- hard: exclusion inputs ---
        {"name": "allergens",         "type": "string[]", "facet": True},
        {"name": "diet_flags",        "type": "string[]", "facet": True},
        {"name": "provenance",        "type": "string",   "facet": True},
        {"name": "allergen_verified", "type": "bool",     "facet": True},

        # --- precomputed ranking axes (no arithmetic in sort_by) ---
        {"name": "protein_density", "type": "float"},
        {"name": "satiety_score",   "type": "float"},
        {"name": "glycemic_proxy",  "type": "float"},
        {"name": "sodium_density",  "type": "float"},   # NEW: mg per 100 kcal
        {"name": "is_warm",         "type": "bool", "facet": True},

        # --- availability ---
        {"name": "available_from", "type": "int32"},
        {"name": "available_to",   "type": "int32"},

        {"name": "embedding", "type": "float[]",
         "embed": {"from": ["name", "description", "tags", "venue_name"],
                   "model_config": EMBED_CONFIG}},
    ],
    "default_sorting_field": "calories",
}
```

**Every numeric ranking axis must be `facet: True`.** Facet stats are how the empty state computes "40g over your carb target" (§5.6). Skipping this costs you the partial-match feature.

**`dish_family` is the novelty key, not `id`.** "You've had a burger three times" is the useful signal; "you've had *this exact* burger" is not.

### 3.3 `nutrition_notes_v1`

Small curated corpus (20–30 docs) grounding the situational mappings. Turns LLM-invented nutrition advice into cited retrieval.

```python
NUTRITION_NOTES_SCHEMA = {
    "name": "nutrition_notes_v1",
    "fields": [
        {"name": "title",     "type": "string"},
        {"name": "body",      "type": "string"},
        {"name": "situation", "type": "string[]", "facet": True},  # exam|post_workout|hangover|late_night|early_class
        {"name": "source",    "type": "string"},                    # citation shown in UI
        {"name": "embedding", "type": "float[]",
         "embed": {"from": ["title", "body"], "model_config": EMBED_CONFIG}},
    ],
}
```

### 3.4 `conversation_store`

Required by Typesense's built-in RAG. Schema is fixed by Typesense — copy it verbatim from the Conversational Search docs for v29.1. Do not improvise the fields.

### 3.5 `user_history` (SQLite, not Typesense)

**No hosted database, and no user identity.** A single SQLite file next to the API process holding one implicit profile's history. There is no `user_id` column, no session, no cookie, no login. If the API is deployed somewhere with an ephemeral disk the file resets on restart, which is acceptable because `bootstrap.py` seeds a synthetic 7-day history. The novelty ranking must be demonstrable on a cold start with zero clicks and zero setup.

```sql
CREATE TABLE meal_log (
  id INTEGER PRIMARY KEY,
  item_id TEXT NOT NULL,
  dish_family TEXT NOT NULL,
  venue_id TEXT NOT NULL,
  logged_at TIMESTAMP NOT NULL,
  -- SNAPSHOTTED. Never join to food_items at read time.
  name TEXT, calories INT, protein_g REAL, carbs_g REAL,
  fat_g REAL, fiber_g REAL, sodium_mg INT
);
```

Macros are snapshotted at log time. A reindex that changes an item's nutrition must never retroactively alter a past log.

---

## 4. Seed data

**There is no ingestion pipeline.** All data is hardcoded placeholder content in a single file, `api/data/seed.json`, committed to the repo. No adapters, no scrapers, no OCR, no external feeds, no dead-letter queue. `bootstrap.py` reads that file, validates it, derives computed fields, and indexes it. That is the entire data path, and it should be about 60 lines.

```
data/seed.json
{
  "venues":          [ 5 objects  ],
  "items":           [ ~100 objects ],
  "nutrition_notes": [ ~25 objects  ],
  "synonyms":        [ ~15 pairs    ]
}
```

- **5 off-campus venues**, modeled on real West Lafayette restaurants and renamed. Real coordinates. **Place 3 within walking distance of campus and 2 at 2–3 miles out.** Without outliers the radius filter excludes nothing and geo search is decorative.
- **~100 dishes**, 15–25 per venue. Enough that grouping and faceting have something to chew on, few enough to hand-write in an hour.
- **Provenance is a hand-typed label, not a derived fact.** Spread it deliberately: some `OFFICIAL_FEED` + `allergen_verified: true`, some `CHAIN_PUBLISHED`, a few `CROWD_VERIFIED`, and at least 8 items `ESTIMATED` + `allergen_verified: false` so the withheld-count demo has something to withhold. The four tiers still drive the safety layer exactly as specified; they are simply assigned by you rather than by a source.
- **Descriptions are load-bearing.** At this corpus size, semantic search quality *is* description quality. Two sentences per dish, mentioning texture, temperature, and how it eats. "Grilled chicken" retrieves nothing; "charred chicken thigh over rice, served hot, eats like a full meal" retrieves for "warm and filling".
- **Deliberate edge cases:** a zero-calorie item, an item available only 11:00–14:00, three near-identical burgers across venues (tests grouping), a clean-allergen-list-but-unverified item, and a high-protein item that is also very high sodium (tests that sort axes conflict honestly).
- **`dish_family` populated on every doc.** Novelty depends on it.
- **Derived fields are never hand-typed.** `protein_density`, `satiety_score`, `glycemic_proxy`, `sodium_density`, `is_warm` are computed by `derive.py` at load. Typing them by hand across 100 dishes guarantees inconsistency, and the ranking axes are exactly where inconsistency is invisible.

**Validate the JSON on load, loudly.** Hand-written data is the most likely source of a silent bug in this build, more likely than any query code. `data/loader.py` must fail the boot with a specific message naming the offending item when:

- the `allergens` key is missing on any item (never default it to `[]` — an empty list means "verified none", absence means "we don't know")
- `allergen_verified: true` appears on an item whose `provenance` is `ESTIMATED`
- `venue_id` references a venue not in the file
- any macro is negative, or `calories` is absent
- `dish_family` or `texture` is missing or outside the allowed set

A partial index is worse than no index. Fail the whole load.

---

## 5. Query architecture

Everything funnels through `app/typesense/query_builder.py`. One function assembles Typesense params, and it is the only place that does.

### 5.1 Stage 1 — Classify

`app/query/classify.py`. Pure function, no I/O, fully unit-testable.

| Plan | Trigger | LLM? |
|---|---|---|
| `BROWSE` | empty query, or `venue_id` supplied | No |
| `SPECIFIC` | query contains numeric constraints (`\d+\s*(cal|kcal|g|mg|protein|fat|sodium|carb)`) or maps cleanly to known tags/families via a keyword table | No |
| `SITUATIONAL` | everything else | Yes |

`SPECIFIC` is a regex + keyword extractor producing structured constraints directly. It must be **deterministic and sub-100ms**. When it parses only part of the query, it downgrades to `SITUATIONAL` and passes the parsed fragments as pre-set constraints so the LLM only fills gaps.

### 5.2 Stage 2 — Parse (SITUATIONAL only)

Typesense NL search, used **as a parser**:

```
POST /multi_search
  nl_query=true, nl_model_id=<id>, nl_query_debug=true, per_page=0
```

Read `parsed_nl_query.generated_params`. Discard everything else about this response — the hits are not used.

Register the model once at bootstrap, idempotently, via `POST /nl_search_models`. Include the schema fields and the situational mappings in the model's `system_prompt`, sourced from `nutrition_notes`, so prompt and corpus can't drift.

Cache on `hash(normalized_query + exclusions + goal)` with a 10-minute TTL. `scripts/prewarm.py` populates it before the demo. The cache is demo insurance, not an optimization.

### 5.3 Stage 3 — Validate (the trust boundary)

`app/query/validate.py`. **LLM output is untrusted input.** This module is the reason the safety claim holds.

```
reject / strip:
  - any field name not in the schema allowlist
  - any clause touching allergens, diet_flags, provenance, allergen_verified
    (the model has no business writing these, ever)
  - any `||` operator anywhere in the generated filter
  - unbalanced parentheses
  - sort fields not in SORT_ALLOWLIST

on any rejection: log it, set reasoning.degraded_reason, continue with
what survived. Never raise. Never fall back to "pass it through".
```

**Why the `||` rule exists.** Typesense concatenates the LLM's filter onto yours with `&&` and no parentheses: explicit `in_stock:true` plus generated `color:red && price:<50` becomes `in_stock:true && color:red && price:<50`. If the model emits a disjunction, you get `exclusion && a:1 || b:2`, and since `&&` binds tighter than `||`, the right branch escapes the exclusion. Write a contract test with a mocked model that returns an OR filter and assert the excluded item never appears. This is the single test that proves the safety story is real rather than asserted.

### 5.4 Stage 4 — Compose

We build the final filter string ourselves, every group parenthesized, exclusions first:

```python
filter_by = " && ".join(filter(None, [
    exclusions_fragment(ctx),        # (allergens:![peanuts,dairy])
    provenance_gate(ctx),            # (allergen_verified:true)  -- only if any exclusion active
    availability_fragment(ctx),      # (available_from:<=NOW && available_to:>=NOW)
    geo_fragment(ctx),               # (location:(lat,lng,3 mi))
    validated_soft_fragment(parsed), # (calories:<600 && texture:dry)
]))
```

The provenance gate is **conditional**. With no exclusions active, unverified items appear normally. That conditionality is itself a test case.

### 5.5 Stage 5 — Sort

**Typesense allows a maximum of 3 sort fields.** Budget them deliberately:

| Slot | Content |
|---|---|
| 1 | `_eval([...]):desc` — the composite: goal bucket + novelty bucket + situational bonus |
| 2 | The primary numeric axis (`protein_density:desc`, `glycemic_proxy:asc`, `calories:asc`, `sodium_density:asc`) |
| 3 | `_text_match:desc` — relevance tiebreak |

Geo does **not** get a slot. All seven venues sit inside one square mile; distance carries no signal here. Expose `walk_minutes` in the payload and let the client display it.

**Novelty via `_eval`.** Typesense `sort_by` supports no arithmetic, so novelty must be a boolean bucket:

```python
recent_families = history.families_eaten(days=7, min_count=2)   # no user_id — one profile
# -> ["burger", "pizza"]
novelty = f"(dish_family:!=[{','.join(recent_families)}]):2" if recent_families else None
goal_bucket = GOAL_EVAL[ctx.goal]        # e.g. "(protein_density:>2.5):3"

sort_by = f"_eval([{goal_bucket}, {novelty}]):desc, {GOAL_AXIS[ctx.goal]}, _text_match:desc"
```

Items from families the user has been repeating fall a tier. They are never filtered out — novelty is a preference, and preferences are ranked, never filtered.

**`sort_override` from the client** replaces slot 2 only. Slots 1 and 3 are untouched, so hard filters and safety are unaffected by any client sort choice. Allowlist:

```python
SORT_ALLOWLIST = {
    "calories_asc": "calories:asc", "calories_desc": "calories:desc",
    "protein_desc": "protein_g:desc", "sodium_asc": "sodium_mg:asc",
    "fat_asc": "fat_g:asc", "fiber_desc": "fiber_g:desc",
    "price_asc": "price_cents:asc", "satiety_desc": "satiety_score:desc",
}
```

Anything not in this dict is a 422. Never interpolate a client string into `sort_by`.

### 5.6 Stage 6 — Execute (one `multi_search`)

Four searches, one HTTP request:

```
1. GATED      full query, gated, facet_by=calories,protein_g,sodium_mg,fat_g
              group_by=venue_id, group_limit=3   <- ONLY when total_found >= 20
              include_fields: "$venues(name,walk_minutes,price_tier)"
              exclude_fields: "embedding"
              filter_curated_hits: true
2. UNGATED    identical, provenance gate removed, per_page=0
              NO group_by. exhaustive_search=true.
              -> withheld_count = ungated.found - gated_ungrouped.found
3. PARTIAL    identical, soft numeric constraints removed, per_page=3
              -> partial_matches, with fails[] computed from facet stats
4. NOTES      nutrition_notes, semantic, per_page=2
              -> the citation behind interpreted_intent
```

**Grouping is conditional and counts are never grouped.** Two reasons, both load-bearing:

- With 5 venues, `group_limit: 2` caps you at 10 results, which is most of what any query returns. Grouping exists to stop one venue dominating out of hundreds. Use `group_limit: 3`, and skip `group_by` entirely below 20 hits.
- **`found` is an approximation when `group_by` is active.** Diffing two approximations gives a `withheld_count` that is confidently wrong, in the one place the spec demands exactness. Run both counting queries ungrouped with `exhaustive_search: true`. At ~125 documents exhaustive search costs nothing.

Search 1 therefore issues a grouped query for display and an ungrouped one for the count when grouping is on. That is 5 searches in the envelope, still one HTTP request.

Search 3 is what makes the empty state real. The old spec asked for "clears everything except 40g over your carb target" without saying how. Compare each partial hit's numeric fields against the dropped constraints; the delta is the `fails[]` string.

`exclude_fields: "embedding"` on **every** search, always. A 384-float array per hit will otherwise dominate your payload.

### 5.7 Top picks

`top_picks` is the first 3 of `results` after ranking, each annotated with a `why` built from facts, not from a model:

```python
why = [reason for reason in [
    goal_reason(hit, ctx),          # "32g protein, 6.4g per 100 cal"
    novelty_reason(hit, history),   # "you haven't had a bowl this week"
    constraint_reason(hit, ctx),    # "dairy-free, verified"
    situation_reason(hit, parsed),  # "low glycemic — steady through your exam"
] if reason]
```

Generated strings from templates over real field values. No LLM in this path. It is the fastest, most reliable part of the response and it is what the judges read first.

---

## 6. Capability surface (transport-agnostic)

> **STATUS: the wire contract is NOT agreed yet.** Frontend and backend have not settled request/response JSON. Claude Code must **not** invent one and bake it into the core. Build to the domain layer below; the JSON shape plugs in later at a single seam.

### 6.1 The layering rule

```
router  →  service  →  query_builder  →  Typesense
   ↑                        ↓
serializer  ←────  domain object
```

- **Services return domain objects.** Plain Python dataclasses in `app/domain/`. No `BaseModel`, no JSON, no field-name opinions leaking outward.
- **Serializers are the only place a wire shape exists.** `app/api/serializers/v0.py`, one function per capability. Currently a thin passthrough.
- **Every test asserts on domain objects, never on JSON.** This is the whole point: when the contract lands, one file changes and zero tests break.
- **Request parsing mirrors this.** Routers accept loose input, normalize it into a `SearchIntent` domain object in one adapter function, and pass that inward. Nothing downstream reads raw request JSON.

Anything that hardcodes a wire key outside `app/api/` is a bug, including in tests.

### 6.2 Domain vocabulary

These are the *concepts* the backend produces, and the names both teams should use in conversation so the eventual contract is a rename-free mapping. Field names here are internal; the wire may differ.

**`SearchIntent`** — everything needed to run a search
`raw_query`, `lat`, `lng`, `now_minutes`, `hard_exclusions` (allergens + diet flags), `goal`, `radius_mi`, `novelty_enabled`, `sort_override_key`, `page`

No `user_id`. `hard_exclusions` and `goal` arrive on the request, held in client-side local state (a toggle row or a drawer), never fetched from a server-side profile. `lat`/`lng` default to the campus centroid when the browser withholds geolocation.

**`ScoredItem`** — one dish, ranked
- identity: `id`, `name`, `description`, `dish_family`, `texture`, `tags`
- venue: `venue_id`, `venue_name`, `source_type`, `lat`, `lng`, `walk_minutes`
- nutrition: `calories`, `protein_g`, `carbs_g`, `fat_g`, `fiber_g`, `sodium_mg`, `price_cents`
- trust: `provenance` (one of the four tiers), `allergen_verified`, `cleared_constraints` (label + passed)
- explanation: `why` (list of strings, populated for top picks only), `seen_recently` (bool)

**`PartialMatch`** — `item` (ScoredItem) + `fails` (human strings like "40g over your carb target")

**`ReasoningTrace`** — `plan` (BROWSE / SPECIFIC / SITUATIONAL), `interpreted_intent`, `llm_generated_filters` (raw), `rejected_clauses` (what validation stripped and why), `applied_filters` (the final composed string, ours), `applied_sort`, `citations` (title + source + snippet), `llm_error`, `degraded`, `llm_ms`, `typesense_ms`

**`SearchOutcome`** — `top_picks` (≤3 ScoredItems carrying `why`), `results`, `total_found`, `withheld_count`, `trace`, `partial_matches`, `available_sorts`, `took_ms`

**`VenueSummary`** — `id`, `name`, `kind`, `cuisine`, `lat`, `lng`, `walk_minutes`, `price_tier`, `item_count`, `open_now`

**`DaySummary`** — `entries`, `totals` (the six macros), `repeated_families`

### 6.3 Capabilities

Paths are **provisional**. What is fixed is the responsibility, the inputs, and the domain object returned.

| Capability | Provisional path | Input | Returns | LLM | Budget |
|---|---|---|---|---|---|
| Map bootstrap | `GET /api/venues` | none | `list[VenueSummary]` | No | <100ms |
| Venue drill-down | `GET /api/venues/{id}/items` | venue id + `SearchIntent` for exclusions | `VenueSummary` + `list[ScoredItem]` | No | <150ms |
| Search | `POST /api/search` | `SearchIntent` | `SearchOutcome` | Plan-dependent | <300ms specific, <3s situational |
| Re-sort | same endpoint, `sort_override_key` set | `SearchIntent` | `SearchOutcome` | **Never** | <200ms |
| Log a meal | `POST /api/log` | item id | `DaySummary` | No | <50ms |
| Today's totals | `GET /api/log/today` | none | `DaySummary` | No | <50ms |
| Comparable dishes | `POST /api/similar` | item id + `SearchIntent` | `list[ScoredItem]` | No | <200ms |
| Health | `GET /api/health` | none | status, Typesense reachability, collection doc counts, active embedder, server version | No | <50ms |

**Re-sort must not re-run the LLM.** It is the same cached parse with sort slot 2 swapped. If a client sort change triggers an LLM call, the implementation is wrong.

### 6.4 The serializer seam

```python
# app/api/serializers/v0.py — the ONLY file that knows about wire format
def serialize_search(outcome: SearchOutcome) -> dict: ...
def serialize_venues(venues: list[VenueSummary]) -> dict: ...
def serialize_day(summary: DaySummary) -> dict: ...
def parse_search_intent(payload: dict) -> SearchIntent: ...
```

Default `v0` behavior: flat snake_case, field names exactly as in §6.2, object at top level. This is a placeholder chosen for legibility, not a proposal.

When the contract is agreed, add `v1.py` and switch a config value. Keep `v0` working until the frontend has migrated. Never edit domain objects to match a wire decision.

### 6.5 Unblocking the frontend before the contract exists

`scripts/emit_samples.py` runs real queries against the seeded index and writes serialized output to `api/samples/`:

```
samples/
├── search_situational.json      # "quick energy before an exam"
├── search_specific.json         # "600 cal, low sodium, dry"
├── search_with_exclusions.json  # withheld_count > 0
├── search_empty.json            # partial_matches populated
├── venues.json
└── log_today.json
```

Frontend builds against these files. They are generated from real data through the real serializer, so they can't drift into fiction the way hand-written fixtures do. Regenerate and re-commit whenever the serializer changes.

### 6.6 Contract freeze

Agree the wire shape before frontend *integration* begins, not before backend starts. The decision needs exactly three answers:

1. Envelope or bare object (`{data, error}` vs. the object at top level).
2. Case convention, and which side converts.
3. How errors and the `degraded` state surface: HTTP status, a field, or both.

Everything else is a rename. Write the answers into `docs/DECISIONS.md`, then implement `v1.py`. Budget 20 minutes; do not let this block Phases 0–4.

---

## 7. Typesense feature integration map

Judging criterion 2 rewards breadth. This is the checklist — each row is a claim you can make on stage.

| Feature | Where it lands | Priority |
|---|---|---|
| **Hybrid search** | `query_by` includes `embedding` alongside text fields; `vector_query: "embedding:([], alpha: 0.3)"` | P0 |
| **Semantic / vector search** | The `alpha` blend; "warm and comforting" must return soups | P0 |
| **Federated multi_search** | The 4-search envelope in §5.6, one request across 2 collections | P0 |
| **NL search models** | Stage-2 parser, `nl_query_debug` feeds the reasoning trace | P0 |
| **Filter scoring `_eval`** | Sort slot 1: goal bucket + novelty bucket | P0 |
| **Faceting + facet stats** | Partial-match `fails[]`, client sort ranges | P0 |
| **`group_by` / `group_limit`** | `venue_id`, limit 3, **only above 20 hits, never on count queries** (§5.6) | P1 |
| **Geo search** | `location:(lat,lng,N mi)` filter — meaningful only because 2 venues sit 2–3 mi out; polygon filter for the campus-boundary overlay | P1 |
| **JOINs** | `food_items.venue_id -> venues.id`; `filter_by: "$venues(open_now:true)"`, `include_fields: "$venues(name,walk_minutes)"`. Venue closes → update 1 doc, not 40 | P1 |
| **Synonyms** | Campus slang → menu names ("gains"→protein, local nicknames). Seed 15–20, demos instantly | P1 |
| **Curation / overrides** | Pin a daily special. **`filter_curated_hits: true` is mandatory** or a pinned item bypasses an allergen exclusion | P1 |
| **Conversational search (RAG)** | Over `nutrition_notes` only, never over `food_items`. Answers "why this strategy", never "is this safe for me" | P2 |
| **Search analytics** | `analytics_tag` per query; capture no-hits queries only. Popular-query aggregation and query suggestions need traffic volume you won't have — skip them | P2 |
| **Stopwords + stemming** | Strip "I want something…"; stem fries/fried | P2 |
| **Presets** | Store hero-query param sets server-side, one more named feature | P3 |
| **Voice query** | `voice_query_model: {"model_name": "ts/whisper/base.en"}` on the collection. Audio must be **16 kHz 16-bit mono WAV**, base64, via `multi_search`. Requires `EMBEDDER=builtin` sizing | P3 |
| **Aliases** | `bootstrap.py` builds `v{n+1}` and swaps the alias, so re-seeding mid-build never leaves the index empty. Keep this — you will re-seed a dozen times tonight. Skip the batching/retry/dead-letter machinery from the old spec | P0 |

P0 and P1 is the realistic ship list. That is 11 distinct Typesense surfaces.

---

## 8. Repo layout

```
api/
├── app/
│   ├── main.py                    # FastAPI, CORS, routers
│   ├── config.py                  # pydantic-settings
│   ├── domain/                    # §6.2 — plain dataclasses, no wire format
│   │   ├── intent.py  item.py  outcome.py  venue.py  day.py
│   ├── api/
│   │   ├── routers/               # thin: parse -> service -> serialize
│   │   │   ├── search.py  venues.py  log.py  health.py
│   │   └── serializers/
│   │       └── v0.py              # THE ONLY file that knows JSON shape
│   ├── services/                  # returns domain objects, never dicts
│   │   ├── search.py  venues.py  log.py
│   ├── query/                     # NEW — the brain
│   │   ├── classify.py            # 3 plans, pure, unit-tested
│   │   ├── validate.py            # LLM output -> safe fragments. THE trust boundary
│   │   ├── compose.py             # filter_by + sort_by assembly
│   │   └── explain.py             # why[] and fails[] template generation
│   ├── typesense/
│   │   ├── client.py              # admin client
│   │   ├── schema.py              # all 4 collections, versioned
│   │   ├── query_builder.py       # THE single entry point -> multi_search body
│   │   └── nl_model.py            # idempotent NL model registration
│   ├── constraints/
│   │   ├── exclusions.py  goals.py  provenance.py
│   ├── history/
│   │   ├── store.py               # SQLModel + SQLite
│   │   └── signals.py             # remaining targets + repeated families
│   └── data/
│       ├── loader.py              # read seed.json, validate, fail loud
│       └── derive.py              # computed ranking axes, pure functions
├── scripts/
│   ├── bootstrap.py  reindex.py  prewarm.py  emit_samples.py
├── samples/                       # generated, committed, for frontend (§6.5)
├── data/
│   └── seed.json                  # THE dataset. Hardcoded. No pipeline.
└── tests/
    ├── unit/                      # classify, validate, derive, explain
    └── contract/                  # against a real Typesense
```

---

## 9. Build phases

Test-first. Each phase: write `TESTS`, watch them fail, implement, verify, commit.

### Phase 0 — Cloud + skeleton `[BE]` · 30 min
Provision the Cloud cluster (v29.1). FastAPI with CORS and `/api/health`. `client.py` reaching Cloud over https:443. One contract test: create a throwaway collection, index a doc, retrieve, delete.
**Verify:** `/api/health` reports `typesense_ok: true` against Cloud.

### Phase 1 — Schemas, derive, seed `[BE]` · 60 min
All four collections, created behind aliases. `derive.py` pure functions with unit tests (`protein_density` of 30g/500kcal = 6.0; zero calories = 0.0, no ZeroDivisionError). `loader.py` validation tests: each of the five failure conditions in §4 aborts the load with a message naming the item. Write `data/seed.json` — 5 venues, ~100 items, 25 notes, 15 synonym pairs.
**Verify:** `bootstrap.py` indexes clean; corrupt one item in `seed.json` five different ways and confirm each aborts with a useful message; run `reindex.py` while curling the alias in a loop — never a 404, never zero results.

### Phase 2 — Browse + core search `[BE]` · 45 min
`GET /api/venues`, `GET /api/venues/{id}/items`. Structured search only, no LLM: hybrid `query_by`, `filter_by`, `group_by`, facets, `exclude_fields`. Five pins on the map is the entire browse experience.
**Tests:** "something warm and comforting" returns soups though neither word appears (the hybrid proof — if it fails, `embedding` is missing from `query_by`); grouping caps a venue at 3 and is skipped below 20 hits; a 1-mile radius excludes the two outlying venues; no response ever contains a raw embedding array.
**Verify:** remove `embedding` from `query_by`, watch the semantic test fail, put it back. Now the test has teeth. Then run `emit_samples.py` and commit `samples/` so the frontend is unblocked (§6.5).

### Phase 3 — Safety layer `[BE]` · 45 min
`exclusions.py`, `provenance.py`, `validate.py`. The gated/ungated `multi_search` pair and exact `withheld_count`.
**Tests (the most important suite in the repo):**
- an item containing peanuts never appears under a peanut exclusion, across 20 phrasings
- `allergen_verified: false` items never appear when **any** exclusion is active, even with a clean allergen list
- with no exclusions, unverified items **do** appear (the gate is conditional)
- **a mocked LLM returning `a:1 || b:2` cannot surface an excluded item**
- the explicit `filter_by` string is never empty when exclusions are present
- `withheld_count` is **exact**: seed a known set, assert the number equals the docs removed by the provenance gate specifically. Both count queries must be ungrouped with `exhaustive_search: true` (§10.10)
**Verify:** read the generated `filter_by` string by hand. If you can't confirm it by eye, the composition is too clever.

### Phase 4 — Classifier + specific plan `[BE]` · 30 min
`classify.py` and the `SPECIFIC` path, no LLM. `"600 cal, under 20g fat, dry"` returns correct items in under 150ms.
**Verify:** the specific plan never issues an LLM call — assert on a call counter.

### Phase 5 — NL parse + validate + reasoning `[BE]` · 60 min
Register the NL model. Parse-only, validate, re-issue. `ReasoningTrace` populated including `rejected_clauses`. Cache + `prewarm.py`.
**Tests:** the applied filter always contains our exclusion fragment regardless of LLM output; a provider 500 sets `degraded: True` and falls back to keyword search without raising; hero-query invariants (right axis chosen, exclusion survived, radius sane) rather than strict equality.
**Verify:** `"exam in an hour, don't want to crash"` → low-glycemic items with a citation. Kill your internet mid-query → degrades cleanly. Run it 5 times → **identical safety filter every time**, even as the LLM's contribution varies.

### Phase 6 — History, novelty, top picks `[BE]` · 45 min
`POST /api/log`, `GET /api/log/today`, macros snapshotted. `signals.py` produces remaining targets and repeated families from the single implicit profile. Novelty `_eval` bucket. `explain.py` generates `why[]`.
**Tests:** logging twice creates two rows; a reindex changing nutrition does not alter past logs; after logging 3 burgers, burgers drop below a comparable non-burger in the same query; **a freshly bootstrapped database already yields a non-empty `recent_families`**, so novelty works with zero clicks.
**Verify:** log a meal → rerun the same search → ranking visibly shifted, and the UI can say why. Delete the SQLite file, re-run bootstrap, confirm novelty still demonstrates.

### Phase 7 — Sort override + polish `[BE]` · 20 min
`sort_override` allowlist, `sort_options` in the response, `filter_curated_hits: true`, synonyms loaded, analytics tags.
**Verify:** an unknown sort key returns 422; sorting by low sodium never surfaces an item the exclusions filtered.

**Optional if ahead:** conversational RAG over `nutrition_notes`, voice query, presets.

---

## 10. Known bugs and gotchas

**10.1 — v30.x NL search returns 0 hits.** With `nl_query=true`, the LLM's augmented `q` is ignored at search time because the engine prefers the original natural-language sentence written into `raw_query`. `parsed_nl_query.augmented_params` reports the correct values, so the debug payload looks perfect and only `found: 0` reveals it. Introduced in v30.0 by PR #2642, present in 30.0/30.1/30.2 and main; 29.x is unaffected. **Mitigation: pin 29.1.** If you must run 30.x, instruct the NL model's `system_prompt` to always emit `raw_query` with the same value as `q`. Our parse-only architecture (§5.2–5.4) also sidesteps it, since we never let Typesense execute the LLM's query — but pin 29.1 anyway.

**10.2 — NL search kills hybrid ranking.** When the LLM decides a query is filter-shaped it emits `q: "*"`. A wildcard has no text to embed, so semantic ranking silently vanishes on exactly the queries you're demoing. §5.4 fixes this by always supplying our own semantic query string.

**10.3 — Filter concatenation has no parentheses.** See §5.3. Never rely on Typesense to AND the LLM's filter onto yours safely.

**10.4 — No arithmetic in `sort_by`.** There is no `protein_g / calories`. `_eval()` with boolean expressions and custom scores is the only computed-scoring primitive. Every ratio or composite is computed at load time in `derive.py`. Wanting to compute inside `sort_by` means you need a new derived field and a reindex, not a cleverer query.

**10.5 — Max 3 sort fields.** Budget them (§5.5).

**10.6 — Auto-embeddings regenerate on restart.** There's a reported issue where embeddings are rebuilt on every restart even with unchanged data. On Cloud, version and config changes restart the node. At 120 docs this is seconds; don't schedule a config change mid-demo anyway.

**10.7 — Curation bypasses filters.** Pinned hits can appear despite `filter_by` unless `filter_curated_hits: true` is set. A merchandising feature that defeats the allergen gate is the worst bug in this codebase. Set it globally.

**10.8 — JOIN + hybrid interaction is unverified.** Test the JOIN against a hybrid query in Phase 2. If reference fields misbehave with `embedding` in `query_by`, fall back to the denormalized `venue_name` / `walk_minutes` fields already in the schema and drop the JOIN to a nice-to-have.

**10.9 — CLIP is unavailable with `EMBEDDER=remote`.** Image embedding is built-in-model-only. Camera is cut from this build regardless; noted so nobody rediscovers it at 9pm.

---

**10.10 — `group_by` makes `found` approximate.** Introduced in v29. Any count you derive by diffing two grouped queries is wrong. All counting queries run ungrouped with `exhaustive_search: true`. See §5.6.

**10.11 — Semantic search always returns something at this corpus size.** With ~125 documents every query has a nearest neighbour, so a bad match looks exactly as confident as a good one. Keep `alpha` keyword-leaning (0.3 or lower) so exact matches beat vague vector proximity, and treat seed description quality as embedding quality. There is no statistical mass to smooth this out.

**10.12 — Empty results are the common path, not an edge case.** An LLM that generates four ANDed constraints against ~100 dishes will return zero hits regularly. Search 3 in the envelope is not a nicety; it is what the user sees on a meaningful fraction of queries.

## 11. Local loop

```bash
cd api
uv sync
cp .env.example .env                  # fill in Cloud host + keys
python scripts/bootstrap.py           # collections, NL model, seed, synonyms
uvicorn app.main:app --reload --port 8000
pytest                                # unit + contract

python scripts/reindex.py             # rebuild from seed.json + alias swap
python scripts/prewarm.py             # cache hero queries BEFORE demoing
```

---

## 12. Demo checklist

- [ ] `prewarm.py` run, hero queries cached
- [ ] Local Docker fallback started and seeded, `TYPESENSE_HOST` swap tested
- [ ] Three rehearsed queries: one situational (`"quick energy before an exam"`), one hyper-specific (`"600 cal, under 800mg sodium, dry, something I can eat walking"`), one with exclusions active so `withheld_count` shows
- [ ] Fresh bootstrap confirmed: novelty re-ranks with zero clicks, no sign-in step anywhere in the flow
- [ ] Reasoning panel open on screen when you say "the model never touches the allergen filter"
- [ ] Say "placeholder data modeled on five real venues" once, early. Do not let a judge discover it