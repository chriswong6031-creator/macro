"""Prophet US miss-audit + conversion telemetry — nightly MEASUREMENT, ZERO authority.

Productionizes ``research/prophet_us_audit/runner_exclusion_audit.py`` (frozen results:
``research/prophet_us_audit/RESULTS_2026-08-03.md``) as the nightly instrument the Prophet US
trend-intelligence program grades itself against
(``research/PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`` §W0).

WHAT IT MEASURES (nightly, over the committed S&P-1500 close caches)

  A. RUNNER EXCLUSION — the top-150 names by 63-session return (and the top-50 by 21-session):
     for each, whether it is eligible TODAY and, when it is not, WHICH leg excluded it
     (``not_topped_veto(stoch_ob+stoch_bear+macd_bear)`` / ``rsi_cap_on_fresh_cross`` /
     ``freshness_expired`` / ``no_recent_3d_stoch_cross`` / ``no_cross``), plus how many of the
     trailing 63 sessions it WAS eligible and the date it first became eligible in that window.

  B. SIGHTING -> PLAN CONVERSION — of the runners the engine actually saw (>=1 eligible day in
     the window), how many ever became a Prophet plan (``site/prophet/plans/*.json``, by asset).

  C. THEME-REPRESENTATION LATENCY — for the top-5 themes by ``emerging_score`` in
     ``site/marketdata/subsector_rotation.json``, how many members are present in the
     ``us_standouts`` buy / ran / leaders lanes today.

  D. SUMMARY — universe n, eligible-today n (both bases), excluder histogram, and the
     runner-sector vs eligible-sector histograms that show the mismatch.

  F. BASKET-GRAIN MISSES — "the gold question", automated. Sections A-C ask whether the
     engine saw a NAME. This one asks the altitude above it: did a whole THEME run with
     nobody on the board? For every curated US basket (``data/baskets/membership.json``,
     point-in-time dated membership) the equal-weight 5d and 10d member returns, that
     10d return's percentile inside the basket's OWN trailing-252-session 10d history,
     and how many of its members are on any visible board lane. A basket in its own top
     decile with ZERO members visible is a named miss row. Motivated by the 2026-08-05
     missed-ignitions audit: ``b-gold_miners`` printed Trough/BUY in the sector-cycle
     forward log while the Act board had it on reduce/avoid, and no instrument anywhere
     counted "this basket ignited and we showed nobody".

  E. NAME_SCORE SCORECARD — the forward grade of the per-name POTENTIAL score
     (``engine/name_score_grader.py`` → ``data/name_score/us_calls.parquet``): rank-IC at
     21d/63d with the per-date cross-section behind it, the buy-tier hit rate, and P@k
     against each date's own graded cross-section. Wired here because the score is LIVE and
     LOAD-BEARING while unmeasured — the board's displayed ``conviction.score`` IS
     name_score's ``potential_score`` (a backward-compat overwrite in
     ``scripts/build_stock_library.py``) — and the grader that already runs nightly was
     consumed by NOTHING. Read-only telemetry: no threshold, no alarm, no gate; every null
     is printed with a plain reason (roadmap
     ``research/PROPHET_US_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md`` §4.4 action 1).

  F. PRIORITY_SCORE SCORECARD — the forward grade of the ``us_prophet_v1`` PRIORITY score,
     over the FULL analyzed universe.  ``engine/us_prophet_grades.py`` grades every stamped
     Context Vector row (~1,579 names a night, not the ~12 that become plans) at H=10/21
     sessions excess-vs-SPY; this block joins those outcomes to the score the system gave
     each name that night and reports rank-IC, P@k (k=1/5/10/25), a decile lift table and
     the per-decile loser rate — the operator's question (2026-08-05) in its bluntest form:
     "it would be a disaster if high-scored names underperform."  Because EVERY name is
     graded, a pick's hit is judged against that night's whole universe rather than against
     the picks alone — something the plan-only record could never do.  Read-only telemetry:
     no threshold, no alarm, no gate; coverage is disclosed (the builder computes the
     itemized legs on the buy lane only, so most stamped rows carry no score, and a missing
     score is a null, never a zero).  Masterplan
     ``research/PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`` §W7.3.

BASES (two, named — they are NOT interchangeable)

  ``tier_stream``  the vectorized per-day production twin of ``cascade``, on COMPLETED buckets.
                   T1 is taken via cascade's own raw-3D-cross fallback, so the stream is a
                   self-contained close-only signal. This is the basis for BOTH the runner
                   today-verdict and the 63-session eligibility window, so the two can never
                   disagree about the same day.
  ``cascade``      the scalar last-bar production call, no ``take_active`` (no §7 master
                   supplied here), provisional resample tail. This reproduces the frozen
                   "cascade-eligible today = 38" headline. It is a STRICTER set than the
                   stream basis because raw-3D-cross T1 needs ``take_active``.

  Neither is the live board's basis: the board additionally runs ``signal_gate``'s
  take/pending/early paths over a wider universe (1,579 names incl. Russell + curated extras),
  which is why its ``eligible`` count is larger. The per-runner ``gate_*`` fields carry the
  production ``signal_gate`` verdict + ``near_miss_reason`` for exactly that comparison.

  The excluder ATTRIBUTION reuses ``confluence_tiers``' own helpers and constants
  (``_tf_bars``/``_rsi_macd``/``_stoch_rsi_kd``/``_xup``/``_since``/``_to_daily``/
  ``_ticks_since`` + ``OB``/``OS``/``CONF_W``/``BUY_RSI_MAX``/``FRESH_TICKS``) to name WHICH
  leg is down. It never decides eligibility — that verdict always comes from ``tier_stream``.
  There is no forked copy of the tier math in this module.

ZERO AUTHORITY (house law). This is ops telemetry. Nothing may read it for rank, gate, size,
membership, or any user-facing claim; no module outside ``scripts/run_prophet_miss_audit.py``
and the tests imports it. It writes ONLY ``data/prophet_miss_audit/`` and mutates no other
store on any path.

NIGHTLY-ONLY LAW (nightly is the SOLE advancer of forward ledgers). ``run(advance=True)`` —
reached only via ``python -m scripts.run_prophet_miss_audit --nightly`` — is the only path
that writes the real artifact or appends to the forward log. A default (intraday / re-render /
local) invocation computes and prints, and writes NOTHING; ``--out-dir DIR`` runs the full
write into a scratch dir, never the real store. The forward-log append is idempotent on
``price_through``: a second nightly run on the same price date appends nothing.

DETERMINISM. No wall clock anywhere: every result is keyed by ``price_through`` (the caches'
own last bar). Two runs over the same caches produce byte-identical artifacts.

FAIL-SOFT, NEVER SILENT. A missing/unreadable optional input degrades to nulls AND appends a
row to the artifact's ``degraded`` list naming the path and the reason. A missing close cache
is fatal (there is nothing to measure).

Run (nightly / DAG):   python -m scripts.run_prophet_miss_audit --nightly
Run (safe local test): python -m scripts.run_prophet_miss_audit --out-dir /tmp/pma
Run (dry, no writes):  python -m scripts.run_prophet_miss_audit
"""
from __future__ import annotations

import glob
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from engine import confluence_tiers as ct
from engine import grading
from engine import name_score_grader as nsg
from engine import signal_gate as sg
from engine.confluence_tiers import (
    BUY_RSI_MAX, CONF_W, FRESH_TICKS, OB, OS,
    _rsi_macd, _since, _stoch_rsi_kd, _tf_bars, _ticks_since, _to_daily, _xup,
)
from engine.technicals import rsi
from lib import store

ROOT = Path(__file__).resolve().parents[1]

SCHEMA = "prophet_miss_audit/v1"

# universe: the three committed breadth close caches (S&P 500 / 400 / 600)
UNIVERSE_GROUPS = ("breadth", "midcap_breadth", "smallcap_breadth")
SECTORS_PARQUET = "data/breadth/ticker_sectors.parquet"

PLANS_GLOB = "site/prophet/plans/*.json"
STANDOUTS_JSON = "site/factordata/us_standouts.json"
ROTATION_JSON = "site/marketdata/subsector_rotation.json"
THEME_PIT_JSONL = "data/themes_heatmap/subsector_perf_history.jsonl"

# Basket-grain layer (section F).
BASKET_MEMBERSHIP_JSON = "data/baskets/membership.json"
#: WHICH STORE, AND WHY. The audit's own universe is the three breadth close caches,
#: and those cannot answer this question: they are the S&P 1500, while the baskets that
#: ignited in the motivating case are full of names outside it (ASTS, RKLB, LUNR). Of
#: the 691 currently-live basket members, ``data/baskets/ohlcv`` carries 690 and
#: ``data/baskets/extras.parquet`` 676 — and the per-ticker store also runs from 2014
#: rather than 2023, which the trailing-252-session reference window needs. It is also
#: the store the basket machinery itself reads (``engine.basket_index``), so a basket's
#: return here and on the baskets page come from the same bars.
BASKET_OHLCV_DIR = "data/baskets/ohlcv"

ARTIFACT_REL = "data/prophet_miss_audit/latest.json"
FORWARD_LOG_REL = "data/prophet_miss_audit/forward_log.jsonl"

# --- §4.5 SCAN TIER (operator-ratified 2026-08-05) ---------------------------------
# The runner scan above covers the S&P-1500 close caches. An off-index runner
# (CRCL, and the FNV/FSM/EXK/AG/SBSW receipts) is not merely un-admitted there —
# it is structurally INVISIBLE, because it is not in the frame at all. The scan
# tier widens the SEEING to a liquidity-floored slice of the whole-market daily
# store, so such a name is at minimum SEEN and counted missed, with its excluder
# named. Admission is untouched: nothing here feeds rank, gate, size or intake.
#
# The scan pass needs data/massive_stock_day (617 MB, R2-canonical) which the
# ENGINE job does not restore — so it runs in its own post-engine lane
# (scripts/run_us_scan_tier.py) and writes its own artifact. build_audit READS
# that artifact's summary rather than recomputing it, so the W0 document carries
# scan-tier coverage at no cost to the engine job, with its own asof disclosed.
SCAN_ARTIFACT_REL = "data/prophet_scan_tier/latest.json"
SCAN_FORWARD_LOG_REL = "data/prophet_scan_tier/forward_log.jsonl"
SCAN_SCHEMA = "prophet_scan_tier/v1"
SCAN_TOP_N = 150         # top runners by 63-session return within the scan tier

TOP63_N = 150          # top runners by 63-session return
TOP21_N = 50           # top fast movers by 21-session return
LOOKBACK = 63          # eligibility window, in sessions
THEME_TOP_N = 5        # themes graded for representation latency
STANDOUT_LANES = ("buy", "ran", "leaders")

# --- F. basket-grain misses ---------------------------------------------------
#: Every lane a member can be VISIBLE on. `featured` is a flag inside `buy`, not a
#: lane, so it needs no entry: a featured name is a buy row and is already counted.
#: `laggards` is deliberately absent — it is the board's "these are the weak ones"
#: shelf, so a name appearing there is not the basket being surfaced as opportunity.
BASKET_BOARD_LANES = ("buy", "watch", "leaders", "ran")
BASKET_EW_HORIZONS = (5, 10)     # the two EW member-return windows reported
BASKET_MISS_HORIZON = 10         # the horizon the top-decile test runs on
BASKET_HISTORY = 252             # trailing sessions of own-history for the percentile
BASKET_TOP_DECILE = 0.90         # >= this percentile in own history = "ignited"
BASKET_MIN_MEMBERS = 3           # below this an EW read is one or two names, not a basket
#: Minimum 10d observations in the reference window. Well under BASKET_HISTORY so a
#: basket seeded mid-window still reports, but high enough that "top decile" is not a
#: statement about eleven overlapping numbers.
BASKET_MIN_HISTORY = 60
#: Member-coverage floor below which a basket's read PAGES rather than merely
#: disclosing (the masterplan's W-B threshold). Above it a shortfall is structural and
#: sits in `degraded` without an annotation: one delisted-or-unfetched member out of
#: twelve is a fact worth printing, not an alarm worth firing every night for a year.
#: Below it the read is the D12 failure — gold_miners scored on 1 of 12 members — and
#: that must be impossible to miss.
BASKET_COVERAGE_WARN = 0.60

# annotation thresholds (ops alarms only — never a gate)
CONVERSION_WARN = 0.05          # sighting -> plan conversion below this warns
NEVER_ELIGIBLE_WARN = 0.40      # share of top-63d runners with ZERO eligible days

# --- E. name_score scorecard (read-only mirror; NO alarm threshold lives here) ---
NAME_SCORE_MARKET = "US"
NAME_SCORE_LEDGER_REL = "data/name_score/us_calls.parquet"
PK_K = (1, 3, 5, 10)     # the top-k depths reported
# A P@k date needs a graded cross-section at least this wide, so a date on which the
# forward join resolved a handful of names cannot masquerade as a ranking result.
# STATED, not tuned; it admits dates, it gates nothing.
PK_MIN_XS = 20
# Disclosure rule (not a gate): a horizon graded on fewer than this many IC dates is
# marked thin so no reader mistakes a two-date sample for a measurement.
THIN_MIN_IC_DATES = 5

# --- F. priority_score scorecard (read-only mirror of the full-population grade store) ---
# PROPHET US §W7.3. The score whose robustness the operator asked about (2026-08-05) is the
# us_prophet_v1 priority score; the grade store now carries an outcome for EVERY stamped
# name, so this block can ask both "is the ordering right?" (rank-IC / P@k / deciles over
# the scored rows) and "does the board beat the universe at all?" (the population leg).
PRIORITY_GRADES_REL = "data/us_prophet_rank/grades/YYYY-MM/YYYY-MM-DD.parquet"
PRIORITY_CANDIDATES_REL = "data/us_prophet_rank/candidates/YYYY-MM.parquet"
#: Mirrors engine.us_prophet_grades.HORIZONS — imported there, restated here only as the
#: forward-log row's column set (the log is flat and its columns must be stable).
PRIORITY_HORIZONS = (10, 21, 42, 63)
PRIORITY_PK_K = (1, 5, 10, 25)   # the depths the ranked all-picks surface actually shows
# A decile table needs a cross-section wide enough that a decile is not one name. STATED,
# not tuned; it excludes dates from a table, it gates nothing.
PRIORITY_DECILE_MIN_XS = 20
# Below this many scored rows the horizon is summarised as accruing rather than measured.
PRIORITY_MIN_SCORED = 20
# A lane's forward read is printed only once it has this many graded rows behind it.
PRIORITY_MIN_LANE_N = 10

