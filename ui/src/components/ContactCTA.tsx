import type { SocialProfileRow } from '../lib/types';

type Props = {
  emails: string[];
  website: string | null;
  profiles: SocialProfileRow[];
};

function platformLabel(platform: string) {
  if (platform === 'instagram') return 'Instagram';
  if (platform === 'youtube') return 'YouTube';
  return platform;
}

export default function ContactCTA({ emails, website, profiles }: Props) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="text-sm font-semibold text-slate-900">Contact</div>
      <div className="mt-1 text-sm text-slate-600">External only (email / website / platform links)</div>

      <div className="mt-4 flex flex-col gap-2">
        {emails && emails.length ? (
          <div className="flex flex-wrap gap-2">
            {emails.map((e) => (
              <a
                key={e}
                href={`mailto:${e}`}
                className="inline-flex items-center rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
              >
                Email: {e}
              </a>
            ))}
          </div>
        ) : (
          <div className="text-sm text-slate-600">No email found.</div>
        )}

        {website ? (
          <a
            href={website}
            target="_blank"
            rel="noreferrer"
            className="inline-flex w-fit items-center rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-900 hover:bg-slate-50"
          >
            Visit website
          </a>
        ) : null}

        <div className="mt-3">
          <div className="text-xs font-medium text-slate-600">Platform links</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {profiles.map((p) => (
              <a
                key={p.id}
                href={p.profile_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-900 hover:bg-slate-50"
              >
                Open {platformLabel(p.platform)}
              </a>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
