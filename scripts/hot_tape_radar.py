"""scripts/hot_tape_radar.py — the */5 intraday Hot Tape radar.

Implements research/MARKETING_HOT_TAPE_MASTERPLAN.md §3.2/§3.4: load the live
tape + the nightly context pack, run the detectors
(:func:`engine.marketing.hot_tape.detect_events`), compose wire copy
(:func:`engine.marketing.hot_tape_wire.compose_wire`), draw the house tape card,
and book the result as an `immediate` outbox item so
`marketing-publish.yml post_now_item=<ids>` sends it within minutes.

    python -m scripts.hot_tape_radar [--dry-run] [--demo]

TWO THINGS THE COPY PATH DOES BEYOND THE TEMPLATE (masterplan §10 E1):

* **P2 phrasing.** Every composed post goes through
  :func:`engine.marketing.hot_tape_llm.phrase_or_fallback`, which phrases the
  SAME FactPacket in wire register behind the numeric-consistency gate and
  hands back the deterministic template on any failure. The template is the
  floor, never a hope: `phrase` below can only return postable text.
* **Two-step publish.** An alert at severity >= `two_step.min_severity` earns
  ONE follow-up "context brief" (mechanism + affected names + what we are
  watching), filed on a LATER tick by :func:`pending_briefs`. Codex case study
  2026-07-28: on the same story and account the flash won ~8% more views, the
  contextual version won ~9% better interaction efficiency and a ~49% higher
  repost/view ratio. The alert wins speed; the brief wins reposts.

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
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

_CODE_ROOT = str(Path(__file__).resolve().parent.parent)
if _CODE_ROOT not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, _CODE_ROOT)

from engine.marketing import hot_tape as HT  # noqa: E402
from engine.marketing import hot_tape_llm as HL  # noqa: E402
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
    "earnings_reaction",
})

#: Triggers whose post is about a GROUP of names, and where each one keeps its
#: [[symbol, pct], ...] constituents. These get the watchlist card, not a price
#: chart — see :func:`resolve_group_card` for why they get one at all.
_GROUP_ROWS_FACT: dict[str, str] = {
    "sector_rout": "leaders",
    "sector_rip": "leaders",
    "contrarian_breadth": "green",
}
GROUP_TRIGGERS: frozenset[str] = frozenset(_GROUP_ROWS_FACT)

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


def _slug(raw: Any) -> str:
    """A filename-safe token for a group label ("REIT - Residential" -> "reit-residential").

    Used in a chart_id, which becomes a path and an R2 key, so it must never
    emit a separator or an empty string.
    """
    out = "".join(ch if ch.isalnum() else "-" for ch in str(raw or "").lower())
    return "-".join(p for p in out.split("-") if p) or "market"


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

def window_end_epoch(root: Path, *, now: datetime | None = None,
                     demo: bool = False) -> int:
    """Epoch seconds at which today's ET window (end + grace) closes.

    The session-long pass loop stops here. Computed from the SAME config
    ``HT.in_window`` reads and on the SAME Eastern clock, because a second
    implementation of the DST reasoning in bash is how the shipped crons ended up
    describing a UTC window in the first place.

    Demo returns a far-future stamp: demo exists to run on a closed tape, and a
    demo loop that stopped at the real window end could not demonstrate anything.
    Never raises — on any failure it returns `now`, which stops the loop after one
    pass rather than looping until the job timeout.
    """
    t = now or datetime.now(timezone.utc)
    if demo:
        return int(t.timestamp()) + 86_400
    try:
        cfg = HT.load_config(root)
        end = HT._parse_hhmm(_cfg(cfg, "window_et.end", "16:05"), time(16, 5))
        try:
            grace = float(_cfg(cfg, "window_grace_min", HT.DEFAULTS["window_grace_min"]))
        except (TypeError, ValueError):
            grace = float(HT.DEFAULTS["window_grace_min"])
        et_now = HT._et_clock(t)
        close = et_now.replace(hour=end.hour, minute=end.minute, second=0,
                               microsecond=0) + timedelta(minutes=max(0.0, grace))
        return int(close.timestamp())
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: window_end_epoch failed (%s) — one pass only", exc)
        return int(t.timestamp())


def freshness_cfg(cfg: dict | None, *, demo: bool) -> dict:
    """The config the freshness gate ACTUALLY applies.

    Demo relaxes ONLY the ceiling, and only through the config's own demo block —
    never by skipping the check. Extracted so the GATE and the LOG cannot
    disagree about it. They did: the stand-down message resolved the ceiling from
    the demo-aware config while the summary line resolved it from the raw one, so
    a demo pass printed ``ceiling=27m`` while actually judging against 100015m
    (observed in run 30529411662). A log line that misreports the threshold it
    applied is worse than no log line — this whole defect took a day to find
    because the numbers on screen had to be correlated by hand against another
    lane's push times.
    """
    if not demo:
        return cfg if isinstance(cfg, dict) else {}
    out = dict(cfg or {})
    out["max_quote_age_min"] = _cfg(cfg, "demo.max_quote_age_min", 100000)
    return out


@lru_cache(maxsize=4)
def remote_quote_urls(root: Path) -> tuple[str, ...]:
    """The VPS live plane URLs for the merge, from ``config.yml`` ``live:``.

    CACHED PER ROOT because this loop fires ~81 times a session and the answer is a
    URL — re-parsing the 4k-line config.yml on every pass to re-read one string is
    the cost ``llm_config`` documents right above. A session that wanted a new URL
    would be a new process anyway (the poller re-execs per run).

    Resolution and the operator's off switch both live in
    :func:`engine.marketing.live_verify.remote_quote_urls`; this only supplies the
    config.

    NO CONFIG MEANS NO REMOTE SOURCE — not "fall back to the estate default". A root
    without a readable config.yml is a test harness or a partial checkout, not
    production, and a resolver that reached for a hardcoded URL there would put a
    live network call inside every unit test that builds a tmp_path root: a suite
    that fails when a web host is down, and a source of real fetches on a machine
    that never asked for one. The degraded behaviour is exactly the repo-local
    merge, which is what this lane had before the remote source existed.
    """
    try:
        import yaml  # noqa: PLC0415

        path = root / "config.yml"
        if not path.exists():
            return ()
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        return LV.remote_quote_urls(loaded if isinstance(loaded, dict) else {})
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: live.public_quotes_url unreadable (%s) - "
                    "repo-local quote sources only this pass", exc)
        return ()


def load_quotes(root: Path, *, now: datetime, cfg: dict, demo: bool) -> tuple[dict, bool, float | None]:
    """(live view, fresh?, freshest age in minutes). Never raises.

    ``quotes_fresh`` is a gate on the FRESHEST quote — one stale symbol must not
    stand a 2k-symbol merge down. The other half of that trade is enforced here
    (reviewer m4): individual quotes older than the same ceiling are DROPPED
    from the detection input, because a merge that passes on its freshest entry
    still carries entries hours old, and a detector cannot tell them apart. A
    quote with no ``ts_ms`` of its own (the heatmap's pct-only tiles) is judged
    by the artifact's asof, so a fresh artifact keeps them all.

    BOTH halves use the SAME ceiling, and it is the delay-aware one
    (``HT.effective_max_quote_age_min``). They diverged before: the gate passed on
    a real-time BTC/FX tick while this drop measured the equity book against a
    bare 12 minutes that a ~15-min-delayed feed can never satisfy, so a pass that
    cleared the gate went on to discard every equity it existed to detect on. One
    definition, one ceiling — and a drop that empties the book stands the pass
    down out loud rather than detecting on what is left.
    """
    live = LV.load_live_quotes(root, remote_urls=remote_quote_urls(root))
    gate_cfg = freshness_cfg(cfg, demo=demo)
    max_age = HT.effective_max_quote_age_min(live, gate_cfg)
    fresh, age = HT.quotes_fresh(live, now, gate_cfg)
    if fresh:
        before = len((live.get("quotes") if isinstance(live.get("quotes"), dict) else {}) or {})
        live = _drop_stale_quotes(live, now=now, max_age_min=max_age)
        after = len((live.get("quotes") if isinstance(live.get("quotes"), dict) else {}) or {})
        if before and after < before * MIN_LIVE_BOOK_SHARE:
            # THE HOLE THIS CLOSES. quotes_fresh gates on min(age) across a
            # MIXED-LATENCY universe, and the merge carries real-time crypto/FX
            # alongside ~15-min-delayed equities. A single live BTC tick can
            # therefore certify a merge whose entire equity book is 40 minutes
            # behind — which is what 2026-07-29T18:08Z actually was: freshest
            # 21.92m (an FX print) over equities stamped ~17:31 by a push at
            # 17:46. Passing that gate and then dropping every name the detectors
            # run on is not a filter, it is a silent outage.
            print(f"::warning title=hot-tape::live book collapsed under the "
                  f"{max_age:g}m ceiling ({after}/{before} quotes survived, floor "
                  f"{MIN_LIVE_BOOK_SHARE:.0%}) - the freshest quote is real-time but "
                  "the tape behind it is not. No events this pass; this is a "
                  "WRITER-LANE fault, not a threshold to widen", flush=True)
            fresh = False
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


# ─────────────────────────────────────────────────────────────────────────────
# Self-refresh of the live tape
#
# WHY THE RADAR FETCHES ITS OWN QUOTES. Until 2026-07-30 this lane read only
# artifacts written by OTHER lanes: the `live-data` branch snapshot
# (live-quotes.yml) plus site/live + the heatmap. That made a detector's freshness
# depend on a cadence it does not own, and on 2026-07-29 the dependency went dark:
#
#   * live-quotes.yml's 5-minute tick has been disabled since 2026-07-27T22:50Z
#     (VPS_LIVE_PRIMARY=true gates the job off), leaving only a */15 tape-gate
#     tick that was sized for the publisher's 45-minute gate, not a 12-minute one.
#   * GitHub starves this repo's scheduled workflows: 104 scheduled runs delivered
#     across the WHOLE repo in the 8h RTH window on 2026-07-29 — live-quotes 11 of
#     128 ticks (8.6%), this radar 6 of 92 (6.5%). The writer fired ~1.4x/hour.
#   * two of those eleven delivered live-quotes ticks then died at 8m06s inside
#     `git fetch` — a full-tree checkout against an 8-minute job timeout.
#
# Net: the merged view the radar gated on was 20-60 minutes old all day and every
# sampled pass stood down. Measured directly — age 49.72m at 15:48Z against a last
# push of 14:58:23Z; age 21.92m at 18:08Z against 17:46:53Z.
#
# A radar whose only input is another lane's commit cadence is not a radar. So a
# pass fetches the tape itself when the shared view is behind, and writes it to
# the path the merge already reads — no new precedence, no new artifact, and
# live-quotes.yml stays exactly as valuable as it was (still the browser's
# fallback, the publisher's tape gate, and this lane's cheap common case).
# ─────────────────────────────────────────────────────────────────────────────

#: Where live_verify's merge reads the full-universe snapshot (its _SNAPSHOT_REL).
SNAPSHOT_REL = "data/marketing/live_quotes_snapshot.json"

#: Share of the merged book that must SURVIVE the per-quote staleness drop for a
#: pass to proceed. Guards the mixed-latency hole in a ``min()``-based freshness
#: gate — see the comment in :func:`load_quotes`.
MIN_LIVE_BOOK_SHARE = 0.5

#: A self-fetch that resolves less than this share of its universe is DISCARDED
#: rather than written. Overwriting a complete-but-stale snapshot with a mostly
#: empty fresh one trades a fixable staleness problem for an unfixable coverage
#: one: the names that dropped out lose their price entirely and fall back to the
#: heatmap's pct-only tiles, which the price-gated detectors cannot use at all.
MIN_SELF_FETCH_COVERAGE = 0.5

#: Hard cap on the self-fetch universe. At the measured ~37 symbols/s Yahoo rate
#: 900 names is ~24s inside a 12-minute job budget, and the radar's actionable set
#: (503 heatmap tiles + pack names to adv_rank 300, heavily overlapping) lands
#: well under it. The cap exists so a pack growth spurt cannot quietly turn a
#: 25-second step into a timeout.
MAX_SELF_FETCH_SYMBOLS = 900


def radar_universe(
    pack: dict | None,
    heatmap: dict | None,
    *,
    signals: list[dict] | None = None,
    earnings: dict | None = None,
    cfg: dict | None = None,
) -> list[str]:
    """Exactly the symbols this pass's detectors can act on. Never raises.

    Ordered by priority so the cap truncates the least useful tail first: the
    heatmap tiles (every group detector reads them), then the liquid pack names
    inside ``detectors.mover.adv_rank_max``, then the index proxy the contrarian
    detector needs, then today's armed plan levels and earnings reporters.
    """
    out: list[str] = []
    seen: set[str] = set()

    def _add(raw: Any) -> None:
        sym = str(raw or "").strip().upper().lstrip("$")
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)

    # Each leg is guarded SEPARATELY. One malformed input must not cost the
    # others: a junk pack that took the whole assembly down with it would also
    # drop the contrarian detector's index proxy, so a bad store would silently
    # narrow the radar instead of just narrowing itself.
    def _leg(label: str, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            log.warning("hot_tape_radar: universe leg %s degraded: %s", label, exc)

    def _tiles() -> None:
        for tile in (heatmap or {}).get("tiles") or []:
            if isinstance(tile, dict):
                _add(tile.get("t") or tile.get("ticker"))

    def _pack_names() -> None:
        try:
            rank_max = float(_cfg(cfg, "detectors.mover.adv_rank_max", 300))
        except (TypeError, ValueError):
            rank_max = 300.0
        for sym, rec in ((pack or {}).get("tickers") or {}).items():
            if not isinstance(rec, dict):
                continue
            rank = rec.get("adv_rank")
            try:
                if rank is not None and float(rank) <= rank_max:
                    _add(sym)
            except (TypeError, ValueError):
                continue

    def _index() -> None:
        _add(_cfg(cfg, "detectors.contrarian.index_ticker", "SPY"))

    def _signal_names() -> None:
        for sig in signals or []:
            if isinstance(sig, dict):
                src = sig.get("source") if isinstance(sig.get("source"), dict) else {}
                _add(src.get("ticker") or sig.get("ticker"))

    def _earnings_names() -> None:
        for sym in ((earnings or {}).get("tickers") or {}):
            _add(sym)

    _leg("heatmap", _tiles)
    _leg("pack", _pack_names)
    _leg("index", _index)
    _leg("signals", _signal_names)
    _leg("earnings", _earnings_names)

    if len(out) > MAX_SELF_FETCH_SYMBOLS:
        print(f"::warning title=hot-tape::self-fetch universe {len(out)} exceeds "
              f"{MAX_SELF_FETCH_SYMBOLS} - truncating (heatmap tiles are first, "
              "never dropped)", flush=True)
        out = out[:MAX_SELF_FETCH_SYMBOLS]
    return out


def refresh_live_snapshot(
    root: Path,
    *,
    universe: list[str],
    builder: Callable[[list[str]], dict] | None = None,
) -> bool:
    """Fetch `universe` live and write it where the merge reads. True when written.

    Fail-soft in every direction: a refused fetch, a partial fetch below
    ``MIN_SELF_FETCH_COVERAGE``, an unwritable path or any exception all leave the
    committed snapshot untouched and return False, so the worst case is exactly
    the behaviour that existed before this function — the freshness gate then
    stands the pass down on its own, and says so.
    """
    if not universe:
        return False
    if os.environ.get("HOT_TAPE_NO_LIVE_FETCH", "").strip() == "1":
        # An explicit operator/CI opt-out. Printed, never silent: a lane that
        # stopped fetching without saying so is the 2026-07-26 mute shape.
        print("::notice title=hot-tape::live self-fetch disabled "
              "(HOT_TAPE_NO_LIVE_FETCH=1) - using the committed snapshot only",
              flush=True)
        return False
    try:
        if builder is None:
            from scripts.build_live_quotes import build as _build  # noqa: PLC0415

            def builder(syms: list[str]) -> dict:  # noqa: F811
                # symbols= takes the EXACT universe (bypassing CORE + the site
                # scrape + conviction), the same door the btc-live lane uses, so
                # this needs no built site tree in the sparse checkout.
                return _build(root / "site", symbols=syms)

        snap = builder(list(universe))
        quotes = (snap or {}).get("quotes") if isinstance(snap, dict) else None
        if not isinstance(quotes, dict) or not quotes:
            print("::warning title=hot-tape::live self-fetch resolved no quotes - "
                  "keeping the committed snapshot", flush=True)
            return False

        coverage = len(quotes) / max(1, len(universe))
        if coverage < MIN_SELF_FETCH_COVERAGE:
            print(f"::warning title=hot-tape::live self-fetch covered "
                  f"{len(quotes)}/{len(universe)} ({coverage:.0%} < "
                  f"{MIN_SELF_FETCH_COVERAGE:.0%}) - discarding it and keeping the "
                  "committed snapshot", flush=True)
            return False

        dest = root / SNAPSHOT_REL
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_text(json.dumps(snap), encoding="utf-8")
        tmp.replace(dest)
        print(f"hot-tape self-fetch wrote {len(quotes)}/{len(universe)} quotes "
              f"asof={snap.get('asof')} "
              f"delayed_min={((snap.get('meta') or {}).get('delayed_min'))}", flush=True)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=hot-tape::live self-fetch failed ({exc}) - falling "
              "back to the committed snapshot", flush=True)
        return False


def _cell(value: Any) -> Any:
    """One parquet cell, with the vendor's null spellings flattened to None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none", "null"}:
        return None
    return value


def load_earnings(root: Path) -> dict:
    """The earnings calendar view for the reaction detector. Never raises.

    {"asof": <max as_of>, "tickers": {SYM: {next_date, next_time, eps_forecast,
    surprises, as_of}}}, read from ``data/earnings/earnings.parquet``.

    PYARROW, NEVER PANDAS. The whole intraday lane installs pyyaml+requests+
    pyarrow (gate 0.6) and pays that install 81 times a day; pandas is ~40s of
    it. The import is lazy and its absence is NOT an error — the detector simply
    sees an empty calendar and stands down, which is the same "no post" the rest
    of this file degrades to.

    ``surprises_json`` is parsed HERE so the detector stays a pure function of
    plain Python: the engine reads the store, the detector reads the engine.
    """
    out: dict[str, Any] = {"asof": None, "tickers": {}}
    path = root / HT.EARNINGS_REL
    if not path.exists():
        return out
    try:
        import pyarrow.parquet as pq  # noqa: PLC0415
    except ImportError:
        log.warning("hot_tape_radar: pyarrow unavailable - earnings detector stands down")
        return out
    try:
        table = pq.read_table(path)
        columns = set(table.column_names)
        if not {"ticker", "next_date"} <= columns:
            log.warning("hot_tape_radar: earnings.parquet lacks ticker/next_date (%s)",
                        sorted(columns))
            return out
        data = table.to_pydict()
        n = len(data.get("ticker") or [])
        blank: list[Any] = [None] * n
        rows: dict[str, dict] = {}
        asof_max: str | None = None
        for i in range(n):
            sym = str(_cell(data["ticker"][i]) or "").strip().upper()
            if not sym:
                continue
            as_of = _cell(data.get("as_of", blank)[i])
            as_of = str(as_of) if as_of is not None else None
            if as_of and (asof_max is None or as_of > asof_max):
                asof_max = as_of
            raw = _cell(data.get("surprises_json", blank)[i])
            surprises: list = []
            if raw is not None:
                try:
                    parsed = json.loads(str(raw))
                    surprises = parsed if isinstance(parsed, list) else []
                except (TypeError, ValueError):
                    surprises = []
            next_date = _cell(data["next_date"][i])
            next_time = _cell(data.get("next_time", blank)[i])
            rows[sym] = {
                "next_date": str(next_date)[:10] if next_date is not None else None,
                "next_time": str(next_time) if next_time is not None else None,
                "eps_forecast": _f(_cell(data.get("eps_forecast", blank)[i])),
                "surprises": surprises,
                "as_of": as_of,
            }
        out["tickers"] = rows
        out["asof"] = asof_max
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: earnings read failed (%s)", exc)
        return {"asof": None, "tickers": {}}
    return out


def llm_config(root: Path) -> dict:
    """config.yml's ``hot_tape.llm`` block, wrapped for hot_tape_llm.

    RESOLVED ONCE PER PASS and threaded explicitly, for two reasons.

    First, cost: ``hot_tape_llm`` falls back to ``lib.config.load()``, which
    re-parses the 4k-line config.yml on every call, and this loop fires 81 times
    a day.

    Second, and load-bearing: it must NOT be ``config/hot_tape.yml``. That file
    is the RADAR's tuning surface and its top-level ``enabled: true`` is the
    radar's master switch — but ``hot_tape_llm._llm_cfg`` accepts a bare block
    and would read that key as the LLM desk's own arming flag. Handing the radar
    config to the phrasing layer would therefore arm the model lane the moment
    the radar was on, with none of the knobs the operator wrote. The wrapper
    here ({"llm": ...}) resolves unambiguously to the config.yml block, and an
    absent/unreadable block resolves to {} — i.e. disarmed.
    """
    block: dict = {}
    try:
        import yaml  # noqa: PLC0415

        path = root / "config.yml"
        if path.exists():
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            hot_tape = loaded.get("hot_tape") if isinstance(loaded, dict) else None
            if isinstance(hot_tape, dict) and isinstance(hot_tape.get("llm"), dict):
                block = dict(hot_tape["llm"])
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: hot_tape.llm config unreadable (%s) - "
                    "deterministic templates only", exc)
    return {"llm": block}


