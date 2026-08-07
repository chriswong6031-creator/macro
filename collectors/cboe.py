"""CBOE collectors: daily put/call ratios and SPX dealer-gamma (GEX).

GEX methodology (standard open-source convention, e.g. gex-tracker):
  dealers assumed long calls / short puts ->
    call GEX(strike) = +gamma * OI * 100 * spot^2 * 0.01
    put  GEX(strike) = -gamma * OI * 100 * spot^2 * 0.01
  net GEX = sum over strikes (expressed in $bn per 1% move);
  gamma flip = the zero-gamma spot from a ±25% grid reevaluation of net dealer gamma
    (engine/gex_engine._gamma_flip, same convention as collectors/deribit).
The earlier cumulative-by-strike zero-crossing is undefined whenever net GEX ends
negative (the cumsum never re-crosses zero), which blanked the dashboard banner for
every short-gamma session 2026-06-24 -> 07-28.
This is an assumption, not ground truth — see LIMITATIONS.md. Delayed chain,
EOD cadence: a regime/vol-context input, not a day-trading tool.
"""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

from collectors.base import Adapter
from lib import config, nyse_calendar

log = logging.getLogger(__name__)

# 2026-07-27: the CBOE CDN rate-limited (HTTP 429) the delayed_quotes chain endpoint
# for ~a minute spanning the putcall + gex sweeps; the 3s/6s/12s per-request ladder sat
# entirely inside the window, so _SPX/SPY/MSFT (and putcall with them) lost the session
# while QQQ recovered on a retry 10s later. The window flaps per-request, so one spaced
# extra attempt after a real cooldown beats more rapid-fire retries.
CHAIN_429_COOLDOWN_S = 60.0

# 2026-07-30 proved 60s is not enough. The CDN held the 429 CONTINUOUSLY for ≥3 minutes
# (23:42:32Z → 23:45:33Z+, run 30590845976) — past the 3/6/12s per-request ladder AND
# past the single 60s cooldown above — so putcall + gex/gex_SPX/gex_SPY/gex_QQQ/gex_IWM
# all lost the session; the single names only landed because the window lifted later in
# the sweep. A chain snapshot is unrecoverable after tonight (delayed_quotes serves the
# LIVE snapshot only), so the cost asymmetry is extreme: 5 idle minutes on a bad night
# versus a permanent hole. Escalate to a spaced LADDER — 60s, then 300s — which spans
# the measured 07-30 window with margin. Both adapters walk the same ladder.
CHAIN_429_COOLDOWN_LADDER_S: tuple[float, ...] = (CHAIN_429_COOLDOWN_S, 300.0)


# ── WRITE-SIDE SESSION GATE (M7, review 2026-07-29) ───────────────────────────
# Both adapters below stamp their one-row snapshot with `pd.Timestamp(date.today())`
# unconditionally, so a run on a Saturday/Sunday/holiday RECOMPUTES every field off a
# stale carried-forward chain and lands it as a genuine-looking observation. That is how
# data/cboe/{gex,putcall}.parquet each came to hold 13 non-session rows of 39 — rows that
# corrupt `.iloc[-1]`, rolling means, percentile windows, POSITIONAL "n-session" lookbacks
# and maturity `len()` gates all over the estate (#3721 class).
#
# Every READER now session-filters, so the historical rows are harmless and are left in
# place — no backfill, no rewrite. This gate stops NEW ones landing: on a non-session day
# the adapter returns nothing and the store simply does not advance, which is the honest
# outcome (there was no session, so there is no observation).
def _session_gated(frames: dict, adapter: str) -> dict:
    """Drop a whole snapshot when today is not an NYSE session."""
    today = date.today()
    if nyse_calendar.is_session(today):
        return frames
    # Bare line-start print: a logger prefix would push "::" off column 0 and GitHub
    # would drop the annotation (tests/test_gh_annotation_line_start.py).
    print(f"::notice title=cboe-session-gate::{adapter}: {today} is not an NYSE session "
          f"- snapshot discarded rather than stamped as an observation", flush=True)
    log.info("cboe: %s skipped — %s is not a trading session", adapter, today)
    return {}


