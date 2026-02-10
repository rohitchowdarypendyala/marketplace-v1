import { NextRequest, NextResponse } from 'next/server';
import { badRequest, json } from '../../../../lib/http';
import {
  consumeValidOtp,
  createSession,
  findOrCreateUser,
  SESSION_TTL_DAYS,
  type UserRow,
} from '../../../../lib/auth';

export const runtime = 'nodejs';

// POST /api/auth/verify
// body: { email, code }
export async function POST(req: NextRequest) {
  let body: any;
  try {
    body = await req.json();
  } catch {
    return badRequest('invalid JSON body');
  }

  const email = String(body?.email || '').trim().toLowerCase();
  const code = String(body?.code || '').trim();

  if (!email || !email.includes('@')) return badRequest('email is required');
  if (!/^[0-9]{6}$/.test(code)) return badRequest('code must be a 6-digit number');

  const ok = consumeValidOtp(email, code);
  if (!ok) {
    return badRequest('invalid or expired OTP');
  }

  // Role handling (demo): if user does not exist, create with requested role (default business).
  const roleRaw = String(body?.role || 'business').trim().toLowerCase();
  const desiredRole = roleRaw === 'influencer' ? 'influencer' : 'business';

  const user: UserRow = findOrCreateUser(email, desiredRole);

  const sess = createSession(user.id);

  const res = json({ ok: true, user });
  res.cookies.set({
    name: 'mp_session',
    value: sess.token,
    httpOnly: true,
    sameSite: 'lax',
    secure: false, // demo-local; set true behind HTTPS
    path: '/',
    maxAge: SESSION_TTL_DAYS * 24 * 60 * 60,
  });
  return res;
}
