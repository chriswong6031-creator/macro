"""scripts/live_breadth_poller.py — live intraday market-breadth poller.

Phase 2 ENGINE lane of the Live Tape program
(research/LIVE_TAPE_SCOREBOARD_MASTERPLAN.md §4, decisions D6/D7). Produces
``site/live/breadth.json``: advancers / decliners / % > 50-&-200DMA / 52w
new-high-low counts across the S&P Composite 1500 by size tier, refreshed on a
1-2 min RTH cadence.

HOW (D6 — snapshot join, NOT a per-name websocket):
  - ONE Polygon full-market snapshot call per cycle (the no-``tickers``-filter
    form of the endpoint engine.live_quotes already wraps for filtered use) —
    never a per-symbol fan-out, never a websocket, never a new entitlement. The
    plan is STANDARD (15-min delayed); ``delay_min`` is stamped honestly as
    15 + snapshot staleness.
  - Per-name thresholds (prev_close / MA50 / MA200 / 52w hi-lo, tier membership)
    are computed IN-MEMORY at startup from the SAME nightly-baked stores the
    breadth builders read — ``data/<ns>/_closes_cache.parquet`` +
    ``constituents.parquet`` for ns in {breadth, midcap_breadth, smallcap_breadth}
    — and refreshed only when a store's date advances. ZERO writes under
    ``data/`` (house ledger law: intraday lanes discard data/ writes).
  - The join/count maths live in the pure module ``engine.live_breadth``
    (unit-tested without a socket); this file is the I/O + loop shell.

Output goes ONLY to ``site/live/breadth.json`` (+ a tiny state file under the OS
tmpdir if needed). DISPLAY-TIER: no store writes, no ledger advancement, no
stance copy.

Usage:
  # Single cycle (smoke / tests) — always emits, with the honest `session` value
  python -m scripts.live_breadth_poller --once

  # Single cycle, no network — emits a fail-soft empty-tiers payload
  python -m scripts.live_breadth_poller --once --offline

  # Single cycle then commit+push site/live/breadth.json (host-side)
  python -m scripts.live_breadth_poller --once --publish

  # Continuous RTH loop (self-exits outside 09:25-16:05 ET on weekdays)
  python -m scripts.live_breadth_poller --rth-only --publish

Config block ``live_breadth:`` in config.yml (all optional — defaults below):
  cadence_sec:   90     # target poll interval (60-120s window)
  jitter_sec:    10     # +-uniform jitter added to each sleep
Falls back to the shared ``live.delayed_min`` (15) for the vendor delay floor.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from lib import config

log = logging.getLogger("live_breadth_poller")

# Stdlib zoneinfo (repo convention) — no pytz.
ET = ZoneInfo("America/New_York")

# RTH window (America/New_York) — poller active within this range (mirrors
# live_flow_poller: 09:25 warm-up through a 16:05 wind-down).
RTH_START_H, RTH_START_M = 9, 25
RTH_END_H,   RTH_END_M   = 16, 5
# Premarket window opens at 04:00 ET (Polygon serves premarket prints; session
# tag "pre" from 04:00 to 09:30, "rth" 09:30-16:00, "post" 16:00-20:00).
PRE_START_H = 4
RTH_OPEN_H,  RTH_OPEN_M  = 9, 30
RTH_CLOSE_H              = 16
POST_END_H               = 20

# Cadence bounds (masterplan §4 gate 5: 60-120s).
CADENCE_MIN, CADENCE_MAX = 60, 120
DEFAULT_CADENCE = 90
DEFAULT_JITTER = 10

# Polygon full-market snapshot: the SAME endpoint engine.live_quotes wraps for
# the filtered (per-symbol) call — with NO `tickers` param it returns the whole
# US-stocks market in one request (D6). Vendor delay floor for the STANDARD plan.
_POLY_SNAPSHOT = "/v2/snapshot/locale/us/markets/stocks/tickers"
DEFAULT_DELAY_MIN = 15

_SIGTERM = {"stop": False}


def _install_sigterm() -> None:
    """Graceful SIGTERM/SIGINT — finish the current cycle, then exit the loop."""
    def _handler(signum, _frame):
        log.info("poller: signal %s received — will exit after this cycle", signum)
        _SIGTERM["stop"] = True
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):   # e.g. not the main thread
            pass


# ── config ────────────────────────────────────────────────────────────────────

def _cfg() -> dict:
    try:
        return dict(config.load().get("live_breadth", {}) or {})
    except Exception:  # noqa: BLE001
        return {}


def _delay_floor() -> int:
    """Vendor delay floor (minutes). Shared with the live overlay's `delayed_min`
    so the two live surfaces stamp the same honest delay; overridable in the
    live_breadth block."""
    cfg = _cfg()
    if cfg.get("delayed_min") is not None:
        return int(cfg["delayed_min"])
    try:
        return int((config.load().get("live") or {}).get("delayed_min", DEFAULT_DELAY_MIN))
    except Exception:  # noqa: BLE001
        return DEFAULT_DELAY_MIN


def _cadence(cfg: dict) -> int:
    c = int(cfg.get("cadence_sec", DEFAULT_CADENCE))
    return max(CADENCE_MIN, min(CADENCE_MAX, c))


# ── session window ─────────────────────────────────────────────────────────────

def session_tag(now: datetime | None = None) -> str:
    """US-equity session label for `now` (America/New_York): one of
    "pre" | "rth" | "post" | "closed". Weekends + outside 04:00-20:00 ET = closed.

    Pure over an injected `now` (tests pass fixed DST-boundary datetimes — no
    wall-clock-dependent assertions). Never raises.
    """
    try:
        et = (now or datetime.now(timezone.utc)).astimezone(ET)
        if et.weekday() >= 5:                       # Sat / Sun
            return "closed"
        mins = et.hour * 60 + et.minute
        pre_start = PRE_START_H * 60
        rth_open = RTH_OPEN_H * 60 + RTH_OPEN_M      # 570
        rth_close = RTH_CLOSE_H * 60                 # 960
        post_end = POST_END_H * 60                   # 1200
        if mins < pre_start or mins >= post_end:
            return "closed"
        if mins < rth_open:
            return "pre"
        if mins < rth_close:
            return "rth"
        return "post"
    except Exception:  # noqa: BLE001
        return "closed"


def within_rth(now: datetime | None = None) -> bool:
    """True iff `now` (ET) is within the poller's continuous window
    (09:25-16:05 on a weekday). Mirrors live_flow_poller._within_rth. Never
    raises — returns False on any error."""
    try:
        et = (now or datetime.now(timezone.utc)).astimezone(ET)
        if et.weekday() >= 5:
            return False
        t = et.hour * 60 + et.minute
        start = RTH_START_H * 60 + RTH_START_M       # 565
        end = RTH_END_H * 60 + RTH_END_M             # 965
        return start <= t <= end
    except Exception:  # noqa: BLE001
        return False


# ── threshold store (loaded once at startup; refreshed when the cache advances) ─

class ThresholdStore:
    """In-memory per-name thresholds for all three S&P size tiers, derived from
    the nightly-baked breadth close caches. Loaded once, cheaply refreshed only
    when a cache's newest date advances. READ-ONLY over data/ — never writes.

    Per tier it holds ``{canonical_symbol: {prev_close, ma50, ma200, hi52, lo52}}``
    computed exactly as collectors/breadth.compute does (MA windows + 52w NH/NL
    window from config), plus the member set (from constituents.parquet, falling
    back to the close-cache columns).
    """

    def __init__(self) -> None:
        # tier_key -> {canonical_symbol: threshold-dict}
        self.by_tier: dict[str, dict[str, dict]] = {}
        # tier_key -> newest cache date seen (for advance detection)
        self._asof: dict[str, str] = {}
        # tier_key -> namespace / config block name
        from engine.live_breadth import BREADTH_TIERS
        self._tiers = BREADTH_TIERS

    def _cache_path(self, ns: str) -> Path:
        return config.data_dir() / ns / "_closes_cache.parquet"

    def _members(self, ns: str, close_cols: list[str]) -> list[str]:
        """Tier membership: constituents.parquet index if present, else the close
        cache's columns. Canonicalised (dot->dash) to match the cache keys."""
        from engine.live_breadth import canonical_symbol
        cpath = config.data_dir() / ns / "constituents.parquet"
        syms: list[str] = []
        if cpath.exists():
            try:
                import pandas as pd
                idx = pd.read_parquet(cpath).index
                syms = [canonical_symbol(s) for s in idx]
            except Exception as e:  # noqa: BLE001
                log.warning("poller: constituents read failed for %s (%s) — "
                            "falling back to close-cache columns", ns, e)
        if not syms:
            syms = [canonical_symbol(c) for c in close_cols]
        # de-dup, keep order
        seen: dict[str, None] = {}
        for s in syms:
            seen.setdefault(s, None)
        return list(seen)

    def _load_tier(self, ns: str) -> tuple[dict[str, dict], str | None]:
        """Compute the threshold dict for one tier from its close cache.

        Returns ({canonical_symbol: thresholds}, asof_date_str) or ({}, None) if
        the cache is absent/unreadable (fail-soft — that tier is simply empty).
        """
        import pandas as pd
        from engine.live_breadth import canonical_symbol

        p = self._cache_path(ns)
        if not p.exists():
            log.warning("poller: breadth cache absent for %s (%s) — tier skipped", ns, p)
            return {}, None
        try:
            closes = pd.read_parquet(p)
        except Exception as e:  # noqa: BLE001
            log.warning("poller: breadth cache unreadable for %s (%s) — tier skipped", ns, e)
            return {}, None
        if closes.empty:
            return {}, None
        closes = closes.sort_index()
        asof = pd.Timestamp(closes.index.max())
        block = config.load().get(ns, {}) or {}
        w50, w200 = block.get("ma_windows", [50, 200])
        nhw = int(block.get("nhnl_window", 252))

        # Canonicalise columns (they are already dash-form from the collector, but
        # fold defensively so the join keys match the snapshot canonicalisation).
        closes.columns = [canonical_symbol(c) for c in closes.columns]
        closes = closes.loc[:, ~closes.columns.duplicated()]

        last_row = closes.iloc[-1]
        ma50 = closes.rolling(int(w50), min_periods=int(w50)).mean().iloc[-1]
        ma200 = closes.rolling(int(w200), min_periods=int(w200)).mean().iloc[-1]
        hi52 = closes.rolling(nhw, min_periods=nhw).max().iloc[-1]
        lo52 = closes.rolling(nhw, min_periods=nhw).min().iloc[-1]

        members = self._members(ns, list(closes.columns))
        colset = set(closes.columns)

        def _num(series, sym):
            if series is None or sym not in colset:
                return None
            v = series.get(sym)
            if v is None or pd.isna(v):
                return None
            f = float(v)
            return f if f > 0 else None

        out: dict[str, dict] = {}
        for sym in members:
            if sym not in colset:
                continue
            # prev_close = the cache's NEWEST baked close (the last COMPLETE
            # session). For a live poll on day D, "prev" is the close of D-1 — which
            # is exactly the freshest row the nightly cache holds (baked overnight
            # after that session). Advancer = live last > this close. The MA50/MA200
            # and 52w-band levels are likewise the last-row (.iloc[-1]) baselines.
            prev_close = _num(last_row, sym)
            out[sym] = {
                "prev_close": prev_close,
                "ma50": _num(ma50, sym),
                "ma200": _num(ma200, sym),
                "hi52": _num(hi52, sym),
                "lo52": _num(lo52, sym),
            }
        return out, asof.strftime("%Y-%m-%d")

    def refresh(self) -> bool:
        """(Re)load any tier whose cache date has advanced. Returns True if
        anything (re)loaded. Safe to call every cycle — it re-reads the parquet
        header cheaply and only recomputes when the newest date changed."""
        changed = False
        import pandas as pd
        for key, ns, _univ, _label in self._tiers:
            p = self._cache_path(ns)
            new_asof = None
            if p.exists():
                try:
                    idx = pd.read_parquet(p, columns=[]).index
                    if len(idx):
                        new_asof = pd.Timestamp(idx.max()).strftime("%Y-%m-%d")
                except Exception:  # noqa: BLE001 — full load below handles errors
                    new_asof = None
            if key in self.by_tier and new_asof is not None and new_asof == self._asof.get(key):
                continue                      # unchanged — keep the cached thresholds
            th, asof = self._load_tier(ns)
            self.by_tier[key] = th
            self._asof[key] = asof or ""
            changed = True
            log.info("poller: thresholds loaded for %s (%d members, asof=%s)",
                     key, len(th), asof)
        return changed

    def all_symbols(self) -> set[str]:
        out: set[str] = set()
        for th in self.by_tier.values():
            out |= set(th.keys())
        return out


