# Job Tracker

Job search dashboard for Ratul Sarker.

## What it is
- Vercel-deployed lightweight dashboard
- Python API (`api/jobs.py`)
- Static frontend (`public/index.html`)
- Job data stored in a Neon Postgres database

## Live
- Production: `https://jobs.ratulsarker.com`

## Data backend
- Neon Postgres (project `job-tracker`); single `jobs` table
- Connection via `DATABASE_URL` env var (pooled endpoint on Vercel)
- Indexed: btree on status/category/date_added, pg_trgm GIN on a generated
  `search_blob` column for fast substring search
- Reads load all rows then filter/score in Python (curated tabs); writes are
  atomic single-row INSERT/UPDATE/DELETE (no read-modify-write race)
- Migrated off the legacy GitHub Gist on 2026-06-13

## Local structure
- `api/jobs.py` — API + filtering + gist sync logic
- `public/index.html` — UI
- `vercel.json` — Vercel routing
- `requirements.txt` — Python deps

## Notes
- The tracker currently keeps some legacy fields (like `tier`) for compatibility, but the main UI is now driven by fit/lane/status rather than tiers.
- Small-company, fall-finance, and micro-mature targeting logic lives in the API filtering layer.
