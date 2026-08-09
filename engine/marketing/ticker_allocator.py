"""engine.marketing.ticker_allocator — one night's chart subjects, spread wide.

THE DEFECT THIS EXISTS TO END. The chart/watchlist lanes drew their subjects
from `attention_supply` (hot story, retail chatter, options volume, the top of
the dollar-volume board, stage-2 leaders) and from `house_picks`, which yields
at most 7 names a night by config. Those pools overlap heavily at the top, so
the network posted the same handful of mega-caps night after night while the
liquidity board underneath it — 2,673 names in `hot_tape_pack.json` — was never
reached. This module is the other half of the supply: a DETERMINISTIC daily
partition of the liquid US universe across the desks.

WHAT IT IS::

    a deterministic per-day, per-account subject list drawn by liquidity rank
    a ZERO-OVERLAP partition: one ticker reaches at most ONE desk on a day
    a mega-cap quota so the names readers know keep a steady presence
    a high-timeframe tag on a few subjects, verified against real bar counts

WHAT IT IS NOT. It is not a signal, a score, or a ranking of merit: `adv_rank`
is a VOLUME fact and the only thing it says is "this trades a lot". Nothing here
originates a call (constitution A7), nothing here writes, and nothing here
decides whether a post ships — the cooldowns, the reuse budget, the near-dup
guard, the cadence cap and the approval desk all still run downstream and can
still delete any subject this hands them.

HOW IT REACHES A POST. `allocate()` returns `Allocation` objects; `supply_rows()`
renders them into the row shape `content_studio.plan_account(ticker_supply=...)`
already walks, so the wiring is a per-account supply list and NOT a new lane. The
`pool` tag on each row (`allocator_megacap` / `allocator_tail` /
`allocator_long_view`) survives into `ContentItem.supply_pool`, then into
`content_plan.json` and the outbox item's provenance — which is both the
operator's receipt for "why is this name in tonight's plan" and the handshake a
writer can key on to frame a long-view post. It is also load-bearing for the
CHART: the featured-chart loop refuses to draw a plan-less item unless it carries
a `supply_pool`, so a row without one ships uncharted and defers forever
(tests/test_chart_director.py::test_a_supply_sourced_item_is_still_chartable).

WHAT IS *NOT* WIRED, stated plainly so nobody reads more into the tag than is
there: `copy_shape` and `timeframe` ride on the supply row and land in the plan
report, but no writer reads them yet and the chart director still picks its own
timeframe from the post's `angle` (`content_studio.director_timeframe_hint`). A
`long_view` subject is verified to HAVE the weekly/monthly history it claims; it
is not yet guaranteed to be DRAWN on that axis.

COOLDOWNS ARE PER ACCOUNT HERE, and that is the narrower of the two gates.
`content_studio.ticker_exposure` is network-wide (ticker → last day ANY desk
showed it) and `plan_account._draw_supply` applies that set to every row this
module produces. So the per-account cooldown below is a FLOOR — it stops one
desk re-running its own name — and the network cooldown on top of it may still
remove a subject this module allocated. Neither one is bypassed.

Public API::

    ALLOCATOR_DEFAULTS                          -> dict
    allocator_cfg(cfg)                          -> dict
    liquid_universe(root, *, cfg, as_of)        -> list[dict]
    account_cooldowns(root, *, as_of, accounts, cfg, state) -> dict[str, frozenset]
    allocate(root, *, as_of, accounts, cfg, ...) -> dict[str, list[Allocation]]
    supply_rows(allocation)                     -> dict[str, list[dict]]
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ALLOCATOR_DEFAULTS",
    "Allocation",
    "allocator_cfg",
    "liquid_universe",
    "account_cooldowns",
    "allocate",
    "supply_rows",
]

#: The in-code fallbacks for `ticker_allocator:` in config/marketing.yml. The
#: config block is the operator surface; these keep a config-less checkout (and
#: every test) working, and they are the numbers quoted in the wave brief.
ALLOCATOR_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "universe_depth": 1200,            # how deep into adv_rank we may draw
    "per_account_per_day": 12,         # chart subjects per desk per day
    "htf_per_account_per_day": 3,      # of those, drawn for the longer view
    "htf_timeframes": ("WEEKLY", "MONTHLY"),
    "megacap_quota_rank": 100,         # adv_rank <= this is a mega-cap
    "megacap_per_account_per_day": 3,
    "cooldown_days": 3,                # per ACCOUNT, per ticker, in sessions
    "min_htf_bars": 60,                # refuse a stub long-view series
}

#: Supply-row `pool` tags. Truthy by construction — an empty tag would make the
#: featured-chart loop skip the item and the post would defer forever.
POOL_MEGACAP = "allocator_megacap"
POOL_TAIL = "allocator_tail"
POOL_LONG_VIEW = "allocator_long_view"

#: copy_shape vocabulary. `tape` is the chart director's own word for a
#: no-claim card; `long_view` is its high-timeframe sibling.
SHAPE_TAPE = "tape"
SHAPE_LONG_VIEW = "long_view"

#: A US listing symbol as the hot-tape pack spells them. Share classes arrive
#: with a dot or a hyphen (`BRK.B`, `BRK-B`), and both spellings of the SAME
#: line are present in the pack — see `_identity` for why that matters.
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z.\-]{0,6}$")


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

def allocator_cfg(cfg: dict | None) -> dict[str, Any]:
    """The resolved `ticker_allocator:` block, every key with its fallback.

    ONE reader of the block, so a knob can never be honoured at one seam and
    ignored at another (same contract as `content_studio.selection_cfg`). Junk
    values fall back rather than raising: a typo in a config number must not be
    able to take the nightly down.
    """
    raw = ((cfg or {}).get("ticker_allocator") or {}) if isinstance(cfg, dict) else {}

    def _int(key: str, floor: int = 0) -> int:
        default = int(ALLOCATOR_DEFAULTS[key])
        try:
            return max(floor, int(raw.get(key, default)))
        except (TypeError, ValueError):
            return default

    tfs_raw = raw.get("htf_timeframes", ALLOCATOR_DEFAULTS["htf_timeframes"])
    tfs = tuple(
        str(t).strip().upper() for t in (tfs_raw or ())
        if str(t).strip().upper() in ("WEEKLY", "MONTHLY", "DAILY")
    ) or tuple(ALLOCATOR_DEFAULTS["htf_timeframes"])

    return {
        "enabled": bool(raw.get("enabled", ALLOCATOR_DEFAULTS["enabled"])),
        "universe_depth": _int("universe_depth", 1),
        "per_account_per_day": _int("per_account_per_day", 0),
        "htf_per_account_per_day": _int("htf_per_account_per_day", 0),
        "htf_timeframes": tfs,
        "megacap_quota_rank": _int("megacap_quota_rank", 1),
        "megacap_per_account_per_day": _int("megacap_per_account_per_day", 0),
        "cooldown_days": _int("cooldown_days", 0),
        "min_htf_bars": _int("min_htf_bars", 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Determinism
# ─────────────────────────────────────────────────────────────────────────────

def _rotation_key(as_of: str, account: str, ticker: str) -> int:
    """A stable per-(day, desk, name) shuffle key.

    NEVER `hash()`: CPython salts string hashing per process (PYTHONHASHSEED), so
    a governor re-run of the SAME night would re-shuffle every desk and hand the
    plan a different universe than the one the first pass published. blake2b is
    stable across processes, hosts and Python versions.

    Varying with `as_of` is what ROTATES the mega-cap quota: each day is an
    independent permutation, so no desk owns NVDA every night.
    """
    payload = f"{as_of}|{account}|{ticker}".encode("utf-8")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")


def _identity(ticker: str) -> str:
    """The dedupe key for one LISTING, folding the two share-class spellings.

    The pack carries `BRK.B` and `BRK-B`, `BF.B` and `BF-B`, `MOG.A` and `MOG-A`
    — one line, two vendor spellings. Handing one spelling to one desk and the
    other to another is exactly the cross-account overlap this module promises
    not to produce, and no reader would call it two names.

    This folds SPELLINGS ONLY. It is not a corporate-family fold: GOOG and GOOGL
    are separate lines with separate tapes and stay separate subjects.
    """
    return str(ticker or "").strip().upper().replace("-", ".")


def _human_dollars(v: float) -> str:
    """A dollar figure in the words a receipt uses ($1.2B, $340M)."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "$0"
    for cut, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= cut:
            return f"${n / cut:.1f}{suffix}"
    return f"${n:.0f}"


