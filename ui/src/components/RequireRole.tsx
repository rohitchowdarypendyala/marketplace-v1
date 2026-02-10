'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { getMe, logout } from '../lib/authClient';

type Props = {
  role: 'business' | 'influencer';
  children: React.ReactNode;
};

export default function RequireRole({ role, children }: Props) {
  const router = useRouter();
  const [state, setState] = useState<'loading' | 'ok' | 'unauthorized'>('loading');
  const [email, setEmail] = useState<string>('');

  useEffect(() => {
    let alive = true;
    setState('loading');

    getMe()
      .then((res) => {
        if (!alive) return;
        if (!res.ok || !res.user) {
          router.replace(`/login?role=${encodeURIComponent(role)}`);
          return;
        }
        if (res.user.role !== role) {
          setEmail(res.user.email);
          setState('unauthorized');
          return;
        }
        setState('ok');
      })
      .catch(() => {
        if (!alive) return;
        router.replace(`/login?role=${encodeURIComponent(role)}`);
      });

    return () => {
      alive = false;
    };
  }, [role, router]);

  async function onLogout() {
    try {
      await logout();
    } finally {
      router.replace('/');
    }
  }

  if (state === 'loading') {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">Loading…</div>
    );
  }

  if (state === 'unauthorized') {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-800">
        <div className="font-semibold">Unauthorized</div>
        <div className="mt-1">
          Signed in as <span className="font-medium">{email}</span>. This page requires role: <b>{role}</b>.
        </div>
        <button
          onClick={onLogout}
          className="mt-4 inline-flex items-center rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
        >
          Logout
        </button>
      </div>
    );
  }

  return <>{children}</>;
}
