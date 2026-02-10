#!/usr/bin/env python3
"""Manual linking helper for marketplace creators/profiles.

Stdlib only: sqlite3, argparse, datetime, json, sys

Never auto-merges creators; only reassigns social_profiles.creator_id with explicit commands.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from typing import List, Optional, Tuple

DB_PATH = "/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/marketplace.db"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON;")
    con.row_factory = sqlite3.Row
    return con


def ensure_creator_for_profile(con: sqlite3.Connection, profile_id: int) -> int:
    r = con.execute(
        "SELECT id, creator_id, display_name, handle, platform FROM social_profiles WHERE id=?",
        (profile_id,),
    ).fetchone()
    if r is None:
        raise SystemExit(f"Profile not found: {profile_id}")

    if r["creator_id"] is not None:
        return int(r["creator_id"])

    primary = (r["display_name"] or "").strip() or (r["handle"] or "").strip() or f"{r['platform']}:{r['id']}"
    now = utc_now_iso()
    cur = con.execute("INSERT INTO creators(primary_name, linktree_domain, created_at) VALUES(?,?,?)", (primary, None, now))
    cid = int(cur.lastrowid)
    con.execute("UPDATE social_profiles SET creator_id=? WHERE id=?", (cid, profile_id))
    return cid


def list_profiles(con: sqlite3.Connection, search: Optional[str], limit: int) -> None:
    params: List[object] = []
    where = ""
    if search:
        where = "WHERE (handle LIKE ? OR display_name LIKE ? OR profile_url LIKE ?)"
        s = f"%{search}%"
        params.extend([s, s, s])
    params.append(limit)

    rows = con.execute(
        f"""
        SELECT id, platform, handle, display_name, followers, posts, creator_id,
               identity_status, stats_status, data_confidence
        FROM social_profiles
        {where}
        ORDER BY id ASC
        LIMIT ?
        """,
        params,
    ).fetchall()

    for r in rows:
        print(
            "|".join(
                "" if r[k] is None else str(r[k])
                for k in [
                    "id",
                    "platform",
                    "handle",
                    "display_name",
                    "followers",
                    "posts",
                    "creator_id",
                    "identity_status",
                    "stats_status",
                    "data_confidence",
                ]
            )
        )


def do_link(con: sqlite3.Connection, source_id: int, target_id: int, force: bool) -> None:
    src = con.execute(
        "SELECT id, platform, handle, creator_id, identity_status, display_name FROM social_profiles WHERE id=?",
        (source_id,),
    ).fetchone()
    tgt = con.execute(
        "SELECT id, platform, handle, creator_id, identity_status, display_name FROM social_profiles WHERE id=?",
        (target_id,),
    ).fetchone()

    if src is None:
        raise SystemExit(f"Source profile not found: {source_id}")
    if tgt is None:
        raise SystemExit(f"Target profile not found: {target_id}")

    src_before = src["creator_id"]
    tgt_before = tgt["creator_id"]

    if src_before is not None and not force:
        raise SystemExit(
            "Refusing to overwrite existing creator_id on source profile. Re-run with --force to proceed."
        )

    target_creator_id = ensure_creator_for_profile(con, target_id)

    # Print before
    print(
        f"source_profile_id: {source_id} | before_creator_id: {'' if src_before is None else src_before} | target_creator_id: {target_creator_id}"
    )
    print(
        f"target_profile_id: {target_id} | before_creator_id: {'' if tgt_before is None else tgt_before} | target_creator_id: {target_creator_id}"
    )

    con.execute(
        "UPDATE social_profiles SET creator_id=?, identity_status='linked' WHERE id=?",
        (target_creator_id, source_id),
    )

    # Set target identity_status to linked only if it was standalone
    if (tgt["identity_status"] or "").strip().lower() == "standalone":
        con.execute(
            "UPDATE social_profiles SET identity_status='linked' WHERE id=?",
            (target_id,),
        )

    # Print after
    src_after = con.execute("SELECT creator_id, identity_status FROM social_profiles WHERE id=?", (source_id,)).fetchone()
    tgt_after = con.execute("SELECT creator_id, identity_status FROM social_profiles WHERE id=?", (target_id,)).fetchone()
    print(f"source_after_creator_id: {src_after['creator_id']} | identity_status: {src_after['identity_status']}")
    print(f"target_after_creator_id: {tgt_after['creator_id']} | identity_status: {tgt_after['identity_status']}")


def create_creator_and_link(con: sqlite3.Connection, profile_ids: List[int], primary_name: str) -> None:
    now = utc_now_iso()
    cur = con.execute("INSERT INTO creators(primary_name, linktree_domain, created_at) VALUES(?,?,?)", (primary_name, None, now))
    cid = int(cur.lastrowid)
    print(f"created_creator_id: {cid}")

    for pid in profile_ids:
        r = con.execute("SELECT id, creator_id FROM social_profiles WHERE id=?", (pid,)).fetchone()
        if r is None:
            raise SystemExit(f"Profile not found: {pid}")
        before = r["creator_id"]
        con.execute(
            "UPDATE social_profiles SET creator_id=?, identity_status='linked' WHERE id=?",
            (cid, pid),
        )
        print(f"linked_profile_id: {pid} | before_creator_id: {'' if before is None else before} | after_creator_id: {cid}")


def list_suggestions(con: sqlite3.Connection, status: str, limit: int) -> None:
    rows = con.execute(
        """
        SELECT id, social_profile_id, suggested_creator_id, confidence, reason, status, created_at
        FROM identity_suggestions
        WHERE status = ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (status, limit),
    ).fetchall()

    for r in rows:
        print(
            "|".join(
                "" if r[k] is None else str(r[k])
                for k in [
                    "id",
                    "social_profile_id",
                    "suggested_creator_id",
                    "confidence",
                    "reason",
                    "status",
                    "created_at",
                ]
            )
        )


