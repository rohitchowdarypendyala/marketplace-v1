# Marketplace V2 — API Contracts (Paths Only)

This document lists the proposed REST endpoints for V2. No implementation details.

---

## Auth
- `POST /api/v2/auth/start-otp`
- `POST /api/v2/auth/verify-otp`
- `POST /api/v2/auth/logout`
- `GET  /api/v2/me`

---

## Ingestion
- `POST /api/v2/ingestion/jobs` (create job)
- `GET  /api/v2/ingestion/jobs` (list jobs)
- `GET  /api/v2/ingestion/jobs/:id`
- `POST /api/v2/ingestion/jobs/:id/run` (manual trigger)

---

## Messaging
- `POST /api/v2/threads` (create thread)
- `GET  /api/v2/threads` (list threads)
- `GET  /api/v2/threads/:id`
- `POST /api/v2/threads/:id/messages` (send message)
- `GET  /api/v2/threads/:id/messages` (list messages)

---

## Claims
- `POST /api/v2/claims` (create claim)
- `GET  /api/v2/claims` (list my claims)
- `POST /api/v2/claims/:id/verify` (bio code verification)

---

## Admin actions
- `POST /api/v2/admin/creators` (manual add creator)
- `POST /api/v2/admin/social-profiles` (manual add profile)
- `POST /api/v2/admin/claims/:id/approve`
- `POST /api/v2/admin/claims/:id/reject`
- `GET  /api/v2/admin/ingestion/jobs` (overview)

---

## Notes
- V1 endpoints remain available as read-only.
- V2 endpoints are namespaced under `/api/v2` for clarity and compatibility.
