import { NextRequest } from 'next/server';
import { json, badRequest } from '../../../lib/http';
import { clampInt, toFloat, toInt, toOrder, toSort } from '../../../lib/parse';
import { listCreators } from '../../../lib/creatorsQuery';

export const runtime = 'nodejs';

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;

  const q = sp.get('q') || undefined;
  const platform = sp.getAll('platform').filter(Boolean);
  const data_confidence = sp.getAll('data_confidence').filter(Boolean);
  const exclude_flag = sp.getAll('exclude_flag').filter(Boolean);

  const trustMin = toFloat(sp.get('trust_min'));
  const trustMax = toFloat(sp.get('trust_max'));
  const followersMin = toInt(sp.get('followers_min'));
  const followersMax = toInt(sp.get('followers_max'));
  const avgViewsMin = toFloat(sp.get('avg_views_min'));
  const avgViewsMax = toFloat(sp.get('avg_views_max'));
  const pfwMin = toFloat(sp.get('pfw_min'));

  const sort = toSort(sp.get('sort'));
  const order = toOrder(sp.get('order'));

  const limit = clampInt(toInt(sp.get('limit'), 20) ?? 20, 1, 100);
  const offset = clampInt(toInt(sp.get('offset'), 0) ?? 0, 0, 1_000_000);

  // basic validation
  const allowedPlatforms = new Set(['instagram', 'youtube']);
  for (const p of platform) {
    if (!allowedPlatforms.has(p)) return badRequest(`invalid platform: ${p}`);
  }
  const allowedConfidence = new Set(['low', 'medium', 'high']);
  for (const dc of data_confidence) {
    if (!allowedConfidence.has(dc)) return badRequest(`invalid data_confidence: ${dc}`);
  }

  const { total, items } = listCreators({
    q,
    platform,
    trustMin,
    trustMax,
    followersMin,
    followersMax,
    avgViewsMin,
    avgViewsMax,
    pfwMin,
    dataConfidence: data_confidence,
    excludeFlag: exclude_flag,
    sort,
    order,
    limit,
    offset,
  });

  return json({ items, limit, offset, total });
}