# ── Polygon full-market snapshot (ONE call per cycle) ──────────────────────────

def _snapshot_url() -> str:
    base = config.load()["polygon"]["base_url"].rstrip("/")
    return base + _POLY_SNAPSHOT


def fetch_full_market(offline: bool = False) -> tuple[dict, str, datetime | None]:
    """One Polygon full-market snapshot -> ({canonical_symbol: last_price},
    status, snapshot_ts). Reuses engine.live_quotes.parse_polygon_snapshot (the
    pure parser) for per-name price/ts extraction — never a per-symbol fan-out.

    status in {"ok","not_authorized","error","no_response","offline","no_key"}.
    snapshot_ts is the freshest per-name quote_ts (for honest staleness). The
    key handling mirrors live_quotes exactly (POLYGON_API_KEY / MASSIVE_API_KEY);
    the key never appears in logs or output. INERT — returns ({}, status, None)
    on any failure so the caller emits a fail-soft payload.
    """
    if offline:
        return {}, "offline", None
    import requests
    from engine import live_quotes

    key = config.secret("POLYGON_API_KEY") or config.secret("MASSIVE_API_KEY")
    if not key:
        log.warning("poller: no Polygon key (POLYGON_API_KEY/MASSIVE_API_KEY) — "
                    "emitting empty payload")
        return {}, "no_key", None
    try:
        # NO `tickers` param = the full-market form: one request, all US stocks.
        r = requests.get(_snapshot_url(), params={"apiKey": key}, timeout=30,
                         headers={"User-Agent": "Mozilla/5.0 (macro-dashboard live_breadth)"})
    except Exception as e:  # noqa: BLE001
        log.warning("poller: snapshot request failed: %s", e)
        return {}, "no_response", None
    if r.status_code != 200:
        log.warning("poller: snapshot HTTP %s", r.status_code)
        return {}, ("not_authorized" if r.status_code in (401, 403) else "error"), None
    try:
        payload = r.json()
    except Exception as e:  # noqa: BLE001
        log.warning("poller: snapshot JSON parse failed: %s", e)
        return {}, "error", None
    status = str(payload.get("status", "")).upper()
    if status == "NOT_AUTHORIZED":
        log.error("poller: snapshot NOT_AUTHORIZED — key wrong/unentitled")
        return {}, "not_authorized", None

    quotes = live_quotes.parse_polygon_snapshot(payload)
    last_by_symbol: dict[str, float] = {}
    latest_ts: datetime | None = None
    from engine.live_breadth import canonical_symbol
    for sym, q in quotes.items():
        price = q.get("price")
        if price is None:
            continue
        last_by_symbol[canonical_symbol(sym)] = float(price)
        ts_raw = q.get("quote_ts")
        if ts_raw:
            try:
                ts = datetime.fromisoformat(ts_raw)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts
            except Exception:  # noqa: BLE001
                pass
    return last_by_symbol, ("ok" if last_by_symbol else "no_response"), latest_ts


