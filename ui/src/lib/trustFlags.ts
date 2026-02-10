export const TRUST_FLAGS = [
  {
    flag: "views_dom_outlier",
    label: "Unusual view spikes",
    severity: "medium",
    description: "Recent posts show view counts that deviate significantly from typical engagement patterns.",
  },
  {
    flag: "engagement_metric_suspicious_filtered",
    label: "Engagement metrics filtered",
    severity: "medium",
    description: "Some engagement metrics were excluded due to suspicious or inconsistent values.",
  },
  {
    flag: "comments_disabled_or_limited",
    label: "Comments limited or disabled",
    severity: "medium",
    description: "Comments appear limited or disabled on recent posts.",
  },
  {
    flag: "missing_engagement_metrics",
    label: "Missing engagement data",
    severity: "high",
    description: "Likes or comments could not be reliably collected.",
  },
  {
    flag: "blocked_or_challenge",
    label: "Platform restriction detected",
    severity: "high",
    description: "The profile triggered platform challenges or access blocks during collection.",
  },
  {
    flag: "admin_added",
    label: "Added by website team",
    severity: "low",
    description: "This profile was added manually by the website team using the admin tool.",
  },
];
