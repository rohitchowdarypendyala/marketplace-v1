import { NextRequest } from 'next/server';
import { json } from '../../../lib/http';
import { TRUST_FLAGS } from '../../../lib/trustFlags';

export const runtime = 'nodejs';

export async function GET(_req: NextRequest) {
  return json({ flags: TRUST_FLAGS });
}
