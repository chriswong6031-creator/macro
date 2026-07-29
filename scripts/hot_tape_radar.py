"""scripts/hot_tape_radar.py — the */5 intraday Hot Tape radar.

Implements research/MARKETING_HOT_TAPE_MASTERPLAN.md §3.2/§3.4: load the live
tape + the nightly context pack, run the v1 detectors
(:func:`engine.marketing.hot_tape.detect_events`), compose wire copy
(:func:`engine.marketing.hot_tape_wire.compose_wire`), draw the house tape card,
and book the result as an `immediate` outbox item so
`marketing-publish.yml post_now_item=<ids>` sends it within minutes.

    python -m scripts.hot_tape_radar [--dry-run] [--demo]

WHAT THIS LANE MAY WRITE (ledger law, masterplan §6). Only
``data/marketing/outbox/*`` (through ``outbox.enqueue`` + ``media_publish``),
``data/marketing/hot_tape_ring.jsonl`` and ``data/marketing/hot_tape_fired.jsonl``
— both append-only with ``merge=union`` — plus the runner-local, gitignored
parquet cache under ``data/massive_stock_day/``. NEVER a forward ledger, never
``data/chronicle``, never anything the nightly owns. The nightly is the sole
advancer of forward ledgers and this loop runs 81 times a day.

EVERY TICKER POST CARRIES A CHART (operator law, #3921). A single-name event
whose card cannot be drawn AND hosted is DROPPED here, not enqueued: the
publisher's defer queue is not a parking lot, and `kind="breaking"` is outside
its `_CHART_BEARING_KINDS` gate anyway, so a chartless single-name item would
ship BARE. Sector and contrarian events are breadth posts and ship text-only in
P1 (the sector grid card is P1.5).

FAIL TOWARD "NO POST". Every step is never-raise and degrades to booking
nothing; the process exits 0 unless an invariant is genuinely broken. A radar
that crashes 81 times a day is noise, and a radar that posts on a broken read is
worse than one that posts nothing.

Import discipline: pandas is NEVER imported on this path (the workflow installs
pyyaml+requests+pyarrow only). ``chart_render`` reads its parquet through
pyarrow when pandas is absent; ``requests`` and the renderer are imported lazily
inside the functions that need them so the thin test lane can import this module
with pytest+pyyaml alone.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

_CODE_ROOT = str(Path(__file__).resolve().parent.parent)
if _CODE_ROOT not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, _CODE_ROOT)

from engine.marketing import hot_tape as HT  # noqa: E402
from engine.marketing import hot_tape_wire as HW  # noqa: E402
from engine.marketing import live_verify as LV  # noqa: E402
from engine.marketing import outbox as OB  # noqa: E402
from engine.marketing import story_lock as SL  # noqa: E402

log = logging.getLogger("hot_tape_radar")

HEATMAP_REL = "site/marketdata/sp500_heatmap.json"

#: Daily-bar stores searched before hydrating from R2. This lane is the ONLY
#: caller that opts into data/massive_stock_day; chart_render's default order
#: stops at the two curated trees (see chart_render.HOT_TAPE_PRICE_SUBDIRS —
#: a test pins these two tuples equal so they cannot drift).
PRICE_SUBDIRS = ("data/baskets/ohlcv", "data/stocks", "data/massive_stock_day")
#: Where a hydrated parquet lands (gitignored — runner-local cache, never committed).
HYDRATE_SUBDIR = "data/massive_stock_day"
#: Same literal media_publish._public_base() falls back to.
_DEFAULT_PUBLIC_BASE = "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev"

#: Trigger families that are ABOUT one name, so the chart law applies.
SINGLE_NAME_TRIGGERS: frozenset[str] = frozenset({
    "mover_pop", "mover_drop", "threshold_cross", "streak_rarity", "signal_fired",
})

#: A card drawn off bars older than this is a lie about "so far today".
MAX_BAR_AGE_DAYS = 7
#: Snapshot ring depth: 36 x 5 min ~ the RTH session (masterplan T6 input).
RING_KEEP = 36
#: How long a booked-but-unposted item may still ride a fresh dispatch. Past
#: this the scheduled publish sweep owns it and we only warn (reviewer M4).
CARRYOVER_MAX_AGE_MIN = 20


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    """Directory containing engine/ — always where this script lives (../)."""
    return Path(__file__).resolve().parent.parent


def _cfg(cfg: dict | None, path: str, default: Any) -> Any:
    """Dotted lookup into the hot_tape config with a default. Never raises."""
    node: Any = cfg if isinstance(cfg, dict) else {}
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node if node is not None else default


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def _f(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def _read_json(path: Path) -> dict | None:
    try:
        if not path.exists():
            return None
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: unreadable %s (%s)", path, exc)
        return None


def _load_marketing_cfg(root: Path) -> dict:
    """config/marketing.yml, fail-soft {} — mirrors marketing_publisher's loader."""
    try:
        import yaml  # noqa: PLC0415

        path = root / "config" / "marketing.yml"
        if path.exists():
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: could not load marketing.yml: %s", exc)
    return {}


