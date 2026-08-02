#!/usr/bin/env python3
"""Publish the stock-seasonality calendar clock (Lane 1 + Lane 2 + selection).

Writes ``site/seasonalitydata/index.json`` and one
``site/seasonalitydata/entities/<SYMBOL>.json`` per covered symbol, exactly per
``research/STOCK_SEASONALITY_LANE2_DESIGN_SPEC.md`` §9.

Three properties are worth knowing before editing this file:

* **The universe is measured, never listed.** ``config/seasonality_universe.yml``
  carries a threshold and a scope fence; membership comes from counting complete
  years in ``data/yahoo/`` on every run.
* **The selection correction is cached for a year.** The window family, its
  independent circular year-shift null, and the Westfall-Young adjusted p-values
  all depend on the COMPLETE-year panel, which changes once per calendar year.
  The cache key is the panel's own hash, so a vendor re-adjustment of old prices
  invalidates it even though no year boundary moved. Without this, B=2000 x 2645
  windows x 2 panels x ~290 symbols would run every night for a result that is
  identical 364 nights out of 365.
* **Fail-open per symbol.** A bad parquet, a short history, or a degenerate
  panel logs and continues. ``main`` never raises and always returns 0; a
  seasonality page is context, and taking the nightly down for it would be a
  worse outcome than a missing symbol.

Nothing here ranks symbols against each other, and nothing here emits a
forecast, a score, or a Neural Web state.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.seasonality import calendar as season_calendar  # noqa: E402
from engine.seasonality import panel as season_panel  # noqa: E402
from engine.seasonality import scanner as season_scanner  # noqa: E402

log = logging.getLogger("build_stock_seasonality")

ENTITY_SCHEMA = "biopharma_seasonality.entity.v1"
INDEX_SCHEMA = "biopharma_seasonality.index.v1"
CACHE_SCHEMA = "biopharma_seasonality.selection_cache.v1"

CUM_SCALE = 1e-5
CUM_ENCODING = "int_1e-5_log_return"
WINDOW_CONVENTION = (
    "start_doy/end_doy are 1-based day-of-year; cum index = doy - 1; window log return = "
    "cum[end_doy - 1] - cum[start_doy - 1] (enter at the start_doy close, exit at the end_doy close)"
)
THIN_YEARS = 6

PRICE_SOURCE = {
    "vendor": "yahoo",
    "adjustment": "vendor_current_vintage",
    "is_pit_adjustment": False,
    "field": "close_adjusted",
}

SURVIVORSHIP_DISCLOSURE = (
    "The covered set is built from today's price store, so names that were delisted, "
    "acquired, or renamed are absent. That makes the covered set look healthier than "
    "the real historical market. Nothing on this page ranks symbols against each other, "
    "so the bias does not enter any per-symbol number."
)
ADJUSTMENT_DISCLOSURE = (
    "Split- and dividend-adjusted closes are the vendor's CURRENT vintage re-applied to "
    "all history. This is not a frozen point-in-time adjustment: a very old year can read "
    "slightly differently than it did at the time."
)
RATES_NOTE = (
    "Browsing many symbols runs many familywise tests, so about 5 in 100 symbols clear "
    "their own null by chance alone. These are the program-level rates over the whole "
    "covered set, published so a single symbol's result can be read against them."
)


def _annotate(title: str, message: str) -> None:
    """Emit a GitHub Actions annotation.

    A bare ``print`` on purpose: every logger in this repo prefixes its records,
    and GitHub silently drops an annotation that does not START the line. ``flush``
    is load-bearing because stdout is block-buffered when piped in Actions.
    """
    print(f"::warning title={title}::{message}", flush=True)


# --- policy + universe ------------------------------------------------------


def load_policy(root: Path) -> dict:
    path = Path(root) / "config" / "seasonality_universe.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _in_scope(symbol: str, selection: dict) -> bool:
    if symbol in set(selection.get("exclude") or ()):
        return False
    if any(symbol.startswith(prefix) for prefix in selection.get("exclude_prefixes") or ()):
        return False
    if any(symbol.endswith(suffix) for suffix in selection.get("exclude_suffixes") or ()):
        return False
    return symbol.replace("_", "").replace("-", "").replace(".", "").isalnum()


def measure_universe(root: Path, policy: dict) -> list[dict]:
    """Count complete years for every in-scope symbol and keep those clearing the floor."""
    selection = policy.get("selection") or {}
    minimum = int(selection.get("min_complete_years", season_panel.MIN_COMPLETE_YEARS))
    store = Path(root) / "data" / "yahoo"
    covered: list[dict] = []
    for path in sorted(store.glob("*.parquet")):
        symbol = path.stem
        if not _in_scope(symbol, selection):
            continue
        try:
            closes = season_panel.load_adjusted_closes(root, symbol)
            returns = season_panel.daily_log_returns(closes)
            years = season_panel.complete_years(pd.DatetimeIndex(returns.index))
        except Exception as exc:  # noqa: BLE001 — a bad parquet must not stop the sweep
            log.warning("universe scan skipped %s: %s", symbol, exc)
            continue
        if len(years) >= minimum:
            covered.append({"symbol": symbol, "n_years_available": len(years), "first_year": years[0]})
    return covered


def load_labels(root: Path, policy: dict) -> dict[str, dict]:
    """Resolve display names and sectors: config → membership → SEC → the ticker.

    The chain is ordered by how much it knows. Config labels cover the ETFs and
    indices, which no company registry contains. ``data/universe/membership.parquet``
    covers the operating companies with a real name AND a sector. The SEC titles
    are a last resort with no sector at all.

    A missing source degrades to the ticker, which is legible but useless: the §6
    picker renders ``TICKER · Name · N years``, so an unresolved symbol shows its
    ticker twice. That degrade used to be SILENT — the SEC file this originally
    relied on does not exist in this repo, so 149 of 220 covered symbols shipped
    with ``name == symbol`` and ``sector: null`` and nothing said so. Sources that
    are absent or that leave a large share unresolved now announce themselves.
    """
    labels = {str(k): dict(v or {}) for k, v in (policy.get("labels") or {}).items()}
    from_config = len(labels)

    membership_path = Path(root) / "data" / "universe" / "membership.parquet"
    from_membership = 0
    if membership_path.exists():
        try:
            frame = pd.read_parquet(membership_path, columns=["ticker", "name", "sector"])
            for ticker, name, sector in frame.itertuples(index=False, name=None):
                key = str(ticker or "").strip()
                title = str(name or "").strip()
                if key and title and key not in labels:
                    labels[key] = {
                        "name": title,
                        "group": "equity",
                        "sector": str(sector).strip() or None if sector else None,
                    }
                    from_membership += 1
        except Exception as exc:  # noqa: BLE001 — labels are cosmetic, never fatal
            _annotate("seasonality-labels", f"universe membership unreadable ({exc})")
    else:
        _annotate(
            "seasonality-labels",
            f"{membership_path.relative_to(root)} absent — company names and sectors unresolved",
        )

    sec_path = Path(root) / "data" / "edgar" / "company_tickers.json"
    from_sec = 0
    if sec_path.exists():
        try:
            raw = json.loads(sec_path.read_text(encoding="utf-8"))
            for row in raw.values():
                ticker = str(row.get("ticker") or "").strip()
                title = str(row.get("title") or "").strip()
                if ticker and title and ticker not in labels:
                    labels[ticker] = {"name": title, "group": "equity", "sector": None}
                    from_sec += 1
        except Exception as exc:  # noqa: BLE001
            _annotate("seasonality-labels", f"SEC company titles unreadable ({exc})")

    log.info(
        "seasonality labels: %d from config, %d from universe membership, %d from SEC titles",
        from_config,
        from_membership,
        from_sec,
    )
    return labels


def label_for(symbol: str, labels: dict[str, dict]) -> dict:
    entry = labels.get(symbol) or {}
    return {
        "name": entry.get("name") or symbol,
        "group": entry.get("group") or "equity",
        "sector": entry.get("sector"),
    }


# --- selection cache --------------------------------------------------------


def cache_path(root: Path, symbol: str) -> Path:
    return Path(root) / "data" / "seasonality" / "selection" / f"{symbol}.json"


def load_cache(root: Path, symbol: str) -> dict | None:
    path = cache_path(root, symbol)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("selection cache unreadable for %s: %s", symbol, exc)
        return None
    return payload if payload.get("schema") == CACHE_SCHEMA else None


# Bump whenever _scan_block's SHAPE or the meaning of anything inside it changes.
# Without this a code change that adds a field to the cached block would be
# invisible to the panel hash — the panel did not move, so every symbol would
# keep serving a block built by the previous version of the code, forever. The
# key check below is belt-and-braces: it also refuses a block whose key set does
# not match what this build writes, so forgetting to bump cannot ship silently.
SELECTION_FORMAT = 3
_SCAN_BLOCK_KEYS = frozenset(
    {
        "format", "panel_hash", "family_hash", "n_years", "seed", "B",
        "max_abs_t_quantiles", "max_abs_t_ladder", "null_by_lookback", "registered_panel", "best",
    }
)


def _cache_hit(block: dict | None, panel: season_panel.YearPanel | None, resamples: int) -> bool:
    if block is None or panel is None:
        return block is None and panel is None
    return (
        block.get("format") == SELECTION_FORMAT
        and set(block) == _SCAN_BLOCK_KEYS
        and block.get("panel_hash") == season_scanner.panel_fingerprint(panel)
        # Same data is not the same question: a cached null is only valid for the
        # family it was maximised over.
        and block.get("family_hash") == season_scanner.family_fingerprint()
        and int(block.get("B", -1)) == resamples
    )


def _scan_block(result: season_scanner.ScanResult) -> dict:
    return {
        "format": SELECTION_FORMAT,
        "panel_hash": result.panel_hash,
        "family_hash": result.family_hash,
        "n_years": result.n_years,
        "seed": result.seed,
        "B": result.n_resamples,
        "max_abs_t_quantiles": result.max_abs_t_quantiles,
        "max_abs_t_ladder": result.max_abs_t_ladder,
        "null_by_lookback": result.null_by_lookback,
        "registered_panel": result.registered_panel,
        "best": result.best,
    }


# --- payload ----------------------------------------------------------------


def quantize(path: np.ndarray) -> list[int]:
    """Log-cumulative path to integers in 1e-5 units (see ``calendar.cum_scale``)."""
    return [int(value) for value in np.rint(np.asarray(path, dtype=np.float64) / CUM_SCALE)]


def _family_block(block: dict) -> dict:
    return {
        "n_candidates": season_scanner.N_CANDIDATES,
        "start_days": season_scanner.START_DAYS_RULE,
        "horizons_days": list(season_scanner.HORIZONS_DAYS),
        "statistic": season_scanner.STATISTIC,
        "null": {
            "method": season_scanner.NULL_METHOD,
            "B": block["B"],
            "max_abs_t_quantiles": block["max_abs_t_quantiles"],
            # --- additive, see the PR body: the client cannot compute a null, so
            # the chance track and a dragged window's graded read need the shape.
            "seed": block["seed"],
            "n_years": block["n_years"],
            "max_abs_t_quantile_ladder": block["max_abs_t_ladder"],
        },
        # --- additive. The page's `10y | 15y | 25y | Max` pills each change the
        # panel, and a 10-year |t| judged against the 25-year null above is
        # compared against a threshold built from a different sample size and a
        # different autocorrelation structure — wrong, and flatteringly so. One
        # null per offered lookback shorter than the panel; a lookback at least as
        # long as the panel IS the panel, so it is absent and the client falls
        # back to `null` above (that is the "Max" pill).
        "null_by_lookback": block["null_by_lookback"],
        "registered_panel": block["registered_panel"],
        "best": block["best"],
        # --- additive disclosure. The null maximum is taken over the 2645-window
        # grid above. Seven of the twelve calendar-month rows are 28 or 31 days
        # long and are therefore NOT grid members, so their p_adj_maxt_family is
        # priced against a family that does not literally contain them. Measured
        # effect over 8000 (resample, row) cells: zero — the 2645-window maximum
        # dominates a single month window in every draw — but an approximation a
        # reader cannot see is exactly what this program exists not to ship.
        "registered_panel_pricing": (
            "every registered row is priced against the maximum over the 2645-window grid; "
            "month rows whose length is not in horizons_days are not themselves grid members"
        ),
    }


def _default_window(
    raw_block: dict,
    neutral_block: dict | None,
    neutral_panel: season_panel.YearPanel | None,
    *,
    n_years_complete: int,
    is_benchmark: bool,
) -> dict | None:
    best = raw_block.get("best")
    if not best:
        return None
    raw_clears = bool(best["clears_95"])

    neutral_clears: bool | None = None
    neutral_basis = "unavailable"
    if is_benchmark:
        # The benchmark's residual against itself is identically zero. Its calendar
        # structure IS the market's, so "clears vs market" is false by construction
        # rather than unknown.
        neutral_clears = False
        neutral_basis = "self_benchmark"
    elif neutral_block and neutral_panel is not None:
        stats = season_scanner.window_statistics(
            neutral_panel.cum, best["start_doy"], best["end_doy"]
        )
        if stats["abs_t"] is not None:
            neutral_clears = bool(stats["abs_t"] >= neutral_block["max_abs_t_quantiles"]["0.95"])
            neutral_basis = season_panel.BETA_SOURCE

    if n_years_complete < THIN_YEARS:
        state = "thin"
    elif raw_clears and neutral_clears:
        state = "own"
    elif raw_clears:
        # Includes the unknown-neutral case: "the market's pattern" is the
        # strongest claim we can make without overclaiming a name-specific one.
        state = "market"
    else:
        state = "fails"

    exceedance = float(best["exceedance_pct"])
    return {
        "start_doy": best["start_doy"],
        "end_doy": best["end_doy"],
        "source": "symbol_best",
        "abs_t": best["abs_t"],
        "null_max_exceedance_pct": max(1.0, float(round(exceedance))),
        "state": state,
        "raw_clears": raw_clears,
        "neutral_clears": neutral_clears,
        "stability": best["stability"],
        # --- additive: the floored value above can never print 0%, but it also
        # cannot distinguish "0.05%" from "1.0%". The unfloored figure keeps that.
        "null_max_exceedance_raw_pct": round(exceedance, 3),
        "neutral_basis": neutral_basis,
    }


def build_entity_payload(
    *,
    symbol: str,
    label: dict,
    panel: season_panel.YearPanel,
    returns: pd.Series,
    neutral_panel: season_panel.YearPanel | None,
    raw_block: dict | None,
    neutral_block: dict | None,
    n_years_available: int,
    as_of: date | None,
    generated_at: str,
    benchmark: str,
) -> dict:
    # `asof` is a FRESHNESS claim — the page renders it as "Through Jul 31". It is
    # the symbol's own last observed session, never the wall clock: defaulting to
    # today would advertise data through tonight on a store that stopped three
    # weeks ago, and nothing on the page would contradict it.
    asof = as_of or panel.last_session or date.today()
    aggregate = season_calendar.canonical_paths(panel)
    payload: dict = {
        "schema": ENTITY_SCHEMA,
        "symbol": symbol,
        "name": label["name"],
        "asof": asof.isoformat(),
        "generated_at": generated_at,
        "price_source": dict(PRICE_SOURCE),
        "coverage": {
            "n_years_complete": panel.n_years,
            "first_year": panel.years[0] if panel.years else None,
            "last_complete_year": panel.years[-1] if panel.years else None,
            "n_years_available": n_years_available,
            "years_capped_at": season_panel.YEARS_CAP,
            "complete_year_rule": season_panel.COMPLETE_YEAR_RULE,
            "missing_session_policy": season_panel.MISSING_SESSION_POLICY,
            "leap_policy": season_panel.LEAP_POLICY,
        },
        "calendar": {
            "basis": "calendar_day",
            "n_slots": season_panel.N_SLOTS,
            "labels": list(season_panel.slot_labels()),
            # --- additive: makes the integer quantization self-describing so a
            # consumer cannot read 30125 as a 30125x log return.
            "cum_encoding": CUM_ENCODING,
            "cum_scale": CUM_SCALE,
            # --- additive: two independent implementations of this spec already
            # disagreed by one day on what `start_doy` names. Stating it in the
            # artifact is cheaper than a silent off-by-one on every published
            # window. Matches §9's client formula and §3's `Aug 3 -> Sep 11` chip
            # (doy 215 -> 254): enter at the start_doy close, exit at the end_doy
            # close.
            "window_convention": WINDOW_CONVENTION,
        },
        "years": [
            {"year": year, "cum": quantize(panel.cum[index])}
            for index, year in enumerate(panel.years)
        ],
        "current_year": (
            {
                "year": panel.current_year,
                "last_index": panel.current_last_index,
                "cum": quantize(panel.current_cum),
            }
            if panel.current_year is not None and panel.current_cum is not None
            else None
        ),
        "aggregate": {key: quantize(value) for key, value in aggregate.items()},
        "views": season_calendar.build_views(panel, returns),
    }

    if raw_block is not None:
        payload["family"] = _family_block(raw_block)
        payload["default_window"] = _default_window(
            raw_block,
            neutral_block,
            neutral_panel,
            n_years_complete=panel.n_years,
            is_benchmark=symbol == benchmark,
        )
    else:
        # §9: an absent family block is a defined state — the page then says the
        # search accounting is not finished rather than inventing a verdict.
        payload["family"] = None
        payload["default_window"] = None

    neutral: dict = {}
    if neutral_panel is not None and symbol != benchmark:
        market = {
            "benchmark": benchmark,
            "beta_source": season_panel.BETA_SOURCE,
            "years": [
                {"year": year, "cum": quantize(neutral_panel.cum[index])}
                for index, year in enumerate(neutral_panel.years)
            ],
        }
        if neutral_block is not None:
            market["family"] = _family_block(neutral_block)
        neutral["market"] = market
    payload["neutral"] = neutral
    return payload


# --- build ------------------------------------------------------------------


def _write_json(path: Path, payload: dict, *, volatile_keys: tuple[str, ...] = ()) -> tuple[bool, int]:
    """Write only when the meaningful content changed. Returns (wrote, bytes)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False) + "\n"
    if path.exists() and volatile_keys:
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            stable_new = {k: v for k, v in payload.items() if k not in volatile_keys}
            stable_old = {k: v for k, v in existing.items() if k not in volatile_keys}
            if stable_new == stable_old:
                return False, len(path.read_bytes())
        except Exception:  # noqa: BLE001 — an unreadable prior file is simply replaced
            pass
    path.write_text(text, encoding="utf-8")
    return True, len(text.encode("utf-8"))


