#!/usr/bin/env python3
"""Marketplace V1 scoring engine (stdlib-only).

Computes explainable authenticity_score + trust_score for social_profiles.
YouTube scoring v1 implemented.

DB: /home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/marketplace.db

Usage:
  ../.venv/bin/python score_profiles.py --dry-run --platform youtube

Options:
  --dry-run
  --platform youtube|instagram|facebook|all (default all)
  --limit N (default 50)
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict

DB_PATH = "/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/marketplace.db"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_columns(con: sqlite3.Connection) -> None:
    # SQLite doesn't support IF NOT EXISTS for ADD COLUMN in older versions reliably;
    # do a pragma table_info check.
    cols = {row[1] for row in con.execute("PRAGMA table_info(social_profiles);").fetchall()}
    needed = {
        "authenticity_score": "REAL NULL",
        "trust_score": "REAL NULL",
        "reach_ratio": "REAL NULL",
        "trust_flags": "TEXT NULL",
        "updated_at": "TEXT NULL",
    }
    for name, decl in needed.items():
        if name not in cols:
            con.execute(f"ALTER TABLE social_profiles ADD COLUMN {name} {decl};")


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def score_youtube(
    subs: Optional[int],
    avg_views: Optional[float],
    freq: Optional[float],
    data_confidence: str,
) -> Tuple[Optional[float], float, float, List[str]]:
    flags: List[str] = []

    reach_ratio: Optional[float] = None
    if subs and avg_views is not None and subs > 0:
        reach_ratio = float(avg_views) / float(subs)
    else:
        flags.append("missing reach_ratio")

    authenticity = 60.0

    if reach_ratio is not None:
        if reach_ratio >= 0.8:
            authenticity += 25
        elif reach_ratio >= 0.4:
            authenticity += 18
        elif reach_ratio >= 0.2:
            authenticity += 10
        elif reach_ratio >= 0.1:
            authenticity += 5
        else:
            authenticity -= 10
            flags.append("low views vs subscribers")

    if freq is None:
        flags.append("missing posting frequency")
    else:
        if freq >= 4:
            authenticity += 10
        elif freq >= 2:
            authenticity += 6
        elif freq >= 1:
            authenticity += 3
        else:
            authenticity -= 5
            flags.append("infrequent posting")

    authenticity = clamp(authenticity)

    trust = authenticity
    if data_confidence == "high" or avg_views is not None:
        trust += 5
    trust = clamp(trust)

    return reach_ratio, authenticity, trust, flags


def score_instagram(
    followers: Optional[int],
    posts: Optional[int],
    avg_likes: Optional[float],
    avg_comments: Optional[float],
    freq: Optional[float],
    stats_status: str,
    data_confidence: str,
) -> Tuple[Optional[float], float, float, List[str]]:
    flags: List[str] = []

    engagement_rate: Optional[float] = None
    if followers and followers > 0 and (avg_likes is not None or avg_comments is not None):
        engagement_rate = float((avg_likes or 0.0) + (avg_comments or 0.0)) / float(followers)

    authenticity = 55.0

    if followers is None or posts is None:
        authenticity = 25.0
        flags.append("missing_core_stats")
    else:
        if posts < 5 and followers > 10000:
            authenticity -= 10
            flags.append("few_posts_high_followers")

        if engagement_rate is None:
            flags.append("missing_engagement_metrics")
        else:
            if engagement_rate >= 0.05:
                authenticity += 25
            elif engagement_rate >= 0.03:
                authenticity += 18
            elif engagement_rate >= 0.015:
                authenticity += 10
            elif engagement_rate >= 0.008:
                authenticity += 5
            else:
                authenticity -= 10
                flags.append("low_engagement_rate")

        if freq is None:
            flags.append("missing_posting_frequency")
        else:
            if freq >= 4:
                authenticity += 8
            elif freq >= 2:
                authenticity += 5
            elif freq >= 1:
                authenticity += 2
            else:
                authenticity -= 5
                flags.append("infrequent_posting")

        if stats_status in ("self_submitted", "oauth_verified"):
            authenticity += 5
        elif stats_status == "missing_public":
            authenticity -= 5
            flags.append("unverified_public_stats")

    authenticity = clamp(authenticity)

    trust = authenticity
    if stats_status == "oauth_verified":
        trust += 10
    elif stats_status == "self_submitted":
        trust += 5
    if data_confidence == "low":
        trust -= 5
    trust = clamp(trust)

    return engagement_rate, authenticity, trust, flags


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--platform", default="all", choices=["youtube", "instagram", "facebook", "all"])
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--id", type=int, default=None, help="Score only a specific social_profiles.id")
    args = ap.parse_args()

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA foreign_keys = ON;")
        ensure_columns(con)

        where_parts = []
        params: List[object] = []
        if args.platform != "all":
            where_parts.append("platform = ?")
            params.append(args.platform)
        if args.id is not None:
            where_parts.append("id = ?")
            params.append(args.id)

        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        rows = con.execute(
            f"""
            SELECT id, platform, handle, followers, posts,
                   avg_views_last_10, avg_likes_last_10, avg_comments_last_10,
                   posting_frequency_per_week, stats_status, data_confidence
            FROM social_profiles
            {where}
            ORDER BY id ASC
            LIMIT ?
            """,
            (*params, args.limit),
        ).fetchall()

        now = utc_now_iso()

        for r in rows:
            pid = int(r["id"])
            platform = r["platform"]
            handle = r["handle"] or ""
            subs = r["followers"]
            posts = r["posts"]
            avg_views = r["avg_views_last_10"]
            avg_likes = r["avg_likes_last_10"]
            avg_comments = r["avg_comments_last_10"]
            freq = r["posting_frequency_per_week"]
            stats_status = (r["stats_status"] or "missing_public").strip().lower()
            data_conf = (r["data_confidence"] or "low").strip().lower()

            reach_ratio = None
            authenticity = None
            trust = None
            flags: List[str] = []

            if platform == "youtube":
                reach_ratio, authenticity, trust, flags = score_youtube(subs, avg_views, freq, data_conf)
            elif platform == "instagram":
                reach_ratio, authenticity, trust, flags = score_instagram(
                    subs, posts, avg_likes, avg_comments, freq, stats_status, data_conf
                )
            else:
                continue

            # Remove stale placeholder flags
            flags = [f for f in flags if f != "scoring_not_implemented"]

            flags_json = json.dumps(flags)

            # Console output per requirements
            rr_disp = "" if reach_ratio is None else f"{reach_ratio:.4f}"
            print(
                f"social_profile_id: {pid} | platform: {platform} | handle: {handle} | "
                f"reach_ratio: {rr_disp} | authenticity_score: {authenticity:.1f} | trust_score: {trust:.1f} | flags: {flags_json}"
            )

            if not args.dry_run:
                con.execute(
                    """
                    UPDATE social_profiles
                    SET authenticity_score = ?, trust_score = ?, reach_ratio = ?, trust_flags = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (authenticity, trust, reach_ratio, flags_json, now, pid),
                )

        if not args.dry_run:
            con.commit()

    finally:
        con.close()


if __name__ == "__main__":
    main()
