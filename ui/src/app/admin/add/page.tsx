'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import RequireRole from '../../../components/RequireRole';

type Job = {
  id: number;
  input_url: string;
  detected_platform: string;
  normalized_profile_url: string;
  status: string;
  error: string | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
};

export default function AdminAddPage() {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [jobs, setJobs] = useState<Job[]>([]);

  async function loadJobs() {
    try {
      const res = await fetch('/api/admin/ingest/jobs', { cache: 'no-store' });
      const json = await res.json();
      if (res.ok && json.ok) setJobs(json.items || []);
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    loadJobs();
  }, []);

  async function onAdd() {
    setError(null);
    setResult(null);
    const u = url.trim();
    if (!u) {
      setError('URL is required');
      return;
    }

    setLoading(true);
    try {
      const res = await fetch('/api/admin/ingest', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ url: u }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json?.error || json?.message || `HTTP ${res.status}`);
      setResult(json);
      await loadJobs();
    } catch (e: any) {
      setError(String(e?.message || e));
      await loadJobs();
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-4xl space-y-4 px-4 py-6">
      <RequireRole role="admin">
        <div className="rounded-2xl border border-slate-200 bg-white p-6">
          <h1 className="text-2xl font-semibold text-slate-900">Admin: Add & Ingest</h1>
          <p className="mt-2 text-sm text-slate-600">Paste an Instagram or YouTube profile URL, then ingest stats.</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6">
          {error ? (
            <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>
          ) : null}

          <label className="text-xs font-medium text-slate-600">Profile URL</label>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.instagram.com/handle/ or https://www.youtube.com/@handle"
            className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-slate-400"
          />

          <button
            onClick={onAdd}
            disabled={loading}
            className="mt-4 inline-flex items-center rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
          >
            {loading ? 'Adding & ingesting…' : 'Add & Ingest'}
          </button>

          {result?.ok ? (
            <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-950">
              <div className="font-semibold">Success</div>
              <div className="mt-1">creator_id: {result.creator_id}</div>
              <div>social_profile_id: {result.social_profile_id}</div>
              <div className="mt-2">
                <Link href={`/creators/${result.creator_id}`} className="font-medium hover:underline">
                  View creator profile
                </Link>
              </div>
            </div>
          ) : null}
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6">
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold text-slate-900">Recent ingest jobs</div>
            <button
              onClick={loadJobs}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-900 hover:bg-slate-50"
            >
              Refresh
            </button>
          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs text-slate-500">
                <tr>
                  <th className="py-2 pr-4">ID</th>
                  <th className="py-2 pr-4">Platform</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">URL</th>
                  <th className="py-2 pr-4">Updated</th>
                </tr>
              </thead>
              <tbody className="text-slate-700">
                {jobs.map((j) => (
                  <tr key={j.id} className="border-t border-slate-100">
                    <td className="py-2 pr-4">{j.id}</td>
                    <td className="py-2 pr-4">{j.detected_platform}</td>
                    <td className="py-2 pr-4">
                      <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs">
                        {j.status}
                      </span>
                      {j.error ? <div className="mt-1 text-xs text-red-700">{j.error}</div> : null}
                    </td>
                    <td className="py-2 pr-4 max-w-[420px] truncate" title={j.normalized_profile_url}>
                      {j.normalized_profile_url}
                    </td>
                    <td className="py-2 pr-4">{j.updated_at}</td>
                  </tr>
                ))}
                {!jobs.length ? (
                  <tr>
                    <td colSpan={5} className="py-4 text-sm text-slate-500">
                      No jobs yet.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </RequireRole>
    </main>
  );
}
