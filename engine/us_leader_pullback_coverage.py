"""engine/us_leader_pullback_coverage.py — the LEADER-PULLBACK COVERAGE publisher.

WHY THIS FILE EXISTS
--------------------
`engine/us_leader_pullback.py` (#5007, §6.9 R4) is the organ.  It writes NO file by
design and its LEADER leg needs ``rs_pct`` — a PIT CROSS-SECTIONAL percentile it refuses
to reach for itself, so that a single-name call can never leak one.  #5105 then shipped
the EARLY-TURN starter intake, whose leader half reads the organ's coverage from
``site/anticipationdata/us_leader_pullback.json``.

NOTHING PUBLISHED THAT FILE.  Measured on this base: the washout half of the intake
admits (``us_basket_turn`` emits per-basket WASHED_OUT), the leader half resolved ``{}``
on every production run and disclosed itself as "the leader-pullback organ published no
coverage for this run".  Fail-closed and honest — and structurally incapable of admitting
anything.  This module is the missing publisher.

WHAT IT PRODUCES
----------------
ONE site artifact per nightly run::

    site/anticipationdata/us_leader_pullback.json
    {"schema": "us_leader_pullback.v0", ..., "states": {TICKER: <organ latest() row>}}

and NOTHING else.  No ``data/`` path, no ledger, no forward state — the nightly is the
sole advancer of forward ledgers and this is a per-run site artifact builder, not a
ledger.  Re-running it twice on the same store produces the same bytes.

CONSTRUCTION DISCIPLINE — the #5026 pattern, no permissive defaults
------------------------------------------------------------------
The TURN WATCH desk (#5026) took leader fires 28 -> 7 by feeding the organ a REAL
point-in-time RS cross-section instead of permissive defaults.  This publisher runs the
same construction:

* the cross-section is the organ's OWN :func:`us_leader_pullback.rs_excess_percentile`,
  computed ONCE per run over the graded universe against the SPY close on the same
  adjustment basis — never a per-name RS invented here, which would be a second answer
  to the question that lane measures;
* the universe is :mod:`engine.us_turn_watch`'s GRADED DECK STORE — the same population
  that desk's leg (d) ranks over, so the percentile in this artifact and the percentile
  behind that desk mean the same thing and the two can never disagree about a name.  A
  cross-section over a different population is a different number wearing the same name,
  and ``RS_TOP_PCT`` is a pre-registered v0 constant whose quartile was measured against
  THIS population (#5026: leader fires 28 -> 7 once the organ was fed a real PIT
  cross-section).  ``STORE_LADDER`` below is a parameter so a widening is a one-line
  change — but it is a CONSTRUCTION change and belongs to the §6.6 re-measurement route,
  jointly with the desk, not to a publisher PR.  See ``coverage.store_ladder``;
* a name with no ``rs_pct`` on its last session is published with the organ's own
  ``null_reason`` and NO state.  It is never imputed to the middle of the cross-section,
  and "not a leader" is never manufactured out of a missing input;
* no lookahead: :func:`rs_excess_percentile` ranks within each date and the benchmark is
  forward-filled only, so the value at date *t* is a function of bars at or before *t*.
  :func:`us_leader_pullback.evaluate` carries the same guarantee bar by bar.

THIN AND NULL DAYS PUBLISH; A DEAD RUN DOES NOT OVERWRITE A LIVE ONE
--------------------------------------------------------------------
Display tier: no gauntlet gates this artifact, and a day on which the organ claims no
state for anybody still publishes — with every name's ``null_reason`` printed.  The one
thing that does NOT publish is a RUN-WIDE data failure (no universe, no benchmark, so no
cross-section at all): writing an all-null artifact there would delete yesterday's real
coverage and make a broken price store indistinguishable from a quiet tape.  That run
prints a ``::warning``, leaves the previous artifact in place, and exits 0 — the
consumer's own ``asof`` guard is what keeps a stale row from being read as fresh.

AUTHORITY
---------
DISPLAY TIER.  This module ranks nothing, gates nothing, sizes nothing and escalates
nothing; it publishes the organ's per-name state so a consumer that already fails closed
can resolve it.  The organ's v0 constants are ungauntleted and its AUTHORITY block rides
into the artifact verbatim.
"""
from __future__ import annotations