# --- G. entry_status re-measurement (ANTICIPATION §6.6) ---------------------------------
# The entry-value ladder's evidence loop. Named here only so a degraded row can name its
# input; every definition, threshold and shape lives in engine.us_entry_status_remeasure,
# which is where the block is computed.
ENTRY_STATUS_LEDGER_REL = "data/us_board_ledger/retro_grades.parquet"

# excluder vocabulary (stable strings — the histogram keys downstream reads)
EXC_ELIGIBLE = "ELIGIBLE"
EXC_INSUFFICIENT = "insufficient_history"
EXC_RSI_CAP = "rsi_cap_on_fresh_cross"
EXC_FRESHNESS = "freshness_expired"
EXC_NO_RECENT_3D = "no_recent_3d_stoch_cross"
EXC_NO_CROSS = "no_cross"
VETO_LEGS = ("stoch_ob", "stoch_bear", "macd_bear")     # cascade's not-topped legs, in order


# --------------------------------------------------------------------------- #
# atomic writers (house law: tmp-file + os.replace, never open('w') truncation)
# --------------------------------------------------------------------------- #
def _atomic_write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(doc, ensure_ascii=False, indent=1, default=str, sort_keys=False)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, path)


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str, sort_keys=False) + "\n")


def _num(x: Any) -> Any:
    """JSON-safe scalar: numpy -> python, NaN/inf -> None."""
    if x is None:
        return None
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        f = float(x)
        return f if np.isfinite(f) else None
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #
def load_universe(root: Path = ROOT) -> tuple[pd.DataFrame, dict[str, str], list[dict]]:
    """Wide close frame over the three breadth caches + a ticker->sector map.

    Reindexes every cache onto the LONGEST index (the mid/small caches carry ~3y, the large-cap
    cache ~1y) and drops duplicate columns, keeping the first — same construction the frozen
    audit used, so the universe count is comparable night to night. Raises when no cache is
    readable: there is nothing to measure. A missing sector map degrades to "?" sectors.
    """
    degraded: list[dict] = []
    frames: list[pd.DataFrame] = []
    for grp in UNIVERSE_GROUPS:
        p = root / "data" / grp / "_closes_cache.parquet"
        try:
            frames.append(pd.read_parquet(p))
        except Exception as exc:  # noqa: BLE001 — fail-soft per source, disclosed
            degraded.append({"input": str(p.relative_to(root)), "severity": "unexpected",
                             "reason": f"unreadable: {exc} — universe is missing this cap band"})
    if not frames:
        raise FileNotFoundError(
            "no readable close cache under data/{%s}/_closes_cache.parquet"
            % ",".join(UNIVERSE_GROUPS)
        )
    idx = max((f.index for f in frames), key=len)
    wide = pd.concat([f.reindex(idx) for f in frames], axis=1)
    wide = wide.loc[:, ~wide.columns.duplicated()]
    if not isinstance(wide.index, pd.DatetimeIndex):
        wide.index = pd.to_datetime(wide.index)
    wide = wide.sort_index()

    sector: dict[str, str] = {}
    sp = root / SECTORS_PARQUET
    try:
        sec = pd.read_parquet(sp)
        sector = dict(zip(sec["ticker"], sec["sector"]))
    except Exception as exc:  # noqa: BLE001
        degraded.append({"input": SECTORS_PARQUET, "severity": "unexpected",
                         "reason": f"unreadable: {exc} — sector histograms collapse to '?'"})
    return wide, sector, degraded


def load_plan_assets(root: Path = ROOT) -> tuple[set[str], list[dict]]:
    """The set of assets that ever became a Prophet plan (site/prophet/plans/*.json)."""
    degraded: list[dict] = []
    assets: set[str] = set()
    files = sorted(glob.glob(str(root / PLANS_GLOB)))
    if not files:
        degraded.append({"input": PLANS_GLOB, "severity": "unexpected",
                         "reason": "no plan files — conversion numerator is 0 by absence, "
                                   "not by measurement"})
        return assets, degraded
    unreadable = 0
    for f in files:
        try:
            doc = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            unreadable += 1
            continue
        a = doc.get("asset")
        if isinstance(a, str) and a:
            assets.add(a)
    if unreadable:
        degraded.append({"input": PLANS_GLOB, "severity": "unexpected",
                         "reason": f"{unreadable}/{len(files)} plan files unreadable — "
                                   "conversion numerator may undercount"})
    return assets, degraded


def _read_json(root: Path, rel: str, degraded: list[dict], why: str) -> dict | None:
    p = root / rel
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        degraded.append({"input": rel, "severity": "unexpected",
                         "reason": f"unreadable: {exc} — {why}"})
        return None


# --------------------------------------------------------------------------- #
# A. excluder attribution — WHICH leg is down (diagnostic overlay, never a verdict)
# --------------------------------------------------------------------------- #
def leg_snapshot(close: pd.Series) -> dict:
    """Last-bar values of every cascade leg, computed with confluence_tiers' OWN helpers.

    This is a DIAGNOSTIC overlay: it reports the leg states the production cascade reads, so an
    exclusion can be named. It never decides eligibility (``attribute_excluder`` takes that from
    ``tier_stream``) and it contains no forked tier math — every helper and constant is imported
    from ``engine.confluence_tiers``. Returns ``{}`` on thin/unusable history.
    """
    c = close.dropna()
    if len(c) < ct.MIN_HISTORY:
        return {}
    if not isinstance(c.index, pd.DatetimeIndex):
        c = c.copy()
        c.index = pd.to_datetime(c.index)
    di = c.index
    last = len(di) - 1

    sm, smk = _tf_bars(c, 2)
    m2, s2 = _rsi_macd(sm)
    mb2 = _xup(m2, s2)

    ss3, sk3 = _tf_bars(c, 3)
    k3, d3 = _stoch_rsi_kd(ss3)
    sb3 = _xup(k3, d3)
    recent3 = _since(sb3) <= CONF_W
    fromos3 = d3.rolling(CONF_W).min() < OS
    r14_3 = rsi(ss3, ct.RSI_LEN)
    m3, s3 = _rsi_macd(ss3)
    mb3 = _xup(m3, s3)

    wk = c.resample("W-FRI").last().dropna()
    wm, ws = _rsi_macd(wk)
    wbull = (wm >= ws).shift(1)

    def td(s, kn, how="ffill"):
        return _to_daily(s, kn, di, how)

    k3_d, d3_d = td(k3, sk3), td(d3, sk3)
    m3_d, s3_d = td(m3, sk3), td(s3, sk3)
    r14_d = td(r14_3, sk3)
    recent3_d = td(recent3.fillna(False), sk3).fillna(False)
    fromos3_d = td(fromos3.fillna(False), sk3).fillna(False)
    mb2_d = td(mb2.fillna(False), smk, "event")
    mb3_d = td(mb3.fillna(False), sk3, "event")
    wbull_d = wbull.reindex(di, method="ffill").fillna(False).astype(bool)

    k3n, d3n = float(k3_d.iloc[last]), float(d3_d.iloc[last])
    m3n, s3n = float(m3_d.iloc[last]), float(s3_d.iloc[last])
    r14n = float(r14_d.iloc[last]) if pd.notna(r14_d.iloc[last]) else np.nan

    # cascade's not-topped legs, verbatim (engine/confluence_tiers.py "NOT-TOPPED" block)
    stoch_ob = bool((k3n >= OB) or (d3n >= OB))
    stoch_bear = bool(k3n < d3n)
    macd_bear = bool(m3n < s3n)
    rsi_block = bool(pd.notna(r14n) and r14n >= BUY_RSI_MAX)

    # tick ages of the two cross families (T1 raw-3D fallback, T2 gated, T2 raw)
    idx3 = np.where(mb3_d.fillna(False).to_numpy())[0]
    t1_ticks = _ticks_since(sk3, di[int(idx3[-1])]) if len(idx3) else None
    confirm3 = (wbull_d | fromos3_d)
    rsi_ok = (r14_d < BUY_RSI_MAX).fillna(False)
    t2_buy = (mb2_d & recent3_d & confirm3 & rsi_ok).fillna(False)
    idx2 = np.where(t2_buy.to_numpy())[0]
    t2_ticks = _ticks_since(smk, di[int(idx2[-1])]) if len(idx2) else None
    # raw 2D cross age IGNORING the vetoes — detects "the cross happened, a veto ate it"
    idx2raw = np.where(mb2_d.fillna(False).to_numpy())[0]
    t2raw_ticks = _ticks_since(smk, di[int(idx2raw[-1])]) if len(idx2raw) else None

    return {
        "stoch_ob": stoch_ob, "stoch_bear": stoch_bear, "macd_bear": macd_bear,
        "rsi_block": rsi_block,
        "k3": round(k3n, 1) if np.isfinite(k3n) else None,
        "d3": round(d3n, 1) if np.isfinite(d3n) else None,
        "rsi3d": (round(r14n, 1) if pd.notna(r14n) else None),
        "t1_ticks": t1_ticks, "t2_ticks": t2_ticks, "t2raw_ticks": t2raw_ticks,
        "recent3": bool(recent3_d.iloc[last]),
    }


def attribute_excluder(close: pd.Series, *, eligible_today: bool) -> dict:
    """Name the DOMINANT excluder for a name that is not eligible today.

    ``eligible_today`` is the production verdict (``tier_stream``'s last row) — this function
    only explains it. Evaluation order mirrors the cascade's own: the not-topped veto short-
    circuits everything (``cascade`` returns blank the moment it trips), then the RSI cap on an
    otherwise-fresh 2D cross, then freshness expiry, then the missing legs.

    Returns ``{excluder, excluder_family, veto_legs, **leg_snapshot}``. ``excluder`` is
    ``"ELIGIBLE"`` when the name is eligible; ``excluder_family`` collapses the parametrized
    veto string to ``"not_topped_veto"`` so histograms can be read either way.
    """
    legs = leg_snapshot(close)
    if not legs:
        return {"excluder": EXC_INSUFFICIENT, "excluder_family": EXC_INSUFFICIENT,
                "veto_legs": []}
    fired = [n for n in VETO_LEGS if legs[n]]
    out = dict(legs)
    out["veto_legs"] = fired
    if eligible_today:
        out["excluder"] = EXC_ELIGIBLE
        out["excluder_family"] = EXC_ELIGIBLE
        return out
    if fired:
        out["excluder"] = "not_topped_veto(" + "+".join(fired) + ")"
        out["excluder_family"] = "not_topped_veto"
        return out
    t1t, t2r = legs["t1_ticks"], legs["t2raw_ticks"]
    if legs["rsi_block"] and t2r is not None and t2r <= FRESH_TICKS:
        exc = EXC_RSI_CAP
    elif (t1t is not None and t1t > FRESH_TICKS) or (t2r is not None and t2r > FRESH_TICKS):
        exc = EXC_FRESHNESS
    elif not legs["recent3"]:
        exc = EXC_NO_RECENT_3D
    else:
        exc = EXC_NO_CROSS
    out["excluder"] = exc
    out["excluder_family"] = exc
    return out


# --------------------------------------------------------------------------- #
# B. eligibility window — production tier_stream, one pass per name
# --------------------------------------------------------------------------- #
def eligibility_window(close: pd.Series, lookback: int = LOOKBACK) -> dict:
    """Trailing-``lookback``-session eligibility record for one name, from ``ct.tier_stream``.

    ``eligible_today`` is the stream's LAST row — the same object the window counts, so the
    "eligible today" verdict and the window can never disagree about the same session.
    Returns nulls (never raises) when the stream is empty (thin history).
    """
    st = ct.tier_stream(close)
    if st.empty:
        return {"eligible_today": False, "tier_today": None, "days_eligible": None,
                "first_eligible": None, "fwd_ret_from_first_pct": None, "tiers_seen": []}
    tail = st.tail(lookback)
    elig = tail["eligible"].to_numpy().astype(bool)
    out = {
        "eligible_today": bool(st["eligible"].iloc[-1]),
        "tier_today": st["tier"].iloc[-1],
        "days_eligible": int(elig.sum()),
        "first_eligible": None,
        "fwd_ret_from_first_pct": None,
        "tiers_seen": [],
    }
    if out["days_eligible"]:
        first = tail.index[int(np.flatnonzero(elig)[0])]
        cc = close.dropna()
        try:
            px0 = float(cc.loc[:first].iloc[-1])
            pxn = float(cc.iloc[-1])
            out["fwd_ret_from_first_pct"] = round((pxn / px0 - 1) * 100, 2)
        except (IndexError, ZeroDivisionError, ValueError):
            out["fwd_ret_from_first_pct"] = None
        out["first_eligible"] = str(pd.Timestamp(first).date())
        out["tiers_seen"] = sorted({t for t in tail.loc[elig, "tier"] if t})
    return out


def scan_windows(px: pd.DataFrame, tickers, lookback: int = LOOKBACK) -> dict[str, dict]:
    """``eligibility_window`` per ticker. One ``tier_stream`` pass per name (~50ms each).

    Deliberately scoped to the RUNNER set, not the whole universe: the universe-wide
    eligible-today set comes from the cheaper-per-name ``cascade`` pass, and streaming all
    ~1,500 names would double the nightly cost for a number no gate reads.
    """
    return {t: eligibility_window(px[t], lookback) for t in tickers}


# --------------------------------------------------------------------------- #
# B2. sighting -> plan conversion
# --------------------------------------------------------------------------- #
def conversion_join(runner_rows: list[dict], plan_assets: set[str]) -> dict:
    """Sighting -> plan conversion over the runner rows.

    SIGHTED = the engine actually saw the name: >=1 eligible day in the trailing window (a name
    with ``days_eligible is None`` was never measurable and is excluded from the denominator,
    not counted as a miss). CONVERTED = that ticker is the ``asset`` of some Prophet plan.
    ``rate`` is None when nothing was sighted — an empty denominator is not a 0% conversion.
    """
    sighted = [r for r in runner_rows if (r.get("days_eligible") or 0) >= 1]
    converted = [r["ticker"] for r in sighted if r["ticker"] in plan_assets]
    unconverted = [r["ticker"] for r in sighted if r["ticker"] not in plan_assets]
    never_sighted = [r["ticker"] for r in runner_rows if r.get("days_eligible") == 0]
    return {
        "sighted_n": len(sighted),
        "converted_n": len(converted),
        "rate": (round(len(converted) / len(sighted), 4) if sighted else None),
        "converted": sorted(converted),
        "never_sighted_n": len(never_sighted),
        "unconverted_top": unconverted[:25],
        "plan_universe_n": len(plan_assets),
    }


