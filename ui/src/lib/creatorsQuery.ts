import { db } from './db';

export type CreatorsQueryParams = {
  q?: string;
  platform?: string[]; // repeat
  trustMin?: number | null;
  trustMax?: number | null;
  followersMin?: number | null;
  followersMax?: number | null;
  avgViewsMin?: number | null;
  avgViewsMax?: number | null;
  pfwMin?: number | null;
  dataConfidence?: string[]; // repeat
  excludeFlag?: string[]; // repeat
  sort: 'trust' | 'followers' | 'avg_views' | 'pfw' | 'updated_at';
  order: 'asc' | 'desc';
  limit: number;
  offset: number;
};

function likePattern(s: string) {
  // SQLite LIKE; escape % and _
  return `%${s.replaceAll('%', '\\%').replaceAll('_', '\\_')}%`;
}

function buildWhere(p: CreatorsQueryParams) {
  const where: string[] = [];
  const args: any[] = [];

  // q match: creators.primary_name OR any social_profiles.handle
  if (p.q && p.q.trim()) {
    const pat = likePattern(p.q.trim().toLowerCase());
    where.push(
      `(
        lower(c.primary_name) LIKE ? ESCAPE "\\" OR
        EXISTS (
          SELECT 1 FROM social_profiles spq
          WHERE spq.creator_id=c.id
            AND lower(coalesce(spq.handle, '')) LIKE ? ESCAPE "\\"
        )
      )`
    );
    args.push(pat, pat);
  }

  // trust range filters computed from social_profiles.trust_score
  if (p.trustMin != null) {
    where.push(
      `(SELECT avg(sp.trust_score) FROM social_profiles sp WHERE sp.creator_id=c.id AND sp.trust_score IS NOT NULL) >= ?`
    );
    args.push(p.trustMin);
  }
  if (p.trustMax != null) {
    where.push(
      `(SELECT avg(sp.trust_score) FROM social_profiles sp WHERE sp.creator_id=c.id AND sp.trust_score IS NOT NULL) <= ?`
    );
    args.push(p.trustMax);
  }

  // exclude_flag: exclude creators where ANY social profile trust_flags contains flag
  for (const f of p.excludeFlag || []) {
    if (!f) continue;
    where.push(
      `NOT EXISTS (
        SELECT 1 FROM social_profiles spe
        WHERE spe.creator_id=c.id
          AND spe.trust_flags IS NOT NULL
          AND spe.trust_flags LIKE ?
      )`
    );
    args.push(`%"${f}"%`);
  }

  // social_profiles-based filters via EXISTS
  const spWhere: string[] = ['sp.creator_id = c.id'];
  const spArgs: any[] = [];

  if (p.platform && p.platform.length) {
    spWhere.push(`sp.platform IN (${p.platform.map(() => '?').join(',')})`);
    spArgs.push(...p.platform);
  }
  if (p.dataConfidence && p.dataConfidence.length) {
    spWhere.push(`sp.data_confidence IN (${p.dataConfidence.map(() => '?').join(',')})`);
    spArgs.push(...p.dataConfidence);
  }
  if (p.followersMin != null) {
    spWhere.push('sp.followers >= ?');
    spArgs.push(p.followersMin);
  }
  if (p.followersMax != null) {
    spWhere.push('sp.followers <= ?');
    spArgs.push(p.followersMax);
  }
  if (p.avgViewsMin != null) {
    spWhere.push('sp.avg_views_last_10 >= ?');
    spArgs.push(p.avgViewsMin);
  }
  if (p.avgViewsMax != null) {
    spWhere.push('sp.avg_views_last_10 <= ?');
    spArgs.push(p.avgViewsMax);
  }
  if (p.pfwMin != null) {
    spWhere.push('sp.posting_frequency_per_week >= ?');
    spArgs.push(p.pfwMin);
  }

  if (spWhere.length > 1) {
    where.push(`EXISTS (SELECT 1 FROM social_profiles sp WHERE ${spWhere.join(' AND ')})`);
    args.push(...spArgs);
  }

  return { whereSql: where.length ? `WHERE ${where.join(' AND ')}` : '', args };
}

