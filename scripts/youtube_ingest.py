#!/usr/bin/env python3
"""YouTube public ingestion worker (stdlib-only).

Usage:
  ../.venv/bin/python youtube_ingest.py [--dry-run] [--accurate-metrics] <youtube-channel-url>

Supported inputs:
  - https://www.youtube.com/@handle
  - https://www.youtube.com/channel/<id>
  - https://www.youtube.com/c/<name>
  - https://www.youtube.com/user/<name>

Writes to SQLite:
  /home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/marketplace.db

Notes:
- Public HTML parsing is best-effort; YouTube markup changes frequently.
- Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone, date
from html import unescape
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Iterable
import xml.etree.ElementTree as ET

DB_PATH = Path("/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/marketplace.db")


@dataclass
class VideoStat:
    video_id: str
    views: Optional[int]
    publish_date: Optional[str]  # YYYY-MM-DD


@dataclass
class ChannelMetrics:
    canonical_url: str
    display_name: str
    handle: Optional[str]

    raw_subscribers: Optional[str]
    raw_video_count: Optional[str]
    raw_total_views: Optional[str]

    subscribers: Optional[int]
    video_count: Optional[int]
    total_views: Optional[int]

    last10: List[VideoStat]
    avg_views_last_10: Optional[float]
    posting_frequency_per_week: Optional[float]
    external_links: List[str]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def norm_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise SystemExit("Missing URL")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url.lstrip("/")
    return url


def canonicalize_channel_url(input_url: str) -> Tuple[str, Optional[str]]:
    u = norm_url(input_url)
    parsed = urllib.parse.urlsplit(u)
    host = (parsed.netloc or "").lower()
    if host.endswith("m.youtube.com"):
        host = "www.youtube.com"
    if host.endswith("youtu.be"):
        raise SystemExit("Please provide a YouTube channel URL, not a youtu.be video URL")

    path = re.sub(r"/+$", "", parsed.path or "")

    handle = None
    m = re.match(r"^/@([^/]+)$", path)
    if m:
        handle = "@" + m.group(1)
        return f"https://www.youtube.com/{handle}", handle

    m = re.match(r"^/channel/([^/]+)$", path)
    if m:
        return f"https://www.youtube.com/channel/{m.group(1)}", None

    if path.startswith("/c/") or path.startswith("/user/"):
        return f"https://www.youtube.com{path}", None

    m = re.match(r"^/(@[^/]+)(?:/.*)?$", path)
    if m:
        handle = m.group(1)
        return f"https://www.youtube.com/{handle}", handle

    return f"https://www.youtube.com{path}", None


def http_get(url: str, timeout: float = 20.0) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return data.decode("utf-8", errors="replace")


def _extract_balanced_json_object(s: str, start: int) -> Optional[str]:
    if start < 0 or start >= len(s) or s[start] != "{":
        return None
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
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def extract_yt_initial_data(html: str) -> Optional[dict]:
    m = re.search(r"var\s+ytInitialData\s*=", html)
    if m:
        brace = html.find("{", m.end())
        blob = _extract_balanced_json_object(html, brace)
        if blob:
            return json.loads(blob)

    m = re.search(r"\"ytInitialData\"\s*:\s*\{", html)
    if m:
        brace = html.find("{", m.end() - 1)
        blob = _extract_balanced_json_object(html, brace)
        if blob:
            return json.loads(blob)
    return None


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


def safe_get(obj, path: List):
    cur = obj
    for key in path:
        if cur is None:
            return None
        if isinstance(key, int):
            if isinstance(cur, list) and 0 <= key < len(cur):
                cur = cur[key]
            else:
                return None
        else:
            if isinstance(cur, dict):
                cur = cur.get(key)
            else:
                return None
    return cur


def _deep_iter_strings(obj) -> Iterable[str]:
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, str):
            yield cur
        elif isinstance(cur, dict):
            for v in cur.values():
                stack.append(v)
        elif isinstance(cur, list):
            for v in cur:
                stack.append(v)


def _pick_largest_match_string(obj, pattern: re.Pattern) -> Optional[str]:
    best = None
    best_val = -1
    for s in _deep_iter_strings(obj):
        for m in pattern.finditer(s):
            raw = m.group(0)
            val = parse_metric_int(raw)
            if val is not None and val > best_val:
                best_val = val
                best = raw
    return best


def extract_display_name(html: str, data: Optional[dict]) -> str:
    m = re.search(r"<meta\s+property=\"og:title\"\s+content=\"([^\"]+)\"", html, re.I)
    if m:
        return unescape(m.group(1)).strip()
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    if m:
        title = unescape(m.group(1)).strip()
        title = re.sub(r"\s*-\s*YouTube\s*$", "", title)
        return title.strip()
    return "(Unknown)"


def extract_video_count_from_initial_data(data: dict) -> Tuple[Optional[str], Optional[str]]:
    # A)
    a = safe_get(data, ["header", "c4TabbedHeaderRenderer", "videosCountText", "runs", 0, "text"])
    if isinstance(a, str) and "video" in a.lower():
        return a.strip(), "A"

    # B)
    broot = safe_get(
        data,
        [
            "header",
            "pageHeaderRenderer",
            "content",
            "pageHeaderViewModel",
            "metadata",
            "contentMetadataViewModel",
        ],
    )
    pat = re.compile(r"\b[0-9,.]+\s+videos\b", re.I)
    if broot is not None:
        cand = _pick_largest_match_string(broot, pat)
        if cand:
            return cand.strip(), "B"

    # C) whole JSON, choose largest numeric to avoid shelf counts
    cand = _pick_largest_match_string(data, pat)
    if cand:
        return cand.strip(), "C"

    return None, None


def extract_subscribers_from_initial_data(data: dict) -> Tuple[Optional[str], Optional[str]]:
    # A)
    a = safe_get(data, ["header", "c4TabbedHeaderRenderer", "subscriberCountText", "simpleText"])
    if isinstance(a, str) and "subscriber" in a.lower():
        return a.strip(), "A"

    # B)
    b = safe_get(data, ["header", "c4TabbedHeaderRenderer", "subscriberCountText", "runs", 0, "text"])
    if isinstance(b, str) and "subscriber" in b.lower():
        return b.strip(), "B"

    # C) recursive: first match, but pick largest numeric
    pat = re.compile(r"\b[0-9,.]+\s*[KMB]?\s+subscribers\b", re.I)
    cand = _pick_largest_match_string(data, pat)
    if cand:
        return cand.strip(), "C"

    return None, None


def extract_total_views_from_initial_data(data: dict) -> Tuple[Optional[str], Optional[str]]:
    # Only set if explicit channel views text exists in header metadata.
    root = safe_get(
        data,
        [
            "header",
            "pageHeaderRenderer",
            "content",
            "pageHeaderViewModel",
            "metadata",
            "contentMetadataViewModel",
        ],
    )
    if root is None:
        return None, None

    pat = re.compile(r"\b[0-9,.]+\s*[KMB]?\s+views\b", re.I)
    cand = _pick_largest_match_string(root, pat)
    if cand:
        return cand.strip(), "header_metadata"
    return None, None


def extract_external_links(html: str) -> List[str]:
    hrefs = re.findall(r"href=\"(https?://[^\"]+)\"", html, re.I)
    links = []
    for h in hrefs:
        u = unescape(h)
        u = urllib.parse.unquote(u)
        if not u.startswith("http"):
            continue
        host = (urllib.parse.urlsplit(u).netloc or "").lower()
        if any(host.endswith(x) for x in ("youtube.com", "google.com", "youtu.be", "ytimg.com", "googleusercontent.com")):
            continue
        links.append(u)
    out = []
    seen = set()
    for u in links:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def linktree_domain_from_url(url: str) -> Optional[str]:
    try:
        host = (urllib.parse.urlsplit(url).netloc or "").lower()
    except Exception:
        return None
    if host.endswith("linktr.ee") or host.endswith("linktree.com"):
        return host
    return None


def _deep_find_first(obj, key: str) -> Optional[str]:
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if key in cur and isinstance(cur[key], str):
                return cur[key]
            for v in cur.values():
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def extract_channel_id(data: Optional[dict], html: str, canonical_url: str) -> Optional[str]:
    """Extract channel_id (UC...) from URL, ytInitialData, or raw HTML."""
    m = re.match(r"^https?://www\.youtube\.com/channel/(UC[0-9A-Za-z_-]{20,})", canonical_url)
    if m:
        return m.group(1)

    # Try ytInitialData first
    if data:
        # Some pages include channelId fields in multiple places; pick the first valid UC...
        for s in _deep_iter_strings(data):
            if isinstance(s, str) and re.match(r"^UC[0-9A-Za-z_-]{20,}$", s):
                return s
        cid = _deep_find_first(data, "channelId")
        if isinstance(cid, str) and re.match(r"^UC[0-9A-Za-z_-]{20,}$", cid):
            return cid

    # Regex scan HTML for "channelId":"UC..."
    ids = re.findall(r"\"channelId\"\s*:\s*\"(UC[0-9A-Za-z_-]{20,})\"", html)
    for cid in ids:
        if re.match(r"^UC[0-9A-Za-z_-]{20,}$", cid):
            return cid

    # Broader fallback: any UC... token in HTML
    ids = re.findall(r"\b(UC[0-9A-Za-z_-]{20,})\b", html)
    for cid in ids:
        if re.match(r"^UC[0-9A-Za-z_-]{20,}$", cid):
            return cid

    return None


def fetch_rss_video_ids(channel_id: str, limit: int = 10) -> List[Tuple[str, Optional[str]]]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={urllib.parse.quote(channel_id)}"
    xml_text = http_get(url)
    root = ET.fromstring(xml_text)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
    }
    out = []
    for entry in root.findall("atom:entry", ns):
        vid_el = entry.find("yt:videoId", ns)
        pub_el = entry.find("atom:published", ns)
        if vid_el is None:
            continue
        vid = (vid_el.text or "").strip()
        pub = (pub_el.text or "").strip() if pub_el is not None else None
        pub_date = pub[:10] if pub and len(pub) >= 10 else None
        out.append((vid, pub_date))
        if len(out) >= limit:
            break
    return out


def extract_yt_initial_player_response(html: str) -> Optional[dict]:
    # Pattern: var ytInitialPlayerResponse = {...};
    m = re.search(r"var\s+ytInitialPlayerResponse\s*=", html)
    if not m:
        return None
    brace = html.find("{", m.end())
    blob = _extract_balanced_json_object(html, brace)
    if not blob:
        return None
    return json.loads(blob)


def fetch_video_stats(video_id: str) -> VideoStat:
    html = http_get(f"https://www.youtube.com/watch?v={urllib.parse.quote(video_id)}")
    pr = extract_yt_initial_player_response(html) or {}
    view_count = safe_get(pr, ["videoDetails", "viewCount"])
    views = parse_metric_int(view_count) if view_count is not None else None
    pub = safe_get(pr, ["microformat", "playerMicroformatRenderer", "publishDate"]) or safe_get(
        pr, ["microformat", "playerMicroformatRenderer", "uploadDate"]
    )
    pub_date = pub if isinstance(pub, str) else None
    return VideoStat(video_id=video_id, views=views, publish_date=pub_date)


def compute_avg_views(last10: List[VideoStat]) -> Optional[float]:
    vals = [v.views for v in last10 if v.views is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def compute_posting_frequency_per_week(last10: List[VideoStat]) -> Tuple[Optional[float], Optional[str], Optional[str], Optional[int], int]:
    """Return (freq_per_week, oldest_published, newest_published, date_span_days, N_used)."""
    dates: List[date] = []
    for v in last10:
        if v.publish_date and re.match(r"^\d{4}-\d{2}-\d{2}$", v.publish_date):
            y, m, d = map(int, v.publish_date.split("-"))
            dates.append(date(y, m, d))

    n = len(dates)
    if n < 2:
        return None, None, None, None, n

    newest = max(dates)
    oldest = min(dates)
    span_days = (newest - oldest).days
    weeks = span_days / 7.0 if span_days is not None else 0.0

    if weeks > 0:
        # (N-1) intervals over the date span
        freq = (n - 1) / weeks
    else:
        freq = None

    return freq, oldest.isoformat(), newest.isoformat(), span_days, n


def parse_channel_metrics(channel_url: str, accurate: bool) -> Tuple[ChannelMetrics, Dict[str, object]]:
    canonical, handle = canonicalize_channel_url(channel_url)
    html = http_get(canonical)
    data = extract_yt_initial_data(html)
    yt_found = data is not None

    display_name = extract_display_name(html, data)

    # subscribers (ytInitialData-first)
    raw_subs = None
    subs = None
    subs_path = None
    if data:
        raw_subs, subs_path = extract_subscribers_from_initial_data(data)
        subs = parse_metric_int(raw_subs) if raw_subs else None

    # video count (ytInitialData-first)
    raw_vids = None
    vids = None
    vids_path = None
    if data:
        raw_vids, vids_path = extract_video_count_from_initial_data(data)
        vids = parse_metric_int(raw_vids) if raw_vids else None

    # total views (ytInitialData-only; else None)
    raw_views = None
    views = None
    views_path = None
    if data:
        raw_views, views_path = extract_total_views_from_initial_data(data)
        views = parse_metric_int(raw_views) if raw_views else None

    external_links = extract_external_links(html)

    last10: List[VideoStat] = []
    avg_views = None
    freq = None
    last10_ids_found = 0

    channel_id_found: Optional[str] = None
    rss_entries_found = 0
    sample_video_ids: List[str] = []
    views_parsed_count = 0

    if accurate:
        channel_id_found = extract_channel_id(data, html, canonical)
        if channel_id_found:
            rss = fetch_rss_video_ids(channel_id_found, limit=10)
            rss_entries_found = len(rss)
            last10_ids_found = rss_entries_found
            sample_video_ids = [vid for (vid, _d) in rss[:3]]
            for vid, pub_date in rss:
                vs = fetch_video_stats(vid)
                if vs.views is not None:
                    views_parsed_count += 1
                # Prefer RSS publish_date (stable) if missing or not in YYYY-MM-DD
                if pub_date is not None:
                    if (vs.publish_date is None) or (not re.match(r"^\d{4}-\d{2}-\d{2}$", str(vs.publish_date))):
                        vs.publish_date = pub_date
                last10.append(vs)
            avg_views = compute_avg_views(last10)
            freq, oldest_pub, newest_pub, span_days, n_used = compute_posting_frequency_per_week(last10)

    metrics = ChannelMetrics(
        canonical_url=canonical,
        display_name=display_name,
        handle=handle,
        raw_subscribers=raw_subs,
        raw_video_count=raw_vids,
        raw_total_views=raw_views,
        subscribers=subs,
        video_count=vids,
        total_views=views,
        last10=last10,
        avg_views_last_10=avg_views,
        posting_frequency_per_week=freq,
        external_links=external_links,
    )

    dbg = {
        "ytInitialData_found": yt_found,
        "subscribers_path_used": subs_path,
        "total_views_path_used": views_path,
        "video_count_path_used": vids_path,
        "accurate_metrics_enabled": accurate,
        "last_10_video_ids_found": last10_ids_found,
        "channel_id_found": channel_id_found,
        "rss_entries_found": rss_entries_found,
        "sample_video_ids": sample_video_ids,
        "views_parsed_count": views_parsed_count,
        "oldest_published": locals().get('oldest_pub'),
        "newest_published": locals().get('newest_pub'),
        "date_span_days": locals().get('span_days'),
        "N_videos_used_for_frequency": locals().get('n_used'),
    }
    return metrics, dbg


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


def ensure_profile_url_unique(con: sqlite3.Connection, url: str) -> bool:
    row = con.execute("SELECT id FROM social_profiles WHERE profile_url = ?", (url,)).fetchone()
    return row is None


def insert_creator(con: sqlite3.Connection, primary_name: str) -> int:
    now = utc_now_iso()
    cur = con.execute(
        "INSERT INTO creators(primary_name, linktree_domain, created_at) VALUES(?,?,?)",
        (primary_name, None, now),
    )
    return int(cur.lastrowid)


def insert_social_profile(con: sqlite3.Connection, creator_id: int, m: ChannelMetrics, accurate_metrics: bool) -> int:
    now = utc_now_iso()

    stats_status = "ok" if (m.subscribers is not None and m.video_count is not None) else "missing_public"
    data_conf = "medium" if accurate_metrics else "low"

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
          ?, 'youtube', ?, ?, ?, NULL,
          ?, ?, NULL,
          ?, NULL, ?, ?,
          ?, NULL, NULL,
          ?,
          ?, 'standalone', 'discovered',
          ?,
          ?, ?
        )
        """,
        (
            creator_id,
            m.canonical_url,
            m.handle,
            m.display_name,
            (m.external_links[0] if m.external_links else None),
            (linktree_domain_from_url(m.external_links[0]) if m.external_links else None),
            m.subscribers,
            m.video_count,
            m.total_views,
            m.avg_views_last_10,
            m.posting_frequency_per_week,
            data_conf,
            stats_status,
            now,
            now,
        ),
    )
    return int(cur.lastrowid)


