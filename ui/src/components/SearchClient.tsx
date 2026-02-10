'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import CreatorCard from './CreatorCard';
import SearchFilters, { type SearchFilterState } from './SearchFilters';
import SearchSort, { type SearchSortState } from './SearchSort';
import Pagination from './Pagination';
import type { CreatorListResponse } from '../lib/types';

type Props = {
  initial: Record<string, string | string[]>;
};

const DEFAULTS = {
  sort: 'trust',
  order: 'desc',
  limit: '20',
  offset: '0',
} as const;

function compact(n: number) {
  return Intl.NumberFormat('en-US', { notation: 'compact' }).format(n);
}

function normalize(sp: URLSearchParams) {
  const out = new URLSearchParams(sp);
  if (!out.get('sort')) out.set('sort', DEFAULTS.sort);
  if (!out.get('order')) out.set('order', DEFAULTS.order);
  if (!out.get('limit')) out.set('limit', DEFAULTS.limit);
  if (!out.get('offset')) out.set('offset', DEFAULTS.offset);
  return out;
}

function getMany(sp: URLSearchParams, key: string) {
  return sp.getAll(key).filter(Boolean);
}

function setMany(sp: URLSearchParams, key: string, values: string[]) {
  sp.delete(key);
  for (const v of values) {
    if (v) sp.append(key, v);
  }
}

function setOrDelete(sp: URLSearchParams, key: string, value: string) {
  if (!value) sp.delete(key);
  else sp.set(key, value);
}

