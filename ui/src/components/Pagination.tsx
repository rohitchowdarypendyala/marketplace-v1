'use client';

type Props = {
  total: number;
  limit: number;
  offset: number;
  onChange: (nextOffset: number) => void;
};

export default function Pagination({ total, limit, offset, onChange }: Props) {
  if (!total || total <= limit) return null;

  const prevOffset = Math.max(0, offset - limit);
  const nextOffset = offset + limit;
  const hasPrev = offset > 0;
  const hasNext = nextOffset < total;

  return (
    <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4">
      <button
        disabled={!hasPrev}
        onClick={() => onChange(prevOffset)}
        className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-900 hover:bg-slate-50 disabled:opacity-40"
      >
        Prev
      </button>

      <div className="text-sm text-slate-600">
        Showing {Math.min(total, offset + 1)}–{Math.min(total, offset + limit)} of {total}
      </div>

      <button
        disabled={!hasNext}
        onClick={() => onChange(nextOffset)}
        className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-900 hover:bg-slate-50 disabled:opacity-40"
      >
        Next
      </button>
    </div>
  );
}
