"""engine/marketing/x_intel.py — E3 competitive-intelligence corpus + analysis.

Masterplan §10 E3. This module is the AUTOMATED v1 of a thing that already
exists by hand: ``research/marketing_dockets/x_corpus_2026_07_29/{stats.md,
exemplars.md}`` were produced once, manually, from 286 original posts across 17
finance accounts. That docket is the ground truth this module reproduces on a
schedule — same source (twitterapi.io ``/twitter/user/last_tweets``), same
methodology notes (raw vs content line counts, strict vs any decimal, ALL-CAPS
lead), same registers.

    weekly harvest  ->  corpus.jsonl  ->  deterministic tables  ->  report.json
    (billed, capped)    (append-only)     (LLM never scores)       + WEEKLY_REPORT.md
                                                 |
                                                 v
                                        exemplar candidates (PENDING)
                                        -> exemplar_store.promote_pending()
                                        -> operator pins a version in config
                                        -> the writer reads THAT version only

**THE LLM NEVER SCORES** (charter §2 amendment 9, restated in masterplan §10 E3:
"LLM distills style; engagement math stays deterministic"). Every number this
module produces is arithmetic over observed counters. It imports no model client
and must not.

**ZERO VIEWS IS NOT A ZERO RATE.** A post whose ``views`` the API did not return
is UNMEASURED, not unengaging. It is excluded from every rate denominator and
counted in ``n_no_views`` instead of being folded in as 0.0 — the same law the
labels store applies to impressions (``labels._post_label``).

**Budget.** twitterapi.io is ONE account and ONE shared $75/month bucket, already
carrying the Trump wire (``press_providers``) and the reply desk
(``reply_discovery``). This lane carves its own counter and refuses to spend past
a hard monthly CALL cap; see ``DEFAULTS['monthly_call_cap']`` for the arithmetic.
Unlike the two poller lanes its counter is COMMITTED (``state.json`` under the
corpus dir), because this lane runs weekly in its own GitHub-hosted workflow that
commits its artifacts — it never runs on the render host, so the
"pollers make zero repo writes" law does not reach it.

Public API:
    DEFAULTS / SCHEMA / REPORT_SCHEMA / STATE_SCHEMA / REGISTERS
    resolve_cfg(cfg) -> dict
    intel_dir/corpus_path/state_path/report_path/weekly_report_path(root)
    roster(cfg) -> list[dict]                     # config/marketing.yml intel.roster
    classify(text, *, has_media=False) -> dict    # deterministic format tags
    is_retweet(raw) -> bool
    extract_tweets(response) -> list[dict]        # data.tweets nesting
    normalize_tweet(raw, *, handle, register, captured_at, source) -> dict | None
    load_corpus(root|path) -> list[dict]          # folded newest-per-id
    append_corpus(rows, *, root) -> int
    load_state(root) / save_state(state, root)
    budget_check(state, cfg, *, now, want=1) -> tuple[bool, str, dict]
    record_call(state, n_items, *, cfg, now) -> float
    Harvester(cfg).run(*, state, now, handles=None, offline=False) -> dict
    analyze(rows, *, cfg=None, prior=None, now) -> dict
    render_markdown(report) -> str
"""
from __future__ import annotations

import contextlib
import html
import json
import logging
import os
import re
import statistics
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

SCHEMA = "marketing.x_intel_post/v1"
REPORT_SCHEMA = "marketing.x_intel_report/v1"
STATE_SCHEMA = "marketing.x_intel_state/v1"

_TIMEOUT_S = 15
_MAX_BYTES = 4_000_000
_DAY_FMT = "%Y-%m-%d"
_ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

#: The corpus registers, verbatim from the manual docket's "By register" table
#: (``x_corpus_2026_07_29/stats.md``) as slugs. These are ACCOUNT registers: the
#: roster declares one per handle and the tables group on it.
REGISTERS: tuple[str, ...] = ("wire", "aggregator", "commentary", "trader", "macro_color")

#: How an intel register maps onto the HOUSE register vocabulary
#: (``labels.REGISTER_NAMES`` — the expression dial's 0/1/2). The writer hook
#: asks for exemplars by whichever name it has; ``exemplar_store`` normalises
#: through this map so a caller never has to know both vocabularies.
HOUSE_REGISTER_MAP: dict[str, tuple[str, ...]] = {
    "wire": ("wire",),
    "analysis": ("aggregator", "commentary"),
    "persona": ("trader", "macro_color"),
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
#: EVERY THRESHOLD IS A CONFIG KEY (charter §8). ``config/marketing.yml``
#: ``intel:`` overrides these documented defaults.
DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "base_url": "https://api.twitterapi.io",
    "endpoint": "/twitter/user/last_tweets",
    "auth_header": "X-API-Key",
    "key_env": "TWITTERAPI_IO_KEY",
    "user_agent": "MastermindX-Intel/1.0 (+https://mastermind-x.com)",
    # ── THE BUDGET, WITH THE ARITHMETIC SHOWN ─────────────────────────────
    # twitterapi.io bills per TWEET RETURNED, not per call: $0.15 / 1,000
    # tweets with a $0.00015 minimum charge per request. One roster call
    # returns ~20 tweets, so:
    #       20 tweets x $0.15/1000  =  $0.003  per call
    # The 600-call monthly ceiling is therefore ~$1.80/month against the shared
    # $75 twitterapi.io bucket, and it is sized as:
    #       17 roster accounts x 1 weekly deep pass x 4.4 weeks  =  ~75 calls
    #     + a daily light pass on the 5 fastest desks (5 x 30)   =   150 calls
    #     + operator re-runs, backfills, a doubled week          =  headroom
    #     ------------------------------------------------------------------
    #                                                            =  600 calls
    # ~8x the weekly-only need, ~2.6x the weekly+daily need. It is a CALL cap
    # rather than a dollar cap because a call is the unit the harvester can
    # count BEFORE it spends; the dollar counter rides alongside as the second,
    # independent stop and is the number the operator reads.
    "monthly_call_cap": 600,
    "monthly_usd_cap": 5.0,
    "price_per_1k_tweets_usd": 0.15,
    "min_charge_per_request_usd": 0.00015,
    # One run may not eat the month. 17 = one full roster pass.
    "max_calls_per_run": 20,
    # ── ANALYSIS ──────────────────────────────────────────────────────────
    # Posts created inside this window feed the tables. Older corpus rows stay
    # on disk (append-only ledger law) but do not skew a "what works now" read.
    "analysis_window_days": 90,
    # A table row below this n carries verdict="seeding" and makes NO ranking
    # claim. Lower than the labels store's 20 on purpose: an intel cell counts
    # OTHER PEOPLE's posts, which arrive ~340/week, not ours.
    "n_floor": 12,
    # Roster lives in config (seeded from the manual docket's 17 accounts).
    "roster": [],
    "exemplar_store": {
        # THE PIN. null/absent = the writer sees NO exemplars (dark by
        # default). Set to a version integer that promote_pending() minted.
        "active_version": None,
        "max_pending": 40,
        "per_register": 8,
        # A candidate needs a real measurement behind it. Posts under this
        # view count are excluded from the candidate pool entirely — their
        # interaction rate is a ratio over a denominator too thin to rank on.
        "min_views": 5000,
    },
}


