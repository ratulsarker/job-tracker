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

## Rahat tab — second person's board (Canada software/tech)
- Jobs tagged `source='rahat-*'` form a separate board surfaced by the **👤 Rahat · CA**
  tab. The partition is the `source` column (no schema change): the Rahat tab shows
  only those rows, and every other tab — plus the stat pills / category dropdown
  (`build_meta`) — excludes them, so Rahat's roles never mix into Ratul's tabs.
- Daily ingest: a Vercel cron (`crons` in `vercel.json`, 11:00 UTC) hits
  `GET /api/cron` → `ingest_rahat()`, which pulls Canada roles matched to Rahat's CV
  (Java/SQL/JS/Angular/Power Platform/data/technical-consultant), word-boundary
  skill-scores + de-dupes them (by URL and company+role), and inserts up to
  `RAHAT_MAX_INSERT` (25) per run.
  - **Source priority**: Adzuna CA (`ADZUNA_APP_ID` / `ADZUNA_APP_KEY`, free key —
    best Canada coverage) → Remotive keyless fallback (remote roles filtered to
    Canada / North America / Worldwide). Works with zero keys; better with the key.
  - Protect the endpoint by setting `CRON_SECRET` in Vercel — Vercel then sends it as
    `Authorization: Bearer …`; manual runs can pass `?key=<secret>`. If unset, the
    endpoint runs open.

## Export (CSV / Excel)
- Header **Export** menu → `GET /api/export?...&format=csv|xlsx`. It runs the *exact*
  current tab + filters + search through `apply_filters` with **no pagination**, so
  what you export equals what's on screen (e.g. search `bmo` → only BMO rows).
- CSV is UTF-8-BOM (clean in Excel); XLSX is styled via `openpyxl` (bold header,
  column widths, frozen header row, autofilter). XLSX falls back to CSV if `openpyxl`
  is unavailable.

## Filtering
- Quick search (curated tabs) is multi-term **AND** over company/role/category/location;
  the Search tab's full mode spans the whole blob (notes/description too). `exclude`
  terms and category/status filters compose with the tab and the search.

## Env vars (Vercel)
- `DATABASE_URL` (required) · `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` (optional, improves
  Rahat ingest) · `CRON_SECRET` (optional, protects `/api/cron`) · `APP_PASSWORD`
  (legacy auth, currently open).

## Notes
- The tracker currently keeps some legacy fields (like `tier`) for compatibility, but the main UI is now driven by fit/lane/status rather than tiers.
- Small-company, fall-finance, and micro-mature targeting logic lives in the API filtering layer.
