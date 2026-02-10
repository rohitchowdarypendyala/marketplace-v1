import { NextRequest } from 'next/server';
import { json } from '../../../../lib/http';
import { deleteSessionByToken } from '../../../../lib/auth';

export const runtime = 'nodejs';

// POST /api/auth/logout
export async function POST(req: NextRequest) {
  const token = req.cookies.get('mp_session')?.value;
  if (token) {
    // nice-to-have: remove session row
    try {
      deleteSessionByToken(token);
    } catch {
      // ignore
    }
  }

  const res = json({ ok: true });
  res.cookies.set({ name: 'mp_session', value: '', path: '/', maxAge: 0 });
  return res;
}