def _iso_date(raw: Any) -> date | None:
    try:
        return date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError):
        return None


def _utc_day(now: datetime) -> str:
    """The day the detector keys and the fired ledger are stamped with."""
    return now.astimezone(timezone.utc).date().isoformat()


def _et_day(now: datetime) -> str:
    """Today's US-Eastern trading date — the item's ``as_of``.

    Inside the 09:25-16:05 ET window this is always the same calendar day as
    :func:`_utc_day` (09:25 ET is 13:25Z or 14:25Z depending on the season);
    the two can only differ between 00:00Z and 05:00Z, which the window guard
    never admits.
    """
    try:
        from zoneinfo import ZoneInfo  # noqa: PLC0415

        return now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except Exception:  # noqa: BLE001
        return (now.astimezone(timezone.utc) - timedelta(hours=5)).date().isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# Inputs
# ─────────────────────────────────────────────────────────────────────────────

def load_quotes(root: Path, *, now: datetime, cfg: dict, demo: bool) -> tuple[dict, bool, float | None]:
    """(live view, fresh?, freshest age in minutes). Never raises.

    ``quotes_fresh`` is a gate on the FRESHEST quote — one stale symbol must not
    stand a 2k-symbol merge down. The other half of that trade is enforced here
    (reviewer m4): individual quotes older than the same ceiling are DROPPED
    from the detection input, because a merge that passes on its freshest entry
    still carries entries hours old, and a detector cannot tell them apart. A
    quote with no ``ts_ms`` of its own (the heatmap's pct-only tiles) is judged
    by the artifact's asof, so a fresh artifact keeps them all.
    """
    live = LV.load_live_quotes(root)
    gate_cfg = cfg
    max_age = float(_cfg(cfg, "max_quote_age_min", HT.DEFAULTS["max_quote_age_min"]))
    if demo:
        # Demo relaxes ONLY the freshness ceiling, and only through the config's
        # own demo block — never by skipping the check.
        gate_cfg = dict(cfg or {})
        gate_cfg["max_quote_age_min"] = _cfg(cfg, "demo.max_quote_age_min", 100000)
        max_age = float(gate_cfg["max_quote_age_min"])
    fresh, age = HT.quotes_fresh(live, now, gate_cfg)
    if fresh:
        live = _drop_stale_quotes(live, now=now, max_age_min=max_age)
    return live, fresh, age


def _drop_stale_quotes(live: dict, *, now: datetime, max_age_min: float) -> dict:
    """A copy of `live` carrying only quotes inside `max_age_min`. Never raises."""
    try:
        quotes = live.get("quotes") if isinstance(live.get("quotes"), dict) else None
        if not quotes:
            return live
        asof = live.get("asof")
        kept: dict[str, Any] = {}
        dropped = 0
        for sym, quote in quotes.items():
            if not isinstance(quote, dict):
                continue
            age = LV._quote_age_min(quote, asof, now)
            if age is not None and age > max_age_min:
                dropped += 1
                continue
            kept[sym] = quote
        if not dropped:
            return live
        print(f"hot-tape quote-age kept={len(kept)} dropped={dropped} "
              f"(> {max_age_min:g}m)", flush=True)
        out = dict(live)
        out["quotes"] = kept
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: per-quote staleness filter skipped: %s", exc)
        return live


