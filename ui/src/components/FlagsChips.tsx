import type { TrustFlagDef } from '../lib/types';

type Props = {
  title?: string;
  flags: string[];
  defs: TrustFlagDef[];
};

function severityClasses(sev: string) {
  if (sev === 'high') return 'border-red-200 bg-red-50 text-red-800';
  if (sev === 'medium') return 'border-amber-200 bg-amber-50 text-amber-800';
  return 'border-slate-200 bg-slate-50 text-slate-700';
}

export default function FlagsChips({ title, flags, defs }: Props) {
  if (!flags || flags.length === 0) return null;

  const map = new Map(defs.map((d) => [d.flag, d] as const));

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      {title ? <div className="mb-2 text-sm font-semibold text-slate-900">{title}</div> : null}
      <div className="flex flex-wrap gap-2">
        {flags.map((f) => {
          const def = map.get(f);
          const tooltip = def
            ? `${def.label}: ${def.description}`
            : `Unknown flag: ${f}`;
          const sev = def?.severity || 'low';
          const cls = severityClasses(sev);
          return (
            <span
              key={f}
              className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium ${cls}`}
              title={tooltip}
            >
              {def?.label || f}
            </span>
          );
        })}
      </div>
    </div>
  );
}