def insert_snapshot(con: sqlite3.Connection, social_profile_id: int, m: ChannelMetrics) -> int:
    now = utc_now_iso()
    cur = con.execute(
        """
        INSERT INTO profile_snapshots(
          social_profile_id, followers, total_views,
          avg_views_last_10, avg_likes_last_10, avg_comments_last_10,
          posting_frequency_per_week, timestamp
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            social_profile_id,
            m.subscribers,
            m.total_views,
            m.avg_views_last_10,
            None,
            None,
            m.posting_frequency_per_week,
            now,
        ),
    )
    return int(cur.lastrowid)


def maybe_identity_suggestions(con: sqlite3.Connection, social_profile_id: int, m: ChannelMetrics) -> int:
    domains = []
    for u in m.external_links:
        d = linktree_domain_from_url(u)
        if d:
            domains.append(d)
    domains = list(dict.fromkeys(domains))
    if not domains:
        return 0

    suggestions = 0
    for dmn in domains:
        rows = con.execute(
            "SELECT DISTINCT creator_id FROM social_profiles WHERE linktree_domain = ? AND creator_id IS NOT NULL",
            (dmn,),
        ).fetchall()
        for (creator_id,) in rows:
            con.execute(
                """
                INSERT INTO identity_suggestions(
                  social_profile_id, suggested_creator_id, reason, confidence, status, created_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    social_profile_id,
                    int(creator_id),
                    f"Matching linktree_domain={dmn} from external links",
                    0.7,
                    "open",
                    utc_now_iso(),
                ),
            )
            suggestions += 1
    return suggestions


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--accurate-metrics", action="store_true")
    ap.add_argument("channel_url")
    args = ap.parse_args()

    m, dbg = parse_channel_metrics(args.channel_url, accurate=args.accurate_metrics)

    print(f"display_name: {m.display_name}")
    print(f"handle: {m.handle or ''}")
    print(f"canonical_url: {m.canonical_url}")

    if args.dry_run:
        # Required debug lines
        print(f"raw_subscribers: {m.raw_subscribers if m.raw_subscribers is not None else ''}")
        print(f"parsed_subscribers: {m.subscribers if m.subscribers is not None else ''}")
        print(f"source_path_subscribers: {dbg.get('subscribers_path_used') or ''}")

        print(f"raw_total_views: {m.raw_total_views if m.raw_total_views is not None else ''}")
        print(f"parsed_total_views: {m.total_views if m.total_views is not None else ''}")
        print(f"source_path_total_views: {dbg.get('total_views_path_used') or ''}")

        print(f"ytInitialData_found: {str(bool(dbg.get('ytInitialData_found')))}")
        print(f"video_count_path_used: {dbg.get('video_count_path_used') or ''}")
        print(f"raw_video_count: {m.raw_video_count if m.raw_video_count is not None else ''}")
        print(f"parsed_video_count: {m.video_count if m.video_count is not None else ''}")

        print(f"accurate_metrics_enabled: {str(bool(dbg.get('accurate_metrics_enabled')))}")
        print(f"channel_id_found: {dbg.get('channel_id_found') or ''}")
        print(f"rss_entries_found: {dbg.get('rss_entries_found') or 0}")
        sv = dbg.get('sample_video_ids') or []
        if isinstance(sv, list):
            print(f"sample_video_ids: {', '.join(sv[:3])}")
        else:
            print("sample_video_ids: ")
        print(f"views_parsed_count: {dbg.get('views_parsed_count') or 0}")
        print(f"last_10_video_ids_found: {dbg.get('last_10_video_ids_found') or 0}")
        print(f"avg_views_last_10: {m.avg_views_last_10 if m.avg_views_last_10 is not None else ''}")
        print(f"oldest_published: {dbg.get('oldest_published') or ''}")
        print(f"newest_published: {dbg.get('newest_published') or ''}")
        v = dbg.get('date_span_days')
        print(f"date_span_days: {v if v is not None else ''}")
        v2 = dbg.get('N_videos_used_for_frequency')
        print(f"N_videos_used_for_frequency: {v2 if v2 is not None else ''}")
        print(f"posting_frequency_per_week: {m.posting_frequency_per_week if m.posting_frequency_per_week is not None else ''}")

        # Extra debug: last 2 videos (only in --dry-run --accurate-metrics)
        if args.accurate_metrics:
            vids = [v for v in (m.last10 or []) if v.video_id]
            vids.sort(key=lambda v: (v.publish_date or ""), reverse=True)
            print("Last 2 videos:")
            for i, v in enumerate(vids[:2], start=1):
                views_disp = v.views if v.views is not None else ""
                pub_disp = v.publish_date if v.publish_date is not None else ""
                print(f"{i}) {v.video_id} | published: {pub_disp} | views: {views_disp}")

        return

    # Live write path
    con = connect_db()
    try:
        if not ensure_profile_url_unique(con, m.canonical_url):
            print("Profile URL already exists; exiting")
            return

        creator_id = insert_creator(con, m.display_name)
        social_profile_id = insert_social_profile(con, creator_id, m, accurate_metrics=bool(args.accurate_metrics))
        snapshot_id = insert_snapshot(con, social_profile_id, m)
        suggestions = maybe_identity_suggestions(con, social_profile_id, m)
        con.commit()

        print(f"creator_id: {creator_id}")
        print(f"social_profile_id: {social_profile_id}")
        print(f"subscribers: {m.subscribers if m.subscribers is not None else ''}")
        print(f"avg_views_last_10: {m.avg_views_last_10 if m.avg_views_last_10 is not None else ''}")
        print(f"posting_frequency_per_week: {m.posting_frequency_per_week if m.posting_frequency_per_week is not None else ''}")
        print(f"snapshot inserted: {snapshot_id}")
        print(f"identity suggestions count: {suggestions}")

    finally:
        con.close()


if __name__ == "__main__":
    main()
