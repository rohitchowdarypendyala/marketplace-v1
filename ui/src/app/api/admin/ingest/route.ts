import { NextRequest } from 'next/server';
import { badRequest, json } from '../../../../lib/http';
import { getUserFromRequest } from '../../../../lib/auth';
import { detectPlatform, normalizeProfileUrl } from '../../../../lib/platformDetect';
import { addAndIngest } from '../../../../lib/ingestWrite';
import { db } from '../../../../lib/db';

export const runtime = 'nodejs';

function nowIso() {
  return new Date().toISOString();
}

// POST /api/admin/ingest
// body: { url }
// Admin-only. For demo, runs ingestion inline within the request.
export async function POST(req: NextRequest) {
  const user = getUserFromRequest(req);
  if (!user || user.role !== 'admin') {
    return json({ ok: false, error: 'unauthorized' }, { status: 401 });
  }

  let body: any;
  try {
    body = await req.json();
  } catch {
    return badRequest('invalid JSON body');
  }

  const inputUrl = String(body?.url || '').trim();
  if (!inputUrl) return badRequest('url is required');

  const platform = detectPlatform(inputUrl);
  if (!platform) return badRequest('unsupported URL (only instagram.com / youtube.com supported)');

  const normalized = normalizeProfileUrl(platform, inputUrl);
  if (!normalized) return badRequest('unsupported profile URL format');

  const d = db();
  const ts = nowIso();

  // create job row
  d.prepare(
    `INSERT INTO ingest_jobs(
      requested_by_user_id, input_url, detected_platform, normalized_profile_url,
      status, error, created_at, updated_at, finished_at
    ) VALUES(?,?,?,?,?,?,?,?,?)`
  ).run(user.id, inputUrl, platform, normalized, 'queued', null, ts, ts, null);

  const jobRow = d.prepare(`SELECT last_insert_rowid() as id`).get() as any;
  const job_id = Number(jobRow.id);

  // run inline for demo
  try {
    d.prepare(`UPDATE ingest_jobs SET status='running', updated_at=? WHERE id=?`).run(nowIso(), job_id);

    const ids = await addAndIngest(platform, normalized);

    d.prepare(`UPDATE ingest_jobs SET status='success', updated_at=?, finished_at=? WHERE id=?`).run(
      nowIso(),
      nowIso(),
      job_id
    );

    return json({
      ok: true,
      job_id,
      detected_platform: platform,
      normalized_profile_url: normalized,
      creator_id: ids.creator_id,
      social_profile_id: ids.social_profile_id,
    });
  } catch (e: any) {
    d.prepare(`UPDATE ingest_jobs SET status='failed', error=?, updated_at=?, finished_at=? WHERE id=?`).run(
      String(e?.message || e),
      nowIso(),
      nowIso(),
      job_id
    );
    return json(
      { ok: false, job_id, error: String(e?.message || e) },
      { status: 500 }
    );
  }
}
