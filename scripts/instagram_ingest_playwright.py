#!/usr/bin/env python3
"""Instagram ingestion via Playwright using a persistent logged-in session (no OAuth).

CLI:
  ../.venv/bin/python instagram_ingest_playwright.py --login
  ../.venv/bin/python instagram_ingest_playwright.py [--dry-run] https://www.instagram.com/<handle>/
  ../.venv/bin/python instagram_ingest_playwright.py --profile-url https://www.instagram.com/<handle>/ [--dry-run]
  ../.venv/bin/python instagram_ingest_playwright.py --file /path/to/ig_urls.txt [--dry-run]

Session storage:
  /home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/.pw/ig_profile

DB:
  /home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/marketplace.db

Notes:
- Logged-in session must be created once with --login.
- Rate limit: sleeps 3–6 seconds random between batch profiles.

Stdlib + Playwright.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sqlite3
import time
import urllib.parse
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

DB_PATH = Path("/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/marketplace.db")
PW_PROFILE_DIR = Path("/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/.pw/ig_profile")
DEBUG_DIR = Path("/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/.pw/debug")

def normalize_text(s: Any) -> str:
    if s is None:
        return ""
    t = str(s)
    t = unicodedata.normalize("NFKC", t)
    # remove zero-width chars
    t = re.sub(r"[\u200B-\u200D\uFEFF]", "", t)
    t = t.replace("\u00a0", " ")
    return t.strip()


EMAIL_RE = re.compile(r"(?i)([a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,})")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_metric_int(text: Any) -> Optional[int]:
    if text is None:
        return None
    t = str(text).strip()
    if not t:
        return None
    # keep digits, separators and suffix
    t = t.replace("\u00a0", " ")
    t = re.sub(r"[^0-9.,KMBkmb]", "", t)
    if not t:
        return None
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
    url = (url or "").strip().strip('"').strip("'")
    if not url:
        raise ValueError("Missing URL")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url.lstrip("/")
    parsed = urllib.parse.urlsplit(url)
    if "instagram.com" not in (parsed.netloc or ""):
        raise ValueError("Please provide an instagram.com profile URL")
    parts = [p for p in (parsed.path or "").split("/") if p]
    if not parts:
        raise ValueError("Could not extract handle")
    handle = parts[0].lstrip("@")
    canonical = f"https://www.instagram.com/{handle}/"
    return canonical, handle


def domain_of(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url).netloc or "").lower()
    except Exception:
        return ""


def is_threads_domain(host: str) -> bool:
    h = (host or "").lower()
    return h.endswith("threads.net") or h.endswith("threads.com")


def is_meta_domain(host: str) -> bool:
    h = (host or "").lower()
    return any(
        h.endswith(d)
        for d in (
            "facebook.com",
            "meta.com",
            "instagram.com",
        )
    )


def linktree_domain(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    host = domain_of(url)
    for d in ("linktr.ee", "linkin.bio", "beacons.ai"):
        if host.endswith(d):
            return host
    return None


def extract_urls_from_text(text: str) -> List[str]:
    text = normalize_text(text)
    if not text:
        return []
    found = re.findall(r"https?://[^\s\]\)\"']+", text)
    out: List[str] = []
    for u in found:
        u = u.rstrip(".,;)]\"")
        if u.endswith("]"):
            u = u[:-1]
        out.append(u)
    return out


def strip_tracking_params(url: str) -> str:
    try:
        p = urllib.parse.urlsplit(url)
        qs = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
        kept = []
        for k, v in qs:
            lk = k.lower()
            if lk == "fbclid" or lk.startswith("utm_"):
                continue
            kept.append((k, v))
        new_q = urllib.parse.urlencode(kept)
        return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, new_q, p.fragment))
    except Exception:
        return url


def unwrap_instagram_redirect(url: str) -> Tuple[str, bool]:
    """IG often wraps external links as https://l.instagram.com/?u=<encoded>."""
    try:
        p = urllib.parse.urlsplit(url)
        host = (p.netloc or "").lower()
        if host == "l.instagram.com":
            qs = urllib.parse.parse_qs(p.query)
            u = qs.get("u", [""])[0]
            if u:
                real = urllib.parse.unquote(u)
                real = strip_tracking_params(real)
                return real, True
    except Exception:
        return url, False
    return strip_tracking_params(url), False


def is_social_domain(host: str) -> bool:
    h = (host or "").lower()
    return any(
        h.endswith(d)
        for d in (
            "tiktok.com",
            "youtube.com",
            "youtu.be",
            "whatsapp.com",
            "wa.me",
            "twitter.com",
            "x.com",
            "linkedin.com",
        )
    )


def classify_link(url: str) -> str:
    u = (url or "").strip().lower()
    if not u:
        return "other"
    if u.startswith("mailto:"):
        return "other"
    if u.startswith("tel:"):
        return "other"
    host = domain_of(u)
    if any(host.endswith(d) for d in ("youtube.com", "youtu.be")):
        return "youtube"
    if host.endswith("wa.me") or host.endswith("whatsapp.com"):
        return "whatsapp"
    # Meta/threads are considered noise (threads is hard-ignored elsewhere)
    if is_meta_domain(host) or is_threads_domain(host):
        return "other"
    if u.startswith("http://") or u.startswith("https://"):
        return "website"
    return "other"


def detect_contact_website(items: List[ExternalLinkItem]) -> Optional[str]:
    # If title contains contact-ish keywords, pick first (prefer website type)
    contact_kw = re.compile(r"\b(contact|contact us|business|collab|email)\b", re.I)
    matches: List[ExternalLinkItem] = []
    for it in items:
        title = normalize_text(it.title)
        url = normalize_text(it.url)
        host = domain_of(url)
        if not url:
            continue
        if is_threads_domain(host) or is_meta_domain(host):
            continue
        if title and contact_kw.search(title):
            matches.append(ExternalLinkItem(title=title, url=url))
    if not matches:
        return None
    # Prefer website type
    for it in matches:
        if classify_link(it.url) == "website":
            return it.url
    return matches[0].url or None


def choose_primary_website(items: List[ExternalLinkItem], contact_website: Optional[str], emails: List[str]) -> Tuple[Optional[str], str]:
    # Priority 1: contact wins
    if contact_website:
        return contact_website, "contact_title"

    # Filter out threads + meta noise for primary selection
    filtered: List[ExternalLinkItem] = []
    for it in items:
        url = normalize_text(it.url)
        host = domain_of(url)
        if not url:
            continue
        if is_threads_domain(host) or is_meta_domain(host):
            continue
        filtered.append(ExternalLinkItem(title=normalize_text(it.title), url=url))

    # Priority 2: pick first website-domain link (not product/shop if avoidable)
    website_items = [it for it in filtered if classify_link(it.url) == "website"]

    def is_producty(it: ExternalLinkItem) -> bool:
        t = (it.title or "").lower()
        host = domain_of(it.url)
        if any(k in t for k in ("shop", "store", "buy", "order", "product", "brand")):
            return True
        if any(k in host for k in ("shop", "store")):
            return True
        return False

    if website_items:
        non_product = [it for it in website_items if not is_producty(it)]
        if non_product:
            return non_product[0].url, "first_website_non_product"
        return website_items[0].url, "first_website"

    # Fall back (do NOT ignore youtube/whatsapp)
    if emails:
        return f"mailto:{emails[0]}", "picked_email"

    yt = [it for it in filtered if classify_link(it.url) == "youtube"]
    if yt:
        return yt[0].url, "picked_youtube"

    wa = [it for it in filtered if classify_link(it.url) == "whatsapp"]
    if wa:
        return wa[0].url, "picked_whatsapp"

    return None, "no_primary"


def build_external_links_json(items: List[ExternalLinkItem]) -> Tuple[str, int]:
    """Return (json, threads_ignored_count). Threads is hard-ignored."""
    payload = []
    threads_ignored = 0

    for it in items:
        title = normalize_text(it.title)
        url = normalize_text(it.url)
        if not url:
            continue

        # Hard ignore threads
        host = domain_of(url)
        if is_threads_domain(host):
            threads_ignored += 1
            continue

        # Ignore other meta noise from storage
        if is_meta_domain(host):
            continue

        typ = classify_link(url)
        if typ not in ("website", "youtube", "whatsapp", "other"):
            typ = "other"

        payload.append({"title": title, "type": typ, "url": url})

    return json.dumps(payload, sort_keys=True), threads_ignored


def extract_emails_from_contact_buttons(page) -> List[str]:
    """Best-effort extraction from profile contact buttons (Email / Contact info)."""
    found = set()

    # Try explicit Email button (may open mailto: link or a dialog)
    try:
        email_btn = page.get_by_role("button", name=re.compile(r"^email$", re.I))
        if email_btn.count() > 0 and email_btn.first.is_visible(timeout=800):
            # Sometimes opens a mailto: anchor rather than popup; click and then scan page
            try:
                email_btn.first.click(timeout=1200)
                page.wait_for_timeout(500)
            except Exception:
                pass
            # scan for mailto:
            try:
                hrefs = page.locator('a[href^="mailto:"]').evaluate_all("els => els.map(e => e.getAttribute('href'))")
                for h in hrefs or []:
                    if h and h.lower().startswith("mailto:"):
                        addr = h.split(":", 1)[1].split("?", 1)[0]
                        if addr:
                            found.add(addr.lower())
            except Exception:
                pass
    except Exception:
        pass

    # Try "Contact info" modal
    try:
        cbtn = page.get_by_role("button", name=re.compile(r"contact\s*info|contact|call|text", re.I))
        if cbtn.count() > 0 and cbtn.first.is_visible(timeout=800):
            cbtn.first.click(timeout=1500)
            page.wait_for_timeout(800)
            dialog = page.locator('[role="dialog"]').first
            if dialog.count() > 0 and dialog.first.is_visible(timeout=1500):
                txt = normalize_text(dialog.first.inner_text() or "")
                for e in EMAIL_RE.findall(txt):
                    found.add(e.lower())
                # capture any mailto links
                hrefs = dialog.first.locator('a[href^="mailto:"]').evaluate_all(
                    "els => els.map(e => e.getAttribute('href'))"
                )
                for h in hrefs or []:
                    if h and h.lower().startswith("mailto:"):
                        addr = h.split(":", 1)[1].split("?", 1)[0]
                        if addr:
                            found.add(addr.lower())
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
    except Exception:
        pass

    return sorted(found)


@dataclass
class ExternalLinkItem:
    title: str
    url: str


@dataclass
class IGProfileData:
    canonical_url: str
    handle: str
    display_name: Optional[str]
    followers: Optional[int]
    following: Optional[int]
    posts: Optional[int]
    bio_text: str
    external_links: List[ExternalLinkItem]
    external_links_json: str
    emails: List[str]
    contact_website: Optional[str]
    primary_website: str
    primary_reason: str
    filtered_domains: Dict[str, int]
    unwrapped_urls_count: int
    modal_opened: bool
    modal_items_found: int
    sample_modal_titles: List[str]
    sample_modal_urls: List[str]
    avg_views_last_10: Optional[float]
    avg_likes_last_10: Optional[float]
    avg_comments_last_10: Optional[float]
    posting_frequency_per_week: Optional[float]
    posting_frequency_per_week_90d: Optional[float]


