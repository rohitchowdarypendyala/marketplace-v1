#!/usr/bin/env python3
"""Instagram public ingestion worker (stdlib-only, no OAuth).

Usage:
  ../.venv/bin/python instagram_ingest.py [--dry-run] https://www.instagram.com/<handle>/

Stdlib only: urllib, sqlite3, re, json, datetime, html
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List, Iterable

DB_PATH = Path("/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/marketplace.db")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_metric_int(text: str) -> Optional[int]:
    if text is None:
        return None
    t = unescape(str(text)).strip()
    if not t:
        return None
    t = t.replace("\u00a0", "").replace(" ", "")
    m = re.search(r"(\d+(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)([KMB])?", t, re.I)
    if not m:
        return None
    num_str = m.group(1).replace(",", "")
    suf = (m.group(2) or "").upper()
    try:
        num = float(num_str)
    except Exception:
        return None
    mult = 1
    if suf == "K":
        mult = 1_000
    elif suf == "M":
        mult = 1_000_000
    elif suf == "B":
        mult = 1_000_000_000
    return int(num * mult)


def normalize_url(url: str) -> Tuple[str, str]:
    url = url.strip().strip('"').strip("'")
    if not url:
        raise SystemExit("Missing URL")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url.lstrip("/")

    parsed = urllib.parse.urlsplit(url)
    if "instagram.com" not in (parsed.netloc or ""):
        raise SystemExit("Please provide an instagram.com profile URL")

    path = parsed.path.strip()
    # expect /handle/ optionally
    parts = [p for p in path.split("/") if p]
    if not parts:
        raise SystemExit("Could not extract handle from URL")
    handle = parts[0]
    handle = handle.lstrip("@")

    canonical = f"https://www.instagram.com/{handle}/"
    return canonical, handle


def http_get(url: str, timeout: float = 20.0) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return data.decode("utf-8", errors="replace")


def _extract_balanced_json_object(s: str, start: int) -> Optional[str]:
    if start < 0 or start >= len(s) or s[start] not in "{[":
        return None
    opener = s[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def extract_json_blobs(html: str) -> List[dict]:
    blobs: List[dict] = []

    # window._sharedData = {...};
    m = re.search(r"window\._sharedData\s*=", html)
    if m:
        brace = html.find("{", m.end())
        blob = _extract_balanced_json_object(html, brace)
        if blob:
            try:
                blobs.append(json.loads(blob))
            except Exception:
                pass

    # __NEXT_DATA__ script tag
    m = re.search(r"<script[^>]+id=\"__NEXT_DATA__\"[^>]*>(.*?)</script>", html, re.S | re.I)
    if m:
        txt = m.group(1).strip()
        try:
            blobs.append(json.loads(txt))
        except Exception:
            pass

    # additionalDataLoaded('feed', {...}); style
    for m in re.finditer(r"additionalDataLoaded\([^,]+,\s*\{", html):
        brace = html.find("{", m.end() - 1)
        blob = _extract_balanced_json_object(html, brace)
        if blob:
            try:
                blobs.append(json.loads(blob))
            except Exception:
                pass

    return blobs


def deep_find(obj: Any, key: str) -> Optional[Any]:
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if key in cur:
                return cur[key]
            for v in cur.values():
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def parse_from_json(blobs: List[dict], handle: str) -> Dict[str, Any]:
    # Try to find a user object with username == handle
    for b in blobs:
        user = deep_find(b, "user")
        if isinstance(user, dict):
            uname = user.get("username")
            if uname and uname.lower() == handle.lower():
                return user

    # fallback: look for any username
    for b in blobs:
        user = deep_find(b, "user")
        if isinstance(user, dict) and user.get("username"):
            return user

    return {}


def linktree_domain(url: str) -> Optional[str]:
    if not url:
        return None
    try:
        host = (urllib.parse.urlsplit(url).netloc or "").lower()
    except Exception:
        return None
    if any(host.endswith(d) for d in ("linktr.ee", "linkin.bio", "beacons.ai")):
        return host
    return None


def extract_meta_description(html: str) -> Tuple[bool, Optional[str]]:
    m = re.search(r"<meta\s+name=\"description\"\s+content=\"([^\"]+)\"", html, re.I)
    if not m:
        return False, None
    return True, unescape(m.group(1)).strip()


def parse_counts_from_meta_description(desc: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    # Typical: "X Followers, Y Following, Z Posts - ..."
    followers = following = posts = None
    if not desc:
        return None, None, None

    m = re.search(r"([0-9][0-9.,]*\s*[KMB]?)\s+Followers", desc, re.I)
    if m:
        followers = parse_metric_int(m.group(1))
    m = re.search(r"([0-9][0-9.,]*\s*[KMB]?)\s+Following", desc, re.I)
    if m:
        following = parse_metric_int(m.group(1))
    m = re.search(r"([0-9][0-9.,]*\s*[KMB]?)\s+Posts", desc, re.I)
    if m:
        posts = parse_metric_int(m.group(1))

    return followers, following, posts


def fallback_counts_from_html(html: str) -> Tuple[Optional[int], Optional[int]]:
    # Very rough: parse "X posts" and "Y followers" visible text
    posts = None
    followers = None
    m = re.search(r"([0-9][0-9.,]*\s*[KMB]?)\s+posts", html, re.I)
    if m:
        posts = parse_metric_int(m.group(1))
    m = re.search(r"([0-9][0-9.,]*\s*[KMB]?)\s+followers", html, re.I)
    if m:
        followers = parse_metric_int(m.group(1))
    return posts, followers


def ensure_stats_status_column(con: sqlite3.Connection) -> None:
    cols = {row[1] for row in con.execute("PRAGMA table_info(social_profiles);").fetchall()}
    if "stats_status" not in cols:
        con.execute(
            "ALTER TABLE social_profiles ADD COLUMN stats_status TEXT NOT NULL DEFAULT 'missing_public' CHECK(stats_status IN ('ok','missing_public','self_submitted','oauth_verified'));"
        )


def connect_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON;")
    ensure_stats_status_column(con)
    return con


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("url")
    args = ap.parse_args()

    canonical, handle = normalize_url(args.url)
    html = http_get(canonical)

    blobs = extract_json_blobs(html)
    user = parse_from_json(blobs, handle)

    display_name = (user.get("full_name") if user else None) or handle
    bio = (user.get("biography") if user else None)
    ext = (user.get("external_url") if user else None)

    followers = None
    following = None
    posts = None

    # counts from JSON when present
    if user:
        followers = deep_find(user, "edge_followed_by")
        if isinstance(followers, dict) and "count" in followers:
            followers = followers.get("count")
        following = deep_find(user, "edge_follow")
        if isinstance(following, dict) and "count" in following:
            following = following.get("count")
        posts = deep_find(user, "edge_owner_to_timeline_media")
        if isinstance(posts, dict) and "count" in posts:
            posts = posts.get("count")

    meta_found, meta_desc = extract_meta_description(html)

    # meta-description fallback for counts
    if (followers is None or following is None or posts is None) and meta_desc:
        mf, mfo, mp = parse_counts_from_meta_description(meta_desc)
        followers = followers if followers is not None else mf
        following = following if following is not None else mfo
        posts = posts if posts is not None else mp

    # fallback regex if needed
    if posts is None or followers is None:
        fb_posts, fb_followers = fallback_counts_from_html(html)
        posts = posts if posts is not None else fb_posts
        followers = followers if followers is not None else fb_followers

    followers_i = parse_metric_int(followers) if not isinstance(followers, int) else followers
    following_i = parse_metric_int(following) if not isinstance(following, int) else following
    posts_i = parse_metric_int(posts) if not isinstance(posts, int) else posts

    ltd = linktree_domain(ext or "")

    stats_status = "ok" if (followers_i is not None or posts_i is not None or following_i is not None) else "missing_public"
    identity_status = "needs_review" if stats_status == "missing_public" else "standalone"
    data_confidence = "low"  # public scrape is low confidence by default

    # Print console output always
    print(f"display_name: {display_name}")
    print(f"handle: @{handle}")
    print(f"canonical_url: {canonical}")
    print(f"followers: {followers_i if followers_i is not None else ''}")
    print(f"following: {following_i if following_i is not None else ''}")
    print(f"posts: {posts_i if posts_i is not None else ''}")
    print(f"external_website: {ext or ''}")
    print(f"linktree_domain: {ltd or ''}")
    print(f"stats_status: {stats_status}")

    if stats_status == "missing_public":
        print("WARNING: public counts not available; marked needs_review and low confidence")

    now = utc_now_iso()

    if args.dry_run:
        print(f"meta_description_found: {str(bool(meta_found))}")
        raw_md = (meta_desc or "")
        print(f"raw_meta_description: {raw_md[:120]}")
        print("creator_id: dry-run")
        print("social_profile_id: dry-run")
        print("identity_suggestions_created: 0")
        return

    con = connect_db()
    try:
        # Unique check
        exists = con.execute("SELECT id FROM social_profiles WHERE profile_url = ?", (canonical,)).fetchone()
        if exists:
            print("Profile already exists")
            return

        # Always create NEW creator
        cur = con.execute(
            "INSERT INTO creators(primary_name, linktree_domain, created_at) VALUES(?,?,?)",
            (display_name, None, now),
        )
        creator_id = int(cur.lastrowid)

        cur = con.execute(
            """
            INSERT INTO social_profiles(
              creator_id, platform, profile_url, handle, display_name, bio,
              external_website, linktree_domain, profile_image_hash,
              followers, following, posts, total_views,
              avg_views_last_10, avg_likes_last_10, avg_comments_last_10,
              posting_frequency_per_week,
              data_confidence, identity_status, source,
              stats_status,
              created_at, last_fetched_at
            ) VALUES(
              ?, 'instagram', ?, ?, ?, ?,
              ?, ?, NULL,
              ?, ?, ?, NULL,
              NULL, NULL, NULL,
              NULL,
              ?, ?, 'discovered',
              ?,
              ?, ?
            )
            """,
            (
                creator_id,
                canonical,
                handle,
                display_name,
                bio,
                ext,
                ltd,
                followers_i,
                following_i,
                posts_i,
                data_confidence,
                identity_status,
                stats_status,
                now,
                now,
            ),
        )
        social_profile_id = int(cur.lastrowid)

        # Snapshot
        cur = con.execute(
            """
            INSERT INTO profile_snapshots(
              social_profile_id, followers, total_views,
              avg_views_last_10, avg_likes_last_10, avg_comments_last_10,
              posting_frequency_per_week, timestamp
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (social_profile_id, followers_i, None, None, None, None, None, now),
        )

        # Identity suggestions
        sugg = 0
        if ltd or ext:
            # match either linktree_domain OR external_website
            rows = []
            if ltd:
                rows.extend(
                    con.execute(
                        "SELECT DISTINCT creator_id FROM social_profiles WHERE linktree_domain = ? AND creator_id IS NOT NULL",
                        (ltd,),
                    ).fetchall()
                )
            if ext:
                rows.extend(
                    con.execute(
                        "SELECT DISTINCT creator_id FROM social_profiles WHERE external_website = ? AND creator_id IS NOT NULL",
                        (ext,),
                    ).fetchall()
                )
            seen = set()
            for (cid,) in rows:
                if cid in seen:
                    continue
                seen.add(cid)
                con.execute(
                    """
                    INSERT INTO identity_suggestions(
                      social_profile_id, suggested_creator_id, reason, confidence, status, created_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (social_profile_id, int(cid), "shared external link", 0.7, "open", now),
                )
                sugg += 1

        con.commit()

        print(f"creator_id: {creator_id}")
        print(f"social_profile_id: {social_profile_id}")
        print(f"identity_suggestions_created: {sugg}")

    finally:
        con.close()


if __name__ == "__main__":
    main()
