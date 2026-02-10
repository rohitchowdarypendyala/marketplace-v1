import re, sys
from pathlib import Path

p = Path("/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/scripts/instagram_ingest_playwright.py")
s = p.read_text(encoding="utf-8")

m = re.search(r"^def _extract_media_metrics\b", s, re.M)
if not m:
    print("PATCH_FAIL: could not find def _extract_media_metrics")
    sys.exit(2)
start = m.start()

m2 = re.search(r"^(def |class )", s[m.end():], re.M)
end = (m.end() + m2.start()) if m2 else len(s)
block = s[start:end]

# Guard: don't double-inject only if our marker is present
if "BEGIN PATCH: views sanity" in block:
    print("PATCH_SKIP: patch markers already present in _extract_media_metrics")
    sys.exit(0)

ret_matches = list(re.finditer(r"^\s{4}return\b", block, re.M))
if not ret_matches:
    print("PATCH_FAIL: could not find an indented return inside _extract_media_metrics")
    sys.exit(3)
ret = ret_matches[-1].start()
head = block[:ret]
tail = block[ret:]

INJECT = r'''    # --- BEGIN PATCH: views sanity + comments disabled probe (surgical) ---
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
                    trust_flags.append("views_dom_suspicious")
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
'''

new_block = head + INJECT + tail
new_s = s[:start] + new_block + s[end:]
p.write_text(new_s, encoding="utf-8")
print("PATCH_OK: injected views sanity + comments disabled probe into _extract_media_metrics")