def ensure_schema(con: sqlite3.Connection) -> None:
    cols = {row[1] for row in con.execute("PRAGMA table_info(social_profiles);").fetchall()}
    if "stats_status" not in cols:
        con.execute(
            "ALTER TABLE social_profiles ADD COLUMN stats_status TEXT NOT NULL DEFAULT 'missing_public' CHECK(stats_status IN ('ok','missing_public','self_submitted','oauth_verified'));"
        )
    if "updated_at" not in cols:
        con.execute("ALTER TABLE social_profiles ADD COLUMN updated_at TEXT NULL;")

    # Playwright ingestion: store all external links + chosen websites
    if "external_links_json" not in cols:
        con.execute("ALTER TABLE social_profiles ADD COLUMN external_links_json TEXT;")
    if "contact_website" not in cols:
        con.execute("ALTER TABLE social_profiles ADD COLUMN contact_website TEXT;")
    if "primary_website" not in cols:
        con.execute("ALTER TABLE social_profiles ADD COLUMN primary_website TEXT;")
    if "contact_emails_json" not in cols:
        con.execute("ALTER TABLE social_profiles ADD COLUMN contact_emails_json TEXT;")

    # Accurate engagement metrics
    if "posting_frequency_per_week_90d" not in cols:
        con.execute("ALTER TABLE social_profiles ADD COLUMN posting_frequency_per_week_90d REAL;")


def connect_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON;")
    ensure_schema(con)
    return con


def is_logged_in(page) -> bool:
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""
    if "/accounts/login" in url:
        return False
    try:
        html = page.content()
        if re.search(r"name=\"username\"", html, re.I):
            return False
    except Exception:
        pass
    try:
        if page.get_by_role("link", name=re.compile(r"home", re.I)).is_visible(timeout=1500):
            return True
    except Exception:
        pass
    try:
        if page.locator('a[href^="/direct/"]').first.is_visible(timeout=1500):
            return True
    except Exception:
        pass
    return False


def _has_session_cookie(ctx) -> bool:
    try:
        cookies = ctx.cookies("https://www.instagram.com")
    except Exception:
        return False
    for c in cookies:
        if (c.get("name") or "").lower() in ("sessionid", "ds_user_id") and c.get("value"):
            return True
    return False


def save_screenshot(page, name: str, enabled: bool) -> Optional[str]:
    if not enabled:
        return None
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = DEBUG_DIR / f"{ts}_{name}.png"
        page.screenshot(path=str(path), full_page=True)
        return str(path)
    except Exception:
        return None


def safe_click_text(page, pattern: str, timeout_ms: int = 1500) -> bool:
    try:
        loc = page.get_by_text(re.compile(pattern, re.I)).first
        if loc and loc.is_visible(timeout=timeout_ms):
            loc.click(timeout=timeout_ms)
            return True
    except Exception:
        return False
    return False


def handle_common_popups(page) -> None:
    # Cookies / notifications / save login prompts (best-effort)
    for pat in [
        r"accept all",
        r"allow all cookies",
        r"only allow essential",
        r"not now",
    ]:
        try:
            safe_click_text(page, pat, timeout_ms=1200)
            page.wait_for_timeout(300)
        except Exception:
            pass


def detect_blocked_or_challenge(page) -> bool:
    u = (page.url or "").lower()
    if "challenge" in u or "checkpoint" in u:
        return True
    try:
        txt = page.inner_text("body")[:2500]
    except Exception:
        txt = ""
    if re.search(r"challenge|checkpoint|verify|suspicious|try again later", txt, re.I):
        return True
    return False