# --------------------------------------------------------------------------- #
# C. theme-representation latency
# --------------------------------------------------------------------------- #
def _theme_members(rotation: dict) -> dict[str, list[str]]:
    """theme name -> sorted member tickers (union over that theme's subsectors)."""
    out: dict[str, set[str]] = {}
    for sub in rotation.get("subsectors") or []:
        theme = sub.get("theme")
        if not theme:
            continue
        bucket = out.setdefault(theme, set())
        for m in sub.get("members") or []:
            t = m.get("t") if isinstance(m, dict) else m
            if isinstance(t, str) and t:
                bucket.add(t)
    return {k: sorted(v) for k, v in out.items()}


def _disclose_theme_top5_gap(root: Path, degraded: list[dict]) -> None:
    """Disclose WHY ``days_since_top5_entry`` is null. Always null in this wave — by design.

    Recovering a theme's top-5 ENTRY DATE needs a PIT archive that ranks the SAME unit (theme)
    by the SAME field (``emerging_score``) the live artifact ranks by. ``data/themes_heatmap/
    subsector_perf_history.jsonl`` archives per-SUBSECTOR performance (1D/1W/1M/… returns)
    keyed by ``asof`` and carries no theme-level rank, so the date is not derivable from it
    without inventing an aggregation across a different unit. The honest output is a printed
    null plus this disclosure — never an approximation wearing the theme's label. Masterplan W2
    owns the theme-level PIT rank archive; building it is not this wave.
    """
    p = root / THEME_PIT_JSONL
    head: dict | None = None
    if p.exists():
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    head = json.loads(line)
                    break
        except Exception as exc:  # noqa: BLE001
            degraded.append({"input": THEME_PIT_JSONL, "severity": "unexpected",
                             "reason": f"unreadable: {exc} — theme days_since_top5_entry null"})
            return
    unit = "absent" if head is None else "+".join(sorted(head.keys()))
    degraded.append({
        "input": THEME_PIT_JSONL, "severity": "structural",
        "reason": f"carries {unit} — no theme-level emerging_score rank, so the top-5 entry "
                  "date is not recoverable from this archive; days_since_top5_entry reported "
                  "null rather than approximated from the subsector unit (masterplan W2 owns "
                  "the theme-level PIT rank archive)",
    })


def theme_representation(root: Path, standouts: dict | None, rotation: dict | None,
                         degraded: list[dict], top_n: int = THEME_TOP_N) -> dict:
    """Top-``top_n`` themes by ``emerging_score`` and how many members are on the board today."""
    if not rotation:
        return {"basis": None, "themes": [], "available": False}
    themes = [t for t in (rotation.get("themes") or []) if isinstance(t, dict)]
    if not themes:
        degraded.append({"input": ROTATION_JSON, "severity": "unexpected",
                         "reason": "no themes[] block — theme representation empty"})
        return {"basis": None, "themes": [], "available": False}
    ranked = sorted(themes, key=lambda t: (t.get("emerging_score") is None,
                                           -(t.get("emerging_score") or 0.0),
                                           str(t.get("theme") or "")))[:top_n]
    members_by_theme = _theme_members(rotation)
    _disclose_theme_top5_gap(root, degraded)   # days_since_top5_entry is null by design here

    lanes: dict[str, set[str]] = {}
    if standouts:
        for lane in STANDOUT_LANES:
            rows = standouts.get(lane) or []
            lanes[lane] = {r.get("ticker") for r in rows
                           if isinstance(r, dict) and r.get("ticker")}
    else:
        lanes = {lane: set() for lane in STANDOUT_LANES}

    out_themes = []
    for rank, t in enumerate(ranked, start=1):
        name = t.get("theme")
        members = members_by_theme.get(name, [])
        present = {lane: sorted(set(members) & lanes.get(lane, set())) for lane in STANDOUT_LANES}
        out_themes.append({
            "rank": rank,
            "theme": name,
            "emerging_score": _num(t.get("emerging_score")),
            "n_members": len(members),
            "present_counts": {lane: len(v) for lane, v in present.items()},
            "present": present,
            "represented_n": len({x for v in present.values() for x in v}),
            # null with a named reason in `degraded` — see _disclose_theme_top5_gap
            "days_since_top5_entry": None,
        })
    return {
        "basis": "subsector_rotation.emerging_score",
        "days_since_top5_entry_basis": None,
        "rotation_asof": rotation.get("asof"),
        "standouts_asof": (standouts or {}).get("as_of"),
        "available": True,
        "themes": out_themes,
    }


# --------------------------------------------------------------------------- #
# F. basket-grain misses — "did a whole theme run with nobody on the board?"
# --------------------------------------------------------------------------- #
def basket_close_reader(root: Path = ROOT) -> Callable[[str], "pd.Series | None"]:
    """A MEMOIZED per-ticker close reader over ``data/baskets/ohlcv``.

    Memoized because basket membership overlaps heavily — AAPL is in mag7, ai_infra and
    us_sector_tech — so an unmemoized walk would re-read the same parquet several times.
    Only the ``close`` column is pulled; the OHLCV store carries five.
    Returns ``None`` for an absent or unreadable ticker: coverage is COUNTED by the
    caller and disclosed per basket, never silently averaged over.
    """
    cache: dict[str, "pd.Series | None"] = {}
    base = root / BASKET_OHLCV_DIR

    def read(ticker: str) -> "pd.Series | None":
        if ticker in cache:
            return cache[ticker]
        series: "pd.Series | None" = None
        path = base / f"{ticker}.parquet"
        if path.exists():
            try:
                frame = pd.read_parquet(path, columns=["close"])
                s = pd.to_numeric(frame["close"], errors="coerce").dropna()
                s.index = pd.DatetimeIndex(s.index)
                series = s.sort_index()
            except Exception:  # noqa: BLE001 — telemetry never takes the lane down
                series = None
        cache[ticker] = series
        return series

    return read


def _live_members(members: list[dict], asof: pd.Timestamp) -> list[str]:
    """Members live at ``asof`` — the point-in-time ``[added, removed)`` window that
    ``engine.baskets._ew_level`` uses, so this layer and the baskets page agree about
    who was in the basket on a given day."""
    out: list[str] = []
    for m in members or []:
        ticker = m.get("ticker")
        if not isinstance(ticker, str) or not ticker:
            continue
        added = m.get("added")
        if added and pd.Timestamp(added) > asof:
            continue
        removed = m.get("removed")
        if removed and pd.Timestamp(removed) <= asof:
            continue
        out.append(ticker)
    return out


def basket_ew_level(members: list[dict], close_of: Callable[[str], "pd.Series | None"],
                    ) -> tuple["pd.Series | None", int, int]:
    """Equal-weight LEVEL series for one basket → ``(level, n_read, n_members)``.

    Same construction as ``engine.baskets._ew_level``: equal weight over the members
    LIVE on each day (dated membership, renormalised daily), cumulated from the first
    day the basket had any. Return-space, so a member joining or leaving rebalances
    rather than jumping the level.

    ``n_read`` is the coverage receipt. D12/D13 of the missed-ignitions audit is the
    reason it is returned rather than assumed: the basket-turn organ read 1 of 12
    gold_miners members and 0 of 15 space_economy members, and printed a number that
    looked exactly like a fully-read one.
    """
    n_members = len({m.get("ticker") for m in (members or []) if m.get("ticker")})
    series = {}
    for ticker in {m.get("ticker") for m in (members or []) if m.get("ticker")}:
        s = close_of(ticker)
        if s is not None and len(s) > max(BASKET_EW_HORIZONS) + 1:
            series[ticker] = s
    if len(series) < BASKET_MIN_MEMBERS:
        return None, len(series), n_members

    px = pd.DataFrame(series).sort_index()
    idx = px.index
    rets = px.pct_change()
    mask = pd.DataFrame(False, index=idx, columns=list(px.columns))
    for m in members:
        ticker = m.get("ticker")
        if ticker not in mask.columns:
            continue
        live = idx >= pd.Timestamp(m["added"]) if m.get("added") else np.ones(len(idx), bool)
        if m.get("removed"):
            live = live & (idx < pd.Timestamp(m["removed"]))
        mask[ticker] = live
    ew = rets.where(mask).mean(axis=1)
    first = ew.first_valid_index()
    if first is None:
        return None, len(series), n_members
    level = (1.0 + ew.loc[first:].fillna(0.0)).cumprod()
    return level, len(series), n_members


def _trailing_ew(level: "pd.Series", sessions: int) -> float | None:
    """The basket's own trailing ``sessions``-bar return off its EW level."""
    if level is None or len(level) <= sessions:
        return None
    try:
        return float(level.iloc[-1] / level.iloc[-sessions - 1] - 1.0)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def own_history_pctile(level: "pd.Series", horizon: int = BASKET_MISS_HORIZON,
                       window: int = BASKET_HISTORY) -> tuple[float | None, int]:
    """Today's ``horizon``-bar return as a percentile of the basket's OWN trailing
    ``window`` sessions of the same measure → ``(pctile, n_observations)``.

    Own-history, never cross-basket: a 10-day move that is huge for defensives is
    ordinary for quantum names, and ranking the two together would surface the same
    high-vol baskets every night. Today is INSIDE its own window — the question is "is
    this one of this basket's biggest 10-day moves", which includes it by construction.

    MID-RANK, not the weak inequality. ``(hist <= today).mean()`` reads 1.00 — a
    perfect top-decile flag — for a basket whose every 10d return is 0.0, because a
    dead series ties with itself on every bar. That is the failure mode where a store
    that stopped updating pages as an ignition. Ties therefore split:
    ``below + half the ties``, which puts a flat basket at 0.50 and leaves a genuine
    unique maximum at ~1.00.

    The observations OVERLAP (a 10-day return sampled daily), so ``n`` is not an
    independent sample count: 252 rows carry roughly 25 non-overlapping windows. That
    is why this is ops telemetry with a printed percentile and not a p-value.
    ``(None, n)`` when the window is too thin to rank against.
    """
    if level is None or len(level) <= horizon:
        return None, 0
    rolling = (level / level.shift(horizon) - 1.0).dropna()
    hist = rolling.tail(window)
    if len(hist) < BASKET_MIN_HISTORY:
        return None, int(len(hist))
    current = float(rolling.iloc[-1])
    below = float((hist < current).mean())
    ties = float((hist == current).mean())
    return round(below + 0.5 * ties, 4), int(len(hist))


def basket_misses(root: Path, standouts: dict | None, degraded: list[dict],
                  price_through: str | None = None) -> dict:
    """Section F: every US basket's EW move vs its board representation.

    A basket in its own top decile on 10d with ZERO members on any visible lane is the
    named miss. BOTH halves are required and each is reported alongside the flag, so a
    reader can see that a quiet basket with nobody on the board is not a miss and that
    a running basket with three names on the board is a hit.

    ZERO AUTHORITY. Nothing reads this for rank, gate, size or membership; it is the
    instrument §8 of the missed-ignitions masterplan grades sector-grain miss latency
    against. Fail-soft: unreadable membership degrades to an available=False block with
    the reason named.
    """
    null = {"tier": "ops_telemetry", "available": False, "misses": [], "baskets": []}
    membership = _read_json(root, BASKET_MEMBERSHIP_JSON, degraded,
                            "basket-grain miss layer unavailable")
    baskets = (membership or {}).get("baskets")
    if not isinstance(baskets, dict) or not baskets:
        return {**null, "null_reason": f"no baskets[] in {BASKET_MEMBERSHIP_JSON}"}

    close_of = basket_close_reader(root)
    lanes: dict[str, set[str]] = {}
    for lane in BASKET_BOARD_LANES:
        rows = (standouts or {}).get(lane) or []
        lanes[lane] = {r.get("ticker") for r in rows
                       if isinstance(r, dict) and r.get("ticker")}
    on_board = set().union(*lanes.values()) if lanes else set()

    rows: list[dict] = []
    store_last: pd.Timestamp | None = None
    for basket_id in sorted(baskets):
        spec = baskets[basket_id] or {}
        members = spec.get("members") or []
        level, n_read, n_members = basket_ew_level(members, close_of)
        asof = level.index[-1] if level is not None and len(level) else None
        if asof is not None and (store_last is None or asof > store_last):
            store_last = asof
        live = _live_members(members, asof) if asof is not None else [
            m.get("ticker") for m in members if not m.get("removed")]
        present = sorted({t for t in live if t in on_board})
        pctile, n_hist = own_history_pctile(level)
        row = {
            "basket_id": basket_id,
            "name": spec.get("name"),
            "category": spec.get("category"),
            "as_of": (str(asof.date()) if asof is not None else None),
            "n_members": n_members,
            "n_members_live": len(live),
            "n_members_read": n_read,
            "n_members_on_board": len(present),
            "members_on_board": present,
            "present_counts": {lane: len({t for t in live if t in lane_tickers})
                               for lane, lane_tickers in lanes.items()},
            "pctile": pctile,
            "pctile_n": n_hist,
            "miss": False,
        }
        for horizon in BASKET_EW_HORIZONS:
            value = _trailing_ew(level, horizon)
            row[f"ew_{horizon}d"] = (round(value, 6) if value is not None else None)
        if level is None:
            row["null_reason"] = (
                f"fewer than {BASKET_MIN_MEMBERS} members readable in "
                f"{BASKET_OHLCV_DIR} ({n_read}/{n_members})")
        elif pctile is None:
            row["null_reason"] = (
                f"{n_hist} own-history {BASKET_MISS_HORIZON}d observations, below the "
                f"{BASKET_MIN_HISTORY} needed to rank against")
        else:
            row["miss"] = bool(pctile >= BASKET_TOP_DECILE
                               and row["n_members_on_board"] == 0)
        rows.append(row)

    scored = [r for r in rows if r["pctile"] is not None]
    misses = [r for r in scored if r["miss"]]
    def _coverage(row: dict) -> float:
        return (row["n_members_read"] / row["n_members"]) if row["n_members"] else 1.0

    partial = [r for r in rows if r["n_members_read"] < r["n_members"]]
    starved = sorted(r["basket_id"] for r in partial
                     if _coverage(r) < BASKET_COVERAGE_WARN)
    thin = sorted(r["basket_id"] for r in partial
                  if _coverage(r) >= BASKET_COVERAGE_WARN)
    if starved:
        degraded.append({
            "input": BASKET_OHLCV_DIR, "severity": "unexpected",
            "reason": f"{len(starved)} basket(s) read below "
                      f"{BASKET_COVERAGE_WARN:.0%} of their members: "
                      f"{', '.join(starved[:12])} — an EW level over a minority of a "
                      f"basket is not that basket's move (the D12 failure)",
        })
    if thin:
        degraded.append({
            "input": BASKET_OHLCV_DIR, "severity": "structural",
            "reason": f"{len(thin)} basket(s) missing at least one member close while "
                      f"still reading at or above {BASKET_COVERAGE_WARN:.0%}: "
                      f"{', '.join(thin[:12])} — EW read over the members present, "
                      f"per-basket counts on each row's n_members_read. Disclosed "
                      f"rather than paged: a single unfetched member is a standing "
                      f"fact, and an annotation that fires every night is noise",
        })
    store_asof = str(store_last.date()) if store_last is not None else None
    if store_asof and price_through and store_asof != price_through:
        degraded.append({
            "input": BASKET_OHLCV_DIR, "severity": "unexpected",
            "reason": f"basket store last bar {store_asof} != breadth-cache "
                      f"price_through {price_through} — the basket block is keyed to "
                      f"its OWN store's last bar, never the other cache's clock",
        })
    return {
        "tier": "ops_telemetry",
        "authority": "none — measurement only; no rank/gate/size/membership consumer",
        "available": True,
        "as_of": store_asof,
        "standouts_asof": (standouts or {}).get("as_of"),
        "basis": (
            f"equal-weight member returns over {BASKET_OHLCV_DIR} with point-in-time "
            f"dated membership (engine.baskets._ew_level construction); the "
            f"{BASKET_MISS_HORIZON}d return ranked inside the basket's OWN trailing "
            f"{BASKET_HISTORY}-session history of the same measure. Overlapping "
            f"windows — the percentile is a description, not a test."
        ),
        "miss_rule": (
            f"pctile >= {BASKET_TOP_DECILE} AND zero live members on any of "
            f"{list(BASKET_BOARD_LANES)} (featured is a flag inside buy)"
        ),
        "lanes": list(BASKET_BOARD_LANES),
        "n_baskets": len(rows),
        "n_scored": len(scored),
        "n_misses": len(misses),
        "n_top_decile": sum(1 for r in scored if r["pctile"] >= BASKET_TOP_DECILE),
        "n_unrepresented": sum(1 for r in scored if r["n_members_on_board"] == 0),
        "misses": sorted(misses, key=lambda r: -(r["pctile"] or 0.0)),
        "baskets": sorted(rows, key=lambda r: (r["pctile"] is None,
                                               -(r["pctile"] or 0.0),
                                               r["basket_id"])),
    }


