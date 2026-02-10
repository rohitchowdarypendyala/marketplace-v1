# Marketplace V2 — Investor Demo Flow

This is the step-by-step story for a clean, repeatable V2 demo.

---

## 1) Influencer signs up
- Open the app and show influencer signup.
- User enters email → receives OTP → verifies.
- Emphasize: OTP establishes identity; V2 is no longer “anonymous demo data”.

---

## 2) Stats are pulled
- Influencer either:
  - claims an existing profile, or
  - submits a profile for ingestion.
- Show ingestion job status moving through queued → running → success.
- Show updated stats reflected in the profile view.
- Mention: trust score remains computed and not user-editable.

---

## 3) Business signs up
- Business enters email → OTP verify.
- Business can browse creators like in V1.

---

## 4) Business messages influencer
- Business opens a creator page and clicks “Message”.
- A thread is created and the business sends a short intro.
- Influencer sees the message in their inbox.
- Emphasize: messaging is in-app; email is not exposed by default.

---

## 5) Trust + transparency explained
- Show Trust Score prominently.
- Open trust flags tooltips.
- Explain that flags communicate limitations/anomalies so businesses can make informed decisions.

---

## Demo safety notes
- Admin-added profiles must show “Added by Marketplace Team” label.
- Keep the dataset small and pre-warmed for demo reliability.
