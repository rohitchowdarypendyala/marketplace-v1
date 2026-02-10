import FlagsChips from './FlagsChips';
import type { SocialProfileRow, TrustFlagDef } from '../lib/types';

type Props = {
  profile: SocialProfileRow;
  trustFlagDefs: TrustFlagDef[];
};

function platformLabel(platform: string) {
  if (platform === 'instagram') return 'Instagram';
  if (platform === 'youtube') return 'YouTube';
  return platform;
}

function fmtNum(n: number | null) {
  if (n == null) return null;
  return Intl.NumberFormat('en-US', { notation: 'compact' }).format(n);
}

function Metric({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div className="text-xs font-medium text-slate-600">{label}</div>
      <div className="mt-1 text-sm font-semibold text-slate-900">{value}</div>
    </div>
  );
}

export default function PlatformCard({ profile, trustFlagDefs }: Props) {
  const handle = profile.handle || profile.display_name || '';

  const metrics = [
    { label: 'Followers', value: fmtNum(profile.followers) },
    { label: 'Avg views (last 10)', value: fmtNum(profile.avg_views_last_10) },
    { label: 'Avg likes (last 10)', value: fmtNum(profile.avg_likes_last_10) },
    { label: 'Avg comments (last 10)', value: fmtNum(profile.avg_comments_last_10) },
    {
      label: 'Posting freq / week (30d)',
      value: profile.posting_frequency_per_week == null ? null : profile.posting_frequency_per_week.toFixed(2),
    },
    {
      label: 'Posting freq / week (90d)',
      value: profile.posting_frequency_per_week_90d == null ? null : profile.posting_frequency_per_week_90d.toFixed(2),
    },
  ];

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-sm font-semibold text-slate-900">{platformLabel(profile.platform)}</div>
          <div className="mt-1 text-sm text-slate-700">{handle ? `@${handle}` : ''}</div>
        </div>

        <a
          href={profile.profile_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-900 hover:bg-slate-50"
        >
          Open profile
        </a>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {metrics.map((m) => (
          <Metric key={m.label} label={m.label} value={m.value} />
        ))}
      </div>

      <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
        <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
          <div>
            <span className="text-slate-500">stats_status:</span> {profile.stats_status || '—'}
          </div>
          <div>
            <span className="text-slate-500">data_confidence:</span> {profile.data_confidence || '—'}
          </div>
          <div>
            <span className="text-slate-500">updated_at:</span> {profile.updated_at || '—'}
          </div>
          <div>
            <span className="text-slate-500">last_fetched_at:</span> {profile.last_fetched_at || '—'}
          </div>
        </div>
      </div>

      <div className="mt-4">
        <FlagsChips title="Flags" flags={profile.trust_flags || []} defs={trustFlagDefs} />
      </div>
    </div>
  );
}