# --------------------------------------------------------------------------- #
# E. name_score scorecard — read-only mirror of the nightly grader's own outputs
# --------------------------------------------------------------------------- #
def name_score_series_reader(market: str = NAME_SCORE_MARKET) -> Callable[[str], pd.Series | None]:
    """A per-ticker MEMOIZED close-series resolver, identical to the resolution half of
    ``engine.name_score_grader._fwd_return``.

    WHY THIS EXISTS (runtime, not method). ``grade()`` originally resolved the series
    inside a per-(row, horizon) loop, so a 72k-row ledger cost ~145k parquet reads —
    MEASURED at 13.4 minutes and rising with every night's stamp, which is a fifth of the
    whole render budget for telemetry no gate reads. The ledger's 72k rows span only ~3k
    tickers, so reading each name ONCE and reusing the series makes the same computation
    cost ~3s. The read count is bounded by the UNIVERSE (stable), not by ledger depth
    (accruing), so this stays cheap as the ledger grows. ``grade()`` now carries the same
    per-name memo (``name_score_grader._series_reader`` — same shape, added after this
    adapter proved it); this reader stays the audit's OWN resolution so the anti-fork pin
    compares two implementations rather than one through a pointer.

    It is a caching wrapper, NOT a second opinion: the group ladder
    (``name_score_grader._FWD_GROUP``), the ``close`` coercion, and the US dead-name
    extension (``engine.grading.resolve_series``) are the grader's, and the forward return
    itself is taken from ``engine.grading.grade_next_bar_return`` — the same call
    ``_fwd_return`` makes. ``tests/test_prophet_miss_audit.py`` pins the whole block against
    a live ``name_score_grader.grade()`` run on a synthetic ledger, so a drift in either
    module fails the suite rather than shipping a second set of numbers.
    """
    m = (market or NAME_SCORE_MARKET).upper()
    grp = nsg._FWD_GROUP.get(m, "china")
    groups = (grp,) if isinstance(grp, str) else grp
    cache: dict[str, pd.Series | None] = {}

    def read(ticker: str) -> pd.Series | None:
        t = str(ticker)
        if t in cache:
            return cache[t]
        df = None
        try:
            for g in groups:
                df = store.read(g, t)
                if df is not None and "close" in df:
                    break
            s = (pd.to_numeric(df["close"], errors="coerce").dropna()
                 if (df is not None and "close" in df) else None)
        except Exception:  # noqa: BLE001 — a per-name read failure is a null, never fatal
            s = None
        if m == "US":
            try:
                s = grading.resolve_series(t, s)
            except Exception:  # noqa: BLE001
                pass
        cache[t] = None if (s is None or s.empty) else s.sort_index()
        return cache[t]

    return read


def grade_calls(calls: pd.DataFrame, *, market: str = NAME_SCORE_MARKET,
                series_for: Callable[[str], pd.Series | None] | None = None,
                horizons: tuple[int, ...] = nsg._HORIZONS_D,
                ) -> tuple[dict[int, pd.DataFrame], dict]:
    """Join each call to its forward return, per horizon. Returns (frames, coverage).

    ``calls`` is the grader's own ledger frame AFTER ``_drop_frozen_echoes`` (the caller
    quarantines and reports the echo count — a frozen-feed re-stamp is a fabricated
    observation, never a graded call). A call with no resolvable series contributes to NO
    horizon; a call whose horizon has not matured is absent from THAT horizon only — never
    scored 0, never carried forward.
    """
    read = series_for or name_score_series_reader(market)
    recs: dict[int, list[dict]] = {h: [] for h in horizons}
    resolved: set[str] = set()
    stamped: set[str] = set()
    for _i, row in calls.iterrows():
        t = str(row["ticker"])
        stamped.add(t)
        s = read(t)
        if s is None:
            continue
        resolved.add(t)
        d0 = str(pd.Timestamp(row["date"]).date())
        for h in horizons:
            fr = grading.grade_next_bar_return(s, d0, h)
            if fr is None:
                continue
            recs[h].append({"date": str(row["date"]), "ticker": t, "score": row.get("score"),
                            "tier": row.get("tier"), "fwd": fr})
    frames = {h: pd.DataFrame(recs[h], columns=["date", "ticker", "score", "tier", "fwd"])
              for h in horizons}
    grp = nsg._FWD_GROUP.get((market or "").upper(), "china")
    coverage = {
        "group": grp if isinstance(grp, str) else list(grp),
        "n_names_stamped": len(stamped),
        "n_names_resolved": len(resolved),
        "coverage_pct": (round(100.0 * len(resolved) / len(stamped), 1) if stamped else None),
        "note": "the forward join resolves only names with a per-name close store; a stamped "
                "name with no store is absent from every horizon, not scored zero",
    }
    return frames, coverage


def precision_at_k(g: pd.DataFrame, *, ks: tuple[int, ...] = PK_K,
                   min_xs: int = PK_MIN_XS) -> dict:
    """P@k of the score's OWN ordering against each date's graded cross-section.

    DEFINITIONS, stated (this block sets no threshold that gates anything):
      * cohort      — one stamp date's graded calls; a date contributes only when its
                      graded cross-section is >= ``min_xs`` wide.
      * hit         — the call's forward return beats THAT DATE'S median graded forward
                      return (date-demeaned by construction, so a market-wide up day cannot
                      manufacture precision).
      * P@k         — share of the top-k by score (ties broken on ticker, so the ordering is
                      reproducible) that are hits, averaged over qualifying dates.
      * base        — share of ALL that date's graded calls that are hits, averaged the same
                      way. It is near 0.50 by construction (the median splits the cohort);
                      it is REPORTED rather than assumed so the reader compares P@k to the
                      cohort's own measured base, never to an asserted coin flip.
      * lift        — mean P@k − mean base. Positive means the top of the score's ordering
                      beat its own cohort; negative means it did not.

    Every denominator is the MATURED cohort, never the resolved-winner subset. When no date
    qualifies the result is ``None`` with a named reason — an absent measurement is not a
    50% precision.
    """
    out: dict[str, Any] = {
        "definition": (f"hit = forward return > that stamp date's median graded forward "
                       f"return; dates with a graded cross-section < {min_xs} are excluded "
                       f"from P@k (the exclusion is stated and counted below, not silent)"),
        "min_cross_section": min_xs,
        "n_dates_eligible": 0,
        "n_dates_excluded_thin": 0,
        "cross_section": None,
        "by_k": {f"p_at_{k}": None for k in ks},
    }
    if g.empty:
        out["null_reason"] = "no graded calls at this horizon"
        return out
    sizes: list[int] = []
    cohorts: list[pd.DataFrame] = []
    thin = 0
    for _d, sub in g.groupby("date"):
        if len(sub) < min_xs:
            thin += 1
            continue
        med = float(sub["fwd"].median())
        cohorts.append(sub.assign(hit=sub["fwd"] > med))
        sizes.append(int(len(sub)))
    out["n_dates_excluded_thin"] = thin
    out["n_dates_eligible"] = len(cohorts)
    if not cohorts:
        out["null_reason"] = (f"no stamp date carries a graded cross-section of {min_xs}+ "
                              f"names ({thin} date(s) too thin) — P@k is not computable, "
                              f"which is not the same as 50%")
        return out
    out["cross_section"] = {"min": min(sizes), "median": int(np.median(sizes)),
                            "max": max(sizes)}
    bases = [float(c["hit"].mean()) for c in cohorts]
    out["base_rate"] = round(float(np.mean(bases)), 3)
    for k in ks:
        vals = []
        for c in cohorts:
            top = c.sort_values(["score", "ticker"], ascending=[False, True]).head(k)
            vals.append(float(top["hit"].mean()))
        out["by_k"][f"p_at_{k}"] = {
            "value": round(float(np.mean(vals)), 3),
            "lift_vs_base": round(float(np.mean(vals) - np.mean(bases)), 3),
            "n_dates": len(vals),
            "n_picks": int(sum(min(k, len(c)) for c in cohorts)),
        }
    return out


def horizon_scorecard(g: pd.DataFrame, h: int) -> dict:
    """One horizon's read: rank-IC (the grader's own construction), buy-tier hit rate,
    per-tier forward, and P@k. Nulls carry a plain reason; nothing here is a threshold."""
    out: dict[str, Any] = {"horizon_d": h, "n_graded": int(len(g))}
    if len(g) < 5:
        out.update({
            "rank_ic": None, "n_ic_dates": 0, "ic_cross_section": None,
            "buy_tier_hit_rate": None, "by_tier": {}, "precision_at_k": None,
            "thin": True,
            "null_reason": (f"still accruing — {len(g)} call(s) have {h} sessions of forward "
                            f"price past their next-bar fill; the grader reports 'accruing' "
                            f"below 5"),
        })
        return out
    ics: list[float] = []
    ic_ns: list[int] = []
    for _d, sub in g.groupby("date"):
        # the grader's own per-date admission: a cross-section needs >= 5 DISTINCT scores
        # before a Spearman correlation on it means anything.
        if sub["score"].nunique() >= 5:
            ics.append(float(sub["score"].rank().corr(sub["fwd"].rank())))
            ic_ns.append(int(len(sub)))
    buys = g[g["tier"].isin(nsg._BUY_TIERS)]
    hit = float((buys["fwd"] > 0).mean()) if len(buys) else None
    by_tier: dict[str, dict] = {}
    for lab, sub in g.groupby("tier"):
        if len(sub) >= 5:
            by_tier[str(lab)] = {"n": int(len(sub)),
                                 "mean_fwd": round(float(sub["fwd"].mean()), 4),
                                 "pos_rate": round(float((sub["fwd"] > 0).mean()), 3)}
    out.update({
        "rank_ic": (round(float(np.mean(ics)), 4) if ics else None),
        "n_ic_dates": len(ics),
        "ic_cross_section": ({"min": min(ic_ns), "median": int(np.median(ic_ns)),
                              "max": max(ic_ns)} if ic_ns else None),
        "buy_tier_hit_rate": (round(hit, 3) if hit is not None else None),
        "buy_tier_n": int(len(buys)),
        "by_tier": by_tier,
        "precision_at_k": precision_at_k(g),
        "thin": len(ics) < THIN_MIN_IC_DATES,
    })
    if not ics:
        out["null_reason"] = ("no stamp date carries 5+ distinct scores in its graded "
                              "cross-section — rank-IC is not computable")
    elif out["thin"]:
        out["thin_reason"] = (f"{len(ics)} IC date(s) — below the {THIN_MIN_IC_DATES}-date "
                              f"disclosure floor; read as a sample, not a measurement")
    return out


def name_score_scorecard(root: Path = ROOT, degraded: list[dict] | None = None, *,
                         market: str = NAME_SCORE_MARKET,
                         series_for: Callable[[str], pd.Series | None] | None = None) -> dict:
    """The read-only ``name_score`` block. Fail-soft: any missing input degrades to nulls
    with a named reason and a ``degraded`` row, never an exception into the nightly."""
    deg = degraded if degraded is not None else []
    m = (market or NAME_SCORE_MARKET).upper()
    block: dict[str, Any] = {
        "tier": "ops_telemetry",
        "authority": "none — read-only mirror of engine/name_score_grader outputs; no rank, "
                     "gate, size, or user-facing consumer",
        "market": m,
        "source": NAME_SCORE_LEDGER_REL,
        "graded_by": "engine.grading.grade_next_bar_return (next-bar fill, survivorship-aware) "
                     "via engine.name_score_grader's own forward-store ladder",
        "scored_field": "score — name_score.potential_score, the number the US board displays "
                        "as conviction.score (scripts/build_stock_library.py overwrites "
                        "c['score'] with the potential score for backward compatibility)",
        "available": False,
    }
    p = root / NAME_SCORE_LEDGER_REL
    try:
        calls = pd.read_parquet(p)
    except Exception as exc:  # noqa: BLE001 — fail-soft, disclosed
        deg.append({"input": NAME_SCORE_LEDGER_REL, "severity": "unexpected",
                    "reason": f"unreadable: {exc} — name_score scorecard is null, not zero"})
        block["null_reason"] = f"ledger unreadable: {exc}"
        return block
    if calls.empty or "date" not in calls.columns:
        deg.append({"input": NAME_SCORE_LEDGER_REL, "severity": "unexpected",
                    "reason": "ledger empty or missing the date column — scorecard is null"})
        block["null_reason"] = "ledger empty or malformed"
        return block

    kept, n_frozen = nsg._drop_frozen_echoes(calls)
    dates = sorted(str(d) for d in kept["date"].dropna().unique())
    block.update({
        "available": True,
        "n_calls": int(len(kept)),
        "n_frozen_echoes_excluded": int(n_frozen),
        "n_stamp_dates": len(dates),
        "stamp_dates": {"first": (dates[0] if dates else None),
                        "last": (dates[-1] if dates else None)},
    })
    try:
        frames, coverage = grade_calls(kept, market=m, series_for=series_for)
    except Exception as exc:  # noqa: BLE001
        deg.append({"input": NAME_SCORE_LEDGER_REL, "severity": "unexpected",
                    "reason": f"forward join failed: {exc} — scorecard horizons are null"})
        block["null_reason"] = f"forward join failed: {exc}"
        return block
    block["forward_store"] = coverage
    block["by_horizon"] = {f"{h}d": horizon_scorecard(g, h) for h, g in frames.items()}
    return block


