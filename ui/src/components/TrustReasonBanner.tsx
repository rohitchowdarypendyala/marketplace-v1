type Props = {
  reason: string | null;
};

export default function TrustReasonBanner({ reason }: Props) {
  if (!reason || !reason.trim()) return null;

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-950">
      <div className="text-sm font-semibold">Note</div>
      <div className="mt-1 text-sm">{reason}</div>
    </div>
  );
}
