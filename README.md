# Job Tracker

Job search dashboard for Ratul Sarker.

## What it is
- Vercel-deployed lightweight dashboard
- Python API (`api/jobs.py`)
- Static frontend (`public/index.html`)
- Job data stored in a separate GitHub Gist backend

## Live
- Production: `https://jobs.ratulsarker.com`

## Data backend
- GitHub Gist stores `jobs.json`
- App reads/writes the gist rather than using a traditional database

## Local structure
- `api/jobs.py` — API + filtering + gist sync logic
- `public/index.html` — UI
- `vercel.json` — Vercel routing
- `requirements.txt` — Python deps

## Notes
- The tracker currently keeps some legacy fields (like `tier`) for compatibility, but the main UI is now driven by fit/lane/status rather than tiers.
- Small-company, fall-finance, and micro-mature targeting logic lives in the API filtering layer.