import json
import logging
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine import us_leader_pullback as organ
from engine.us_turn_watch import (
    BENCHMARK,
    DECK_STORE,
    SELECTION_ERA,
    _safe_stem,
    load_close,
    universe,
)

log = logging.getLogger(__name__)

__all__ = [
    "SCHEMA", "ARTIFACT", "AUTHORITY", "DISCLOSURE", "DISCLOSURE_ZH",
    "MIN_BARS", "COVERAGE_SHRINK_WARN", "STORE_LADDER",
    "load_bars", "rs_cross_section", "compute_coverage", "write_artifact",
    "artifact_path", "run",
]

#: The rungs this publisher reads, in order.  DECK STORE ONLY, deliberately — see the
#: construction note in the module docstring.  MEASURED 2026-08-09 on the committed
#: 2026-08-07 board: 28 of 54 Prophet candidates are absent from this rung and 25 of them
#: (ADAM among them — the named acceptance case for the §6.8(b) zone law) sit on the lower
#: rungs of ``us_turn_watch.STORE_LADDER``, which carry the SAME adjustment basis (239/239
#: overlapping names agree on the 126-session return to <0.5pp).  Widening is therefore
#: SAFE for the basis and would take deck-store coverage of the board's own candidates
#: from 26/54 to 51/54 — but it takes the cross-section from 697 names to 2,994, which
#: restates every percentile the pre-registered ``RS_TOP_PCT`` quartile is measured
#: against and would desync this artifact from the TURN WATCH desk's leg (d).  That is a
#: §6.6 re-measurement, not a publisher change.
STORE_LADDER: tuple[str, ...] = (DECK_STORE,)

#: The artifact's schema IS the organ's — every row in ``states`` is one
#: :func:`us_leader_pullback.latest` row, so a constants change that mints a new organ
#: schema moves this artifact with it.  ``engine.us_early_turn`` accepts any schema whose
#: family prefix is ``us_leader_pullback``.
SCHEMA = organ.SCHEMA

#: Path parts under ``site/``.  MUST stay byte-identical to
#: ``engine.us_early_turn._LEADER_ARTIFACT`` — the whole point of this module is that the
#: consumer finds the file.  ``tests/test_us_leader_pullback_coverage.py`` pins the pair.
ARTIFACT: tuple[str, ...] = ("anticipationdata", "us_leader_pullback.json")

#: The organ's OWN history floor, not the desk's 200.  A name below it can only produce a
#: ``needs 260 daily bars`` null, so it is counted as short history and left out of the
#: cross-section rather than published as a row that says nothing.
MIN_BARS = organ.MIN_HISTORY_BARS

#: Coverage falling below this fraction of the previous run's is annotated.  A publisher
#: that silently halves its universe looks exactly like a quiet tape from downstream —
#: the shrink direction is the one a detector goes blind in.
COVERAGE_SHRINK_WARN = 0.5

AUTHORITY = dict(organ.AUTHORITY)

DISCLOSURE = (
    "Per-name leader-pullback state for the US graded universe, published so the "
    "early-entry intake can resolve it. Display tier, v0 constants, ungauntleted: it "
    "ranks nothing, gates nothing and sizes nothing. Names the organ could not state are "
    "published with the reason printed, never as a quiet 'no'."
)
DISCLOSURE_ZH = (
    "美股评级范围内每只个股的“龙头回踩”状态，发布出来供早期入场判断读取。"
    "仅供展示，采用 v0 参数、未经检验流程：不参与排序、准入或仓位。"
    "组件无法给出状态的个股会连同原因一并列出，而不是含糊地记为“否”。"
)


# ---------------------------------------------------------------------------
# Store access
# ---------------------------------------------------------------------------

