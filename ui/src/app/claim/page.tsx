'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

export default function ClaimPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [platform, setPlatform] = useState<'instagram' | 'youtube'>('instagram');
  const [profileUrl, setProfileUrl] = useState('');
  const [note, setNote] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    const em = email.trim();
    const url = profileUrl.trim();

    if (!em || !em.includes('@')) {
      setError('Please enter a valid email.');
      return;
    }
    if (!url || !url.startsWith('http')) {
      setError('Please enter a valid profile URL (starting with http/https).');
      return;
    }

    setLoading(true);
    try {
      const res = await fetch('/api/claim/request', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email: em, platform, profile_url: url, note: note.trim() }),
      });

      const json = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(json?.message || `Request failed (HTTP ${res.status})`);
      }

      setSuccess(`Request submitted. Reference: ${json?.request_id || 'ok'}`);

      // Redirect to submitted page (demo)
      router.push('/claim/submitted');
    } catch (err: any) {
      setError(String(err?.message || err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-3xl space-y-4 px-4 py-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-6">
        <h1 className="text-2xl font-semibold text-slate-900">Claim your creator profile</h1>
        <p className="mt-2 text-sm text-slate-600">Demo only — no data changes in V1</p>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6">
        <div className="text-sm font-semibold text-slate-900">Find your profile</div>
        <p className="mt-2 text-sm text-slate-700">
          Start by searching creators here:{' '}
          <Link href="/search" className="font-medium text-slate-900 hover:underline">
            /search
          </Link>
          . If you can’t find your profile, submit a manual claim request below.
        </p>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6">
        <div className="text-sm font-semibold text-slate-900">Manual claim request</div>
        <p className="mt-2 text-sm text-slate-600">This submits a request for review. No database changes are made.</p>

        {error ? (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>
        ) : null}

        {success ? (
          <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
            {success}
          </div>
        ) : null}

        <form onSubmit={onSubmit} className="mt-4 space-y-4">
          <div>
            <label className="text-xs font-medium text-slate-600">Email (required)</label>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              placeholder="you@domain.com"
              className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-slate-400"
              required
            />
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600">Platform</label>
            <select
              value={platform}
              onChange={(e) => setPlatform(e.target.value as any)}
              className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              <option value="instagram">Instagram</option>
              <option value="youtube">YouTube</option>
            </select>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600">Profile URL (required)</label>
            <input
              value={profileUrl}
              onChange={(e) => setProfileUrl(e.target.value)}
              type="url"
              placeholder="https://www.instagram.com/yourhandle/"
              className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-slate-400"
              required
            />
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600">Note (optional)</label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Anything you want us to know"
              className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-slate-400"
              rows={3}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="inline-flex w-full items-center justify-center rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
          >
            {loading ? 'Submitting…' : 'Submit request'}
          </button>
        </form>
      </div>
    </main>
  );
}
