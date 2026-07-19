"""engine.marketing.links — Funnel W1a (docket D07): canonical UTM link builder + static short-link lane.

Every clickable URL a post carries is the tagged canonical link, tagged exactly once.
Deterministic; no RNG; no server-side redirects (static-site law).

No stale-code pruning for short-link pages: post ids are stable across rebuilds, so
old codes are harmless and pruning would require a live inventory comparison.
"""
from __future__ import annotations

import base64
import hashlib
import html
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_BASE_URL: str = "https://mastermind-x.com/"
DEFAULT_UTM_SOURCE: str = "x"

# ─────────────────────────────────────────────────────────────────────────────
# Config helper
# ─────────────────────────────────────────────────────────────────────────────


def links_cfg(cfg: dict | None) -> dict:
    """Read links config from the marketing cfg dict; apply defaults.

    Returns a dict with keys:
      base_url    — normalized to trailing "/"
      utm_source  — default "x"
      short_links — bool, default True
    """
    raw: dict = (cfg or {}).get("links", {}) or {}
    base_url: str = str(raw.get("base_url", None) or DEFAULT_BASE_URL)
    # Normalize: exactly one trailing slash
    base_url = base_url.rstrip("/") + "/"
    return {
        "base_url": base_url,
        "utm_source": str(raw.get("utm_source", None) or DEFAULT_UTM_SOURCE),
        "short_links": bool(raw.get("short_links", True)),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Core URL builders
# ─────────────────────────────────────────────────────────────────────────────


def canonical_link(
    account_id: str,
    content_kind: str,
    post_id: str,
    *,
    base_url: str | None = None,
    utm_source: str | None = None,
) -> str:
    """Return the canonical UTM-tagged link for a post.

    URL form: {base}?utm_source={src}&utm_medium={account}&utm_campaign={kind}&utm_content={post_id}

    Param order is fixed. Each value is percent-encoded. Empty/None values
    sanitize to the string "unknown".
    """
    base = (base_url or DEFAULT_BASE_URL).rstrip("/") + "/"
    src = utm_source or DEFAULT_UTM_SOURCE

    def _enc(v: str | None) -> str:
        s = (v or "").strip()
        return quote(s, safe="") if s else "unknown"

    qs = (
        f"utm_source={_enc(src)}"
        f"&utm_medium={_enc(account_id)}"
        f"&utm_campaign={_enc(content_kind)}"
        f"&utm_content={_enc(post_id)}"
    )
    return f"{base}?{qs}"


def short_code(post_id: str) -> str:
    """Return a 10-character stable base32 code derived from post_id.

    Charset: [a-z2-7]. Deterministic — same post_id always yields same code.
    """
    digest = hashlib.sha256(post_id.encode("utf-8")).digest()
    return base64.b32encode(digest).decode("ascii").lower().rstrip("=")[:10]


def short_link(post_id: str, *, base_url: str | None = None) -> str:
    """Return the static short-link URL for a post (directory-index form).

    Form: {base}go/{code}/

    The trailing slash ensures static hosts serve index.html without a redirect
    or rewrite rule.
    """
    base = (base_url or DEFAULT_BASE_URL).rstrip("/") + "/"
    code = short_code(post_id)
    return f"{base}go/{code}/"


def is_tagged_canonical(url: str, *, base_url: str | None = None) -> bool:
    """Return True iff url starts with the base_url host and carries all four utm_* params."""
    base = (base_url or DEFAULT_BASE_URL).rstrip("/") + "/"
    try:
        parsed = urlsplit(url)
        base_parsed = urlsplit(base)
        if parsed.netloc != base_parsed.netloc:
            return False
        qs = parse_qs(parsed.query)
        for param in ("utm_source", "utm_medium", "utm_campaign", "utm_content"):
            if param not in qs or not qs[param]:
                return False
        return True
    except Exception:  # noqa: BLE001
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Text tagging helpers
# ─────────────────────────────────────────────────────────────────────────────

# Small cache so _base_re() doesn't recompile the same pattern repeatedly.
_BASE_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _base_re(base_url: str | None = None) -> re.Pattern[str]:
    """Return a compiled regex matching base-domain URL occurrences in text.

    Matches: optional https?://, optional www., the domain, optional path/query
    (non-whitespace), stripped of trailing sentence punctuation (.,;:!?)]}.
    """
    base = (base_url or DEFAULT_BASE_URL).rstrip("/") + "/"
    host = urlsplit(base).netloc or base.split("/")[2]
    if host not in _BASE_RE_CACHE:
        escaped = re.escape(host)
        # Match optional scheme+www, the host, optional path/query (non-space chars),
        # but do NOT eat trailing sentence punctuation
        _BASE_RE_CACHE[host] = re.compile(
            r"(?:https?://)?(?:www\.)?" + escaped + r"(?:[^\s]*)?",
            re.IGNORECASE,
        )
    return _BASE_RE_CACHE[host]


def tag_text(
    text: str,
    canonical: str,
    *,
    base_url: str | None = None,
    keep: tuple[str, ...] = (),
) -> tuple[str, int]:
    """Replace every untagged base-domain URL in text with canonical.

    - Occurrences already equal to canonical (or any URL in *keep*, e.g. the
      post's own short link) are left alone.
    - Non-base-domain URLs are untouched.
    - After replacement, if canonical appears more than once, keep the first and
      remove the rest; collapse doubled spaces and strip.
    - Returns (new_text, n_rewritten).
    - Idempotent: calling twice yields 0 rewrites and identical text.
    """
    pattern = _base_re(base_url)
    n_rewritten = 0

    def _replace(m: re.Match[str]) -> str:
        nonlocal n_rewritten
        raw = m.group(0)
        # Trailing sentence punctuation is prose, not URL — split it off and
        # re-append AFTER a space: punctuation concatenated straight onto the
        # canonical query string would pollute utm_content for any linkifier
        # that scans to whitespace ("…utm_content=p1?" parses content as "p1?").
        stripped = raw.rstrip(".,;:!?)]}")
        suffix = raw[len(stripped):]
        if stripped == canonical or stripped in keep:
            return raw  # already one of our tagged links — leave untouched
        n_rewritten += 1
        return canonical + (" " + suffix if suffix else "")

    result = pattern.sub(_replace, text)

    # Deduplicate: keep only the first occurrence of canonical
    first_pos = result.find(canonical)
    if first_pos != -1:
        after_first = result[first_pos + len(canonical):]
        if canonical in after_first:
            # Count and remove subsequent occurrences
            parts = after_first.split(canonical)
            n_extra = len(parts) - 1
            n_rewritten = max(0, n_rewritten - n_extra)  # adjust: dedup extras were already counted
            after_first = " ".join(parts)
            result = result[: first_pos + len(canonical)] + after_first

    # Collapse doubled spaces
    result = re.sub(r" {2,}", " ", result).strip()
    return result, n_rewritten


# ─────────────────────────────────────────────────────────────────────────────
# Plan iteration
# ─────────────────────────────────────────────────────────────────────────────


def iter_plan_posts(plan: dict):
    """Yield every queue-item dict from plan["accounts"][*]["queue"]."""
    for acct in plan.get("accounts", []):
        for item in acct.get("queue", []):
            yield item


# ─────────────────────────────────────────────────────────────────────────────
# Content Studio wiring
# ─────────────────────────────────────────────────────────────────────────────


def attach_links(account_rows: list[dict], cfg: dict | None = None) -> dict:
    """Attach canonical UTM links to every queue item in account_rows.

    For every item in every account row's queue:
      - Sets item["link"] = canonical_link(...)
      - Sets item["short_code"] and item["short_link"] when short_links is on
      - Runs tag_text over item["headline"] and item["body"]

    Returns a summary dict with posts_linked, urls_rewritten, note.

    Idempotent: calling twice yields identical items.
    """
    lcfg = links_cfg(cfg)
    base_url = lcfg["base_url"]
    utm_source = lcfg["utm_source"]
    do_short = lcfg["short_links"]

    # Copy is validated BEFORE links are attached; retagging can lengthen a
    # post past the copywriter budget (headline + 1 + body > _MAX_CHARS).
    # When it does, fall back to the short link in-text (it redirects to the
    # canonical, so attribution is preserved); if still over, flag the item —
    # printed, not hidden.
    try:
        from engine.marketing.copywriter import _MAX_CHARS as _max_chars  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        _max_chars = 275

    posts_linked = 0
    urls_rewritten = 0
    overflow_shortened = 0
    overflow_flagged = 0

    for acct_row in account_rows:
        for item in acct_row.get("queue", []):
            account = item.get("account", "") or ""
            kind = item.get("type", "") or ""
            post_id = item.get("id", "") or ""

            link = canonical_link(
                account,
                kind,
                post_id,
                base_url=base_url,
                utm_source=utm_source,
            )
            item["link"] = link

            s_link: str | None = None
            if do_short:
                code = short_code(post_id)
                s_link = short_link(post_id, base_url=base_url)
                item["short_code"] = code
                item["short_link"] = s_link

            # Tag headline and body (the post's own short link is never retagged)
            keep = (s_link,) if s_link else ()
            headline = item.get("headline") or ""
            body = item.get("body") or ""
            new_headline, hr = tag_text(headline, link, base_url=base_url, keep=keep)
            new_body, br = tag_text(body, link, base_url=base_url, keep=keep)
            urls_rewritten += hr + br

            # Post-tag length re-check (validate_copy ran before this pass)
            if (hr or br) and len(new_headline) + 1 + len(new_body) > _max_chars and s_link:
                new_headline = new_headline.replace(link, s_link)
                new_body = new_body.replace(link, s_link)
                overflow_shortened += 1
            if (hr or br) and len(new_headline) + 1 + len(new_body) > _max_chars:
                item["_link_overflow"] = True
                overflow_flagged += 1

            item["headline"] = new_headline
            item["body"] = new_body

            posts_linked += 1

    note = (
        f"{posts_linked} posts linked; {urls_rewritten} in-text URLs retagged."
        if posts_linked
        else "No queue items found — nothing to link."
    )
    return {
        "posts_linked": posts_linked,
        "urls_rewritten": urls_rewritten,
        "overflow_shortened": overflow_shortened,
        "overflow_flagged": overflow_flagged,
        "note": note,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Short-link page builder
# ─────────────────────────────────────────────────────────────────────────────


def short_link_page(
    code: str,
    target_url: str,
    *,
    base_url: str | None = None,
) -> str:
    """Return a complete, byte-stable HTML redirect stub for a short-link code.

    Contains: meta-refresh, robots noindex/nofollow, canonical href, fallback anchor.
    English only (redirect stub — not a designed surface).
    No timestamps or dynamic content (deterministic by contract).
    """
    base = (base_url or DEFAULT_BASE_URL).rstrip("/") + "/"
    escaped_target = html.escape(target_url, quote=True)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        '<meta charset="utf-8">\n'
        '<meta name="robots" content="noindex,nofollow">\n'
        f'<meta http-equiv="refresh" content="0;url={escaped_target}">\n'
        f'<link rel="canonical" href="{html.escape(base, quote=True)}">\n'
        "<title>mastermind-x.com</title>\n"
        f'<a href="{escaped_target}">Continue to mastermind-x.com</a>\n'
    )


def build_short_link_pages(
    plan: dict,
    out_dir,
    cfg: dict | None = None,
) -> dict:
    """Write a static redirect page for every queue item in the plan.

    For each item that has (or can derive) a short code, writes:
      <out_dir>/<code>/index.html

    containing short_link_page(code, item["link"]).

    Write pattern: temp file + os.replace in the same directory (house law).
    Creates parent directories as needed.
    No pruning of stale codes — post ids are stable; old codes are harmless.
    Deterministic: same plan → byte-identical files.

    Returns {"pages_written": int, "out_dir": str}.
    """
    lcfg = links_cfg(cfg)
    if not lcfg["short_links"]:
        return {"pages_written": 0, "out_dir": str(Path(out_dir))}
    base_url = lcfg["base_url"]
    utm_source = lcfg["utm_source"]
    out = Path(out_dir)
    pages_written = 0

    for item in iter_plan_posts(plan):
        post_id = item.get("id", "") or ""
        if not post_id:
            continue

        code = item.get("short_code") or short_code(post_id)

        # Derive link if not already attached
        link = item.get("link")
        if not link:
            link = canonical_link(
                item.get("account", "") or "",
                item.get("type", "") or "",
                post_id,
                base_url=base_url,
                utm_source=utm_source,
            )

        page_dir = out / code
        page_dir.mkdir(parents=True, exist_ok=True)
        page_path = page_dir / "index.html"
        content = short_link_page(code, link, base_url=base_url)

        # Atomic write: temp + os.replace (house law — never open('w') truncate in place)
        tmp_fd, tmp_path_str = tempfile.mkstemp(dir=page_dir, prefix=".tmp_", suffix=".html")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path_str, page_path)
        except Exception:
            try:
                os.unlink(tmp_path_str)
            except Exception:  # noqa: BLE001
                pass
            raise

        pages_written += 1

    return {"pages_written": pages_written, "out_dir": str(out)}
