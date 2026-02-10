#!/usr/bin/env python3
"""Recompute V1 Trust Scores for the influencer marketplace.

Writes:
- social_profiles.trust_score (per-profile platform_score 0..100)
- social_profiles.trust_reason (short human-readable reason)
- social_profiles.trust_flags (JSON array; may add required missing_* flags)
- creators.avg_trust / creators.worst_trust / creators.flags_summary (creator-level)

Deterministic, stdlib-only.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import fmean
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = "/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/marketplace.db"


CANONICAL_TRUST_FLAGS = [
    "comments_disabled_or_limited",
    "comments_suspicious_filtered",
    "engagement_metric_suspicious_filtered",
    "followers_discrepancy_meta_vs_header",
    "likes_hidden",
    "missing_engagement_metrics",
    "missing_posting_frequency",
    "missing_views_for_engagement",
    "views_dom_outlier",
    "blocked_or_challenge",
    "partial_metrics_due_to_block",
]

PENALTIES: Dict[str, float] = {
    "missing_engagement_metrics": 15,
    "missing_posting_frequency": 10,
    "missing_views_for_engagement": 6,
    "views_dom_outlier": 8,
    "engagement_metric_suspicious_filtered": 10,
    "comments_disabled_or_limited": 4,
    "comments_suspicious_filtered": 6,
    "likes_hidden": 6,
    "followers_discrepancy_meta_vs_header": 3,
    "blocked_or_challenge": 20,
}


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def safe_json_list(val: Any) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:
            return []
    return []


def json_dumps_compact(xs: List[str]) -> str:
    return json.dumps(xs, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def mean(xs: List[float]) -> Optional[float]:
    xs2 = [x for x in xs if x is not None]
    if not xs2:
        return None
    return float(fmean(xs2))


@dataclass
class SocialProfile:
    id: int
    creator_id: Optional[int]
    platform: str
    profile_url: str
    handle: Optional[str]
    followers: Optional[int]
    avg_views_last_10: Optional[float]
    avg_likes_last_10: Optional[float]
    avg_comments_last_10: Optional[float]
    posting_frequency_per_week: Optional[float]
    stats_status: str
    data_confidence: str
    trust_flags: List[str]


def compute_platform_score(sp: SocialProfile) -> Tuple[float, List[str]]:
    flags = list(dict.fromkeys(sp.trust_flags))

    # A1 Engagement Rate score (0–40)
    engagement_points = 0.0
    if sp.avg_views_last_10 is not None and sp.avg_views_last_10 > 0:
        likes = float(sp.avg_likes_last_10 or 0.0)
        comments = float(sp.avg_comments_last_10 or 0.0)
        like_rate = likes / float(sp.avg_views_last_10)
        comment_rate = comments / float(sp.avg_views_last_10)
        eng_rate = like_rate + 2.0 * comment_rate
        engagement_points = 40.0 * min(eng_rate, 0.08) / 0.08
    else:
        if (sp.avg_likes_last_10 is not None) or (sp.avg_comments_last_10 is not None):
            engagement_points = 10.0
            if "missing_views_for_engagement" not in flags:
                flags.append("missing_views_for_engagement")
        else:
            engagement_points = 0.0
            if "missing_engagement_metrics" not in flags:
                flags.append("missing_engagement_metrics")

    # A2 Consistency score (0–25) from pfw
    pfw = sp.posting_frequency_per_week
    if pfw is None:
        consistency_points = 0.0
        if "missing_posting_frequency" not in flags:
            flags.append("missing_posting_frequency")
    else:
        if pfw >= 5:
            consistency_points = 25.0
        elif pfw >= 3:
            consistency_points = 20.0
        elif pfw >= 1:
            consistency_points = 14.0
        elif pfw >= 0.5:
            consistency_points = 8.0
        else:
            consistency_points = 3.0

    # A3 Reach reliability score (0–15)
    reach_points = 8.0
    if (sp.followers is not None and sp.followers > 0) and (sp.avg_views_last_10 is not None):
        ratio = float(sp.avg_views_last_10) / float(sp.followers)
        if 0.02 <= ratio <= 0.40:
            reach_points = 15.0
        elif (0.005 <= ratio < 0.02) or (0.40 < ratio <= 1.50):
            reach_points = 10.0
        else:
            reach_points = 5.0

    # A4 Data quality score (0–20)
    quality_points = 0.0
    if (sp.stats_status or "").lower() == "ok":
        quality_points += 10.0

    dc = (sp.data_confidence or "").lower()
    if dc == "high":
        quality_points += 10.0
    elif dc == "medium":
        quality_points += 6.0
    elif dc == "low":
        quality_points += 3.0
    else:
        quality_points += 0.0

    platform_score = clamp(engagement_points + consistency_points + reach_points + quality_points, 0.0, 100.0)
    return platform_score, flags


def profile_weight(sp: SocialProfile) -> float:
    present = 0
    if sp.avg_views_last_10 is not None:
        present += 1
    if sp.avg_likes_last_10 is not None:
        present += 1
    if sp.avg_comments_last_10 is not None:
        present += 1
    if sp.posting_frequency_per_week is not None:
        present += 1

    if present == 4:
        return 1.0
    if present >= 2:
        return 0.7
    return 0.4


def creator_trust_reason(all_flags: List[str]) -> str:
    s = set(all_flags)
    if any(f.startswith("missing_") for f in s):
        return "insufficient data to compute accurately (missing engagement/posting frequency/views)"
    if "blocked_or_challenge" in s:
        return "instagram blocked/challenge — partial data"
    return ""


def compute_creator_trust(
    profiles: List[Tuple[SocialProfile, float]],
    creator_platforms_ok: Dict[str, bool],
) -> Tuple[float, str, List[str]]:
    # profiles: list of (profile, platform_score)
    if not profiles:
        return 0.0, "insufficient data to compute accurately (missing engagement/posting frequency/views)", ["missing_engagement_metrics"]

    # Weighted average of platform_score
    num = 0.0
    den = 0.0
    all_flags: List[str] = []
    for sp, platform_score in profiles:
        w = profile_weight(sp)
        num += (platform_score * w)
        den += w
        all_flags.extend(sp.trust_flags)
    weighted_avg = (num / den) if den > 0 else 0.0

    # platform bonus
    bonus = 0.0
    if creator_platforms_ok.get("instagram") and creator_platforms_ok.get("youtube"):
        bonus = 5.0

    # penalties: unique flags across creator
    uniq_flags = list(dict.fromkeys(all_flags))
    penalty = 0.0
    for f in uniq_flags:
        penalty += float(PENALTIES.get(f, 0.0))

    final_trust = clamp(weighted_avg + bonus - penalty, 0.0, 100.0)
    reason = creator_trust_reason(uniq_flags)
    return final_trust, reason, uniq_flags


def ensure_column_exists(cur: sqlite3.Cursor, table: str, col: str) -> bool:
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table});").fetchall()]
    return col in cols


def main() -> int:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Schema sanity
    for tbl, col in [
        ("social_profiles", "trust_score"),
        ("social_profiles", "trust_flags"),
        ("creators", "id"),
    ]:
        if not ensure_column_exists(cur, tbl, col):
            raise RuntimeError(f"Missing required column: {tbl}.{col}")

    has_trust_reason = ensure_column_exists(cur, "social_profiles", "trust_reason")
    has_creator_avg = ensure_column_exists(cur, "creators", "avg_trust")
    has_creator_worst = ensure_column_exists(cur, "creators", "worst_trust")
    has_creator_flags = ensure_column_exists(cur, "creators", "flags_summary")

    # Load profiles
    rows = cur.execute(
        """
        SELECT
          id, creator_id, platform, profile_url, handle,
          followers, avg_views_last_10, avg_likes_last_10, avg_comments_last_10,
          posting_frequency_per_week, stats_status, data_confidence, trust_flags
        FROM social_profiles
        """
    ).fetchall()

    profiles_by_creator: Dict[Optional[int], List[SocialProfile]] = defaultdict(list)
    all_profiles: List[SocialProfile] = []

    for r in rows:
        sp = SocialProfile(
            id=int(r["id"]),
            creator_id=(int(r["creator_id"]) if r["creator_id"] is not None else None),
            platform=str(r["platform"]),
            profile_url=str(r["profile_url"]),
            handle=(str(r["handle"]) if r["handle"] is not None else None),
            followers=(int(r["followers"]) if r["followers"] is not None else None),
            avg_views_last_10=(float(r["avg_views_last_10"]) if r["avg_views_last_10"] is not None else None),
            avg_likes_last_10=(float(r["avg_likes_last_10"]) if r["avg_likes_last_10"] is not None else None),
            avg_comments_last_10=(float(r["avg_comments_last_10"]) if r["avg_comments_last_10"] is not None else None),
            posting_frequency_per_week=(float(r["posting_frequency_per_week"]) if r["posting_frequency_per_week"] is not None else None),
            stats_status=str(r["stats_status"]),
            data_confidence=str(r["data_confidence"]),
            trust_flags=safe_json_list(r["trust_flags"]),
        )
        all_profiles.append(sp)
        profiles_by_creator[sp.creator_id].append(sp)

    now = datetime.now(timezone.utc).isoformat()

    # Per-profile platform score
    profile_platform_score: Dict[int, float] = {}
    profile_flags_updated: Dict[int, List[str]] = {}

    for sp in all_profiles:
        platform_score, flags = compute_platform_score(sp)
        profile_platform_score[sp.id] = platform_score
        profile_flags_updated[sp.id] = flags

        # Write back per-profile trust_score
        cur.execute(
            "UPDATE social_profiles SET trust_score=?, trust_flags=?, updated_at=? WHERE id=?",
            (platform_score, json_dumps_compact(flags), now, sp.id),
        )

    # Per-creator trust summary
    creator_rows = cur.execute("SELECT id, primary_name FROM creators").fetchall()
    creators = {int(r["id"]): str(r["primary_name"]) for r in creator_rows}

    creator_scores: Dict[int, float] = {}

    for creator_id, profs in profiles_by_creator.items():
        if creator_id is None:
            continue

        # set updated flags on each profile object in-memory
        updated_profiles: List[SocialProfile] = []
        for sp in profs:
            sp2 = SocialProfile(**{**sp.__dict__, "trust_flags": profile_flags_updated.get(sp.id, sp.trust_flags)})
            updated_profiles.append(sp2)

        creator_platforms_ok = {
            "instagram": any((p.platform == "instagram" and (p.stats_status or "").lower() == "ok") for p in updated_profiles),
            "youtube": any((p.platform == "youtube" and (p.stats_status or "").lower() == "ok") for p in updated_profiles),
        }

        items = [(p, float(profile_platform_score.get(p.id, 0.0))) for p in updated_profiles]
        creator_trust, reason, uniq_flags = compute_creator_trust(items, creator_platforms_ok)
        creator_scores[creator_id] = creator_trust

        # Write trust_reason per profile (same reason for profiles under creator; UI can show creator reason)
        if has_trust_reason:
            for p in updated_profiles:
                cur.execute(
                    "UPDATE social_profiles SET trust_reason=?, updated_at=? WHERE id=?",
                    (reason, now, p.id),
                )

        # creators summary fields
        if has_creator_avg or has_creator_worst or has_creator_flags:
            platform_scores = [float(profile_platform_score.get(p.id, 0.0)) for p in updated_profiles]
            avg_trust = mean(platform_scores)
            worst_trust = min(platform_scores) if platform_scores else None
            flags_summary = json_dumps_compact(list(dict.fromkeys(uniq_flags)))

            sets = []
            params: List[Any] = []
            if has_creator_avg:
                sets.append("avg_trust=?")
                params.append(creator_trust)
            if has_creator_worst:
                sets.append("worst_trust=?")
                params.append(float(worst_trust) if worst_trust is not None else None)
            if has_creator_flags:
                sets.append("flags_summary=?")
                params.append(flags_summary)
            if sets:
                params.append(creator_id)
                cur.execute(f"UPDATE creators SET {', '.join(sets)} WHERE id=?", params)

    con.commit()

    # Print top 5 creators by reach (followers)
    # Reach heuristic: max followers across the creator's social profiles.
    reach_by_creator: Dict[int, int] = defaultdict(int)
    for sp in all_profiles:
        if sp.creator_id is None:
            continue
        if sp.followers is not None:
            reach_by_creator[sp.creator_id] = max(reach_by_creator[sp.creator_id], int(sp.followers))

    ranked = sorted(reach_by_creator.items(), key=lambda kv: kv[1], reverse=True)[:5]
    print("top5_creators_by_reach:")
    for cid, reach in ranked:
        name = creators.get(cid, f"creator_{cid}")
        ct = creator_scores.get(cid)
        print(f"- creator_id={cid} name={name} reach_followers_max={reach} creator_trust={'' if ct is None else round(ct, 2)}")

    print(f"profiles_updated: {len(all_profiles)}")
    print(f"creators_updated: {len(creator_scores)}")

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
