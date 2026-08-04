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

ARTIFACT_REL = "data/prophet_miss_audit/latest.json"
FORWARD_LOG_REL = "data/prophet_miss_audit/forward_log.jsonl"

TOP63_N = 150          # top runners by 63-session return
TOP21_N = 50           # top fast movers by 21-session return
LOOKBACK = 63          # eligibility window, in sessions
THEME_TOP_N = 5        # themes graded for representation latency
STANDOUT_LANES = ("buy", "ran", "leaders")

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
# E. name_score scorecard — read-only mirror of the nightly grader's own outputs
# --------------------------------------------------------------------------- #
def name_score_series_reader(market: str = NAME_SCORE_MARKET) -> Callable[[str], pd.Series | None]:
    """A per-ticker MEMOIZED close-series resolver, identical to the resolution half of
    ``engine.name_score_grader._fwd_return``.

    WHY THIS EXISTS (runtime, not method). ``grade()`` resolves the series inside a
    per-(row, horizon) loop, so a 72k-row ledger costs ~145k parquet reads — MEASURED at
    13.4 minutes and rising with every night's stamp, which is a fifth of the whole render
    budget for telemetry no gate reads. The ledger's 72k rows span only ~3k tickers, so
    reading each name ONCE and reusing the series makes the same computation cost ~3s. The
    read count is bounded by the UNIVERSE (stable), not by ledger depth (accruing), so this
    stays cheap as the ledger grows.

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
                with_cascade_basis: bool = True, with_name_score: bool = True) -> dict:
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
    name_score = (name_score_scorecard(root, degraded) if with_name_score else
                  {"tier": "ops_telemetry", "available": False,
                   "null_reason": "not computed (with_name_score=False)"})

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
    }

    doc = {
        "schema": SCHEMA,
        "price_through": price_through,
        "tier": "ops_telemetry",
        "authority": "none — measurement only; no rank/gate/size consumer",
        "bases": {
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
        "name_score_scorecard": name_score,
        "top63_runners": runner_rows,
        "top21_runners": fast_rows,
        "eligible_today": cascade_elig,
        "degraded": degraded,
    }
    return doc


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
        "degraded_n": len(doc["degraded"]),
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
    if doc["degraded"]:
        print(f"  DEGRADED ({len(doc['degraded'])}):")
        for d in doc["degraded"]:
            print(f"    {d['input']}: {d['reason']}")
    where = (" -> %s" % artifact) if artifact else ""
    print(f"  writes: artifact={'yes' if wrote_artifact else 'NO (not nightly)'}{where}, "
          f"forward_log={'appended' if wrote_log else 'no append'}")
