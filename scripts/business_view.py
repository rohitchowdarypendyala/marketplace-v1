#!/usr/bin/env python3
"""Read-only Business View for creators (Marketplace V1).

Stdlib only: sqlite3, argparse, json, datetime, textwrap
DB: /home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/marketplace.db

Commands:
  ../../.venv/bin/python business_view.py list
  ../../.venv/bin/python business_view.py show --creator-id 1
  ../../.venv/bin/python business_view.py show --handle <handle> [--platform instagram|youtube|...]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
import textwrap
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = "/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/marketplace.db"


def safe_json_list(s: Any) -> List[Any]:
    if s is None:
        return []
    if isinstance(s, list):
        return s
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else []
    except Exception:
        return []


def safe_json_str(s: Any) -> str:
    if s is None:
        return ""
    return str(s)


def fmt_num(n: Any) -> str:
    if n is None or n == "":
        return ""
    try:
        if isinstance(n, (int, float)):
            if isinstance(n, float) and n.is_integer():
                return str(int(n))
            return str(n)
        return str(n)
    except Exception:
        return ""


def normalize_handle(h: str) -> str:
    h = (h or "").strip()
    if h.startswith("@"):  # DB is inconsistent
        h = h[1:]
    return h.lower()


def connect_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def table_cols(con: sqlite3.Connection, table: str) -> set:
    return {r["name"] for r in con.execute(f"PRAGMA table_info({table});").fetchall()}


def creator_display_name(con: sqlite3.Connection, creator_id: int) -> str:
    ccols = table_cols(con, "creators")
    if "display_name" in ccols:
        r = con.execute("SELECT display_name, primary_name FROM creators WHERE id=?", (creator_id,)).fetchone()
        if r is not None:
            dn = (r["display_name"] or "").strip()
            if dn:
                return dn
            pn = (r["primary_name"] or "").strip()
            if pn:
                return pn
    else:
        r = con.execute("SELECT primary_name FROM creators WHERE id=?", (creator_id,)).fetchone()
        if r is not None:
            pn = (r["primary_name"] or "").strip()
            if pn:
                return pn

    # fallback: first profile display_name or handle
    r = con.execute(
        """
        SELECT display_name, handle
        FROM social_profiles
        WHERE creator_id=?
        ORDER BY id ASC
        LIMIT 1
        """,
        (creator_id,),
    ).fetchone()
    if r:
        dn = (r["display_name"] or "").strip()
        if dn:
            return dn
        return (r["handle"] or "").strip() or str(creator_id)

    return str(creator_id)


def list_creators(con: sqlite3.Connection, limit: int = 200, include_empty: bool = False) -> None:
    sp_cols = table_cols(con, "social_profiles")

    rows = con.execute(
        """
        SELECT id FROM creators
        ORDER BY id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    for r in rows:
        cid = int(r["id"])
        name = creator_display_name(con, cid)

        profs = con.execute(
            """
            SELECT platform, handle, followers, primary_website, contact_emails_json,
                   trust_score, trust_flags
            FROM social_profiles
            WHERE creator_id=?
            ORDER BY id ASC
            """,
            (cid,),
        ).fetchall()

        profiles_count = len(profs)
        if profiles_count == 0 and not include_empty:
            continue

        platforms = sorted({(p["platform"] or "").strip() for p in profs if (p["platform"] or "").strip()})

        total_reach = 0
        for p in profs:
            try:
                if p["followers"] is not None:
                    total_reach += int(p["followers"])
            except Exception:
                pass

        primary_contact = "none"
        for p in profs:
            pw = (p["primary_website"] or "").strip() if "primary_website" in sp_cols else ""
            if pw:
                primary_contact = f"website: {pw}"
                break
        if primary_contact == "none":
            for p in profs:
                emails = safe_json_list(p["contact_emails_json"] if "contact_emails_json" in sp_cols else None)
                if emails:
                    primary_contact = f"email: {str(emails[0])}"
                    break

        trust_vals: List[float] = []
        flags_count = 0
        for p in profs:
            ts = p["trust_score"] if "trust_score" in sp_cols else None
            if ts is not None:
                try:
                    trust_vals.append(float(ts))
                except Exception:
                    pass
            tf = p["trust_flags"] if "trust_flags" in sp_cols else None
            if tf:
                flags_count += len(safe_json_list(tf))

        if trust_vals:
            avg_trust = sum(trust_vals) / max(1, len(trust_vals))
            avg_trust_str = f"{avg_trust:.1f}"
        else:
            avg_trust_str = "insufficient data to compute"

        print(
            "|".join(
                [
                    str(cid),
                    name.replace("|", " "),
                    ",".join(platforms),
                    str(total_reach) if total_reach else "",
                    primary_contact,
                    avg_trust_str,
                    str(flags_count),
                    str(profiles_count),
                ]
            )
        )


