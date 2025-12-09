# TURF Registry & Resolver

A tiny, GitHub-ready scaffold that implements:

- `turf.track_registry.v1` (JSON model)
- Resolver with exact/alias + fuzzy (Levenshtein via rapidfuzz)
- Minimal `turf.execution_request.v1` → `turf.scrape_plan.v1` wiring
- CLI: `turf resolve` and `turf plan`
- Tests for resolver

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# Try resolve against the NSW seed registry
turf resolve --registry data/nsw_seed.json --tracks "werigee" "wagga riverside" --state-hint VIC
turf resolve --registry data/nsw_seed.json --tracks "Randwick" "Ballina"

# Build a minimal scrape plan
turf plan --registry data/nsw_seed.json --date 2025-12-09 --states NSW --tracks "Wagga" "Ballina" > plan.json
cat plan.json
```

## Repo layout

- `src/turf/models.py` — Pydantic models
- `src/turf/normalise.py` — normalisation helpers
- `src/turf/resolver.py` — index + resolve
- `src/turf/cli.py` — Typer CLI
- `data/nsw_seed.json` — tiny seed registry for NSW
- `tests/test_resolver.py` — unit tests

## GitHub Actions

The provided workflow runs tests on push/PR.

## Notes

- The registry builder is left as a stub in `src/turf/registry_builder.py` for future work (RA/R&S ingestion).

