'use client';

export type SearchSortState = {
  sort: 'trust' | 'followers' | 'avg_views' | 'pfw' | 'updated_at';
  order: 'asc' | 'desc';
};

type Props = {
  value: SearchSortState;
  onChange: (partial: Partial<SearchSortState>) => void;
};

export default function SearchSort({ value, onChange }: Props) {
  return (
    <div className="flex items-center gap-2">
      <select
        value={value.sort}
        onChange={(e) => onChange({ sort: e.target.value as SearchSortState['sort'] })}
        className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
      >
        <option value="trust">Trust</option>
        <option value="followers">Followers</option>
        <option value="avg_views">Avg views</option>
        <option value="pfw">Posting frequency</option>
        <option value="updated_at">Updated</option>
      </select>

      <button
        type="button"
        onClick={() => onChange({ order: value.order === 'desc' ? 'asc' : 'desc' })}
        className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-900 hover:bg-slate-50"
        title="Toggle order"
      >
        {value.order === 'desc' ? 'Desc' : 'Asc'}
      </button>
    </div>
  );
}
