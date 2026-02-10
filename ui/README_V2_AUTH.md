# Marketplace V2 Phase 1 — Auth (Demo OTP)

This document explains how to apply the Phase 1 auth migration and test the demo OTP flow.

> Demo behavior: OTP is printed to server logs. No email provider is required.

---

## Apply migration (no sqlite3 CLI required)

From `marketplace/`:

```bash
python3 - <<'PY'
import pathlib, sqlite3

db = '/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/marketplace.db'
sql_path = '/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/migrations/2026_02_v2_phase1_auth.sql'

sql = pathlib.Path(sql_path).read_text()
con = sqlite3.connect(db)
con.executescript(sql)
con.commit()
con.close()
print('migration_applied:', sql_path)
PY
```

---

## Run dev server

```bash
cd ui
npm run dev -- -H 0.0.0.0 -p 3000
```

---

## Test with curl

### 1) Start OTP
```bash
curl -s -X POST http://localhost:3000/api/auth/start \
  -H 'content-type: application/json' \
  -d '{"email":"test@example.com","role":"business"}'
```

Check server logs for:
`[DEMO OTP] email=test@example.com role=business code=123456`

### 2) Verify OTP (creates session cookie)
```bash
curl -i -s -X POST http://localhost:3000/api/auth/verify \
  -H 'content-type: application/json' \
  -d '{"email":"test@example.com","code":"123456"}'
```

### 3) Call /api/me using the cookie
Copy the `Set-Cookie: mp_session=...` value from step 2 and use it:

```bash
curl -s http://localhost:3000/api/me \
  -H 'cookie: mp_session=YOUR_TOKEN_HERE'
```

### 4) Logout
```bash
curl -s -X POST http://localhost:3000/api/auth/logout \
  -H 'cookie: mp_session=YOUR_TOKEN_HERE'
```

---

## Notes
- OTP codes are hashed before storing.
- Session tokens are hashed before storing; raw token is only stored in the HttpOnly cookie.
- Basic rate limit: max 5 OTP requests per email per hour.
- This is demo-safe and intended for investors/testing. Replace OTP delivery with email/SMS in later phases.
