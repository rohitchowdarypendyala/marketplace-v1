import { NextRequest } from 'next/server';
import { json } from '../../../lib/http';
import { getUserFromRequest } from '../../../lib/auth';

export const runtime = 'nodejs';

// GET /api/me
export async function GET(req: NextRequest) {
  const user = getUserFromRequest(req);
  if (!user) return json({ ok: false, user: null });
  return json({ ok: true, user });
}
