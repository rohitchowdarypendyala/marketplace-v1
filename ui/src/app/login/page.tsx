'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { startOtp, verifyOtp } from '../../lib/authClient';

export default function LoginPage() {
  const router = useRouter();
  const sp = useSearchParams();

  const initialRole = (sp.get('role') || 'business').toLowerCase();
  const [role, setRole] = useState<'business' | 'influencer'>(
    initialRole === 'influencer' ? 'influencer' : 'business'
  );

  const [email, setEmail] = useState('');
  const [step, setStep] = useState<'start' | 'verify'>('start');
  const [otp, setOtp] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    // keep role in sync with URL if user lands on /login?role=influencer
    setRole(initialRole === 'influencer' ? 'influencer' : 'business');
  }, [initialRole]);

  async function onSend() {
    setError(null);
    const em = email.trim().toLowerCase();
    if (!em || !em.includes('@')) {
      setError('Please enter a valid email.');
      return;
    }

    setLoading(true);
    try {
      await startOtp(em, role);
      setSent(true);
      setStep('verify');
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function onVerify() {
    setError(null);
    const em = email.trim().toLowerCase();
    const code = otp.trim();

    if (!/^[0-9]{6}$/.test(code)) {
      setError('Enter the 6-digit OTP.');
      return;
    }

    setLoading(true);
    try {
      const res = await verifyOtp(em, code, role);
      // Redirect based on selected role (demo)
      if (role === 'influencer') router.push('/me');
      else router.push('/search');
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-md space-y-4 px-4 py-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-6">
        <h1 className="text-2xl font-semibold text-slate-900">Login</h1>
        <p className="mt-2 text-sm text-slate-600">Demo OTP — code is printed in server logs.</p>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6">
        {error ? (
          <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            {error}
          </div>
        ) : null}

        <div className="space-y-4">
          <div>
            <label className="text-xs font-medium text-slate-600">Role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as any)}
              className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
              disabled={step === 'verify'}
            >
              <option value="business">Business</option>
              <option value="influencer">Influencer</option>
            </select>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600">Email</label>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              placeholder="you@domain.com"
              className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-slate-400"
              disabled={step === 'verify'}
            />
          </div>

          {step === 'start' ? (
            <button
              onClick={onSend}
              disabled={loading}
              className="inline-flex w-full items-center justify-center rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
            >
              {loading ? 'Sending…' : 'Send OTP'}
            </button>
          ) : (
            <>
              <div>
                <label className="text-xs font-medium text-slate-600">OTP (6 digits)</label>
                <input
                  value={otp}
                  onChange={(e) => setOtp(e.target.value)}
                  inputMode="numeric"
                  placeholder="123456"
                  className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-slate-400"
                />
                <div className="mt-2 text-xs text-slate-500">
                  {sent ? 'OTP sent. Check server logs (demo).' : null}
                </div>
              </div>

              <button
                onClick={onVerify}
                disabled={loading}
                className="inline-flex w-full items-center justify-center rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
              >
                {loading ? 'Verifying…' : 'Verify'}
              </button>

              <button
                onClick={() => {
                  setStep('start');
                  setOtp('');
                  setSent(false);
                  setError(null);
                }}
                className="w-full text-sm font-medium text-slate-700 hover:text-slate-900"
              >
                Start over
              </button>
            </>
          )}
        </div>
      </div>
    </main>
  );
}