def plan_signals(root: Path, *, now: datetime, max_age_days: int = 2) -> list[dict]:
    """Prophet plan levels still worth arming intraday (masterplan §3, T-signal).

    Reads the TRACKED outbox queue — the same rows the publisher folds — keeps
    `signal` items whose source carries ticker+entry+direction and whose as_of is
    within `max_age_days`, and keeps the NEWEST row per signal_id. Status is
    deliberately irrelevant: a level our engine published is our proprietary
    event whether or not that particular post ever went out.
    """
    try:
        today = now.astimezone(timezone.utc).date()
        best: dict[str, dict] = {}
        for item in OB.read_items(root):
            if str(item.get("kind") or "") != "signal":
                continue
            src = item.get("source") if isinstance(item.get("source"), dict) else {}
            ticker = str(src.get("ticker") or "").strip().upper().lstrip("$")
            entry = _f(src.get("entry"))
            direction = str(src.get("direction") or "").strip()
            if not ticker or entry is None or not direction:
                continue
            as_of = str(item.get("as_of") or "")[:10]
            stamp = _iso_date(as_of)
            if stamp is None or stamp > today or (today - stamp).days > max_age_days:
                continue
            sid = str(src.get("signal_id") or src.get("plan_item_id") or item.get("id") or "")
            if not sid:
                continue
            prior = best.get(sid)
            if prior is None or str(prior.get("as_of") or "") < as_of:
                best[sid] = {"ticker": ticker, "entry": float(entry),
                             "direction": direction, "signal_id": sid, "as_of": as_of}
        return sorted(best.values(), key=lambda s: (s["ticker"], s["signal_id"]))
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: plan_signals failed: %s", exc)
        return []


def ring_entry(
    *,
    now: datetime,
    day: str,
    live: dict,
    events: list,
    cfg: dict,
) -> dict:
    """One compact snapshot row: breadth + the index, for the T6 "$X in 3h" claims."""
    quotes = live.get("quotes") if isinstance(live.get("quotes"), dict) else {}
    n_up = n_dn = 0
    for q in quotes.values():
        pct = _f(q.get("change_pct")) if isinstance(q, dict) else None
        if pct is None:
            continue
        if pct > 0:
            n_up += 1
        elif pct < 0:
            n_dn += 1
    index_sym = str(_cfg(cfg, "detectors.contrarian.index_ticker", "SPY")).upper()
    index_q = quotes.get(index_sym) if isinstance(quotes, dict) else None
    return {
        "at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "day": day,
        "session": HT.session_phase(now),
        "n_quotes": len(quotes),
        "quotes_asof": live.get("asof"),
        "index_ticker": index_sym,
        "index_pct": _f((index_q or {}).get("change_pct")) if isinstance(index_q, dict) else None,
        "n_up": n_up,
        "n_down": n_dn,
        "n_events": len(events or []),
    }


def roll_ring(root: Path, entry: dict, *, day: str) -> None:
    """Append this pass's snapshot; compact ONLY across a day boundary.

    Rewriting a same-day ring throws away the intraday history the "$X added in
    3 hours" claims are built from, so compaction waits until the oldest row is
    from a previous day.
    """
    try:
        rows = HT.load_ring(root, 0)
        oldest = str((rows[0].get("day") if rows else "") or
                     str((rows[0].get("at") if rows else ""))[:10])
        if rows and oldest and oldest < day:
            HT.compact_ring(root, keep=RING_KEEP)
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: ring compaction skipped: %s", exc)
    HT.append_ring(root, entry)


# ─────────────────────────────────────────────────────────────────────────────
# Chart resolution (single-name events only)
# ─────────────────────────────────────────────────────────────────────────────

def _public_base() -> str:
    """R2 public base, resolved exactly the way media_publish._public_base does."""
    base = ""
    try:
        from lib import config  # noqa: PLC0415

        base = str(config.load().get("r2_data_plane", {}).get("public_base", "") or "")
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: config public_base read failed (%s) — fallback", exc)
    return (base or _DEFAULT_PUBLIC_BASE).rstrip("/")


def http_fetch(url: str, dest: Path) -> bool:
    """Download `url` to `dest` (2 tries, 10s). True on success. Never raises."""
    try:
        import requests  # noqa: PLC0415
    except ImportError:
        log.warning("hot_tape_radar: requests unavailable — cannot hydrate %s", dest.name)
        return False
    for attempt in (1, 2):
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200 and resp.content:
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(dest.suffix + ".tmp")
                tmp.write_bytes(resp.content)
                tmp.replace(dest)
                return True
            log.warning("hot_tape_radar: hydrate %s -> HTTP %s (attempt %d)",
                        url, resp.status_code, attempt)
        except Exception as exc:  # noqa: BLE001
            log.warning("hot_tape_radar: hydrate %s failed (attempt %d): %s", url, attempt, exc)
    return False