# --------------------------------------------------------------------------- #
# F. priority_score scorecard — read-only mirror of the full-population grade store
# --------------------------------------------------------------------------- #
def _population_leg(g: pd.DataFrame) -> dict:
    """The whole graded universe's own read at one horizon — the "more data" half.

    This block exists because the record is no longer ~12 plans a night: every stamped
    name is graded, so the board's cohort can finally be compared against the universe it
    was drawn from instead of against nothing.
    """
    excess = pd.to_numeric(g["excess_spy"], errors="coerce").dropna()
    out: dict[str, Any] = {
        "n": int(len(g)),
        "n_excess": int(len(excess)),
        "n_dates": int(g["stamp_date"].nunique()),
        "mean_excess": (round(float(excess.mean()), 5) if len(excess) else None),
        "median_excess": (round(float(excess.median()), 5) if len(excess) else None),
        "pos_rate": (round(float((excess > 0).mean()), 4) if len(excess) else None),
        "by_lane": {},
    }
    if not len(excess):
        out["null_reason"] = ("no graded row carries an excess mark — the SPY cache was "
                              "missing on every grading night (absolute marks may still "
                              "exist; a null excess is not a zero excess)")
        return out
    if "lane" in g.columns:
        for lane, sub in g.groupby(g["lane"].fillna("not_on_board")):
            vals = pd.to_numeric(sub["excess_spy"], errors="coerce").dropna()
            if len(vals) < PRIORITY_MIN_LANE_N:
                continue
            out["by_lane"][str(lane)] = {
                "n": int(len(vals)),
                "mean_excess": round(float(vals.mean()), 5),
                "median_excess": round(float(vals.median()), 5),
                "pos_rate": round(float((vals > 0).mean()), 4),
            }
    return out


def _score_deciles(g: pd.DataFrame, *, min_xs: int = PRIORITY_DECILE_MIN_XS) -> dict:
    """Decile lift + loser rate, deciles cut WITHIN each stamp date.

    DEFINITIONS, stated (this block gates nothing):
      * decile     — 1 = lowest priority score of that date's scored cross-section,
                     10 = highest.  Cut per date, so a day when every score is high cannot
                     masquerade as a top decile.
      * hit        — excess vs SPY above that date's median excess across the graded
                     population OF THE SAME COHORT.  That comparator is the point of
                     grading the whole universe: it asks "did this name beat a name drawn
                     at random that night", which the 12-plans-a-night record could never
                     answer.  It is taken WITHIN the cohort because curated and scan names
                     are different populations — judging a curated pick against a median
                     dominated by scan names would flatter it by construction.
      * loser_rate — share of the decile with excess < 0.  The operator's question in its
                     bluntest form: are high-scored names losing money against SPY?
      * lift       — top decile mean excess − bottom decile mean excess.

    A date whose scored cross-section is thinner than ``min_xs`` is EXCLUDED and counted;
    it is never padded into a decile it cannot support.
    """
    out: dict[str, Any] = {
        "definition": (f"deciles cut within each stamp date (10 = highest priority score); "
                       f"hit = excess vs SPY above that date's median excess across the "
                       f"FULL graded population (every stamped name); loser = excess < 0; "
                       f"dates with fewer than {min_xs} scored names are excluded and "
                       f"counted"),
        "min_cross_section": min_xs,
        "n_dates_eligible": 0, "n_dates_excluded_thin": 0,
        "by_decile": {}, "top_minus_bottom_excess": None,
    }
    if g.empty:
        out["null_reason"] = "no graded rows at this horizon"
        return out
    frames: list[pd.DataFrame] = []
    thin = 0
    for _date, sub in g.groupby("stamp_date"):
        scored = sub[sub["prophet_score"].notna() & sub["excess_spy"].notna()]
        if len(scored) < min_xs:
            thin += 1
            continue
        pop_median = pd.to_numeric(sub["excess_spy"], errors="coerce").dropna()
        if pop_median.empty:
            thin += 1
            continue
        try:
            decile = pd.qcut(scored["prophet_score"].rank(method="first"), 10,
                             labels=False, duplicates="drop") + 1
        except ValueError:      # fewer distinct ranks than requested bins
            thin += 1
            continue
        frames.append(scored.assign(_decile=decile.astype(int),
                                    _hit=scored["excess_spy"] > float(pop_median.median())))
    out["n_dates_excluded_thin"] = thin
    out["n_dates_eligible"] = len(frames)
    if not frames:
        out["null_reason"] = (f"no stamp date carries {min_xs}+ scored names with a graded "
                              f"excess ({thin} date(s) too thin) — a decile table is not "
                              f"computable, which is not the same as a flat one")
        return out
    pooled = pd.concat(frames, ignore_index=True)
    for decile, sub in pooled.groupby("_decile"):
        vals = pd.to_numeric(sub["excess_spy"], errors="coerce").dropna()
        if vals.empty:
            continue
        out["by_decile"][f"d{int(decile)}"] = {
            "n": int(len(vals)),
            "mean_excess": round(float(vals.mean()), 5),
            "median_excess": round(float(vals.median()), 5),
            "hit_rate": round(float(sub["_hit"].mean()), 4),
            "loser_rate": round(float((vals < 0).mean()), 4),
        }
    top, bottom = out["by_decile"].get("d10"), out["by_decile"].get("d1")
    if top and bottom:
        out["top_minus_bottom_excess"] = round(
            top["mean_excess"] - bottom["mean_excess"], 5)
    return out


def _priority_precision_at_k(g: pd.DataFrame, *, ks: tuple[int, ...] = PRIORITY_PK_K,
                             min_xs: int = PK_MIN_XS) -> dict:
    """P@k of the priority score's OWN ordering, scored against the FULL population.

    Same shape as :func:`precision_at_k` (the name_score block's), with one deliberate
    difference stated here rather than left to be discovered: ``hit`` compares against the
    median of every graded name that night, not against the median of the ranked cohort.
    The name_score block cannot do that — its ledger holds only the names it stamped — and
    it is exactly what the full-population grade store was built to make possible.
    """
    out: dict[str, Any] = {
        "definition": (f"hit = excess vs SPY above that stamp date's FULL-population median "
                       f"excess WITHIN THIS COHORT (every graded name in it, not just the "
                       f"ranked ones); dates whose scored cross-section is < {min_xs} are "
                       f"excluded and counted"),
        "min_cross_section": min_xs,
        "n_dates_eligible": 0, "n_dates_excluded_thin": 0,
        "cross_section": None, "base_rate": None,
        "by_k": {f"p_at_{k}": None for k in ks},
    }
    if g.empty:
        out["null_reason"] = "no graded rows at this horizon"
        return out
    cohorts: list[pd.DataFrame] = []
    bases: list[float] = []
    sizes: list[int] = []
    thin = 0
    for _date, sub in g.groupby("stamp_date"):
        pop = pd.to_numeric(sub["excess_spy"], errors="coerce").dropna()
        scored = sub[sub["prophet_score"].notna() & sub["excess_spy"].notna()]
        if pop.empty or len(scored) < min_xs:
            thin += 1
            continue
        med = float(pop.median())
        cohorts.append(scored.assign(_hit=scored["excess_spy"] > med))
        # the base a reader compares P@k against is the RANKED cohort's own hit rate:
        # "did the top of the list beat the rest of the list", never an assumed coin flip.
        bases.append(float((scored["excess_spy"] > med).mean()))
        sizes.append(int(len(scored)))
    out["n_dates_excluded_thin"] = thin
    out["n_dates_eligible"] = len(cohorts)
    if not cohorts:
        out["null_reason"] = (f"no stamp date carries a scored cross-section of {min_xs}+ "
                              f"names ({thin} date(s) too thin) — P@k is not computable, "
                              f"which is not the same as 50%")
        return out
    out["cross_section"] = {"min": min(sizes), "median": int(np.median(sizes)),
                            "max": max(sizes)}
    out["base_rate"] = round(float(np.mean(bases)), 3)
    for k in ks:
        vals = []
        for cohort in cohorts:
            top = cohort.sort_values(["prophet_score", "ticker"],
                                     ascending=[False, True]).head(k)
            vals.append(float(top["_hit"].mean()))
        out["by_k"][f"p_at_{k}"] = {
            "value": round(float(np.mean(vals)), 3),
            "lift_vs_base": round(float(np.mean(vals) - np.mean(bases)), 3),
            "n_dates": len(vals),
            "n_picks": int(sum(min(k, len(c)) for c in cohorts)),
        }
    return out


def _class_legs(g: pd.DataFrame) -> dict:
    """Per signal class, the population read at THIS horizon — basing beside momentum.

    Operator ruling 2026-08-05: a basing pick and a momentum pick are different bets, and a
    single 10-session headline grades the wait instead of the call.  Every class is reported
    at EVERY horizon in the ladder, so nothing is hidden; ``chartered_horizon`` (fixed in
    :mod:`engine.us_prophet_grades` BEFORE any long-horizon data matured) says which one is
    that class's HEADLINE read, so no one can pick the flattering horizon after the fact.
    """
    out: dict[str, Any] = {}
    if "signal_class" not in g.columns:
        return out
    for label, sub in g.groupby(g["signal_class"].fillna("unclassified")):
        vals = pd.to_numeric(sub["excess_spy"], errors="coerce").dropna()
        leg: dict[str, Any] = {"n": int(len(sub)), "n_excess": int(len(vals))}
        if len(vals) < PRIORITY_MIN_LANE_N:
            leg["null_reason"] = (f"{len(vals)} graded row(s) with an excess mark — below "
                                  f"the {PRIORITY_MIN_LANE_N}-row floor for a printed read")
        else:
            leg.update({
                "mean_excess": round(float(vals.mean()), 5),
                "median_excess": round(float(vals.median()), 5),
                "pos_rate": round(float((vals > 0).mean()), 4),
                "loser_rate": round(float((vals < 0).mean()), 4),
            })
        out[str(label)] = leg
    return out


def priority_horizon_scorecard(g: pd.DataFrame, h: int) -> dict:
    """One horizon's read of the priority score: rank-IC, P@k, deciles, population.

    Computed on ONE cohort's rows — the caller splits curated from scan before calling, so
    nothing here ever pools the two.  Nulls carry a plain reason; nothing here is a
    threshold and nothing gates on it.
    """
    scored = g[g["prophet_score"].notna() & g["excess_spy"].notna()]
    out: dict[str, Any] = {
        "horizon_d": h,
        "n_graded": int(len(g)),
        "n_scored": int(len(scored)),
        "n_dates": int(g["stamp_date"].nunique()) if len(g) else 0,
        "population": _population_leg(g),
        "by_signal_class": _class_legs(g),
    }
    if len(scored) < PRIORITY_MIN_SCORED:
        out.update({
            "rank_ic": None, "n_ic_dates": 0, "ic_cross_section": None,
            "precision_at_k": None, "deciles": None, "thin": True,
            "null_reason": (
                f"still accruing — {len(scored)} graded row(s) carry a stamped priority "
                f"score at H={h} (the builder computes the itemized legs on the buy lane "
                f"only, so most stamped names have no score); below {PRIORITY_MIN_SCORED} "
                f"nothing is summarised"),
        })
        return out
    ics: list[float] = []
    ic_ns: list[int] = []
    degenerate = 0
    for _date, sub in scored.groupby("stamp_date"):
        if sub["prophet_score"].nunique() < 5:
            continue
        value = float(sub["prophet_score"].rank().corr(sub["excess_spy"].rank()))
        # A cross-section whose forward returns are all identical has ZERO variance, so
        # Spearman is undefined and pandas returns NaN. Averaging that NaN in would poison
        # the whole horizon, and json.dumps would then emit a bare `NaN` — invalid JSON
        # that a strict reader rejects. Drop the date and COUNT it: an undefined
        # correlation is a missing observation, never a 0.0 correlation.
        if not np.isfinite(value):
            degenerate += 1
            continue
        ics.append(value)
        ic_ns.append(int(len(sub)))
    out.update({
        "rank_ic": (round(float(np.mean(ics)), 4) if ics else None),
        "n_ic_dates": len(ics),
        "n_ic_dates_degenerate": degenerate,
        "ic_cross_section": ({"min": min(ic_ns), "median": int(np.median(ic_ns)),
                              "max": max(ic_ns)} if ic_ns else None),
        "precision_at_k": _priority_precision_at_k(g),
        "deciles": _score_deciles(g),
        "thin": len(ics) < THIN_MIN_IC_DATES,
    })
    if not ics:
        out["null_reason"] = (
            f"no stamp date yields a defined rank-IC — {degenerate} date(s) had 5+ distinct "
            f"scores but zero variance in their forward returns (correlation undefined), "
            f"and the rest carry fewer than 5 distinct scores. Not computable is not zero"
            if degenerate else
            "no stamp date carries 5+ distinct priority scores in its graded "
            "cross-section — rank-IC is not computable")
    elif out["thin"]:
        out["thin_reason"] = (f"{len(ics)} IC date(s) — below the {THIN_MIN_IC_DATES}-date "
                              f"disclosure floor; read as a sample, not a measurement")
    return out


