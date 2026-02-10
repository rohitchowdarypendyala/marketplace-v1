'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { getMe, logout } from '../lib/authClient';
import type { MeResponse } from '../lib/types';

export default function AppHeader() {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getMe()
      .then((r) => {
        if (!alive) return;
        setMe(r);
        setLoading(false);
      })
      .catch(() => {
        if (!alive) return;
        setMe({ ok: false, user: null });
        setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [pathname]);

  async function onLogout() {
    try {
      await logout();
    } finally {
      // refresh current page state
      router.push('/');
      router.refresh();
    }
  }

  const user = me?.ok ? me.user : null;

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/" className="text-sm font-semibold text-slate-900">
          Marketplace
        </Link>

        <div className="flex items-center gap-3">
          {loading ? (
            <div className="text-sm text-slate-500">…</div>
          ) : user ? (
            <>
              <div className="hidden text-sm text-slate-600 sm:block">
                Signed in as <span className="font-medium text-slate-900">{user.email}</span>
              </div>
              <button
                onClick={onLogout}
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-900 hover:bg-slate-50"
              >
                Logout
              </button>
            </>
          ) : (
            <Link
              href="/login"
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-900 hover:bg-slate-50"
            >
              Login
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
