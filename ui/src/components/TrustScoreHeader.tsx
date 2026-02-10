type Props = {
  name: string;
  avgTrust: number | null;
  worstTrust: number | null;
};

export default function TrustScoreHeader({ name, avgTrust, worstTrust }: Props) {
  const scoreText = avgTrust == null ? '—' : Math.round(avgTrust);
  const worstText = worstTrust == null ? '—' : Math.round(worstTrust);

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">{name}</h1>
          <div className="mt-1 text-sm text-slate-600">
            Worst platform score: <span className="font-medium text-slate-800">{worstText}</span>
          </div>
        </div>

        <div className="inline-flex items-center rounded-lg bg-slate-900 px-4 py-2 text-white">
          <div className="text-sm font-medium">Trust Score</div>
          <div className="ml-2 text-xl font-semibold">{scoreText}/100</div>
        </div>
      </div>
    </div>
  );
}
