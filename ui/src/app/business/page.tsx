'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import RequireRole from '../../components/RequireRole';
import { getMe, logout } from '../../lib/authClient';

export default function BusinessPage() {
  const router = useRouter();
  const [email, setEmail] = useState<string>('');
  const [role, setRole] = useState<string>('');

  useEffect(() => {
    getMe().then((r) => {
      if (r.ok && r.user) {
        setEmail(r.user.email);
        setRole(r.user.role);
      }
    });
  }, []);

  async function onLogout() {
    try {
      await logout();
    } finally {
      router.replace('/');
    }
  }

  return (
    <main className="mx-auto w-full max-w-3xl space-y-4 px-4 py-6">
      <RequireRole role="business">
        <div className="rounded-2xl border border-slate-200 bg-white p-6">
          <h1 className="text-2xl font-semibold text-slate-900">Business</h1>
          <div className="mt-2 text-sm text-slate-700">
            Signed in as <span className="font-medium">{email}</span>
          </div>
          <div className="mt-1 text-sm text-slate-600">Role: {role}</div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6">
          <Link href="/search" className="inline-flex text-sm font-medium text-slate-900 hover:underline">
            Go to /search
          </Link>
        </div>

        <button
          onClick={onLogout}
          className="inline-flex w-fit items-center rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800"
        >
          Logout
        </button>
      </RequireRole>
    </main>
  );
}
