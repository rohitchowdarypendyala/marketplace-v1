import { NextRequest } from 'next/server';
import { json, badRequest } from '../../../../../lib/http';
import { getUserFromRequest } from '../../../../../lib/auth';
import { db } from '../../../../../lib/db';

export const runtime = 'nodejs';

// GET /api/admin/ingest/jobs?status=queued|running|success|failed
export async function GET(req: NextRequest) {
  const user = getUserFromRequest(req);
  if (!user || user.role !== 'admin') {
    return json({ ok: false, error: 'unauthorized' }, { status: 401 });
  }

  const status = (req.nextUrl.searchParams.get('status') || '').trim();
  const allowed = new Set(['queued', 'running', 'success', 'failed']);
  if (status && !allowed.has(status)) {
    return badRequest('invalid status');
  }

  const d = db();
  const rows = status
    ? (d
        .prepare(
          `SELECT id, requested_by_user_id, input_url, detected_platform, normalized_profile_url,
                  status, error, created_at, updated_at, finished_at
           FROM ingest_jobs
           WHERE status = ?
           ORDER BY id DESC
           LIMIT 50`
        )
        .all(status) as any[])
    : (d
        .prepare(
          `SELECT id, requested_by_user_id, input_url, detected_platform, normalized_profile_url,
                  status, error, created_at, updated_at, finished_at
           FROM ingest_jobs
           ORDER BY id DESC
           LIMIT 50`
        )
        .all() as any[]);

  return json({ ok: true, items: rows });
}
