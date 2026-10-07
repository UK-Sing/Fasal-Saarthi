# Fasal Sarthi – agent notes

Backend: FastAPI + OR-Tools CP-SAT in `backend/` (Python 3.12 via uv). `frontend/` is a separate git repo (ignored by the root repo); the typed client source of truth is `frontend_starter/lib/api.ts`.

## Commands (run from `backend/`)

- Tests: `uv run pytest -q` (tests run on `DATABASE_BACKEND=memory`, live data off — see `tests/conftest.py`)
- Firestore smoke test (real project, cleans up after itself): `FIREBASE_SMOKE=1 uv run pytest -q tests/test_firestore_smoke.py -s`
- API: `uv run uvicorn app.main:app --reload` (Swagger at <http://localhost:8000/docs>)
- Demo rehearsal (API must be running): `uv run python ../scripts/demo.py [BASE_URL]`
- Typecheck the client: `frontend/node_modules/.bin/tsc --noEmit --strict --skipLibCheck --target es2022 --module esnext --moduleResolution bundler --lib es2022,dom --types node --typeRoots frontend/node_modules/@types frontend_starter/lib/api.ts` (from repo root)

## Conventions

- Config is read from repo-root `.env` (then `backend/.env`, then real env vars). Relative SQLite paths resolve against `backend/`. `DATABASE_BACKEND` selects persistence: `firestore` (default; needs `FIREBASE_PROJECT_ID` + `FIREBASE_CREDENTIALS` pointing at the service-account key outside the repo), `sqlite` (offline fallback via `DATABASE_URL`), `memory` (tests). Endpoints go through the repository layer in `app/repositories/`; farm ids are opaque strings.
- All agronomic numbers live in `backend/app/data/*.yaml`; the LLM only rephrases template text, never decides crops/doses.
- If you change `crops.yaml` or `PLANS` weights, re-run tests: `test_price_crash_changes_plan` and `test_lower_soil_changes_balanced_plan` guard the demo story.
