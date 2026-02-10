#!/usr/bin/env python3
"""Manual/self-submitted stats updater for marketplace.

Stdlib only: sqlite3, argparse, datetime, json

Updates an existing social_profiles row (by profile_url preferred; else platform+handle),
inserts a profile_snapshots row, and optionally re-scores.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = "/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/marketplace.db"

METRIC_FIELDS = {
    "followers",
    "following",
    "posts",
    "total_views",
    "avg_views_last_10",
    "avg_likes_last_10",
    "avg_comments_last_10",
    "posting_frequency_per_week",
}

OTHER_FIELDS = {
    "bio",
    "external_website",
    "linktree_domain",
}

SUPPORTED_FIELDS = METRIC_FIELDS | OTHER_FIELDS


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_handle(h: str) -> str:
    h = (h or "").strip()
    if h.startswith("@"):  # store without @ for matching
        h = h[1:]
    return h.lower()


def ensure_columns(con: sqlite3.Connection) -> None:
    cols = {row[1] for row in con.execute("PRAGMA table_info(social_profiles);").fetchall()}
    # ensure stats_status exists
    if "stats_status" not in cols:
        con.execute(
            "ALTER TABLE social_profiles ADD COLUMN stats_status TEXT NOT NULL DEFAULT 'missing_public' CHECK(stats_status IN ('ok','missing_public','self_submitted','oauth_verified'));"
        )
    # scoring columns (from PROMPT 3)
    if "authenticity_score" not in cols:
        con.execute("ALTER TABLE social_profiles ADD COLUMN authenticity_score REAL NULL;")
    if "trust_score" not in cols:
        con.execute("ALTER TABLE social_profiles ADD COLUMN trust_score REAL NULL;")
    if "reach_ratio" not in cols:
        con.execute("ALTER TABLE social_profiles ADD COLUMN reach_ratio REAL NULL;")
    if "trust_flags" not in cols:
        con.execute("ALTER TABLE social_profiles ADD COLUMN trust_flags TEXT NULL;")
    if "updated_at" not in cols:
        con.execute("ALTER TABLE social_profiles ADD COLUMN updated_at TEXT NULL;")


def fetch_profile(con: sqlite3.Connection, platform: str, profile_url: Optional[str], handle: Optional[str]) -> Optional[sqlite3.Row]:
    con.row_factory = sqlite3.Row
    if profile_url:
        return con.execute("SELECT * FROM social_profiles WHERE profile_url = ?", (profile_url,)).fetchone()

    if not handle:
        return None
    nh = normalize_handle(handle)
    # match both stored with and without @
    return con.execute(
        """
        SELECT * FROM social_profiles
        WHERE platform = ?
          AND (lower(replace(handle,'@','')) = ?)
        """,
        (platform, nh),
    ).fetchone()


def compute_youtube_score(row: sqlite3.Row) -> Tuple[Optional[float], Optional[float], Optional[float], List[str]]:
    # Inline replicate scoring rules from score_profiles.py for youtube.
    subs = row["followers"]
    avg_views = row["avg_views_last_10"]
    freq = row["posting_frequency_per_week"]
    data_confidence = (row["data_confidence"] or "low").strip().lower()

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

    authenticity = max(0.0, min(100.0, authenticity))

    trust = authenticity
    if data_confidence == "high" or avg_views is not None:
        trust += 5
    trust = max(0.0, min(100.0, trust))

    return reach_ratio, authenticity, trust, flags


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True, choices=["instagram", "youtube", "facebook"])
    ap.add_argument("--handle", default=None)
    ap.add_argument("--profile-url", default=None)

    # Updatable fields
    ap.add_argument("--followers", type=int)
    ap.add_argument("--following", type=int)
    ap.add_argument("--posts", type=int)
    ap.add_argument("--total_views", type=int)
    ap.add_argument("--avg_views_last_10", type=float)
    ap.add_argument("--avg_likes_last_10", type=float)
    ap.add_argument("--avg_comments_last_10", type=float)
    ap.add_argument("--posting_frequency_per_week", type=float)
    ap.add_argument("--bio", type=str)
    ap.add_argument("--external_website", type=str)
    ap.add_argument("--linktree_domain", type=str)

    ap.add_argument("--note", type=str, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rescore", action="store_true")

    args = ap.parse_args()

    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("PRAGMA foreign_keys = ON;")
        ensure_columns(con)

        row = fetch_profile(con, args.platform, args.profile_url, args.handle)
        if row is None:
            print("Profile not found")
            return 1

        pid = int(row["id"])
        handle = row["handle"] or ""

        # Determine updates
        updates: Dict[str, Any] = {}
        for f in SUPPORTED_FIELDS:
            v = getattr(args, f, None)
            if v is not None:
                updates[f] = v

        metric_updated = any(k in METRIC_FIELDS for k in updates.keys())

        # Always set these when metric updated
        now = utc_now_iso()
        if metric_updated:
            updates["stats_status"] = "self_submitted"
            updates["data_confidence"] = "medium"
        updates["updated_at"] = now

        # identity_status rule: do not auto-change

        # Dry-run: print old -> new
        if args.dry_run:
            changed_fields = list(updates.keys())
            print(f"social_profile_id: {pid}")
            print(f"platform: {args.platform}")
            print(f"handle: {handle}")
            print("changes:")
            for k, nv in updates.items():
                ov = row[k] if k in row.keys() else None
                print(f"- {k}: {ov} -> {nv}")

            snap = {
                "social_profile_id": pid,
                "followers": updates.get("followers", row["followers"]),
                "total_views": updates.get("total_views", row["total_views"]),
                "avg_views_last_10": updates.get("avg_views_last_10", row["avg_views_last_10"]),
                "avg_likes_last_10": updates.get("avg_likes_last_10", row["avg_likes_last_10"]),
                "avg_comments_last_10": updates.get("avg_comments_last_10", row["avg_comments_last_10"]),
                "posting_frequency_per_week": updates.get(
                    "posting_frequency_per_week", row["posting_frequency_per_week"]
                ),
                "timestamp": now,
                "note": args.note,
            }
            print("snapshot_payload:")
            print(json.dumps(snap, sort_keys=True))
            return 0

        # Live update
        if updates:
            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            params = list(updates.values()) + [pid]
            con.execute(f"UPDATE social_profiles SET {set_clause} WHERE id = ?", params)

        # Insert snapshot
        followers = updates.get("followers", row["followers"])
        total_views = updates.get("total_views", row["total_views"])
        avg_views = updates.get("avg_views_last_10", row["avg_views_last_10"])
        avg_likes = updates.get("avg_likes_last_10", row["avg_likes_last_10"])
        avg_comments = updates.get("avg_comments_last_10", row["avg_comments_last_10"])
        pfw = updates.get("posting_frequency_per_week", row["posting_frequency_per_week"])

        cur = con.execute(
            """
            INSERT INTO profile_snapshots(
              social_profile_id, followers, total_views,
              avg_views_last_10, avg_likes_last_10, avg_comments_last_10,
              posting_frequency_per_week, timestamp
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (pid, followers, total_views, avg_views, avg_likes, avg_comments, pfw, now),
        )
        snapshot_id = int(cur.lastrowid)

        # Optional rescore
        new_auth = new_trust = None
        flags: List[str] = []
        if args.rescore:
            # Prefer using score_profiles.py logic if available.
            row2 = con.execute("SELECT * FROM social_profiles WHERE id = ?", (pid,)).fetchone()
            try:
                import score_profiles  # type: ignore

                if args.platform == "youtube":
                    reach, auth, trust, flags = score_profiles.score_youtube(
                        row2["followers"],
                        row2["avg_views_last_10"],
                        row2["posting_frequency_per_week"],
                        (row2["data_confidence"] or "low").strip().lower(),
                    )
                elif args.platform == "instagram":
                    reach, auth, trust, flags = score_profiles.score_instagram(
                        row2["followers"],
                        row2["posts"],
                        row2["avg_likes_last_10"],
                        row2["avg_comments_last_10"],
                        row2["posting_frequency_per_week"],
                        (row2["stats_status"] or "missing_public").strip().lower(),
                        (row2["data_confidence"] or "low").strip().lower(),
                    )
                else:
                    reach, auth, trust, flags = None, None, None, ["scoring_not_implemented"]

                # Remove placeholder if present
                flags = [f for f in flags if f != "scoring_not_implemented"]

                if auth is not None and trust is not None:
                    con.execute(
                        "UPDATE social_profiles SET reach_ratio=?, authenticity_score=?, trust_score=?, trust_flags=?, updated_at=? WHERE id=?",
                        (reach, auth, trust, json.dumps(flags), now, pid),
                    )
                    new_auth, new_trust = auth, trust
                else:
                    con.execute(
                        "UPDATE social_profiles SET trust_flags=?, updated_at=? WHERE id=?",
                        (json.dumps(flags), now, pid),
                    )

            except Exception:
                # fallback: legacy youtube-only inline
                if args.platform == "youtube":
                    reach, auth, trust, flags = compute_youtube_score(row2)
                    con.execute(
                        "UPDATE social_profiles SET reach_ratio=?, authenticity_score=?, trust_score=?, trust_flags=?, updated_at=? WHERE id=?",
                        (reach, auth, trust, json.dumps(flags), now, pid),
                    )
                    new_auth, new_trust = auth, trust
                else:
                    flags = ["scoring_not_implemented"]
                    con.execute(
                        "UPDATE social_profiles SET trust_flags=?, updated_at=? WHERE id=?",
                        (json.dumps(flags), now, pid),
                    )

        con.commit()

        updated_fields = list(updates.keys())
        print(f"social_profile_id: {pid}")
        print(f"platform: {args.platform}")
        print(f"handle: {handle}")
        print(f"updated_fields: {', '.join(updated_fields) if updated_fields else ''}")
        if metric_updated:
            print(f"stats_status: self_submitted")
            print(f"data_confidence: medium")
        else:
            print(f"stats_status: {row['stats_status']}")
            print(f"data_confidence: {row['data_confidence']}")
        print(f"snapshot_inserted_id: {snapshot_id}")
        if args.rescore:
            if new_auth is not None:
                print(f"authenticity_score: {new_auth}")
                print(f"trust_score: {new_trust}")
            print(f"flags: {json.dumps(flags)}")

        return 0

    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