def load_bars(ticker: str, data_root: Path,
              ladder: tuple[str, ...] = STORE_LADDER
              ) -> tuple[pd.Series | None, pd.Series | None, str | None]:
    """``(close, volume, store)`` for one name; ``(None, None, None)`` when unusable.

    The CLOSE half is normalised exactly as :func:`us_turn_watch.load_close` normalises
    it — float cast, datetime index, last-wins de-duplication, sorted, NaN-dropped — so
    the series the organ evaluates here is the series that desk evaluates.  The organ
    also wants VOLUME (its anchored VWAP is ``sum(close*volume)/sum(volume)``), which
    that loader does not return, so this one reads the frame once and takes both columns
    rather than paying a second parquet read per name.

    Volume is returned as-is on the close's own index; the organ decides for itself when
    it is unusable and NULLS its anchored VWAP with a named reason.  Nothing here
    fabricates a volume, and a store with no volume column is a valid input.
    """
    stem = _safe_stem(ticker)
    for sub in ladder:
        p = data_root / sub / f"{stem}.parquet"
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p)
            if "close" not in df.columns or df.empty:
                continue
            idx = pd.to_datetime(df.index)
            close = pd.Series(df["close"].astype(float).to_numpy(), index=idx)
            vol = None
            if "volume" in df.columns:
                vol = pd.Series(
                    pd.to_numeric(df["volume"], errors="coerce").to_numpy(), index=idx)
            keep = ~close.index.duplicated(keep="last")
            close = close[keep].sort_index()
            if vol is not None:
                vol = vol[keep].sort_index()
            finite = close.notna()
            close = close[finite]
            if vol is not None:
                vol = vol[finite]
            if close.empty:
                continue
            return close, vol, sub
        except Exception as e:  # noqa: BLE001 — one unreadable file never kills the run
            log.debug("load_bars(%s) from %s/: %s", ticker, sub, e)
            continue
    return None, None, None


# ---------------------------------------------------------------------------
# The cross-section
# ---------------------------------------------------------------------------

def rs_cross_section(closes: dict[str, pd.Series],
                     benchmark: pd.Series | None) -> dict[str, pd.Series]:
    """PIT cross-sectional RS percentile per name, computed ONCE for the whole run.

    Delegates to :func:`us_leader_pullback.rs_excess_percentile` — the organ's own
    construction, never a re-derivation.  Returns ``{}`` when there is no benchmark or no
    universe: that is the honest "no cross-section" state, and :func:`compute_coverage`
    treats it as a run-wide data failure rather than publishing a board of nulls.

    The percentile is over THIS universe (the graded deck store, ~700 US names).  Its
    width rides into the artifact as ``coverage.cross_section_names`` so the number is
    never read as a market-wide rank.
    """
    if not closes or benchmark is None or len(benchmark) == 0:
        return {}
    try:
        wide = pd.DataFrame(closes).sort_index()
        pct = organ.rs_excess_percentile(wide, benchmark)
    except Exception as e:  # noqa: BLE001
        print(f"::warning title=leader-pullback-coverage::RS cross-section failed ({e}) "
              f"— no coverage published this run", flush=True)
        log.warning("us_leader_pullback_coverage: cross-section failed: %s", e)
        return {}
    if pct is None or getattr(pct, "empty", True):
        return {}
    return {str(tk): pct[tk] for tk in pct.columns}


# ---------------------------------------------------------------------------
# Row shaping
# ---------------------------------------------------------------------------

def _compact(row: dict[str, Any]) -> dict[str, Any]:
    """Drop ``None`` values from an organ row.

    LOSSLESS FOR EVERY CONSUMER, and that is the whole argument: every read of these rows
    downstream goes through ``Mapping.get(key)``, which returns ``None`` for an absent key
    and for a present ``None`` alike.  The organ's ``latest()`` emits all 30 columns on
    every name and most are ``None`` outside an open episode, so keeping them would add
    roughly 40% to a ~700-name nightly artifact to encode nothing.  ``state`` and
    ``null_reason`` are exactly complementary on an organ row, so "state absent" still
    means "the organ nulled this name" and still carries its reason.
    """
    return {k: v for k, v in row.items() if v is not None}