def accept_suggestion(con: sqlite3.Connection, suggestion_id: int, force: bool) -> None:
    sug = con.execute(
        "SELECT id, social_profile_id, suggested_creator_id, status, reason, confidence FROM identity_suggestions WHERE id=?",
        (suggestion_id,),
    ).fetchone()
    if sug is None:
        raise SystemExit("Suggestion not found")

    if (sug["status"] or "").strip().lower() != "open":
        raise SystemExit("Suggestion is not open")

    spid = int(sug["social_profile_id"])
    suggested_cid = int(sug["suggested_creator_id"])

    prof = con.execute(
        "SELECT id, creator_id, identity_status FROM social_profiles WHERE id=?",
        (spid,),
    ).fetchone()
    if prof is None:
        raise SystemExit("Profile not found")

    before = prof["creator_id"]
    if before is not None and not force:
        raise SystemExit("Refusing to overwrite existing creator_id on profile. Re-run with --force")

    print(
        f"accept_suggestion_id: {suggestion_id} | profile_id: {spid} | before_creator_id: {'' if before is None else before} | after_creator_id: {suggested_cid}"
    )

    con.execute(
        "UPDATE social_profiles SET creator_id=?, identity_status='linked' WHERE id=?",
        (suggested_cid, spid),
    )
    con.execute("UPDATE identity_suggestions SET status='accepted' WHERE id=?", (suggestion_id,))


def reject_suggestion(con: sqlite3.Connection, suggestion_id: int) -> None:
    cur = con.execute("UPDATE identity_suggestions SET status='rejected' WHERE id=?", (suggestion_id,))
    if cur.rowcount == 0:
        raise SystemExit("Suggestion not found")
    print(f"rejected_suggestion_id: {suggestion_id}")


def parse_profile_ids(s: str) -> List[int]:
    out: List[int] = []
    for part in (s or "").split(","):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    if not out:
        raise SystemExit("No profile ids provided")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("list_profiles")
    sp.add_argument("--search", default=None)
    sp.add_argument("--limit", type=int, default=20)

    sp = sub.add_parser("link")
    sp.add_argument("--source-profile-id", type=int, required=True)
    sp.add_argument("--target-profile-id", type=int, required=True)
    sp.add_argument("--force", action="store_true")

    sp = sub.add_parser("create_creator_and_link")
    sp.add_argument("--profile-ids", required=True, help="Comma-separated ids")
    sp.add_argument("--primary-name", required=True)

    sp = sub.add_parser("suggestions")
    sp.add_argument("--status", default="open", choices=["open", "accepted", "rejected"])
    sp.add_argument("--limit", type=int, default=50)

    sp = sub.add_parser("accept_suggestion")
    sp.add_argument("--suggestion-id", type=int, required=True)
    sp.add_argument("--force", action="store_true")

    sp = sub.add_parser("reject_suggestion")
    sp.add_argument("--suggestion-id", type=int, required=True)

    args = ap.parse_args()

    con = connect_db()
    try:
        if args.cmd == "list_profiles":
            list_profiles(con, args.search, args.limit)
        elif args.cmd == "link":
            do_link(con, args.source_profile_id, args.target_profile_id, args.force)
        elif args.cmd == "create_creator_and_link":
            ids = parse_profile_ids(args.profile_ids)
            create_creator_and_link(con, ids, args.primary_name)
        elif args.cmd == "suggestions":
            list_suggestions(con, args.status, args.limit)
        elif args.cmd == "accept_suggestion":
            accept_suggestion(con, args.suggestion_id, args.force)
        elif args.cmd == "reject_suggestion":
            reject_suggestion(con, args.suggestion_id)
        else:
            raise SystemExit("Unknown command")

        con.commit()
        return 0

    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
