export type TrustFlagDef = {
  flag: string;
  label: string;
  severity: 'low' | 'medium' | 'high';
  description: string;
};

export type TrustFlagsResponse = {
  flags: TrustFlagDef[];
};

export type CreatorRow = {
  id: number;
  primary_name: string;
  avg_trust: number | null;
  worst_trust: number | null;
  flags_summary: string[];
};

export type SocialProfileRow = {
  id: number;
  creator_id: number;
  platform: 'instagram' | 'youtube' | string;
  profile_url: string;
  handle: string | null;
  display_name: string | null;
  bio: string | null;

  followers: number | null;
  following: number | null;
  posts: number | null;
  total_views: number | null;

  avg_views_last_10: number | null;
  avg_likes_last_10: number | null;
  avg_comments_last_10: number | null;
  posting_frequency_per_week: number | null;
  posting_frequency_per_week_90d: number | null;

  stats_status: string;
  data_confidence: string;

  trust_score: number | null;
  trust_reason: string | null;
  trust_flags: string[];

  contact_emails_json?: string | null;
  contact_emails?: string[];
  primary_website?: string | null;
  contact_website?: string | null;
  external_website?: string | null;
  external_links_json?: string | null;

  updated_at: string | null;
  last_fetched_at: string | null;
};

export type CreatorApiResponse = {
  creator: CreatorRow;
  profiles: SocialProfileRow[];
  contact: {
    emails: string[];
    website: string | null;
  };
};

export type MeResponse = {
  ok: boolean;
  user: { id: number; email: string; role: string } | null;
};

export type AuthStartResponse = { ok: boolean };

export type AuthVerifyResponse = {
  ok: boolean;
  user: { id: number; email: string; role: string };
};

export type LogoutResponse = { ok: boolean };

export type HeadlineProfile = {
  id: number;
  platform: string;
  handle: string | null;
  profile_url: string;
  followers: number | null;
  avg_views_last_10: number | null;
  avg_likes_last_10: number | null;
  avg_comments_last_10: number | null;
  posting_frequency_per_week: number | null;
  stats_status: string;
  data_confidence: string;
  trust_score: number | null;
  trust_reason: string | null;
} | null;

export type CreatorListItem = {
  creator: CreatorRow;
  headline_profile: HeadlineProfile;
};

export type CreatorListResponse = {
  items: CreatorListItem[];
  limit: number;
  offset: number;
  total: number;
};