def phrase(packet: HT.FactPacket, fallback_text: str, *, llm_cfg: dict) -> dict:
    """Phrase one packet through the P2 LLM wire desk. ALWAYS returns text.

    ``hot_tape_llm.phrase_or_fallback`` is the contract: it never raises and
    always hands back postable copy — the model's when it clears every gate
    (numbers trace to the FactPacket, no calls, no hedging, cashtag policy),
    the deterministic template otherwise. The try/except here is belt only.

    ONE EXTRA GATE ON THE MODEL BRANCH: the LLM module's call-language list is
    narrower than this desk's own :data:`hot_tape_wire.WIRE_BANNED` — it has no
    "accumulate", "load up", "calls", "puts" or "bid" — and gate 0.4 is a house
    law, not a per-module preference. Model copy that trips the wider list falls
    back to the template, so the deterministic floor still holds.
    """
    result: dict = {}
    try:
        result = HL.phrase_or_fallback(
            HW.llm_packet(packet), str(packet.trigger), fallback_text,
            link=None, links_allowed=False, cfg=llm_cfg,
        ) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: phrasing failed for %s (%s) - template posts",
                    packet.key, exc)
        result = {}

    text = str(result.get("text") or "").strip() or fallback_text
    mode = str(result.get("mode") or "fallback_provider")
    violations = list(result.get("violations") or [])
    if mode == "llm":
        hits = HW.ban_hits(text)
        if hits:
            print("::warning title=hot-tape-llm-banned::model copy for "
                  f"{packet.key} carried house-banned language ({','.join(hits)}) "
                  "- the deterministic template posted instead", flush=True)
            text, mode = fallback_text, "fallback_validation"
            violations = violations + [f"wire_banned:'{w}'" for w in hits]
    return {
        "text": text,
        "mode": mode,
        "provider": result.get("provider"),
        "latency_ms": result.get("latency_ms"),
        "violations": violations,
    }


