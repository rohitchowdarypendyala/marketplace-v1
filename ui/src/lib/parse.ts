export function toInt(v: string | null, def: number | null = null): number | null {
  if (v == null || v === '') return def;
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) ? n : def;
}

export function toFloat(v: string | null, def: number | null = null): number | null {
  if (v == null || v === '') return def;
  const n = Number.parseFloat(v);
  return Number.isFinite(n) ? n : def;
}

export function toOrder(v: string | null): 'asc' | 'desc' {
  return (v || '').toLowerCase() === 'asc' ? 'asc' : 'desc';
}

export function toSort(v: string | null): 'trust' | 'followers' | 'avg_views' | 'pfw' | 'updated_at' {
  const s = (v || '').toLowerCase();
  if (s === 'followers' || s === 'avg_views' || s === 'pfw' || s === 'updated_at') return s;
  return 'trust';
}

export function clampInt(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

export function parseJsonArray(val: unknown): string[] {
  if (!val) return [];
  if (Array.isArray(val)) return val.map(String);
  if (typeof val !== 'string') return [];
  const s = val.trim();
  if (!s) return [];
  try {
    const parsed = JSON.parse(s);
    if (Array.isArray(parsed)) return parsed.map(String);
  } catch {
    // ignore
  }
  return [];
}