export default function SearchClient({ initial }: Props) {
  const router = useRouter();
  const sp = useSearchParams();

  // Local controlled input for q (debounced URL push)
  const [qInput, setQInput] = useState(typeof initial.q === 'string' ? initial.q : '');
  const qDebounceRef = useRef<number | null>(null);

  const [filtersOpen, setFiltersOpen] = useState(false);

  // Derived state from URL (source of truth)
  const urlState = useMemo(() => {
    const n = normalize(new URLSearchParams(sp.toString()));
    return {
      q: n.get('q') || '',
      platform: getMany(n, 'platform'),
      trust_min: n.get('trust_min') || '',
      trust_max: n.get('trust_max') || '',
      followers_min: n.get('followers_min') || '',
      avg_views_min: n.get('avg_views_min') || '',
      pfw_min: n.get('pfw_min') || '',
      data_confidence: getMany(n, 'data_confidence'),
      exclude_flag: getMany(n, 'exclude_flag'),
      sort: (n.get('sort') || DEFAULTS.sort) as SearchSortState['sort'],
      order: (n.get('order') || DEFAULTS.order) as SearchSortState['order'],
      limit: n.get('limit') || DEFAULTS.limit,
      offset: n.get('offset') || DEFAULTS.offset,
    };
  }, [sp]);

  // keep qInput in sync when navigation happens externally (back/forward)
  useEffect(() => {
    setQInput(urlState.q);
  }, [urlState.q]);

  const [data, setData] = useState<CreatorListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const qs = useMemo(() => normalize(new URLSearchParams(sp.toString())).toString(), [sp]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);

    fetch(`/api/creators?${qs}`, { cache: 'no-store' })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return (await res.json()) as CreatorListResponse;
      })
      .then((json) => {
        if (!alive) return;
        setData(json);
        setLoading(false);
      })
      .catch((e) => {
        if (!alive) return;
        setError(String(e?.message || e));
        setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [qs]);

  function pushParams(next: URLSearchParams) {
    const normalized = normalize(next);
    router.push(`/search?${normalized.toString()}`);
  }

  function resetOffset(next: URLSearchParams) {
    next.set('offset', '0');
  }

  function onQChange(v: string) {
    setQInput(v);
    if (qDebounceRef.current) window.clearTimeout(qDebounceRef.current);
    qDebounceRef.current = window.setTimeout(() => {
      const next = normalize(new URLSearchParams(sp.toString()));
      setOrDelete(next, 'q', v.trim());
      resetOffset(next);
      pushParams(next);
    }, 300);
  }

  function onFiltersChange(partial: Partial<SearchFilterState>) {
    const next = normalize(new URLSearchParams(sp.toString()));

    if (partial.platform) {
      setMany(next, 'platform', partial.platform);
    }
    if (partial.data_confidence) {
      setMany(next, 'data_confidence', partial.data_confidence);
    }
    if (partial.exclude_flag) {
      setMany(next, 'exclude_flag', partial.exclude_flag);
    }

    if (partial.trust_min !== undefined) setOrDelete(next, 'trust_min', partial.trust_min);
    if (partial.trust_max !== undefined) setOrDelete(next, 'trust_max', partial.trust_max);
    if (partial.followers_min !== undefined) setOrDelete(next, 'followers_min', partial.followers_min);
    if (partial.avg_views_min !== undefined) setOrDelete(next, 'avg_views_min', partial.avg_views_min);
    if (partial.pfw_min !== undefined) setOrDelete(next, 'pfw_min', partial.pfw_min);

    resetOffset(next);
    pushParams(next);
  }

  function onSortChange(s: Partial<SearchSortState>) {
    const next = normalize(new URLSearchParams(sp.toString()));
    if (s.sort) next.set('sort', s.sort);
    if (s.order) next.set('order', s.order);
    resetOffset(next);
    pushParams(next);
  }

  function onPageChange(nextOffset: number) {
    const next = normalize(new URLSearchParams(sp.toString()));
    next.set('offset', String(Math.max(0, nextOffset)));
    pushParams(next);
  }

  const total = data?.total ?? 0;
  const limit = data?.limit ?? (Number.parseInt(urlState.limit || DEFAULTS.limit, 10) || 20);
  const offset = data?.offset ?? (Number.parseInt(urlState.offset || DEFAULTS.offset, 10) || 0);

  return (
    <div className="space-y-4">
      {/* Search bar */}
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex-1">
            <div className="text-sm font-semibold text-slate-900">Search creators</div>
            <input
              value={qInput}
              onChange={(e) => onQChange(e.target.value)}
              placeholder="Search by name or handle"
              className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-slate-400"
            />
          </div>

          <div className="flex items-center gap-2">
            <button
              className="inline-flex items-center rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-900 hover:bg-slate-50 sm:hidden"
              onClick={() => setFiltersOpen((v) => !v)}
            >
              {filtersOpen ? 'Hide filters' : 'Show filters'}
            </button>
            <SearchSort value={{ sort: urlState.sort, order: urlState.order }} onChange={onSortChange} />
          </div>
        </div>

        <div className="mt-2 text-xs text-slate-500">{loading ? 'Loading…' : `${compact(total)} results`}</div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[320px_1fr]">
        {/* Filters (desktop) */}
        <div className={`${filtersOpen ? 'block' : 'hidden'} lg:block`}>
          <SearchFilters
            value={{
              platform: urlState.platform,
              trust_min: urlState.trust_min,
              trust_max: urlState.trust_max,
              followers_min: urlState.followers_min,
              avg_views_min: urlState.avg_views_min,
              pfw_min: urlState.pfw_min,
              data_confidence: urlState.data_confidence,
              exclude_flag: urlState.exclude_flag,
            }}
            onChange={onFiltersChange}
          />
        </div>

        {/* Results */}
        <div className="space-y-3">
          {error ? (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
              Failed to load results: {error}
            </div>
          ) : null}

          {loading && !data ? (
            <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">Loading…</div>
          ) : null}

          {!loading && data && data.items.length === 0 ? (
            <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
              No creators match your filters.
            </div>
          ) : null}

          {data?.items?.map((item) => (
            <CreatorCard key={item.creator.id} item={item} />
          ))}

          <Pagination total={total} limit={limit} offset={offset} onChange={onPageChange} />
        </div>
      </div>
    </div>
  );
}
