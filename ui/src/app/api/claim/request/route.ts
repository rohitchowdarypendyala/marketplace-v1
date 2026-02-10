import { NextRequest } from 'next/server';
import { json, badRequest } from '../../../../lib/http';
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';

export const runtime = 'nodejs';

// Demo-only: writes to local JSONL file. NO DB writes.
export async function POST(req: NextRequest) {
  let body: any;
  try {
    body = await req.json();
  } catch {
    return badRequest('invalid JSON body');
  }

  const email = String(body?.email || '').trim();
  const platform = String(body?.platform || '').trim();
  const profile_url = String(body?.profile_url || '').trim();
  const note = String(body?.note || '').trim();

  if (!email || !email.includes('@')) return badRequest('email required');
  if (!platform) return badRequest('platform required');
  if (!profile_url || !profile_url.startsWith('http')) return badRequest('profile_url required');

  const ts = new Date().toISOString().replaceAll(':', '').replaceAll('-', '');
  const rand = crypto.randomBytes(3).toString('hex');
  const request_id = `${ts}-${rand}`;

  const record = {
    request_id,
    email,
    platform,
    profile_url,
    note,
    created_at: new Date().toISOString(),
  };

  const localDir = path.resolve(process.cwd(), '..', '.local');
  const filePath = path.join(localDir, 'claim_requests.jsonl');

  await fs.mkdir(localDir, { recursive: true });
  await fs.appendFile(filePath, JSON.stringify(record) + '\n', { encoding: 'utf8' });

  return json({ ok: true, request_id });
}
