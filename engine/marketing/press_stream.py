"""engine/marketing/press_stream.py — twitterapi.io PUSH lane (websocket filter rules).

Replaces the killed REST hot-poll lane (``x_follow`` — see the postmortem in
config/press_sources.yml) with the SAME vendor's push transport: server-side
filter rules (``from:A OR from:B``) delivered over a websocket
(wss://ws.twitterapi.io/twitter/tweet/websocket, ``x-api-key`` header —
docs.twitterapi.io, probed 2026-08-03). Billing is per MATCHED TWEET DELIVERED
at the same $0.15/1k unit the REST lane paid — an idle hour delivers nothing
and costs nothing. That inverts the poll lane's cost shape, which re-billed the
full ~20-tweet page every 75 s whether or not anything was new (~$28/day for a
register that produces ~$0.10/day of NEW tweets).

Three parts, each independently fail-soft:

* ``chunk_rules`` / ``sync_rules`` — converge the config handle register onto
  the vendor's rule store (rule ``value`` is capped at 255 chars, so a tier
  becomes N ``from:...`` OR-chunks; ``is_effect=1`` activates). Driven by
  ``scripts/press_x_stream_rules.py`` — an OPERATOR action, never the daemon,
  so arming spend stays a deliberate step.
* ``StreamListener`` — a daemon thread holding the websocket. Every delivered
  tweet is normalized to the exact FeedItem shape the REST provider produced
  (same ids, same corroboration flags from the register) and appended to a
  JSONL spool under data/marketing/press/. Reconnects with capped backoff;
  a dead stream degrades to the free RSS estate, never to a crash.
* ``drain_spool`` — called by the press tick. Returns the spooled items and
  truncates the file. The tick feeds them through the SAME pipeline (garbage
  gate -> relevance -> corroboration -> desk/rail): push changes the
  TRANSPORT, never the laws.

The ``websockets`` import (sync client, v12+) is lazy and guarded — CI packs
and dev hosts without the lib lose the listener, not the tick. The VPS venv
carries websockets 16.0.

Thread-safety contract: the listener thread touches ONLY the spool file and
its own stats sidecar (stream_stats.json). It NEVER writes state.json /
seen.json — those belong to the tick thread, whose read-modify-write cycle a
second writer would race.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from engine.marketing.breaking_feed import FeedItem, _make_id, _parse_pub_date, _snippet

log = logging.getLogger(__name__)

# Same documented pricing unit as the REST lane (press_providers).
_PRICE_PER_1K = 0.15

_DEFAULT_WS_URL = "wss://ws.twitterapi.io/twitter/tweet/websocket"
_DEFAULT_RULES_BASE = "https://api.twitterapi.io"
_DEFAULT_KEY_ENV = "TWITTERAPI_IO_KEY"
_DEFAULT_TAG_PREFIX = "mmx-press"
_RULE_VALUE_MAX = 255
# update_rule documents 0.1–86400; the vendor's own blog example uses 5 s.
_DEFAULT_TIER_INTERVALS = {"fast": 5.0, "mid": 30.0, "slow": 120.0}

_SPOOL_NAME = "stream_spool.jsonl"
_STATS_NAME = "stream_stats.json"
_SPOOL_MAX_BYTES = 8 * 1024 * 1024   # runaway guard: drop, log, keep running
_BACKOFF_START_S = 5.0
_BACKOFF_CAP_S = 300.0
_HTTP_TIMEOUT_S = 20

# One process-wide lock per spool path (listener thread appends, tick drains).
_SPOOL_LOCKS: dict[str, threading.Lock] = {}
_SPOOL_LOCKS_GUARD = threading.Lock()


def _spool_lock(path: Path) -> threading.Lock:
    key = str(path)
    with _SPOOL_LOCKS_GUARD:
        if key not in _SPOOL_LOCKS:
            _SPOOL_LOCKS[key] = threading.Lock()
        return _SPOOL_LOCKS[key]


def _press_dir(root: Path | str) -> Path:
    return Path(root) / "data" / "marketing" / "press"


# ─────────────────────────────────────────────────────────────────────────────
# Config access
# ─────────────────────────────────────────────────────────────────────────────

def stream_cfg(press_cfg: dict) -> dict:
    """The ``x_stream`` block, always a dict."""
    block = (press_cfg or {}).get("x_stream")
    return block if isinstance(block, dict) else {}


def enabled(press_cfg: dict) -> bool:
    return bool(stream_cfg(press_cfg).get("enabled", False))


def _api_key(cfg: dict) -> str:
    return os.environ.get(str(cfg.get("key_env", _DEFAULT_KEY_ENV)), "").strip()


def handle_register(cfg: dict) -> dict[str, dict]:
    """lower-cased handle -> handle row (tier / corroboration / route flags)."""
    out: dict[str, dict] = {}
    for row in cfg.get("handles", []) or []:
        if isinstance(row, dict) and row.get("handle"):
            out[str(row["handle"]).lower()] = row
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Rule construction + remote sync (operator-driven, REST)
# ─────────────────────────────────────────────────────────────────────────────

def chunk_rules(cfg: dict, *, satire_blocklist: list[str] | None = None) -> list[dict]:
    """The desired remote rule set for this config, deterministically.

    One tier -> N rules named ``<prefix>-<tier>-<n>``, each value an OR-chunk of
    ``from:`` clauses within the vendor's 255-char value cap. Deterministic
    (register order preserved) so repeated syncs converge instead of churning.
    Satire-blocked handles never reach a rule — same ingestion-time law as the
    REST lane.
    """
    prefix = str(cfg.get("rule_tag_prefix", _DEFAULT_TAG_PREFIX))
    intervals = {**_DEFAULT_TIER_INTERVALS,
                 **(cfg.get("tier_intervals_s") or {})}
    satire = {h.lower() for h in (satire_blocklist or [])}

    by_tier: dict[str, list[str]] = {}
    for row in cfg.get("handles", []) or []:
        if not isinstance(row, dict) or not row.get("handle"):
            continue
        handle = str(row["handle"]).strip()
        if not handle or handle.lower() in satire:
            continue
        by_tier.setdefault(str(row.get("tier", "mid")), []).append(handle)

    rules: list[dict] = []
    for tier, handles in by_tier.items():
        try:
            interval = float(intervals.get(tier, _DEFAULT_TIER_INTERVALS["mid"]))
        except (TypeError, ValueError):
            interval = _DEFAULT_TIER_INTERVALS["mid"]
        chunk: list[str] = []
        for handle in handles:
            clause = f"from:{handle}"
            candidate = " OR ".join(chunk + [clause])
            if chunk and len(candidate) > _RULE_VALUE_MAX:
                rules.append({"tag": f"{prefix}-{tier}-{len([r for r in rules if r['tag'].startswith(f'{prefix}-{tier}-')]) + 1}",
                              "value": " OR ".join(chunk),
                              "interval_seconds": interval})
                chunk = [clause]
            else:
                chunk.append(clause)
        if chunk:
            rules.append({"tag": f"{prefix}-{tier}-{len([r for r in rules if r['tag'].startswith(f'{prefix}-{tier}-')]) + 1}",
                          "value": " OR ".join(chunk),
                          "interval_seconds": interval})
    return rules


def _rules_request(cfg: dict, path: str, payload: dict | None = None) -> dict:
    """One authenticated JSON call to the rules REST API. Raises on transport."""
    base = str(cfg.get("rules_base_url", _DEFAULT_RULES_BASE)).rstrip("/")
    key = _api_key(cfg)
    if not key:
        raise RuntimeError(f"{cfg.get('key_env', _DEFAULT_KEY_ENV)} unset")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = Request(
        base + path,
        data=body,
        headers={
            "X-API-Key": key,
            "Content-Type": "application/json",
            "User-Agent": "MastermindPressStream/1.0 (+https://mastermind-x.com)",
        },
        method="POST" if payload is not None else "GET",
    )
    with urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:  # noqa: S310 — https to a pinned base
        return json.loads(resp.read().decode("utf-8", "replace"))


def list_remote_rules(cfg: dict) -> list[dict]:
    data = _rules_request(cfg, "/oapi/tweet_filter/get_rules")
    rules = data.get("rules")
    return rules if isinstance(rules, list) else []


def sync_rules(cfg: dict, *, satire_blocklist: list[str] | None = None,
               deactivate_only: bool = False) -> dict:
    """Converge remote rules (ours = tag-prefixed) onto the config register.

    Adds missing rules, updates drifted ones, activates everything ours
    (``is_effect=1``), and DELETES stale prefixed rules so a handle removed
    from config stops billing. Rules without our prefix are never touched.
    ``deactivate_only=True`` flips every prefixed rule to is_effect=0 instead —
    the spend kill switch that keeps the rule inventory for a later re-arm.

    Returns {"created": [...], "updated": [...], "deleted": [...],
    "deactivated": [...], "unchanged": [...], "errors": [...]}.
    """
    prefix = str(cfg.get("rule_tag_prefix", _DEFAULT_TAG_PREFIX))
    report = {"created": [], "updated": [], "deleted": [],
              "deactivated": [], "unchanged": [], "errors": []}

    remote = [r for r in list_remote_rules(cfg)
              if str(r.get("tag", "")).startswith(prefix)]
    remote_by_tag = {str(r.get("tag")): r for r in remote}

    if deactivate_only:
        for tag, rule in remote_by_tag.items():
            try:
                _rules_request(cfg, "/oapi/tweet_filter/update_rule", {
                    "rule_id": rule.get("rule_id"),
                    "tag": tag,
                    "value": rule.get("value", ""),
                    "interval_seconds": rule.get("interval_seconds", 60),
                    "is_effect": 0,
                })
                report["deactivated"].append(tag)
            except Exception as exc:  # noqa: BLE001
                report["errors"].append(f"{tag}: {exc}")
        return report

    desired = chunk_rules(cfg, satire_blocklist=satire_blocklist)
    desired_by_tag = {r["tag"]: r for r in desired}

    for tag, want in desired_by_tag.items():
        have = remote_by_tag.get(tag)
        try:
            if have is None:
                created = _rules_request(cfg, "/oapi/tweet_filter/add_rule", {
                    "tag": tag,
                    "value": want["value"],
                    "interval_seconds": want["interval_seconds"],
                })
                rule_id = created.get("rule_id")
                # add_rule ships inactive by design; activation is update_rule.
                _rules_request(cfg, "/oapi/tweet_filter/update_rule", {
                    "rule_id": rule_id,
                    "tag": tag,
                    "value": want["value"],
                    "interval_seconds": want["interval_seconds"],
                    "is_effect": 1,
                })
                report["created"].append(tag)
            elif (str(have.get("value", "")) != want["value"]
                  or float(have.get("interval_seconds", -1) or -1)
                  != float(want["interval_seconds"])
                  or int(have.get("is_effect", 1) or 0) != 1):
                _rules_request(cfg, "/oapi/tweet_filter/update_rule", {
                    "rule_id": have.get("rule_id"),
                    "tag": tag,
                    "value": want["value"],
                    "interval_seconds": want["interval_seconds"],
                    "is_effect": 1,
                })
                report["updated"].append(tag)
            else:
                report["unchanged"].append(tag)
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"{tag}: {exc}")

    for tag, rule in remote_by_tag.items():
        if tag in desired_by_tag:
            continue
        try:
            _rules_request(cfg, "/oapi/tweet_filter/delete_rule",
                           {"rule_id": rule.get("rule_id")})
            report["deleted"].append(tag)
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"{tag}: {exc}")
    return report


# ─────────────────────────────────────────────────────────────────────────────
# Event normalization (pure; fixture-tested)
# ─────────────────────────────────────────────────────────────────────────────

def _event_tweets(payload: Any) -> list[dict]:
    """Every tweet dict in one websocket message, across the shapes the vendor
    has shipped: {"tweets":[...]}, {"data":{"tweets":[...]}}, {"tweet":{...}},
    or a bare tweet object. Unknown shapes yield [] (the caller logs)."""
    if not isinstance(payload, dict):
        return []
    tweets = payload.get("tweets")
    if tweets is None and isinstance(payload.get("data"), dict):
        tweets = payload["data"].get("tweets")
    if tweets is None and isinstance(payload.get("tweet"), dict):
        tweets = [payload["tweet"]]
    if tweets is None and payload.get("id") and payload.get("text"):
        tweets = [payload]
    return [t for t in tweets or [] if isinstance(t, dict)]


def _tweet_handle(tw: dict) -> str:
    author = tw.get("author")
    if isinstance(author, dict):
        for key in ("userName", "username", "screen_name", "screenName"):
            if author.get(key):
                return str(author[key]).strip()
    for key in ("userName", "username", "screen_name"):
        if tw.get(key):
            return str(tw[key]).strip()
    return ""


def normalize_event(payload: Any, register: dict[str, dict],
                    *, satire: set[str] | None = None) -> list[dict]:
    """Websocket message -> FeedItem dicts, byte-compatible with the REST
    lane's output so everything downstream (seen-ledger keys, corroboration
    classes, scoring, the desk) treats a pushed tweet exactly like a polled
    one. Tweets from handles outside the register are dropped — a stale remote
    rule must not widen ingestion beyond the committed register."""
    items: list[dict] = []
    satire = satire or set()
    for tw in _event_tweets(payload):
        tid = str(tw.get("id") or "").strip()
        text = str(tw.get("text") or "")
        if not tid or not text:
            continue
        handle = _tweet_handle(tw)
        row = register.get(handle.lower())
        if row is None or handle.lower() in satire:
            continue
        created = str(tw.get("createdAt") or tw.get("created_at") or "")
        snippet = _snippet(text)
        items.append(FeedItem(
            id=_make_id(f"x:{handle}", tid),
            source=f"x_{handle}",
            source_name=f"@{handle}",
            source_tier="x_relay",
            url=f"https://twitter.com/{handle}/status/{tid}",
            published_at=_parse_pub_date(created),
            headline=snippet[:120] if snippet else f"@{handle} post",
            body_snippet=snippet,
        ) | {
            "x_handle": handle,
            "corroboration_class": row.get("corroboration_class", "hearsay"),
            "strict_corroboration": bool(row.get("strict_corroboration", False)),
            "route": row.get("route", "wire"),
        })
    return items


# ─────────────────────────────────────────────────────────────────────────────
# Spool (listener appends; the press tick drains)
# ─────────────────────────────────────────────────────────────────────────────

def append_spool(root: Path | str, items: list[dict]) -> int:
    """Append normalized items to the JSONL spool. Returns rows written.

    A spool past _SPOOL_MAX_BYTES stops growing (rows dropped + one warning per
    breach) — the tick draining every 75 s makes that ceiling unreachable
    unless the daemon is wedged, and a wedged daemon must not fill the disk.
    """
    if not items:
        return 0
    path = _press_dir(root) / _SPOOL_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with _spool_lock(path):
        try:
            if path.exists() and path.stat().st_size > _SPOOL_MAX_BYTES:
                log.warning("press_stream spool over %d bytes — dropping %d rows",
                            _SPOOL_MAX_BYTES, len(items))
                return 0
            with path.open("a", encoding="utf-8") as fh:
                for item in items:
                    fh.write(json.dumps(item, default=str) + "\n")
            return len(items)
        except OSError as exc:
            log.warning("press_stream spool append failed: %s", exc)
            return 0


def drain_spool(root: Path | str) -> list[dict]:
    """Read + truncate the spool; dedupe by id preserving arrival order."""
    path = _press_dir(root) / _SPOOL_NAME
    if not path.exists():
        return []
    with _spool_lock(path):
        try:
            raw = path.read_text(encoding="utf-8")
            path.write_text("", encoding="utf-8")
        except OSError as exc:
            log.warning("press_stream spool drain failed: %s", exc)
            return []
    items: list[dict] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        iid = str(row.get("id") or "")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        items.append(row)
    return items


def _bump_stats(root: Path | str, n_delivered: int, *, connected: bool) -> None:
    """Listener-thread-owned sidecar: delivered counts + estimated USD by
    month, last event stamp, connection state. NEVER state.json (tick-owned)."""
    path = _press_dir(root) / _STATS_NAME
    try:
        stats = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        stats = {}
    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    bucket = stats.setdefault("months", {}).setdefault(
        month, {"delivered": 0, "est_usd": 0.0})
    if n_delivered:
        bucket["delivered"] = int(bucket.get("delivered", 0)) + n_delivered
        bucket["est_usd"] = round(
            float(bucket.get("est_usd", 0.0)) + n_delivered / 1000.0 * _PRICE_PER_1K, 6)
        stats["last_event_at"] = now.isoformat()
    stats["connected"] = bool(connected)
    stats["updated_at"] = now.isoformat()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(stats), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        log.warning("press_stream stats write failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Listener thread
# ─────────────────────────────────────────────────────────────────────────────

class StreamListener:
    """Holds the websocket in a daemon thread; spools every delivered tweet.

    Fail-soft everywhere: no key / no ``websockets`` lib / a refused connection
    all degrade to "no stream items this tick" while the RSS estate carries the
    wire. Reconnects with exponential backoff capped at 5 min.
    """

    def __init__(self, press_cfg: dict, root: Path | str,
                 *, satire_blocklist: list[str] | None = None):
        self.cfg = stream_cfg(press_cfg)
        self.root = Path(root)
        self.register = handle_register(self.cfg)
        self.satire = {h.lower() for h in (satire_blocklist or [])}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> bool:
        """True when the thread launched (key + lib + register present)."""
        if not self.register:
            log.info("press_stream: no handles in register — listener not started")
            return False
        if not _api_key(self.cfg):
            log.info("press_stream: %s unset — listener not started (free lanes carry the wire)",
                     self.cfg.get("key_env", _DEFAULT_KEY_ENV))
            return False
        try:
            import websockets.sync.client  # noqa: F401, PLC0415
        except ImportError:
            log.warning("press_stream: websockets lib unavailable — listener not started")
            return False
        self._thread = threading.Thread(
            target=self._run, name="press-x-stream", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    # -- internals -----------------------------------------------------------

    def _run(self) -> None:
        from websockets.sync.client import connect  # noqa: PLC0415

        url = str(self.cfg.get("ws_url", _DEFAULT_WS_URL))
        key = _api_key(self.cfg)
        backoff = _BACKOFF_START_S
        while not self._stop.is_set():
            try:
                with connect(
                    url,
                    additional_headers={"x-api-key": key},
                    open_timeout=_HTTP_TIMEOUT_S,
                    close_timeout=5,
                ) as ws:
                    log.info("press_stream: connected to %s", url)
                    _bump_stats(self.root, 0, connected=True)
                    backoff = _BACKOFF_START_S
                    # recv timeout keeps the loop responsive to stop(); the
                    # vendor pings under the hood (websockets answers pongs).
                    while not self._stop.is_set():
                        try:
                            message = ws.recv(timeout=30)
                        except TimeoutError:
                            continue
                        self._handle_message(message)
            except Exception as exc:  # noqa: BLE001 — reconnect, never crash the daemon
                if self._stop.is_set():
                    break
                log.warning("press_stream: connection lost (%s: %s) — retry in %.0fs",
                            type(exc).__name__, exc, backoff)
                _bump_stats(self.root, 0, connected=False)
                self._stop.wait(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP_S)
        _bump_stats(self.root, 0, connected=False)

    def _handle_message(self, message: str | bytes) -> None:
        try:
            payload = json.loads(message)
        except (TypeError, ValueError):
            return
        items = normalize_event(payload, self.register, satire=self.satire)
        if items:
            written = append_spool(self.root, items)
            _bump_stats(self.root, written, connected=True)
        elif isinstance(payload, dict) and _event_tweets(payload):
            # Tweets arrived but none survived the register gate — a remote
            # rule wider than the committed register. Say so; do not ingest.
            log.warning("press_stream: %d delivered tweet(s) matched no "
                        "registered handle — run press_x_stream_rules --sync",
                        len(_event_tweets(payload)))


def start_listener(press_cfg: dict, root: Path | str,
                   *, satire_blocklist: list[str] | None = None) -> StreamListener | None:
    """Daemon entrypoint: construct + start; None when the lane stays dark."""
    if not enabled(press_cfg):
        return None
    listener = StreamListener(press_cfg, root, satire_blocklist=satire_blocklist)
    return listener if listener.start() else None
