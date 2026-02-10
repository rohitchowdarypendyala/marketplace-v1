'use client';

export type SearchFilterState = {
  platform: string[];
  trust_min: string;
  trust_max: string;
  followers_min: string;
  avg_views_min: string;
  pfw_min: string;
  data_confidence: string[];
  exclude_flag: string[];
};

type Props = {
  value: SearchFilterState;
  onChange: (partial: Partial<SearchFilterState>) => void;
};

const EXCLUDE_FLAGS = [
  'blocked_or_challenge',
  'missing_engagement_metrics',
  'likes_hidden',
  'comments_disabled_or_limited',
  'views_dom_outlier',
  'engagement_metric_suspicious_filtered',
] as const;

function toggle(list: string[], v: string) {
  const s = new Set(list);
  if (s.has(v)) s.delete(v);
  else s.add(v);
  return Array.from(s);
}

function Checkbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: () => void }) {
  return (
    <label className="flex items-center gap-2 text-sm text-slate-700">
      <input type="checkbox" checked={checked} onChange={onChange} className="h-4 w-4" />
      {label}
    </label>
  );
}

export default function SearchFilters({ value, onChange }: Props) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="text-sm font-semibold text-slate-900">Filters</div>

      <div className="mt-4 space-y-4">
        {/* platform */}
        <div>
          <div className="text-xs font-medium text-slate-600">Platform</div>
          <div className="mt-2 space-y-1">
            <Checkbox
              label="Instagram"
              checked={value.platform.includes('instagram')}
              onChange={() => onChange({ platform: toggle(value.platform, 'instagram') })}
            />
            <Checkbox
              label="YouTube"
              checked={value.platform.includes('youtube')}
              onChange={() => onChange({ platform: toggle(value.platform, 'youtube') })}
            />
          </div>
        </div>

        {/* trust */}
        <div>
          <div className="text-xs font-medium text-slate-600">Trust score (0–100)</div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <input
              value={value.trust_min}
              onChange={(e) => onChange({ trust_min: e.target.value })}
              placeholder="min"
              inputMode="numeric"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            <input
              value={value.trust_max}
              onChange={(e) => onChange({ trust_max: e.target.value })}
              placeholder="max"
              inputMode="numeric"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
          </div>
        </div>

        {/* followers */}
        <div>
          <div className="text-xs font-medium text-slate-600">Followers (min)</div>
          <input
            value={value.followers_min}
            onChange={(e) => onChange({ followers_min: e.target.value })}
            placeholder="e.g., 100000"
            inputMode="numeric"
            className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          />
        </div>

        {/* avg views */}
        <div>
          <div className="text-xs font-medium text-slate-600">Avg views last 10 (min)</div>
          <input
            value={value.avg_views_min}
            onChange={(e) => onChange({ avg_views_min: e.target.value })}
            placeholder="e.g., 50000"
            inputMode="numeric"
            className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          />
        </div>

        {/* posting frequency */}
        <div>
          <div className="text-xs font-medium text-slate-600">Posting / week (min)</div>
          <input
            value={value.pfw_min}
            onChange={(e) => onChange({ pfw_min: e.target.value })}
            placeholder="e.g., 1"
            inputMode="decimal"
            className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          />
        </div>

        {/* data confidence */}
        <div>
          <div className="text-xs font-medium text-slate-600">Data confidence</div>
          <div className="mt-2 space-y-1">
            <Checkbox
              label="High"
              checked={value.data_confidence.includes('high')}
              onChange={() => onChange({ data_confidence: toggle(value.data_confidence, 'high') })}
            />
            <Checkbox
              label="Medium"
              checked={value.data_confidence.includes('medium')}
              onChange={() => onChange({ data_confidence: toggle(value.data_confidence, 'medium') })}
            />
            <Checkbox
              label="Low"
              checked={value.data_confidence.includes('low')}
              onChange={() => onChange({ data_confidence: toggle(value.data_confidence, 'low') })}
            />
          </div>
        </div>

        {/* exclude flags */}
        <div>
          <div className="text-xs font-medium text-slate-600">Exclude flags</div>
          <div className="mt-2 space-y-1">
            {EXCLUDE_FLAGS.map((f) => (
              <Checkbox
                key={f}
                label={f}
                checked={value.exclude_flag.includes(f)}
                onChange={() => onChange({ exclude_flag: toggle(value.exclude_flag, f) })}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