# ─────────────────────────────────────────────────────────────────────────────
# Universe
# ─────────────────────────────────────────────────────────────────────────────

def liquid_universe(
    root: object,
    *,
    cfg: dict | None = None,
    as_of: str | None = None,
) -> list[dict]:
    """The liquid US board, most-traded first, capped at `universe_depth`.

    Rows are ``{ticker, adv_rank, adv20_dollars, asof}``.

    The STALENESS VERDICT is delegated to `attention_source.top_by_dollar_volume`
    rather than re-derived here: that function already owns the pool's freshness
    budget and already prints the annotation when the pack lags, and a second
    copy of a freshness law is a second thing to drift. The pack is then re-read
    for the NUMERIC `adv_rank` (the gated list carries it only inside prose), and
    a name present in one and not the other is simply dropped.

    Fail-soft: an absent or stale pack yields [] and never raises.
    """
    resolved = allocator_cfg(cfg)
    depth = int(resolved["universe_depth"])
    try:
        from engine.marketing import attention_source as _asrc  # noqa: PLC0415
        gated = _asrc.top_by_dollar_volume(root, n=depth, as_of=as_of) or []
        pack = _asrc.load_hot_tape_pack(root) or {}
    except Exception:  # noqa: BLE001 — a supply read must never break a plan
        return []

    recs = pack.get("tickers") if isinstance(pack.get("tickers"), dict) else {}
    trade_date = str(pack.get("trade_date") or "")[:10]

    out: list[dict] = []
    seen: set[str] = set()
    for row in gated:
        tkr = str(row.get("ticker") or "").strip().upper()
        if not tkr or not _SYMBOL_RE.match(tkr):
            continue
        ident = _identity(tkr)
        if ident in seen:
            # Keep-first is keep-BEST here: `gated` is ordered by adv_rank, so
            # the surviving spelling is the more heavily traded of the pair,
            # which is the one with the live tape behind it.
            continue
        rec = recs.get(tkr)
        if not isinstance(rec, dict):
            continue
        try:
            rank = int(rec.get("adv_rank"))
        except (TypeError, ValueError):
            continue
        try:
            adv = float(rec.get("adv20_dollars"))
        except (TypeError, ValueError):
            adv = 0.0
        seen.add(ident)
        out.append({
            "ticker": tkr,
            "adv_rank": rank,
            "adv20_dollars": adv,
            "asof": str(rec.get("last_date") or trade_date)[:10],
        })
        if len(out) >= depth:
            break
    out.sort(key=lambda r: (r["adv_rank"], r["ticker"]))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Per-account cooldowns