class PutCallAdapter(Adapter):
    """Put/call volume ratios COMPUTED from CBOE delayed chains (the official
    market-statistics CSV endpoints went behind the SPA in 2025/26). Index P/C
    from SPX; equity-proxy P/C from SPY+QQQ+IWM combined. Not the official
    total-market ratio — a computed proxy from the most liquid underlyings
    (see LIMITATIONS.md), which also obeys the 'compute, don't scrape' rule."""

    name = "cboe_putcall"
    group = "cboe"

    def __init__(self) -> None:
        self.cfg = config.load()["cboe"]

    def _chain_volumes(self, symbol: str, retries: int | None = None) -> tuple[float, float]:
        url = self.cfg["chain_url"].replace("_SPX", symbol)
        r = self.http_get(url, retries=retries or self.cfg["retries"], timeout=120)
        options = pd.DataFrame(r.json()["data"]["options"])
        cp = options["option"].str.extract(r"\d{6}([CP])\d{8}$")[0]
        vol = pd.to_numeric(options["volume"], errors="coerce").fillna(0)
        return float(vol[cp == "P"].sum()), float(vol[cp == "C"].sum())

    def _spx_after_cooldowns(self, first_err: Exception) -> tuple[float, float]:
        """Walk CHAIN_429_COOLDOWN_LADDER_S on the all-or-nothing _SPX leg.

        putcall is whole-frame dependent on _SPX (index_pc_ratio has no other source),
        so this leg failing costs the WHOLE session — that is how 07-27 and 07-30 both
        died. One 60s cooldown cleared the ~1-min 07-27 flap; the ≥3-min 07-30 window
        outlasted it, so a second spaced attempt at 300s follows. Re-raises the LAST
        error when the ladder is exhausted, so the source still reports FAILED and the
        coverage tripwire makes the resulting hole loud."""
        err = first_err
        for cooldown in CHAIN_429_COOLDOWN_LADDER_S:
            log.warning("putcall: _SPX chain failed (%s); cooling down %.0fs for one "
                        "spaced retry", err, cooldown)
            time.sleep(cooldown)
            try:
                return self._chain_volumes("_SPX", retries=1)
            except Exception as e:  # noqa: BLE001 — walk the ladder, then fail the source
                err = e
        raise err

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        from datetime import date
        try:
            put_idx, call_idx = self._chain_volumes("_SPX")
        except Exception as e:  # noqa: BLE001 — spaced retries, then fail the source
            put_idx, call_idx = self._spx_after_cooldowns(e)
        put_eq = call_eq = 0.0
        for sym in ("SPY", "QQQ", "IWM"):
            try:
                p, c = self._chain_volumes(sym)
                put_eq += p
                call_eq += c
            except Exception as e:  # noqa: BLE001 — partial proxy still useful
                log.warning("putcall: %s chain failed: %s", sym, e)
        snap = pd.DataFrame({
            "index_pc_ratio": [put_idx / call_idx if call_idx else None],
            "equity_pc_ratio": [put_eq / call_eq if call_eq else None],
            "index_put_vol": [put_idx], "index_call_vol": [call_idx],
            "equity_put_vol": [put_eq], "equity_call_vol": [call_eq],
        }, index=[pd.Timestamp(date.today())])
        return _session_gated({"putcall": snap.dropna(axis=1, how="all")}, "PutCallAdapter")


# underlyings scored daily for the GEX/magnets layer (engine/gex_engine.py). Indices
# + a small set of the most-liquid optionable single-names (dealer-sign is least
# unreliable where the chain is deep). Overridable via config cboe.gex.symbols.
DEFAULT_GEX_SYMBOLS = ["_SPX", "SPY", "QQQ", "IWM",
                       "NVDA", "AAPL", "TSLA", "AMD", "META", "MSFT"]