def local_parquet(ticker: str, root: Path) -> Path | None:
    """The first daily-bar parquet for `ticker` already on this host."""
    for sub in PRICE_SUBDIRS:
        path = root / sub / f"{ticker}.parquet"
        if path.exists():
            return path
    return None


def load_bars(
    ticker: str,
    root: Path,
    *,
    now: datetime,
    fetcher: Callable[[str, Path], bool] | None = None,
) -> tuple[Any, str]:
    """((bars, warmup) | None, reason).

    reason is "ok" only when bars exist AND the last one is inside
    MAX_BAR_AGE_DAYS: "no-bars" / "chart-stale" name the two ways a card is
    refused. `fetcher` None = never touch the network (the dry-run simulation).
    """
    try:
        if local_parquet(ticker, root) is None:
            if fetcher is None:
                return None, "no-bars"
            url = f"{_public_base()}/massive_stock_day/{ticker}.parquet"
            if not fetcher(url, root / HYDRATE_SUBDIR / f"{ticker}.parquet"):
                return None, "no-bars"
        from engine.marketing.chart_render import (  # noqa: PLC0415
            HOT_TAPE_PRICE_SUBDIRS,
            load_ohlcv_windowed,
        )

        # THIS lane opts into the wide tail; every other chart_render caller
        # keeps the two curated trees (chart_render.HOT_TAPE_PRICE_SUBDIRS).
        windowed = load_ohlcv_windowed(ticker, root, subdirs=HOT_TAPE_PRICE_SUBDIRS)
        if not windowed or not windowed[0] or not windowed[0][0]:
            return None, "no-bars"
        last = _iso_date(windowed[0][0][-1])
        if last is None:
            return None, "no-bars"
        if (now.astimezone(timezone.utc).date() - last).days > MAX_BAR_AGE_DAYS:
            return None, "chart-stale"
        return windowed, "ok"
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: bar load failed for %s: %s", ticker, exc)
        return None, "no-bars"


def _is_massive_only(ticker: str, root: Path) -> bool:
    """True when the ONLY bars this host can offer come from the massive store.

    Either the file is already there and no curated tree has the name, or no
    local file exists at all — in which case the hydrate lands in
    HYDRATE_SUBDIR, which is the massive store. Answering before the download
    means a refusal costs nothing.
    """
    path = local_parquet(ticker, root)
    if path is None:
        return True
    try:
        return path.parent.resolve() == (root / HYDRATE_SUBDIR).resolve()
    except Exception:  # noqa: BLE001
        return HYDRATE_SUBDIR in str(path).replace("\\", "/")


