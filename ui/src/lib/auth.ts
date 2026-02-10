import crypto from 'node:crypto';
import type { NextRequest } from 'next/server';
import { db } from './db';

export const OTP_TTL_MIN = 10;
export const SESSION_TTL_DAYS = 14;

export function hashSha256(input: string | Buffer): string {
  const buf = typeof input === 'string' ? Buffer.from(input, 'utf8') : input;
  return crypto.createHash('sha256').update(buf).digest('hex');
}

export function createOtpCode(): string {
  // 6-digit numeric
  const n = crypto.randomInt(0, 1_000_000);
  return String(n).padStart(6, '0');
}

export function createSessionToken(): string {
  // raw token stored only in cookie; DB stores sha256(token)
  return crypto.randomBytes(32).toString('hex');
}

function nowIso(): string {
  return new Date().toISOString();
}

function addMinutesIso(min: number): string {
  return new Date(Date.now() + min * 60_000).toISOString();
}

function addDaysIso(days: number): string {
  return new Date(Date.now() + days * 24 * 60 * 60_000).toISOString();
}

export type UserRow = {
  id: number;
  email: string;
  role: 'influencer' | 'business' | 'admin';
};

export function rateLimitOtpOrThrow(email: string): void {
  // Demo-safe basic rate limit: max 5 OTP requests per email per hour
  const d = db();
  const cutoff = new Date(Date.now() - 60 * 60_000).toISOString();
  const row = d
    .prepare(`SELECT count(*) as cnt FROM otp_codes WHERE email = ? AND created_at >= ?`)
    .get(email, cutoff) as any;
  const cnt = Number(row?.cnt || 0);
  if (cnt >= 5) {
    throw new Error('Too many OTP requests. Please try again later.');
  }
}

export function storeOtp(email: string, code: string): void {
  const d = db();
  const code_hash = hashSha256(code);
  d.prepare(
    `INSERT INTO otp_codes(email, code_hash, expires_at, created_at)
     VALUES(?,?,?,?)`
  ).run(email, code_hash, addMinutesIso(OTP_TTL_MIN), nowIso());
}

export function consumeValidOtp(email: string, code: string): boolean {
  const d = db();
  const code_hash = hashSha256(code);
  const now = nowIso();

  // Get the latest unexpired OTP for this email
  const row = d
    .prepare(
      `SELECT id, code_hash, expires_at
       FROM otp_codes
       WHERE email = ? AND expires_at >= ?
       ORDER BY id DESC
       LIMIT 1`
    )
    .get(email, now) as any;

  if (!row) return false;
  if (String(row.code_hash) !== code_hash) return false;

  // Prevent reuse: delete this OTP row
  d.prepare(`DELETE FROM otp_codes WHERE id = ?`).run(row.id);
  return true;
}

export function findOrCreateUser(email: string, role: UserRow['role']): UserRow {
  const d = db();

  const existing = d
    .prepare(`SELECT id, email, role FROM users WHERE email = ? LIMIT 1`)
    .get(email) as any;

  if (existing) {
    return {
      id: Number(existing.id),
      email: String(existing.email),
      role: existing.role as UserRow['role'],
    };
  }

  d.prepare(`INSERT INTO users(email, role, created_at) VALUES(?,?,?)`).run(email, role, nowIso());

  const created = d
    .prepare(`SELECT id, email, role FROM users WHERE email = ? LIMIT 1`)
    .get(email) as any;

  return {
    id: Number(created.id),
    email: String(created.email),
    role: created.role as UserRow['role'],
  };
}

export function createSession(userId: number): { token: string; expiresAt: string } {
  const d = db();
  const token = createSessionToken();
  const token_hash = hashSha256(token);
  const expires_at = addDaysIso(SESSION_TTL_DAYS);
  d.prepare(`INSERT INTO sessions(user_id, token_hash, expires_at, created_at) VALUES(?,?,?,?)`).run(
    userId,
    token_hash,
    expires_at,
    nowIso()
  );
  return { token, expiresAt: expires_at };
}

export function deleteSessionByToken(token: string): void {
  const d = db();
  const token_hash = hashSha256(token);
  d.prepare(`DELETE FROM sessions WHERE token_hash = ?`).run(token_hash);
}

export function getUserFromRequest(req: NextRequest): UserRow | null {
  const token = req.cookies.get('mp_session')?.value;
  if (!token) return null;

  const d = db();
  const token_hash = hashSha256(token);
  const now = nowIso();

  const row = d
    .prepare(
      `SELECT u.id, u.email, u.role
       FROM sessions s
       JOIN users u ON u.id = s.user_id
       WHERE s.token_hash = ? AND s.expires_at >= ?
       LIMIT 1`
    )
    .get(token_hash, now) as any;

  if (!row) return null;
  return {
    id: Number(row.id),
    email: String(row.email),
    role: row.role as UserRow['role'],
  };
}