GEX_Q = {"_SPX": 0.013, "SPY": 0.013, "QQQ": 0.006, "IWM": 0.013}  # div yields; names -> 0


class GexAdapter(Adapter):
    """Dealer-gamma summaries for SPX + liquid underlyings. Persists a 1-row/day
    summary per symbol (regime/flip/magnets/IV30 history -> feeds the board's regime
    panel, the per-stock context overlay, and the realized-vol validation). The rich
    per-strike chain is NOT stored (the runner is a date-indexed time series); the
    board/stock builds re-fetch the live chain for the strike-ladder detail. The
    legacy `gex` (SPX) frame is preserved byte-for-byte for build_site + the
    gex_flip_cross alert. A VOL-REGIME + LEVELS MAP, not alpha (see LIMITATIONS.md)."""

    name = "cboe_gex"
    group = "cboe"

    def __init__(self) -> None:
        self.cfg = config.load()["cboe"]

    def _chain(self, symbol: str, retries: int | None = None) -> tuple[pd.DataFrame, float]:
        """Fetch + parse one underlying's delayed chain -> per-strike DataFrame
        [K, T, iv(decimal), oi, gamma, is_call, expiry] + spot."""
        url = self.cfg["chain_url"].replace("_SPX", symbol)
        r = self.http_get(url, retries=retries or self.cfg["retries"], timeout=120)
        data = r.json()["data"]
        spot = float(data.get("close") or data.get("current_price"))
        o = pd.DataFrame(data["options"])
        m = o["option"].str.extract(r"^[A-Z]+W?(?P<exp>\d{6})(?P<cp>[CP])(?P<strike>\d{8})$")
        o["is_call"] = m["cp"] == "C"
        o["K"] = pd.to_numeric(m["strike"], errors="coerce") / 1000.0
        exp = pd.to_datetime(m["exp"], format="%y%m%d", errors="coerce")
        o["expiry"] = exp
        o["T"] = (exp - pd.Timestamp(date.today())).dt.days / 365.0
        o["iv"] = pd.to_numeric(o.get("iv"), errors="coerce")
        o["oi"] = pd.to_numeric(o.get("open_interest"), errors="coerce")
        o["gamma"] = pd.to_numeric(o.get("gamma"), errors="coerce")
        return o.dropna(subset=["K", "T", "is_call", "oi"]), spot

    def _legacy_spx(self, o: pd.DataFrame, spot: float, gcfg: dict,
                    engine_flip: "float | None" = None) -> pd.DataFrame:
        """Original SPX frame (net_gex_bn, flip_strike, spot, spot_vs_flip_pct) for
        build_site + gex_flip_cross + latest['market_gamma']. net_gex_bn/spot math is
        unchanged. flip_strike/spot_vs_flip_pct now carry the ENGINE's grid-reevaluated
        zero-gamma level (engine.gex_engine._gamma_flip, passed in from fetch()): the
        old cumulative-by-strike zero crossing is UNDEFINED whenever net GEX ends
        negative (the cumsum never re-crosses zero) — exactly the short-gamma regime
        the dealer-gamma banner exists to flag. It blanked the banner every short
        session 2026-06-24→07-28 (flip present on 22/22 net-positive days, 2/17
        net-negative), and where it did resolve it sat 5-13% above spot (the put-wall
        offset point), contradicting the board's engine flip ~1% from spot. One
        definition now serves both surfaces; the sign convention of
        spot_vs_flip_pct (spot below flip -> negative -> dealers short) is unchanged."""
        c = o.dropna(subset=["gamma"]).copy()
        horizon = pd.Timestamp(date.today()) + pd.Timedelta(days=gcfg["max_expiry_days"])
        win = gcfg["strike_window_pct"]
        c = c[(c["expiry"] <= horizon) & c["K"].between(spot * (1 - win), spot * (1 + win))]
        mult = gcfg["contract_multiplier"] * spot ** 2 * gcfg["pct_move"]
        sign = np.where(c["is_call"], 1.0, -1.0)
        c = c.assign(gex=sign * c["gamma"] * c["oi"] * mult)
        by_strike = c.groupby("K")["gex"].sum().sort_index()
        flip = (float(engine_flip)
                if engine_flip is not None and np.isfinite(engine_flip) else np.nan)
        if np.isnan(flip):
            # A NaN flip blanks the dashboard banner and nulls latest['market_gamma']
            # downstream — make it loud in the Actions summary. Bare line-start print:
            # a logger prefix would make GitHub silently drop the annotation.
            print("::warning title=gex flip NaN::SPX gamma-flip unresolved (engine "
                  f"grid found no zero crossing; net_gex_bn={by_strike.sum() / 1e9:.1f})"
                  " — flip_strike/spot_vs_flip_pct NaN, dealer-gamma banner will be "
                  "blank", flush=True)
        svf = (spot / flip - 1) * 100 if not np.isnan(flip) else np.nan
        return pd.DataFrame({"net_gex_bn": [by_strike.sum() / 1e9], "flip_strike": [flip],
                             "spot": [spot], "spot_vs_flip_pct": [svf]},
                            index=[pd.Timestamp(date.today())])

    @staticmethod
    def _row(summ: dict) -> pd.DataFrame:
        """1-row/day summary frame (the per-strike detail is re-fetched at build)."""
        keep = ("spot", "net_gex_bn", "net_vex", "net_cex", "gamma_flip",
                "dist_to_flip_pct", "gamma_regime", "magnet_up", "magnet_down",
                "charm_anchor", "charm_net_sign", "iv30", "put_call_oi_ratio",
                "max_pain", "n_strikes", "tier")
        return pd.DataFrame({k: [summ.get(k)] for k in keep},
                            index=[pd.Timestamp(date.today())])

    def _collect_symbol(self, sym: str, gcfg: dict, ecfg: dict,
                        out: dict[str, pd.DataFrame], retries: int | None = None) -> None:
        from engine.gex_engine import compute_gex     # lazy — keep the collector light
        chain, spot = self._chain(sym, retries=retries)
        summ = compute_gex(chain, spot, cfg={**ecfg, "r": gcfg.get("r", 0.043),
                                             "q": GEX_Q.get(sym, 0.0)})
        out[f"gex_{sym.lstrip('_')}"] = self._row(summ)
        if sym == "_SPX":
            out["gex"] = self._legacy_spx(chain, spot, gcfg,
                                          engine_flip=summ.get("gamma_flip"))

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        gcfg = self.cfg["gex"]
        symbols = gcfg.get("symbols", DEFAULT_GEX_SYMBOLS)
        ecfg = {k: gcfg[k] for k in ("contract_multiplier", "pct_move",
                                     "strike_window_pct", "max_expiry_days") if k in gcfg}
        out: dict[str, pd.DataFrame] = {}
        failed: list[str] = []
        for sym in symbols:
            try:
                self._collect_symbol(sym, gcfg, ecfg, out)
            except Exception as e:  # noqa: BLE001 — partial coverage still useful
                failed.append(sym)
                log.warning("gex: %s failed: %s", sym, e)
        # A chain snapshot is unrecoverable after tonight — spend the cooldown ladder on
        # single-attempt recovery sweeps before accepting a permanent per-symbol hole.
        # Each pass re-sweeps only what is STILL failing and stops as soon as the set
        # empties, so a clean night never sleeps and the 07-27 shape (recovered on the
        # first 60s pass) never reaches the 300s pass. Only the ≥3-min 07-30 window does.
        for cooldown in CHAIN_429_COOLDOWN_LADDER_S:
            if not failed:
                break
            time.sleep(cooldown)
            still: list[str] = []
            for sym in failed:
                try:
                    self._collect_symbol(sym, gcfg, ecfg, out, retries=1)
                    log.info("gex: %s recovered on the %.0fs post-cooldown sweep",
                             sym, cooldown)
                except Exception as e:  # noqa: BLE001 — coverage tripwire makes this loud
                    still.append(sym)
                    log.warning("gex: %s failed after the %.0fs cooldown too: %s",
                                sym, cooldown, e)
            failed = still
        # #3721 weekend-row gate stays the LAST thing this adapter does, so the
        # post-cooldown recovery sweep (#4014) is gated too — a Saturday recovery row
        # is as fabricated as a Saturday first-pass row.
        return _session_gated(out, "GexAdapter")