function orderBySql(sort: CreatorsQueryParams['sort'], order: CreatorsQueryParams['order']) {
  const dir = order.toUpperCase() === 'ASC' ? 'ASC' : 'DESC';

  if (sort === 'followers') {
    return `ORDER BY (
      SELECT coalesce(sp.followers, -1)
      FROM social_profiles sp
      WHERE sp.creator_id=c.id
      ORDER BY (sp.platform='instagram') DESC, (sp.followers IS NULL) ASC, sp.followers DESC
      LIMIT 1
    ) ${dir}`;
  }

  if (sort === 'avg_views') {
    return `ORDER BY (
      SELECT coalesce(sp.avg_views_last_10, -1)
      FROM social_profiles sp
      WHERE sp.creator_id=c.id
      ORDER BY (sp.platform='instagram') DESC, (sp.avg_views_last_10 IS NULL) ASC, sp.avg_views_last_10 DESC
      LIMIT 1
    ) ${dir}`;
  }

  if (sort === 'pfw') {
    return `ORDER BY (
      SELECT coalesce(sp.posting_frequency_per_week, -1)
      FROM social_profiles sp
      WHERE sp.creator_id=c.id
      ORDER BY (sp.platform='instagram') DESC, (sp.posting_frequency_per_week IS NULL) ASC, sp.posting_frequency_per_week DESC
      LIMIT 1
    ) ${dir}`;
  }

  if (sort === 'updated_at') {
    return `ORDER BY (
      SELECT coalesce(sp.updated_at, '')
      FROM social_profiles sp
      WHERE sp.creator_id=c.id
      ORDER BY (sp.updated_at IS NULL) ASC, sp.updated_at DESC
      LIMIT 1
    ) ${dir}`;
  }

  // trust default: avg trust score across profiles
  return `ORDER BY (
    SELECT coalesce(avg(sp.trust_score), -1)
    FROM social_profiles sp
    WHERE sp.creator_id=c.id AND sp.trust_score IS NOT NULL
  ) ${dir}`;
}

function safeParseFlags(s: any) {
  if (!s || typeof s !== 'string') return [];
  try {
    const parsed = JSON.parse(s);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function listCreators(p: CreatorsQueryParams) {
  const d = db();
  const { whereSql, args } = buildWhere(p);

  // Phase A1: total
  const totalRow = d.prepare(`SELECT count(*) as cnt FROM creators c ${whereSql}`).get(...args) as any;
  const total = Number(totalRow?.cnt || 0);

  // Phase A2: page of creator IDs
  const orderBy = orderBySql(p.sort, p.order);
  const idsRows = d
    .prepare(`SELECT c.id FROM creators c ${whereSql} ${orderBy} LIMIT ? OFFSET ?`)
    .all(...args, p.limit, p.offset) as any[];
  const ids = idsRows.map((r) => Number(r.id)).filter((n) => Number.isFinite(n));

  if (!ids.length) return { total, items: [] as any[] };

  // Phase B: creators + computed avg/worst + headline profile
  const placeholders = ids.map(() => '?').join(',');
  const orderCase = `CASE c.id ${ids.map((id, i) => `WHEN ${id} THEN ${i}`).join(' ')} END`;

  const sql = `
    SELECT
      c.id as creator_id,
      c.primary_name,

      (SELECT avg(sp.trust_score) FROM social_profiles sp WHERE sp.creator_id=c.id AND sp.trust_score IS NOT NULL) as avg_trust,
      (SELECT min(sp.trust_score) FROM social_profiles sp WHERE sp.creator_id=c.id AND sp.trust_score IS NOT NULL) as worst_trust,

      hp.id as hp_id,
      hp.platform as hp_platform,
      hp.handle as hp_handle,
      hp.profile_url as hp_profile_url,
      hp.followers as hp_followers,
      hp.avg_views_last_10 as hp_avg_views_last_10,
      hp.avg_likes_last_10 as hp_avg_likes_last_10,
      hp.avg_comments_last_10 as hp_avg_comments_last_10,
      hp.posting_frequency_per_week as hp_posting_frequency_per_week,
      hp.stats_status as hp_stats_status,
      hp.data_confidence as hp_data_confidence,
      hp.trust_score as hp_trust_score,
      hp.trust_flags as hp_trust_flags
    FROM creators c
    LEFT JOIN social_profiles hp
      ON hp.id = (
        SELECT sp.id
        FROM social_profiles sp
        WHERE sp.creator_id = c.id
        ORDER BY (sp.platform='instagram') DESC, (sp.followers IS NULL) ASC, sp.followers DESC
        LIMIT 1
      )
    WHERE c.id IN (${placeholders})
    ORDER BY ${orderCase} ASC
  `;

  const rows = d.prepare(sql).all(...ids) as any[];

  const items = rows.map((r) => {
    // creator flags summary: union of headline trust_flags (best-effort)
    const flags_summary = safeParseFlags(r.hp_trust_flags);

    return {
      creator: {
        id: r.creator_id,
        primary_name: r.primary_name,
        avg_trust: r.avg_trust,
        worst_trust: r.worst_trust,
        flags_summary,
      },
      headline_profile: r.hp_id
        ? {
            id: r.hp_id,
            platform: r.hp_platform,
            handle: r.hp_handle,
            profile_url: r.hp_profile_url,
            followers: r.hp_followers,
            avg_views_last_10: r.hp_avg_views_last_10,
            avg_likes_last_10: r.hp_avg_likes_last_10,
            avg_comments_last_10: r.hp_avg_comments_last_10,
            posting_frequency_per_week: r.hp_posting_frequency_per_week,
            stats_status: r.hp_stats_status,
            data_confidence: r.hp_data_confidence,
            trust_score: r.hp_trust_score,
            trust_reason: null,
          }
        : null,
    };
  });

  return { total, items };
}