def resolve_chart(
    packet: HT.FactPacket,
    *,
    root: Path,
    marketing_cfg: dict,
    as_of: str,
    now: datetime,
    fetcher: Callable[[str, Path], bool] | None = None,
    suspect: bool = False,
) -> dict:
    """Draw + publish the HOUSE tape card for a single-name event.

    Returns {"media": entry | None, "published": dict, "reason": str}. The card
    is byte-identical in configuration to content_studio's non-signal (tape)
    variant — one renderer, one look, no drift (the 2026-07-26 incident).

    `suspect` is the pack's split-suspicion flag for this ticker. The detectors
    already refuse that record's history FACTS; the PICTURE has to go with them
    when the only bars available come from data/massive_stock_day, which is not
    split-adjusted — a card whose candles cliff 66% on a 3-for-1 is a lie-shaped
    image no caption can repair.
    """
    out: dict[str, Any] = {"media": None, "published": {}, "reason": "no-bars"}
    ticker = str(packet.ticker or "").upper()
    if not ticker:
        return out
    if suspect and _is_massive_only(ticker, root):
        out["reason"] = "suspect-history"
        return out
    windowed, reason = load_bars(ticker, root, now=now, fetcher=fetcher)
    if windowed is None:
        out["reason"] = reason
        return out
    (dates, o, h, l, c, volume), warmup = windowed
    try:
        from engine.marketing.chart_render import (  # noqa: PLC0415
            chart_cta_enabled,
            render_chart_v2,
        )
        from engine.marketing.media_publish import publish_card  # noqa: PLC0415

        svg = render_chart_v2(
            ticker=ticker,
            dates=dates,
            o=o,
            h=h,
            l=l,
            c=c,
            volume=volume,
            timeframe="DAILY",
            # A tape card draws NO marker, NO highlight disc and NO SETUP pill:
            # this post reports the tape, it does not claim an entry (gate 0.4).
            marker_index=None,
            highlight_index=None,
            pct_from_index=None,
            show_indicators=True,
            indicators=("volume", "macd"),
            warmup=warmup,
            volume_overlay=True,
            subpanel_h=190,
            height=880,
            company_name=ticker,
            logo_root=root,
            cta=chart_cta_enabled(marketing_cfg),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: render failed for %s: %s", ticker, exc)
        out["reason"] = "render-failed"
        return out

    chart_id = f"hottape-{packet.trigger}-{ticker.lower()}-{now.strftime('%H%M')}Z"
    try:
        published = publish_card(svg, chart_id=chart_id, as_of=as_of, root=root)
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: publish_card failed for %s: %s", chart_id, exc)
        published = {}
    out["published"] = dict(published or {})
    out["published"]["chart_id"] = chart_id

    url = str((published or {}).get("media_url") or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        # No hosted PNG = no picture on X. A single-name post cannot ship bare.
        out["reason"] = "no-media-url"
        return out

    entry: dict[str, Any] = {
        "kind": "chart_svg",
        "path": (published.get("svg_path")
                 or f"data/marketing/outbox/media/{as_of}/{chart_id}.svg"),
        "chart_id": chart_id,
        "ticker": ticker,
        "media_url": url,
    }
    if published.get("media_png_path"):
        entry["media_png_path"] = published["media_png_path"]
    out["media"] = entry
    out["reason"] = "ok"
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Story lock (one-owner law)
# ─────────────────────────────────────────────────────────────────────────────

def story_key_for(packet: HT.FactPacket) -> str:
    """The lock identity for one tape event."""
    subject = packet.ticker or packet.sector or ""
    return SL.story_key(
        cluster_key=f"hot_tape:{packet.trigger}:{subject}",
        event_id=packet.key,
        headline="",
    )


def story_lock_check(account: str, key: str, *, root: Path, now: datetime, cfg: dict):
    """Cross-account one-owner lock against the outbox queue.

    Mirrors press_lane._story_lock_check: returns a LockVerdict, or None when the
    lock could not run — a lock that cannot read its state must not become a
    silent publication stopper.
    """
    if not key:
        return None
    try:
        return SL.check(account, key, OB.read_items_all(root), now=now, cfg=cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=story-lock-unavailable::{key}: {exc}", flush=True)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Emit
# ─────────────────────────────────────────────────────────────────────────────

def _pack_suspect(pack: dict | None, ticker: Any) -> bool:
    """The pack's split-suspicion flag for `ticker`. False when unknown."""
    try:
        sym = str(ticker or "").upper()
        rec = ((pack or {}).get("tickers") or {}).get(sym)
        return bool(rec.get("suspect")) if isinstance(rec, dict) else False
    except Exception:  # noqa: BLE001
        return False


#: Enqueue return codes that are a FINAL verdict on this text today. Each is
#: recorded in the fired ledger with item_id None: the event was seen and
#: settled, so the cooldown/dedupe memory must know about it, and the next pass
#: must not re-detect it, re-render its card and re-offer it to the same guard
#: (reviewer M10). "invalid:*" is deliberately NOT here — that is our bug, and
#: it should shout on every pass until someone fixes it.
_TERMINAL_ENQUEUE_CODES: frozenset[str] = frozenset({
    "duplicate", "cross_account_duplicate", "cap_exceeded",
})


def emit(
    events: list,
    *,
    root: Path,
    cfg: dict,
    marketing_cfg: dict,
    fired_today: list[dict],
    now: datetime,
    as_of: str,
    demo: bool,
    dry_run: bool,
    fetcher: Callable[[str, Path], bool] | None = None,
    pack: dict | None = None,
) -> list[str]:
    """Book the top events. Returns the ids of the items actually queued."""
    max_per_run = int(_cfg(cfg, "emit.max_per_run", 3))
    max_per_day = int(_cfg(cfg, "emit.max_per_day", 20))
    wire_account = str(_cfg(cfg, "emit.account", "mastermind_news"))
    flagship_account = str(_cfg(cfg, "emit.flagship_account", "flagship"))
    # Flagship mirrors the BIGGEST events only — the floor alone is not enough,
    # because three industry routs in one sweep all clear it (operator
    # 2026-07-28). No DEFAULTS entry in hot_tape.py; the fallback lives here.
    flagship_budget = int(_cfg(cfg, "emit.flagship_max_per_run", 1))

    # DEMO IS A DEMO, NOT A CAMPAIGN (reviewer M5). demo_override relaxes every
    # detector threshold at once, so a quiet tape can produce a dozen "events"
    # of no consequence — and with the publisher armed those are REAL posts.
    # Bound the blast radius to one post, on the wire desk, never the flagship.
    if demo:
        max_per_run = min(max_per_run, 1)
        flagship_budget = 0

    day_used = sum(1 for row in (fired_today or []) if row.get("item_id"))
    booked: list[str] = []

    for packet in events:
        if len(booked) >= max_per_run:
            break
        if day_used >= max_per_day:
            print(f"::notice title=hot-tape::daily emit cap reached "
                  f"({day_used}/{max_per_day}) - standing down", flush=True)
            break

        account = HT.severity_account(packet, cfg)
        if account == flagship_account and flagship_budget <= 0:
            # Budget spent this pass: the event still ships, on the wire desk.
            account = wire_account

        key = story_key_for(packet)
        verdict = story_lock_check(account, key, root=root, now=now, cfg=marketing_cfg)
        if verdict is not None and not bool(verdict):
            print(f"hot-tape LOCK-SKIP {packet.key} owner={getattr(verdict, 'owner', '?')}",
                  flush=True)
            continue

        copy = HW.compose_wire(packet, cfg=cfg)
        if not copy or not str(copy.get("text") or "").strip():
            print(f"hot-tape REFUSE {packet.key} no-device", flush=True)
            continue
        text = str(copy["text"]).strip()

        media: list[dict] = []
        published: dict[str, Any] = {}
        chart_state = "none"
        if packet.trigger in SINGLE_NAME_TRIGGERS:
            if dry_run:
                # Simulation: local bars only, no fetch, no render, no upload.
                _, reason = load_bars(str(packet.ticker or ""), root, now=now, fetcher=None)
                if reason != "ok":
                    print(f"hot-tape DROP {packet.key} {reason}", flush=True)
                    continue
                chart_state = "ok(simulated)"
            else:
                card = resolve_chart(packet, root=root, marketing_cfg=marketing_cfg,
                                     as_of=as_of, now=now, fetcher=fetcher,
                                     suspect=_pack_suspect(pack, packet.ticker))
                if card.get("media") is None:
                    # EVERY TICKER POST CARRIES A CHART: drop, never enqueue bare.
                    print(f"hot-tape DROP {packet.key} {card.get('reason')}", flush=True)
                    continue
                media = [card["media"]]
                published = card.get("published") or {}
                chart_state = "ok"

        if dry_run:
            print(f"hot-tape WOULD-BOOK key={packet.key} account={account} "
                  f"trigger={packet.trigger} chart={chart_state} chars={len(text)}",
                  flush=True)
            print(f"    {text}", flush=True)
            booked.append(packet.key)
            day_used += 1
            if account == flagship_account:
                flagship_budget -= 1
            continue

        try:
            item = OB.make_item(
                account=account,
                kind="breaking",
                text=text,
                as_of=as_of,
                media=media,
                scheduled_at="immediate",
                slot=f"HOT-{now.strftime('%H%M')}Z",
                priority=1,
                provenance="hot_tape",
                source=HT.packet_to_source(packet, media=published),
                now=now,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("hot_tape_radar: make_item refused %s: %s", packet.key, exc)
            print(f"hot-tape ENQUEUE-SKIP {packet.key} invalid:{exc}", flush=True)
            continue
        if isinstance(item.get("source"), dict):
            # story_lock reads source.story_key — without it the lock we just
            # consulted would own nothing and never bind on the next pass.
            item["source"]["story_key"] = key
            item["source"]["devices"] = list(copy.get("devices") or [])

        rc = OB.enqueue(item, root, cfg=marketing_cfg)
        if rc == "queued":
            HT.append_fired(root, HT.fired_entry(packet, item_id=item["id"], account=account))
            booked.append(item["id"])
            day_used += 1
            if account == flagship_account:
                flagship_budget -= 1
            print(f"hot-tape BOOKED id={item['id']} account={account} "
                  f"trigger={packet.trigger} at={now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
                  flush=True)
            continue

        print(f"hot-tape ENQUEUE-SKIP {packet.key} {rc}", flush=True)
        if rc in _TERMINAL_ENQUEUE_CODES:
            # The suppression HELD — record the fire so the cooldown/dedupe
            # memory knows this event was seen, with no item_id to claim. Only
            # "duplicate" used to be recorded, so a cross-account near-dup or a
            # cap rejection came back every five minutes: re-detected, re-drawn
            # (a Chrome raster + an R2 upload each time) and re-refused.
            HT.append_fired(root, HT.fired_entry(packet, item_id=None, account=account))
        elif str(rc).startswith("invalid:"):
            # OUR bug, not a guard doing its job: an item we built failed our
            # own validator. Unrecorded on purpose so it shouts every pass.
            print(f"::warning title=hot-tape-invalid-item::{packet.key} was "
                  f"refused by outbox.validate_item ({rc}) - the radar built an "
                  "item its own schema rejects", flush=True)
    return booked


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch (booked + carryover)
# ─────────────────────────────────────────────────────────────────────────────

def dispatch_ids(
    root: Path,
    booked: list[str],
    *,
    fired_today: list[dict],
    now: datetime,
) -> list[str]:
    """The ids this pass should hand marketing-publish, oldest first.

    NOT just what we booked in the last thirty seconds (reviewer M4). The
    dispatch is ONE fire-and-forget API call and the workflow only makes it when
    THIS pass booked something — so an item booked at 10:00 whose dispatch lost
    a push race, or whose publisher run was superseded, sat in the queue until
    the next scheduled sweep, which is exactly the ">= 20 min" latency the
    program exists to beat. Every still-queued item this lane booked TODAY
    inside CARRYOVER_MAX_AGE_MIN rides along with the new one at no extra cost.

    Older-than-carryover items are the scheduled sweep's problem, and are named
    in one line-start warning so an unposted backlog is visible rather than
    silent.
    """
    out: list[str] = []
    candidates = [r for r in (fired_today or [])
                  if r.get("item_id") and str(r["item_id"]) not in booked]
    if not candidates:
        # Nothing this lane booked today is unaccounted for, so skip the fold:
        # this runs 81 times a day and most passes have no carryover at all.
        return list(booked)
    try:
        statuses = OB.fold_state(root).get("status") or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: outbox fold failed, dispatching booked only: %s", exc)
        return list(booked)

    pending: list[tuple[str, str]] = []      # (fired_at, item_id)
    stale: list[str] = []
    for row in candidates:
        item_id = str(row["item_id"])
        if statuses.get(item_id) not in ("queued", "approved"):
            continue
        when = _parse_iso(row.get("fired_at"))
        age = (now - when).total_seconds() / 60.0 if when is not None else None
        if age is None or age > CARRYOVER_MAX_AGE_MIN:
            stale.append(item_id)
            continue
        pending.append((str(row.get("fired_at") or ""), item_id))

    if stale:
        print("::warning title=hot-tape-unposted::"
              f"{len(stale)} hot-tape item(s) booked over {CARRYOVER_MAX_AGE_MIN}m "
              f"ago are still unposted: {','.join(sorted(set(stale)))} - the "
              "scheduled publish sweep owns them", flush=True)

    seen: set[str] = set()
    for _, item_id in sorted(pending):
        if item_id not in seen:
            seen.add(item_id)
            out.append(item_id)
    for item_id in booked:                   # this pass's own, newest, last
        if item_id not in seen:
            seen.add(item_id)
            out.append(item_id)
    return out


def _parse_iso(raw: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def run(
    root: Path,
    *,
    now: datetime | None = None,
    demo: bool = False,
    dry_run: bool = False,
    fetcher: Callable[[str, Path], bool] | None = None,
) -> int:
    """One radar pass. Never raises; 0 unless an invariant is genuinely broken."""
    ts = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    cfg = HT.load_config(root)

    if not bool(_cfg(cfg, "enabled", True)):
        print("::notice title=hot-tape::disabled in config/hot_tape.yml - standing down",
              flush=True)
        return 0
    # in_window enforces the weekday too, so this is the whole schedule guard.
    # The window is EASTERN, not UTC — same window in both DST regimes.
    if not demo and not HT.in_window(ts, cfg):
        print(f"::notice title=hot-tape::outside the "
              f"{_cfg(cfg, 'window_et.start', '09:25')}-{_cfg(cfg, 'window_et.end', '16:05')} ET "
              f"weekday window ({ts.strftime('%Y-%m-%dT%H:%MZ')}) - standing down", flush=True)
        return 0

    live, fresh, age = load_quotes(root, now=ts, cfg=cfg, demo=demo)
    quotes = live.get("quotes") if isinstance(live.get("quotes"), dict) else {}
    print(f"hot-tape quotes n={len(quotes)} asof={live.get('asof')} "
          f"age={age}m source={live.get('source')} demo={int(bool(demo))}", flush=True)
    if not fresh:
        print(f"::warning title=hot-tape::live quotes are stale (freshest {age}m old) "
              "- no events this pass", flush=True)
        return 0

    pack = HT.load_pack(root)
    heatmap = _read_json(root / HEATMAP_REL)
    day = _utc_day(ts)
    as_of = _et_day(ts)
    ring = HT.load_ring(root, RING_KEEP)
    fired_today = HT.load_fired(root, day)
    signals = plan_signals(root, now=ts)

    events = HT.detect_events(
        live,
        pack=pack,
        heatmap=heatmap,
        plan_signals=signals,
        ring=ring,
        fired_today=fired_today,
        now=ts,
        cfg=cfg,
        demo=demo,
    )
    print(f"hot-tape scan pack={'yes' if pack else 'no'} "
          f"bridge={int(HT.bridge_ok(pack, ts, cfg=cfg))} "
          f"tiles={len((heatmap or {}).get('tiles') or [])} signals={len(signals)} "
          f"fired_today={len(fired_today)} events={len(events)}", flush=True)
    for packet in events:
        print(f"hot-tape DETECT {packet.trigger} {packet.ticker or packet.sector} "
              f"{packet.direction} sev={packet.severity:.0f} key={packet.key}", flush=True)

    if not dry_run:
        # EVERY pass, eventless included: the ring is the intraday history.
        roll_ring(root, ring_entry(now=ts, day=day, live=live, events=events, cfg=cfg),
                  day=day)

    booked = emit(
        events,
        root=root,
        cfg=cfg,
        marketing_cfg=_load_marketing_cfg(root),
        fired_today=fired_today,
        now=ts,
        as_of=as_of,
        demo=demo,
        dry_run=dry_run,
        fetcher=fetcher if fetcher is not None else http_fetch,
        pack=pack,
    )

    if not dry_run:
        ids = dispatch_ids(root, booked, fired_today=HT.load_fired(root, day), now=ts)
        if ids:
            joined = ",".join(ids)
            print(f"hot-tape DISPATCH ids={joined}", flush=True)
            out_path = os.environ.get("GITHUB_OUTPUT", "").strip()
            if out_path:
                try:
                    with open(out_path, "a", encoding="utf-8") as fh:
                        fh.write(f"post_now_ids={joined}\n")
                except Exception as exc:  # noqa: BLE001
                    log.warning("hot_tape_radar: GITHUB_OUTPUT write failed: %s", exc)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Hot Tape intraday radar — detect live tape events and book wire posts.")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="detect + compose + simulate the card; write NOTHING")
    parser.add_argument("--demo", action="store_true",
                        help="relax window/freshness/thresholds per the config demo block "
                             "(also via env HOT_TAPE_DEMO=1); items are stamped demo")
    parser.add_argument("--root", default=None,
                        help="repo root (default: this script's parent)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s",
                        stream=sys.stderr)
    root = Path(args.root) if args.root else _repo_root()
    demo = bool(args.demo) or _flag("HOT_TAPE_DEMO")
    try:
        return run(root, demo=demo, dry_run=bool(args.dry_run))
    except Exception as exc:  # noqa: BLE001
        # Fail toward "no post": a radar that turns 81 runs a day red is noise.
        print(f"::warning title=hot-tape::radar pass failed: {exc}", flush=True)
        log.warning("hot_tape_radar: unexpected failure", exc_info=True)
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