# ─────────────────────────────────────────────────────────────────────────────

def account_cooldowns(
    root: object,
    *,
    as_of: str,
    accounts: list[str] | tuple[str, ...] | None = None,
    cfg: dict | None = None,
    state: dict | None = None,
) -> dict[str, frozenset[str]]:
    """account → the tickers THAT DESK may not draw tonight.

    Folded from the outbox ledger (`outbox.fold_state`), which is repo-truth
    about what each desk has actually shown readers. Only the EXPOSURE statuses
    count (`content_studio._EXPOSURE_STATUSES`): a quarantined or failed post
    reached nobody and must not lock a name out of tonight's plan.

    STRICTLY EARLIER DAYS ONLY, and the elapsed span is measured in SESSIONS via
    `content_studio.trading_days_since` — a calendar diff would give every Friday
    name a free pass on Monday. Both laws are IMPORTED rather than restated: a
    cooldown that means one thing here and another there is the drift this repo
    keeps paying for.

    Fail-soft: an unreadable ledger yields empty sets (no per-account cooldown).
    The network-wide cooldown in `plan_account` still applies on top, so a
    missing ops file degrades this gate, it does not remove all gating.
    """
    resolved = allocator_cfg(cfg)
    days = int(resolved["cooldown_days"])
    names = [str(a) for a in (accounts or ())]
    empty = {a: frozenset() for a in names}
    if days <= 0:
        return empty

    try:
        from engine.marketing.content_studio import (  # noqa: PLC0415
            _EXPOSURE_STATUSES,
            _item_tickers,
            trading_days_since,
        )
        if state is None:
            from engine.marketing.outbox import fold_state  # noqa: PLC0415
            state = fold_state(root)
        items = (state or {}).get("items") or {}
        statuses = (state or {}).get("status") or {}
    except Exception as exc:  # noqa: BLE001
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning(
            "ticker_allocator.account_cooldowns: ledger unreadable (%s) — "
            "no per-account cooldown", exc)
        return empty

    today = str(as_of or "")[:10]
    # account → ticker → the latest prior day that desk showed it.
    latest: dict[str, dict[str, str]] = {}
    for iid, item in items.items():
        if str(statuses.get(iid, "queued")) not in _EXPOSURE_STATUSES:
            continue
        acct = str(item.get("account") or "")
        if not acct:
            continue
        day = str(item.get("as_of") or "")[:10]
        if not day or (today and day >= today):
            continue
        per_acct = latest.setdefault(acct, {})
        for tkr in _item_tickers(item):
            if day > per_acct.get(tkr, ""):
                per_acct[tkr] = day

    out: dict[str, frozenset[str]] = {}
    for acct in (names or list(latest)):
        cooled: set[str] = set()
        for tkr, day in (latest.get(acct) or {}).items():
            elapsed = trading_days_since(day, today)
            # Fails CLOSED on an undateable row, exactly like `cooled_tickers`:
            # a row we cannot date is a row we cannot clear.
            if elapsed is None or elapsed < days:
                cooled.add(_identity(tkr))
        out[acct] = frozenset(cooled)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# High-timeframe verification