#: Share of calendar rows that must be inside the freshness ceiling before the
#: reaction detector counts as healthy. The FILE's max as_of is not the answer:
#: on 2026-07-29 the shipped parquet carried a 2026-07-28 stamp on 3 rows and a
#: 2026-06-19 stamp on the other 1,361, so a whole-file check called a 0.2%-fresh
#: calendar healthy while the detector could see almost none of it.
MIN_FRESH_EARNINGS_SHARE = 0.5


def _warn_stale_earnings(earnings: dict, *, now: datetime, cfg: dict) -> None:
    """One line-start warning when the calendar is too old to fire on.

    DEGRADED MUST NOT SHIP CONFIDENT. The reaction detector refuses every row
    whose own ``as_of`` is past ``detectors.earnings.max_calendar_age_days``,
    which is correct — but a silent refusal reads exactly like "no company
    reported today", and the lane would look healthy while being structurally
    dark. Row-level, not file-level, for the reason on the constant above.
    """
    try:
        rows = earnings.get("tickers") or {}
        if not rows:
            return
        today = now.astimezone(timezone.utc).date()
        max_age = int(_cfg(cfg, "detectors.earnings.max_calendar_age_days", 21))
        view_asof = earnings.get("asof")
        fresh = 0
        undated = 0
        for row in rows.values():
            asof = _iso_date((row or {}).get("as_of") or view_asof)
            if asof is None:
                undated += 1
            elif (today - asof).days <= max_age:
                fresh += 1
        total = len(rows)
        if fresh >= max(1, int(total * MIN_FRESH_EARNINGS_SHARE)):
            return
        newest = _iso_date(view_asof)
        print(f"::warning title=hot-tape-earnings::only {fresh}/{total} earnings "
              f"calendar rows are inside the {max_age}d freshness ceiling "
              f"({undated} carry no as_of, newest stamp "
              f"{newest.isoformat() if newest else 'none'}) - the reaction "
              "detector can only see that slice until "
              "data/earnings/earnings.parquet refreshes", flush=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: earnings staleness check skipped: %s", exc)


def needs_chart(packet: HT.FactPacket) -> bool:
    """Does the operator's every-ticker-post-carries-a-chart law apply here?

    Trigger family for an alert, and the SUBJECT for a context brief: a brief
    that names one ticker is a ticker post no matter which trigger built it.

    A GROUP post owes a picture too (2026-07-31). It used to answer False here
    — "a breadth post ships text-only in P1 exactly as its alert did" — which
    was true about the price chart and wrong about the law. The copy names its
    movers, so the publisher's chart law quarantines it: 19 group posts queued
    on 2026-07-30 and all 19 died there. The picture is the watchlist card, not
    a chart, and it is owed only when the packet actually carries the names to
    put on it.
    """
    if packet.trigger in SINGLE_NAME_TRIGGERS:
        return True
    if packet.trigger in GROUP_TRIGGERS:
        return bool(group_rows(packet))
    return packet.trigger == HT.BRIEF_TRIGGER and bool(packet.ticker)


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


def group_rows(packet: HT.FactPacket) -> list[dict[str, Any]]:
    """The names a group post is about, as watchlist-card rows.

    Both group families already carry their constituents — `sector_rout` /
    `sector_rip` in facts["leaders"], `contrarian_breadth` in facts["green"] —
    as [[symbol, pct], ...] in the order the copy names them. That is exactly
    render_watchlist_card's row shape minus the price, which it degrades
    cleanly on (no pill rather than a placeholder dash).

    Returns [] when the packet is not a group post or its constituents are
    missing/unusable, which the caller reads as "no card" and drops the post.
    """
    fact_key = _GROUP_ROWS_FACT.get(str(packet.trigger or ""))
    if not fact_key:
        return []
    rows: list[dict[str, Any]] = []
    for entry in (packet.facts.get(fact_key) or []):
        try:
            sym, pct = entry[0], entry[1]
        except (TypeError, IndexError, KeyError):
            continue
        ticker = str(sym or "").strip().upper().lstrip("$")
        pct_f = _f(pct)
        if not ticker or pct_f is None:
            continue
        rows.append({"ticker": ticker, "pct_change": float(pct_f), "price": None})
    return rows


def _group_card_title(packet: HT.FactPacket) -> str:
    """The card's hero line. Plain words, and it says nothing the post does not."""
    label = str(packet.sector or "").strip()
    if str(packet.trigger) == "contrarian_breadth":
        return "Defensive names green"
    verb = "selling off" if str(packet.direction) == "down" else "bid up"
    return f"{label} {verb}".strip() if label else f"A group {verb}"


def _group_card_subtitle(packet: HT.FactPacket) -> str | None:
    """The panel's own caption: the breadth fact, straight out of the packet.

    Deliberately NOT a second stance. The post text carries the read; a card
    that argues alongside it can contradict it, and every number here is one
    the packet already authorised (gate 0.3).
    """
    f = packet.facts
    n_members = f.get("n_members")
    agree = f.get("n_down") if str(packet.direction) == "down" else f.get("n_up")
    median = _f(f.get("median_pct"))
    if agree is None or n_members is None or median is None:
        n_green = f.get("n_green")
        return f"{n_green} names green" if n_green else None
    way = "lower" if str(packet.direction) == "down" else "higher"
    return f"{agree} of {n_members} {way}, median {median:+.1f}%"


def resolve_group_card(
    packet: HT.FactPacket,
    *,
    root: Path,
    marketing_cfg: dict,
    as_of: str,
    now: datetime,
) -> dict[str, Any]:
    """The picture for a post about a GROUP of names. Same contract as
    :func:`resolve_chart` — {"media", "published", "reason"}.

    WHY THIS EXISTS. `needs_chart` used to answer False for the whole group
    family, on the reasoning that a breadth read is not a post about one name
    and has no price chart to draw. True, and it made the family
    unpublishable: the copy names its movers ("Best: $SNDK +21.1%, $WDC
    +15.2%"), and the publisher's chart law — a post that NAMES TICKERS ships
    a picture, whatever kind it claims to be (operator 2026-07-30) —
    quarantines every one of them. Two rules, each right on its own, that
    between them deleted an entire post family: 19 queued on 2026-07-30, 19
    quarantined.

    A price chart was never the answer for a group. render_watchlist_card is —
    the third member of the same card family, written for exactly this ("a
    plain multi-ticker text post ... as a screenshot of a premium SaaS
    watchlist panel").

    The rows come straight from the packet, so nothing here can invent a name
    or a number. The card does read bars, but only for the per-row sparkline
    (load_closes n=10 under logo_root), and that read is silent on a miss — a
    name with no local history draws no sparkline rather than a made-up one.
    """
    out: dict[str, Any] = {"media": None, "published": {}, "reason": "no-rows"}
    rows = group_rows(packet)
    if not rows:
        return out
    try:
        from engine.marketing.chart_render import (  # noqa: PLC0415
            chart_cta_enabled,
            render_watchlist_card,
        )
        from engine.marketing.media_publish import publish_card  # noqa: PLC0415

        svg = render_watchlist_card(
            _group_card_title(packet),
            rows,
            as_of=as_of,
            subtitle=_group_card_subtitle(packet),
            logo_root=root,
            cta=chart_cta_enabled(marketing_cfg),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: group card render failed for %s: %s",
                    packet.key, exc)
        out["reason"] = "render-failed"
        return out

    # Keyed on the packet, not a ticker: this card is about the group.
    chart_id = f"hottape-{packet.trigger}-{_slug(packet.sector or 'market')}-{now.strftime('%H%M')}Z"
    try:
        published = publish_card(svg, chart_id=chart_id, as_of=as_of, root=root)
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: publish_card failed for %s: %s", chart_id, exc)
        published = {}
    out["published"] = dict(published or {})
    out["published"]["chart_id"] = chart_id

    url = str((published or {}).get("media_url") or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        out["reason"] = "no-media-url"
        return out

    entry: dict[str, Any] = {
        "kind": "chart_svg",
        "path": (published.get("svg_path")
                 or f"data/marketing/outbox/media/{as_of}/{chart_id}.svg"),
        "chart_id": chart_id,
        "tickers": [r["ticker"] for r in rows],
        "media_url": url,
    }
    if published.get("media_png_path"):
        entry["media_png_path"] = published["media_png_path"]
    out["media"] = entry
    out["reason"] = "ok"
    return out


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


def book_packet(
    packet: HT.FactPacket,
    *,
    account: str,
    root: Path,
    cfg: dict,
    marketing_cfg: dict,
    llm_cfg: dict,
    now: datetime,
    as_of: str,
    dry_run: bool,
    fetcher: Callable[[str, Path], bool] | None = None,
    pack: dict | None = None,
) -> dict:
    """Lock -> compose -> phrase -> draw -> enqueue ONE packet. Never raises.

    Returns {"status", "item_id", "text"}. ``status`` is "queued", "would_book"
    (dry run), "lock_skip", "no_device", "drop:<reason>", or an outbox enqueue
    code. The CALLER owns the fired ledger, the caps and the dispatch list, so
    an alert and a two-step brief can share every step of this without sharing
    their budgets.
    """
    key = story_key_for(packet)
    verdict = story_lock_check(account, key, root=root, now=now, cfg=marketing_cfg)
    if verdict is not None and not bool(verdict):
        print(f"hot-tape LOCK-SKIP {packet.key} owner={getattr(verdict, 'owner', '?')}",
              flush=True)
        return {"status": "lock_skip", "item_id": None, "text": ""}

    copy = HW.compose_wire(packet, cfg=cfg)
    if not copy or not str(copy.get("text") or "").strip():
        print(f"hot-tape REFUSE {packet.key} no-device", flush=True)
        return {"status": "no_device", "item_id": None, "text": ""}
    template_text = str(copy["text"]).strip()

    # P2: the model phrases the SAME facts the template just rendered, and the
    # template is the floor it falls back to (masterplan §3.3 / §10 E1).
    phrased = phrase(packet, template_text, llm_cfg=llm_cfg)
    text = phrased["text"]

    # PREFLIGHT BEFORE THE PICTURE (2026-07-30).
    #
    # resolve_chart() below is a Chrome raster AND an R2 upload. It used to run
    # before enqueue, so every duplicate, near-duplicate and cap rejection paid
    # full price for an image nobody would ever see — on a nightly render budget
    # that is law (~67 min, 4-core-bound). Nothing enqueue rejects on depends on
    # the media: the id hashes (account, kind, text, as_of), and the dedupe and
    # cap checks read text and account. The deciding facts are all in hand HERE.
    #
    # This is an optimisation, never a gate. preflight_enqueue is fail-open and
    # reads without the outbox lock, so it can only ever skip work it was going
    # to lose anyway; enqueue below still runs every check authoritatively. The
    # caller records these codes in the fired ledger (_TERMINAL_ENQUEUE_CODES),
    # so a refusal here suppresses the re-detect on the next five-minute pass
    # exactly as a post-render refusal did.
    if not dry_run:
        _pre = OB.preflight_enqueue(
            account=account, kind="breaking", text=text, as_of=as_of,
            root=root, cfg=marketing_cfg,
        )
        if _pre != "ok":
            print(f"hot-tape REFUSE {packet.key} {_pre} (preflight, no render)",
                  flush=True)
            return {"status": _pre, "item_id": None, "text": text}

    media: list[dict] = []
    published: dict[str, Any] = {}
    chart_state = "none"
    if needs_chart(packet):
        is_group = packet.trigger in GROUP_TRIGGERS
        if dry_run:
            # Simulation: local inputs only, no fetch, no render, no upload.
            if is_group:
                # A group card needs no bars — its rows ARE the packet — so the
                # only way it can fail is having no names, which needs_chart
                # already refused above.
                chart_state = "ok(simulated,group)"
            else:
                _, reason = load_bars(str(packet.ticker or ""), root, now=now,
                                      fetcher=None)
                if reason != "ok":
                    print(f"hot-tape DROP {packet.key} {reason}", flush=True)
                    return {"status": f"drop:{reason}", "item_id": None, "text": text}
                chart_state = "ok(simulated)"
        elif is_group:
            card = resolve_group_card(packet, root=root,
                                      marketing_cfg=marketing_cfg,
                                      as_of=as_of, now=now)
            if card.get("media") is None:
                print(f"hot-tape DROP {packet.key} {card.get('reason')}", flush=True)
                return {"status": f"drop:{card.get('reason')}", "item_id": None,
                        "text": text}
            media = [card["media"]]
            published = card.get("published") or {}
            chart_state = "ok(group)"
        else:
            card = resolve_chart(packet, root=root, marketing_cfg=marketing_cfg,
                                 as_of=as_of, now=now, fetcher=fetcher,
                                 suspect=_pack_suspect(pack, packet.ticker))
            if card.get("media") is None:
                # EVERY TICKER POST CARRIES A CHART: drop, never enqueue bare.
                print(f"hot-tape DROP {packet.key} {card.get('reason')}", flush=True)
                return {"status": f"drop:{card.get('reason')}", "item_id": None,
                        "text": text}
            media = [card["media"]]
            published = card.get("published") or {}
            chart_state = "ok"

    if dry_run:
        print(f"hot-tape WOULD-BOOK key={packet.key} account={account} "
              f"trigger={packet.trigger} chart={chart_state} llm={phrased['mode']} "
              f"chars={len(text)}", flush=True)
        print(f"    {text}", flush=True)
        return {"status": "would_book", "item_id": None, "text": text}

    try:
        item = OB.make_item(
            account=account,
            kind="breaking",
            text=text,
            as_of=as_of,
            media=media,
            scheduled_at="immediate",
            slot=f"HOT-{now.strftime('%H%M')}Z",
            # M2: an alert outranks a brief. The publisher considers items by
            # (priority, scheduled_at, id), so a brief at the same priority as a
            # fresh alert could take the pass ahead of live news purely on its
            # older timestamp. A brief is context for something already posted;
            # it can always wait one pass.
            priority=(2 if packet.trigger == HT.BRIEF_TRIGGER else 1),
            provenance="hot_tape",
            source=HT.packet_to_source(packet, media=published),
            now=now,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: make_item refused %s: %s", packet.key, exc)
        print(f"hot-tape ENQUEUE-SKIP {packet.key} invalid:{exc}", flush=True)
        return {"status": f"invalid:{exc}", "item_id": None, "text": text}

    if isinstance(item.get("source"), dict):
        # story_lock reads source.story_key — without it the lock we just
        # consulted would own nothing and never bind on the next pass.
        item["source"]["story_key"] = key
        item["source"]["devices"] = list(copy.get("devices") or [])
        # Phrasing telemetry: gate 0.8 tunes on measured engagement, and
        # "did a model write this one" is the first column that table needs.
        item["source"]["llm"] = {
            "mode": phrased["mode"],
            "provider": phrased["provider"],
            "latency_ms": phrased["latency_ms"],
            "violations": len(phrased["violations"]),
        }

    rc = OB.enqueue(item, root, cfg=marketing_cfg)
    if rc == "queued":
        print(f"hot-tape BOOKED id={item['id']} account={account} "
              f"trigger={packet.trigger} at={now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
              flush=True)
        return {"status": "queued", "item_id": item["id"], "text": text}

    print(f"hot-tape ENQUEUE-SKIP {packet.key} {rc}", flush=True)
    if str(rc).startswith("invalid:"):
        # OUR bug, not a guard doing its job: an item we built failed our own
        # validator. Unrecorded on purpose so it shouts every pass.
        print(f"::warning title=hot-tape-invalid-item::{packet.key} was "
              f"refused by outbox.validate_item ({rc}) - the radar built an "
              "item its own schema rejects", flush=True)
    return {"status": rc, "item_id": None, "text": text}


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
    llm_cfg: dict | None = None,
    briefs: list[tuple] | None = None,
) -> list[str]:
    """Book the top events, then the two-step briefs. Returns the queued ids.

    `briefs` is [(brief FactPacket, the alert's account), ...] from
    :func:`pending_briefs`. Briefs are booked AFTER the alerts and out of their
    OWN budget: an alert is time-critical (gate 0.1 asks for <=20 min) and must
    never lose its slot to a follow-up, while a brief that loses every slot on a
    busy tape would age past ``two_step.max_age_min`` and never ship at all.
    They still count against the DAILY cap, which is the real volume valve.
    """
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
    llm = llm_cfg if isinstance(llm_cfg, dict) else {"llm": {}}
    said_capped = False

    def _over_day_cap() -> bool:
        nonlocal said_capped
        if day_used < max_per_day:
            return False
        if not said_capped:                  # one notice per pass, not per loop
            said_capped = True
            print(f"::notice title=hot-tape::daily emit cap reached "
                  f"({day_used}/{max_per_day}) - standing down", flush=True)
        return True

    for packet in events:
        if len(booked) >= max_per_run:
            break
        if _over_day_cap():
            break

        account = HT.severity_account(packet, cfg)
        if account == flagship_account and flagship_budget <= 0:
            # Budget spent this pass: the event still ships, on the wire desk.
            account = wire_account

        result = book_packet(packet, account=account, root=root, cfg=cfg,
                             marketing_cfg=marketing_cfg, llm_cfg=llm, now=now,
                             as_of=as_of, dry_run=dry_run, fetcher=fetcher, pack=pack)
        status = result["status"]

        if status == "would_book":
            booked.append(packet.key)
            day_used += 1
            if account == flagship_account:
                flagship_budget -= 1
            continue
        if status == "queued":
            HT.append_fired(root, HT.fired_entry(packet, item_id=result["item_id"],
                                                 account=account))
            booked.append(result["item_id"])
            day_used += 1
            if account == flagship_account:
                flagship_budget -= 1
            continue
        if status in _TERMINAL_ENQUEUE_CODES:
            # The suppression HELD — record the fire so the cooldown/dedupe
            # memory knows this event was seen, with no item_id to claim. Only
            # "duplicate" used to be recorded, so a cross-account near-dup or a
            # cap rejection came back every five minutes: re-detected, re-drawn
            # (a Chrome raster + an R2 upload each time) and re-refused.
            HT.append_fired(root, HT.fired_entry(packet, item_id=None, account=account))

    # ── Two-step publish: the context brief for an already-posted alert ──────
    # A demo is bounded to ONE post (reviewer M5). pending_briefs already
    # returns nothing in demo; this is the belt for any direct caller.
    brief_budget = 0 if demo else int(
        _cfg(cfg, "two_step.max_per_run", HT.DEFAULTS["two_step"]["max_per_run"]))
    for packet, account in (briefs or []):
        if brief_budget <= 0:
            break
        if _over_day_cap():
            break
        result = book_packet(packet, account=account, root=root, cfg=cfg,
                             marketing_cfg=marketing_cfg, llm_cfg=llm, now=now,
                             as_of=as_of, dry_run=dry_run, fetcher=fetcher, pack=pack)
        status = result["status"]
        if status == "would_book":
            booked.append(packet.key)
            day_used += 1
            brief_budget -= 1
            continue
        if status == "queued":
            HT.append_fired(root, HT.fired_entry(packet, item_id=result["item_id"],
                                                 account=account))
            booked.append(result["item_id"])
            day_used += 1
            brief_budget -= 1
            continue
        if status in _TERMINAL_ENQUEUE_CODES or status == "no_device":
            # A brief that refused for want of a device, or that a guard
            # deduped, is SETTLED: the alert is minutes old and the tape will
            # not hand us a better mechanism five minutes later. Recording it
            # stops the radar rebuilding and re-refusing the same brief every
            # pass until the window closes.
            HT.append_fired(root, HT.fired_entry(packet, item_id=None, account=account))
    return booked


# ─────────────────────────────────────────────────────────────────────────────
# Two-step publish (codex law: the alert wins speed, the brief wins reposts)
# ─────────────────────────────────────────────────────────────────────────────

def pending_briefs(
    root: Path,
    *,
    fired_today: list[dict],
    live: dict,
    pack: dict | None,
    heatmap: dict | None,
    now: datetime,
    cfg: dict,
    demo: bool,
) -> list[tuple]:
    """[(brief packet, the alert's account)] for alerts that earned a follow-up.

    Codex case study 2026-07-28 (§Strongest controlled comparisons A): on the
    SAME story and the SAME account the one-line flash won ~8% more views while
    the contextual version won ~9% better interaction efficiency and a ~49%
    higher repost/view ratio. So the alert ships first and alone, and the brief
    follows on a LATER tick.

    Four gates, all in this function:

      * severity >= ``two_step.min_severity`` (default 90) — above the flagship
        mirror floor, because a second post is a bigger commitment than a mirror;
      * age inside [``delay_min``, ``max_age_min``] — the NEXT tick at the
        earliest (never the pass that booked the alert), and never so late that
        "context" has become a history lesson;
      * the alert actually reached the queue and is still alive there — a brief
        explaining a post that was quarantined is an orphan;
      * no brief for this alert exists in the fired ledger (one per event id).

    Demo passes file NO briefs: a demo is bounded to one post (reviewer M5).
    """
    if demo or not bool(_cfg(cfg, "two_step.enabled", True)):
        return []
    try:
        min_sev = float(_cfg(cfg, "two_step.min_severity",
                             HT.DEFAULTS["two_step"]["min_severity"]))
        delay = float(_cfg(cfg, "two_step.delay_min", HT.DEFAULTS["two_step"]["delay_min"]))
        max_age = float(_cfg(cfg, "two_step.max_age_min",
                             HT.DEFAULTS["two_step"]["max_age_min"]))

        done = {str(r.get("key")) for r in (fired_today or []) if r.get("key")}
        candidates: list[dict] = []
        for row in (fired_today or []):
            key = str(row.get("key") or "")
            if not key or not row.get("item_id") or row.get("demo"):
                continue
            if str(row.get("trigger") or "") == HT.BRIEF_TRIGGER:
                continue
            if HT.brief_key(key) in done:
                continue
            severity = _f(row.get("severity"))
            if severity is None or severity < min_sev:
                continue
            fired_at = _parse_iso(row.get("fired_at"))
            if fired_at is None:
                continue
            age = (now - fired_at).total_seconds() / 60.0
            if age < delay or age > max_age:
                continue
            candidates.append(row)
        if not candidates:
            return []

        # The alert must still be alive in the queue. ONE fold, and only when
        # there is something to brief — this loop runs 81 times a day.
        try:
            statuses = OB.fold_state(root).get("status") or {}
        except Exception as exc:  # noqa: BLE001
            log.warning("hot_tape_radar: outbox fold failed, no briefs this pass: %s", exc)
            return []

        out: list[tuple] = []
        for row in sorted(candidates, key=lambda r: str(r.get("fired_at") or "")):
            # THE ALERT MUST HAVE POSTED, not merely reached the queue (M2). A
            # context brief is the SECOND half of a two-step publish: it says
            # why the thing you just saw matters. Accepting "queued"/"approved"
            # meant the brief could go out while the alert was still waiting on
            # the publisher's gates, and if the alert was then quarantined (its
            # copy, its cap, its tape check) the brief was already live,
            # explaining a post nobody ever saw. The delay window makes this
            # cheap to require: by the time a brief is eligible the alert has
            # had a full publisher pass to reach "posted".
            #
            # This check is a SNAPSHOT at build time; :func:`dispatch_ids`
            # re-checks it before every send, because a booked brief can outlive
            # its alert's "posted" status (recall, quarantine) while it waits.
            if statuses.get(str(row["item_id"])) != "posted":
                continue
            packet = HT.build_brief_packet(
                row, quotes=live, pack=pack, heatmap=heatmap, now=now, cfg=cfg,
                demo=demo, quotes_asof=(live or {}).get("asof"))
            if packet is None:
                print(f"hot-tape BRIEF-REFUSE {row['key']} no-mechanism", flush=True)
                continue
            account = str(row.get("account") or _cfg(cfg, "emit.account", "mastermind_news"))
            out.append((packet, account))
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_radar: pending_briefs failed: %s", exc)
        return []


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

    # The alert item_id behind each ALERT key this lane fired today. Built from
    # the same rows, so resolving a brief's parent costs no extra read.
    alert_item_by_key: dict[str, str] = {}
    for row in (fired_today or []):
        k, iid = str(row.get("key") or ""), row.get("item_id")
        if k and iid and str(row.get("trigger") or "") != HT.BRIEF_TRIGGER:
            alert_item_by_key.setdefault(k, str(iid))

    pending: list[tuple[str, str]] = []      # (fired_at, item_id)
    stale: list[str] = []
    orphans: list[tuple[str, str]] = []      # (brief item_id, parent status)
    for row in candidates:
        item_id = str(row["item_id"])
        if statuses.get(item_id) not in ("queued", "approved"):
            continue
        # A BRIEF RIDES ONLY WHILE ITS ALERT IS STILL POSTED (#3960 minor).
        # pending_briefs makes that check when the brief is BUILT, and that is a
        # SNAPSHOT: a brief whose dispatch lost a push race, or whose publisher
        # run was superseded, sits queued and every later pass inside the
        # carryover window re-dispatches it. If the alert was recalled (operator
        # kill) or quarantined in that gap, the second half of a two-step publish
        # would go out explaining a post nobody ever saw. Re-checked here because
        # this is the last point the radar controls before the send.
        # Fail closed either way, but only DESTROY on positive evidence: a
        # resolved alert that is no longer posted makes the brief a permanent
        # orphan (quarantine, so the scheduled sweep cannot send it either),
        # while an unresolvable parent is merely withheld -- it ages out of the
        # carryover window on its own and a fold hiccup must not cost a
        # legitimate brief. The predicate is shared with the publisher's
        # send-time gate (HT.orphaned_brief_status) so the two call sites of
        # the recall cascade cannot drift.
        orphan_status = HT.orphaned_brief_status(
            row.get("key"), row.get("trigger"), alert_item_by_key, statuses)
        if orphan_status is not None:
            orphans.append((item_id, orphan_status))
            continue
        when = _parse_iso(row.get("fired_at"))
        age = (now - when).total_seconds() / 60.0 if when is not None else None
        if age is None or age > CARRYOVER_MAX_AGE_MIN:
            stale.append(item_id)
            continue
        pending.append((str(row.get("fired_at") or ""), item_id))

    for item_id, parent_status in orphans:
        print(f"::warning title=hot-tape-orphan-brief::context brief {item_id} is "
              f"not dispatched: the alert it explains is {parent_status}, not "
              "posted - a brief is the second half of a two-step publish and "
              "never ships alone", flush=True)
        if parent_status == "unresolved":
            continue
        try:
            OB.transition(item_id, "quarantined", actor="hot_tape_radar", root=root,
                          note=f"orphaned context brief: alert is {parent_status}")
        except Exception as exc:  # noqa: BLE001
            log.warning("hot_tape_radar: could not quarantine orphan brief %s: %s",
                        item_id, exc)

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

#: Hot-tape render litter older than this is swept at the start of each pass.
#: 2 days keeps today and yesterday available for an operator looking at a card
#: in the console, and throws away everything the R2 URL already owns.
_HOT_TAPE_RENDER_RETENTION_DAYS = 2


def sweep_hot_tape_renders(
    root: "Path | str",
    *,
    now: datetime | None = None,
    retention_days: int = _HOT_TAPE_RENDER_RETENTION_DAYS,
) -> int:
    """Delete stale hottape-*.svg/.png render inputs. Returns files removed.

    THE LEAK (2026-07-30): this lane renders a card for EVERY candidate it
    evaluates, before it knows whether the post will ship, on every intraday
    sweep. In one day that wrote 8,068 hottape-*.svg into
    data/marketing/outbox/media/<date>/ -- a directory that is COMMITTED, because
    the nightly chart-NNN.svg snapshots there feed the admin console preview.
    420 MB in the media tree, ~8k new tracked files per day, and a git that had
    started printing "too many unreachable loose objects" on every command.

    The .gitignore now excludes hottape-*.svg specifically (the nightly
    chart-NNN.svg snapshots stay committed). This is the other half: without a
    sweep the files still accumulate on the runner's disk forever.

    Deletes ONLY files matching the hottape- prefix. Never raises: a sweep
    failure must not cost the radar its pass.
    """
    from pathlib import Path as _P
    base = _P(root) / "data" / "marketing" / "outbox" / "media"
    ts = now or datetime.now(timezone.utc)
    cutoff = (ts - timedelta(days=retention_days)).date()
    removed = 0
    try:
        if not base.is_dir():
            return 0
        for day_dir in base.iterdir():
            if not day_dir.is_dir():
                continue
            try:
                day = date.fromisoformat(day_dir.name)
            except (ValueError, TypeError):
                continue          # not a date-named dir: leave it alone
            if day >= cutoff:
                continue
            for f in list(day_dir.glob("hottape-*")):
                try:
                    f.unlink()
                    removed += 1
                except OSError:
                    pass
    except Exception as exc:  # noqa: BLE001 — never cost the radar its pass
        log.warning("hot_tape_radar: render sweep failed: %s", exc)
        return removed
    if removed:
        log.info("hot_tape_radar: swept %d stale render file(s)", removed)
    return removed


def run(
    root: Path,
    *,
    now: datetime | None = None,
    demo: bool = False,
    dry_run: bool = False,
    fetcher: Callable[[str, Path], bool] | None = None,
    quote_builder: Callable[[list[str]], dict] | None = None,
) -> int:
    """One radar pass. Never raises; 0 unless an invariant is genuinely broken.

    ``quote_builder`` overrides the live self-refresh fetcher (see
    :func:`refresh_live_snapshot`); it is only consulted when the shared quote
    view is already too stale to act on, so a healthy tape never reaches it.
    """
    ts = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    # Sweep this lane's own render litter before doing anything else.
    sweep_hot_tape_renders(root, now=ts)
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

    pack = HT.load_pack(root)
    heatmap = _read_json(root / HEATMAP_REL)
    signals = plan_signals(root, now=ts)
    earnings = load_earnings(root)

    live, fresh, age = load_quotes(root, now=ts, cfg=cfg, demo=demo)
    if not fresh and not demo:
        # The shared tape is behind. Fetch it ourselves rather than stand down on
        # another lane's cadence — see the self-refresh block above. Demo is
        # excluded on purpose: its whole point is running against a quiet or
        # closed tape, and its relaxed ceiling admits the committed snapshot
        # anyway, so a demo pass must not spend a live fetch to prove nothing.
        universe = radar_universe(pack, heatmap, signals=signals,
                                  earnings=earnings, cfg=cfg)
        print(f"hot-tape shared tape is {age}m old - self-fetching "
              f"{len(universe)} symbols", flush=True)
        if refresh_live_snapshot(root, universe=universe, builder=quote_builder):
            live, fresh, age = load_quotes(root, now=ts, cfg=cfg, demo=demo)

    quotes = live.get("quotes") if isinstance(live.get("quotes"), dict) else {}
    # Print the ceiling AND its two components. A bare "age=21.92m" reads as a
    # verdict with no bar to measure it against; the 2026-07-29 dark day was
    # diagnosed by hand-correlating those numbers against another lane's push
    # times, which is work the log line should already have done.
    # The SAME resolution the gate used — demo included. See freshness_cfg.
    applied = freshness_cfg(cfg, demo=demo)
    ceiling = HT.effective_max_quote_age_min(live, applied)
    print(f"hot-tape quotes n={len(quotes)} asof={live.get('asof')} "
          f"age={age}m ceiling={ceiling:g}m "
          f"(budget={_cfg(applied, 'max_quote_age_min', HT.DEFAULTS['max_quote_age_min'])}m "
          f"+ feed_delay={live.get('feed_delay_min') or 0:g}m) "
          f"source={live.get('source')} demo={int(bool(demo))}", flush=True)
    if not fresh:
        print(f"::warning title=hot-tape::live quotes are stale (freshest {age}m old "
              f"vs {ceiling:g}m ceiling) - no events this pass. The tape is written "
              "by live-quotes.yml plus this pass's own fetch; a persistent gap here "
              "is a WRITER-LANE fault, not a threshold to widen", flush=True)
        return 0

    # pack / heatmap / signals / earnings were read above the freshness gate:
    # the self-refresh needs them to know which symbols to fetch.
    day = _utc_day(ts)
    as_of = _et_day(ts)
    ring = HT.load_ring(root, RING_KEEP)
    fired_today = HT.load_fired(root, day)

    events = HT.detect_events(
        live,
        pack=pack,
        heatmap=heatmap,
        plan_signals=signals,
        earnings=earnings,
        ring=ring,
        fired_today=fired_today,
        now=ts,
        cfg=cfg,
        demo=demo,
    )
    print(f"hot-tape scan pack={'yes' if pack else 'no'} "
          f"bridge={int(HT.bridge_ok(pack, ts, cfg=cfg))} "
          f"tiles={len((heatmap or {}).get('tiles') or [])} signals={len(signals)} "
          f"earnings={len(earnings.get('tickers') or {})}@{earnings.get('asof')} "
          f"fired_today={len(fired_today)} events={len(events)}", flush=True)
    _warn_stale_earnings(earnings, now=ts, cfg=cfg)
    for packet in events:
        print(f"hot-tape DETECT {packet.trigger} {packet.ticker or packet.sector} "
              f"{packet.direction} sev={packet.severity:.0f} key={packet.key}", flush=True)

    if not dry_run:
        # EVERY pass, eventless included: the ring is the intraday history.
        roll_ring(root, ring_entry(now=ts, day=day, live=live, events=events, cfg=cfg),
                  day=day)

    briefs = pending_briefs(root, fired_today=fired_today, live=live, pack=pack,
                            heatmap=heatmap, now=ts, cfg=cfg, demo=demo)
    for packet, account in briefs:
        print(f"hot-tape BRIEF {packet.facts.get('alert_key')} -> {packet.key} "
              f"account={account} "
              f"mechanism={(packet.facts.get('mechanism') or {}).get('kind')}", flush=True)

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
        llm_cfg=llm_config(root),
        briefs=briefs,
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
            # GITHUB_OUTPUT is APPEND-ONLY and collapses to one value per step, so
            # it cannot carry per-pass ids when one step runs the radar several
            # times (the multi-pass loop in marketing-hot-tape.yml). This file is
            # the per-pass channel: the loop truncates it before each pass and
            # dispatches exactly what that pass booked. Absent env = unchanged
            # single-pass behaviour.
            ids_file = os.environ.get("HOT_TAPE_IDS_FILE", "").strip()
            if ids_file:
                try:
                    Path(ids_file).write_text(joined, encoding="utf-8")
                except Exception as exc:  # noqa: BLE001
                    log.warning("hot_tape_radar: ids-file write failed: %s", exc)
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
    parser.add_argument("--window-status", action="store_true", dest="window_status",
                        help="print IN_WINDOW=0|1 and WINDOW_END_EPOCH=<int> for the "
                             "session-long pass loop, then exit. Detects nothing, "
                             "writes nothing.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s",
                        stream=sys.stderr)
    root = Path(args.root) if args.root else _repo_root()
    demo = bool(args.demo) or _flag("HOT_TAPE_DEMO")

    if args.window_status:
        # ONE window authority. The session-long loop in marketing-hot-tape.yml
        # needs to know when to stop passing, and re-deriving the ET window in
        # bash would be a second implementation of the DST reasoning that
        # HT.in_window already carries — the exact split-brain that put a UTC
        # window in the shipped crons. So it asks the radar instead.
        print(f"IN_WINDOW={1 if (demo or HT.in_window(None, HT.load_config(root))) else 0}")
        print(f"WINDOW_END_EPOCH={window_end_epoch(root, demo=demo)}")
        return 0

    try:
        return run(root, demo=demo, dry_run=bool(args.dry_run))
    except Exception as exc:  # noqa: BLE001
        # Fail toward "no post": a radar that turns 81 runs a day red is noise.
        print(f"::warning title=hot-tape::radar pass failed: {exc}", flush=True)
        log.warning("hot_tape_radar: unexpected failure", exc_info=True)
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