def build(
    *,
    root: Path,
    as_of: date | None = None,
    generated_at: str | None = None,
    resamples: int = season_scanner.DEFAULT_RESAMPLES,
    symbols: list[str] | None = None,
    null_budget: int | None = None,
    prune: bool = True,
) -> dict:
    """Build the whole seasonality artifact set. Never raises for one bad symbol."""
    root = Path(root)
    started = time.time()
    policy = load_policy(root)
    selection = policy.get("selection") or {}
    benchmark = str(policy.get("benchmark") or "SPY")
    labels = load_labels(root, policy)

    universe = measure_universe(root, policy)
    if symbols:
        wanted = set(symbols)
        universe = [row for row in universe if row["symbol"] in wanted]
    if not universe:
        _annotate("stock_seasonality", "no symbol cleared the complete-year floor — nothing written")
        return {"n_entities": 0, "wrote": 0, "elapsed_s": round(time.time() - started, 2)}

    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    cap = int(selection.get("years_cap", season_panel.YEARS_CAP))

    benchmark_returns: pd.Series | None = None
    try:
        benchmark_returns = season_panel.daily_log_returns(
            season_panel.load_adjusted_closes(root, benchmark)
        )
    except Exception as exc:  # noqa: BLE001
        _annotate(
            "stock_seasonality",
            f"benchmark {benchmark} unreadable ({exc}) — market-neutral panels skipped this run",
        )

    entities_dir = root / "site" / "seasonalitydata" / "entities"
    index_entries: list[dict] = []
    total_bytes = 0
    wrote = 0
    recomputed = 0
    failures: list[str] = []
    raw_clearing = 0
    raw_tested = 0
    neutral_clearing = 0
    neutral_symbols = 0
    max_entity_bytes = 0
    largest_symbol = ""
    last_sessions: list[date] = []

    for row in universe:
        symbol = row["symbol"]
        try:
            closes = season_panel.load_adjusted_closes(root, symbol)
            returns = season_panel.daily_log_returns(closes)
            panel = season_panel.build_year_panel(returns, symbol=symbol, cap=cap)
            if panel.n_years == 0:
                failures.append(symbol)
                continue
            # Slot 0 IS the rebase anchor, so a Jan-1 session's return enters no
            # window and no aggregate path while `views.month[k=1]` still counts
            # it — the two would report January differently and both look fine.
            # No US equity or ETF can trip this; an around-the-clock instrument
            # that slipped past the scope fence would, so refuse it loudly rather
            # than publish two Januaries.
            if float(np.abs(panel.daily[:, 0]).max()) > 0.0:
                _annotate(
                    "stock_seasonality",
                    f"{symbol} has a Jan-1 session: slot 0 is the rebase anchor, so its return "
                    "would enter no window — symbol skipped (see config/seasonality_universe.yml)",
                )
                failures.append(symbol)
                continue

            neutral_panel = None
            if symbol != benchmark and benchmark_returns is not None:
                neutral_panel = season_panel.build_neutral_panel(
                    returns, benchmark_returns, symbol=symbol, keep_years=panel.years, cap=cap
                )

            cached = load_cache(root, symbol) or {}
            raw_block = cached.get("raw")
            neutral_block = cached.get("neutral")
            needs_raw = not _cache_hit(raw_block, panel, resamples)
            # When the benchmark itself is unreadable there IS no neutral panel to
            # judge, so a stored block is stale-but-good rather than wrong. Marking
            # it "needs recompute" would overwrite it with null on one bad night
            # and force a full B x 2645 resample on the night after the heal.
            needs_neutral = (
                False
                if (benchmark_returns is None and symbol != benchmark)
                else not _cache_hit(neutral_block, neutral_panel, resamples)
            )

            if (needs_raw or needs_neutral) and null_budget is not None and recomputed >= null_budget:
                # Budget exhausted: keep any valid cached block, publish the rest
                # with an absent family (a defined §9 state), and finish tomorrow.
                raw_block = raw_block if _cache_hit(raw_block, panel, resamples) else None
                neutral_block = neutral_block if _cache_hit(neutral_block, neutral_panel, resamples) else None
            else:
                if needs_raw:
                    result = season_scanner.scan(panel, n_resamples=resamples)
                    raw_block = _scan_block(result) if result else None
                if needs_neutral:
                    result = (
                        season_scanner.scan(neutral_panel, n_resamples=resamples)
                        if neutral_panel is not None
                        else None
                    )
                    neutral_block = _scan_block(result) if result else None
                if needs_raw or needs_neutral:
                    recomputed += 1
                    _write_json(
                        cache_path(root, symbol),
                        {
                            "schema": CACHE_SCHEMA,
                            "symbol": symbol,
                            "last_complete_year": panel.years[-1],
                            "raw": raw_block,
                            "neutral": neutral_block,
                        },
                    )

            label = label_for(symbol, labels)
            payload = build_entity_payload(
                symbol=symbol,
                label=label,
                panel=panel,
                returns=returns,
                neutral_panel=neutral_panel,
                raw_block=raw_block,
                neutral_block=neutral_block,
                n_years_available=row["n_years_available"],
                as_of=as_of,  # None => the symbol's own last session

                generated_at=generated_at,
                benchmark=benchmark,
            )
            changed, size = _write_json(
                entities_dir / f"{symbol}.json", payload, volatile_keys=("generated_at",)
            )
            wrote += int(changed)
            total_bytes += size
            if size > max_entity_bytes:
                max_entity_bytes, largest_symbol = size, symbol

            if panel.last_session is not None:
                last_sessions.append(panel.last_session)
            if raw_block and raw_block.get("best"):
                raw_tested += 1
                raw_clearing += int(bool(raw_block["best"]["clears_95"]))
            if neutral_block and neutral_block.get("best"):
                neutral_symbols += 1
                neutral_clearing += int(bool(neutral_block["best"]["clears_95"]))

            index_entries.append(
                {
                    "symbol": symbol,
                    "name": label["name"],
                    "group": label["group"],
                    "sector": label["sector"],
                    "n_years": row["n_years_available"],
                    "first_year": row["first_year"],
                    # --- additive: n_years is the AVAILABLE history per §9's example,
                    # while the panel (and therefore the chart) is capped. The picker
                    # promise in §6 needs the number the page will actually draw.
                    "n_years_panel": panel.n_years,
                }
            )
        except Exception as exc:  # noqa: BLE001 — one symbol never takes the lane down
            log.warning("seasonality entity failed for %s: %s", symbol, exc)
            failures.append(symbol)

    unresolved = sorted(row["symbol"] for row in index_entries if row["name"] == row["symbol"])
    if index_entries and len(unresolved) > len(index_entries) // 5:
        _annotate(
            "seasonality-labels",
            f"{len(unresolved)} of {len(index_entries)} covered symbols have no display name "
            f"(the picker would show the ticker twice): {', '.join(unresolved[:12])}",
        )

    covered = {row["symbol"] for row in index_entries}
    partial = bool(symbols)
    # A partial run knows nothing about the symbols it did not look at. Pruning
    # or republishing the index from one would delete the other ~219 entity files
    # and rewrite the catalog to a single row — a `--symbols AAPL` debug run would
    # take the whole page down. Only a full sweep may speak for the universe.
    healthy = bool(covered) and len(failures) <= len(universe) // 2
    if prune and not partial and healthy:
        _prune_entities(entities_dir, covered)
    elif prune:
        log.info(
            "prune skipped (partial=%s, covered=%d, failures=%d) — the committed tree "
            "is more trustworthy than this run",
            partial,
            len(covered),
            len(failures),
        )

    if partial:
        log.info("partial run (%d symbol(s)) — index.json left untouched", len(covered))
        return {
            "n_entities": len(index_entries),
            "wrote": wrote,
            "null_recomputed": recomputed,
            "failures": len(failures),
            "partial": True,
            "total_bytes": total_bytes,
            "max_entity_bytes": max_entity_bytes,
            "largest_symbol": largest_symbol,
            "elapsed_s": round(time.time() - started, 2),
        }

    # Same freshness law as the per-entity `asof`: the newest session the covered
    # set actually contains, not the night the builder happened to run.
    index_as_of = as_of or (max(last_sessions) if last_sessions else date.today())
    index_payload = {
        "schema": INDEX_SCHEMA,
        "as_of": index_as_of.isoformat(),
        "default_symbol": (
            str(policy.get("default_symbol") or benchmark)
            if str(policy.get("default_symbol") or benchmark) in covered
            else (sorted(covered)[0] if covered else None)
        ),
        "n_entities": len(index_entries),
        "entities": sorted(index_entries, key=lambda entry: entry["symbol"]),
        # --- additive (commissioned): the honesty strip prints these so a single
        # symbol's result can be read against the program-level fire rate.
        "program_rates": {
            "resamples": resamples,
            "raw": {
                # Denominator is symbols whose null was actually COMPUTED, not
                # symbols published. A budget-limited night ships some entities
                # with no family block at all; counting those as non-clearing
                # would understate the rate against the 5% chance expectation the
                # note below tells the reader to compare it with.
                "n_symbols": raw_tested,
                "n_clearing": raw_clearing,
                "share": round(raw_clearing / raw_tested, 4) if raw_tested else None,
            },
            "market_neutral": {
                "n_symbols": neutral_symbols,
                "n_clearing": neutral_clearing,
                "share": round(neutral_clearing / neutral_symbols, 4) if neutral_symbols else None,
            },
            "chance_expectation_share": 0.05,
            "note": RATES_NOTE,
        },
        "disclosures": {
            "min_complete_years": int(selection.get("min_complete_years", season_panel.MIN_COMPLETE_YEARS)),
            "survivorship": SURVIVORSHIP_DISCLOSURE,
            "price_adjustment": ADJUSTMENT_DISCLOSURE,
            "no_ranking": "This artifact set carries no score, rank, or cross-symbol ordering.",
        },
    }
    _write_json(root / "site" / "seasonalitydata" / "index.json", index_payload)

    if failures:
        _annotate(
            "stock_seasonality",
            f"{len(failures)} symbol(s) skipped: {', '.join(sorted(failures)[:12])}",
        )

    summary = {
        "n_entities": len(index_entries),
        "wrote": wrote,
        "null_recomputed": recomputed,
        "failures": len(failures),
        "unresolved_labels": len(unresolved),
        "total_bytes": total_bytes,
        "max_entity_bytes": max_entity_bytes,
        "largest_symbol": largest_symbol,
        "raw_clearing": raw_clearing,
        "raw_tested": raw_tested,
        "neutral_clearing": neutral_clearing,
        "neutral_symbols": neutral_symbols,
        "elapsed_s": round(time.time() - started, 2),
    }
    log.info("stock seasonality: %s", json.dumps(summary))
    return summary


def _prune_entities(entities_dir: Path, covered: set[str]) -> None:
    """Drop entity files for symbols that no longer clear the floor."""
    if not entities_dir.exists():
        return
    for path in entities_dir.glob("*.json"):
        if path.stem in covered:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if payload.get("schema") == ENTITY_SCHEMA:
            path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the stock seasonality calendar clock.")
    parser.add_argument("--root", type=Path, default=_REPO_ROOT)
    parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--resamples", type=int, default=season_scanner.DEFAULT_RESAMPLES)
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument(
        "--null-budget",
        type=int,
        default=None,
        help="Cap symbols whose null is recomputed in one run (default: unlimited).",
    )
    parser.add_argument("--no-prune", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        summary = build(
            root=args.root,
            as_of=args.as_of,
            generated_at=args.generated_at,
            resamples=args.resamples,
            symbols=args.symbols,
            null_budget=args.null_budget,
            prune=not args.no_prune,
        )
        print(json.dumps(summary), flush=True)
    except Exception as exc:  # noqa: BLE001 — fail-open: context never takes the lane down
        log.warning("stock seasonality build failed: %s", exc)
        _annotate("stock_seasonality", f"build failed ({exc}) — previous artifact retained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