# ─────────────────────────────────────────────────────────────────────────────

def _htf_bars(ticker: str, root: object, timeframe: str, want: int) -> int:
    """Resampled bars available for *ticker* at *timeframe*, capped at *want*.

    Reads the same split-adjusted daily parquets every other chart caller reads
    and resamples through `chart_render.load_ohlcv_timeframe`, so the count is
    the count the CARD would draw — not an estimate off a daily row count.

    Returns 0 for a missing file, an unreadable file, or a timeframe the loader
    refuses. 0 means "do not promise a long view for this name".
    """
    try:
        from engine.marketing.chart_render import load_ohlcv_timeframe  # noqa: PLC0415
        res = load_ohlcv_timeframe(
            str(ticker), root, timeframe=str(timeframe),
            lookback_bars=max(5, int(want)), warm=0)
    except Exception:  # noqa: BLE001 — an unreadable parquet is a refusal
        return 0
    if not res:
        return 0
    bars = res[0]
    if not bars or not bars[0]:
        return 0
    return len(bars[0])


# ─────────────────────────────────────────────────────────────────────────────
# Allocation
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Allocation:
    """One subject handed to one desk for one day."""

    ticker: str
    account: str
    timeframe: str      # DAILY | WEEKLY | MONTHLY
    copy_shape: str     # SHAPE_TAPE | SHAPE_LONG_VIEW
    adv_rank: int
    pool: str
    why: str
    asof: str = ""
    fresh: bool = True

    def as_supply_row(self) -> dict:
        """The row shape `plan_account(ticker_supply=...)` walks.

        `pool` and `why` are the two keys that reach a `ContentItem` (as
        `supply_pool` / `supply_why`); `pool` is read with a bare subscript
        there, so it is never omitted. The rest is provenance the plan report
        and any downstream reader can join on.
        """
        return {
            "ticker": self.ticker,
            "why": self.why,
            "asof": self.asof,
            "source": "hot_tape_pack",
            "pool": self.pool,
            "fresh": bool(self.fresh),
            "timeframe": self.timeframe,
            "copy_shape": self.copy_shape,
            "adv_rank": int(self.adv_rank),
        }


