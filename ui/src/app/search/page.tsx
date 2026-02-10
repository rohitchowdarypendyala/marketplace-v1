import SearchClient from '../../components/SearchClient';

type SP = string | string[] | undefined;

function first(v: SP): string {
  if (!v) return '';
  return Array.isArray(v) ? v[0] ?? '' : v;
}

function many(v: SP): string[] {
  if (!v) return [];
  return Array.isArray(v) ? v.filter(Boolean) : v ? [v] : [];
}

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, SP>>;
}) {
  const sp = await searchParams;

  // Pass only as initial state; URL remains the source of truth in the client.
  const initial = {
    q: first(sp.q),
    platform: many(sp.platform),
    trust_min: first(sp.trust_min),
    trust_max: first(sp.trust_max),
    followers_min: first(sp.followers_min),
    followers_max: first(sp.followers_max),
    avg_views_min: first(sp.avg_views_min),
    avg_views_max: first(sp.avg_views_max),
    pfw_min: first(sp.pfw_min),
    data_confidence: many(sp.data_confidence),
    exclude_flag: many(sp.exclude_flag),
    sort: first(sp.sort),
    order: first(sp.order),
    limit: first(sp.limit),
    offset: first(sp.offset),
  };

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-6">
      <SearchClient initial={initial} />
    </main>
  );
}
