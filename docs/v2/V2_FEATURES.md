# Marketplace V2 — Feature Plan

This document defines the V2 feature scope in clear, buildable sections.

---

## 1) Influencer registration (OTP-based)

### Goals
- Allow influencers to create an account with verified identity.
- Establish a safe basis for profile claiming and messaging.

### Requirements
- Email OTP signup/login.
- Session/token creation after OTP verification.
- Minimal profile: name (optional), email, created_at.

### Notes
- OTP is mandatory for identity.
- No social OAuth in the first cut unless needed for verification.

---

## 2) Business registration (OTP-based)

### Goals
- Allow businesses to create accounts and contact influencers via in-app messaging.

### Requirements
- Email OTP signup/login.
- Basic business entity: company_name (optional), email domain (optional), created_at.
- Ability to view creators and start message threads.

---

## 3) Admin/manual influencer add (no auth)

### Goals
- Enable manual entry of creators during demos or internal onboarding.

### Requirements
- A minimal admin-only route/tool (protected by environment secret or internal access).
- Any creator/profile added through this path must be labeled:
  - “Added by Marketplace Team”

### Notes
- This is an operational shortcut for demos; it should not bypass ingestion/verification in the long term.

---

## 4) Profile ingestion (Instagram / YouTube)

### Goals
- Convert ingestion into a managed process that can be re-run safely.

### Requirements
- Create ingestion jobs with status and logs.
- Support:
  - Instagram ingestion (session-based, no OAuth)
  - YouTube public ingestion
- Store raw artifacts where needed for debugging (paths only, not in DB blobs unless required).

### Notes
- Ingestion updates should not allow user edits to trust score fields.

---

## 5) Internal messaging (business → influencer)

### Goals
- Allow businesses to contact influencers without exposing personal contact details by default.

### Requirements
- In-app threads and messages.
- Message status: sent/delivered/read (at minimum: sent).
- Basic safety controls:
  - rate limiting
  - abuse reporting hooks (future)

### Notes
- Messaging is internal-only by default.
- External email can remain as a fallback path, but is not the default in V2.

---

## 6) Claim profile flow (existing → extended)

### Goals
- Move from V1 “demo request” to a real verification flow.

### Requirements
- Claim request tied to an OTP-verified influencer account.
- Verification methods (phased):
  1. Bio code verification (Instagram/YouTube)
  2. Manual review (admin)
- Claim status lifecycle: pending → verified / rejected / expired.

### Notes
- Claiming links an influencer identity to existing creators/social_profiles.
- No automatic merging across creators without explicit verification.