def resolve_cfg(cfg: dict | None) -> dict:
    """Merge ``config/marketing.yml`` ``intel:`` over the documented defaults."""
    raw = ((cfg or {}).get("intel") or {}) if isinstance(cfg, dict) else {}
    out: dict[str, Any] = dict(DEFAULTS)
    for key, val in (raw or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = {**out[key], **val}
        else:
            out[key] = val
    return out


def roster(cfg: dict | None) -> list[dict]:
    """The account roster: ``[{handle, register, tier?, note?}, ...]``.

    Entries with no handle are DROPPED WITH A WARNING rather than polled as an
    empty username — a typo in the roster must not become a billed request for
    nothing.
    """
    conf = resolve_cfg(cfg)
    out: list[dict] = []
    for entry in (conf.get("roster") or []):
        if isinstance(entry, str):
            entry = {"handle": entry}
        if not isinstance(entry, dict):
            continue
        handle = str(entry.get("handle") or "").strip().lstrip("@")
        if not handle:
            log.warning("x_intel.roster: dropping entry with no handle: %r", entry)
            continue
        reg = str(entry.get("register") or "").strip().lower()
        if reg not in REGISTERS:
            reg = "unknown"
        out.append({
            "handle": handle,
            "register": reg,
            "tier": str(entry.get("tier") or "weekly").strip().lower(),
            "note": str(entry.get("note") or ""),
        })
    return out


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def _root_path(root: Path | str | None) -> Path:
    if root is None:
        return Path(__file__).resolve().parent.parent.parent
    return Path(root)


def intel_dir(root: Path | str | None = None) -> Path:
    return _root_path(root) / "data" / "marketing" / "x_intel"


def corpus_path(root: Path | str | None = None) -> Path:
    return intel_dir(root) / "corpus.jsonl"


def state_path(root: Path | str | None = None) -> Path:
    return intel_dir(root) / "state.json"


def report_path(root: Path | str | None = None) -> Path:
    return intel_dir(root) / "report.json"


def weekly_report_path(root: Path | str | None = None) -> Path:
    return intel_dir(root) / "WEEKLY_REPORT.md"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def iso_stamp(now: datetime) -> str:
    """UTC ``%Y-%m-%dT%H:%M:%SZ``. Public because ``exemplar_store`` stamps too,
    and two modules writing two timestamp formats into one store is how a
    sort-by-time later returns the wrong order."""
    dt = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    return dt.strftime(_ISO_FMT)


#: Internal alias — this module's own call sites predate the public name.
_iso = iso_stamp


def _month_key(now: datetime) -> str:
    dt = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    return dt.strftime("%Y-%m")


def _opt_int(value: object) -> int | None:
    """int or None. NOT 0 on failure — an absent counter is unmeasured."""
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_created(value: object) -> datetime | None:
    """Parse the several timestamp shapes twitterapi.io returns."""
    s = str(value or "").strip()
    if not s:
        return None
    for candidate in (s, s.replace("Z", "+00:00")):
        with contextlib.suppress(ValueError):
            dt = datetime.fromisoformat(candidate)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    # Twitter's legacy "Tue Jul 29 01:45:12 +0000 2026"
    with contextlib.suppress(ValueError):
        return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
    return None


def _day_of(value: object) -> str:
    dt = _parse_created(value)
    return dt.strftime(_DAY_FMT) if dt else str(value or "")[:10]


def _median(values: Sequence[float]) -> float | None:
    return round(statistics.median(values), 6) if values else None


# ---------------------------------------------------------------------------
# Deterministic format classifiers
#
# These reproduce the manual docket's methodology notes EXACTLY (see
# x_corpus_2026_07_29/stats.md §"Methodology notes"). Where the docket reports
# two readings of the same thing (raw vs content lines, strict vs any decimal)
# BOTH are kept — the docket's key finding #1 is precisely that the gap between
# them is the finding.
# ---------------------------------------------------------------------------
_RE_CASHTAG = re.compile(r"\$[A-Za-z]{1,5}(?![A-Za-z0-9])")
_RE_STARTS_CASHTAG = re.compile(r"^\s*\$[A-Za-z]{1,5}(?![A-Za-z0-9])")
_RE_DIGIT = re.compile(r"\d")
#: Strict decimal per the docket: exactly 2+ digits after the point (4.75).
_RE_DECIMAL_STRICT = re.compile(r"\d+\.\d\d")
#: Any decimal, including the far more common single-decimal percent (4.7%).
_RE_DECIMAL_ANY = re.compile(r"\d+\.\d+")
#: A digit run touching a '.' on neither side.
_RE_BARE_INT = re.compile(r"(?<![\d.])\d+(?![\d.])")
_RE_URL = re.compile(r"https?://", re.IGNORECASE)
_RE_LIST_LEAD = re.compile(r"^\s*(?:[-*•·]|\d+[.)]|\d+/)\s+")
_RE_WORD = re.compile(r"\S+")

#: ALL-CAPS words that are NOT tickers — the docket's exclude list, so
#: `starts_ticker` does not read "BREAKING" or "FOMC" as a symbol.
_NON_TICKER_CAPS: frozenset[str] = frozenset({
    "BREAKING", "JUST", "NEW", "GDP", "CPI", "PPI", "PCE", "FOMC", "FED", "ECB",
    "BOJ", "BOE", "US", "USA", "UK", "EU", "CEO", "CFO", "COO", "IPO", "ETF",
    "AI", "OPEC", "NATO", "WSJ", "CNBC", "SEC", "FDA", "DOJ", "IMF", "NFP",
    "ISM", "PMI", "YOY", "MOM", "QOQ", "ATH", "EPS", "RSI", "USD", "EUR", "JPY",
})

#: Emoji-ish codepoint ranges (misc pictographs, dingbats, flags, arrows+VS16,
#: geometric shapes ext.) — the docket's "common emoji blocks".
_EMOJI_RANGES: tuple[tuple[int, int], ...] = (
    (0x1F300, 0x1FAFF), (0x1F000, 0x1F0FF), (0x2600, 0x27BF),
    (0x2B00, 0x2BFF), (0x1F1E6, 0x1F1FF), (0xFE0F, 0xFE0F), (0x2190, 0x21FF),
)


def _has_emoji(text: str) -> bool:
    return any(any(lo <= ord(ch) <= hi for lo, hi in _EMOJI_RANGES) for ch in text)


def _first_alpha_token(text: str) -> str:
    """First token with a letter in it, skipping leading emoji/digits/punct."""
    for tok in _RE_WORD.findall(text):
        stripped = tok.strip("\"'“”‘’*_()[]:;,.!?-—…")
        if any(ch.isalpha() for ch in stripped):
            return stripped
    return ""


def _median_words_per_sentence(text: str) -> float | None:
    """Docket methodology: split on newlines, then on .!? boundaries, pool ALL
    fragments across the post and take the median of their word counts."""
    frags: list[int] = []
    for line in text.split("\n"):
        for frag in re.split(r"[.!?]+", line):
            words = len(_RE_WORD.findall(frag))
            if words:
                frags.append(words)
    return float(statistics.median(frags)) if frags else None


def classify(text: str, *, has_media: bool = False) -> dict:
    """Deterministic format tags for one post. No model, no judgement calls.

    ``shape`` maps the post onto OUR OWN shape vocabulary
    (``content_studio.SHAPES``) rather than inventing a third one, because the
    whole point of the distribution table is comparing a competitor corpus to
    our configured quotas (``shapes.quotas``). A vocabulary mismatch there would
    make the comparison unreadable.
    """
    raw = (text or "").strip()
    raw_lines_list = raw.split("\n") if raw else []
    content_list = [ln for ln in raw_lines_list if ln.strip()]
    raw_lines = len(raw_lines_list)
    content_lines = len(content_list)
    has_blank_spacer = raw_lines > content_lines

    lead = _first_alpha_token(raw)
    all_caps_lead = len(lead) >= 2 and lead.isupper()
    starts_cashtag = bool(_RE_STARTS_CASHTAG.match(raw))
    starts_ticker = starts_cashtag or (
        all_caps_lead and len(lead) <= 5 and lead not in _NON_TICKER_CAPS
    )
    is_list = any(_RE_LIST_LEAD.match(ln) for ln in content_list)

    # Shape, in our vocabulary. `caption` FIRST: the docket's media-only rows
    # are exactly the caption shape (the chart does the talking), and reading
    # them as `one_liner` would inflate the one_liner rate we compare quotas on.
    if has_media and content_lines <= 1 and len(raw) <= 80:
        shape = "caption"
    elif content_lines == 0:
        shape = "caption" if has_media else "empty"
    elif content_lines == 1:
        shape = "one_liner"
    elif content_lines == 2:
        shape = "two_part"
    elif is_list:
        shape = "list"
    else:
        shape = "stack"

    return {
        "chars": len(raw),
        "raw_lines": raw_lines,
        "content_lines": content_lines,
        "has_blank_spacer": has_blank_spacer,
        "shape": shape,
        "has_cashtag": bool(_RE_CASHTAG.search(raw)),
        "starts_cashtag": starts_cashtag,
        "starts_ticker": starts_ticker,
        "has_number": bool(_RE_DIGIT.search(raw)),
        "has_bare_int": bool(_RE_BARE_INT.search(raw)),
        "decimal_strict": bool(_RE_DECIMAL_STRICT.search(raw)),
        "decimal_any": bool(_RE_DECIMAL_ANY.search(raw)),
        "all_caps_lead": all_caps_lead,
        "has_emoji": _has_emoji(raw),
        "ends_question": raw.endswith("?"),
        "has_url": bool(_RE_URL.search(raw)),
        "has_media": bool(has_media),
        "median_words_per_sentence": _median_words_per_sentence(raw),
        "register_guess": _register_guess(raw, all_caps_lead=all_caps_lead,
                                          starts_cashtag=starts_cashtag,
                                          content_lines=content_lines),
    }


def _register_guess(text: str, *, all_caps_lead: bool, starts_cashtag: bool,
                    content_lines: int) -> str:
    """A POST-level register read, deterministic and deliberately crude.

    NOT the authority — the roster's declared per-ACCOUNT register is, and that
    is what the tables group on. This exists because an account writes in more
    than one register (a trader posts a wire headline; a wire desk posts a
    chart), and a per-post tag is the only way to see that inside a corpus
    grouped by account.
    """
    upper = text.upper()
    # CASHTAG LEAD IS CHECKED FIRST, and that ordering is load-bearing. The
    # docket notes the overlap explicitly: "$AAPL reads as leading token AAPL
    # (all caps)", so `$PLTR reclaimed the 50-day` satisfies all_caps_lead too.
    # Testing the caps branch first read every trader setup as a wire headline.
    if starts_cashtag:
        return "trader"
    if all_caps_lead and content_lines <= 2:
        return "wire"
    if upper.startswith(("BREAKING", "JUST IN", "*")):
        return "wire"
    has_num = bool(_RE_DIGIT.search(text))
    if has_num and bool(_RE_URL.search(text)) and content_lines >= 2:
        return "aggregator"
    if has_num:
        return "commentary"
    return "macro_color"


# ---------------------------------------------------------------------------
# Response parsing — the data.tweets nesting, RT filtering, entity unescaping
# ---------------------------------------------------------------------------
#: Keys a tweet list can live under, in preference order. twitterapi.io's
#: last_tweets nests at ``data.tweets``; other endpoints flatten to ``tweets``.
_ITEM_KEYS: tuple[str, ...] = ("tweets", "data", "results", "items", "replies")


def extract_tweets(response: object) -> list[dict]:
    """Pull tweet objects out of the response, whatever shape it arrived in.

    twitterapi.io's ``/twitter/user/last_tweets`` nests at ``data.tweets``; the
    single-level ``tweets`` shape is also accepted so a future endpoint swap
    does not silently harvest zero rows.
    """
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    if not isinstance(response, dict):
        return []
    for key in _ITEM_KEYS:
        val = response.get(key)
        if isinstance(val, list):
            return [r for r in val if isinstance(r, dict)]
        if isinstance(val, dict):
            for nested in _ITEM_KEYS:
                inner = val.get(nested)
                if isinstance(inner, list):
                    return [r for r in inner if isinstance(r, dict)]
    return []


def is_retweet(raw: dict) -> bool:
    """A pure retweet — someone else's post, carrying someone else's style.

    The API returns RTs inline with originals and their text is prefixed
    ``RT @handle:``. Keeping them would put another account's writing into this
    account's style row, which is the one thing a style corpus may not do.
    Quote-tweets are NOT retweets: the quoting text is the author's own and the
    docket keeps them, flagged ``is_quote``.
    """
    if not isinstance(raw, dict):
        return False
    text = str(raw.get("text") or raw.get("full_text") or "")
    if text.lstrip().startswith("RT @"):
        return True
    for key in ("retweeted_tweet", "retweetedTweet", "retweeted_status"):
        if isinstance(raw.get(key), dict) and raw.get(key):
            return True
    for key in ("isRetweet", "is_retweet", "retweeted"):
        if raw.get(key) is True:
            return True
    return False


def _author_block(raw: dict) -> dict:
    for key in ("author", "user"):
        blk = raw.get(key)
        if isinstance(blk, dict):
            return blk
    return {}


def normalize_tweet(
    raw: dict,
    *,
    handle: str,
    register: str = "unknown",
    captured_at: str,
    source: str = "twitterapi.io",
) -> dict | None:
    """One API row -> one corpus row, on the CODEX MEASUREMENT SCHEMA.

    ``research/marketing_dockets/CODEX_CONTENT_CASE_STUDIES_2026_07_28.md``
    §"Recommended measurement schema for future cases" asks for: post URL and
    exact text; account and follower count AT CAPTURE; exact publication and
    capture timestamps; replies/reposts/likes/bookmarks/views; media type and
    whether a quote-post seeded distribution; topic and format tags. Every one
    of those has a field here.

    Counters are ``None`` when the API did not return them — never 0. The
    difference between "nobody looked" and "we were not told how many looked" is
    the difference between a real zero and an unmeasured cell, and every rate in
    ``analyze`` depends on keeping them apart.
    """
    if not isinstance(raw, dict):
        return None
    tid = str(raw.get("id") or raw.get("id_str") or raw.get("tweet_id") or "").strip()
    if not tid:
        return None
    author = _author_block(raw)
    api_handle = str(
        author.get("userName") or author.get("screen_name") or author.get("username") or ""
    ).strip().lstrip("@")
    who = api_handle or str(handle or "").lstrip("@")
    # HTML ENTITIES: the API returns `&amp;`, `&lt;`, `&gt;` raw. The docket
    # unescapes before any classifier runs, because `&amp;` would otherwise read
    # as an extra 4 characters and `&gt;100` would lose its bare integer.
    text = html.unescape(str(raw.get("text") or raw.get("full_text") or ""))

    media = raw.get("extendedEntities") or raw.get("extended_entities") or {}
    media_list = media.get("media") if isinstance(media, dict) else None
    if not isinstance(media_list, list):
        ent = raw.get("entities")
        media_list = (ent or {}).get("media") if isinstance(ent, dict) else None
    media_types = sorted({
        str((m or {}).get("type") or "").strip()
        for m in (media_list or []) if isinstance(m, dict)
    } - {""})
    has_media = bool(media_types)

    quoted = raw.get("quoted_tweet") or raw.get("quotedTweet") or raw.get("quoted_status")
    is_quote = bool(quoted) or bool(raw.get("isQuote") or raw.get("is_quote_status"))

    return {
        "schema": SCHEMA,
        "id": tid,
        "author": who,
        "author_register": str(register or "unknown"),
        "author_followers": _opt_int(
            author.get("followers") or author.get("followers_count")
            or author.get("followersCount")
        ),
        "text": text,
        "url": str(raw.get("url") or raw.get("twitterUrl")
                   or (f"https://x.com/{who}/status/{tid}" if who else "")),
        "created_at": str(raw.get("createdAt") or raw.get("created_at") or ""),
        "created_day": _day_of(raw.get("createdAt") or raw.get("created_at")),
        "captured_at": captured_at,
        "source": source,
        "lang": str(raw.get("lang") or ""),
        # Codex schema: the full engagement vector, nulls preserved.
        "likes": _opt_int(raw.get("likeCount") or raw.get("favorite_count")),
        "retweets": _opt_int(raw.get("retweetCount") or raw.get("retweet_count")),
        "replies": _opt_int(raw.get("replyCount") or raw.get("reply_count")),
        "quotes": _opt_int(raw.get("quoteCount") or raw.get("quote_count")),
        "bookmarks": _opt_int(raw.get("bookmarkCount") or raw.get("bookmark_count")),
        "views": _opt_int(raw.get("viewCount") or raw.get("view_count")
                          or raw.get("impressionCount")),
        "is_quote": is_quote,
        "media_types": media_types,
        "tags": classify(text, has_media=has_media),
    }


# ---------------------------------------------------------------------------
# Corpus I/O — APPEND-ONLY on disk, folded newest-per-id on read
# ---------------------------------------------------------------------------
def _read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001 — a torn final line must not
                    continue       # blind us to the good rows above it
                if isinstance(rec, dict):
                    out.append(rec)
    except (FileNotFoundError, NotADirectoryError, OSError):
        return []
    return out


def load_corpus(root: Path | str | None = None, *, path: Path | str | None = None) -> list[dict]:
    """The corpus, DEDUPED BY TWEET ID, keeping the freshest capture.

    The file is append-only (``.gitattributes`` carries ``merge=union`` for it,
    which is only correct for a file nobody rewrites). Re-captures of the same
    post are therefore normal — engagement counters are cumulative, so the
    latest ``captured_at`` is the current truth and the earlier rows are the
    post's engagement history.
    """
    p = Path(path) if path is not None else corpus_path(root)
    best: dict[str, dict] = {}
    for row in _read_jsonl(p):
        rid = str(row.get("id") or "").strip()
        if not rid:
            continue
        prev = best.get(rid)
        if prev is None or str(row.get("captured_at") or "") >= str(prev.get("captured_at") or ""):
            best[rid] = row
    return [best[k] for k in sorted(best)]


def _engagement_fingerprint(row: dict) -> tuple:
    return (row.get("likes"), row.get("retweets"), row.get("replies"),
            row.get("views"), row.get("bookmarks"), row.get("text"))


def append_corpus(rows: Sequence[dict], *, root: Path | str | None = None,
                  path: Path | str | None = None) -> int:
    """Append rows whose id is new OR whose counters moved. Returns rows written.

    APPEND, NEVER REWRITE. A rewrite would make the ``merge=union`` attribute on
    this path actively harmful: union resolves a conflict by keeping both sides'
    lines, which is right for an append-only ledger and catastrophic for a file
    two runs rewrite in full.

    An identical re-capture (same counters, same text) is DROPPED — it is not
    new information and it would grow the ledger by ~340 rows a week for
    nothing. A capture whose counters moved is kept: that is the engagement
    history the codex schema asks for.
    """
    p = Path(path) if path is not None else corpus_path(root)
    latest = {r["id"]: r for r in load_corpus(path=p)}
    fresh: list[dict] = []
    for row in rows:
        rid = str((row or {}).get("id") or "").strip()
        if not rid:
            continue
        prev = latest.get(rid)
        if prev is not None and _engagement_fingerprint(prev) == _engagement_fingerprint(row):
            continue
        fresh.append(row)
        latest[rid] = row
    if not fresh:
        return 0
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        for row in fresh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return len(fresh)


def write_json_atomic(path: Path, payload: Any) -> None:
    """Atomic replace of a tracked JSON artifact. Public: ``exemplar_store``
    writes the store through the same helper, so both artifacts land the same
    way (tmp in the same dir + ``os.replace``) and a half-written store can
    never be read by the writer hook."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".xi-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


#: Internal alias — this module's own call sites predate the public name.
_write_json_atomic = write_json_atomic


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".xi-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


# ---------------------------------------------------------------------------
# Budget state — COMMITTED, because this lane has no host daemon
# ---------------------------------------------------------------------------
def _empty_state(now: datetime | None = None) -> dict:
    return {
        "schema": STATE_SCHEMA,
        "months": {},
        "handles": {},
        "last_run": None,
        "updated_at": _iso(now) if now else "",
    }


def load_state(root: Path | str | None = None) -> dict:
    """The committed spend counter, fail-soft.

    BE HONEST ABOUT WHAT A LOST STATE FILE COSTS: this counter is the cap, so a
    torn or deleted ``state.json`` reads as zero spend and re-opens the month's
    budget. That is announced rather than swallowed, and the blast radius is
    bounded on both sides — ``max_calls_per_run`` (20, ~$0.06) caps any single
    run, and the cap itself caps the month at ~$1.80. Refusing to run instead
    would be worse: a lane that cannot harvest until an operator hand-repairs a
    JSON file is a lane that stays dark for weeks.

    An ABSENT file is not an error — that is the first run.
    """
    path = state_path(root)
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _empty_state()
    except Exception as exc:  # noqa: BLE001
        print(
            f"::warning title=x-intel-state::spend counter at {path} is unreadable "
            f"({exc}) — this month's counter reads as ZERO, which re-opens the "
            f"budget. One run is still capped by intel.max_calls_per_run and the "
            f"month by intel.monthly_call_cap; restore the file from git history "
            f"to recover the real count.",
            flush=True,
        )
        return _empty_state()
    if not isinstance(blob, dict):
        return _empty_state()
    blob.setdefault("schema", STATE_SCHEMA)
    blob.setdefault("months", {})
    blob.setdefault("handles", {})
    return blob


def save_state(state: dict, root: Path | str | None = None, *, now: datetime | None = None) -> bool:
    try:
        payload = dict(state)
        payload["updated_at"] = _iso(now or datetime.now(tz=timezone.utc))
        _write_json_atomic(state_path(root), payload)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("x_intel.save_state: cannot write %s: %s", state_path(root), exc)
        return False


def month_bucket(state: dict, now: datetime) -> dict:
    months = state.setdefault("months", {})
    return months.setdefault(_month_key(now), {"calls": 0, "tweets": 0, "usd": 0.0})


def budget_check(state: dict, cfg: dict | None = None, *, now: datetime,
                 want: int = 1) -> tuple[bool, str, dict]:
    """May this lane make ``want`` more billed calls? Returns (ok, reason, meta).

    TWO INDEPENDENT STOPS, both hard:
      * the monthly CALL cap — the unit the harvester can count before spending;
      * the monthly USD cap — defence in depth if a page ever returns far more
        tweets per call than the ~20 the cap arithmetic assumes.
    Either one binding refuses the call. There is no soft mode.
    """
    conf = resolve_cfg(cfg)
    bucket = month_bucket(state, now)
    calls = int(bucket.get("calls", 0) or 0)
    usd = float(bucket.get("usd", 0.0) or 0.0)
    call_cap = int(conf.get("monthly_call_cap") or 0)
    usd_cap = float(conf.get("monthly_usd_cap") or 0.0)
    meta = {
        "month": _month_key(now),
        "calls": calls, "usd": round(usd, 6),
        "call_cap": call_cap, "usd_cap": usd_cap,
        "calls_remaining": max(0, call_cap - calls),
    }
    if call_cap > 0 and calls + max(1, int(want)) > call_cap:
        return False, "monthly_call_cap", meta
    if usd_cap > 0 and usd >= usd_cap:
        return False, "monthly_usd_cap", meta
    return True, "", meta


def announce_budget_stop(reason: str, meta: dict) -> None:
    """The refusal annotation. BARE PRINT AT LINE START, flushed.

    A logger here would emit ``WARNING ::warning ...`` and GitHub would silently
    drop the annotation — the CI-guarded house law
    (``tests/test_gh_annotation_line_start.py``).
    """
    if reason == "monthly_call_cap":
        detail = (f"{meta.get('calls')} calls used against a cap of "
                  f"{meta.get('call_cap')}")
    else:
        detail = (f"${float(meta.get('usd', 0.0)):.4f} spent against a cap of "
                  f"${float(meta.get('usd_cap', 0.0)):.2f}")
    print(
        f"::warning title=x-intel-budget::x_intel harvest REFUSED ({reason}) for "
        f"{meta.get('month')}: {detail} — no twitterapi.io call was made. The "
        f"Trump wire and reply desk lanes are unaffected (separate counters). "
        f"Raise intel.monthly_call_cap in config/marketing.yml to lift it.",
        flush=True,
    )


def record_call(state: dict, n_items: int, *, cfg: dict | None = None,
                now: datetime) -> float:
    """Bill one request into the monthly bucket. Returns the marginal cost."""
    conf = resolve_cfg(cfg)
    price = float(conf.get("price_per_1k_tweets_usd") or 0.0)
    floor = float(conf.get("min_charge_per_request_usd") or 0.0)
    cost = max(floor, max(0, int(n_items)) / 1000.0 * price)
    bucket = month_bucket(state, now)
    bucket["calls"] = int(bucket.get("calls", 0) or 0) + 1
    bucket["tweets"] = int(bucket.get("tweets", 0) or 0) + max(0, int(n_items))
    bucket["usd"] = round(float(bucket.get("usd", 0.0) or 0.0) + cost, 6)
    return cost


# ---------------------------------------------------------------------------
# The harvester
# ---------------------------------------------------------------------------
class Harvester:
    """twitterapi.io reads for the style corpus. Read-only, roster-only."""

    billed = True   # dry-run/offline must skip every fetch this class makes

    def __init__(self, cfg: dict | None = None, *, transport=None) -> None:
        conf = resolve_cfg(cfg)
        self.cfg = conf
        self.base_url = str(conf.get("base_url"))
        self.endpoint = str(conf.get("endpoint"))
        self.auth_header = str(conf.get("auth_header"))
        self.key_env = str(conf.get("key_env"))
        self.user_agent = str(conf.get("user_agent"))
        self.max_calls_per_run = max(1, int(conf.get("max_calls_per_run") or 1))
        #: Injectable for tests: ``transport(url, headers) -> parsed json``.
        #: Nothing in production passes it, so the real path is the real path.
        self._transport = transport

    # -- transport ---------------------------------------------------------
    def _request(self, api_key: str, params: dict) -> object | None:
        url = f"{self.base_url}{self.endpoint}?{urlencode(params)}"
        headers = {
            "User-Agent": self.user_agent,
            self.auth_header: api_key,
            "Accept": "application/json",
        }
        if self._transport is not None:
            try:
                return self._transport(url, headers)
            except Exception as exc:  # noqa: BLE001
                print(f"[x_intel] transport error: {exc}", file=sys.stderr)
                return None
        try:
            req = Request(url, headers=headers)  # noqa: S310
            with urlopen(req, timeout=_TIMEOUT_S) as resp:  # noqa: S310
                blob = resp.read(_MAX_BYTES + 1)
            return json.loads(blob.decode("utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001
            print(f"[x_intel] request error ({self.endpoint}): {exc}", file=sys.stderr)
            return None

    # -- the run -----------------------------------------------------------
    def run(
        self,
        *,
        state: dict,
        now: datetime,
        handles: Sequence[dict] | None = None,
        offline: bool = False,
    ) -> dict:
        """Harvest every roster handle within budget. Returns a run summary.

        ``offline`` makes ZERO network calls and ZERO spend (the dry-run law for
        billed providers). Rows harvested are returned under ``rows``; the
        caller owns the corpus append, so a dry run can print what it WOULD
        write without writing it.
        """
        captured_at = _iso(now)
        entries = list(handles) if handles is not None else roster({"intel": self.cfg})
        summary: dict[str, Any] = {
            "as_of": captured_at,
            "handles_requested": len(entries),
            "handles_polled": 0,
            "calls": 0,
            "tweets_seen": 0,
            "retweets_dropped": 0,
            "rows": [],
            "usd": 0.0,
            "stopped": None,
            "per_handle": [],
        }
        if offline:
            summary["stopped"] = "offline"
            return summary
        if not self.cfg.get("enabled", True):
            summary["stopped"] = "disabled"
            print("::notice title=x-intel::intel.enabled is false — harvest skipped",
                  flush=True)
            return summary

        api_key = os.environ.get(self.key_env, "").strip()
        if not api_key:
            summary["stopped"] = "no_api_key"
            print(
                f"::notice title=x-intel::{self.key_env} unset — harvest skipped "
                f"(no spend, no corpus write). This is the DARK default.",
                flush=True,
            )
            return summary

        for entry in entries:
            if summary["calls"] >= self.max_calls_per_run:
                summary["stopped"] = "max_calls_per_run"
                print(
                    f"::notice title=x-intel::run cap {self.max_calls_per_run} reached "
                    f"after {summary['calls']} calls — remaining handles roll to the "
                    f"next run",
                    flush=True,
                )
                break
            ok, reason, meta = budget_check(state, {"intel": self.cfg}, now=now)
            if not ok:
                summary["stopped"] = reason
                announce_budget_stop(reason, meta)
                break

            handle = str(entry.get("handle") or "").strip().lstrip("@")
            if not handle:
                continue
            response = self._request(api_key, {"userName": handle})
            raws = extract_tweets(response)
            # A response we got but could not parse bills at the minimum charge
            # and counts zero tweets — indistinguishable from an empty page. A
            # renamed response key is therefore how this counter silently
            # under-reads, so it is announced (reply_discovery's posture).
            if not raws and isinstance(response, dict) and response:
                print(
                    f"::warning title=x-intel-shape::unrecognised twitterapi.io "
                    f"response shape for @{handle} (keys={sorted(response)[:6]}) — "
                    f"billed at the minimum charge and counted as ZERO tweets; the "
                    f"corpus is under-filling until the shape is added to "
                    f"x_intel._ITEM_KEYS",
                    flush=True,
                )
            cost = record_call(state, len(raws), cfg={"intel": self.cfg}, now=now)
            summary["calls"] += 1
            summary["usd"] = round(float(summary["usd"]) + cost, 6)
            summary["handles_polled"] += 1
            summary["tweets_seen"] += len(raws)

            kept = 0
            dropped = 0
            for raw in raws:
                if is_retweet(raw):
                    dropped += 1
                    continue
                row = normalize_tweet(
                    raw, handle=handle,
                    register=str(entry.get("register") or "unknown"),
                    captured_at=captured_at,
                )
                if row is None:
                    continue
                summary["rows"].append(row)
                kept += 1
            summary["retweets_dropped"] += dropped
            summary["per_handle"].append({
                "handle": handle, "raw": len(raws), "kept": kept, "retweets": dropped,
            })
            hstate = state.setdefault("handles", {}).setdefault(handle, {})
            hstate["last_captured_at"] = captured_at
            hstate["last_kept"] = kept

        state["last_run"] = {
            "at": captured_at,
            "calls": summary["calls"],
            "rows": len(summary["rows"]),
            "usd": summary["usd"],
            "stopped": summary["stopped"],
        }
        return summary


# ---------------------------------------------------------------------------
# The analysis pass — DETERMINISTIC, n-floor gated, nulls printed
# ---------------------------------------------------------------------------
def _interaction_rate(row: dict) -> float | None:
    """(likes + retweets + replies) / views, or None.

    ZERO OR ABSENT VIEWS IS NOT A ZERO RATE. Returning 0.0 for an unmeasured
    post would drag every median toward zero in exact proportion to how many
    posts the API declined to report views for — the same defect
    ``labels._post_label`` refuses for impressions.
    """
    views = row.get("views")
    if not isinstance(views, int) or views <= 0:
        return None
    inter = sum(int(row.get(k) or 0) for k in ("likes", "retweets", "replies"))
    return round(inter / views, 8)


def _repost_rate(row: dict) -> float | None:
    """Reposts per view — the codex's DISTRIBUTION objective.

    "Optimize primarily for repost/view rate when the goal is distribution"
    (codex §Recommended measurement schema). Kept separate from the blended
    interaction rate so a distribution question is answered by a distribution
    number.
    """
    views = row.get("views")
    if not isinstance(views, int) or views <= 0:
        return None
    rt = row.get("retweets")
    if not isinstance(rt, int):
        return None
    return round(rt / views, 8)


def _table(rows: Sequence[dict], key_fn, *, n_floor: int, label: str) -> list[dict]:
    """One grouped engagement table. Same n-floor law as the labels scorecard:
    a thin group is PRINTED with verdict="seeding" and no ranking claim."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(str(key_fn(row) or "unknown"), []).append(row)

    out: list[dict] = []
    for name, grp in groups.items():
        views = [float(r["views"]) for r in grp if isinstance(r.get("views"), int) and r["views"] > 0]
        likes = [float(r["likes"]) for r in grp if isinstance(r.get("likes"), int)]
        rts = [float(r["retweets"]) for r in grp if isinstance(r.get("retweets"), int)]
        inter = [v for v in (_interaction_rate(r) for r in grp) if v is not None]
        repost = [v for v in (_repost_rate(r) for r in grp) if v is not None]
        entry = {
            label: name,
            "n": len(grp),
            "n_no_views": sum(1 for r in grp if not isinstance(r.get("views"), int)
                              or int(r.get("views") or 0) <= 0),
            "med_views": _median(views),
            "med_likes": _median(likes),
            "med_retweets": _median(rts),
            "med_interaction_rate": _median(inter),
            "med_repost_rate": _median(repost),
            "n_rate": len(inter),
        }
        if len(grp) < n_floor:
            entry["verdict"] = "seeding"
            entry["verdict_note"] = (
                f"{len(grp)} posts against an n-floor of {n_floor} — no ranking "
                "claim is made from this row"
            )
        out.append(entry)
    out.sort(key=lambda e: (-int(e["n"]), str(e[label])))
    return out


def _rate(rows: Sequence[dict], pred) -> float | None:
    return round(sum(1 for r in rows if pred(r)) / len(rows), 4) if rows else None


def analyze(rows: Sequence[dict], *, cfg: dict | None = None,
            prior: dict | None = None, now: datetime) -> dict:
    """The weekly report payload. Every number is arithmetic over counters.

    ``prior`` is the previous ``report.json``; the diff block reports how the
    headline rates moved week over week. A first run has no prior and says so
    rather than diffing against zeros.
    """
    conf = resolve_cfg(cfg)
    floor = max(1, int(conf.get("n_floor") or 1))
    window = max(1, int(conf.get("analysis_window_days") or 1))
    cutoff = (now.astimezone(timezone.utc) - timedelta(days=window)).strftime(_DAY_FMT)

    in_window = [r for r in rows
                 if str(r.get("created_day") or r.get("captured_at") or "")[:10] >= cutoff]

    def tags_of(row: dict) -> dict:
        return row.get("tags") or {}

    shape_counts: dict[str, int] = {}
    for row in in_window:
        shape = str(tags_of(row).get("shape") or "unknown")
        shape_counts[shape] = shape_counts.get(shape, 0) + 1
    n = len(in_window)
    shape_dist = {k: round(v / n, 4) for k, v in sorted(shape_counts.items())} if n else {}

    # OUR quotas, from the same config the mixer reads (`shapes.quotas`), so the
    # comparison is against what we actually run — not a number retyped here.
    quotas = (((cfg or {}).get("shapes") or {}).get("quotas") or {}) if isinstance(cfg, dict) else {}
    quota_gap = []
    if n:
        one_min = quotas.get("one_liner_min")
        two_max = quotas.get("two_part_max")
        if one_min is not None:
            quota_gap.append({
                "shape": "one_liner", "ours_min": float(one_min),
                "theirs": shape_dist.get("one_liner", 0.0),
                "note": "corpus share of single-content-line posts vs our floor",
            })
        if two_max is not None:
            quota_gap.append({
                "shape": "two_part", "ours_max": float(two_max),
                "theirs": shape_dist.get("two_part", 0.0),
                "note": "corpus share of two-content-line posts vs our ceiling",
            })

    precision = {
        "decimal_strict_rate": _rate(in_window, lambda r: tags_of(r).get("decimal_strict")),
        "decimal_any_rate": _rate(in_window, lambda r: tags_of(r).get("decimal_any")),
        "bare_int_rate": _rate(in_window, lambda r: tags_of(r).get("has_bare_int")),
        "has_number_rate": _rate(in_window, lambda r: tags_of(r).get("has_number")),
        "cashtag_rate": _rate(in_window, lambda r: tags_of(r).get("has_cashtag")),
        "starts_cashtag_rate": _rate(in_window, lambda r: tags_of(r).get("starts_cashtag")),
        "all_caps_lead_rate": _rate(in_window, lambda r: tags_of(r).get("all_caps_lead")),
        "emoji_rate": _rate(in_window, lambda r: tags_of(r).get("has_emoji")),
        "url_rate": _rate(in_window, lambda r: tags_of(r).get("has_url")),
        "blank_spacer_rate": _rate(in_window, lambda r: tags_of(r).get("has_blank_spacer")),
        "quote_rate": _rate(in_window, lambda r: r.get("is_quote")),
        "note": (
            "strict decimal is the docket's \\d+\\.\\d\\d (4.75); any-decimal also "
            "catches the far more common single-decimal percent (4.7%). The gap "
            "between them IS the finding — see the docket's key finding #2."
        ),
    }

    report = {
        "schema": REPORT_SCHEMA,
        "produced_by": "engine/marketing/x_intel.py",
        "as_of": now.astimezone(timezone.utc).strftime(_DAY_FMT),
        "generated_at": _iso(now),
        "window_days": window,
        "n_floor": floor,
        "n_posts": n,
        "n_posts_all_time": len(rows),
        "n_authors": len({str(r.get("author") or "") for r in in_window}),
        "by_shape": _table(in_window, lambda r: tags_of(r).get("shape"),
                           n_floor=floor, label="shape"),
        "by_register": _table(in_window, lambda r: r.get("author_register"),
                              n_floor=floor, label="register"),
        "by_author": _table(in_window, lambda r: r.get("author"),
                            n_floor=floor, label="author"),
        "shape_distribution": shape_dist,
        "our_shape_quotas": {k: quotas.get(k) for k in sorted(quotas)},
        "quota_gap": quota_gap,
        "precision": precision,
        "diff_vs_prior": _diff(prior, precision, shape_dist),
        "note": (
            "Operator/writer-desk artifact. Deterministic arithmetic over observed "
            "counters — no model scored anything here (charter §2 amendment 9). "
            "Posts with no view count are excluded from every rate denominator and "
            "counted in n_no_views; an unmeasured post is not a zero-rate post."
        ),
    }
    return report


def _diff(prior: dict | None, precision: dict, shape_dist: dict) -> dict:
    """Week-over-week movement on the headline rates, or an honest null."""
    if not isinstance(prior, dict) or not prior:
        return {"available": False,
                "reason": "no prior report.json — this is the first run"}
    prev_prec = prior.get("precision") or {}
    prev_shape = prior.get("shape_distribution") or {}
    moved: dict[str, dict] = {}
    for key, val in precision.items():
        if not isinstance(val, (int, float)):
            continue
        was = prev_prec.get(key)
        if isinstance(was, (int, float)):
            moved[key] = {"was": round(float(was), 4), "now": round(float(val), 4),
                          "delta": round(float(val) - float(was), 4)}
    shapes: dict[str, dict] = {}
    for key in sorted(set(shape_dist) | set(prev_shape)):
        was = float(prev_shape.get(key) or 0.0)
        nowv = float(shape_dist.get(key) or 0.0)
        shapes[key] = {"was": round(was, 4), "now": round(nowv, 4),
                       "delta": round(nowv - was, 4)}
    return {
        "available": True,
        "prior_as_of": prior.get("as_of"),
        "prior_n_posts": prior.get("n_posts"),
        "rates": moved,
        "shapes": shapes,
    }


# ---------------------------------------------------------------------------
# The markdown report — regenerated every run, tracked
# ---------------------------------------------------------------------------
def _pct(value: object) -> str:
    return f"{float(value) * 100:.1f}%" if isinstance(value, (int, float)) else "—"


def _num(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value:,.0f}" if abs(float(value)) >= 100 else f"{float(value):.4g}"


def _rate6(value: object) -> str:
    return f"{float(value):.5f}" if isinstance(value, (int, float)) else "—"


def _seed_mark(entry: dict) -> str:
    return " *(seeding)*" if entry.get("verdict") == "seeding" else ""


def render_markdown(report: dict) -> str:
    """A compact operator-readable report. Regenerated, never appended to."""
    lines: list[str] = []
    add = lines.append
    add("# X competitive intelligence — weekly report")
    add("")
    add(f"Generated {report.get('generated_at')} by `engine/marketing/x_intel.py` "
        f"(schema `{report.get('schema')}`).")
    add(f"{report.get('n_posts', 0)} original posts from "
        f"{report.get('n_authors', 0)} accounts inside a "
        f"{report.get('window_days')}-day window "
        f"({report.get('n_posts_all_time', 0)} in the corpus all-time).")
    add("")
    add("Every number here is arithmetic over observed counters — no model scored "
        "anything (LLM-never-scores law). A post with no view count is EXCLUDED "
        "from rate denominators (`n_no_views`), never folded in as a zero. A row "
        f"under the n-floor of {report.get('n_floor')} is marked *(seeding)* and "
        "makes no ranking claim.")
    add("")

    add("## By shape (our vocabulary)")
    add("")
    add("| shape | n | no-views | med views | med likes | med interaction/view | med repost/view |")
    add("|---|---|---|---|---|---|---|")
    for e in report.get("by_shape") or []:
        add(f"| `{e.get('shape')}`{_seed_mark(e)} | {e.get('n')} | {e.get('n_no_views')} "
            f"| {_num(e.get('med_views'))} | {_num(e.get('med_likes'))} "
            f"| {_rate6(e.get('med_interaction_rate'))} | {_rate6(e.get('med_repost_rate'))} |")
    add("")

    add("## By register")
    add("")
    add("| register | n | no-views | med views | med likes | med interaction/view | med repost/view |")
    add("|---|---|---|---|---|---|---|")
    for e in report.get("by_register") or []:
        add(f"| {e.get('register')}{_seed_mark(e)} | {e.get('n')} | {e.get('n_no_views')} "
            f"| {_num(e.get('med_views'))} | {_num(e.get('med_likes'))} "
            f"| {_rate6(e.get('med_interaction_rate'))} | {_rate6(e.get('med_repost_rate'))} |")
    add("")

    add("## By account")
    add("")
    add("| account | n | med views | med likes | med interaction/view | med repost/view |")
    add("|---|---|---|---|---|---|")
    for e in report.get("by_author") or []:
        add(f"| @{e.get('author')}{_seed_mark(e)} | {e.get('n')} "
            f"| {_num(e.get('med_views'))} | {_num(e.get('med_likes'))} "
            f"| {_rate6(e.get('med_interaction_rate'))} | {_rate6(e.get('med_repost_rate'))} |")
    add("")

    add("## Shape distribution vs our quotas")
    add("")
    dist = report.get("shape_distribution") or {}
    if dist:
        add("| shape | corpus share |")
        add("|---|---|")
        for shape, share in dist.items():
            add(f"| `{shape}` | {_pct(share)} |")
    else:
        add("*No posts in the window — no distribution to report.*")
    add("")
    for gap in report.get("quota_gap") or []:
        ours = gap.get("ours_min", gap.get("ours_max"))
        bound = "min" if "ours_min" in gap else "max"
        add(f"- `{gap.get('shape')}` — ours ({bound}) {_pct(ours)} vs corpus "
            f"{_pct(gap.get('theirs'))}. {gap.get('note')}")
    add("")

    add("## Precision + signature rates")
    add("")
    prec = report.get("precision") or {}
    add("| metric | rate |")
    add("|---|---|")
    for key in ("decimal_strict_rate", "decimal_any_rate", "bare_int_rate",
                "has_number_rate", "cashtag_rate", "starts_cashtag_rate",
                "all_caps_lead_rate", "emoji_rate", "url_rate",
                "blank_spacer_rate", "quote_rate"):
        add(f"| {key.replace('_', ' ')} | {_pct(prec.get(key))} |")
    add("")
    add(f"> {prec.get('note', '')}")
    add("")

    add("## Week-over-week")
    add("")
    diff = report.get("diff_vs_prior") or {}
    if not diff.get("available"):
        add(f"*{diff.get('reason', 'no prior snapshot')}.*")
    else:
        add(f"Prior snapshot {diff.get('prior_as_of')} "
            f"({diff.get('prior_n_posts')} posts).")
        add("")
        add("| metric | was | now | delta |")
        add("|---|---|---|---|")
        for key, blk in sorted((diff.get("rates") or {}).items()):
            add(f"| {key.replace('_', ' ')} | {_pct(blk.get('was'))} "
                f"| {_pct(blk.get('now'))} | {blk.get('delta'):+.4f} |")
        add("")
        add("| shape | was | now | delta |")
        add("|---|---|---|---|")
        for key, blk in sorted((diff.get("shapes") or {}).items()):
            add(f"| `{key}` | {_pct(blk.get('was'))} | {_pct(blk.get('now'))} "
                f"| {blk.get('delta'):+.4f} |")
    add("")
    return "\n".join(lines) + "\n"


def write_report(report: dict, *, root: Path | str | None = None) -> dict:
    """Write ``report.json`` + ``WEEKLY_REPORT.md``. Both are TRACKED."""
    _write_json_atomic(report_path(root), report)
    _write_text_atomic(weekly_report_path(root), render_markdown(report))
    return {"report": str(report_path(root)), "markdown": str(weekly_report_path(root))}


def load_report(root: Path | str | None = None) -> dict:
    try:
        blob = json.loads(report_path(root).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return blob if isinstance(blob, dict) else {}


__all__ = [
    "SCHEMA", "REPORT_SCHEMA", "STATE_SCHEMA", "DEFAULTS", "REGISTERS",
    "HOUSE_REGISTER_MAP",
    "resolve_cfg", "roster",
    "intel_dir", "corpus_path", "state_path", "report_path", "weekly_report_path",
    "classify", "is_retweet", "extract_tweets", "normalize_tweet",
    "load_corpus", "append_corpus",
    "iso_stamp", "write_json_atomic",
    "load_state", "save_state", "month_bucket", "budget_check",
    "announce_budget_stop", "record_call",
    "Harvester", "analyze", "render_markdown", "write_report", "load_report",
]
