import Link from 'next/link';

export const dynamic = 'force-dynamic';

export default function ClaimSubmittedPage() {
  return (
    <main className="mx-auto w-full max-w-2xl space-y-4 px-4 py-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-6">
        <h1 className="text-2xl font-semibold text-slate-900">Claim request submitted</h1>
        <p className="mt-2 text-sm text-slate-700">
          Thanks — this is a demo-only flow in V1. Your request was recorded locally and will be reviewed manually.
        </p>

        <div className="mt-5 flex flex-col gap-2 sm:flex-row">
          <Link
            href="/search"
            className="inline-flex items-center justify-center rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800"
          >
            Back to search
          </Link>
          <Link
            href="/"
            className="inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-900 hover:bg-slate-50"
          >
            Home
          </Link>
        </div>
      </div>

      <div className="text-xs text-slate-500">
        V1 is read-only: no authentication and no database changes.
      </div>
    </main>
  );
}
