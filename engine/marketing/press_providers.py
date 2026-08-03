"""engine.marketing.press_providers — PRESS-FEEDS providers (D05 Addendum 2).

Adds FeedItem providers to the breaking-feed adapter seam, each consuming a
DOCUMENTED published endpoint (mirror RSS, mirror JSON archive, twitterapi.io read
API, Alpaca's official news REST API). No first-party scraping, no browser
automation, no Nitter — the appendix §2 scrape kills STAND.

Public providers (each returns the standard breaking_feed FeedItem dict, plus a
few provider-specific keys that downstream relevance/summary ignore):
    TrumpstruthProvider        source_tier="mirror",   author=Trump, no key
    TwitterApiIoProvider       source_tier="x_relay",  key via env TWITTERAPI_IO_KEY
    CnnTruthBackfillProvider   source_tier="mirror",   backfill/corroboration only
    AlpacaNewsProvider         source_tier="wire",     keys via env ALPACA_API_KEY_ID
                                                       + ALPACA_API_SECRET_KEY

Public helper:
    display_source_name(name) -> str   generic display name, never an @handle

Design contract (mirrors earnings_feed / breaking_feed):
    - Pure parse_* functions are network-free and fixture-tested directly.
    - fetch() is the ONLY network path; never called in tests.
    - All fail-soft: return [] rather than raise on any error.
    - Providers make ZERO repo/git writes. Cursor / spend / seen state is written
      by the daemon under data/marketing/press/ (gitignored), never here — a
      provider only READS the session_state dict handed to it and MUTATES it
      in place (same pattern as breaking_feed.poll_source).

FeedItem extra keys (never break the 8-key minimum contract):
    truth_status_id  str   the Truth Social status id (mirror items) — the
                           cross-mirror dedupe key so trumpstruth + CNN never
                           double-emit the same post.
    corroboration_class  str  "direct-quote" | "hearsay" | "wire"
    x_handle         str   the source handle (x_relay items)
    symbols          list  tickers the wire itself tagged (Alpaca items only,
                           present only when the article carried any)
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from engine.marketing.breaking_feed import (
    FeedItem,
    _make_id,
    _parse_pub_date,
    _snippet,
    _strip_html,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_UA = "MastermindBreakingBot/1.0 (+https://mastermind-x.com)"
_FEED_TIMEOUT = 15
_MAX_MIRROR_BYTES = 32 * 1024 * 1024   # CNN archive is ~19 MB — allow headroom
_MAX_RSS_BYTES = 4 * 1024 * 1024
_TRUTH_NS = "{https://truthsocial.com/ns}"

# twitterapi.io documented pricing floor (docs.twitterapi.io, probed 2026-07-27):
#   "$0.15/1k tweets", "Minimum charge: $0.00015 per request".
_TW_PRICE_PER_1K = 0.15
_TW_MIN_CHARGE = 0.00015

# Alpaca /v1beta1/news (docs.alpaca.markets, probed 2026-07-29): query params
# start / end / sort / limit (1-50) / symbols / page_token; auth headers
# APCA-API-KEY-ID + APCA-API-SECRET-KEY; response {news: [...], next_page_token}.
_ALPACA_REST_URL = "https://data.alpaca.markets/v1beta1/news"
_ALPACA_LIMIT_MAX = 50            # endpoint hard maximum
_ALPACA_MAX_BYTES = 8 * 1024 * 1024
_ALPACA_BACKOFF_CAP_S = 900       # 15 min ceiling on the 429 ladder

#: Preflight notices already emitted BY THIS PROCESS. A keyless host has to say
#: so ONCE — not once per 75 s tick for the life of the daemon.
_PREFLIGHT_NOTICED: set[str] = set()

# ─────────────────────────────────────────────────────────────────────────────
# SOURCE-ACCOUNT DE-HANDLING (operator law 2026-08-02)
#
# We reword and republish news; we NEVER tag or brand the original account. Live
# posts on @mastermindx001 on 2026-08-02/03 shipped "-- @FirstSquawk reporting",
# "-- @financialjuice reporting" and a "@BRICSinfo · AGGREGATOR" card chip. That
# is an X flag risk (unsolicited mentions of accounts we relay) and it reads as
# low-quality scraping, so the DISPLAY name of an X relay item is generic.
#
# THE `x_handle` FIELD STAYS. It is the independence key
# (story_spine.independence_key keys on it first), so de-handling it would
# silently collapse two relays of one claim onto one source and kill the
# >=2-independent-sources instant path. Only the human-visible name changes.
# ─────────────────────────────────────────────────────────────────────────────

#: The public display name every X-relay item carries instead of "@handle".
GENERIC_RELAY_DISPLAY = "Newswire"

#: A token indistinguishable from a bare X handle: no whitespace, no dot, only
#: [A-Za-z0-9_], within X's 15-character handle limit.
_HANDLE_SHAPED_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


def display_source_name(name: str) -> str:
    """Public display name for a source — never an @handle (operator law 2026-08-02).

    Returns :data:`GENERIC_RELAY_DISPLAY` for anything empty, anything starting
    with ``@``, and any bare handle-shaped token; otherwise the name, stripped.

    FAIL-CLOSED, and it costs something. A single-word publisher name
    ("Reuters") is shape-identical to an X handle, so a config that supplies one
    on THIS lane also collapses to the generic display. That trade is
    deliberate: the false positive costs a generic word in one post, while the
    false negative is a live @mention of an account we relay — the defect this
    function exists to make unreachable. Multi-word / dotted names
    ("Truth Social (via CNN archive)", "cnbc.com") are not handle-shaped and
    pass through untouched, which is every non-relay caller.
    """
    text = str(name or "").strip()
    if not text or text.startswith("@") or _HANDLE_SHAPED_RE.match(text):
        return GENERIC_RELAY_DISPLAY
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _preflight_notice(slug: str, message: str) -> None:
    """Emit a start-of-line ``::notice`` at most once per process for `slug`.

    Repo GH-annotation law: bare ``print`` at LINE START with ``flush`` — never
    through a logger, whose level prefix makes GitHub drop the annotation.
    """
    if slug in _PREFLIGHT_NOTICED:
        return
    _PREFLIGHT_NOTICED.add(slug)
    print(f"::notice title={slug}::{message}", flush=True)


def _as_utc(dt: datetime | None) -> datetime:
    """The run's clock as an aware UTC datetime (wall clock only as a fallback)."""
    d = dt or datetime.now(tz=timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def _iso_to_dt(raw: Any) -> datetime | None:
    """Parse an ISO8601 stamp to aware UTC; None when absent or unparseable."""
    if not raw:
        return None
    try:
        d = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def _cfg_int(raw: Any, default: int) -> int:
    """A non-negative int from config; anything unusable falls back to `default`."""
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return default
    return val if val >= 0 else default

def _rt_target_status_id(content: str) -> str | None:
    """If content is a bare 'RT: <truthsocial status url>', return the target id.

    Mirror RTs render as 'RT: https://truthsocial.com/users/<user>/statuses/<id>'.
    The RT wrapper itself is a distinct status id; the *target* is what carries
    the substance, and corroboration should point at the target post.
    """
    m = re.search(r"/statuses/(\d+)", content or "")
    return m.group(1) if m else None


def _is_month_key(ts_iso: str) -> str:
    """YYYY-MM month bucket for the twitterapi.io spend cap."""
    try:
        dt = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.now(tz=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m")


# ─────────────────────────────────────────────────────────────────────────────
# TrumpstruthProvider — trumpstruth.org RSS (no key)
# ─────────────────────────────────────────────────────────────────────────────

class TrumpstruthProvider:
    """Parse the trumpstruth.org RSS mirror into FeedItems.

    The feed carries a `truth:` namespace (xmlns:truth="https://truthsocial.com/ns")
    with truth:originalId (the Truth Social status id) and truth:originalUrl. Items
    include RTs (description 'RT: <url>') and full post content. source_tier="mirror",
    author=Trump. Dedupe key = the Truth Social status id (truth_status_id).
    """

    source_tier = "mirror"

    def __init__(self, source_cfg: dict):
        self.cfg = source_cfg
        self.key = source_cfg.get("key", "trumpstruth")
        self.source_name = source_cfg.get("source_name", "Truth Social (via trumpstruth.org)")
        self.author = source_cfg.get("author", "Donald J. Trump")
        self.url = source_cfg.get("url", "https://trumpstruth.org/feed")
        self.poll_interval_s = int(source_cfg.get("poll_interval_s", 75))
        self.user_agent = str(source_cfg.get("user_agent", _DEFAULT_UA))

    # ---- pure parse (fixture-tested) ----------------------------------------

    def parse(self, xml_text: str) -> list[FeedItem]:
        """Parse the trumpstruth RSS text into FeedItems. Never raises."""
        try:
            return self._parse(xml_text)
        except Exception as exc:  # noqa: BLE001
            print(f"[press_providers] trumpstruth parse error: {exc}", file=sys.stderr)
            return []

    def _parse(self, xml_text: str) -> list[FeedItem]:
        import xml.etree.ElementTree as ET  # noqa: PLC0415

        root = ET.fromstring(xml_text)
        channel = root.find("channel")
        if channel is None:
            channel = root
        results: list[FeedItem] = []
        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or link).strip()
            pub_raw = (item.findtext("pubDate") or "").strip()
            desc_raw = (item.findtext("description") or "").strip()

            # truth: namespace fields — the canonical Truth Social status id/url
            original_id = (item.findtext(f"{_TRUTH_NS}originalId") or "").strip()
            original_url = (item.findtext(f"{_TRUTH_NS}originalUrl") or "").strip()

            if not (title or link or desc_raw):
                continue

            snippet = _snippet(desc_raw)
            headline = _strip_html(title) if title else snippet[:120]

            # Dedupe key: the Truth Social status id when present; else the mirror
            # status URL. RT wrappers keep their own id but point at the target.
            status_id = original_id or _rt_target_status_id(desc_raw) or guid or link
            item_id = _make_id(self.key, status_id)

            # RTs carry no title text of substance — flag them but keep them
            # (an RT of a market-moving account is itself a signal).
            is_rt = bool(re.search(r"(?<!\w)RT:\s", desc_raw))

            results.append(FeedItem(
                id=item_id,
                source=self.key,
                source_name=self.source_name,
                source_tier=self.source_tier,
                url=original_url or link or guid,
                published_at=_parse_pub_date(pub_raw),
                headline=headline or "(Truth Social post)",
                body_snippet=snippet,
            ) | {
                "truth_status_id": str(original_id or status_id),
                "author": self.author,
                "is_retweet": is_rt,
                "corroboration_class": "direct-quote",
                "mirror_url": link,
            })
        return results

    # ---- network fetch (never in tests) -------------------------------------

    def fetch(
        self, *, root: Path | str, session_state: dict[str, Any],
        offline: bool = False, now: datetime | None = None,
    ) -> list[FeedItem]:
        # FREE mirror RSS (no key, no per-request charge): `offline` and `now` are
        # accepted for a uniform poll_all signature but ignored — a dry-run may
        # still read this free feed to preview the pipeline (M2), and this lane
        # books no spend, so it has no month bucket to agree about.
        text = _conditional_get(
            self.url, self.key, session_state,
            user_agent=self.user_agent, interval_s=self.poll_interval_s,
            max_bytes=_MAX_RSS_BYTES,
        )
        if text is None:
            return []
        return self.parse(text)


# ─────────────────────────────────────────────────────────────────────────────
# CnnTruthBackfillProvider — CNN Truth archive JSON (backfill / corroboration)
# ─────────────────────────────────────────────────────────────────────────────

class CnnTruthBackfillProvider:
    """Parse the CNN Truth Social archive JSON (backfill / corroboration only).

    JSON array of {id, created_at, content, url, media[], *_count}. 19 MB payload:
    conditional GET is mandatory and the poll cadence is slow (never the hot loop).
    Shares Truth status ids with the trumpstruth mirror, so cross-mirror dedupe
    via truth_status_id prevents double-emission.
    """

    source_tier = "mirror"

    def __init__(self, source_cfg: dict):
        self.cfg = source_cfg
        self.key = source_cfg.get("key", "cnn_truth_backfill")
        self.source_name = source_cfg.get("source_name", "Truth Social (via CNN archive)")
        self.author = source_cfg.get("author", "Donald J. Trump")
        self.url = source_cfg.get("url", "https://ix.cnn.io/data/truth-social/truth_archive.json")
        self.poll_interval_s = int(source_cfg.get("poll_interval_s", 21600))
        self.user_agent = str(source_cfg.get("user_agent", _DEFAULT_UA))
        # Only surface the newest N rows on each parse — the archive is a full
        # history; the daemon's seen-ledger handles the rest.
        self.max_rows = int(source_cfg.get("max_rows", 200))

    def parse(self, json_text: str) -> list[FeedItem]:
        try:
            return self._parse(json_text)
        except Exception as exc:  # noqa: BLE001
            print(f"[press_providers] cnn_truth parse error: {exc}", file=sys.stderr)
            return []

    def _parse(self, json_text: str) -> list[FeedItem]:
        data = json.loads(json_text)
        if isinstance(data, dict):
            rows = data.get("items") or data.get("data") or []
        elif isinstance(data, list):
            rows = data
        else:
            return []

        results: list[FeedItem] = []
        for row in rows[: self.max_rows]:
            if not isinstance(row, dict):
                continue
            status_id = str(row.get("id") or "").strip()
            content = str(row.get("content") or "")
            url = str(row.get("url") or "")
            created = str(row.get("created_at") or "")
            if not (status_id or content):
                continue

            snippet = _snippet(content)
            item_id = _make_id(self.key, status_id or url)
            is_rt = bool(re.search(r"(?<!\w)RT:\s", content))
            headline = snippet[:120] if snippet else "(Truth Social post)"

            results.append(FeedItem(
                id=item_id,
                source=self.key,
                source_name=self.source_name,
                source_tier=self.source_tier,
                url=url,
                published_at=_parse_pub_date(created),
                headline=headline,
                body_snippet=snippet,
            ) | {
                "truth_status_id": status_id,
                "author": self.author,
                "is_retweet": is_rt,
                "corroboration_class": "direct-quote",
            })
        return results

    def fetch(
        self, *, root: Path | str, session_state: dict[str, Any],
        offline: bool = False, now: datetime | None = None,
    ) -> list[FeedItem]:
        # FREE mirror JSON archive (no key, no per-request charge): `offline` and
        # `now` are accepted for a uniform poll_all signature but ignored (M2).
        text = _conditional_get(
            self.url, self.key, session_state,
            user_agent=self.user_agent, interval_s=self.poll_interval_s,
            max_bytes=_MAX_MIRROR_BYTES,
        )
        if text is None:
            return []
        return self.parse(text)


# ─────────────────────────────────────────────────────────────────────────────
# TwitterApiIoProvider — twitterapi.io read relay (key via env; skips when unset)
# ─────────────────────────────────────────────────────────────────────────────

class TwitterApiIoProvider:
    """Poll the x_follow allowlist via twitterapi.io's read API.

    Endpoint (docs.twitterapi.io, probed 2026-07-27):
        GET https://api.twitterapi.io/twitter/user/last_tweets
        params: userName, cursor, includeReplies
        auth header: X-API-Key
        response: {tweets: [{id, text, createdAt, ...}], has_next_page, next_cursor}

    The endpoint has no native since-id param, so since-id filtering is done
    client-side: keep tweets whose numeric id > the stored per-handle cursor, and
    advance the cursor to the newest id seen. Per-request accounting + a monthly
    spend-cap guard stops the lane at cap and emits a start-of-line ::warning.

    Skips CLEANLY (returns []) when TWITTERAPI_IO_KEY is unset — no account is
    created for this build.

    BILLED lane: every fetch that reaches the network costs real money (min charge
    $0.00015/request). A dry-run/offline tick MUST NOT reach it — the spend it
    would bill is never persisted in dry-run, so repeated dry-runs would bill the
    monthly cap counter cannot see (M2). fetch(offline=True) returns [] before any
    request; the free RSS/JSON mirror providers ignore `offline` and may still poll.
    """

    source_tier = "x_relay"
    billed = True   # M2: this lane costs money; dry-run/offline must skip its fetch

    def __init__(self, x_follow_cfg: dict, *, spend_cap_usd: float,
                 satire_blocklist: list[str] | None = None):
        self.cfg = x_follow_cfg
        self.base_url = x_follow_cfg.get("base_url", "https://api.twitterapi.io")
        self.endpoint = x_follow_cfg.get("endpoint", "/twitter/user/last_tweets")
        self.auth_header = x_follow_cfg.get("auth_header", "X-API-Key")
        self.key_env = x_follow_cfg.get("key_env", "TWITTERAPI_IO_KEY")
        self.exclude_pcf = bool(x_follow_cfg.get("exclude_pcf_labeled", True))
        self.poll_tiers = x_follow_cfg.get("poll_tiers", {})
        self.user_agent = str(x_follow_cfg.get("user_agent", _DEFAULT_UA))
        self.spend_cap_usd = float(spend_cap_usd)
        # Lower-cased satire blocklist for O(1) membership at ingestion.
        self.satire = {h.lower() for h in (satire_blocklist or [])}
        # Handle list; PCF-labeled + satire handles dropped at construction.
        self.handles = [
            h for h in x_follow_cfg.get("handles", [])
            if isinstance(h, dict) and h.get("handle")
            and h["handle"].lower() not in self.satire
            and not (self.exclude_pcf and h.get("pcf_labeled"))
        ]

    # ---- pure parse (fixture-tested) ----------------------------------------

    def parse_tweets(
        self, response_json: str | dict, handle_cfg: dict, *, since_id: str | None
    ) -> tuple[list[FeedItem], str | None]:
        """Parse one user/last_tweets response into (FeedItems, new_since_id).

        Keeps only tweets whose numeric id > since_id; the returned new_since_id
        is the max id seen (or the old since_id when nothing newer arrived).
        Network-free — fixture-tested directly.
        """
        try:
            data = response_json if isinstance(response_json, dict) else json.loads(response_json)
        except Exception as exc:  # noqa: BLE001
            print(f"[press_providers] twitterapiio parse error: {exc}", file=sys.stderr)
            return [], since_id

        # Response shape tolerance: tweets may sit at top level or under data.
        tweets = data.get("tweets")
        if tweets is None and isinstance(data.get("data"), dict):
            tweets = data["data"].get("tweets")
        if not isinstance(tweets, list):
            return [], since_id

        handle = str(handle_cfg.get("handle", "")).strip()
        corr_class = handle_cfg.get("corroboration_class", "hearsay")
        strict = bool(handle_cfg.get("strict_corroboration", False))
        route = handle_cfg.get("route", "wire")

        since_int = _as_int(since_id)
        max_id_int = since_int
        results: list[FeedItem] = []
        for tw in tweets:
            if not isinstance(tw, dict):
                continue
            tid = str(tw.get("id") or "").strip()
            text = str(tw.get("text") or "")
            created = str(tw.get("createdAt") or tw.get("created_at") or "")
            if not tid:
                continue
            tid_int = _as_int(tid)
            # Since-id gate (client-side — endpoint has no native sinceId).
            if since_int is not None and tid_int is not None and tid_int <= since_int:
                continue
            if tid_int is not None and (max_id_int is None or tid_int > max_id_int):
                max_id_int = tid_int

            snippet = _snippet(text)
            # De-handled headline fallback (operator law 2026-08-02): a text-less
            # tweet used to yield "@FirstSquawk post", which is a source tag on
            # the one surface that goes straight into a post body.
            headline = snippet[:120] if snippet else "Wire flash"
            item_id = _make_id(f"x:{handle}", tid)
            results.append(FeedItem(
                id=item_id,
                source=f"x_{handle}",
                # DISPLAY name only — generic by law. `source` and `x_handle`
                # below still carry the handle, which is what corroboration and
                # the independence key read. The old value ("@{handle}") is
                # passed through the normalizer rather than dropped, so the
                # @-prefixed branch catches it whatever the config supplied —
                # including a handle longer than X's own 15-character limit.
                source_name=display_source_name(f"@{handle}"),
                source_tier=self.source_tier,
                url=f"https://twitter.com/{handle}/status/{tid}" if handle else "",
                published_at=_parse_pub_date(created),
                headline=headline,
                body_snippet=snippet,
            ) | {
                "x_handle": handle,
                "corroboration_class": corr_class,
                "strict_corroboration": strict,
                "route": route,
                # XG-W5: observed engagement, carried from the response body we
                # ALREADY paid for. This is a parse of bytes already on the wire —
                # no extra request, no new endpoint, no new spend path, and no
                # first-party X scraping (twitterapi.io stays the only X read
                # path). It is the free virality ground truth the scoring brain's
                # source_authority prior accrues from; absent keys yield 0s, and
                # a source that never carries counts stays on the neutral prior.
                "x_engagement": _engagement(tw),
            })

        new_since = str(max_id_int) if max_id_int is not None else since_id
        return results, new_since

    # ---- network fetch (never in tests) -------------------------------------

    def fetch(
        self, *, root: Path | str, session_state: dict[str, Any],
        offline: bool = False, now: datetime | None = None,
    ) -> list[FeedItem]:
        """Poll every handle whose per-tier interval has elapsed.

        session_state["twitterapiio"] holds:
            cursors: {handle -> since_id}
            spend:   {month_key -> {requests, tweets, usd}}
        Mutated in place; the daemon persists it. At the monthly cap the lane
        STOPS and emits a start-of-line ::warning (never via a logger).

        offline=True (dry-run / disarmed): return [] before ANY network request
        (M2). This lane is billed and dry-run does not persist spend, so a network
        read here would bill money the cap counter never records.

        `now` is THE RUN'S CLOCK and picks the spend month bucket. The Actions
        wire seeds and folds that bucket from its own `ts`; re-reading the wall
        clock here meant a tick at 23:59:30 on the last of the month could book
        its delta into the NEXT month, which the caller's fold never reads — a
        request billed for real against a counter nothing increments.
        """
        import os  # noqa: PLC0415

        if offline:
            # M2: billed lane — never touch the network in a dry-run/offline tick.
            return []

        api_key = os.environ.get(self.key_env, "").strip()
        if not api_key:
            # Skip cleanly — no key, no lane, no account created.
            return []

        st = session_state.setdefault("twitterapiio", {})
        cursors: dict[str, str] = st.setdefault("cursors", {})
        spend: dict[str, dict] = st.setdefault("spend", {})
        last_poll: dict[str, float] = st.setdefault("last_poll", {})

        now_ts = time.time()
        _month_at = now or datetime.now(tz=timezone.utc)
        if _month_at.tzinfo is None:
            _month_at = _month_at.replace(tzinfo=timezone.utc)
        month_key = _month_at.astimezone(timezone.utc).strftime("%Y-%m")
        month_spend = spend.setdefault(month_key, {"requests": 0, "tweets": 0, "usd": 0.0})

        # Spend-cap guard — STOP the lane at cap (checked before spending more).
        if float(month_spend.get("usd", 0.0)) >= self.spend_cap_usd:
            print(
                f"::warning title=twitterapiio-spend-cap::twitterapi.io monthly spend "
                f"${float(month_spend['usd']):.4f} reached cap ${self.spend_cap_usd:.2f} "
                f"for {month_key} — lane stopped",
                flush=True,
            )
            return []

        all_items: list[FeedItem] = []
        for hcfg in self.handles:
            handle = str(hcfg.get("handle", "")).strip()
            if not handle:
                continue
            interval = int(self.poll_tiers.get(hcfg.get("tier", "mid"), 105))
            if (now_ts - float(last_poll.get(handle, 0.0))) < interval:
                continue

            # Re-check the cap before EACH request so a burst can't overshoot.
            if float(month_spend.get("usd", 0.0)) >= self.spend_cap_usd:
                print(
                    f"::warning title=twitterapiio-spend-cap::twitterapi.io monthly spend "
                    f"${float(month_spend['usd']):.4f} reached cap ${self.spend_cap_usd:.2f} "
                    f"for {month_key} — lane stopped mid-tick",
                    flush=True,
                )
                break

            last_poll[handle] = now_ts
            raw = self._request(api_key, handle)
            if raw is None:
                # A FAILED CALL IS STILL A BILLED CALL (#3960 minor). ``_request``
                # collapses a network error, a timeout AND an HTTP 4xx/5xx into
                # None, and the vendor's floor is per REQUEST, not per successful
                # request: "Minimum charge: $0.00015 per request". Skipping the
                # accounting here made every failure free in our ledger, so a
                # handle that 401s or times out on all 288 ticks a day burned real
                # money the cap could not see -- and the cap is the only thing
                # standing between this lane and the shared $75 account bucket.
                # Bill the floor, then move on.
                month_spend["requests"] = int(month_spend.get("requests", 0)) + 1
                month_spend["usd"] = round(
                    float(month_spend.get("usd", 0.0)) + _TW_MIN_CHARGE, 6)
                continue

            # Account the request (min charge floor + per-tweet price).
            items, new_since = self.parse_tweets(
                raw, hcfg, since_id=cursors.get(handle)
            )
            n_tweets = _count_tweets(raw)
            cost = max(_TW_MIN_CHARGE, n_tweets / 1000.0 * _TW_PRICE_PER_1K)
            month_spend["requests"] = int(month_spend.get("requests", 0)) + 1
            month_spend["tweets"] = int(month_spend.get("tweets", 0)) + n_tweets
            month_spend["usd"] = round(float(month_spend.get("usd", 0.0)) + cost, 6)

            cursors[handle] = new_since or cursors.get(handle) or ""
            all_items.extend(items)

        return all_items

    def _request(self, api_key: str, handle: str) -> dict | None:
        """One GET /twitter/user/last_tweets call. Returns parsed JSON or None."""
        qs = urlencode({"userName": handle, "includeReplies": "false"})
        url = f"{self.base_url}{self.endpoint}?{qs}"
        try:
            req = Request(url, headers={  # noqa: S310
                "User-Agent": self.user_agent,
                self.auth_header: api_key,
                "Accept": "application/json",
            })
            with urlopen(req, timeout=_FEED_TIMEOUT) as resp:  # noqa: S310
                raw = resp.read(_MAX_RSS_BYTES + 1)
            text = raw.decode("utf-8", errors="replace")
            return json.loads(text)
        except Exception as exc:  # noqa: BLE001
            print(f"[press_providers] twitterapiio request error ({handle}): {exc}",
                  file=sys.stderr)
            return None


# ─────────────────────────────────────────────────────────────────────────────
# AlpacaNewsProvider — official Alpaca (Benzinga-powered) news REST API
# ─────────────────────────────────────────────────────────────────────────────

class AlpacaNewsProvider:
    """Poll Alpaca's OFFICIAL news REST endpoint (IS-W1 free corroboration spine).

    Endpoint (docs.alpaca.markets, probed 2026-07-29):
        GET https://data.alpaca.markets/v1beta1/news
        params: start, end, sort (asc|desc, by updated date), limit (1-50),
                symbols, page_token
        auth headers: APCA-API-KEY-ID / APCA-API-SECRET-KEY
        response: {news: [{id, headline, author, created_at, updated_at,
                           summary, content, url, images[], symbols[], source}],
                   next_page_token}

    NEVER a scraping path — this is the documented, keyed API, and the only news
    lane Alpaca publishes. One page per poll, newest first; the daemon's shared
    seen-ledger owns cross-tick dedupe, this provider owns the cursor.

    ARMING IS AN ENV DECISION, NOT A CONFIG ONE. ``alpaca.enabled: true`` ships in
    config/press_sources.yml for every host; a host without BOTH env keys is a
    total no-op — zero network, one ``::notice`` per PROCESS (not per tick), no
    state writes. That is what lets the same committed config ride the VPS daemon
    and the Actions wire while only the credentialed host actually polls.

    PER-PROVIDER COLD START. The global press cold-start prime only covers a
    brand-new deployment; a provider added mid-life arrives at a lane whose seen
    ledger is warm, so its first page — up to 50 back-dated articles — would look
    like 50 simultaneous breaks. The FIRST poll therefore ingests NOTHING and only
    advances the cursor to the newest timestamp it saw. A history page is not
    live news.

    CURSOR SEMANTICS. ``since`` tracks the newest INGESTED ``created_at``; it is
    passed back as ``start`` and re-checked client-side so only strictly-newer
    items survive (the endpoint's interval is inclusive, and it filters/sorts on
    UPDATED date while we key on CREATED date). Since ``updated_at >= created_at``
    always, a ``start`` cut on updated date can only over-fetch, never hide an
    item whose created_at is newer than the cursor — the client-side strict
    compare then does the real work. Nothing is lost; re-served rows are dropped.

    STATE (``session_state["alpaca"]``, mutated in place, persisted by the caller):
        since         iso  newest ingested created_at — the cursor
        last_poll     iso  politeness stamp; min_interval_s is floored against it
        primed_at     iso  when the cold-start prime ran (audit only)
        backoff_until iso  429 ladder; backoff_s is the current step (cap 15 min)
    """

    source_tier = "wire"
    #: FeedItem `source` — the lane, not the byline. The article's own publisher
    #: (Benzinga, and whatever else Alpaca resells) lands in `source_name`.
    key = "alpaca_benzinga"
    #: Where this provider's cursor lives inside the shared session_state dict.
    state_key = "alpaca"

    def __init__(self, alpaca_cfg: dict):
        self.cfg = dict(alpaca_cfg or {})
        self.rest_url = str(self.cfg.get("rest_url") or _ALPACA_REST_URL)
        self.key_env = str(self.cfg.get("key_env") or "ALPACA_API_KEY_ID")
        self.secret_env = str(self.cfg.get("secret_env") or "ALPACA_API_SECRET_KEY")
        # Politeness floor. The daemon ticks every ~75 s today; this holds even if
        # that shrinks, because it is checked against a PERSISTED last_poll stamp
        # rather than against the tick interval.
        self.min_interval_s = _cfg_int(self.cfg.get("min_interval_s"), 60)
        self.limit = min(max(_cfg_int(self.cfg.get("limit"), 50), 1), _ALPACA_LIMIT_MAX)
        self.snippet_max_chars = min(
            max(_cfg_int(self.cfg.get("snippet_max_chars"), 400), 1), 2000)
        self.user_agent = str(self.cfg.get("user_agent") or _DEFAULT_UA)

    # ---- pure parse (fixture-tested) ----------------------------------------

    def parse(
        self, payload: str | dict, *, since: str | None = None
    ) -> tuple[list[FeedItem], str | None]:
        """Parse one /v1beta1/news response into (FeedItems, newest_ingested_iso).

        Keeps only items strictly newer than `since`; de-dupes the page by article
        id; drops headline-less rows. `newest_ingested_iso` is the max
        ``published_at`` among the items RETURNED (None when none were), which is
        what the caller advances the cursor to. Network-free — never raises.
        """
        try:
            return self._parse(payload, since=since)
        except Exception as exc:  # noqa: BLE001
            # A start-of-line annotation, not a stderr line: every OTHER failure
            # in this lane (url / oversize / fetch / auth / 429 / http) surfaces
            # in the Actions summary, and this one is the most dangerous of the
            # set — on the COLD-START poll a swallowed mapper fault still primes
            # the cursor and still prints the success notice, so the lane reports
            # itself armed and healthy while ingesting nothing, forever.
            print(f"::warning title=alpaca-parse::Alpaca news page could not be "
                  f"mapped ({type(exc).__name__}: {exc}) — no items this tick",
                  flush=True)
            return [], None

    def _parse(
        self, payload: str | dict, *, since: str | None
    ) -> tuple[list[FeedItem], str | None]:
        data = payload if isinstance(payload, dict) else json.loads(payload)
        if not isinstance(data, dict):
            return [], None
        rows = data.get("news")
        if rows is None:
            rows = data.get("data") or []
        if not isinstance(rows, list):
            return [], None

        since_dt = _iso_to_dt(since)
        newest: datetime | None = None
        page_ids: set[str] = set()
        results: list[FeedItem] = []
        stampless = 0

        for row in rows:
            if not isinstance(row, dict):
                continue
            raw_id = str(row.get("id") or "").strip()
            if not raw_id or raw_id in page_ids:
                continue                       # page-local dedupe by article id
            headline = _strip_html(str(row.get("headline") or ""))
            if not headline:
                continue                       # a headline-less row is not news
            raw_ts = str(row.get("created_at") or row.get("updated_at") or "").strip()
            pub_dt = _iso_to_dt(raw_ts) if raw_ts else None
            # Review N3: a row whose timestamp is absent OR unparseable is
            # DROPPED, counted, and noticed — it can neither be ordered against
            # the cursor nor advance it. The earlier rule ingested it with an
            # ingest-time stamp, which either stalled the cursor forever (an
            # all-stampless page re-serves every poll) or fast-forwarded it to
            # "now" past items still in flight. Both are worse than losing a
            # malformed row the other wire sources will re-carry.
            if pub_dt is None:
                stampless += 1
                continue
            published_at = _parse_pub_date(raw_ts)
            if since_dt is not None and pub_dt <= since_dt:
                continue                       # strictly-newer-than-cursor

            page_ids.add(raw_id)
            if pub_dt is not None and (newest is None or pub_dt > newest):
                newest = pub_dt

            # Summaries carry markup often enough that a raw pass-through would
            # ship "<p>" into a post body; strip before the config cap so the cap
            # counts characters a reader sees.
            body = str(row.get("summary") or "") or str(row.get("content") or "")
            item = FeedItem(
                id=f"alpaca:{raw_id}",
                # Review N7: PER-PUBLISHER source key, not one lane-wide slug.
                # garbage_gate's source blocklist reads `source`, so collapsing
                # every resold publisher into "alpaca_benzinga" left the
                # operator no lever against one bad reseller short of a URL
                # host entry. The lane prefix stays so provenance still says
                # which pipe carried it.
                source=_alpaca_source_key(row.get("source")),
                source_name=_pretty_wire_name(row.get("source")),
                source_tier=self.source_tier,
                url=str(row.get("url") or ""),
                published_at=published_at,
                headline=headline,
                body_snippet=_strip_html(body)[: self.snippet_max_chars],
            ) | {
                "corroboration_class": "wire",
                "author": str(row.get("author") or ""),
            }
            symbols = [str(s).strip().upper()
                       for s in (row.get("symbols") or []) if str(s).strip()]
            if symbols:
                # Downstream scoring tolerates extra keys; the wire's own ticker
                # tags are strictly better than re-deriving them from prose.
                item["symbols"] = symbols
            results.append(item)

        if stampless:
            print(f"::notice title=alpaca-timestampless::{stampless} Alpaca news "
                  f"row(s) carried no parseable timestamp — dropped (cannot be "
                  "ordered against the cursor)", flush=True)
        return results, (newest.isoformat() if newest is not None else None)

    # ---- network fetch (never in tests) -------------------------------------

    def fetch(
        self, *, root: Path | str, session_state: dict[str, Any],
        offline: bool = False, now: datetime | None = None,
    ) -> list[FeedItem]:
        """One page of news, or [] — this lane never kills the tick.

        `offline=True` (dry-run / disarmed inspection): zero network AND zero
        state writes. The cursor is CONSUMING, and a dry-run's state is thrown
        away, so advancing it here would hide those items from the next live run
        (the same non-consuming law the daemon applies to the seen ledger).

        `now` IS THE RUN'S CLOCK — the politeness floor and the backoff stamp are
        both measured against it, so the Actions lane (fresh checkout, committed
        cursors.json) and the daemon (long-lived process) agree on one clock.
        """
        import os  # noqa: PLC0415

        if offline:
            return []

        api_key = os.environ.get(self.key_env, "").strip()
        api_secret = os.environ.get(self.secret_env, "").strip()
        if not (api_key and api_secret):
            missing = " + ".join(
                name for name, val in ((self.key_env, api_key),
                                       (self.secret_env, api_secret)) if not val
            )
            _preflight_notice(
                "alpaca-preflight",
                f"Alpaca news lane configured but {missing} unset on this host — "
                "lane skipped (env presence arms it, never the config file alone)",
            )
            return []

        st = session_state.setdefault(self.state_key, {})
        now_dt = _as_utc(now)

        backoff_until = _iso_to_dt(st.get("backoff_until"))
        if backoff_until is not None and now_dt < backoff_until:
            return []

        last_poll = _iso_to_dt(st.get("last_poll"))
        if last_poll is not None and \
                (now_dt - last_poll).total_seconds() < self.min_interval_s:
            return []

        # Stamp BEFORE the request: a request that fails still consumed the slot,
        # so a hard-failing endpoint is polled at the floor, not on every tick.
        st["last_poll"] = now_dt.isoformat()
        since = str(st.get("since") or "")
        payload = self._request(api_key, api_secret, since=since, state=st, now=now_dt)
        if payload is None:
            return []                          # _request already annotated

        st.pop("backoff_until", None)
        st.pop("backoff_s", None)
        items, newest = self.parse(payload, since=since or None)

        if not since:
            # PER-PROVIDER COLD START: prime the cursor, ingest nothing. An empty
            # first page still primes (to the run clock) — there is nothing older
            # to miss, and leaving the cursor unset would re-arm the prime against
            # the first real batch. This is the ONE `sort=desc` request the lane
            # makes: page one of "newest first" IS the freshest timestamp.
            st["since"] = newest or now_dt.isoformat()
            st["primed_at"] = now_dt.isoformat()
            print(f"::notice title=alpaca-cold-start::Alpaca news cursor primed to "
                  f"{st['since']} from {len(items)} history item(s) — none ingested "
                  "(a history page is not live news)", flush=True)
            return []

        if newest:
            st["since"] = newest
            # Review N2: cursored polls are `sort=asc` + `start=<cursor>`, so a
            # backlog wider than one page catches up CONTIGUOUSLY — the cursor
            # advances to the newest of the OLDEST page and the next poll picks
            # up exactly where this one stopped. A full page therefore means
            # "more to come next poll", not silent loss; say so at notice level.
            rows = payload.get("news")
            if rows is None:
                rows = payload.get("data") or []
            if isinstance(rows, list) and len(rows) >= self.limit:
                print(f"::notice title=alpaca-page-catchup::Alpaca news returned "
                      f"a full page ({len(rows)} of limit {self.limit}) — older "
                      "backlog continues on the next poll (asc cursor advance)",
                      flush=True)
        return items

    def _request(self, api_key: str, api_secret: str, *, since: str,
                 state: dict, now: datetime) -> dict | None:
        """One GET /v1beta1/news call. Returns parsed JSON, or None after warning."""
        from urllib.error import HTTPError  # noqa: PLC0415

        if not str(self.rest_url).lower().startswith("https://"):
            print(f"::warning title=alpaca-url::refusing a non-https Alpaca news url "
                  f"({self.rest_url!r}) — lane skipped", flush=True)
            return None

        # Review N2: the cold-start probe (no cursor) asks newest-first so page
        # one carries the freshest stamp to prime to. Every CURSORED poll asks
        # OLDEST-first from the cursor, so a backlog wider than one page drains
        # contiguously across polls instead of the cursor leaping over it.
        params = {"limit": str(self.limit), "sort": "desc" if not since else "asc"}
        if since:
            params["start"] = since
        url = f"{self.rest_url}?{urlencode(params)}"
        try:
            req = Request(url, headers={  # noqa: S310
                "User-Agent": self.user_agent,
                "Accept": "application/json",
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": api_secret,
            })
            with urlopen(req, timeout=_FEED_TIMEOUT) as resp:  # noqa: S310
                raw = resp.read(_ALPACA_MAX_BYTES + 1)
            if len(raw) > _ALPACA_MAX_BYTES:
                print(f"::warning title=alpaca-oversize::Alpaca news page exceeded "
                      f"{_ALPACA_MAX_BYTES} bytes — dropped for this tick", flush=True)
                return None
            return json.loads(raw.decode("utf-8", errors="replace"))
        except HTTPError as exc:
            self._note_http_error(exc, state=state, now=now)
            return None
        except Exception as exc:  # noqa: BLE001
            # Network/DNS/timeout/JSON — honest and loud, but the wire lives on.
            print(f"::warning title=alpaca-fetch::Alpaca news poll failed "
                  f"({type(exc).__name__}: {exc}) — no items from this lane this tick",
                  flush=True)
            return None

    def _note_http_error(self, exc: Any, *, state: dict, now: datetime) -> None:
        """Annotate an HTTP failure; 429 also arms the doubling backoff ladder."""
        code = _cfg_int(getattr(exc, "code", 0), 0)

        if code in (401, 403):
            print(f"::warning title=alpaca-auth::Alpaca news rejected the credentials "
                  f"(HTTP {code}) — check {self.key_env} / {self.secret_env} on this "
                  "host; lane skipped", flush=True)
            return

        if code == 429:
            step = float(state.get("backoff_s") or 0.0)
            step = min(max(step * 2.0, float(self.min_interval_s or 60)),
                       float(_ALPACA_BACKOFF_CAP_S))
            state["backoff_s"] = step
            state["backoff_until"] = (now + timedelta(seconds=step)).isoformat()
            print(f"::warning title=alpaca-rate-limit::Alpaca news returned HTTP 429 — "
                  f"backing off {int(step)}s (until {state['backoff_until']}, cap "
                  f"{_ALPACA_BACKOFF_CAP_S}s)", flush=True)
            return

        print(f"::warning title=alpaca-http::Alpaca news returned HTTP {code} — "
              "no items from this lane this tick", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# Small pure helpers
# ─────────────────────────────────────────────────────────────────────────────

def _alpaca_source_key(raw: Any) -> str:
    """Machine `source` key for one Alpaca-carried article: ``alpaca_<publisher>``.

    Review N7: the blocklist lever. ``garbage_gate._source_blocked`` reads
    ``source`` (never ``source_name``), so the key must name the actual
    publisher the wire resold, one slug per publisher. Lowercase, non-alnum
    collapsed to underscores; an article naming no publisher falls to the
    lane's historical ``alpaca_benzinga``.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", str(raw or "").strip().lower()).strip("_")
    return f"alpaca_{slug}" if slug else "alpaca_benzinga"


def _pretty_wire_name(raw: Any) -> str:
    """Display name from an article's own `source` field ("benzinga" -> "Benzinga").

    Only an ALL-LOWERCASE value is title-cased; anything already carrying capitals
    ("MarketWatch") is left exactly as the wire sent it, because ``str.title()``
    would mangle it to "Marketwatch". An absent source is named for the lane
    rather than invented — we do not know who wrote it.
    """
    name = str(raw or "").strip()
    if not name:
        return "Alpaca"
    return name.title() if name.islower() else name


def _engagement(tweet: dict) -> dict[str, int]:
    """Like/retweet/reply/view counts from a twitterapi.io tweet object.

    Key-name tolerant (the endpoint has shipped both camelCase and snake_case
    shapes); any absent or unparseable field reads 0. Never raises — a shape
    change must degrade the scoring brain's authority prior, never break the
    wire parse that feeds the whole press lane.
    """
    aliases: dict[str, tuple[str, ...]] = {
        "likes": ("likeCount", "like_count", "favorite_count", "favoriteCount"),
        "retweets": ("retweetCount", "retweet_count"),
        "replies": ("replyCount", "reply_count"),
        "views": ("viewCount", "view_count", "impressionCount"),
    }
    out: dict[str, int] = {}
    for field, keys in aliases.items():
        value = 0
        for key in keys:
            raw = tweet.get(key)
            if raw is None:
                continue
            try:
                value = int(float(raw))
            except (TypeError, ValueError):
                continue
            break
        out[field] = max(0, value)
    return out


def _as_int(s: str | None) -> int | None:
    try:
        return int(str(s))
    except (TypeError, ValueError):
        return None


def _count_tweets(response: str | dict) -> int:
    try:
        data = response if isinstance(response, dict) else json.loads(response)
        tweets = data.get("tweets")
        if tweets is None and isinstance(data.get("data"), dict):
            tweets = data["data"].get("tweets")
        return len(tweets) if isinstance(tweets, list) else 0
    except Exception:  # noqa: BLE001
        return 0


def _conditional_get(
    url: str,
    key: str,
    session_state: dict[str, Any],
    *,
    user_agent: str,
    interval_s: int,
    max_bytes: int,
) -> str | None:
    """Politeness-floored conditional GET (ETag / Last-Modified). Returns text or None.

    Mirrors breaking_feed.poll_source's conditional-GET + backoff discipline but
    lives here so the mirror providers do not depend on breaking_feed's per-source
    RSS config shape. Mutates session_state[key] in place; makes ZERO repo writes.
    """
    from urllib.error import HTTPError  # noqa: PLC0415

    if not str(url).lower().startswith(("http://", "https://")):
        print(f"[press_providers] {key}: refusing non-http(s) url", file=sys.stderr)
        return None

    src_state = session_state.setdefault(key, {})
    now_ts = time.time()
    last_poll = float(src_state.get("last_poll_ts", 0))
    fail_count = int(src_state.get("fail_count", 0))
    backoff_until = float(src_state.get("backoff_until", 0))

    effective_interval = min(interval_s * (2 ** min(fail_count, 8)), 3600)
    if now_ts < backoff_until or (now_ts - last_poll) < effective_interval:
        return None

    src_state["last_poll_ts"] = now_ts

    try:
        req = Request(url, headers={"User-Agent": user_agent})  # noqa: S310
        if src_state.get("etag"):
            req.add_header("If-None-Match", src_state["etag"])
        if src_state.get("last_modified"):
            req.add_header("If-Modified-Since", src_state["last_modified"])

        with urlopen(req, timeout=_FEED_TIMEOUT) as resp:  # noqa: S310
            raw = resp.read(max_bytes + 1)
            if len(raw) > max_bytes:
                print(f"[press_providers] {key}: feed exceeds {max_bytes} bytes — dropped",
                      file=sys.stderr)
                src_state["fail_count"] = fail_count + 1
                return None
            text = raw.decode("utf-8", errors="replace")
            new_etag = resp.headers.get("ETag", "")
            new_last_mod = resp.headers.get("Last-Modified", "")

        src_state["fail_count"] = 0
        src_state.pop("backoff_until", None)
        if new_etag:
            src_state["etag"] = new_etag
        if new_last_mod:
            src_state["last_modified"] = new_last_mod
        return text

    except HTTPError as exc:
        if exc.code == 304:
            src_state["fail_count"] = 0
            return None
        if exc.code in (429, 503):
            retry_after = (exc.headers.get("Retry-After", "") if exc.headers else "")
            try:
                delay = float(retry_after)
            except (TypeError, ValueError):
                delay = 0.0
            if delay > 0:
                src_state["backoff_until"] = now_ts + delay
        src_state["fail_count"] = fail_count + 1
        print(f"[press_providers] {key}: HTTP {exc.code}", file=sys.stderr)
        return None
    except Exception as exc:  # noqa: BLE001
        src_state["fail_count"] = fail_count + 1
        print(f"[press_providers] {key}: fetch error: {exc}", file=sys.stderr)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Provider factory + poll_all
# ─────────────────────────────────────────────────────────────────────────────

_PROVIDER_CLASSES = {
    "trumpstruth": TrumpstruthProvider,
    "cnn_truth_backfill": CnnTruthBackfillProvider,
}


def build_providers(press_cfg: dict) -> list:
    """Instantiate mirror + x_relay + wire providers from a parsed press_sources.yml.

    Returns a flat list of provider objects (each exposing .fetch(root=, session_state=)).
    Skips lanes that are disabled or unconfigured. The twitterapi.io and Alpaca lanes
    are constructed whenever configured (each skips cleanly at fetch time when its
    key is absent) — CONSTRUCTION IS FREE AND SILENT, arming happens in fetch().
    """
    providers: list = []
    satire = list(press_cfg.get("satire_blocklist") or [])

    for src in press_cfg.get("truth_mirrors", []) or []:
        if not isinstance(src, dict) or not src.get("enabled", True):
            continue
        cls = _PROVIDER_CLASSES.get(src.get("provider"))
        if cls is not None:
            providers.append(cls(src))

    x_follow = press_cfg.get("x_follow") or {}
    if x_follow.get("handles"):
        spend_cap = float(
            (press_cfg.get("spend") or {}).get("twitterapiio_monthly_cap_usd", 75.0)
        )
        providers.append(TwitterApiIoProvider(
            x_follow, spend_cap_usd=spend_cap, satire_blocklist=satire
        ))

    # Alpaca (Benzinga-powered) news REST. `enabled: true` ships for every host;
    # a host without both env keys no-ops inside fetch() with ONE process-level
    # notice, so this construction is harmless everywhere.
    alpaca_cfg = press_cfg.get("alpaca") or {}
    if isinstance(alpaca_cfg, dict) and alpaca_cfg.get("enabled"):
        providers.append(AlpacaNewsProvider(alpaca_cfg))

    return providers


def poll_all(root: Path | str, press_cfg: dict, session_state: dict[str, Any],
             *, offline: bool = False, now: datetime | None = None) -> list[FeedItem]:
    """Poll every configured press provider once; return all fetched FeedItems.

    NOT deduplicated here (the daemon owns the shared seen-ledger across the wire
    RSS lane and the press lane). One dead provider never kills the tick.
    session_state is mutated in place and persisted by the daemon.

    offline=True (dry-run / disarmed): BILLED providers (provider.billed truthy —
    the twitterapi.io lane) return [] without touching the network so a dry-run
    bills nothing (M2). The Alpaca lane also stands down offline — it is free, but
    its cursor is CONSUMING and a dry-run's state is discarded, so a poll there
    would hide those items from the next live run. Free RSS/JSON mirror providers
    (whose cursor is an ETag, not a since-stamp) still fetch.

    `now` IS THE RUN'S CLOCK and decides the spend month bucket. The caller
    (``marketing_press_wire.run``) already picked a month from its own `ts` when
    it seeded the counter and again when it books the delta; the provider used to
    re-read ``datetime.now`` for the same decision, so a tick that straddles a
    month boundary booked its spend into one month and folded the other — money
    spent into a bucket nothing ever reads. One clock, one month.
    """
    items: list[FeedItem] = []
    for prov in build_providers(press_cfg):
        try:
            items.extend(prov.fetch(root=root, session_state=session_state,
                                    offline=offline, now=now))
        except Exception as exc:  # noqa: BLE001
            print(f"[press_providers] provider {type(prov).__name__} error: {exc}",
                  file=sys.stderr)
    return items