# ------------------------------------------------------------------ session coverage
# Pinned IN CODE, not derived from config (the ^GSPC lesson, collectors/yahoo): a
# config-derived expectation goes blind the moment a name falls out of the list.
# Dropping a symbol from collection is an explicit decision — update this too.
CHAIN_FAMILY_SERIES: tuple[str, ...] = (
    "putcall", "gex", *(f"gex_{s.lstrip('_')}" for s in DEFAULT_GEX_SYMBOLS))

# The board/alert-critical backbone: engine/conditions reads putcall, build_site + the
# gex_flip_cross alert read the legacy gex frame, the regime panel leans on gex_SPX.
# All three missing the same session = the 2026-07-27 whole-collection shape.
CORE_CHAIN_SERIES: tuple[str, ...] = ("putcall", "gex", "gex_SPX")

# Sessions permanently absent from the store, with why. The delayed-quotes endpoint
# serves only the LIVE snapshot — a missed session cannot be honestly backfilled, so
# the disclosure entry here is the accepted terminal state (never fabricate a row).
# The coverage tripwire stays loud about an unregistered hole until it is either
# healed (impossible for chains) or explicitly registered here with its cause.
#
# TWO CAUSES LIVE IN HERE, AND THEY HAVE DIFFERENT FIXES (2026-08-06 postmortem).
# The 07-27 entry taught every later reader to blame the CBOE CDN, and for a week
# nobody found the bigger half: MOST of the lost sessions were collected perfectly
# and then thrown away by our own pipeline.
#   * SOURCE loss  — the CDN 429'd the chain endpoint through the retry window.
#     Nothing was ever on disk. Unfixable after the fact; mitigate with retries.
#   * COMMIT loss  — the adapter wrote the row, the collect job then died at a LATER
#     step, `commit data` was skipped, and the next night's `actions/checkout` reset
#     the tracked parquet. The row EXISTED and we deleted it.
# Telling them apart is one command — the store advances only on nights that
# committed, so compare the run log's `cboe_putcall -> ok (1 rows, last <date>)`
# against `git log --format='%ad %s' --date=short -- data/cboe/putcall.parquet`.
# "ok" in the log with no commit that evening is COMMIT loss, not a CBOE outage.
#
# The registry is date-keyed and DATE-GLOBAL — one entry silences every series for that
# date — so each string carries the per-series nuance the key cannot.
KNOWN_PERMANENT_GAPS: dict[date, str] = {
    date(2026, 7, 27): "SOURCE loss — CBOE CDN rate-limited (HTTP 429) the delayed_quotes chain "
                       "endpoint through the whole retry window of the 07-27 evening "
                       "collect (run 30314534128): putcall + gex/gex_SPX/gex_SPY/"
                       "gex_MSFT lost the session; snapshots are unrecoverable.",
    date(2026, 7, 30): "SOURCE loss — CBOE CDN held a continuous HTTP 429 on delayed_quotes for ≥3 "
                       "minutes (23:42:32Z→23:45:33Z+, run 30590845976), outlasting "
                       "both the 3/6/12s per-request ladder and the single 60s "
                       "cooldown of the day: putcall + gex/gex_SPX/gex_SPY/gex_QQQ/"
                       "gex_IWM lost the session (single names landed once the window "
                       "lifted mid-sweep). PARTIALLY HEALED: gex_SPY/gex_QQQ/gex_IWM "
                       "were cross-filled from the same-session polygon archive by "
                       "scripts/backfill_cboe_gex_20260730_from_polygon.py (same "
                       "engine.gex_engine.compute_gex, identical 16-col schema; the "
                       "polygon accrual stamps UTC now(), so the 07-30 session is the "
                       "row stamped 07-31 — pinned by spot==yahoo 07-30 close). "
                       "putcall + gex + gex_SPX STAY LOST: no archive anywhere carries "
                       "SPX options, and putcall is all-or-nothing on its _SPX leg. "
                       "This 429 is what escalated the cooldown to a 60s/300s ladder.",
    date(2026, 7, 31): "SOURCE loss — same 429 flap shape later in the 07-31 evening sweep (run "
                       "30673008620): gex_META + gex_MSFT lost the session; the other "
                       "ten series landed. NOT recoverable — the polygon archive has "
                       "no 07-31 row at all: that Friday-evening accrual crossed into "
                       "Saturday 2026-08-01 UTC and build_polygon_gex's is_session "
                       "gate correctly refused to stamp a non-session date.",
    date(2026, 8, 3): "COMMIT loss — scripts/collect.py crashed mid-run (run 30862763261): "
                      "AttributeError 'NYGamingAdapter' object has no attribute "
                      "'fetch_result_status', then 'expected_failure'. The night's "
                      "single checkpoint commit never ran, so CBOE parquet rows that "
                      "had ALREADY been fetched were discarded by the next checkout — "
                      "all 12 chain series lost the session. Crash class fixed by "
                      "#4534 (duck-typed run_adapter); the commit-loss WINDOW itself "
                      "closed by #4731 (split checkpoint — market data commits before "
                      "the capital-structure chain can fail). No archive: the polygon "
                      "rows died in the same dead commit.",
    date(2026, 8, 4): "COMMIT loss — compile_capital_structure_events raised ManifestIdentityError "
                      "(source ledger row 0 manifest mismatch, run 30960328285) → step "
                      "exit 1 → the same single-checkpoint commit loss as 08-03: all 12 "
                      "chain series lost the session. Fixed by #4600; commit-loss "
                      "window closed by #4731. No archive (same dead commit).",
    date(2026, 8, 5): "COMMIT loss — compile_capital_structure_document_terms exited 2 degraded on a "
                      "mass 'SEC complete-submission must contain exactly 1 canonical "
                      "SEC-HEADER opener line(s)' (run 31056495943) → the same commit "
                      "loss: all 12 chain series lost the session. Fixed by #4640; "
                      "commit-loss window closed by #4731. No archive (same dead "
                      "commit) — the polygon row stamped 08-06 is a LIVE intraday "
                      "snapshot, not the 08-05 close (its spot matches no 08-05 close), "
                      "so it is not an honest cross-fill source.",
}