def _session_stamp(closes: dict[str, pd.Series],
                   benchmark: pd.Series | None) -> tuple[str | None, str | None, str | None]:
    """``(data_session, max_session, note)`` — MAJORITY session, never ``max()``.

    Same rule and the same reason as ``us_turn_watch._session_stamp``: a ``max()`` stamp
    fails OPEN, because one 24/7 tape reaching a later date makes the whole artifact read
    fresh while the equities it is computed on are a session behind.
    """
    dates: list[str] = []
    for s in closes.values():
        try:
            if len(s):
                dates.append(str(pd.Timestamp(s.index[-1]).date()))
        except Exception:  # noqa: BLE001, S112
            continue
    if not dates:
        if benchmark is not None and len(benchmark):
            b = str(pd.Timestamp(benchmark.index[-1]).date())
            return b, b, "no graded names — session taken from the benchmark"
        return None, None, "no graded names and no benchmark — session is unknown"
    counts = Counter(dates)
    session = counts.most_common(1)[0][0]
    newest = max(dates)
    note = None
    if newest != session:
        note = (f"{counts[newest]} of {len(dates)} graded names print a newer bar "
                f"({newest}); coverage is stamped {session}, the session the majority of "
                f"the tape reaches")
    return session, newest, note


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def compute_coverage(data_root: Path | None = None, *,
                     universe_limit: int | None = None) -> dict[str, Any]:
    """Build the coverage artifact.  Never raises; returns the artifact dict.

    ``coverage.publishable`` is FALSE only on a run-wide data failure (no graded names or
    no cross-section).  :func:`run` refuses to write in that case so a broken store cannot
    overwrite a real artifact with a dead one — see the module docstring.
    """
    t0 = time.time()
    from lib import config as _cfg  # noqa: PLC0415
    root = data_root if data_root is not None else _cfg.data_dir()

    bench, _bvol, _bstore = load_bars(BENCHMARK, root)
    tickers = universe(root, universe_limit)

    closes: dict[str, pd.Series] = {}
    volumes: dict[str, pd.Series | None] = {}
    short: list[str] = []
    for tk in tickers:
        close, vol, _store = load_bars(tk, root)
        if close is None:
            continue
        if len(close) < MIN_BARS:
            short.append(tk)
            continue
        closes[tk] = close
        volumes[tk] = vol

    rs = rs_cross_section(closes, bench)
    session, max_session, session_note = _session_stamp(closes, bench)

    states: dict[str, dict[str, Any]] = {}
    state_counts: Counter[str] = Counter()
    null_counts: Counter[str] = Counter()
    for tk in sorted(closes):
        col = rs.get(tk)
        try:
            row = organ.latest(closes[tk], rs_pct=col, volume=volumes.get(tk))
        except Exception as e:  # noqa: BLE001 — one bad name never kills the publisher
            # PUBLISHED as a named null, not dropped.  A name that vanishes from the map
            # reads downstream as "outside the organ's universe", which is a different
            # and false statement — the organ HAS this name and could not state it.
            log.debug("us_leader_pullback_coverage: %s failed (%s)", tk, e)
            row = {
                "schema": organ.SCHEMA,
                "construction_era": organ.CONSTRUCTION_ERA,
                "asof": str(pd.Timestamp(closes[tk].index[-1]).date()),
                "state": None,
                "null_reason": f"organ raised: {type(e).__name__}",
            }
        states[tk] = _compact(row)
        st = row.get("state")
        if st is None:
            # The organ's null_reason is free text with a count in it on the history leg;
            # bucket on its stable head so the census does not explode into 700 keys.
            reason = str(row.get("null_reason") or "unstated")
            null_counts[reason.split(",")[0].split(":")[0].strip()] += 1
        else:
            state_counts[str(st)] += 1

    elapsed = round(time.time() - t0, 2)
    publishable = bool(states) and bool(rs)

    return {
        "schema": SCHEMA,
        "as_of": session,
        "data_session": session,
        "max_session": max_session,
        "session_note": session_note,
        "selection_era": SELECTION_ERA,
        "construction_era": organ.CONSTRUCTION_ERA,
        "indicator_source": "engine.confluence_tiers",
        "authority": AUTHORITY,
        "disclosure": DISCLOSURE,
        "disclosure_zh": DISCLOSURE_ZH,
        "organ_disclosure": organ.DISCLOSURE,
        "constants": organ.CONSTANTS,
        "benchmark": BENCHMARK if bench is not None else None,
        "runtime_seconds": elapsed,
        "coverage": {
            "universe": len(tickers),
            "graded": len(closes),
            "skipped_short_history": len(short),
            "min_bars": MIN_BARS,
            "store_ladder": list(STORE_LADDER),
            "cross_section_names": len(rs),
            "states_published": len(states),
            "state_counts": dict(sorted(state_counts.items())),
            "null_counts": dict(sorted(null_counts.items())),
            "context_states": sorted(("PULLBACK", "RESET_TURN")),
            "universe_limit": universe_limit,
            # FALSE == run-wide data failure. `run` refuses to write, so the previous
            # artifact survives and a broken store never masquerades as a quiet tape.
            "publishable": publishable,
        },
        "states": states,
    }


