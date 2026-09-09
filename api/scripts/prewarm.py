"""Demo insurance. Runs the hero queries through the live API so the LLM
interpreter's cache is populated before you present.

Hackathon wifi plus an LLM round-trip on stage is how a demo dies. Run this
right before presenting, from the same process the demo will hit.

Usage: python scripts/prewarm.py [api_base_url]
"""
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

CONTEXT = {
    "lat": 40.4249,
    "lng": -86.9111,
    "campus_id": "purdue",
    "now_minutes": 720,
    "exclude_allergens": [],
    "diet_flags": [],
    "goal": "none",
    "radius_mi": 3.0,
}

HERO_QUERIES = [
    ("exam in an hour, don't want to crash", {}),
    (
        "my friend has a nut allergy and I'm vegetarian, find somewhere we can both eat",
        {"exclude_allergens": ["peanut", "tree_nut"], "diet_flags": ["vegetarian"]},
    ),
    ("something warm and comforting", {}),
    ("post workout, need protein", {"goal": "high_protein"}),
    ("something light before class", {"goal": "light"}),
]

if __name__ == "__main__":
    ok = True
    # One client for all queries: a fresh connection per request adds seconds on
    # Windows (localhost resolves to ::1 first and falls back), which would make
    # these numbers meaningless as a pre-demo latency check.
    with httpx.Client(timeout=30.0) as client:
        client.get(f"{BASE}/api/health")  # absorb cold-start into an untimed call

        for query, overrides in HERO_QUERIES:
            ctx = {**CONTEXT, **overrides}
            start = time.perf_counter()
            try:
                r = client.post(
                    f"{BASE}/api/search", json={"query": query, "context": ctx}
                )
                r.raise_for_status()
                data = r.json()
                elapsed = int((time.perf_counter() - start) * 1000)
                flag = " [DEGRADED]" if data["reasoning"]["degraded"] else ""
                print(
                    f"{elapsed:>5}ms  {len(data['hits']):>2} hits  "
                    f"withheld={data['withheld_count']}{flag}  {query[:48]}"
                )
            except Exception as e:
                ok = False
                print(f"  FAIL  {query[:48]}: {e}")

    print("\nRun this again right before presenting - it warms the LLM cache.")
    sys.exit(0 if ok else 1)
