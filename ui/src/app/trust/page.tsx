import type { TrustFlagsResponse, TrustFlagDef } from '../../lib/types';

export const dynamic = 'force-dynamic';

function severityClasses(sev: string) {
  if (sev === 'high') return 'border-red-200 bg-red-50 text-red-800';
  if (sev === 'medium') return 'border-amber-200 bg-amber-50 text-amber-800';
  return 'border-slate-200 bg-slate-50 text-slate-700';
}

export default async function TrustPage() {
  let flags: TrustFlagDef[] = [];
  let loadError: string | null = null;

  try {
    const res = await fetch('http://localhost:3000/api/trust_flags', { next: { revalidate: 3600 } });
    if (!res.ok) {
      loadError = `Failed to load trust flags (HTTP ${res.status})`;
    } else {
      const json = (await res.json()) as TrustFlagsResponse;
      flags = json.flags || [];
    }
  } catch (e: any) {
    loadError = String(e?.message || e);
  }

  return (
    <main className="mx-auto w-full max-w-4xl space-y-4 px-4 py-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-6">
        <h1 className="text-2xl font-semibold text-slate-900">How Trust Score Works</h1>
        <p className="mt-3 text-sm text-slate-700">
          Trust Score (0–100) is a precomputed, read-only signal that summarizes how reliable a creator’s recent public
          metrics and platform signals appear. It is designed to reflect engagement consistency and data quality — not
          follower count alone.
        </p>
        <p className="mt-2 text-sm text-slate-700">
          Trust flags provide transparency by explaining data limitations or anomalies observed during collection.
        </p>
      </div>

      {loadError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{loadError}</div>
      ) : null}

      <div className="rounded-2xl border border-slate-200 bg-white p-6">
        <div className="text-sm font-semibold text-slate-900">Trust flags</div>

        {(!flags || flags.length === 0) && !loadError ? (
          <div className="mt-3 text-sm text-slate-600">No trust flags available.</div>
        ) : null}

        <div className="mt-4 space-y-3">
          {flags.map((f) => (
            <div key={f.flag} className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="text-sm font-semibold text-slate-900">{f.label}</div>
                  <div className="mt-1 text-xs text-slate-500">{f.flag}</div>
                </div>
                <span
                  className={`inline-flex w-fit items-center rounded-full border px-3 py-1 text-xs font-medium ${severityClasses(
                    f.severity
                  )}`}
                >
                  {f.severity}
                </span>
              </div>
              <div className="mt-3 text-sm text-slate-700">{f.description}</div>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
