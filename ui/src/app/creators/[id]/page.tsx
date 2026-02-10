import TrustScoreHeader from '../../../components/TrustScoreHeader';
import TrustReasonBanner from '../../../components/TrustReasonBanner';
import FlagsChips from '../../../components/FlagsChips';
import PlatformCard from '../../../components/PlatformCard';
import ContactCTA from '../../../components/ContactCTA';
import type { CreatorApiResponse, TrustFlagsResponse } from '../../../lib/types';

export const dynamic = 'force-dynamic';

const ORIGIN = process.env.NEXT_PUBLIC_APP_URL || `http://localhost:${process.env.PORT || 3000}`;

async function fetchCreator(id: string): Promise<CreatorApiResponse> {
  const res = await fetch(`${ORIGIN}/api/creators/${id}`, { cache: 'no-store' });
  if (!res.ok) {
    throw new Error(`Failed to load creator ${id}: ${res.status}`);
  }
  return (await res.json()) as CreatorApiResponse;
}

async function fetchTrustFlags(): Promise<TrustFlagsResponse> {
  const res = await fetch(`${ORIGIN}/api/trust_flags`, { next: { revalidate: 3600 } });
  if (!res.ok) {
    throw new Error(`Failed to load trust flags: ${res.status}`);
  }
  return (await res.json()) as TrustFlagsResponse;
}

export default async function CreatorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const [data, flagsResp] = await Promise.all([fetchCreator(id), fetchTrustFlags()]);

  const creator = data.creator;
  const profiles = data.profiles || [];
  const trustFlagDefs = flagsResp.flags || [];

  // Trust reason banner: if ANY profile has non-empty trust_reason
  const reason = profiles.find((p) => p.trust_reason && p.trust_reason.trim())?.trust_reason || null;

  return (
    <main className="mx-auto w-full max-w-5xl space-y-4 px-4 py-6">
      <TrustScoreHeader name={creator.primary_name} avgTrust={creator.avg_trust} worstTrust={creator.worst_trust} />

      <TrustReasonBanner reason={reason} />

      <FlagsChips title="Creator flags" flags={creator.flags_summary || []} defs={trustFlagDefs} />

      <div className="grid grid-cols-1 gap-4">
        {profiles.map((p) => (
          <PlatformCard key={p.id} profile={p} trustFlagDefs={trustFlagDefs} />
        ))}
      </div>

      <ContactCTA emails={data.contact?.emails || []} website={data.contact?.website || null} profiles={profiles} />

      <div className="text-xs text-slate-500">
        Data is read-only. Trust score and flags are computed from collected public signals.
      </div>
    </main>
  );
}
