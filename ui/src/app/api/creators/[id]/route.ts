import { NextRequest } from 'next/server';
import { json, badRequest } from '../../../../lib/http';
import { db } from '../../../../lib/db';
import { parseJsonArray } from '../../../../lib/parse';

export const runtime = 'nodejs';

export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const creatorId = Number.parseInt(id, 10);
  if (!Number.isFinite(creatorId)) return badRequest('invalid creator id');

  const d = db();
  const creator = d
    .prepare(
      `SELECT id, primary_name
       FROM creators
       WHERE id = ?`
    )
    .get(creatorId) as any;

  if (!creator) {
    return json({ ok: false, error: 'not_found' }, { status: 404 });
  }

  const profiles = d
    .prepare(
      `SELECT
         id, creator_id, platform, profile_url, handle, display_name, bio,
         followers, following, posts, total_views,
         avg_views_last_10, avg_likes_last_10, avg_comments_last_10,
         posting_frequency_per_week, posting_frequency_per_week_90d,
         stats_status, data_confidence,
         trust_score, trust_flags,
         contact_emails_json, primary_website, contact_website, external_website,
         external_links_json,
         updated_at, last_fetched_at
       FROM social_profiles
       WHERE creator_id = ?
       ORDER BY (platform='instagram') DESC, (followers IS NULL) ASC, followers DESC`
    )
    .all(creatorId) as any[];

  // contact object: emails from first non-empty contact_emails_json across profiles
  let emails: string[] = [];
  for (const p of profiles) {
    const arr = parseJsonArray(p.contact_emails_json);
    if (arr.length) {
      emails = arr;
      break;
    }
  }

  // website: first non-empty primary_website -> contact_website -> external_website across profiles
  let website: string | null = null;
  for (const p of profiles) {
    const w = p.primary_website || p.contact_website || p.external_website;
    if (w && String(w).trim()) {
      website = String(w).trim();
      break;
    }
  }

  const trustScores = profiles
    .map((p) => (p.trust_score == null ? null : Number(p.trust_score)))
    .filter((x) => typeof x === 'number' && Number.isFinite(x)) as number[];

  const avg_trust = trustScores.length ? trustScores.reduce((a, b) => a + b, 0) / trustScores.length : null;
  const worst_trust = trustScores.length ? Math.min(...trustScores) : null;

  // flags_summary: union of all profile trust_flags
  const flagsSet = new Set<string>();
  for (const p of profiles) {
    for (const f of parseJsonArray(p.trust_flags)) flagsSet.add(f);
  }

  const out = {
    creator: {
      id: creator.id,
      primary_name: creator.primary_name,
      avg_trust,
      worst_trust,
      flags_summary: Array.from(flagsSet),
    },
    profiles: profiles.map((p) => ({
      ...p,
      trust_reason: null,
      trust_flags: parseJsonArray(p.trust_flags),
      contact_emails: parseJsonArray(p.contact_emails_json),
    })),
    contact: {
      emails,
      website,
    },
  };

  return json(out);
}