# ── one cycle ──────────────────────────────────────────────────────────────────

def build_breadth(
    store: ThresholdStore,
    last_by_symbol: dict[str, float],
    *,
    now: datetime | None = None,
    snapshot_ts: datetime | None = None,
    offline: bool = False,
    feed_status: str = "ok",
) -> dict:
    """Join the live snapshot against the baked thresholds -> the display payload.

    Pure over its inputs (no I/O) — the poller loads `store`/`last_by_symbol` and
    passes them in; tests call it directly with synthetic fixtures. Members with
    no live last are tallied into meta.missing per tier, never counted as
    unchanged (§4 gate 4).
    """
    from engine import live_breadth as lb

    now = now or datetime.now(timezone.utc)
    session = session_tag(now)
    delay = _delay_floor()
    # Honest staleness: vendor floor + how stale the snapshot itself is.
    if snapshot_ts is not None:
        extra = max(0.0, (now - snapshot_ts).total_seconds() / 60.0)
        delay = int(round(delay + extra))
    asof = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    if offline or not last_by_symbol:
        note = "offline" if offline else feed_status
        return lb.empty_payload(asof=asof, delay_min=delay, session=session, note=note)

    tiers: list[dict] = []
    missing: dict[str, int] = {}
    for key, _ns, univ, label in lb.BREADTH_TIERS:
        th = store.by_tier.get(key, {})
        if not th:
            continue
        present = {s: last_by_symbol[s] for s in th if s in last_by_symbol}
        miss = len(th) - len(present)
        if miss:
            missing[key] = miss
        tiers.append(lb.compute_tier(key, univ, {"en": label[0], "zh": label[1]},
                                     th, present))
    if not tiers:
        return lb.empty_payload(asof=asof, delay_min=delay, session=session,
                                note="no thresholds")
    return lb.build_payload(tiers, asof=asof, delay_min=delay, session=session,
                            missing=missing, n_snapshot=len(last_by_symbol))