def check_chain_session_coverage(lookback_sessions: int = 5) -> list[dict]:
    """Store-level NYSE-session coverage tripwire for the delayed-chain family.

    The 2026-07-27 miss was invisible to every existing layer: putcall FAILED but
    graceful degradation kept the run green; gex returned 7/10 symbols so the source
    was 'ok' and detect_stale_series (which only sees RETURNED frames) had nothing to
    flag; the store-level cor/vol tripwire does not cover this family; and every
    tail-age check went green again the next evening when 07-28 landed — a one-day
    hole is permanently invisible to any last-obs check after one day. So this check
    asks for MEMBERSHIP of each of the last `lookback_sessions` expected NYSE sessions
    (weekend/holiday-dated snapshot rows can never mask a missing session date), and a
    miss stays loud for a week rather than one silent evening. Warn/alert only — it
    writes run_status stale_series entries and prints line-start ::warning/::error
    annotations (bare print, NEVER via a logger — the prefixing format would make
    GitHub drop them); it never fails the lane."""
    from collectors.base import _write_stale_series
    from lib import nyse_calendar, store

    expected = nyse_calendar.expected_last_session()
    window = nyse_calendar.sessions_between(
        expected - timedelta(days=3 * lookback_sessions + 10), expected)[-lookback_sessions:]
    problems: list[dict] = []
    missing_by_series: dict[str, list[date]] = {}
    for series in CHAIN_FAMILY_SERIES:
        df = store.read("cboe", series)
        if df is None:
            problems.append({"group": "cboe", "series": series, "rows": 0,
                             "last_obs": None, "cadence_days": 1, "age_days": None,
                             "reason": "missing from store"})
            missing_by_series[series] = list(window)
            log.warning("chain coverage: %s — missing from store", series)
            continue
        have = {pd.Timestamp(t).date() for t in df.index}
        if not have:
            problems.append({"group": "cboe", "series": series, "rows": 0,
                             "last_obs": None, "cadence_days": 1, "age_days": None,
                             "reason": "empty store frame"})
            missing_by_series[series] = list(window)
            log.warning("chain coverage: %s — empty store frame", series)
            continue
        first = min(have)
        missing = [s for s in window
                   if s not in have and s not in KNOWN_PERMANENT_GAPS
                   and s >= first]  # a young series owes only its own era
        if missing:
            last = max(have)
            reason = (f"missing NYSE session row(s) {', '.join(map(str, missing))} "
                      f"in the last {lookback_sessions} sessions (last obs {last})")
            problems.append({"group": "cboe", "series": series, "rows": len(df),
                             "last_obs": str(last), "cadence_days": 1,
                             "age_days": (expected - last).days, "reason": reason})
            missing_by_series[series] = missing
            log.warning("chain coverage: %s — %s", series, reason)
    if problems:
        _write_stale_series(problems)
        affected = ", ".join(f"{s}[{','.join(map(str, d))}]"
                             for s, d in missing_by_series.items())
        print(f"::warning title=cboe-session-miss::{len(problems)} of "
              f"{len(CHAIN_FAMILY_SERIES)} cboe delayed-chain series missing session "
              f"rows: {affected} — chain snapshots are unrecoverable; investigate "
              f"TODAY or register the gap in collectors/cboe.py KNOWN_PERMANENT_GAPS. "
              f"FIRST check WHICH failure this is, because they have different fixes: "
              f"grep that evening's collect log for `cboe_putcall -> ` / `cboe_gex -> `. "
              f"`-> ok` means the row was COLLECTED and the pipeline then dropped it "
              f"(the collect job died before `commit data`, and the next checkout reset "
              f"the parquet) — look at the job's failing STEP, not at CBOE. `-> failed` "
              f"or `gex: <sym> failed: HTTP 429` is a genuine source loss. "
              f"For a gex_<name> hole ONLY: if data/polygon_gex/summary_<name>.parquet "
              f"carries the same session (same engine, identical schema — note the "
              f"accrual stamps UTC now(), so an evening session usually sits in the "
              f"row stamped session+1), it can be honestly cross-filled — see "
              f"scripts/backfill_cboe_gex_20260730_from_polygon.py for the pattern "
              f"(verify spot against the yahoo close for that session before copying; "
              f"never fabricate a row)", flush=True)
        core_missing = set.intersection(
            *(set(missing_by_series.get(s, [])) for s in CORE_CHAIN_SERIES))
        if core_missing:
            days = ", ".join(map(str, sorted(core_missing)))
            print(f"::error title=cboe-session-miss::whole-family miss — putcall + gex "
                  f"+ gex_SPX all lack session(s) {days} (the 2026-07-27 shape: every "
                  f"board-critical series losing the SAME session, from either a CDN "
                  f"429 or a skipped `commit data` — see KNOWN_PERMANENT_GAPS for how "
                  f"to tell them apart); the board regime panel, conditions P/C and "
                  f"the gex_flip_cross alert are all running without that session",
                  flush=True)
    else:
        log.info("chain coverage: all %d series carry the last %d sessions "
                 "(through %s)", len(CHAIN_FAMILY_SERIES), lookback_sessions, expected)
    return problems
