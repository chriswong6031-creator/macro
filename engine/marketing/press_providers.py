"""engine.marketing.press_providers — PRESS-FEEDS providers (D05 Addendum 2).

Adds three FeedItem providers to the breaking-feed adapter seam, each consuming a
DOCUMENTED published endpoint (mirror RSS, mirror JSON archive, twitterapi.io read
API). No first-party scraping, no browser automation, no Nitter — the appendix §2
scrape kills STAND.

Public providers (each returns the standard breaking_feed FeedItem dict, plus a
few provider-specific keys that downstream relevance/summary ignore):
    TrumpstruthProvider        source_tier="mirror",   author=Trump, no key
    TwitterApiIoProvider       source_tier="x_relay",  key via env TWITTERAPI_IO_KEY
    CnnTruthBackfillProvider   source_tier="mirror",   backfill/corroboration only

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
    corroboration_class  str  "direct-quote" | "hearsay"
    x_handle         str   the source handle (x_relay items)
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
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


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

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
        offline: bool = False,
    ) -> list[FeedItem]:
        # FREE mirror RSS (no key, no per-request charge): `offline` is accepted
        # for a uniform poll_all signature but ignored — a dry-run may still read
        # this free feed to preview the pipeline (M2).
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
        offline: bool = False,
    ) -> list[FeedItem]:
        # FREE mirror JSON archive (no key, no per-request charge): `offline` is
        # accepted for a uniform poll_all signature but ignored (M2).
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
            headline = snippet[:120] if snippet else f"@{handle} post"
            item_id = _make_id(f"x:{handle}", tid)
            results.append(FeedItem(
                id=item_id,
                source=f"x_{handle}",
                source_name=f"@{handle}",
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
        offline: bool = False,
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
        month_key = datetime.now(tz=timezone.utc).strftime("%Y-%m")
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
# Small pure helpers
# ─────────────────────────────────────────────────────────────────────────────

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
    """Instantiate mirror + x_relay providers from a parsed press_sources.yml dict.

    Returns a flat list of provider objects (each exposing .fetch(root=, session_state=)).
    Skips lanes that are disabled or unconfigured. The twitterapi.io lane is always
    constructed (it skips cleanly at fetch time when the key is absent).
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

    return providers


def poll_all(root: Path | str, press_cfg: dict, session_state: dict[str, Any],
             *, offline: bool = False) -> list[FeedItem]:
    """Poll every configured press provider once; return all fetched FeedItems.

    NOT deduplicated here (the daemon owns the shared seen-ledger across the wire
    RSS lane and the press lane). One dead provider never kills the tick.
    session_state is mutated in place and persisted by the daemon.

    offline=True (dry-run / disarmed): BILLED providers (provider.billed truthy —
    the twitterapi.io lane) return [] without touching the network so a dry-run
    bills nothing (M2). Free RSS/JSON mirror providers still fetch.
    """
    items: list[FeedItem] = []
    for prov in build_providers(press_cfg):
        try:
            items.extend(prov.fetch(root=root, session_state=session_state,
                                    offline=offline))
        except Exception as exc:  # noqa: BLE001
            print(f"[press_providers] provider {type(prov).__name__} error: {exc}",
                  file=sys.stderr)
    return items