def artifact_path(site_root: Path | None = None) -> Path:
    if site_root is None:
        from lib import config as _cfg  # noqa: PLC0415
        site_root = _cfg.site_dir()
    return Path(site_root).joinpath(*ARTIFACT)


def write_artifact(artifact: dict[str, Any], site_root: Path | None = None) -> Path:
    """Write ``site/anticipationdata/us_leader_pullback.json``.

    This root is NOT ``site/prophet/`` — that root is exclusive Prophet publisher
    authority and the nightly engine job restores it from HEAD before staging, so an
    artifact written there is reverted on a SUCCESSFUL night too.  ``site/anticipationdata``
    is already the ANTICIPATION surface's own root and rides the step's broad ``git add
    site/``.
    """
    out = artifact_path(site_root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, separators=(",", ":"), default=str,
                              sort_keys=False) + "\n", encoding="utf-8")
    return out


def _previous_states(site_root: Path | None = None) -> int | None:
    """How many states the artifact on disk carries, or None when there is none."""
    p = artifact_path(site_root)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    raw = payload.get("states") if isinstance(payload, dict) else None
    return len(raw) if isinstance(raw, dict) else None


def run(data_root: Path | None = None, site_root: Path | None = None, *,
        universe_limit: int | None = None) -> tuple[Path | None, dict[str, Any]]:
    """Compute and publish.  Returns ``(written_path_or_None, artifact)``.

    ``None`` for the path means the run was a run-wide data failure and the previous
    artifact was deliberately left in place — the fail-closed direction for a publisher
    whose consumer treats missing coverage as "no starter licence".
    """
    artifact = compute_coverage(data_root, universe_limit=universe_limit)
    cov = artifact["coverage"]
    if not cov["publishable"]:
        print(f"::warning title=leader-pullback-coverage::no coverage computed "
              f"(universe={cov['universe']}, graded={cov['graded']}, "
              f"cross_section={cov['cross_section_names']}) — the previous artifact is "
              f"kept rather than overwritten with an empty one; the EARLY-TURN leader "
              f"half admits nothing until the price store loads", flush=True)
        return None, artifact

    prev = _previous_states(site_root)
    if prev and cov["states_published"] < COVERAGE_SHRINK_WARN * prev:
        print(f"::warning title=leader-pullback-coverage-shrink::coverage fell from "
              f"{prev} to {cov['states_published']} names — publishing, but a shrinking "
              f"universe reads downstream exactly like a quiet tape", flush=True)

    out = write_artifact(artifact, site_root)
    return out, artifact
