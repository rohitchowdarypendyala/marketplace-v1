import Link from 'next/link';
import type { CreatorListItem } from '../lib/types';

type Props = {
  item: CreatorListItem;
};

function compact(n: number) {
  return Intl.NumberFormat('en-US', { notation: 'compact' }).format(n);
}

function chip(text: string) {
  return (
    <span
      key={text}
      className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-700"
      title={text}
    >
      {text}
    </span>
  );
}

export default function CreatorCard({ item }: Props) {
  const c = item.creator;
  const hp = item.headline_profile;

  const avg = c.avg_trust == null ? '—' : Math.round(c.avg_trust);
  const worst = c.worst_trust == null ? '—' : Math.round(c.worst_trust);

  const flags = c.flags_summary || [];
  const showFlags = flags.slice(0, 3);
  const more = flags.length - showFlags.length;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-lg font-semibold text-slate-900">{c.primary_name}</div>
          <div className="mt-1 text-sm text-slate-600">
            Trust: <span className="font-semibold text-slate-900">{avg}/100</span>
            <span className="mx-2 text-slate-300">•</span>
            Worst: <span className="font-medium text-slate-800">{worst}</span>
          </div>
        </div>

        <Link
          href={`/creators/${c.id}`}
          className="inline-flex items-center justify-center rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
        >
          View profile
        </Link>
      </div>

      {/* flags */}
      {flags.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {showFlags.map((f) => chip(f))}
          {more > 0 ? chip(`+${more} more`) : null}
        </div>
      ) : null}

      {/* headline metrics */}
      {hp ? (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {hp.followers != null ? (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <div className="text-xs font-medium text-slate-600">Followers</div>
              <div className="mt-1 text-sm font-semibold text-slate-900">{compact(hp.followers)}</div>
            </div>
          ) : null}
          {hp.avg_views_last_10 != null ? (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <div className="text-xs font-medium text-slate-600">Avg views (last 10)</div>
              <div className="mt-1 text-sm font-semibold text-slate-900">{compact(hp.avg_views_last_10)}</div>
            </div>
          ) : null}
          {hp.posting_frequency_per_week != null ? (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <div className="text-xs font-medium text-slate-600">Posting / week</div>
              <div className="mt-1 text-sm font-semibold text-slate-900">{hp.posting_frequency_per_week.toFixed(2)}</div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
