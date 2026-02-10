# Marketplace V2 — DB Changes

## Principles
- V1 tables remain the foundation for discovery.
- **No V1 tables will be mutated directly by user actions.**
- All new write activity (auth, messaging, claims, jobs) happens via **new tables**.
- Trust score fields remain computed and read-only from the UI.

> Note: ingestion may continue to update `social_profiles` fields as a system process. User-initiated writes should not.

---

## New tables (proposed)

### 1) `users`
Stores OTP-verified user identities.
- `id`
- `email` (unique)
- `role` (influencer | business | admin)
- `created_at`
- `status` (active | disabled)

### 2) `businesses`
- `id`
- `owner_user_id` (FK → users)
- `name`
- `created_at`

### 3) `influencer_profiles`
Stores influencer-owned metadata that should not overwrite V1 discovery tables.
- `id`
- `user_id` (FK → users)
- `display_name` (optional override)
- `public_bio` (optional)
- `created_at`

### 4) `claims`
Links a verified user to an existing creator/profile.
- `id`
- `user_id` (FK → users)
- `creator_id` (FK → creators)
- `social_profile_id` (FK → social_profiles)
- `verification_method` (bio_code | manual)
- `verification_code` (for bio_code)
- `status` (pending | verified | rejected | expired)
- `created_at`, `verified_at`

### 5) `threads`
Message threads between business and influencer.
- `id`
- `business_id` (FK → businesses)
- `influencer_user_id` (FK → users)
- `creator_id` (FK → creators) (optional, for context)
- `created_at`

### 6) `messages`
- `id`
- `thread_id` (FK → threads)
- `sender_user_id` (FK → users)
- `body`
- `created_at`
- `status` (sent | delivered | read)

### 7) `ingestion_jobs`
Tracks ingestion runs.
- `id`
- `platform` (instagram | youtube)
- `target_type` (creator | social_profile)
- `target_id`
- `status` (queued | running | success | failed)
- `created_at`, `started_at`, `finished_at`
- `error` (nullable)

### 8) `ingestion_job_logs` (optional)
- `id`
- `job_id` (FK → ingestion_jobs)
- `level` (info | warn | error)
- `message`
- `created_at`

---

## Migration strategy
- Use SQLite migrations in V2 (versioned SQL files).
- Keep migrations additive and reversible where possible.
- Design schemas so migration to a future DB (Postgres) is straightforward:
  - use explicit IDs
  - avoid SQLite-only quirks
  - store timestamps in ISO-8601

---

## Backward compatibility
- Existing V1 fields keep their meaning.
- V2 tables reference V1 tables via foreign keys.
- UI can render V1 creators/social_profiles even if V2 tables are empty.
