import Link from 'next/link';
import { headers } from 'next/headers';

export const dynamic = 'force-dynamic';

type FeaturedItem = {
  creator: {
    id: number;
    primary_name: string;
    avg_trust: number | null;
    worst_trust: number | null;
    flags_summary: string[];
  };
  headline_profile: {
    id: number;
    platform: string;
    handle: string | null;
    profile_url: string;
    followers: number | null;
  } | null;
};

type FeaturedResponse = {
  items: FeaturedItem[];
  limit: number;
  offset: number;
  total: number;
};

function compact(n: number) {
  return Intl.NumberFormat('en-US', { notation: 'compact' }).format(n);
}

function platformLabel(p: string) {
  if (p === 'instagram') return 'Instagram';
  if (p === 'youtube') return 'YouTube';
  return p;
}

async function baseUrl() {
  const h = await headers();
  const host = h.get('x-forwarded-host') ?? h.get('host');
  const proto = h.get('x-forwarded-proto') ?? 'http';
  return `${proto}://${host}`;
}

export default async function HomePage() {
  const res = await fetch(`${await baseUrl()}/api/creators?sort=trust&order=desc&limit=6`, {
    cache: 'no-store',
  });

  let featured: FeaturedItem[] = [];
  if (res.ok) {
    const json = (await res.json()) as FeaturedResponse;
    featured = json.items || [];
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8">
      {/* Hero */}
      <section className="rounded-2xl border border-slate-200 bg-white p-8">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
          Find trusted creators, fast.
        </h1>
        <p className="mt-3 text-sm text-slate-600 sm:text-base">
          Compare influencers across Instagram and YouTube using transparent trust signals.
        </p>

        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
          <Link
            href="/search"
            className="inline-flex items-center justify-center rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800"
          >
            Search creators
          </Link>
          <Link href="/trust" className="text-sm font-medium text-slate-700 hover:text-slate-900">
            How Trust Score works
          </Link>
        </div>
      </section>

      {/* Featured creators */}
      <section className="mt-8">
        <div className="mb-3 flex items-end justify-between">
          <h2 className="text-sm font-semibold text-slate-900">Featured creators</h2>
          <Link href="/search" className="text-sm font-medium text-slate-700 hover:text-slate-900">
            Browse all
          </Link>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {featured.map((it) => {
            const c = it.creator;
            const hp = it.headline_profile;
            const trust = c.avg_trust == null ? '—' : Math.round(c.avg_trust);
            const worst = c.worst_trust == null ? '—' : Math.round(c.worst_trust);
            return (
              <div key={c.id} className="rounded-xl border border-slate-200 bg-white p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-base font-semibold text-slate-900">{c.primary_name}</div>
                    <div className="mt-1 text-xs text-slate-600">Worst platform score: {worst}</div>
                  </div>
                  <div className="shrink-0 rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold text-white">
                    {trust}/100
                  </div>
                </div>

                {hp ? (
                  <div className="mt-4 space-y-1 text-sm text-slate-700">
                    <div>
                      {platformLabel(hp.platform)} {hp.handle ? `@${hp.handle}` : ''}
                    </div>
                    {hp.followers != null ? (
                      <div className="text-sm font-medium text-slate-900">{compact(hp.followers)} followers</div>
                    ) : (
                      <div className="text-sm text-slate-500">Followers: —</div>
                    )}
                  </div>
                ) : (
                  <div className="mt-4 text-sm text-slate-500">No profile data.</div>
                )}

                <div className="mt-5">
                  <Link
                    href={`/creators/${c.id}`}
                    className="inline-flex w-full items-center justify-center rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-900 hover:bg-slate-50"
                  >
                    View profile
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Trust explainer strip */}
      <section className="mt-8 rounded-2xl border border-slate-200 bg-slate-50 p-5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm text-slate-700">
            Trust Score is based on engagement consistency, data quality, and platform signals — not follower count alone.
          </div>
          <Link href="/trust" className="text-sm font-medium text-slate-900 hover:underline">
            Learn more
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="mt-10 border-t border-slate-200 pt-6">
        <div className="flex flex-wrap gap-4 text-sm">
          <Link href="/search" className="font-medium text-slate-700 hover:text-slate-900">
            Search
          </Link>
          <Link href="/trust" className="font-medium text-slate-700 hover:text-slate-900">
            Trust Score
          </Link>
          <Link href="/claim" className="font-medium text-slate-700 hover:text-slate-900">
            Claim profile (demo)
          </Link>
        </div>
        <div className="mt-4 text-xs text-slate-500">
          All data is collected from public sources. This is a read-only demo (V1).
        </div>
      </footer>
    </main>
  );
}