def do_login() -> int:
    PW_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(PW_PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        print("Browser opened. Please log in manually. This window will stay open until login is detected.")

        deadline = time.time() + 900
        while time.time() < deadline:
            page.wait_for_timeout(1000)
            if detect_blocked_or_challenge(page):
                print("BLOCKED_OR_CHALLENGE")
                ctx.close()
                return 2
            if _has_session_cookie(ctx) or is_logged_in(page):
                page.wait_for_timeout(1500)
                ctx.close()
                print("Login session saved")
                return 0

        ctx.close()
        print("SESSION_EXPIRED: please run with --login")
        return 1


def _parse_counts_from_meta_desc(desc: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    # "X Followers, Y Following, Z Posts - ..."
    desc = normalize_text(desc)
    if not desc:
        return None, None, None
    mf = re.search(r"([0-9][0-9.,]*\s*[KMB]?)\s+Followers", desc, re.I)
    mfo = re.search(r"([0-9][0-9.,]*\s*[KMB]?)\s+Following", desc, re.I)
    mp = re.search(r"([0-9][0-9.,]*\s*[KMB]?)\s+Posts", desc, re.I)
    followers = parse_metric_int(mf.group(1)) if mf else None
    following = parse_metric_int(mfo.group(1)) if mfo else None
    posts = parse_metric_int(mp.group(1)) if mp else None
    return followers, following, posts


def _extract_counts_from_json(html: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    # Best-effort: look for "edge_followed_by":{"count":...}
    try:
        m1 = re.search(r"\"edge_followed_by\"\s*:\s*\{\s*\"count\"\s*:\s*(\d+)", html)
        m2 = re.search(r"\"edge_follow\"\s*:\s*\{\s*\"count\"\s*:\s*(\d+)", html)
        m3 = re.search(r"\"edge_owner_to_timeline_media\"\s*:\s*\{\s*\"count\"\s*:\s*(\d+)", html)
        followers = int(m1.group(1)) if m1 else None
        following = int(m2.group(1)) if m2 else None
        posts = int(m3.group(1)) if m3 else None
        return followers, following, posts
    except Exception:
        return None, None, None


def _extract_counts_from_header_row(page) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    # Look for header counters row: posts/followers/following
    js = r"""
() => {
  const out = {posts:null, followers:null, following:null};
  const header = document.querySelector('header');
  if (!header) return out;
  const lis = Array.from(header.querySelectorAll('section ul li'));
  for (const li of lis) {
    const t = (li.getAttribute('aria-label') || li.textContent || '').trim();
    if (!t) continue;
    if (/posts?/i.test(t)) out.posts = t;
    if (/followers?/i.test(t)) out.followers = t;
    if (/following/i.test(t)) out.following = t;
  }
  // If followers/following are links, their aria-label may be on child span
  const fl = document.querySelector('a[href$="/followers/"] span')?.getAttribute('aria-label') || document.querySelector('a[href$="/followers/"]')?.getAttribute('aria-label');
  if (fl) out.followers = fl;
  const fol = document.querySelector('a[href$="/following/"] span')?.getAttribute('aria-label') || document.querySelector('a[href$="/following/"]')?.getAttribute('aria-label');
  if (fol) out.following = fol;
  return out;
}
"""
    d = page.evaluate(js)
    return (
        parse_metric_int(d.get("followers")),
        parse_metric_int(d.get("following")),
        parse_metric_int(d.get("posts")),
    )


def _wait_profile_loaded(page, canonical_url: str) -> None:
    # networkidle can hang on IG; use domcontentloaded + targeted waits.
    page.goto(canonical_url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("header", timeout=20000)
    except Exception:
        pass
    # Allow late async rendering
    page.wait_for_timeout(1500)


def _collect_recent_media_urls(page, last_n: int) -> List[str]:
    # Collect /reel/ and /p/ URLs from the profile grid.
    js = r"""
() => {
  const out = [];
  const seen = new Set();
  const anchors = Array.from(document.querySelectorAll('a[href]'));
  for (const a of anchors) {
    const h = a.getAttribute('href') || '';
    if (!h) continue;
    if (!(h.startsWith('/reel/') || h.startsWith('/p/'))) continue;
    if (seen.has(h)) continue;
    seen.add(h);
    out.push(h);
    if (out.length >= 200) break;
  }
  return out;
}
"""
    hrefs = page.evaluate(js) or []
    urls: List[str] = []
    for h in hrefs:
        if not h:
            continue
        if h.startswith("/"):
            urls.append("https://www.instagram.com" + h)
        else:
            urls.append(h)
    # Deduplicate preserving order
    out: List[str] = []
    seen = set()
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= last_n:
            break
    return out[:last_n]


def _collect_reel_urls_from_reels_page(page, last_n: int) -> List[str]:
    # Collect anchors where href contains /reel/
    js = r"""
() => {
  const out = [];
  const seen = new Set();
  const anchors = Array.from(document.querySelectorAll('a[href*="/reel/"]'));
  for (const a of anchors) {
    const h = a.getAttribute('href') || '';
    if (!h) continue;
    const m = h.match(/\/reel\/[A-Za-z0-9_\-]+\//);
    const key = m ? m[0] : h;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(h);
    if (out.length >= 250) break;
  }
  return out;
}
"""
    hrefs = page.evaluate(js) or []
    urls: List[str] = []
    for h in hrefs:
        if not h:
            continue
        # normalize to canonical https://www.instagram.com/reel/<id>/
        m = re.search(r"/reel/[A-Za-z0-9_\-]+/", h)
        if m:
            urls.append("https://www.instagram.com" + m.group(0))
        elif h.startswith("/"):
            urls.append("https://www.instagram.com" + h)
        else:
            urls.append(h)

    # Deduplicate preserving order, then take newest by taking first N after scroll
    out: List[str] = []
    seen = set()
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= last_n:
            break
    return out[:last_n]


def _extract_media_metrics(
    page,
    reel_url: str,
    shortcode: str,
    grid_views: Optional[int],
    debug: bool,
    save_screenshots: bool,
) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[str], str, str, str, str, str, bool, str, str]:
    """Extract likes/comments/views/published from a REEL page.

    Goals:
      - Never block on <article>
      - Prefer DOM selectors (aria-label Like/Comment + time[datetime])
      - Always write per-reel artifacts (HTML + screenshot) via try/finally

    Returns:
      likes, comments, views, published_iso,
      views_source (reel_dom|grid_overlay|grid_overlay_override|blank),
      published_source (time_datetime|embedded_json|blank),
      wait_path_used (like_svg|comment_svg|time|liked_by|fallback_none),
      selector_strategy, fail_reason,
      views_dom_outlier (bool)
      comments_status (ok|disabled|suspicious|blank)
    """

    def _short(s: str, n: int = 140) -> str:
        s = normalize_text(s)
        return (s[: n - 1] + "…") if len(s) > n else s

    def _nearest_metric_from_container(container_loc) -> Optional[int]:
        """Find a plausible metric number in a container by scanning text contents."""
        try:
            # Grab a limited set to avoid huge scans
            texts = container_loc.locator("span,div,a").all_text_contents()
            for raw in texts:
                t = normalize_text(raw)
                if not t:
                    continue
                # Prefer strings that look like '<num> likes' or '<num> comments'
                m = re.search(r"\b([0-9][0-9.,]*\s*[KMB]?)\b", t)
                if not m:
                    continue
                val = parse_metric_int(m.group(1))
                if val is None:
                    continue
                # Filter obvious junk (icon sizes etc.)
                if val in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16, 20, 24):
                    continue
                return val
        except Exception:
            return None
        return None

    def _metric_near_action_svg(svg_label: str) -> Tuple[Optional[int], str]:
        """Find metric near svg[aria-label=...] by walking to role=button and scanning nearby."""
        svg = page.locator(f'svg[aria-label="{svg_label}"]').first
        if svg.count() == 0:
            return None, "no_svg"

        # closest role=button ancestor (per user-provided HTML clue)
        btn = svg.locator('xpath=ancestor::*[@role="button"][1]')
        if btn.count() == 0:
            return None, "no_button"

        # 1) try direct text on button
        try:
            t = normalize_text(btn.first.inner_text() or "")
            v = parse_metric_int(t)
            if v is not None:
                return v, "btn_text"
        except Exception:
            pass

        # 2) scan a few ancestor containers (action rail)
        for depth in (1, 2, 3, 4):
            try:
                container = btn.locator(f'xpath=ancestor::*[{depth}]').first
                v = _nearest_metric_from_container(container)
                if v is not None:
                    return v, f"ancestor_scan_{depth}"
            except Exception:
                continue

        # 3) if there is a liked_by link nearby, sometimes it contains the count
        try:
            liked = page.locator('a[href*="/liked_by/"]').first
            if liked.count() > 0:
                t = normalize_text(liked.inner_text() or "")
                v = parse_metric_int(t)
                if v is not None:
                    return v, "liked_by_link"
        except Exception:
            pass

        return None, "not_found"

    # A) More reliable "page ready" wait (no article)
    wait_path_used = "fallback_none"
    for sel, label in (
        ('svg[aria-label="Like"]', "like_svg"),
        ('svg[aria-label="Comment"]', "comment_svg"),
        ('time[datetime]', "time"),
        ('a[href*="/liked_by/"]', "liked_by"),
    ):
        try:
            page.wait_for_selector(sel, timeout=10_000)
            wait_path_used = label
            break
        except Exception:
            continue

    likes: Optional[int] = None
    likes_status = "missing"  # ok | hidden_or_unavailable | suspicious | missing
    likes_reason = ""

    comments: Optional[int] = None
    comments_status = "blank"
    views: Optional[int] = None
    views_source = "blank"
    published: Optional[str] = None
    published_source = "blank"

    selector_strategy_parts: List[str] = []
    fail_reason = ""

    # B) Always write per-reel artifacts (html + screenshot) even if parsing fails
    html_path = DEBUG_DIR / f"parse_{shortcode}.html"
    png_path = DEBUG_DIR / f"parse_{shortcode}.png"
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # C) Published datetime
        try:
            published = page.locator('time[datetime]').first.get_attribute('datetime')
            if published:
                published_source = "time_datetime"
                selector_strategy_parts.append("published=time[datetime]")
        except Exception:
            pass

        # C2) Published fallback via embedded JSON/script blobs
        if not published:
            try:
                html_for_parse = page.content() or ""
                # Look for epoch seconds in common keys
                # Examples: "taken_at_timestamp":1700000000
                hits = []
                for key in ("taken_at_timestamp", "taken_at", "created_time"):
                    for m in re.finditer(rf'"{key}"\s*:\s*(\d{{9,12}})', html_for_parse):
                        try:
                            hits.append(int(m.group(1)))
                        except Exception:
                            pass
                # Pick first plausible epoch seconds
                chosen = None
                for ts in hits:
                    # Some are ms; normalize
                    if ts > 10_000_000_000:
                        ts = ts // 1000
                    if 1_200_000_000 <= ts <= 2_200_000_000:
                        chosen = ts
                        break
                if chosen is not None:
                    published = datetime.fromtimestamp(chosen, tz=timezone.utc).replace(microsecond=0).isoformat()
                    published_source = "embedded_json"
                    selector_strategy_parts.append("published=embedded_json")
            except Exception:
                pass

        # D) Likes/comments near aria-label icons
        like_ui_exists = False
        try:
            likes, how = _metric_near_action_svg("Like")
            if likes is not None:
                likes_status = "ok"
                selector_strategy_parts.append(f"likes=svg->button({how})")
            else:
                try:
                    like_ui_exists = page.locator('svg[aria-label="Like"], svg[aria-label="Unlike"]').count() > 0
                except Exception:
                    like_ui_exists = False
        except Exception:
            try:
                like_ui_exists = page.locator('svg[aria-label="Like"], svg[aria-label="Unlike"]').count() > 0
            except Exception:
                like_ui_exists = False

        # Likes hidden/unavailable detection (resilient)
        # Marker-based safeguard: if Like UI exists but no numeric likes parsed (and not blocked), treat as hidden.
        if likes is None and like_ui_exists and (likes_status in ("missing", "missing_ui")):
            try:
                if not detect_blocked_or_challenge(page):
                    likes_status = "hidden_or_unavailable"
                    likes_reason = "like_ui_no_numeric"
                    try:
                        trust_flags.append("likes_hidden")
                    except Exception:
                        pass
            except Exception:
                pass

        if likes is None:
            if not like_ui_exists:
                likes_status = "missing_ui"
                likes_reason = "no_like_ui"
                try:
                    trust_flags.append("missing_engagement_metrics")
                except Exception:
                    pass
            else:
                try:
                    blob = normalize_text(page.inner_text("body", timeout=2000) or "")
                except Exception:
                    blob = ""
                if re.search(
                    r"likes\s+are\s+hidden|like\s+count\s+is\s+hidden|likes\s+hidden\s+by|likes\s+hidden\s+by\s+author|hidden\s+likes",
                    blob,
                    re.I,
                ):
                    likes_status = "hidden_or_unavailable"
                    likes_reason = "phrase"
                    likes = None
                    try:
                        trust_flags.append("likes_hidden")
                    except Exception:
                        pass
                else:
                    likes_status = "hidden_or_unavailable"
                    likes_reason = "no_numeric_near_like"
                    likes = None
                    try:
                        trust_flags.append("likes_hidden")
                    except Exception:
                        pass

        try:
            comments, how = _metric_near_action_svg("Comment")
            if comments is not None:
                comments_status = "ok"
                selector_strategy_parts.append(f"comments=svg->button({how})")
        except Exception:
            pass

        # Comment disabled/limited detection (STRICT + scoped to comments panel)
        # Never override a valid numeric comments count.
        comments_raw_extracted = comments
        composer_present = None
        restriction_text_found = None
        comments_status_reason = ""

        if debug or comments is None or comments_status == "suspicious":
            try:
                c_svg = page.locator('svg[aria-label="Comment"]').first
                c_btn = c_svg.locator('xpath=ancestor::*[@role="button"][1]')
                if c_btn.count() > 0:
                    c_btn.first.click(timeout=2500)
                    page.wait_for_timeout(650)

                    # Dialog scope
                    dialog = page.locator('[role="dialog"]').filter(has_text=re.compile(r"\bcomments\b", re.I)).first
                    if dialog.count() == 0:
                        dialog = page.locator('[role="dialog"]').first

                    # Restriction text detection (inside dialog only)
                    phrases = [
                        r"comments are turned off",
                        r"comments are disabled",
                        r"comments have been limited",
                        r"comments on this post have been limited",
                        r"limited who can comment",
                    ]
                    matched = None
                    for ph in phrases:
                        try:
                            loc = dialog.get_by_text(re.compile(ph, re.I)).first
                            if loc.count() > 0 and loc.first.is_visible(timeout=1200):
                                matched = ph
                                break
                        except Exception:
                            continue
                    restriction_text_found = bool(matched)

                    # Strong evidence only: mark disabled/limited ONLY when restriction text exists in dialog.
                    if matched:
                        comments = None
                        comments_status = "disabled_or_limited"
                        comments_status_reason = "restriction_text_in_panel"
                        try:
                            trust_flags.append("comments_disabled_or_limited")
                        except Exception:
                            pass
                        if debug:
                            print(f"comments_status_detected=disabled_or_limited matched_phrase=\"{matched}\"")

                    # Save panel screenshot only when something is off
                    if debug and save_screenshots and comments_status != "ok":
                        try:
                            p = DEBUG_DIR / f"parse_{shortcode}_comments_panel.png"
                            page.screenshot(path=str(p), full_page=True)
                            print(f"artifact_comments_panel_png: {str(p)} size_bytes={p.stat().st_size}")
                        except Exception:
                            pass

                    # Close drawer
                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass
                    page.wait_for_timeout(250)
            except Exception:
                pass

        if debug:
            print(
                f"comments_raw_extracted={comments_raw_extracted if comments_raw_extracted is not None else ''} "
                f"comments_status={comments_status} "
                f"restriction_text_found={restriction_text_found} comments_status_reason={comments_status_reason}"
            )

        # E) Views on reel page (best-effort DOM, still selector-based)
        # Try: any element containing 'views'/'plays' text; then parse the number from that text.
        reel_dom_views: Optional[int] = None
        try:
            loc = page.get_by_text(re.compile(r"\b(views|plays)\b", re.I)).first
            if loc.count() > 0:
                t = normalize_text(loc.inner_text() or "")
                m = re.search(r"([0-9][0-9.,]*\s*[KMB]?)", t)
                if m:
                    v = parse_metric_int(m.group(1))
                    if v is not None:
                        reel_dom_views = v
                        selector_strategy_parts.append("views=text_contains_views")
        except Exception:
            pass

        grid_overlay_views: Optional[int] = grid_views
        views_dom_outlier = False

        # Views policy (reels): grid_overlay is primary; reel_dom is secondary with sanity.
        if grid_overlay_views is not None:
            views = grid_overlay_views
            views_source = "grid_overlay"
            selector_strategy_parts.append("views=grid_overlay_primary")

            if reel_dom_views is not None and grid_overlay_views > 0:
                ratio = float(reel_dom_views) / float(grid_overlay_views)
                ok_ratio = (0.2 <= ratio <= 10)
                ok_min = reel_dom_views >= 1000
                ok_vs_likes = True
                if likes is not None:
                    ok_vs_likes = reel_dom_views >= likes

                if ok_ratio and ok_min and ok_vs_likes:
                    views = reel_dom_views
                    views_source = "reel_dom"
                    selector_strategy_parts.append("views=reel_dom_sane")
                    if debug:
                        print(
                            f"views_compare: reel_dom={reel_dom_views} grid_overlay={grid_overlay_views} ratio={ratio:.2f} chosen=reel_dom"
                        )
                else:
                    views_dom_outlier = True
                    views_source = "grid_overlay_override"
                    selector_strategy_parts.append("views=grid_overlay_override")
                    if debug:
                        print(
                            f"views_compare: reel_dom={reel_dom_views} grid_overlay={grid_overlay_views} ratio={ratio:.2f} chosen=grid_override"
                        )

        elif reel_dom_views is not None:
            # reel_dom only: accept only if sane.
            if reel_dom_views < 1000 or (likes is not None and reel_dom_views < likes):
                views = None
                views_source = "reel_dom_rejected"
            else:
                views = reel_dom_views
                views_source = "reel_dom"
        else:
            views = None
            views_source = "blank"

    finally:
        # ALWAYS dump full HTML + screenshot for this reel
        try:
            html = page.content()
            html_path.write_text(html, encoding="utf-8", errors="replace")
        except Exception:
            pass

        try:
            page.screenshot(path=str(png_path), full_page=True)
        except Exception:
            pass

        if debug:
            try:
                hs = html_path.stat().st_size if html_path.exists() else 0
                ps = png_path.stat().st_size if png_path.exists() else 0
                print(f"artifact_html: {str(html_path)} size_bytes={hs}")
                print(f"artifact_png: {str(png_path)} size_bytes={ps}")
            except Exception:
                pass

    # Likes sanity filtering (only if likes is present)
    try:
        if likes is not None:
            if likes < 0:
                likes = None
                likes_status = "suspicious"
                likes_reason = "neg"
            elif views is not None and likes > views:
                likes = None
                likes_status = "suspicious"
                likes_reason = "likes_gt_views"
            elif views is not None and views < 1000 and likes > 200:
                likes = None
                likes_status = "suspicious"
                likes_reason = "low_views_high_likes"

            if likes_status == "suspicious":
                try:
                    trust_flags.append("engagement_metric_suspicious_filtered")
                except Exception:
                    pass
    except Exception:
        pass

    # ALWAYS-ON comment sanity filtering (prevents outliers poisoning aggregates)
    try:
        if comments_status != "disabled_or_limited" and comments is not None:
            rule = None
            if views is not None and comments > (0.02 * float(views)):
                rule = "comments_gt_2pct_views"
            elif likes is not None and comments > (0.25 * float(likes)):
                rule = "comments_gt_25pct_likes"
            elif comments > 1000 and (views is None or views < 1000000) and (likes is None or likes < 100000):
                rule = "comments_gt_1000_low_scale"

            if rule:
                if debug:
                    print(
                        f"comments_sanity: views={views if views is not None else ''} "
                        f"likes={likes if likes is not None else ''} "
                        f"comments={comments} -> filtered (rule={rule})"
                    )
                comments = None
                comments_status = "suspicious"
                try:
                    trust_flags.append("comments_suspicious_filtered")
                except Exception:
                    pass
    except Exception:
        pass

    if comments is None and comments_status == "blank":
        comments_status = "blank"

    missing = []
    if likes is None:
        missing.append("likes")
    if comments is None and comments_status not in ("disabled", "disabled_or_limited", "hidden"):
        missing.append("comments")
    if views is None:
        missing.append("views")
    if published is None:
        missing.append("published")

    if missing:
        fail_reason = "missing:" + ",".join(missing)

    selector_strategy = ";".join(selector_strategy_parts)
    # --- BEGIN PATCH: views sanity + comments disabled probe (surgical) ---
    # Assumes these variables may exist from existing logic:
    # reel_dom_views, grid_overlay_views, views, views_source, likes, comments, trust_flags
    try:
        rdv = locals().get("reel_dom_views", None)
        gov = locals().get("grid_overlay_views", None)

        # Views sanity: cross-check reel_dom vs grid_overlay
        if rdv is not None and gov is not None and gov not in (0, None):
            ratio = (rdv / gov) if gov else None
            if ratio is not None and (ratio > 10 or ratio < 0.2):
                views = gov
                views_source = "grid_overlay_override"
                try:
                    trust_flags.append("views_dom_outlier")
                except Exception:
                    pass
                if locals().get("debug", False):
                    print(f"views_compare: reel_dom={rdv} grid_overlay={gov} ratio={ratio:.2f} chosen=grid_override")
            else:
                views = rdv
                views_source = "reel_dom"
                if locals().get("debug", False) and ratio is not None:
                    print(f"views_compare: reel_dom={rdv} grid_overlay={gov} ratio={ratio:.2f} chosen=reel_dom")
        elif rdv is not None and gov is None:
            if rdv < 1000:
                views = None
                views_source = "reel_dom_rejected"
                try:
                    trust_flags.append("views_dom_outlier")
                except Exception:
                    pass
            else:
                views = rdv
                views_source = "reel_dom"
        elif gov is not None and rdv is None:
            views = gov
            views_source = locals().get("views_source", "grid_overlay")

        # If likes present, reject impossible views (only if likes is numeric)
        lk = locals().get("likes", None)
        if views is not None and lk is not None:
            try:
                if views < lk:
                    views = gov if gov is not None else None
                    views_source = "grid_overlay_override"
                    try:
                        trust_flags.append("views_dom_outlier")
                    except Exception:
                        pass
            except Exception:
                pass

        # Comments disabled probe: only when comments missing/suspicious
        comments_status = locals().get("comments_status", "ok")
        cval = locals().get("comments", None)
        if cval in (None, "") or comments_status in ("suspicious", "missing"):
            # NOTE: relies on existing 'page' variable in function (Playwright Page)
            try:
                composer = page.locator('textarea[placeholder*="comment" i], textarea[aria-label*="comment" i], [role="textbox"][aria-label*="comment" i]').first
                has_composer = composer.count() > 0
            except Exception:
                has_composer = True  # fail open

            if not has_composer:
                comments = None
                comments_status = "disabled_or_limited"
                try:
                    trust_flags.append("comments_disabled_or_limited")
                except Exception:
                    pass
    except Exception:
        pass
    # --- END PATCH ---
    if debug:
        print(
            f"likes={likes if likes is not None else ''} likes_status={likes_status}"
            + (f" likes_reason={likes_reason}" if likes_reason else "")
        )

    return (
        likes,
        comments,
        views,
        published,
        views_source,
        published_source,
        wait_path_used,
        selector_strategy,
        fail_reason,
        bool(locals().get("views_dom_outlier", False)),
        comments_status,
        likes_status,
    )


def scrape_accurate_engagement(
    page,
    profile_url: str,
    last_n: int,
    debug: bool = False,
    headed: bool = False,
    save_screenshots: bool = False,
) -> Dict[str, Any]:
    # Returns robust engagement aggregates + sample items + debug.

    def mean(xs: List[int]) -> Optional[float]:
        return (sum(xs) / len(xs)) if xs else None

    def median(xs: List[int]) -> Optional[float]:
        if not xs:
            return None
        ys = sorted(xs)
        n = len(ys)
        mid = n // 2
        if n % 2 == 1:
            return float(ys[mid])
        return (float(ys[mid - 1]) + float(ys[mid])) / 2.0

    def trimmed_mean(xs: List[int]) -> Optional[float]:
        """Trimmed mean: drop top/bottom 10% if n>=10, else mean."""
        if not xs:
            return None
        ys = sorted(xs)
        n = len(ys)
        if n >= 10:
            k = max(1, int(n * 0.10))
            ys = ys[k : n - k]
        return mean(ys)

    def get_body_blob() -> str:
        # Best-effort small normalized text blob for hidden/disabled detection.
        try:
            t = page.inner_text("body", timeout=2000)
        except Exception:
            t = ""
        t = normalize_text(t)
        if len(t) > 20000:
            t = t[:20000]
        return t

    # PART A: always go to reels page
    base = profile_url.rstrip("/") + "/"
    reels_page = base + "reels/"
    page.goto(reels_page, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    handle_common_popups(page)

    # When debugging, capture reels grid artifacts after network settles
    if debug:
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        try:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            grid_html = DEBUG_DIR / "reels_grid.html"
            grid_png = DEBUG_DIR / "reels_grid.png"
            grid_html.write_text(page.content(), encoding="utf-8", errors="replace")
            page.screenshot(path=str(grid_png), full_page=True)
            print(f"reels_grid_html: {str(grid_html)} size_bytes={grid_html.stat().st_size}")
            print(f"reels_grid_png: {str(grid_png)} size_bytes={grid_png.stat().st_size}")
        except Exception:
            pass

    # scroll to top
    try:
        page.evaluate("window.scrollTo(0,0)")
    except Exception:
        pass
    page.wait_for_timeout(1000)

    # wait for reels grid (best effort)
    try:
        page.wait_for_selector('a[href*="/reel/"]', timeout=15000)
    except Exception:
        pass

    # Extra debug before collection
    html_dump_path = None
    html_dump_size = None
    if debug:
        final_url = page.url
        try:
            page_title = page.title()
        except Exception:
            page_title = ""
        login_wall = ("/accounts/login" in (final_url or ""))
        if not login_wall:
            try:
                body_txt = normalize_text(page.inner_text("body") or "")
                if re.search(r"\blog\s*in\b", body_txt, re.I):
                    login_wall = True
            except Exception:
                pass
        print(f"final_url: {final_url}")
        print(f"page_title: {page_title}")
        print(f"login_wall_detected: {str(bool(login_wall))}")

        try:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            html_path = DEBUG_DIR / "last_page.html"
            html = page.content()
            html_path.write_text(html, encoding="utf-8", errors="replace")
            html_dump_path = str(html_path)
            html_dump_size = html_path.stat().st_size
            print(f"html_dump_path: {html_dump_path}")
            print(f"html_dump_size_bytes: {html_dump_size}")
        except Exception:
            pass

    # Collect reel links in visual order with incremental scroll
    collected: List[str] = []
    seen = set()
    grid_views_by_shortcode: Dict[str, int] = {}

    def collect_visible() -> List[Dict[str, str]]:
        """Collect visible reel anchors plus best-effort overlay views text.

        Strategy order for viewsText (grid overlay):
          A) aria-label on anchor or nearest parent role=link/button
          B) visible textContent on anchor/ancestors
        """
        js = r"""
() => {
  const tiles = Array.from(document.querySelectorAll('a[href*="/reel/"]'));
  const items = [];

  function findViewsText(a) {
    // STRICT scoping: try to find the metric text that lives in the icon-overlay row.
    // We can't always identify "play" reliably, so we:
    //  - iterate svg/role=img inside the tile
    //  - walk up 1–3 ancestors
    //  - return the FIRST ancestor text that contains a metric-like token (K/M/B or comma groups)

    function hasMetricToken(txt) {
      const s = String(txt || '');
      return /\b\d+(?:\.\d+)?[KMB]\b/i.test(s) || /\b\d{1,3}(?:,\d{3})+\b/.test(s) || /\b\d+\b/.test(s);
    }

    if (!a) return '';

    // 1) Prefer: metric-only text that is in the SAME small container as an icon (play overlay row)
    try {
      const svgs = Array.from(a.querySelectorAll('svg'));
      for (const svg of svgs) {
        let c = svg;
        for (let hop = 0; hop < 2; hop++) {
          if (!c || !c.parentElement) break;
          c = c.parentElement;
          const els = Array.from(c.querySelectorAll('span,div'));
          for (const el of els) {
            const t = (el && el.textContent) ? String(el.textContent).trim() : '';
            if (!t) continue;
            if (/^\d{1,3}(?:,\d{3})+$/.test(t) || /^\d+(?:\.\d+)?[KMB]$/i.test(t)) {
              return t;
            }
          }
        }
      }
    } catch (e) {}

    // 2) Otherwise, attempt icon-neighborhood scoping (broader)
    const icons = [];
    try {
      icons.push(...Array.from(a.querySelectorAll('svg')));
      icons.push(...Array.from(a.querySelectorAll('[role="img"]')));
    } catch (e) {}

    for (const icon of icons) {
      let cur = icon;
      for (let i = 0; i < 3; i++) {
        if (!cur || !cur.parentElement) break;
        cur = cur.parentElement;
        const txt = (cur && cur.textContent) ? String(cur.textContent).trim() : '';
        if (txt && hasMetricToken(txt)) {
          return txt;
        }
      }
    }

    return '';
  }

  for (const a of tiles) {
    const href = a.getAttribute('href') || '';
    if (!href.includes('/reel/')) continue;
    const r = a.getBoundingClientRect();
    if (r.width < 10 || r.height < 10) continue;
    if (r.bottom < 0 || r.top > window.innerHeight*2) continue;
    items.push({ href, top: r.top, left: r.left, viewsText: findViewsText(a) || '' });
  }

  items.sort((x,y) => (x.top - y.top) || (x.left - y.left));
  return items.map(i => ({ href: i.href, viewsText: i.viewsText }));
}
"""
        try:
            return page.evaluate(js) or []
        except Exception:
            return []

    scroll_steps = 0
    # Keep scrolls limited to reduce timeouts and preserve "latest" ordering.
    while len(collected) < last_n and scroll_steps < 3:
        items = collect_visible()
        for it in items:
            h = (it or {}).get("href", "") if isinstance(it, dict) else str(it)
            vt = (it or {}).get("viewsText", "") if isinstance(it, dict) else ""

            m = re.search(r"/reel/[A-Za-z0-9_\-]+/", h)
            if not m:
                continue
            u = "https://www.instagram.com" + m.group(0)

            rid = ""
            m2 = re.search(r"/reel/([^/]+)/", u)
            if m2:
                rid = m2.group(1)

            # Parse a grid overlay views number, if present (bare metrics like 1.3M / 630K)
            if rid and vt:
                vt_norm = normalize_text(vt)

                tokens = re.findall(
                    r"\b\d{1,3}(?:,\d{3})+\b|\b\d+(?:\.\d+)?[KMB]\b|\b\d+\b",
                    vt_norm,
                    flags=re.I,
                )

                chosen = None
                tiny_candidate = None
                for tok in tokens:
                    v = parse_metric_int(tok)
                    if v is None:
                        continue
                    if v >= 100:
                        chosen = v
                        break
                    tiny_candidate = v

                if chosen is None and tiny_candidate is not None:
                    chosen = tiny_candidate

                if chosen is not None:
                    grid_views_by_shortcode.setdefault(rid, chosen)

            if u in seen:
                continue
            seen.add(u)
            collected.append(u)
            if len(collected) >= last_n:
                break
        if len(collected) >= last_n:
            break
        # scroll down a bit
        try:
            page.mouse.wheel(0, 1400)
        except Exception:
            pass
        page.wait_for_timeout(900)
        scroll_steps += 1

    if debug:
        print(f"reels_collected_count: {len(collected)}")
        print(f"first5_reel_urls: {json.dumps(collected[:5])}")
        if collected:
            print(f"newest_candidate_url: {collected[0]}")
            print(f"oldest_candidate_url: {collected[min(len(collected)-1, last_n-1)]}")

        # Grid overlay view mapping diagnostics
        try:
            print(f"grid_views_mapped_count: {len(grid_views_by_shortcode)}")
            sample = list(grid_views_by_shortcode.items())[:3]
            print(f"grid_views_sample_first3: {json.dumps([f'{k}:{v}' for k,v in sample])}")
        except Exception:
            pass

    if not collected:
        sp = save_screenshot(page, "no_reels_collected", enabled=save_screenshots)
        if debug and sp:
            print(f"screenshot: {sp}")
        raise RuntimeError("NO_POST_LINKS_FOUND")

    # PART B: metric extraction
    views_list: List[int] = []
    likes_list: List[int] = []
    comments_list: List[int] = []

    # For robust frequency: collect published datetimes
    published_dates: List[datetime] = []

    # Status counters
    comments_disabled_count = 0
    comments_disabled_or_limited_count = 0
    comments_suspicious_count = 0
    likes_hidden_count = 0
    likes_suspicious_count = 0
    suspicious_filtered_count = 0

    samples: List[Dict[str, Any]] = []
    outlier_count = 0

    blocked = False
    blocked_shortcode = ""
    blocked_url = ""
    scraped_success_count = 0

    for idx, u in enumerate(collected[:last_n]):
        # Global pacing / rate-limit to reduce IG blocks
        try:
            if idx > 0:
                time.sleep(random.uniform(2.0, 4.0))
                if (idx % 3) == 0:
                    time.sleep(random.uniform(6.0, 10.0))
        except Exception:
            pass

        try:
            page.goto(u, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
            handle_common_popups(page)
        except Exception:
            continue

        # Block/challenge detection on every reel open
        if detect_blocked_or_challenge(page):
            blocked = True
            blocked_url = u
            try:
                m = re.search(r"/reel/([^/]+)/", u)
                blocked_shortcode = m.group(1) if m else (f"idx{idx}")
            except Exception:
                blocked_shortcode = f"idx{idx}"
            try:
                p = DEBUG_DIR / f"parse_{blocked_shortcode}_blocked.png"
                page.screenshot(path=str(p), full_page=True)
            except Exception:
                p = None
            print(f"blocked_detected_on_reel={blocked_shortcode} url={u}")
            if debug and p is not None:
                try:
                    print(f"artifact_blocked_png: {str(p)} size_bytes={p.stat().st_size}")
                except Exception:
                    print(f"artifact_blocked_png: {str(p)}")
            print("blocked_or_challenge: True")
            print(f"partial_reels_scraped_count: {scraped_success_count}")
            print("Recommended: rerun with --last-n 5 and try later if challenge persists")
            # Stop processing further reels; allow partial aggregates.
            break

        rid = ""
        m = re.search(r"/reel/([^/]+)/", u)
        if m:
            rid = m.group(1)

        grid_views = grid_views_by_shortcode.get(rid) if rid else None

        likes, comments, views, published, views_source, published_source, wait_path_used, selector_strategy, fail_reason, views_dom_outlier, comments_status, likes_status = _extract_media_metrics(
            page,
            reel_url=u,
            shortcode=(rid or f"idx{idx}"),
            grid_views=grid_views,
            debug=debug,
            save_screenshots=bool(save_screenshots),
        )

        if views_dom_outlier:
            outlier_count += 1

        # statuses

        # If _extract_media_metrics detected disabled/suspicious comments, respect it.
        if comments_status in ("disabled", "disabled_or_limited"):
            comments_disabled_count += 1
        if comments_status == "disabled_or_limited":
            comments_disabled_or_limited_count += 1
        if comments_status == "suspicious":
            suspicious_filtered_count += 1
            comments_suspicious_count += 1
            if "comments_suspicious_filtered" not in trust_flags:
                trust_flags.append("comments_suspicious_filtered")

        # Likes status from reel parser
        if likes_status == "hidden_or_unavailable":
            likes_hidden_count += 1
            if "likes_hidden" not in trust_flags:
                trust_flags.append("likes_hidden")
        elif likes_status == "suspicious":
            likes_suspicious_count += 1

        # Sanity checks to avoid corrupting aggregates
        likes_for_agg = likes
        comments_for_agg = comments
        likes_suspicious = False
        comments_suspicious = False

        if comments_for_agg is not None and likes_for_agg is not None and comments_for_agg > likes_for_agg * 2:
            comments_suspicious = True
        if comments_for_agg is not None and views is not None and comments_for_agg > int(0.30 * float(views)):
            comments_suspicious = True
        if likes_for_agg is not None and views is not None and likes_for_agg > views:
            likes_suspicious = True

        if comments_suspicious:
            comments_for_agg = None
        if likes_suspicious:
            likes_for_agg = None
        if (comments_suspicious or likes_suspicious) and debug:
            print(
                f"metric_suspicious: {rid or ''} likes_suspicious={str(likes_suspicious)} comments_suspicious={str(comments_suspicious)}"
            )

        if (likes_for_agg is None and likes is not None) or (comments_for_agg is None and comments is not None):
            suspicious_filtered_count += 1

        # published timestamp tracking
        if published:
            try:
                dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                published_dates.append(dt)
            except Exception:
                pass

        # Count successful reels (for partial aggregates)
        if views is not None and published:
            scraped_success_count += 1

        if debug:
            print(
                "reel_debug: "
                f"{rid or ''} | likes={likes if likes is not None else ''} likes_status={likes_status} "
                f"| comments={comments if comments is not None else ''} comments_status={comments_status} "
                f"| views={views if views is not None else ''} views_source={views_source} "
                f"| published={published or ''} published_source={published_source} "
                f"| wait_path_used={wait_path_used} | selector_strategy={selector_strategy} | parse_failed_reason={fail_reason}"
            )

        samples.append(
            {
                "url": u,
                "views": views,
                "likes": likes,
                "comments": comments,
                "published": published or "",
                "likes_status": likes_status,
                "comments_status": comments_status,
                "likes_suspicious": likes_suspicious,
                "comments_suspicious": comments_suspicious,
            }
        )

        # Aggregation lists: only include values that survived filters
        if views is not None:
            views_list.append(views)
        if likes_for_agg is not None:
            likes_list.append(likes_for_agg)
        if comments_for_agg is not None:
            comments_list.append(comments_for_agg)

    # Partial aggregates on block (only if >=3 reels scraped successfully)
    partial_run = bool(blocked)
    if blocked:
        if "blocked_or_challenge" not in trust_flags:
            trust_flags.append("blocked_or_challenge")
        if scraped_success_count >= 3:
            if "partial_metrics_due_to_block" not in trust_flags:
                trust_flags.append("partial_metrics_due_to_block")

    if blocked and scraped_success_count < 3:
        avg_views = None
        avg_likes = None
        avg_comments = None
        med_views = None
        med_likes = None
        med_comments = None
    else:
        # Robust aggregates
        avg_views = mean(views_list)
        avg_likes = mean(likes_list)
        avg_comments = mean(comments_list)

        med_views = median(views_list)
        med_likes = median(likes_list)
        med_comments = median(comments_list)

    # Posting frequency windows (default 30d; also compute 90d)
    now_utc = datetime.now(timezone.utc)
    c30 = len([d for d in published_dates if d >= (now_utc - timedelta(days=30))])
    c90 = len([d for d in published_dates if d >= (now_utc - timedelta(days=90))])

    pfw_30d = (float(c30) / 30.0) * 7.0 if c30 > 0 else None
    pfw_90d = (float(c90) / 90.0) * 7.0 if c90 > 0 else None

    posting_frequency_per_week = pfw_30d
    posting_frequency_computed = posting_frequency_per_week is not None

    if blocked and scraped_success_count < 3:
        posting_frequency_per_week = None
        posting_frequency_computed = False

    if debug:
        if partial_run:
            print(f"partial_run=True scraped_count={scraped_success_count} requested_last_n={last_n}")
        print(f"views_used_count: {len(views_list)}")
        print(f"likes_used_count: {len(likes_list)}")
        print(f"comments_used_count: {len(comments_list)}")
        print(f"comments_suspicious_count: {comments_suspicious_count}")
        print(f"comments_disabled_count: {comments_disabled_count}")
        print(f"likes_hidden_count: {likes_hidden_count}")
        print(f"likes_suspicious_count: {likes_suspicious_count}")
        print(f"median_views_last_10: {'' if med_views is None else med_views}")
        print(f"median_likes_last_10: {'' if med_likes is None else med_likes}")
        print(f"median_comments_last_10: {'' if med_comments is None else med_comments}")
        print(f"trimmed_mean_views_last_10: {'' if avg_views is None else avg_views}")
        print(f"trimmed_mean_likes_last_10: {'' if avg_likes is None else avg_likes}")
        print(f"trimmed_mean_comments_last_10: {'' if avg_comments is None else avg_comments}")
        print(f"pfw_30d: {'' if pfw_30d is None else pfw_30d}")
        print(f"pfw_90d: {'' if pfw_90d is None else pfw_90d}")

    return {
        "items": collected,
        "samples": samples[-3:],
        "avg_views_last_10": avg_views,
        "avg_likes_last_10": avg_likes,
        "avg_comments_last_10": avg_comments,
        "median_views_last_10": med_views,
        "median_likes_last_10": med_likes,
        "median_comments_last_10": med_comments,
        "views_used_count": len(views_list),
        "likes_used_count": len(likes_list),
        "comments_used_count": len(comments_list),
        "comments_disabled_count": comments_disabled_count,
        "comments_suspicious_count": comments_suspicious_count,
        "likes_hidden_count": likes_hidden_count,
        "likes_suspicious_count": likes_suspicious_count,
        "suspicious_filtered_count": suspicious_filtered_count,
        "pfw_30d": pfw_30d,
        "pfw_90d": pfw_90d,
        "posting_frequency_per_week": posting_frequency_per_week,
        "posting_frequency_computed": bool(posting_frequency_computed),
        "views_dom_outlier_count": outlier_count,
        "html_dump_path": html_dump_path,
        "html_dump_size_bytes": html_dump_size,
    }


def open_links_modal(page, debug: bool = False) -> Tuple[bool, List[ExternalLinkItem], List[str]]:
    warnings: List[str] = []

    def try_click(loc, label: str) -> bool:
        try:
            if loc.count() > 0 and loc.first.is_visible(timeout=1200):
                loc.first.click(timeout=2500)
                if debug:
                    warnings.append(f"clicked:{label}")
                return True
        except Exception:
            return False
        return False

    clicked = False

    # A) "and N more"
    clicked = clicked or try_click(page.get_by_text(re.compile(r"and\s+\d+\s+more", re.I)), "and_more")

    # B) any "more links" or "links" near bio
    clicked = clicked or try_click(page.get_by_text(re.compile(r"more\s+links", re.I)), "more_links")
    clicked = clicked or try_click(page.get_by_text(re.compile(r"^links$", re.I)), "links_text")

    # C) link icon/button
    clicked = clicked or try_click(page.locator('svg[aria-label*="Link" i]').locator("xpath=.."), "link_icon")

    if not clicked:
        return False, [], warnings

    # Wait for modal/dialog heading "Links"
    dialog = page.locator('[role="dialog"]').first
    try:
        dialog.wait_for(state="visible", timeout=5000)
    except Exception:
        return False, [], warnings

    try:
        page.get_by_text(re.compile(r"^links$", re.I)).first.wait_for(timeout=3500)
    except Exception:
        # still proceed; some dialogs don't have explicit heading
        pass

    items: List[ExternalLinkItem] = []

    # Collect anchors within dialog
    try:
        anchors = dialog.locator('a[href]')
        n = anchors.count()
        for i in range(min(n, 50)):
            a = anchors.nth(i)
            href = a.get_attribute("href") or ""
            title = (a.inner_text() or "").strip()
            if href.startswith("/"):
                href = urllib.parse.urljoin("https://www.instagram.com", href)
            if not title:
                # sometimes only nested span
                try:
                    title = (a.text_content() or "").strip()
                except Exception:
                    title = ""
            if href or title:
                items.append(ExternalLinkItem(title=title, url=href))
    except Exception:
        pass

    # If no hrefs, try clickable rows and capture popup URL
    if not items:
        try:
            rows = dialog.locator("role=button")
            n = rows.count()
            for i in range(min(n, 25)):
                r = rows.nth(i)
                title = ""
                try:
                    title = (r.inner_text() or "").strip()
                except Exception:
                    pass
                url = ""
                try:
                    with page.expect_popup(timeout=2000) as pop:
                        r.click(timeout=1500)
                    p2 = pop.value
                    url = p2.url
                    p2.close()
                except Exception:
                    warnings.append("modal_item_no_href")
                if title or url:
                    items.append(ExternalLinkItem(title=title, url=url))
        except Exception:
            pass

    # close
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass

    return True, items, warnings


def extract_profile(
    page,
    canonical_url: str,
    handle_hint: str,
    debug: bool = False,
    accurate_metrics: bool = False,
    last_n: int = 10,
    headed: bool = False,
    save_screenshots: bool = False,
) -> Tuple[IGProfileData, Dict[str, Any]]:
    _wait_profile_loaded(page, canonical_url)

    if detect_blocked_or_challenge(page):
        raise RuntimeError("BLOCKED_OR_CHALLENGE")

    # Handle + display name + bio text
    js_basic = r"""
() => {
  const out = {handle:null, display_name:null, bio_text:''};
  out.handle = location.pathname.split('/').filter(Boolean)[0] || null;
  const h2 = document.querySelector('header h2');
  if (h2 && h2.textContent) out.display_name = h2.textContent.trim();
  const h1 = document.querySelector('header h1');
  if ((!out.display_name) && h1 && h1.textContent) out.display_name = h1.textContent.trim();
  const bioDiv = document.querySelector('header section div.-vDIg') || document.querySelector('header section');
  if (bioDiv) {
    const txt = bioDiv.innerText || '';
    if (txt) out.bio_text = txt.trim();
  }
  if (!out.bio_text) {
    const header = document.querySelector('header');
    const txt2 = header ? (header.innerText || '') : '';
    if (txt2) out.bio_text = txt2.trim();
  }
  return out;
}
"""
    b = page.evaluate(js_basic)
    handle = normalize_text(b.get("handle") or handle_hint or "")
    display_name = normalize_text(b.get("display_name") or "") or None
    bio_text = normalize_text(b.get("bio_text") or "")

    # Counts: try A) header row
    raw_followers_header = None
    parsed_followers_header = None
    raw_followers_meta = None
    parsed_followers_meta = None

    followers_h, following, posts = _extract_counts_from_header_row(page)

    # Capture raw header followers text for debug (best-effort)
    try:
        raw_followers_header = page.evaluate(
            """
() => {
  const a = document.querySelector('a[href$="/followers/"]');
  if (!a) return null;
  const s = a.querySelector('span');
  return (s?.getAttribute('aria-label') || a.getAttribute('aria-label') || s?.textContent || a.textContent || '').trim() || null;
}
"""
        )
        raw_followers_header = normalize_text(raw_followers_header)
    except Exception:
        raw_followers_header = None

    # Prefer parsing from raw aria/text if available
    parsed_followers_header = parse_metric_int(raw_followers_header) if raw_followers_header else followers_h
    followers_h = parsed_followers_header

    # B) meta og:description
    try:
        raw_followers_meta = normalize_text(page.locator('meta[property="og:description"]').get_attribute("content") or "")
    except Exception:
        raw_followers_meta = ""

    mf, mfo, mp = _parse_counts_from_meta_desc(raw_followers_meta)
    parsed_followers_meta = mf

    # Choose followers: ALWAYS prefer header if parsed successfully (meta often rounded)
    chosen_followers_source = "none"
    followers = None
    trust_flags: List[str] = []

    if followers_h is not None:
        followers = followers_h
        chosen_followers_source = "header"
        # discrepancy flag vs meta if both exist
        if mf is not None and mf > 0:
            diff_ratio = abs(float(followers_h) - float(mf)) / float(mf)
            if diff_ratio > 0.25:
                trust_flags.append("followers_discrepancy_meta_vs_header")
    elif mf is not None:
        followers = mf
        chosen_followers_source = "meta"

    # Fill missing following/posts from meta if needed
    following = following if following is not None else mfo
    posts = posts if posts is not None else mp

    # C) JSON in page html for any missing
    if following is None or posts is None or followers is None:
        try:
            html = page.content()
        except Exception:
            html = ""
        jf, jfo, jp = _extract_counts_from_json(html)
        if followers is None:
            followers = jf
            chosen_followers_source = "json" if jf is not None else chosen_followers_source
        following = following if following is not None else jfo
        posts = posts if posts is not None else jp

    # Links modal + bio urls
    modal_opened, modal_items, warnings = open_links_modal(page, debug=debug)

    # bio urls
    bio_urls = extract_urls_from_text(bio_text)

    external_links: List[ExternalLinkItem] = []
    external_links.extend(modal_items)
    for u in bio_urls:
        external_links.append(ExternalLinkItem(title="bio", url=u))

    # normalize modal/link titles before email scan
    external_links = [ExternalLinkItem(title=normalize_text(it.title), url=(it.url or "")) for it in external_links]

    # emails from bio text + meta text + modal titles/urls
    visible_text = normalize_text(bio_text) + "\n" + normalize_text(raw_followers_meta) + "\n" + "\n".join([normalize_text(it.title) for it in external_links])
    emails = set(e.lower() for e in EMAIL_RE.findall(visible_text))
    for it in external_links:
        if (it.url or "").startswith("mailto:"):
            addr = (it.url or "").split(":", 1)[1].split("?", 1)[0]
            if addr:
                emails.add(addr.lower())
        for e in EMAIL_RE.findall(it.url or ""):
            emails.add(e.lower())

    # Contact buttons/modal
    for e in extract_emails_from_contact_buttons(page):
        emails.add(e.lower())

    emails_list = sorted(emails)

    # choose external website ignoring meta domains
    # Normalize redirector URLs before storage/choice
    unwrapped_count = 0
    normalized_links: List[ExternalLinkItem] = []
    for it in external_links:
        u = it.url or ""
        if u:
            u, did = unwrap_instagram_redirect(u)
            if did:
                unwrapped_count += 1
        normalized_links.append(ExternalLinkItem(title=it.title, url=u))
    external_links = normalized_links

    # Also normalize modal_items so samples show real URLs
    normalized_modal: List[ExternalLinkItem] = []
    for it in modal_items:
        u = it.url or ""
        if u:
            u, _did = unwrap_instagram_redirect(u)
        normalized_modal.append(ExternalLinkItem(title=it.title, url=u))
    modal_items = normalized_modal

    # Build external_links_json + choose contact/primary
    external_links_json, threads_ignored_count = build_external_links_json(external_links)
    contact_website = detect_contact_website(external_links)
    primary_website, primary_reason = choose_primary_website(external_links, contact_website, emails_list)

    # Final sanitizer: primary_website/external_website must be http(s) only.
    def is_http_url(u: Any) -> bool:
        return isinstance(u, str) and (u.startswith("http://") or u.startswith("https://"))

    # email_used_as_website must always be False (sanitizer ensures no email is stored as website)
    email_used_as_website = False
    if primary_website and not is_http_url(primary_website):
        primary_website = ""
        primary_reason = "no_primary_http_url"

    # For debug: filtered domains summary
    filtered = {
        "total": len(external_links),
        "meta_ignored": len([it for it in external_links if is_meta_domain(domain_of(it.url or ""))]),
        "kept": len([it for it in external_links if it.url]),
    }

    # linktree detection from any link
    # (stored later in DB)

    sample_titles = [it.title for it in modal_items[:5]]
    sample_urls = [it.url for it in modal_items[:5]]

    # Accurate engagement metrics (optional)
    avg_views_last_10 = None
    avg_likes_last_10 = None
    avg_comments_last_10 = None
    posting_frequency_per_week = None
    posting_frequency_per_week_90d = None
    scraped_last3: List[Dict[str, Any]] = []
    posting_freq_computed = False

    if accurate_metrics:
        m = scrape_accurate_engagement(
            page,
            canonical_url,
            last_n=max(1, int(last_n)),
            debug=bool(debug),
            headed=bool(headed),
            save_screenshots=bool(save_screenshots),
        )
        avg_views_last_10 = m.get("avg_views_last_10")
        avg_likes_last_10 = m.get("avg_likes_last_10")
        avg_comments_last_10 = m.get("avg_comments_last_10")
        posting_frequency_per_week = m.get("posting_frequency_per_week")
        posting_frequency_per_week_90d = m.get("pfw_90d")
        posting_freq_computed = bool(m.get("posting_frequency_computed"))
        scraped_last3 = m.get("samples") or []

        outlier_count = int(m.get("views_dom_outlier_count") or 0)
        if outlier_count > 0 and "views_dom_outlier" not in trust_flags:
            trust_flags.append("views_dom_outlier")

        susp_filtered = int(m.get("suspicious_filtered_count") or 0)
        if susp_filtered > 0 and "comments_suspicious_filtered" not in trust_flags:
            trust_flags.append("comments_suspicious_filtered")

        # High-level summary flag
        if any(
            f in trust_flags
            for f in (
                "views_dom_outlier",
                "comments_disabled_or_limited",
                "comments_suspicious_filtered",
                "likes_hidden",
            )
        ) and "engagement_metric_suspicious_filtered" not in trust_flags:
            trust_flags.append("engagement_metric_suspicious_filtered")

        total_items = len(m.get("items") or [])
        likes_used = int(m.get("likes_used_count") or 0)
        comments_used = int(m.get("comments_used_count") or 0)
        likes_hidden = int(m.get("likes_hidden_count") or 0)
        comments_disabled = int(m.get("comments_disabled_count") or 0)

        likes_all_hidden = bool(total_items > 0 and likes_used == 0 and likes_hidden == total_items)
        comments_all_disabled = bool(total_items > 0 and comments_used == 0 and comments_disabled == total_items)

        # Enforce flags if insufficient
        if avg_views_last_10 is None and avg_likes_last_10 is None and avg_comments_last_10 is None:
            trust_flags.append("missing_engagement_metrics")
        else:
            # If BOTH likes+comments missing for reasons other than hidden/disabled, flag.
            if likes_used == 0 and comments_used == 0 and not (likes_all_hidden and comments_all_disabled):
                trust_flags.append("missing_engagement_metrics")

        if not posting_freq_computed:
            trust_flags.append("missing_posting_frequency")

    # Build a bio JSON block
    bio_block = {
        "external_links": [{"title": it.title, "url": it.url} for it in external_links],
        "emails": emails_list,
        "modal_warnings": warnings,
        "trust_flags": trust_flags,
        "accurate_metrics": bool(accurate_metrics),
    }
    bio_final = (bio_text or "").strip()
    append = "\n\n[external_links]=" + json.dumps(bio_block, sort_keys=True)
    if "[external_links]=" not in bio_final:
        bio_final = (bio_final + append).strip() if bio_final else append.strip()

    return IGProfileData(
        canonical_url=canonical_url,
        handle=handle,
        display_name=display_name,
        followers=followers,
        following=following,
        posts=posts,
        bio_text=bio_final,
        external_links=external_links,
        external_links_json=external_links_json,
        emails=emails_list,
        contact_website=contact_website,
        primary_website=primary_website,
        primary_reason=primary_reason,
        filtered_domains=filtered,
        unwrapped_urls_count=unwrapped_count,
        modal_opened=modal_opened,
        modal_items_found=len(modal_items),
        sample_modal_titles=sample_titles,
        sample_modal_urls=sample_urls,
        avg_views_last_10=avg_views_last_10,
        avg_likes_last_10=avg_likes_last_10,
        avg_comments_last_10=avg_comments_last_10,
        posting_frequency_per_week=posting_frequency_per_week,
        posting_frequency_per_week_90d=posting_frequency_per_week_90d,
    ), {
        "raw_followers_header": raw_followers_header,
        "parsed_followers_header": parsed_followers_header,
        "raw_followers_meta": raw_followers_meta,
        "parsed_followers_meta": parsed_followers_meta,
        "chosen_followers_source": chosen_followers_source,
        "trust_flags": trust_flags,
        "chosen_external_website_reason": primary_reason,
        "unwrapped_urls_count": unwrapped_count,
        "threads_ignored_count": threads_ignored_count,
        "contact_website": contact_website,
        "primary_website": primary_website,
        "primary_reason": primary_reason,
        "external_website": primary_website,
        "email_used_as_website": bool(email_used_as_website),
        "external_links_json_count": len(json.loads(external_links_json)) if external_links_json else 0,
        "external_links_json_first2": json.loads(external_links_json)[:2] if external_links_json else [],
        "bio_text_len": len(bio_text),
        "bio_text_preview": repr(bio_text[:200]),
        "meta_text_len": len(raw_followers_meta),
        "meta_text_preview": repr(raw_followers_meta[:200]),
        "emails_found_count": len(emails_list),
        "emails_found": emails_list,
        "accurate_metrics": bool(accurate_metrics),
        "accurate_last3": scraped_last3,
        "avg_views_last_10": avg_views_last_10,
        "avg_likes_last_10": avg_likes_last_10,
        "avg_comments_last_10": avg_comments_last_10,
        "posting_frequency_per_week": posting_frequency_per_week,
        "posting_frequency_computed": bool(posting_freq_computed),
    }


def upsert_profile(con: sqlite3.Connection, p: IGProfileData, dry_run: bool) -> Tuple[str, str, str, Optional[str], Optional[str]]:
    """Returns (creator_id_str, social_profile_id_str, external_website, primary_website, contact_website)."""
    now = utc_now_iso()

    # Back-compat: external_website mirrors primary_website (http(s) only)
    chosen = p.primary_website
    if not (isinstance(chosen, str) and (chosen.startswith("http://") or chosen.startswith("https://"))):
        chosen = ""

    # linktree (ignore threads/meta)
    ltd = None
    for it in p.external_links:
        u = normalize_text(it.url)
        host = domain_of(u)
        if is_threads_domain(host) or is_meta_domain(host):
            continue
        ltd = linktree_domain(u)
        if ltd:
            break

    existing = con.execute(
        "SELECT id, creator_id FROM social_profiles WHERE profile_url=?",
        (p.canonical_url,),
    ).fetchone()

    if existing:
        social_profile_id = int(existing[0])
        creator_id = existing[1]

        if dry_run:
            return (str(creator_id) if creator_id is not None else ""), str(social_profile_id), (chosen or ""), p.primary_website, p.contact_website

        # contact emails: do not overwrite non-empty unless new list is non-empty and different
        existing_email_json = con.execute(
            "SELECT contact_emails_json FROM social_profiles WHERE id=?",
            (social_profile_id,),
        ).fetchone()[0]
        new_email_json = json.dumps(p.emails) if p.emails else None
        if existing_email_json and existing_email_json.strip() not in ("", "[]"):
            if new_email_json and new_email_json != existing_email_json:
                email_to_store = new_email_json
            else:
                email_to_store = existing_email_json
        else:
            email_to_store = new_email_json

        updates = {
            "handle": p.handle,
            "display_name": p.display_name,
            "bio": p.bio_text,
            "external_website": chosen,
            "primary_website": p.primary_website,
            "contact_website": p.contact_website,
            "external_links_json": p.external_links_json,
            "contact_emails_json": email_to_store,
            "linktree_domain": ltd,
            "followers": p.followers,
            "following": p.following,
            "posts": p.posts,
            "avg_views_last_10": p.avg_views_last_10,
            "avg_likes_last_10": p.avg_likes_last_10,
            "avg_comments_last_10": p.avg_comments_last_10,
            "posting_frequency_per_week": p.posting_frequency_per_week,
            "posting_frequency_per_week_90d": p.posting_frequency_per_week_90d,
            "stats_status": "ok",
            "data_confidence": "high",
            "last_fetched_at": now,
            "updated_at": now,
        }
        set_clause = ", ".join([f"{k}=?" for k in updates.keys()])
        con.execute(f"UPDATE social_profiles SET {set_clause} WHERE id=?", (*updates.values(), social_profile_id))

        con.execute(
            """
            INSERT INTO profile_snapshots(
              social_profile_id, followers, total_views,
              avg_views_last_10, avg_likes_last_10, avg_comments_last_10,
              posting_frequency_per_week, timestamp
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                social_profile_id,
                p.followers,
                None,
                p.avg_views_last_10,
                p.avg_likes_last_10,
                p.avg_comments_last_10,
                p.posting_frequency_per_week,
                now,
            ),
        )
        return (str(creator_id) if creator_id is not None else ""), str(social_profile_id), (chosen or ""), p.primary_website, p.contact_website

    if dry_run:
        return "dry-run", "dry-run", (chosen or ""), p.primary_website, p.contact_website

    # Insert new creator + profile + snapshot
    primary_name = p.display_name or p.handle
    cur = con.execute(
        "INSERT INTO creators(primary_name, linktree_domain, created_at) VALUES(?,?,?)",
        (primary_name, None, now),
    )
    creator_id = int(cur.lastrowid)

    cur = con.execute(
        """
        INSERT INTO social_profiles(
          creator_id, platform, profile_url, handle, display_name, bio,
          external_website, primary_website, contact_website, external_links_json,
          contact_emails_json,
          linktree_domain, profile_image_hash,
          followers, following, posts, total_views,
          avg_views_last_10, avg_likes_last_10, avg_comments_last_10,
          posting_frequency_per_week,
          data_confidence, identity_status, source,
          stats_status,
          created_at, last_fetched_at
        ) VALUES(
          ?, 'instagram', ?, ?, ?, ?,
          ?, ?, ?, ?,
          ?,
          ?, NULL,
          ?, ?, ?, NULL,
          ?, ?, ?,
          ?,
          'high', 'standalone', 'discovered',
          'ok',
          ?, ?
        )
        """,
        (
            creator_id,
            p.canonical_url,
            p.handle,
            p.display_name,
            p.bio_text,
            chosen,
            p.primary_website,
            p.contact_website,
            p.external_links_json,
            (json.dumps(p.emails) if p.emails else None),
            ltd,
            p.followers,
            p.following,
            p.posts,
            p.avg_views_last_10,
            p.avg_likes_last_10,
            p.avg_comments_last_10,
            p.posting_frequency_per_week,
            now,
            now,
        ),
    )
    social_profile_id = int(cur.lastrowid)

    con.execute(
        """
        INSERT INTO profile_snapshots(
          social_profile_id, followers, total_views,
          avg_views_last_10, avg_likes_last_10, avg_comments_last_10,
          posting_frequency_per_week, timestamp
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            social_profile_id,
            p.followers,
            None,
            p.avg_views_last_10,
            p.avg_likes_last_10,
            p.avg_comments_last_10,
            p.posting_frequency_per_week,
            now,
        ),
    )

    return str(creator_id), str(social_profile_id), (chosen or ""), p.primary_website, p.contact_website


def read_urls_file(path: str) -> List[str]:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"File not found: {path}")
    urls: List[str] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        urls.append(s)
    return urls


def run_ingest(
    urls: List[str],
    dry_run: bool,
    debug: bool,
    accurate_metrics: bool = False,
    last_n: int = 10,
    headed: bool = False,
    save_screenshots: bool = False,
    rate_limit: bool = True,
) -> int:
    PW_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    # If headed requested but no X/Wayland display is available, fall back to headless.
    if headed and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        print("WARNING: headed requested but no DISPLAY found; falling back to headless. Use xvfb-run for headed mode in WSL.")
        headed = False

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(PW_PROFILE_DIR),
            headless=(not headed),
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()

        # login check
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1000)
        if detect_blocked_or_challenge(page):
            ctx.close()
            print("BLOCKED_OR_CHALLENGE")
            return 2
        if not (_has_session_cookie(ctx) or is_logged_in(page)):
            ctx.close()
            print("SESSION_EXPIRED: please run with --login")
            return 1

        con = connect_db()
        try:
            for i, u in enumerate(urls):
                canonical, handle = normalize_url(u)

                if rate_limit and i > 0:
                    time.sleep(random.uniform(3.0, 6.0))

                try:
                    prof, dbg = extract_profile(
                        page,
                        canonical,
                        handle,
                        debug=debug,
                        accurate_metrics=accurate_metrics,
                        last_n=last_n,
                        headed=headed,
                        save_screenshots=save_screenshots,
                    )
                except RuntimeError as e:
                    if str(e) == "BLOCKED_OR_CHALLENGE":
                        print("BLOCKED_OR_CHALLENGE")
                        return 2
                    raise

                # Choose best external website + store all links
                creator_id, social_profile_id, chosen_external, primary_website, contact_website = upsert_profile(con, prof, dry_run=dry_run)
                if not dry_run:
                    con.commit()
                    # rescore instagram so trust_score is computed
                    try:
                        import score_profiles  # type: ignore

                        # score just this id
                        score_profiles.main  # keep linter quiet
                        # shell out via python API: reuse score_instagram
                        # Fetch updated row
                        con2 = sqlite3.connect(DB_PATH)
                        con2.row_factory = sqlite3.Row
                        r = con2.execute("SELECT * FROM social_profiles WHERE id=?", (int(social_profile_id),)).fetchone()
                        con2.close()
                        if r is not None and r['platform'] == 'instagram':
                            reach, auth, trust, flags = score_profiles.score_instagram(
                                r['followers'], r['posts'], r['avg_likes_last_10'], r['avg_comments_last_10'],
                                r['posting_frequency_per_week'], (r['stats_status'] or 'missing_public').lower(),
                                (r['data_confidence'] or 'low').lower()
                            )
                            con.execute(
                                "UPDATE social_profiles SET reach_ratio=?, authenticity_score=?, trust_score=?, trust_flags=?, updated_at=? WHERE id=?",
                                (reach, auth, trust, json.dumps(flags), utc_now_iso(), int(social_profile_id)),
                            )
                            con.commit()
                    except Exception:
                        pass

                # Output (always)
                print(f"display_name: {prof.display_name or ''}")
                print(f"handle: @{prof.handle}")
                print(f"canonical_url: {prof.canonical_url}")
                print(f"followers: {prof.followers if prof.followers is not None else ''}")
                print(f"following: {prof.following if prof.following is not None else ''}")
                print(f"posts: {prof.posts if prof.posts is not None else ''}")

                if accurate_metrics:
                    # print last 3 items scraped
                    for it in (dbg.get('accurate_last3') or []):
                        print(
                            f"scraped_item: {it.get('url','')} | views={it.get('views','')} | likes={it.get('likes','')} | comments={it.get('comments','')} | published={it.get('published','')}"
                        )
                    print(f"avg_views_last_10: {'' if dbg.get('avg_views_last_10', None) is None else dbg.get('avg_views_last_10')}")
                    print(f"avg_likes_last_10: {'' if dbg.get('avg_likes_last_10', None) is None else dbg.get('avg_likes_last_10')}")
                    print(f"avg_comments_last_10: {'' if dbg.get('avg_comments_last_10', None) is None else dbg.get('avg_comments_last_10')}")
                    print(
                        f"posting_frequency_per_week: {'' if dbg.get('posting_frequency_per_week', None) is None else dbg.get('posting_frequency_per_week')}"
                    )
                    print(f"posting_frequency_computed: {str(bool(dbg.get('posting_frequency_computed', False)))}")

                # Derive linktree domain from any link
                ltd = None
                for it in prof.external_links:
                    ltd = linktree_domain(it.url)
                    if ltd:
                        break

                print(f"external_website: {chosen_external or ''}")
                print(f"linktree_domain: {ltd or ''}")

                if dry_run:
                    print(f"modal_items_found: {prof.modal_items_found}")
                    print(f"unwrapped_urls_count: {dbg.get('unwrapped_urls_count', 0)}")
                    print(f"contact_website: {dbg.get('contact_website','') or ''}")
                    print(f"primary_website: {dbg.get('primary_website','') or ''}")
                    print(f"primary_website_reason: {dbg.get('primary_reason','') or ''}")
                    print(f"external_website: {dbg.get('external_website','') or ''}")
                    print(f"email_used_as_website: {str(bool(dbg.get('email_used_as_website', False)))}")
                    print(f"bio_text_len: {dbg.get('bio_text_len', 0)}")
                    print(f"bio_text_preview: {dbg.get('bio_text_preview', '')}")
                    print(f"meta_text_len: {dbg.get('meta_text_len', 0)}")
                    print(f"meta_text_preview: {dbg.get('meta_text_preview', '')}")
                    print(f"emails_found_count: {dbg.get('emails_found_count', 0)}")
                    print(f"emails_found: {json.dumps(dbg.get('emails_found', []))}")
                    preview = json.dumps(dbg.get('emails_found', [])) if dbg.get('emails_found', None) else ""
                    print(f"stored_contact_emails_json_preview: {preview[:120]}")
                    print(f"trust_flags: {json.dumps(dbg.get('trust_flags', []))}")

                    # external_links_json summary
                    first2 = dbg.get('external_links_json_first2', [])
                    print(f"threads_ignored_count: {dbg.get('threads_ignored_count', 0)}")
                    print(f"external_links_json_count: {dbg.get('external_links_json_count', 0)}")
                    print(f"external_links_json_first2: {json.dumps(first2, sort_keys=True)}")

                    # existing debug
                    print(f"links_found_count: {len(prof.external_links)}")
                    print(f"emails_found: {json.dumps(prof.emails)}")
                    print(f"filtered_domains: {json.dumps(prof.filtered_domains, sort_keys=True)}")
                    print(f"raw_followers_header: {dbg.get('raw_followers_header', '')}")
                    print(f"parsed_followers_header: {dbg.get('parsed_followers_header', '') if dbg.get('parsed_followers_header', None) is not None else ''}")
                    print(f"raw_followers_meta: {dbg.get('raw_followers_meta', '')}")
                    print(f"parsed_followers_meta: {dbg.get('parsed_followers_meta', '') if dbg.get('parsed_followers_meta', None) is not None else ''}")
                    print(f"chosen_followers_source: {dbg.get('chosen_followers_source', '')}")
                    print(f"modal_opened: {str(bool(prof.modal_opened))}")
                    print(f"sample_modal_titles: {json.dumps(prof.sample_modal_titles)}")
                    print(f"sample_modal_urls: {json.dumps(prof.sample_modal_urls)}")

                print(f"creator_id: {creator_id}")
                print(f"social_profile_id: {social_profile_id}")
                print("identity_suggestions_created: 0")

        finally:
            con.close()
            ctx.close()

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--file", default=None)
    ap.add_argument("--profile-url", dest="profile_url", default=None)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--accurate-metrics", action="store_true")
    ap.add_argument("--last-n", type=int, default=10)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--save-screenshots", action="store_true")
    ap.add_argument("url", nargs="?")
    args = ap.parse_args()

    if args.login:
        return do_login()

    urls: List[str] = []
    if args.file:
        urls.extend(read_urls_file(args.file))
    if args.profile_url:
        urls.append(args.profile_url)
    if args.url:
        urls.append(args.url)

    if not urls:
        print("Missing URL or --file")
        return 2

    try:
        return run_ingest(
            urls,
            dry_run=args.dry_run,
            debug=args.debug,
            accurate_metrics=bool(args.accurate_metrics),
            last_n=int(args.last_n),
            headed=bool(args.headed),
            save_screenshots=bool(args.save_screenshots),
        )
    except PWTimeoutError:
        print("BLOCKED_OR_CHALLENGE")
        return 2
    except Exception as e:
        print(str(e))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
