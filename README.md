# Marketplace V1 (Read-only Demo)

Marketplace V1 is a **read-only demo** for discovering and comparing creators across **Instagram** and **YouTube** using a precomputed **Trust Score (0–100)**.

## What this is
- A lightweight creator directory (UI + APIs)
- Trust-based discovery using stored scores and flags
- Built for validation, internal demo, and iteration (not production)

## What this is not (V1)
- No authentication
- No payments
- No in-platform messaging
- No analytics dashboards
- No database writes
- No migrations (schema is frozen)

## Project structure
- `marketplace.db` — SQLite database (local only; not committed)
- `ui/` — Next.js (App Router) frontend + API routes
- `scripts/` — ingestion and maintenance scripts (offline)

## Run the UI
```bash
cd ui
npm install
npm run dev -- -H 0.0.0.0 -p 3000
```

## Environment
- `MARKETPLACE_DB_PATH` (optional): absolute path to SQLite DB.
  - Default: `../marketplace.db` from `ui/`.
