-- Marketplace V2 Phase 2.0: Admin ingest jobs
-- Adds ingest_jobs table used to track admin-triggered profile ingestion.
--
-- NOTE: V1 tables remain unchanged.

BEGIN;

CREATE TABLE IF NOT EXISTS ingest_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  requested_by_user_id INTEGER NOT NULL,
  input_url TEXT NOT NULL,
  detected_platform TEXT NOT NULL CHECK(detected_platform IN ('instagram','youtube')),
  normalized_profile_url TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('queued','running','success','failed')) DEFAULT 'queued',
  error TEXT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  finished_at TEXT NULL,
  FOREIGN KEY (requested_by_user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_ingest_jobs_status ON ingest_jobs(status);
CREATE INDEX IF NOT EXISTS idx_ingest_jobs_created_at ON ingest_jobs(created_at);

COMMIT;
