import { NextRequest, NextResponse } from 'next/server';
import { badRequest, json } from '../../../../lib/http';
import { createOtpCode, rateLimitOtpOrThrow, storeOtp } from '../../../../lib/auth';

export const runtime = 'nodejs';

// POST /api/auth/start
// body: { email, role }
// DEMO ONLY: OTP is printed to server logs.
export async function POST(req: NextRequest) {
  let body: any;
  try {
    body = await req.json();
  } catch {
    return badRequest('invalid JSON body');
  }

  const email = String(body?.email || '').trim().toLowerCase();
  const roleRaw = String(body?.role || 'business').trim().toLowerCase();
  const role = roleRaw === 'influencer' ? 'influencer' : 'business';

  if (!email || !email.includes('@')) {
    return badRequest('email is required');
  }

  try {
    rateLimitOtpOrThrow(email);
  } catch (e: any) {
    return badRequest(String(e?.message || e));
  }

  const code = createOtpCode();
  storeOtp(email, code);

  // DEMO ONLY: print OTP to logs
  console.log(`[DEMO OTP] email=${email} role=${role} code=${code}`);

  return json({ ok: true });
}