# ── output + publish ───────────────────────────────────────────────────────────

def _out_path(site_dir: Path | None = None) -> Path:
    site = Path(site_dir) if site_dir is not None else config.site_dir()
    out_dir = site / "live"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "breadth.json"


def write_payload(payload: dict, site_dir: Path | None = None) -> Path:
    """Atomic write of the payload to site/live/breadth.json. allow_nan=False so a
    non-finite leak fails loudly rather than emitting invalid JSON (mirrors
    build_live_overlay)."""
    out = _out_path(site_dir)
    tmp = out.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(payload, indent=2, allow_nan=False))
    tmp.rename(out)
    return out


def publish(out_path: Path) -> bool:
    """Commit + push site/live/breadth.json to main via the SAME mechanism the
    intraday-fastpath uses for overlay.json (`git add -f site/live/... ` -> commit
    -> push; the file is gitignored, force-tracked). Host-side only; INERT — logs
    and returns False on any git failure so a push error never kills the loop.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        rel = str(out_path)
        # Stage ONLY breadth.json (force — site/live/ is gitignored), then commit.
        add = subprocess.run(["git", "add", "-f", rel],
                             capture_output=True, text=True)
        if add.returncode != 0:
            log.warning("poller: git add failed: %s", add.stderr.strip())
            return False
        # Nothing staged (unchanged payload) -> skip the commit cleanly.
        diff = subprocess.run(["git", "diff", "--cached", "--quiet", "--", rel])
        if diff.returncode == 0:
            log.info("poller: breadth.json unchanged — nothing to publish")
            return True
        commit = subprocess.run(
            ["git", "commit", "-m", f"live: breadth poll {ts}", "--", rel],
            capture_output=True, text=True)
        if commit.returncode != 0:
            log.warning("poller: git commit failed: %s", commit.stderr.strip())
            return False
        push = subprocess.run(["git", "push"], capture_output=True, text=True)
        if push.returncode != 0:
            log.warning("poller: git push failed: %s", push.stderr.strip())
            return False
        log.info("poller: published breadth.json (%s)", ts)
        return True
    except Exception as e:  # noqa: BLE001 — publish must never kill the loop
        log.warning("poller: publish failed: %s", e)
        return False


def _state_path() -> Path:
    return Path(tempfile.gettempdir()) / "live_breadth_poller_state.json"


# ── one full cycle (I/O) ───────────────────────────────────────────────────────

def run_cycle(store: ThresholdStore, *, offline: bool = False,
             do_publish: bool = False, site_dir: Path | None = None) -> dict:
    """Load-refresh thresholds, fetch one snapshot, join, write (+publish).
    Returns the emitted payload."""
    store.refresh()
    last_by_symbol, status, snap_ts = fetch_full_market(offline=offline)
    payload = build_breadth(store, last_by_symbol, snapshot_ts=snap_ts,
                            offline=offline, feed_status=status)
    out = write_payload(payload, site_dir=site_dir)
    n_tiers = len(payload.get("tiers", []))
    comp = payload.get("comp", {})
    log.info("poller: cycle session=%s status=%s tiers=%d adv=%s dec=%s "
             "pa50=%.1f snapshot_names=%s delay=%dm -> %s",
             payload.get("session"), status, n_tiers,
             comp.get("adv"), comp.get("dec"),
             comp.get("pa50") if comp.get("pa50") is not None else float("nan"),
             payload.get("meta", {}).get("snapshot_names"),
             payload.get("delay_min"), out)
    if do_publish:
        publish(out)
    return payload


# ── main loop ──────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live market-breadth poller")
    parser.add_argument("--once", action="store_true",
                        help="Single cycle then exit (always emits, honest session)")
    parser.add_argument("--offline", action="store_true",
                        help="Skip network; emit a fail-soft empty-tiers payload")
    parser.add_argument("--rth-only", action="store_true",
                        help="Exit cleanly outside 09:25-16:05 ET on weekdays "
                             "(use with launchd StartCalendarInterval)")
    parser.add_argument("--publish", action="store_true",
                        help="git add/commit/push site/live/breadth.json each cycle "
                             "(host-side; the intraday-fastpath commit mechanism)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _install_sigterm()

    # --rth-only self-exit: launchd fires at 09:25; the daemon self-exits at 16:05
    # and launchd re-fires next weekday. --once always runs regardless of window.
    if args.rth_only and not args.once and not within_rth():
        log.info("poller: --rth-only outside RTH window — exiting cleanly")
        return 0

    cfg = _cfg()
    cadence = _cadence(cfg)
    jitter = int(cfg.get("jitter_sec", DEFAULT_JITTER))

    store = ThresholdStore()
    store.refresh()
    if not store.all_symbols() and not args.offline:
        log.warning("poller: no thresholds loaded from any tier cache — cycles will "
                    "emit empty payloads until data/<ns>/_closes_cache.parquet exist")

    cycle_n = 0
    while True:
        loop_t0 = time.perf_counter()
        cycle_n += 1
        try:
            run_cycle(store, offline=args.offline, do_publish=args.publish)
        except Exception as e:  # noqa: BLE001 — a cycle error never kills the loop
            log.error("poller: cycle #%d error: %s", cycle_n, e, exc_info=True)
            if args.once:
                return 1

        if args.once:
            return 0
        if _SIGTERM["stop"]:
            log.info("poller: exiting on signal after cycle #%d", cycle_n)
            return 0
        if args.rth_only and not within_rth():
            log.info("poller: --rth-only outside RTH window — exiting cleanly")
            return 0

        elapsed = time.perf_counter() - loop_t0
        sleep_for = max(0.0, cadence - elapsed) + random.uniform(0, max(0, jitter))
        # Chunked sleep so SIGTERM is honored within ~1s instead of a full cadence.
        end = time.perf_counter() + sleep_for
        while time.perf_counter() < end:
            if _SIGTERM["stop"]:
                break
            time.sleep(min(1.0, end - time.perf_counter()))


if __name__ == "__main__":
    sys.exit(main())
