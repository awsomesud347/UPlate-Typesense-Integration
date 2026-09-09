# UPlate Search

> Every food app indexes restaurants. We index food.

Unified item-level food index — dining halls and off-campus restaurants in one Typesense collection — searched in plain English, filtered by hard constraints the LLM structurally cannot loosen, ranked by fit to your targets.

**Typesense Hackathon — Sept 8, 2026.** Full phased build plan lives in [BUILD_PLAN.md](BUILD_PLAN.md). Read §5 (API contract) before writing anything.

## Stack

- **`api/`** — FastAPI + Python 3.12+, typesense-python, Claude API for query understanding. Backend dev + Typesense integration.
- **`web/`** — React 18 + Vite + TypeScript + Tailwind + TanStack Query. UI dev. Phone-first (~390px), demo cropped to mobile.
- **Typesense v30.x** — self-hosted. Docker if you have it (`docker compose up -d`); on the Docker-less Windows machine we run the native Linux binary inside WSL (see below).

## Quickstart

### 1. Typesense

**With Docker:**
```bash
docker compose up -d
curl http://localhost:8108/health
```

**Without Docker (WSL2):**
```bash
# inside WSL Ubuntu:
curl -O https://dl.typesense.org/releases/30.2/typesense-server-30.2-linux-amd64.tar.gz
tar xzf typesense-server-30.2-linux-amd64.tar.gz
mkdir -p ~/typesense-data
./typesense-server --data-dir ~/typesense-data --api-key uplate-dev-key --enable-cors
# port 8108 is reachable from Windows at localhost:8108
```

### 2. Backend

```bash
cd api
python -m venv .venv
.venv\Scripts\activate        # Windows  (source .venv/bin/activate elsewhere)
pip install -e ".[dev]"
copy .env.example .env        # then fill in ANTHROPIC_API_KEY
python scripts/bootstrap.py   # create collection + seed
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd web
npm install
npm run dev                   # http://localhost:5173
```

## The contract

`POST /api/search` — request/response shapes are defined **once**, in [`api/app/schemas/search.py`](api/app/schemas/search.py), and mirrored field-for-field in [`web/src/lib/types.ts`](web/src/lib/types.ts). Fixture responses for UI work without a running backend: [`web/src/lib/fixtures.ts`](web/src/lib/fixtures.ts).

`/api/search` hits real Typesense. **To work without a running Typesense**, set `USE_FIXTURES=true` in `api/.env` — it serves fixture data instead. It's opt-in and off by default because fixture data does not honor allergen exclusions; every fixture response is stamped in the reasoning trace so it can't be mistaken for a real search.

## Typesense v30 gotchas (cost us time — don't repeat them)

- **The per-collection synonyms API is removed in v30+.** `collections/{c}/synonyms` returns 404. v30 uses top-level **synonym sets**: `client.synonym_sets[name].upsert({"items": [...]})`, referenced per-search via the `synonym_sets` query param. Most tutorials and LLM answers still show the old API. See [`app/typesense/synonyms.py`](api/app/typesense/synonyms.py).
- **`sort_by` cannot do arithmetic.** No `protein_g / calories`. Every ratio is precomputed at ingest in [`derive.py`](api/app/ingest/derive.py) and stored as a plain numeric field.
- **Hybrid search only happens if `embedding` is in `query_by`** alongside the text fields. Drop it and you get keyword-only search that looks fine on easy queries and silently fails every semantic one. `test_hybrid_semantic_match` exists to catch exactly that.

## The safety invariant

Hard exclusions (allergens, diet flags) go in the **explicit `filter_by`**, which Typesense ANDs on top of anything the LLM generates. The LLM can only narrow results, never widen them. Items with `allergen_verified: false` are **withheld** (and counted) whenever any exclusion is active. Do not "optimize" this.

## Who owns what

| Area | Owner |
|---|---|
| `web/` — UI, components, phone frame | UI dev |
| `api/app/routers/`, `api/app/llm/` — endpoint + Claude layer | backend dev |
| `api/app/typesense/`, `api/app/ingest/`, `api/data/seed/`, `scripts/` | Typesense integration |
| `api/app/schemas/` + `web/src/lib/types.ts` — **change together or not at all** | everyone |