def priority_score_scorecard(root: Path = ROOT, degraded: list[dict] | None = None) -> dict:
    """The read-only ``priority_score`` block (PROPHET US §W7.3).

    Answers the operator's question — "how robust and correct is our scoring system?" — by
    joining the score the system stamped on a name (the Context Vector store) to what that
    name then did (the full-population grade store).  It RECOMPUTES NOTHING: both stores are
    read through their own modules' readers, exactly as this file's ``name_score`` block
    mirrors ``name_score_grader`` rather than re-deriving it.

    Fail-soft: any missing input degrades to nulls with a named reason and a ``degraded``
    row, never an exception into the nightly.
    """
    deg = degraded if degraded is not None else []
    block: dict[str, Any] = {
        "tier": "ops_telemetry",
        "authority": "none — read-only join of two zero-authority stores; no rank, gate, "
                     "size, board, plan or user-facing consumer",
        "source": f"{PRIORITY_GRADES_REL} joined to {PRIORITY_CANDIDATES_REL}",
        "scored_field": "prophet_score — the us_prophet_v1 priority score exactly as "
                        "us_board_rank.score_rows stamped it that night (itemized legs sit "
                        "beside it in the candidates store; no composite is built here)",
        "graded_by": "engine.us_prophet_grades — engine.grading.forward_metrics (next-bar "
                     "fill, positional session horizons), excess vs SPY",
        "available": False,
    }
    try:
        from engine import us_prophet_grades as upg
    except Exception as exc:  # noqa: BLE001 — minimal-deps lanes
        deg.append({"input": PRIORITY_GRADES_REL, "severity": "unexpected",
                    "reason": f"grade store module unavailable: {exc}"})
        block["null_reason"] = f"grade store module unavailable: {exc}"
        return block
    block["population"] = (
        "EVERY stamped candidate row is graded, not only the ~12 that become plans "
        "(operator order 2026-08-05). Two populations are carried separately and never "
        "pooled: CURATED (board-admissible) and SCAN (seen and stamped, never admitted). "
        "Within each, basing and momentum picks are reported separately at every horizon "
        "in the ladder")
    try:
        block["store"] = upg.coverage(root)
        frame = upg.load_graded_frame(root, score_columns=["lane", "sector"])
    except Exception as exc:  # noqa: BLE001
        deg.append({"input": PRIORITY_GRADES_REL, "severity": "unexpected",
                    "reason": f"grade store unreadable: {exc} — scorecard is null, not zero"})
        block["null_reason"] = f"grade store unreadable: {exc}"
        return block
    if frame is None or frame.empty or "excess_spy" not in frame.columns:
        block["null_reason"] = (
            "no graded rows yet — the grade store accrues prospectively from the first "
            "nightly after merge (H=10 marks land ~11 sessions after a stamp, H=21 ~22). "
            "An absent record is not a null result")
        return block

    scored_mask = frame["prophet_score"].notna()
    cohort_col = upg.DISCRIMINATOR_COLUMN
    cohorts = (frame[cohort_col] if cohort_col in frame.columns
               else pd.Series([None] * len(frame), index=frame.index))
    split_available = bool(cohorts.notna().any())
    block.update({
        "available": True,
        "horizon_ladder": list(upg.HORIZONS),
        "chartered_horizon": dict(upg.CHARTERED_HORIZON),
        "chartered_horizon_note": (
            "PRE-REGISTERED before any H=42/63 data matured (operator ruling 2026-08-05). "
            "Every class is graded and reported at EVERY horizon below, so nothing is "
            "hidden; this map only fixes which horizon is each class's HEADLINE read, so "
            "that 'grade each class at the horizon that flatters it, chosen after seeing "
            "the results' is impossible. PROPOSED pending commissioner adjudication"),
        "score_coverage": {
            "n_rows": int(len(frame)),
            "n_scored": int(scored_mask.sum()),
            "coverage_pct": round(100.0 * float(scored_mask.mean()), 2),
            "note": "the US builder runs us_board_rank.score_rows on the BUY LANE only, so "
                    "a row off the board carries no priority score. That is a MEASURED "
                    "coverage fact, never a zero score — the ranking legs below are "
                    "computed on the scored subset and the population leg on everything",
        },
        "cohort_split": {
            "available": split_available,
            "column": cohort_col,
            "n_by_cohort": {str(k): int(v)
                            for k, v in cohorts.value_counts(dropna=True).to_dict().items()},
            "n_unsplit": int(cohorts.isna().sum()),
            "note": ("curated and scan are DIFFERENT POPULATIONS and are never pooled: "
                     "every statistic below is computed inside one cohort, including the "
                     "median a hit is measured against. Rows graded before the scan-tier "
                     "discriminator landed carry no cohort and are reported under "
                     "'unsplit' — never folded into 'curated'"
                     if split_available else
                     "the scan-tier discriminator has not landed in the candidates store "
                     "yet, so every graded row is one UNSPLIT population. It is labelled "
                     "'unsplit' rather than 'curated' because calling it curated would "
                     "assert a split that has not been measured"),
        },
    })
    # NEVER POOLED: the horizon legs are computed per cohort. There is deliberately no
    # top-level pooled rank-IC or P@k for a reader to misquote across populations.
    by_cohort: dict[str, Any] = {}
    for name, sub in frame.groupby(cohorts.fillna("unsplit")):
        by_cohort[str(name)] = {
            f"{int(h)}d": priority_horizon_scorecard(part, int(h))
            for h, part in sub.groupby("horizon")
        }
    block["by_cohort"] = by_cohort
    # Belt on top of the per-leg braces: nothing non-finite may leave this block. A bare
    # NaN/Infinity is what json.dumps emits for these, and that is INVALID JSON — a strict
    # reader downstream would reject the whole nightly artifact over one degenerate
    # cross-section. _num() is the module's existing numpy->JSON-safe coercion.
    return _scrub_non_finite(block)


def _scrub_non_finite(value: Any) -> Any:
    """Recursively replace NaN/Infinity with None so the artifact stays strict JSON."""
    if isinstance(value, dict):
        return {k: _scrub_non_finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_non_finite(v) for v in value]
    if isinstance(value, (float, np.floating, np.integer, np.bool_)):
        return _num(value)
    return value


def priority_score_row_fields(doc: dict) -> dict:
    """The priority scorecard's HEADLINE figures, flattened for the forward-log row.

    Compact by design — the full block lives in the artifact; the forward log carries only
    the series a reader would plot. ``priority_score_available`` keeps a null unambiguous:
    available + null rank-IC is the ACCRUING state (the block carries the plain reason);
    not-available means the store or the join was unreadable that night, and the artifact's
    ``degraded`` list names which. Null-safe on every path, including a doc with no block.
    """
    ps = doc.get("priority_score_scorecard") or {}
    by_cohort = ps.get("by_cohort") or {}
    split = ps.get("cohort_split") or {}
    out: dict = {
        "priority_score_available": bool(ps.get("available")),
        "priority_score_n_rows": (ps.get("score_coverage") or {}).get("n_rows"),
        "priority_score_coverage_pct": (ps.get("score_coverage") or {}).get("coverage_pct"),
        "priority_cohort_split_available": bool(split.get("available")),
    }
    # One flat column set per (cohort, horizon). The cohort names are FIXED here — a log
    # whose columns depend on tonight's data is not a series anyone can plot.
    for cohort in ("curated", "scan", "unsplit"):
        legs = by_cohort.get(cohort) or {}
        for h in PRIORITY_HORIZONS:
            cell = legs.get(f"{h}d") or {}
            out[f"priority_{cohort}_rank_ic_{h}d"] = cell.get("rank_ic")
            out[f"priority_{cohort}_n_{h}d"] = cell.get("n_graded")
            classes = cell.get("by_signal_class") or {}
            for signal_class in ("basing", "momentum"):
                leg = classes.get(signal_class) or {}
                out[f"priority_{cohort}_{signal_class}_n_{h}d"] = leg.get("n")
                out[f"priority_{cohort}_{signal_class}_mean_excess_{h}d"] = leg.get(
                    "mean_excess")
    return out


# --- G. entry_status re-measurement (ANTICIPATION §6.6) ---------------------------------
def entry_status_scorecard(root: Path = ROOT, degraded: list[dict] | None = None) -> dict:
    """The read-only ``entry_status`` block (PROPHET US ANTICIPATION §6.6).

    The STANDING evidence loop for the patience-first entry-value ladder.  The A2 entry leg
    ships STATUS-NEUTRAL per the §6.6 ruling — on the first US run of this measurement
    (2026-08-08) the CHINA board's measured ordering did not reproduce — and this table is
    what keeps accruing behind that ruling, so an ordering can only ever be re-introduced
    against a record rather than against a memory.  It confers nothing on its own: the map
    is edited by hand by an operator reading these cells.

    All of it lives in :mod:`engine.us_entry_status_remeasure`; this wrapper
    only supplies the miss-audit's root and degraded list, exactly as the ``priority_score``
    block delegates to :mod:`engine.us_prophet_grades`.

    Imported lazily and fail-soft for the same reason its sibling is: the minimal-deps
    lanes that build this audit must degrade to a named null rather than raise.
    """
    deg = degraded if degraded is not None else []
    try:
        from engine import us_entry_status_remeasure as uesr
    except Exception as exc:  # noqa: BLE001 — minimal-deps lanes
        deg.append({"input": ENTRY_STATUS_LEDGER_REL, "severity": "unexpected",
                    "reason": f"entry-status re-measurement module unavailable: {exc}"})
        return {"tier": "ops_telemetry", "available": False,
                "null_reason": f"entry-status re-measurement module unavailable: {exc}"}
    try:
        return uesr.scorecard(root, deg)
    except Exception as exc:  # noqa: BLE001
        deg.append({"input": ENTRY_STATUS_LEDGER_REL, "severity": "unexpected",
                    "reason": f"entry-status re-measurement failed: {exc} — the block is "
                              f"null, not zero"})
        return {"tier": "ops_telemetry", "available": False,
                "null_reason": f"entry-status re-measurement failed: {exc}"}