def find_creator_by_handle(con: sqlite3.Connection, handle: str, platform: Optional[str]) -> Optional[int]:
    nh = normalize_handle(handle)
    if platform:
        r = con.execute(
            """
            SELECT creator_id FROM social_profiles
            WHERE platform=? AND lower(replace(handle,'@',''))=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (platform, nh),
        ).fetchone()
    else:
        r = con.execute(
            """
            SELECT creator_id FROM social_profiles
            WHERE lower(replace(handle,'@',''))=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (nh,),
        ).fetchone()
    if r and r[0] is not None:
        return int(r[0])
    return None


def show_creator(con: sqlite3.Connection, creator_id: int) -> None:
    sp_cols = table_cols(con, "social_profiles")

    name = creator_display_name(con, creator_id)

    print(f"Creator: {name} (creator_id={creator_id})")
    print("=" * 60)

    profs = con.execute(
        "SELECT * FROM social_profiles WHERE creator_id=? ORDER BY id ASC",
        (creator_id,),
    ).fetchall()

    # Business Summary
    platforms = sorted({(p["platform"] or "").strip() for p in profs if (p["platform"] or "").strip()})
    total_reach = 0
    for p in profs:
        try:
            if p["followers"] is not None:
                total_reach += int(p["followers"])
        except Exception:
            pass

    primary_website = ""
    contact_website = ""
    emails: List[str] = []

    for p in profs:
        if "primary_website" in sp_cols and not primary_website:
            primary_website = (p["primary_website"] or "").strip()
        if "contact_website" in sp_cols and not contact_website:
            contact_website = (p["contact_website"] or "").strip()
        if "contact_emails_json" in sp_cols and not emails:
            emails = [str(x) for x in safe_json_list(p["contact_emails_json"]) if str(x).strip()]

    primary_contact = "none"
    if primary_website:
        primary_contact = f"website: {primary_website}"
    elif emails:
        primary_contact = f"email: {emails[0]}"

    trust_vals: List[float] = []
    worst_trust: Optional[float] = None
    flags: List[str] = []
    if "trust_score" in sp_cols:
        for p in profs:
            ts = p["trust_score"]
            if ts is None:
                continue
            try:
                v = float(ts)
                trust_vals.append(v)
                worst_trust = v if worst_trust is None else min(worst_trust, v)
            except Exception:
                pass
    if "trust_flags" in sp_cols:
        for p in profs:
            flags.extend([str(x) for x in safe_json_list(p["trust_flags"])])
    flags = [f for f in flags if f]
    counts: Dict[str, int] = {}
    for f in flags:
        counts[f] = counts.get(f, 0) + 1
    flags_summary = ", ".join([f"{k}({v})" for k, v in sorted(counts.items())]) if counts else ""

    avg_trust = (sum(trust_vals) / max(1, len(trust_vals))) if trust_vals else None

    # trust explanations
    trust_insufficient = (avg_trust is None) or (worst_trust is None)
    trust_reason = None
    if trust_insufficient:
        trust_reason = "missing engagement metrics (likes/comments/views/posting frequency)"

    print("Business Summary:")
    print(f"- total_reach: {total_reach if total_reach else ''}")
    print(f"- platforms: {','.join(platforms)}")
    print(f"- primary_contact: {primary_contact}")
    print(
        f"- avg_trust: {f'{avg_trust:.1f}' if avg_trust is not None else 'insufficient data to compute'}"
    )
    print(
        f"- worst_trust: {f'{worst_trust:.1f}' if worst_trust is not None else 'insufficient data to compute'}"
    )
    if trust_insufficient and trust_reason:
        print(f"- trust_reason: {trust_reason}")
    print(f"- flags_summary: {flags_summary}")

    print("\nProfiles:")
    for p in profs:
        platform = (p["platform"] or "").strip()
        handle = (p["handle"] or "").strip()
        url = (p["profile_url"] or "").strip()

        followers = p["followers"] if "followers" in sp_cols else None
        posts = p["posts"] if "posts" in sp_cols else None

        print(f"- [{platform}] {handle} | {url}")
        print(f"  followers/subs: {fmt_num(followers)} | posts/videos: {fmt_num(posts)}")

        for k in ("avg_views_last_10", "avg_likes_last_10", "avg_comments_last_10", "posting_frequency_per_week"):
            if k in sp_cols:
                v = p[k]
                if v is not None:
                    print(f"  {k}: {fmt_num(v)}")

        for k in ("stats_status", "data_confidence"):
            if k in sp_cols:
                v = (p[k] or "").strip() if p[k] is not None else ""
                if v:
                    print(f"  {k}: {v}")

        for k in ("authenticity_score", "trust_score", "reach_ratio", "trust_flags"):
            if k in sp_cols:
                v = p[k]
                if v is not None and v != "":
                    if k == "trust_flags":
                        v = json.dumps(safe_json_list(v))
                    print(f"  {k}: {v}")

        if "updated_at" in sp_cols and p["updated_at"]:
            print(f"  updated_at: {p['updated_at']}")
        if "last_fetched_at" in sp_cols and p["last_fetched_at"]:
            print(f"  last_fetched_at: {p['last_fetched_at']}")

    print("\nContact:")
    links: List[Dict[str, Any]] = []

    for p in profs:
        if "external_links_json" in sp_cols and not links:
            links = safe_json_list(p["external_links_json"])  # list of {title,url,type}

    # Always print these (even if blank/empty)
    print(f"primary_website: {primary_website}")
    print(f"contact_website: {contact_website}")
    print(f"contact_emails: {json.dumps(emails)}")

    if links:
        print("external_links:")
        for it in links:
            try:
                typ = (it.get("type") or "").strip()
                title = (it.get("title") or "").strip().replace("\n", " ")
                url = (it.get("url") or "").strip()
                print(f"  - [{typ}] {title} -> {url}")
            except Exception:
                continue

    print("\nNotes:")
    # identity statuses + trust flags summary
    id_statuses = sorted({(p["identity_status"] or "").strip() for p in profs if (p["identity_status"] or "").strip()})
    if id_statuses:
        print(f"identity_statuses: {', '.join(id_statuses)}")

    all_flags: List[str] = []
    if "trust_flags" in sp_cols:
        for p in profs:
            all_flags.extend([str(x) for x in safe_json_list(p["trust_flags"])])
    all_flags = [f for f in all_flags if f]
    if all_flags:
        # summarize counts
        counts: Dict[str, int] = {}
        for f in all_flags:
            counts[f] = counts.get(f, 0) + 1
        summary = ", ".join([f"{k}({v})" for k, v in sorted(counts.items())])
        print(f"trust_flags_summary: {summary}")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("list")
    sp.add_argument("--limit", type=int, default=200)
    sp.add_argument("--include-empty", action="store_true")

    sp = sub.add_parser("show")
    sp.add_argument("--creator-id", type=int, default=None)
    sp.add_argument("--handle", default=None)
    sp.add_argument("--platform", default=None)

    args = ap.parse_args()

    con = connect_db()
    try:
        if args.cmd == "list":
            list_creators(con, limit=args.limit, include_empty=bool(args.include_empty))
            return 0

        if args.cmd == "show":
            cid = args.creator_id
            if cid is None:
                if not args.handle:
                    print("Missing --creator-id or --handle")
                    return 2
                cid = find_creator_by_handle(con, args.handle, args.platform)
                if cid is None:
                    print("Creator not found")
                    return 1
            show_creator(con, int(cid))
            return 0

        print("Unknown command")
        return 2

    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