def supply_rows(
    allocation: dict[str, list[Allocation]],
) -> dict[str, list[dict]]:
    """account → supply rows, ready to hand to `plan_account(ticker_supply=)`."""
    return {
        acct: [a.as_supply_row() for a in rows]
        for acct, rows in (allocation or {}).items()
    }


def _why(row: dict, *, megacap_rank: int, is_mega: bool, timeframe: str) -> str:
    """The receipt an operator reads for "why is this name here at all".

    Provenance, not copy. It states the one fact the pack supports — how much
    this name trades — and nothing about direction, merit or expectation.
    """
    base = (f"dollar-volume rank #{row['adv_rank']} "
            f"({_human_dollars(row['adv20_dollars'])} a day)")
    if is_mega:
        base = f"{base}, inside the top {megacap_rank} by liquidity"
    if timeframe != "DAILY":
        base = f"{base}, drawn on the {timeframe.lower()} for the longer view"
    return base


def allocate(
    root: object,
    *,
    as_of: str,
    accounts: list[str] | tuple[str, ...],
    cfg: dict | None = None,
    state: dict | None = None,
    posted_recent: frozenset[str] | set[str] | None = None,
) -> dict[str, list[Allocation]]:
    """The night's subjects, per account, with zero cross-account overlap.

    Deterministic in (as_of, accounts, universe, ledger): the only randomness is
    `_rotation_key`, which is a stable digest, and every ordering below is fully
    keyed. Two calls on the same inputs return the same allocation.

    THE ORDER OF `accounts` IS PART OF THE INPUT. Each phase round-robins over
    the list, so the list's order decides only who gets first refusal within a
    round — but it must be stable across a re-run of the same night, which it is:
    the caller derives it from config.

    `posted_recent` is the long-tail window (`not_posted_within_days`), used only
    to stamp `fresh` for the quota counter. None means the caller offered no
    window, and every allocated name is stamped fresh — which is true of nearly
    all of them at this draw depth, but it is a stamp, not a measurement.

    Fail-soft everywhere: a disabled block, an absent or stale pack, or an empty
    account list returns {} and raises nothing.
    """
    resolved = allocator_cfg(cfg)
    names = [str(a) for a in (accounts or ()) if str(a or "").strip()]
    if not resolved["enabled"] or not names:
        return {}

    per_account = int(resolved["per_account_per_day"])
    if per_account <= 0:
        return {}

    universe = liquid_universe(root, cfg=cfg, as_of=as_of)
    if not universe:
        print("::warning title=marketing-ticker-allocator::"
              "liquid universe empty (hot_tape_pack absent or stale) — the "
              "chart lanes fall back to the attention pools tonight", flush=True)
        return {}

    cooled = account_cooldowns(
        root, as_of=as_of, accounts=names, cfg=cfg, state=state)
    recent = {_identity(t) for t in (posted_recent or ())}

    mega_rank = int(resolved["megacap_quota_rank"])
    mega_n = min(int(resolved["megacap_per_account_per_day"]), per_account)
    megacaps = [r for r in universe if r["adv_rank"] <= mega_rank]
    tail = [r for r in universe if r["adv_rank"] > mega_rank]

    # Per-desk draw orders, computed ONCE. A full permutation per (day, desk)
    # is what buys the spread: nothing here prefers the top of the tail, so the
    # rank-1,180th name is as reachable as the rank-101st.
    def _ordered(pool: list[dict], acct: str) -> list[dict]:
        return sorted(
            pool,
            key=lambda r: (_rotation_key(as_of, acct, r["ticker"]), r["ticker"]))

    mega_order = {a: _ordered(megacaps, a) for a in names}
    tail_order = {a: _ordered(tail, a) for a in names}
    cursor = {a: [0, 0] for a in names}          # [mega index, tail index]

    claimed: set[str] = set()                    # identities, network-wide
    picked: dict[str, list[dict]] = {a: [] for a in names}

    def _take(acct: str, pool: list[dict], idx_slot: int) -> dict | None:
        """The next unclaimed, uncooled row for *acct*, or None."""
        order = (mega_order if idx_slot == 0 else tail_order)[acct]
        i = cursor[acct][idx_slot]
        cool = cooled.get(acct, frozenset())
        while i < len(order):
            row = order[i]
            i += 1
            ident = _identity(row["ticker"])
            if ident in claimed or ident in cool:
                continue
            cursor[acct][idx_slot] = i
            claimed.add(ident)
            return row
        cursor[acct][idx_slot] = i
        return None

    # ── Phase 1: the mega-cap quota, BEFORE the long tail ────────────────────
    # Round-robin rather than desk-by-desk so a thin mega-cap pool is shared
    # evenly instead of being drained by whoever is first in the list.
    for _ in range(mega_n):
        for acct in names:
            row = _take(acct, megacaps, 0)
            if row is not None:
                picked[acct].append(dict(row, _mega=True))

    # ── Phase 2: the long tail, up to the per-desk budget ────────────────────
    for _ in range(per_account):
        for acct in names:
            if len(picked[acct]) >= per_account:
                continue
            row = _take(acct, tail, 1)
            if row is None:
                # The tail is exhausted for this desk (every remaining name is
                # claimed or cooled). Mega-caps are the honest backfill: they
                # are the same universe, already ranked, and the desk is short a
                # subject either way.
                row = _take(acct, megacaps, 0)
                if row is not None:
                    row = dict(row, _mega=True)
            if row is not None:
                picked[acct].append(dict(row))

    # ── Phase 3: the long view ───────────────────────────────────────────────
    # Chosen on a SEPARATE salt so the long-view picks are not just the front of
    # the draw order, and verified against real resampled bars: a name without
    # the history is left on DAILY rather than promised a weekly it cannot draw.
    htf_n = min(int(resolved["htf_per_account_per_day"]), per_account)
    tfs = list(resolved["htf_timeframes"]) or ["WEEKLY"]
    min_bars = int(resolved["min_htf_bars"])
    htf_choice: dict[str, dict[str, str]] = {a: {} for a in names}
    bar_cache: dict[tuple[str, str], int] = {}
    for acct in (names if htf_n > 0 else ()):
        order = sorted(
            picked[acct],
            key=lambda r: (_rotation_key(as_of, acct + "|htf", r["ticker"]),
                           r["ticker"]))
        taken = 0
        for row in order:
            if taken >= htf_n:
                break
            # The timeframe index advances only on ACCEPTANCE, so a run of
            # refusals cannot silently tip the whole night onto one axis.
            tf = tfs[taken % len(tfs)]
            key = (row["ticker"], tf)
            if key not in bar_cache:
                bar_cache[key] = _htf_bars(row["ticker"], root, tf, min_bars)
            if bar_cache[key] < min_bars:
                continue
            htf_choice[acct][row["ticker"]] = tf
            taken += 1

    out: dict[str, list[Allocation]] = {}
    for acct in names:
        rows: list[Allocation] = []
        for row in picked[acct]:
            tkr = row["ticker"]
            tf = htf_choice[acct].get(tkr, "DAILY")
            is_mega = bool(row.get("_mega"))
            long_view = tf != "DAILY"
            rows.append(Allocation(
                ticker=tkr,
                account=acct,
                timeframe=tf,
                copy_shape=SHAPE_LONG_VIEW if long_view else SHAPE_TAPE,
                adv_rank=int(row["adv_rank"]),
                pool=(POOL_LONG_VIEW if long_view
                      else POOL_MEGACAP if is_mega else POOL_TAIL),
                why=_why(row, megacap_rank=mega_rank, is_mega=is_mega,
                         timeframe=tf),
                asof=str(row.get("asof") or ""),
                fresh=_identity(tkr) not in recent,
            ))
        out[acct] = rows
    return out