def entry_status_row_fields(doc: dict) -> dict:
    """The §6.6 table's headline cells, flattened for the forward-log row.

    Delegates to the owning module so the flat column set has ONE definition; null-safe on
    a doc with no block, and on a lane where the module could not be imported at all.
    """
    try:
        from engine import us_entry_status_remeasure as uesr
    except Exception:  # noqa: BLE001 — minimal-deps lanes
        return {"entry_status_available": False}
    return uesr.row_fields(doc)


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def _hist(values: list) -> dict:
    """Deterministic value-count histogram: count desc, then key asc."""
    counts: dict[str, int] = {}
    for v in values:
        k = str(v)
        counts[k] = counts.get(k, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _describe(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0, "mean": None, "p25": None, "median": None, "p75": None,
                "min": None, "max": None}
    s = pd.Series(vals, dtype="float64")
    return {"n": int(s.size), "mean": round(float(s.mean()), 2),
            "p25": round(float(s.quantile(0.25)), 2), "median": round(float(s.median()), 2),
            "p75": round(float(s.quantile(0.75)), 2), "min": round(float(s.min()), 2),
            "max": round(float(s.max()), 2)}


def _runner_rows(px: pd.DataFrame, rets: pd.Series, windows: dict[str, dict],
                 sector: dict[str, str], ret_key: str, *, with_gate: bool) -> list[dict]:
    rows = []
    for ticker, ret in rets.items():
        close = px[ticker]
        win = windows[ticker]          # scan_windows covers the union of both runner sets
        att = attribute_excluder(close, eligible_today=bool(win.get("eligible_today")))
        row = {"ticker": ticker, ret_key: round(float(ret) * 100, 1),
               "sector": sector.get(ticker, "?")}
        row.update(win)
        row.update(att)
        if with_gate:
            try:
                v = sg.gate(ticker, close.dropna())
                row["gate_eligible"] = bool(v.get("eligible"))
                row["gate_tier"] = v.get("tier_cascade")
                row["gate_near_miss"] = v.get("near_miss_reason")
            except Exception:  # noqa: BLE001 — telemetry must never take the lane down
                row["gate_eligible"] = None
                row["gate_tier"] = None
                row["gate_near_miss"] = None
        rows.append(row)
    return rows


def build_audit(root: Path = ROOT, *, top63_n: int = TOP63_N, top21_n: int = TOP21_N,
                lookback: int = LOOKBACK, with_gate: bool = True,
                with_cascade_basis: bool = True, with_name_score: bool = True,
                with_scan_tier: bool = True,
                with_priority_score: bool = True,
                with_entry_status: bool = True,
                with_baskets: bool = True) -> dict:
    """Compute the full audit document. Pure read: writes nothing."""
    degraded: list[dict] = []
    wide, sector, deg = load_universe(root)
    degraded.extend(deg)

    price_through = str(pd.Timestamp(wide.index[-1]).date())
    valid = wide.columns[wide.notna().sum() >= ct.MIN_HISTORY]
    px = wide[valid]
    if px.shape[1] == 0 or px.shape[0] < lookback + 2:
        raise ValueError(f"close cache too thin to audit: {px.shape}")

    r63 = (px.iloc[-1] / px.iloc[-(lookback + 1)] - 1).dropna()
    r21 = (px.iloc[-1] / px.iloc[-22] - 1).dropna()
    top63 = r63.sort_values(ascending=False).head(top63_n)
    top21 = r21.sort_values(ascending=False).head(top21_n)

    windows = scan_windows(px, sorted(set(top63.index) | set(top21.index)), lookback)

    runner_rows = _runner_rows(px, top63, windows, sector, "r63_pct", with_gate=with_gate)
    fast_rows = _runner_rows(px, top21, windows, sector, "r21_pct", with_gate=False)

    # universe eligible-today (cascade basis — the board-shaped, stricter set)
    cascade_elig: list[dict] | None = None
    if with_cascade_basis:
        cascade_elig = []
        for t in px.columns:
            v = ct.cascade(px[t])
            if v.get("eligible"):
                cascade_elig.append({"ticker": t, "tier": v.get("tier"),
                                     "sector": sector.get(t, "?")})

    plan_assets, deg = load_plan_assets(root)
    degraded.extend(deg)
    conversion = conversion_join(runner_rows, plan_assets)

    standouts = _read_json(root, STANDOUTS_JSON, degraded,
                           "theme member lane presence null")
    rotation = _read_json(root, ROTATION_JSON, degraded,
                          "theme representation unavailable")
    themes = theme_representation(root, standouts, rotation, degraded)
    basket_block = (basket_misses(root, standouts, degraded, price_through)
                    if with_baskets else
                    {"tier": "ops_telemetry", "available": False, "misses": [],
                     "baskets": [], "null_reason": "not computed (with_baskets=False)"})
    name_score = (name_score_scorecard(root, degraded) if with_name_score else
                  {"tier": "ops_telemetry", "available": False,
                   "null_reason": "not computed (with_name_score=False)"})
    # §4.5 scan-tier coverage: MIRRORED from the post-engine scan lane's artifact,
    # never recomputed here (that pass needs a 617 MB store this job does not
    # restore). Its own asof travels with it, so a reader can see when the two
    # tiers are a session apart instead of assuming one date covers both.
    scan_tier = scan_tier_coverage(root, degraded) if with_scan_tier else {
        "available": False, "asof": None,
        "null_reason": "not mirrored (with_scan_tier=False)"}
    priority_score = (priority_score_scorecard(root, degraded) if with_priority_score else
                      {"tier": "ops_telemetry", "available": False,
                       "null_reason": "not computed (with_priority_score=False)"})
    # §6.6 ANTICIPATION: entry-status -> forward outcome, the evidence loop that revises the
    # patience-first entry-value constants. A pure read of an already-graded ledger — it
    # regrades nothing and writes nothing.
    entry_status = (entry_status_scorecard(root, degraded) if with_entry_status else
                    {"tier": "ops_telemetry", "available": False,
                     "null_reason": "not computed (with_entry_status=False)"})

    days = [r["days_eligible"] for r in runner_rows if r.get("days_eligible") is not None]
    never = sum(1 for d in days if d == 0)
    summary = {
        "universe_n": int(len(valid)),
        "eligible_today_n": (len(cascade_elig) if cascade_elig is not None else None),
        "top63_n": len(runner_rows),
        "top63_eligible_today_n": sum(1 for r in runner_rows if r.get("eligible_today")),
        "top63_never_eligible_n": never,
        "top63_never_eligible_pct": (round(never / len(days), 4) if days else None),
        "top63_eligible_days": _describe([float(d) for d in days]),
        "top21_n": len(fast_rows),
        "top21_eligible_today_n": sum(1 for r in fast_rows if r.get("eligible_today")),
        "conversion_rate": conversion["rate"],
        "conversion_n": f"{conversion['converted_n']}/{conversion['sighted_n']}",
        # Section F headline. `None` (block unavailable) is a different fact from `0`
        # (every ignited basket had somebody on the board) and stays distinguishable.
        "basket_misses_n": (basket_block.get("n_misses")
                            if basket_block.get("available") else None),
        "basket_scored_n": (basket_block.get("n_scored")
                            if basket_block.get("available") else None),
    }

    doc = {
        "schema": SCHEMA,
        "price_through": price_through,
        "tier": "ops_telemetry",
        "authority": "none — measurement only; no rank/gate/size consumer",
        "bases": {
            "basket_misses": (
                f"equal-weight member returns over {BASKET_OHLCV_DIR} with point-in-time "
                f"dated membership — the basket machinery's own store and construction, "
                f"NOT the breadth caches above (they are S&P-1500 and cannot see the "
                f"off-index members the ignited baskets are full of)."),
            "runner_eligibility": "engine.confluence_tiers.tier_stream (completed buckets, "
                                  "raw-3D-cross T1 fallback) — last row = eligible_today, "
                                  "tail(63) = days_eligible/first_eligible. One basis for both "
                                  "so the verdict and the window cannot disagree about a day.",
            "universe_eligible_today": "engine.confluence_tiers.cascade last bar, "
                                       "take_active=False (no §7 master supplied here) — a "
                                       "STRICTER set than the stream basis, which is why a "
                                       "runner can be stream-eligible and absent from it.",
            "board_gate": "engine.signal_gate.gate per runner (gate_* fields) — the live "
                          "board's own basis, over a narrower universe than the board's.",
            "name_score": "engine.name_score_grader's append-only PIT call ledger, forward-"
                          "joined through engine.grading (next-bar fill, survivorship-aware). "
                          "Read-only: this audit mirrors the grader's numbers, it does not "
                          "change what the grader computes.",
            "priority_score": "engine.us_prophet_grades' full-population grade store "
                              "(H=10/21 sessions, excess vs SPY, next-bar fill) joined to "
                              "the priority score the US Context Vector store stamped for "
                              "that name on that night. Read-only: this audit recomputes "
                              "neither the score nor the grade. EVERY stamped name is "
                              "graded, so a pick's hit is judged against that night's "
                              "whole universe, not against the picks alone.",
        },
        "summary": summary,
        "top63_excluder_hist": _hist([r["excluder"] for r in runner_rows]),
        "top63_excluder_family_hist": _hist([r["excluder_family"] for r in runner_rows]),
        "top21_excluder_hist": _hist([r["excluder"] for r in fast_rows]),
        "veto_leg_hist": _hist([leg for r in runner_rows for leg in r.get("veto_legs", [])]),
        "runner_sector_hist": _hist([r["sector"] for r in runner_rows]),
        "eligible_today_sector_hist": (
            _hist([e["sector"] for e in cascade_elig]) if cascade_elig is not None else None),
        "conversion": conversion,
        "themes": themes,
        "basket_misses": basket_block,
        "name_score_scorecard": name_score,
        "scan_tier": scan_tier,
        "priority_score_scorecard": priority_score,
        "entry_status_scorecard": entry_status,
        "top63_runners": runner_rows,
        "top21_runners": fast_rows,
        "eligible_today": cascade_elig,
        "degraded": degraded,
    }
    return doc


# --------------------------------------------------------------------------- #
# F. SCAN TIER — the same instrument, over the widened seeing set (§4.5)
# --------------------------------------------------------------------------- #
def build_scan_tier_audit(root: Path = ROOT, *, top_n: int = SCAN_TOP_N,
                          lookback: int = LOOKBACK,
                          curated: set[str] | None = None,
                          tickers: list[str] | None = None,
                          floor: dict | None = None) -> dict:
    """Runner-exclusion audit over the liquidity-floored SCAN universe.

    Identical instrument to section A, pointed at a different frame: the runner
    verdict comes from ``ct.tier_stream`` and the excluder from
    ``attribute_excluder`` — the SAME functions the curated audit uses, not a
    parallel implementation. Only the universe differs.

    The point of the block is the ``off_index`` count: a scan-tier runner is a
    name the curated frame could not have rejected, because it was never in the
    frame. Reporting it as "missed" alongside the curated misses would blur two
    different failures, so the taxonomy names it separately —
    ``not_in_curated_universe`` is a COVERAGE fact, not a gate verdict.

    ``tickers``/``floor`` let a caller that ALREADY resolved the universe hand it
    in, so the runner lane pays the 30-second store census once instead of twice
    (it needs the same set to stamp the context vector). Omit both and this
    function resolves it itself.

    Fail-soft: with no store restored in this lane the document is a disclosed
    null carrying the reason, never an empty runner list that reads as "no
    off-index runners tonight".
    """
    from engine import us_scan_universe as usu

    degraded: list[dict] = []
    if not usu.store_available(root):
        return {
            "schema": SCAN_SCHEMA,
            "tier": "ops_telemetry",
            "authority": "none — coverage measurement only; no rank/gate/size consumer",
            "available": False,
            "null_reason": (
                f"{usu.STORE_REL} is not restored in this lane — the scan tier was NOT "
                "measured tonight (a null, not an absence of off-index runners)"),
            "price_through": None,
            "floor": {"rule": usu.floor_rule_text()},
            "summary": {}, "runners": [], "excluder_hist": {}, "sector_hist": {},
            "degraded": degraded,
        }

    curated = set(curated or ())
    if tickers is None or floor is None:
        tickers, floor = usu.resolve(root, curated=curated)
    price_through = floor.get("price_through")
    if not tickers:
        return {
            "schema": SCAN_SCHEMA, "tier": "ops_telemetry",
            "authority": "none — coverage measurement only; no rank/gate/size consumer",
            "available": False,
            "null_reason": floor.get("null_reason") or (
                "the liquidity floor admitted no name outside the curated universe"),
            "price_through": price_through, "floor": floor,
            "summary": {}, "runners": [], "excluder_hist": {}, "sector_hist": {},
            "degraded": degraded,
        }

    px = usu.close_panel(root, tickers)
    if px.empty or px.shape[0] < lookback + 2:
        return {
            "schema": SCAN_SCHEMA, "tier": "ops_telemetry",
            "authority": "none — coverage measurement only; no rank/gate/size consumer",
            "available": False,
            "null_reason": (
                f"scan close panel too thin to audit: {px.shape} — needs > {lookback + 1} "
                "sessions"),
            "price_through": price_through, "floor": floor,
            "summary": {}, "runners": [], "excluder_hist": {}, "sector_hist": {},
            "degraded": degraded,
        }

    valid = px.columns[px.notna().sum() >= ct.MIN_HISTORY]
    px = px[valid]
    r63 = (px.iloc[-1] / px.iloc[-(lookback + 1)] - 1).dropna()
    top = r63.sort_values(ascending=False).head(top_n)

    sector = _scan_sector_map(root, degraded)
    rows: list[dict] = []
    for ticker, ret in top.items():
        close = px[ticker].dropna()
        win = eligibility_window(close, lookback)
        att = attribute_excluder(close, eligible_today=bool(win.get("eligible_today")))
        row = {
            "ticker": ticker,
            "r63_pct": round(float(ret) * 100, 1),
            "sector": sector.get(ticker, "?"),
            # THE coverage fact this block exists to print. Always True here by
            # construction (resolve() removes curated names) — stamped anyway so
            # the row is self-describing when it is read outside this artifact.
            "off_index": True,
            "coverage_reason": "not_in_curated_universe",
        }
        row.update(win)
        row.update(att)
        rows.append(row)

    days = [r["days_eligible"] for r in rows if r.get("days_eligible") is not None]
    never = sum(1 for d in days if d == 0)
    summary = {
        "store_n": floor.get("store_n"),
        "floored_n": floor.get("kept_n"),
        "curated_overlap_n": floor.get("curated_overlap_n"),
        "scan_n": floor.get("scan_n"),
        "panel_n": int(px.shape[1]),
        "runners_n": len(rows),
        "runners_eligible_today_n": sum(1 for r in rows if r.get("eligible_today")),
        "runners_never_eligible_n": never,
        "runners_never_eligible_pct": (round(never / len(days), 4) if days else None),
        "runners_eligible_days": _describe([float(d) for d in days]),
    }
    return {
        "schema": SCAN_SCHEMA,
        "tier": "ops_telemetry",
        "authority": "none — coverage measurement only; no rank/gate/size consumer",
        "available": True,
        "null_reason": None,
        "price_through": price_through,
        "floor": floor,
        "bases": {
            "runner_eligibility": "engine.confluence_tiers.tier_stream — the SAME basis as "
                                  "the curated runner rows, so the two tiers are comparable "
                                  "session for session.",
            "universe": "engine.us_scan_universe.resolve over data/massive_stock_day, minus "
                        "the curated universe (the two tiers are disjoint by construction).",
        },
        "summary": summary,
        "excluder_hist": _hist([r["excluder"] for r in rows]),
        "excluder_family_hist": _hist([r["excluder_family"] for r in rows]),
        "sector_hist": _hist([r["sector"] for r in rows]),
        "runners": rows,
        "degraded": degraded,
    }


def _scan_sector_map(root: Path, degraded: list[dict]) -> dict[str, str]:
    """ticker -> GICS sector for scan names, from the polygon reference table.

    Coverage is genuinely partial: ``data/polygon_universe/reference.parquet`` is
    504 rows (S&P 500 + ``us_sector_*`` baskets), so most scan names resolve to
    "?" — which is the honest answer, and is disclosed rather than guessed from
    the ticker.
    """
    p = root / "data" / "polygon_universe" / "reference.parquet"
    try:
        ref = pd.read_parquet(p, columns=["gics_sector"])
    except Exception as exc:  # noqa: BLE001
        degraded.append({"input": "data/polygon_universe/reference.parquet",
                         "severity": "structural",
                         "reason": f"unreadable: {exc} — scan sector histogram collapses to '?'"})
        return {}
    return {str(t): str(s) for t, s in ref["gics_sector"].items() if pd.notna(s)}


def scan_tier_coverage(root: Path = ROOT, degraded: list[dict] | None = None) -> dict:
    """READ the scan-tier artifact for the W0 document. Never recomputes it.

    The scan pass needs a 617 MB store the engine job does not restore, so the W0
    audit mirrors the artifact the post-engine scan lane wrote rather than paying
    for the pass twice. ``asof`` is the scan artifact's OWN ``price_through``, and
    it is reported beside W0's — a reader must be able to see that the two tiers
    can be a session apart, instead of assuming one date for both.
    """
    p = root / SCAN_ARTIFACT_REL
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        if degraded is not None:
            degraded.append({"input": SCAN_ARTIFACT_REL, "severity": "structural",
                             "reason": f"unreadable: {exc} — scan-tier coverage not mirrored "
                                       "tonight (the scan lane writes it post-engine)"})
        return {"available": False, "asof": None,
                "null_reason": f"{SCAN_ARTIFACT_REL} absent or unreadable — "
                               "scan-tier coverage unmeasured in this document"}
    s = doc.get("summary") or {}
    return {
        "available": bool(doc.get("available")),
        "asof": doc.get("price_through"),
        "null_reason": doc.get("null_reason"),
        "floor_rule": (doc.get("floor") or {}).get("rule"),
        "store_n": s.get("store_n"),
        "scan_n": s.get("scan_n"),
        "runners_n": s.get("runners_n"),
        "runners_eligible_today_n": s.get("runners_eligible_today_n"),
        "runners_never_eligible_n": s.get("runners_never_eligible_n"),
        "excluder_family_hist": doc.get("excluder_family_hist") or {},
    }


def name_score_row_fields(doc: dict) -> dict:
    """The name_score scorecard's HEADLINE figures, flattened for the forward-log row.

    Deliberately compact — the full block lives in the artifact; the forward log only needs
    the series a reader would plot: coverage, and each horizon's rank-IC with the number of
    IC dates behind it. ``name_score_available`` is what keeps a null unambiguous once these
    rows accumulate: available + null rank-IC is the ACCRUING state (the block carries the
    plain reason); not-available means the ledger or the forward join failed that night, and
    the artifact's ``degraded`` list names which.

    Null-safe on every path, including a doc with no block at all — this row is written by
    the nightly and must never be the thing that takes the lane down. ``n_ic_dates`` is
    reported beside every rank-IC so a thin cell can never be read as a measurement.
    """
    ns = doc.get("name_score_scorecard") or {}
    by_h = ns.get("by_horizon") or {}
    out: dict = {
        "name_score_available": bool(ns.get("available")),
        "name_score_coverage_pct": (ns.get("forward_store") or {}).get("coverage_pct"),
    }
    for h in nsg._HORIZONS_D:
        cell = by_h.get(f"{h}d") or {}
        out[f"name_score_rank_ic_{h}d"] = cell.get("rank_ic")
        out[f"name_score_ic_dates_{h}d"] = cell.get("n_ic_dates")
    return out


def summary_row(doc: dict) -> dict:
    """The one-line forward-log row: the summary block + the family histogram, keyed by date."""
    s = doc["summary"]
    return {
        "price_through": doc["price_through"],
        "schema": SCHEMA,
        "universe_n": s["universe_n"],
        "eligible_today_n": s["eligible_today_n"],
        "top63_n": s["top63_n"],
        "top63_eligible_today_n": s["top63_eligible_today_n"],
        "top63_never_eligible_n": s["top63_never_eligible_n"],
        "top63_never_eligible_pct": s["top63_never_eligible_pct"],
        "top63_median_eligible_days": s["top63_eligible_days"]["median"],
        "top21_n": s["top21_n"],
        "top21_eligible_today_n": s["top21_eligible_today_n"],
        "sighted_n": doc["conversion"]["sighted_n"],
        "converted_n": doc["conversion"]["converted_n"],
        "conversion_rate": doc["conversion"]["rate"],
        "excluder_family_hist": doc["top63_excluder_family_hist"],
        # Section F: the series §8 of the missed-ignitions masterplan grades
        # sector-grain miss latency against. Names, not just the count — a miss is only
        # actionable if you can see WHICH basket ran unrepresented.
        "basket_scored_n": doc["summary"].get("basket_scored_n"),
        "basket_misses_n": doc["summary"].get("basket_misses_n"),
        "basket_misses": [r["basket_id"] for r in
                          ((doc.get("basket_misses") or {}).get("misses") or [])],
        **name_score_row_fields(doc),
        **scan_tier_row_fields(doc),
        **priority_score_row_fields(doc),
        **entry_status_row_fields(doc),
        "degraded_n": len(doc["degraded"]),
    }


def scan_tier_row_fields(doc: dict) -> dict:
    """The scan-tier headline, flattened for the forward-log row (§4.5).

    ``scan_tier_asof`` rides beside every figure on purpose: this block is
    MIRRORED from a lane that runs after this one, so its date can legitimately
    trail ``price_through``. Without the date in the row, a later reader plotting
    ``scan_tier_scan_n`` over time would silently be plotting a mixture of
    same-night and previous-night values.

    Null-safe on every path, including a doc with no block at all.
    """
    st = doc.get("scan_tier") or {}
    return {
        "scan_tier_available": bool(st.get("available")),
        "scan_tier_asof": st.get("asof"),
        "scan_tier_scan_n": st.get("scan_n"),
        "scan_tier_runners_n": st.get("runners_n"),
        "scan_tier_runners_eligible_today_n": st.get("runners_eligible_today_n"),
        "scan_tier_runners_never_eligible_n": st.get("runners_never_eligible_n"),
    }


# --------------------------------------------------------------------------- #
# alarms — bare print at line start (repo law; tests/test_gh_annotation_line_start.py)
# --------------------------------------------------------------------------- #
def emit_annotations(doc: dict) -> list[str]:
    """Print the ops alarms and return them (for tests). NEVER through a logger.

    GitHub only parses a workflow command when ``::`` is at column 0, and every logger in this
    repo prefixes the line — see tests/test_gh_annotation_line_start.py.
    """
    msgs: list[str] = []
    conv = doc["conversion"]
    rate = conv["rate"]
    if rate is not None and rate < CONVERSION_WARN:
        msgs.append(
            f"sighting->plan conversion {conv['converted_n']}/{conv['sighted_n']} "
            f"({rate * 100:.1f}%) below {CONVERSION_WARN * 100:.0f}% "
            f"(price_through {doc['price_through']})"
        )
    pct = doc["summary"]["top63_never_eligible_pct"]
    if pct is not None and pct > NEVER_ELIGIBLE_WARN:
        msgs.append(
            f"{doc['summary']['top63_never_eligible_n']}/{doc['summary']['top63_n']} "
            f"top-63d runners never eligible in {LOOKBACK} sessions ({pct * 100:.1f}%) — "
            f"above {NEVER_ELIGIBLE_WARN * 100:.0f}% (price_through {doc['price_through']})"
        )
    # Section F: a basket in its own top decile with nobody on the board is the operator's
    # "gold question" — it fires on the FACT, with no threshold of its own, because one
    # unrepresented ignition is the whole event this instrument was built to catch.
    bm = doc.get("basket_misses") or {}
    if bm.get("available") and bm.get("misses"):
        named = ", ".join(
            f"{r['basket_id']} ({r['ew_10d'] * 100:+.1f}% 10d, "
            f"pctile {r['pctile']:.2f}, {r['n_members_live']} members, 0 on board)"
            for r in bm["misses"][:5])
        msgs.append(
            f"{len(bm['misses'])} basket(s) in their own top decile with ZERO members "
            f"on any board lane (as of {bm.get('as_of')}): {named}")
    # Only UNEXPECTED degradations page. The known-structural gap (no theme-level PIT rank
    # archive) is disclosed in the artifact and printed below, but a permanently-firing
    # annotation is alarm fatigue, not signal.
    unexpected = [d for d in doc["degraded"] if d.get("severity") != "structural"]
    if unexpected:
        names = ", ".join(sorted({d["input"] for d in unexpected}))
        msgs.append(f"degraded inputs ({len(unexpected)}): {names}")
    for m in msgs:
        print(f"::warning title=prophet-miss-audit::{m}", flush=True)
    return msgs


# --------------------------------------------------------------------------- #
# forward log — nightly is the SOLE advancer
# --------------------------------------------------------------------------- #
def append_forward_log(doc: dict, path: Path, *, advance: bool) -> bool:
    """Append one summary row. Returns True only when a row was actually written.

    ``advance`` is the ledger gate: False (any non-nightly invocation) writes NOTHING, matching
    the sibling forward ledgers. Idempotent on ``price_through`` — a second nightly run over the
    same caches appends nothing, so a re-render can never double-count a night.
    """
    if not advance:
        return False
    row = summary_row(doc)
    if path.exists():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    prev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if prev.get("price_through") == row["price_through"]:
                    return False
        except OSError:
            pass
    _append_jsonl(path, row)
    return True


def run(*, advance: bool = False, root: Path = ROOT, out_dir: Path | None = None,
        quiet: bool = False, **kwargs: Any) -> dict:
    """Compute → (optionally) write. Returns the artifact document.

    Write policy — three modes, only one of which touches the real store:
      ``advance=True``            nightly: artifact + forward-log append at the real paths.
      ``out_dir=DIR``             local test: artifact + forward log inside DIR.
      neither (the default)       dry run: compute + print, write nothing anywhere.
    """
    doc = build_audit(root, **kwargs)
    if out_dir is not None:
        artifact = Path(out_dir) / "latest.json"
        forward = Path(out_dir) / "forward_log.jsonl"
        advance = True
    else:
        artifact = root / ARTIFACT_REL
        forward = root / FORWARD_LOG_REL
    if advance:
        _atomic_write_json(artifact, doc)
        wrote = append_forward_log(doc, forward, advance=True)
    else:
        wrote = False
    if not quiet:
        print_summary(doc, wrote_artifact=advance, wrote_log=wrote,
                      artifact=(artifact if advance else None))
    emit_annotations(doc)
    return doc


def print_summary(doc: dict, *, wrote_artifact: bool, wrote_log: bool,
                  artifact: Path | None = None) -> None:
    s = doc["summary"]
    conv = doc["conversion"]
    print(f"[prophet-miss-audit] price_through={doc['price_through']} "
          f"universe={s['universe_n']} eligible_today={s['eligible_today_n']} (cascade basis)")
    print(f"  top-{s['top63_n']} 63d runners: eligible today {s['top63_eligible_today_n']}, "
          f"never eligible in {LOOKBACK} sessions {s['top63_never_eligible_n']}, "
          f"median eligible days {s['top63_eligible_days']['median']}")
    print("  EXCLUDERS (top-63d):")
    for k, v in doc["top63_excluder_hist"].items():
        print(f"    {k:44s} {v}")
    print("  EXCLUDERS (top-21d):")
    for k, v in doc["top21_excluder_hist"].items():
        print(f"    {k:44s} {v}")
    rate_txt = "n/a" if conv["rate"] is None else "%.1f%%" % (conv["rate"] * 100)
    print(f"  conversion sighting->plan: {conv['converted_n']}/{conv['sighted_n']} "
          f"({rate_txt}) converted={conv['converted']}")
    print(f"  runner sectors:   {doc['runner_sector_hist']}")
    print(f"  eligible sectors: {doc['eligible_today_sector_hist']}")
    if doc["themes"].get("available"):
        for t in doc["themes"]["themes"]:
            print(f"  theme #{t['rank']} {t['theme']}: {t['n_members']} members, "
                  f"on board {t['present_counts']}")
    bm = doc.get("basket_misses") or {}
    if bm.get("available"):
        print(f"  baskets (as of {bm.get('as_of')}): {bm['n_scored']}/{bm['n_baskets']} "
              f"scored, {bm['n_top_decile']} in own top decile, "
              f"{bm['n_unrepresented']} with nobody on the board, "
              f"{bm['n_misses']} MISS(es)")
        for r in bm["misses"]:
            print(f"    MISS {r['basket_id']:24s} 10d {r['ew_10d'] * 100:+6.1f}%  "
                  f"pctile {r['pctile']:.2f}  members {r['n_members_live']}  on board 0")
        if not bm["misses"]:
            top = bm["baskets"][0] if bm["baskets"] else None
            if top and top.get("pctile") is not None:
                print(f"    no misses — hottest is {top['basket_id']} at pctile "
                      f"{top['pctile']:.2f} with {top['n_members_on_board']} on the board")
    elif bm:
        print(f"  baskets: null — {bm.get('null_reason')}")
    ns = doc.get("name_score_scorecard") or {}
    if ns.get("available"):
        cov = ns.get("forward_store") or {}
        print(f"  name_score ({ns.get('market')}): {ns.get('n_calls')} calls / "
              f"{ns.get('n_stamp_dates')} stamp dates, forward store resolves "
              f"{cov.get('n_names_resolved')}/{cov.get('n_names_stamped')} names "
              f"({cov.get('coverage_pct')}%)")
        for key, h in (ns.get("by_horizon") or {}).items():
            if h.get("null_reason"):
                print(f"    {key}: null — {h['null_reason']}")
                continue
            pk = (h.get("precision_at_k") or {}).get("by_k") or {}
            p1 = (pk.get("p_at_1") or {}).get("value")
            p5 = (pk.get("p_at_5") or {}).get("value")
            print(f"    {key}: rank_ic={h.get('rank_ic')} over {h.get('n_ic_dates')} IC "
                  f"date(s), n={h.get('n_graded')}, P@1={p1} P@5={p5}"
                  f"{'  [THIN]' if h.get('thin') else ''}")
    elif ns:
        print(f"  name_score: null — {ns.get('null_reason')}")
    st = doc.get("scan_tier") or {}
    if st.get("available"):
        stale = "" if st.get("asof") == doc["price_through"] else \
            f"  [asof {st.get('asof')} — trails this document]"
        print(f"  scan tier: {st.get('scan_n')} off-index names seen, "
              f"{st.get('runners_n')} runners, "
              f"{st.get('runners_eligible_today_n')} eligible today, "
              f"{st.get('runners_never_eligible_n')} never eligible{stale}")
    elif st:
        print(f"  scan tier: null — {st.get('null_reason')}")
    ps = doc.get("priority_score_scorecard") or {}
    if ps.get("available"):
        cov = ps.get("score_coverage") or {}
        split = ps.get("cohort_split") or {}
        print(f"  priority_score: {cov.get('n_rows')} graded row(s), "
              f"{cov.get('n_scored')} carry a stamped score ({cov.get('coverage_pct')}%); "
              f"cohorts {split.get('n_by_cohort') or 'UNSPLIT'}")
        for cohort, legs in (ps.get("by_cohort") or {}).items():
            print(f"    [{cohort}]")
            for key, h in legs.items():
                pop = h.get("population") or {}
                classes = h.get("by_signal_class") or {}
                class_txt = " ".join(
                    f"{c}:n={v.get('n')}/x={v.get('mean_excess')}"
                    for c, v in sorted(classes.items()))
                if h.get("null_reason"):
                    print(f"      {key}: null — {h['null_reason']} "
                          f"(population n={pop.get('n')}, mean excess "
                          f"{pop.get('mean_excess')}) {class_txt}")
                    continue
                pk = (h.get("precision_at_k") or {}).get("by_k") or {}
                dec = h.get("deciles") or {}
                print(f"      {key}: rank_ic={h.get('rank_ic')} over "
                      f"{h.get('n_ic_dates')} IC date(s), scored n={h.get('n_scored')} of "
                      f"{h.get('n_graded')} graded, "
                      f"P@1={(pk.get('p_at_1') or {}).get('value')} "
                      f"P@10={(pk.get('p_at_10') or {}).get('value')}, "
                      f"d10-d1={dec.get('top_minus_bottom_excess')}"
                      f"{'  [THIN]' if h.get('thin') else ''} {class_txt}")
    elif ps:
        print(f"  priority_score: null — {ps.get('null_reason')}")
    # §6.6: the entry-status table renders itself — the owning module holds the one
    # definition of how its cells read, so this file never restates them.
    try:
        from engine import us_entry_status_remeasure as _uesr
        for line in _uesr.summary_lines(doc.get("entry_status_scorecard")):
            print(line)
    except Exception:  # noqa: BLE001 — a summary print must never fail a nightly
        es = doc.get("entry_status_scorecard") or {}
        print(f"  entry_status: null — {es.get('null_reason') or 'unavailable'}")
    if doc["degraded"]:
        print(f"  DEGRADED ({len(doc['degraded'])}):")
        for d in doc["degraded"]:
            print(f"    {d['input']}: {d['reason']}")
    where = (" -> %s" % artifact) if artifact else ""
    print(f"  writes: artifact={'yes' if wrote_artifact else 'NO (not nightly)'}{where}, "
          f"forward_log={'appended' if wrote_log else 'no append'}")
