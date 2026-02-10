# Marketplace V2 — Overview

## Purpose
Marketplace V2 builds on the stable V1 read-only demo and introduces the minimum write-capable platform needed to support real workflows:
- creator onboarding and verification
- business accounts
- profile ingestion as a managed process
- in-app messaging between businesses and influencers

V2 must remain **investor-demoable** while being engineered cleanly and extensibly.

---

## High-level goals
- Enable **OTP-based registration** for influencers and businesses.
- Support **claiming** and **verifying** creator profiles.
- Run **managed ingestion** (Instagram + YouTube) to keep stats fresh.
- Allow **business → influencer** communication via **in-app messaging**.
- Preserve V1 trust-based discovery while adding identity and workflow.

---

## What V2 adds beyond V1
- **Write operations** (new tables only) for:
  - users/accounts
  - business entities
  - claims and verification status
  - messages and threads
  - ingestion jobs and logs
- **Authentication**:
  - OTP login/signup
  - session/token-based auth for API access
- **Messaging**:
  - internal messaging UI + API
  - moderation-friendly storage (auditable)
- **Operational tooling**:
  - lightweight admin/manual add workflow (explicitly labeled)

---

## V2 rules (must not regress)
- **OTP is mandatory for user identity.**
- **Messaging is in-app only by default** (no email exposure by default).
- **Trust score remains computed, not user-editable.**
- **Admin-added profiles must be labeled clearly** (e.g., “Added by Marketplace Team”).

---

## Out of scope (still not in V2)
- Payments or billing flows
- Full campaign management (contracts, deliverables, invoicing)
- Advanced analytics dashboards (cohorts, attribution, conversion tracking)
- Automated outbound messaging / email campaigns
- Public API for third-party integrations

---

## Backward compatibility and preservation
- V1 is preserved forever as a rollback-safe baseline.
- V2 development happens only on the `v2` branch.
- V1 trust score meaning remains unchanged.

---

## Non-goals
- Recomputing trust score in the UI
- Allowing users to edit trust score fields
- Over-automating identity merges (must remain safe and human-auditable)
