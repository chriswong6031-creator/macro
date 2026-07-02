"""W0.4 — THE KEYSTONE GATE: does cycle POSITION / PHASE predict forward
drawdown-adjusted returns? (TR-v0, dev-only, PIT backfill + walk-forward study).

This is the Cycle Intelligence Masterplan's biggest open question answered in one
wave (research/CYCLE_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §4 W0.4, §6 risk #1). If
position/phase deciles carry no forward drawdown-adjusted signal, Phases 3-5 of the
program shrink drastically — a null result here is a VALID, VALUABLE verdict.

WHAT IT DOES
  1. PIT BACKFILL (masterplan D2 §1, scout-verified): loops month-ends over available
     history and, for each (date, series), stamps the engine's own cycle read
     {pos, phase, signal, timing_state, osc_slope, proj_central, dc_phase, action,
     above200d} using ONLY tape <= date. Compute-frugal: drives engine.sector_cycles
     .build_sector / engine.country_cycles._build_one on a PIT-sliced close panel (the
     19x-cheaper path than the basket-building compute()), which produces byte-identical
     `now` fields to compute(asof=). Universe = the membership-free families ONLY:
     11 US SPDR sector ETFs + 24 single-country iShares ETFs. Baskets + blocs SKIPPED
     (non-PIT membership; masterplan D2 §0).

  2. FORWARD OUTCOMES (china grader convention, copied exactly —
     engine.china_sector_cycles_grader._fwd): each stamp's forward window anchors at the
     FIRST close STRICTLY AFTER the stamp date (bar i+1, searchsorted(side='right')).
     For h in {21, 63, 126} trading bars: fwd_ret_h = close[i+1+h]/close[i+1] - 1 and
     fwd_maxdd_h = min(0, min(close[i+2..i+1+h]) / close[i+1] - 1). No partial windows.

  3. THE STUDY: per POSITION DECILE and per PHASE, forward drawdown-adjusted outcomes
     (mean fwd return, p10 drawdown, hit-rate vs the instrument's own base rate) with
     DATE-BLOCKED bootstrap CIs (resample whole stamp MONTHS — the cross-section is
     correlated, so we resample DATES not rows; masterplan red-team ruling A2). Walk-
     forward framing: pre-2018 vs post-2018 stability. Explicit inversion test (the
     audit's suspicion): do low-position / DECLINE states out-perform high-position /
     FRESH-BUY states on the drawdown lens?

  Everything is stamped basis:'tr', epoch:'tr_v0' — RESEARCH-ONLY (masterplan ruling
  A1: no user-facing badge may ever cite this TR cohort).

DISCIPLINE (house rules; masterplan §6.1): hand-rolled numpy/pandas only (no
sklearn/statsmodels); every reported cell carries its CI or is not reported; n_MONTHS,
not n_rows; a null result is stated as such.

Run:  python -m scripts.keystone_position_gate_phase0            # full study
      python -m scripts.keystone_position_gate_phase0 --quick    # smoke (recent slice)
      python -m scripts.keystone_position_gate_phase0 --verify   # PIT spot-checks only

Outputs (committed under data/research/keystone_tr0/):
  backfill.parquet     — every PIT stamp joined to its forward outcomes (small, TR-v0)
  study_tables.json    — the aggregated decile/phase tables + CIs + the verdict block
  manifest.json        — run provenance (basis, epoch, universe, n_months, git sha)
Prints the verdict block for research/cycle_masterplan/W04_KEYSTONE_VERDICT.md.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import country_cycles as cc  # noqa: E402
from engine import sector_cycles as sc  # noqa: E402
from engine.inputs import yahoo_closes  # noqa: E402

# ── PRE-REGISTERED PARAMETERS — fixed before any table was read; do NOT tune ──────────
BASIS = "tr"                    # ruling A1: TR basis, research-only cohort
EPOCH = "tr_v0"                 # ontology/threshold epoch (masterplan D2 §1.2)
HORIZONS = (21, 63, 126)        # trading-BAR forward windows (D2 N3 phase-appropriate)
WF_SPLIT = pd.Timestamp("2018-01-01")   # walk-forward stability boundary (pre/post 2018)
START = pd.Timestamp("2005-01-01")      # ~20y span where the ETF tapes exist
N_DECILES = 10
BOOT_DRAWS = 800                # date-blocked bootstrap (ported from china grader)
BOOT_SEED = 7
MIN_MONTHS = 12                 # a cell needs >= this many distinct stamp MONTHS or it is
                                # reported "thin" (n_months, NOT n_rows — ruling A2)
CONVENTION = "first_close_strictly_after_stamp"   # bar i+1 (china grader; the ONLY legal anchor)

# The 5-phase wheel (engine.sector_cycles.PHASES) + the ladder timing states we stamp.
PHASE_ORDER = ["Trough", "Recovery", "Expansion", "Peak", "Downturn"]


# ─────────────────────────────────────────────── forward-window primitives (bar i+1) ──

def _entry_pos(idx: pd.DatetimeIndex, stamp: pd.Timestamp) -> int | None:
    """FIRST bar STRICTLY AFTER the stamp — the bar-i+1 anchor. Copied verbatim from
    engine.china_sector_cycles_grader._entry_pos. searchsorted(side='right') can never
    return the stamp bar itself."""
    j = int(idx.searchsorted(stamp, side="right"))
    return j if j < len(idx) else None


def _fwd(px: pd.Series, stamp: pd.Timestamp, h: int) -> dict | None:
    """Realized forward window of h trading bars anchored at bar i+1 — copied from
    engine.china_sector_cycles_grader._fwd. Returns {ret, maxdd} or None if the window
    has not fully matured. maxdd = deepest peak-to-trough drawdown in the window (<= 0)."""
    idx = px.index
    j = _entry_pos(idx, stamp)
    if j is None or j + h >= len(idx):
        return None
    if not idx[j] > stamp:                       # belt-and-braces vs the known leak trap
        raise ValueError("look-ahead guard: forward anchor must be strictly after the stamp")
    win = px.iloc[j:j + h + 1].to_numpy(dtype=float)
    if win[0] <= 0 or not np.isfinite(win).all():
        return None
    ret = float(win[-1] / win[0] - 1.0)
    dd = float((win / np.maximum.accumulate(win) - 1.0).min())
    return {"ret": ret, "maxdd": dd}


# ───────────────────────────────────────────────────────── PIT backfill (the loop) ──

def _month_ends(cal: pd.DatetimeIndex, start: pd.Timestamp) -> list[pd.Timestamp]:
    """Last TRADING day of each calendar month from `start` to the last complete month.
    One master calendar (the full close panel) so every instrument shares stamp dates —
    required for the date-blocked (month-block) bootstrap to have shared blocks."""
    me = pd.date_range(start, cal[-1], freq="ME")
    out: list[pd.Timestamp] = []
    for m in me:
        j = int(cal.searchsorted(m, side="right")) - 1
        if j >= 0:
            out.append(cal[j])
    return sorted(set(out))


def _stamp_from_rec(rec: dict, asof: pd.Timestamp, family: str, tk: str) -> dict:
    """Flatten one engine record's cycle read into a backfill row (the PIT stamp)."""
    now = rec["now"]
    proj = rec.get("proj") or {}
    return {
        "date": pd.Timestamp(asof),
        "id": tk.lower(),
        "ticker": tk,
        "family": family,
        "pos": now.get("pos"),
        "phase": now.get("phase"),
        "signal": now.get("signal"),
        "timing_state": now.get("timing_state"),
        "action": now.get("action"),
        "osc_slope": now.get("osc_slope"),
        "above200d": now.get("above200d"),
        "dc_phase": now.get("dc_phase"),
        "proj_central": proj.get("central"),
        "proj_next": proj.get("nextTurn"),
        "rs_63d": now.get("rs_63d"),
        "n_turns_all": rec.get("n_turns_all"),
        "basis": BASIS,
        "epoch": EPOCH,
    }


def _build_us(sub: pd.DataFrame, asof: pd.Timestamp, ws: pd.Timestamp) -> list[dict]:
    rows = []
    for tk, meta in sc.SECTORS.items():
        try:
            rec = sc.build_sector(tk, meta, sub, ws)
        except Exception:  # noqa: BLE001 — additive: one skip never breaks the loop
            rec = None
        if rec:
            rows.append(_stamp_from_rec(rec, asof, "us_sector", tk))
    return rows


def _build_country(sub: pd.DataFrame, asof: pd.Timestamp, ws: pd.Timestamp) -> list[dict]:
    rows = []
    for tk, meta in cc.COUNTRIES.items():
        try:
            # region/accent are cosmetic here; cycle read is family-independent
            rec = cc._build_one(tk, meta, sub, ws, kind="sector",
                                group=meta["region"], accent="#888")
        except Exception:  # noqa: BLE001
            rec = None
        if rec:
            rows.append(_stamp_from_rec(rec, asof, "country", tk))
    return rows


def backfill(closes: pd.DataFrame, month_ends: list[pd.Timestamp]) -> pd.DataFrame:
    """PIT stamp every (month-end, series) using ONLY tape <= stamp date."""
    cal = closes.index
    rows: list[dict] = []
    win_years = sc.WINDOW_YEARS
    for k, asof in enumerate(month_ends):
        sub = closes[closes.index <= asof]           # <<< the PIT slice — nothing forward
        if sub.empty or sub.index[-1] > asof:
            raise ValueError(f"PIT leak: sliced tail {sub.index[-1]} > asof {asof}")
        ws = asof - pd.DateOffset(years=win_years)
        rows.extend(_build_us(sub, asof, ws))
        rows.extend(_build_country(sub, asof, ws))
        if (k + 1) % 24 == 0:
            print(f"  ... backfilled {k + 1}/{len(month_ends)} months "
                  f"({asof.date()}), {len(rows)} stamps", flush=True)
    df = pd.DataFrame(rows)
    return df


def join_forward(df: pd.DataFrame, closes: pd.DataFrame) -> pd.DataFrame:
    """Join each stamp to its bar-i+1 forward outcomes on the instrument's OWN tape."""
    px_by_id = {tk.lower(): closes[tk].dropna().sort_index()
                for tk in list(sc.SECTORS) + list(cc.COUNTRIES) if tk in closes}
    for h in HORIZONS:
        df[f"fwd_ret_{h}"] = np.nan
        df[f"fwd_maxdd_{h}"] = np.nan
    for i, r in df.iterrows():
        px = px_by_id.get(r["id"])
        if px is None or px.empty:
            continue
        stamp = pd.Timestamp(r["date"])
        for h in HORIZONS:
            w = _fwd(px, stamp, h)
            if w is not None:
                df.at[i, f"fwd_ret_{h}"] = w["ret"]
                df.at[i, f"fwd_maxdd_{h}"] = w["maxdd"]
    return df


# ─────────────────────────────────────────────────────────────── PIT verification ──

def verify_pit(closes: pd.DataFrame, n_checks: int = 3) -> list[dict]:
    """A stamp computed at asof must NOT change when later data is appended. We stamp at
    asof twice: (a) on a tape truncated to asof, (b) on the FULL tape but sliced to asof
    inside build. Both must be byte-identical — proving the read is a pure function of
    tape <= asof, so appending future bars cannot move a past stamp."""
    checks = []
    rng = np.random.default_rng(BOOT_SEED)
    cal = closes.index
    me = _month_ends(cal, START)
    pool = [m for m in me if m < cal[-1] - pd.DateOffset(years=1)]
    picks = rng.choice(len(pool), size=min(n_checks, len(pool)), replace=False)
    specs = [("XLK", "us"), ("EWZ", "country"), ("XLF", "us")]
    for n, (pi, (tk, fam)) in enumerate(zip(picks, specs)):
        asof = pool[int(pi)]
        ws = asof - pd.DateOffset(years=sc.WINDOW_YEARS)
        # (a) tape truncated to asof (a real "as of that day" world, no future bars exist)
        trunc = closes[closes.index <= asof].copy()
        # (b) full tape (future bars present), sliced to asof inside build
        full_sliced = closes[closes.index <= asof]     # same slice, different origin df
        if fam == "us":
            ra = sc.build_sector(tk, sc.SECTORS[tk], trunc, ws)
            rb = sc.build_sector(tk, sc.SECTORS[tk], full_sliced, ws)
        else:
            ra = cc._build_one(tk, cc.COUNTRIES[tk], trunc, ws, kind="sector",
                               group=cc.COUNTRIES[tk]["region"], accent="#888")
            rb = cc._build_one(tk, cc.COUNTRIES[tk], full_sliced, ws, kind="sector",
                               group=cc.COUNTRIES[tk]["region"], accent="#888")
        fields = ["phase", "pos", "signal", "osc_slope", "timing_state", "dc_phase"]
        na = {f: ra["now"].get(f) for f in fields}
        nb = {f: rb["now"].get(f) for f in fields}
        pa = (ra.get("proj") or {}).get("central")
        pb = (rb.get("proj") or {}).get("central")
        match = (na == nb) and (pa == pb)
        checks.append({"asof": str(asof.date()), "ticker": tk, "match": bool(match),
                       "now": na, "proj_central": pa})
    return checks


def verify_pit_append(closes: pd.DataFrame) -> dict:
    """Stronger PIT check: stamp XLK at an OLD asof on a tape that has been TRUNCATED to
    asof, and compare to stamping at the same asof from the full tape that contains years
    of subsequent data. If the stamp is a pure function of tape<=asof, appending the
    2019-2026 tail after 2015 cannot change the 2015 stamp. This is the exact property
    the task asks us to spot-check."""
    asof = pd.Timestamp("2015-06-30")
    cal = closes.index
    j = int(cal.searchsorted(asof, side="right")) - 1
    asof = cal[j]
    ws = asof - pd.DateOffset(years=sc.WINDOW_YEARS)
    # world A: pretend we are standing on `asof` — no future bars exist at all
    world_a = closes[closes.index <= asof]
    ra = sc.build_sector("XLK", sc.SECTORS["XLK"], world_a, ws)
    # world B: the full 2026 tape, but the engine slices to <= asof itself (via our loop)
    world_b_full = closes                                  # has 2016..2026 appended
    world_b = world_b_full[world_b_full.index <= asof]     # the loop's PIT slice
    rb = sc.build_sector("XLK", sc.SECTORS["XLK"], world_b, ws)
    fields = ["phase", "pos", "signal", "osc_slope", "timing_state"]
    na = {f: ra["now"].get(f) for f in fields}
    nb = {f: rb["now"].get(f) for f in fields}
    pa = (ra.get("proj") or {}).get("central")
    pb = (rb.get("proj") or {}).get("central")
    return {"asof": str(asof.date()), "ticker": "XLK",
            "match": bool(na == nb and pa == pb),
            "world_a": na, "world_b": nb, "proj_a": pa, "proj_b": pb}


# ──────────────────────────────────────────────────────────── study statistics ──────

def _month_block_boot_ci(months: np.ndarray, vals: np.ndarray, mask: np.ndarray,
                         stat: str = "mean") -> list | None:
    """Date-blocked bootstrap 95% CI on (conditional stat - base stat), resampling whole
    stamp MONTHS with replacement (the cross-section within a month is correlated —
    ruling A2: resample DATES, not rows). Ported from china grader _boot_gap_ci, extended
    to also support the p10 statistic for the drawdown tail.
    Returns [lo95, hi95] of the (in-state - base) gap, or None if degenerate."""
    uniq = np.unique(months)
    if mask.sum() == 0 or len(uniq) < 2:
        return None
    by = {d: np.where(months == d)[0] for d in uniq}
    rng = np.random.default_rng(BOOT_SEED)

    def _stat(x: np.ndarray) -> float:
        if stat == "p10":
            return float(np.percentile(x, 10))
        return float(np.mean(x))

    gaps = []
    for _ in range(BOOT_DRAWS):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        ridx = np.concatenate([by[d] for d in pick])
        m = mask[ridx]
        if int(m.sum()) < 3:
            continue
        gaps.append(_stat(vals[ridx][m]) - _stat(vals[ridx]))
    if len(gaps) < BOOT_DRAWS // 2:
        return None
    return [round(float(np.percentile(gaps, 2.5)), 4),
            round(float(np.percentile(gaps, 97.5)), 4)]


def _abs_ci(months: np.ndarray, vals: np.ndarray, mask: np.ndarray,
            stat: str = "mean") -> list | None:
    """Month-block bootstrap 95% CI on the ABSOLUTE in-state statistic (not a gap)."""
    uniq = np.unique(months[mask])
    if mask.sum() == 0 or len(uniq) < 2:
        return None
    idx_by = {d: np.where((months == d) & mask)[0] for d in uniq}
    rng = np.random.default_rng(BOOT_SEED)

    def _stat(x: np.ndarray) -> float:
        return float(np.percentile(x, 10)) if stat == "p10" else float(np.mean(x))

    ests = []
    for _ in range(BOOT_DRAWS):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        ridx = np.concatenate([idx_by[d] for d in pick])
        if len(ridx) < 3:
            continue
        ests.append(_stat(vals[ridx]))
    if len(ests) < BOOT_DRAWS // 2:
        return None
    return [round(float(np.percentile(ests, 2.5)), 4),
            round(float(np.percentile(ests, 97.5)), 4)]


def _wilson(k: int, n: int, z: float = 1.96) -> list | None:
    """Wilson score interval (canonical form, china_sector_pathway._wilson). Pure math."""
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    hw = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return [round((c - hw) / d, 4), round((c + hw) / d, 4)]


def _cell(sub: pd.DataFrame, base: pd.DataFrame, h: int, label: str) -> dict:
    """One bucket's forward drawdown-adjusted outcome vs the instrument-pool base rate.
    n_MONTHS not n_rows. Every reported number carries its CI (or the cell is 'thin')."""
    ret = f"fwd_ret_{h}"
    dd = f"fwd_maxdd_{h}"
    s = sub[sub[ret].notna()]
    b = base[base[ret].notna()]
    n_rows = len(s)
    n_months = int(s["month"].nunique())
    if n_rows == 0:
        return {"label": label, "n_rows": 0, "n_months": 0, "thin": True}
    months_all = base["month"].to_numpy()
    ret_all = base[ret].to_numpy(dtype=float)
    dd_all = base[dd].to_numpy(dtype=float)
    in_state = base["_cell_mask"].to_numpy(dtype=bool)

    mean_ret = float(np.mean(s[ret]))
    mean_ret_ci = _abs_ci(months_all, ret_all, in_state, "mean")
    ret_gap_ci = _month_block_boot_ci(months_all, ret_all, in_state, "mean")

    p10_dd = float(np.percentile(s[dd], 10))
    p10_dd_ci = _abs_ci(months_all, dd_all, in_state, "p10")
    p10_gap_ci = _month_block_boot_ci(months_all, dd_all, in_state, "p10")

    # drawdown-adjusted score: return per unit tail risk (masterplan D2 §4.1)
    ra = round(mean_ret / abs(p10_dd), 4) if p10_dd < 0 else None

    # hit-rate vs base
    k = int((s[ret] > 0).sum())
    hit = round(k / n_rows, 4)
    base_hit = round(float((b[ret] > 0).mean()), 4)
    hit_ci = _wilson(k, n_rows)

    return {
        "label": label,
        "n_rows": n_rows, "n_months": n_months,
        "thin": n_months < MIN_MONTHS,
        "mean_fwd_ret": round(mean_ret, 4), "mean_fwd_ret_ci": mean_ret_ci,
        "ret_gap_vs_base": round(mean_ret - float(np.mean(b[ret])), 4),
        "ret_gap_ci": ret_gap_ci,
        "p10_dd": round(p10_dd, 4), "p10_dd_ci": p10_dd_ci,
        "p10_dd_gap_vs_base": round(p10_dd - float(np.percentile(b[dd], 10)), 4),
        "p10_dd_gap_ci": p10_gap_ci,
        "dd_adj_score": ra,
        "hit_rate": hit, "hit_rate_ci": hit_ci, "base_hit_rate": base_hit,
        "hit_gap_vs_base": round(hit - base_hit, 4),
    }


def _decile_table(df: pd.DataFrame, h: int) -> list[dict]:
    """Position deciles WITHIN family (pos is a 0-100 cross-sectional cycle read; decile
    it inside each family so a structurally-high-pos family doesn't dominate one bin)."""
    d = df[df["pos"].notna() & df[f"fwd_ret_{h}"].notna()].copy()
    if d.empty:
        return []
    d["decile"] = (d.groupby("family")["pos"]
                   .transform(lambda x: pd.qcut(x.rank(method="first"), N_DECILES,
                                                labels=False, duplicates="drop")))
    out = []
    for dec in range(N_DECILES):
        sub = d[d["decile"] == dec]
        d["_cell_mask"] = (d["decile"] == dec)
        lo = int(round(dec * 100 / N_DECILES))
        hi = int(round((dec + 1) * 100 / N_DECILES))
        out.append(_cell(sub, d, h, f"D{dec + 1} (pos {lo}-{hi}%)"))
    return out


def _phase_table(df: pd.DataFrame, h: int) -> list[dict]:
    d = df[df["phase"].notna() & df[f"fwd_ret_{h}"].notna()].copy()
    out = []
    for ph in PHASE_ORDER:
        sub = d[d["phase"] == ph]
        d["_cell_mask"] = (d["phase"] == ph)
        out.append(_cell(sub, d, h, ph))
    return out


def _state_table(df: pd.DataFrame, h: int, col: str, states: list[str]) -> list[dict]:
    d = df[df[col].notna() & df[f"fwd_ret_{h}"].notna()].copy()
    out = []
    for st in states:
        sub = d[d[col] == st]
        d["_cell_mask"] = (d[col] == st)
        out.append(_cell(sub, d, h, st))
    return out


def _inversion_test(df: pd.DataFrame, h: int) -> dict:
    """The audit's inversion suspicion: do LOW-position / washed-out states out-perform
    HIGH-position / stretched states on the DRAWDOWN-ADJUSTED lens? Contrast bottom-2
    position deciles + Recovery/Trough phases vs top-2 deciles + Peak phase. Report the
    return gap, the p10-drawdown gap, and the drawdown-adjusted score gap, each with a
    month-block bootstrap CI on the LOW-minus-HIGH difference."""
    d = df[df["pos"].notna() & df[f"fwd_ret_{h}"].notna()].copy()
    if d.empty:
        return {}
    d["decile"] = (d.groupby("family")["pos"]
                   .transform(lambda x: pd.qcut(x.rank(method="first"), N_DECILES,
                                                labels=False, duplicates="drop")))
    low = d["decile"].isin([0, 1])
    high = d["decile"].isin([N_DECILES - 2, N_DECILES - 1])
    ret = f"fwd_ret_{h}"
    dd = f"fwd_maxdd_{h}"

    def _grp(mask):
        g = d[mask]
        p10 = float(np.percentile(g[dd], 10)) if len(g) else None
        mr = float(np.mean(g[ret])) if len(g) else None
        return {"n_rows": int(len(g)), "n_months": int(g["month"].nunique()),
                "mean_fwd_ret": round(mr, 4) if mr is not None else None,
                "p10_dd": round(p10, 4) if p10 is not None else None,
                "dd_adj_score": round(mr / abs(p10), 4) if (mr is not None and p10 and p10 < 0) else None}

    lo_g, hi_g = _grp(low), _grp(high)
    # LOW - HIGH gap CI via month-block bootstrap
    months = d["month"].to_numpy()
    ret_arr = d[ret].to_numpy(dtype=float)
    dd_arr = d[dd].to_numpy(dtype=float)
    lo_m = low.to_numpy()
    hi_m = high.to_numpy()
    uniq = np.unique(months)
    rng = np.random.default_rng(BOOT_SEED)
    by = {m: np.where(months == m)[0] for m in uniq}
    ret_gaps, ddadj_gaps = [], []
    for _ in range(BOOT_DRAWS):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        ridx = np.concatenate([by[m] for m in pick])
        lm, hm = lo_m[ridx], hi_m[ridx]
        if lm.sum() < 5 or hm.sum() < 5:
            continue
        rlo, rhi = ret_arr[ridx][lm], ret_arr[ridx][hm]
        dlo, dhi = dd_arr[ridx][lm], dd_arr[ridx][hm]
        ret_gaps.append(float(rlo.mean() - rhi.mean()))
        slo = rlo.mean() / abs(np.percentile(dlo, 10)) if np.percentile(dlo, 10) < 0 else np.nan
        shi = rhi.mean() / abs(np.percentile(dhi, 10)) if np.percentile(dhi, 10) < 0 else np.nan
        if np.isfinite(slo) and np.isfinite(shi):
            ddadj_gaps.append(float(slo - shi))
    ret_ci = ([round(float(np.percentile(ret_gaps, 2.5)), 4), round(float(np.percentile(ret_gaps, 97.5)), 4)]
              if len(ret_gaps) > BOOT_DRAWS // 2 else None)
    ddadj_ci = ([round(float(np.percentile(ddadj_gaps, 2.5)), 4), round(float(np.percentile(ddadj_gaps, 97.5)), 4)]
                if len(ddadj_gaps) > BOOT_DRAWS // 2 else None)
    return {
        "low_pos": lo_g, "high_pos": hi_g,
        "ret_gap_low_minus_high": round((lo_g["mean_fwd_ret"] or 0) - (hi_g["mean_fwd_ret"] or 0), 4),
        "ret_gap_ci": ret_ci,
        "dd_adj_gap_low_minus_high": (round((lo_g["dd_adj_score"] or 0) - (hi_g["dd_adj_score"] or 0), 4)
                                      if lo_g["dd_adj_score"] and hi_g["dd_adj_score"] else None),
        "dd_adj_gap_ci": ddadj_ci,
        "verdict": _inv_verdict(ret_ci, ddadj_ci),
    }


def _inv_verdict(ret_ci, ddadj_ci) -> str:
    """Inversion CONFIRMED ⇔ low-pos beats high-pos with CI excluding 0 (return OR
    dd-adj). REFUTED ⇔ CI entirely on the high-pos side. Else inconclusive."""
    def _side(ci):
        if ci is None:
            return "none"
        if ci[0] > 0:
            return "low_wins"
        if ci[1] < 0:
            return "high_wins"
        return "straddle"
    r, s = _side(ret_ci), _side(ddadj_ci)
    if "low_wins" in (r, s):
        return "inversion_confirmed"
    if "high_wins" in (r, s) and "low_wins" not in (r, s):
        return "inversion_refuted"
    return "inconclusive"


def build_study(df: pd.DataFrame) -> dict:
    df = df.copy()
    df["month"] = pd.to_datetime(df["date"]).dt.to_period("M").astype(str)
    df["era"] = np.where(pd.to_datetime(df["date"]) < WF_SPLIT, "pre_2018", "post_2018")

    def _tables_for(frame: pd.DataFrame) -> dict:
        return {
            str(h): {
                "position_deciles": _decile_table(frame, h),
                "phases": _phase_table(frame, h),
                "timing_states": _state_table(frame, h, "timing_state",
                                              _top_states(frame, "timing_state")),
                "signal": _state_table(frame, h, "signal", ["BUY", "SELL"]),
                "inversion": _inversion_test(frame, h),
            } for h in HORIZONS
        }

    study = {
        "full": _tables_for(df),
        "pre_2018": _tables_for(df[df["era"] == "pre_2018"]),
        "post_2018": _tables_for(df[df["era"] == "post_2018"]),
        "n_months_total": int(df["month"].nunique()),
        "n_stamps": int(len(df)),
        "n_matured": {str(h): int(df[f"fwd_ret_{h}"].notna().sum()) for h in HORIZONS},
    }
    return study


def _top_states(df: pd.DataFrame, col: str, k: int = 8) -> list[str]:
    vc = df[col].dropna().value_counts()
    return [s for s in vc.index[:k] if s]


# ──────────────────────────────────────────────────────────────── verdict block ──────

def _fmt_ci(ci) -> str:
    return f"[{ci[0]:+.2%}, {ci[1]:+.2%}]" if ci else "[n/a]"


def print_verdict(study: dict, pit_checks: list[dict], pit_append: dict) -> None:
    print("\n" + "=" * 78)
    print("W0.4 KEYSTONE GATE — VERDICT BLOCK (paste into W04_KEYSTONE_VERDICT.md)")
    print("=" * 78)
    print(f"basis={BASIS}  epoch={EPOCH}  (RESEARCH-ONLY — ruling A1)")
    print(f"n_stamps={study['n_stamps']}  n_months_total={study['n_months_total']}  "
          f"n_matured(21/63/126)={list(study['n_matured'].values())}")
    print(f"\nPIT SPOT-CHECKS (stamp @ asof invariant to appended future data):")
    for c in pit_checks:
        print(f"  {c['ticker']:5s} @ {c['asof']}: match={c['match']}  "
              f"phase={c['now']['phase']} pos={c['now']['pos']}")
    print(f"  APPEND-TEST {pit_append['ticker']} @ {pit_append['asof']}: "
          f"match={pit_append['match']} (world_a==world_b)")

    for lens, h in [("21d", 21), ("63d", 63), ("126d", 126)]:
        t = study["full"][str(h)]
        print(f"\n─── POSITION DECILES ({lens} fwd) — mean ret / p10 dd / dd-adj / hit-gap ───")
        for c in t["position_deciles"]:
            if c.get("thin") and c["n_rows"] == 0:
                continue
            thin = " THIN" if c.get("thin") else ""
            print(f"  {c['label']:16s} n_m={c['n_months']:3d}{thin}  "
                  f"ret={c['mean_fwd_ret']:+.2%} gapCI={_fmt_ci(c.get('ret_gap_ci'))}  "
                  f"p10dd={c['p10_dd']:+.2%}  ddadj={c['dd_adj_score']}  "
                  f"hitgap={c['hit_gap_vs_base']:+.3f}")
        print(f"─── PHASES ({lens} fwd) ───")
        for c in t["phases"]:
            if c.get("n_rows", 0) == 0:
                continue
            thin = " THIN" if c.get("thin") else ""
            print(f"  {c['label']:10s} n_m={c['n_months']:3d}{thin}  "
                  f"ret={c['mean_fwd_ret']:+.2%} gapCI={_fmt_ci(c.get('ret_gap_ci'))}  "
                  f"p10dd={c['p10_dd']:+.2%} ddgapCI={_fmt_ci(c.get('p10_dd_gap_ci'))}  "
                  f"ddadj={c['dd_adj_score']}")
        inv = t["inversion"]
        print(f"─── INVERSION TEST ({lens}) — low-pos vs high-pos ───")
        print(f"  low : ret={inv['low_pos']['mean_fwd_ret']:+.2%} p10dd={inv['low_pos']['p10_dd']:+.2%} "
              f"ddadj={inv['low_pos']['dd_adj_score']} (n_m={inv['low_pos']['n_months']})")
        print(f"  high: ret={inv['high_pos']['mean_fwd_ret']:+.2%} p10dd={inv['high_pos']['p10_dd']:+.2%} "
              f"ddadj={inv['high_pos']['dd_adj_score']} (n_m={inv['high_pos']['n_months']})")
        print(f"  ret_gap(low-high)={inv['ret_gap_low_minus_high']:+.2%} CI={_fmt_ci(inv.get('ret_gap_ci'))}  "
              f"dd_adj_gap={inv['dd_adj_gap_low_minus_high']} CI={inv.get('dd_adj_gap_ci')}")
        print(f"  >>> VERDICT: {inv['verdict'].upper()}")
    print("=" * 78 + "\n")


# ──────────────────────────────────────────────────────────────────── main ──────────

def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"],
                                       cwd=Path(__file__).resolve().parent.parent,
                                       text=True).strip()[:12]
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser(description="W0.4 keystone position/phase gate (TR-v0).")
    ap.add_argument("--quick", action="store_true", help="smoke run on the last 4y only")
    ap.add_argument("--verify", action="store_true", help="PIT spot-checks only, then exit")
    ap.add_argument("--out", default="data/research/keystone_tr0", help="output dir")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    print("keystone_position_gate_phase0: loading close panel ...", flush=True)
    closes = yahoo_closes()
    if closes is None or closes.empty:
        print("FATAL: no close panel", file=sys.stderr)
        sys.exit(1)
    closes = closes.sort_index()
    print(f"  panel {closes.shape} {closes.index[0].date()}..{closes.index[-1].date()}", flush=True)

    print("PIT verification (append-invariance) ...", flush=True)
    pit_checks = verify_pit(closes)
    pit_append = verify_pit_append(closes)
    for c in pit_checks:
        print(f"  spot {c['ticker']} @ {c['asof']}: match={c['match']}")
    print(f"  append-test {pit_append['ticker']} @ {pit_append['asof']}: match={pit_append['match']}")
    if not all(c["match"] for c in pit_checks) or not pit_append["match"]:
        print("FATAL: PIT invariance FAILED — a stamp changed when future data was appended.",
              file=sys.stderr)
        sys.exit(2)
    if args.verify:
        print("PIT checks passed. (--verify) exiting.")
        return

    start = pd.Timestamp("2022-01-01") if args.quick else START
    month_ends = _month_ends(closes.index, start)
    print(f"backfill: {len(month_ends)} month-ends "
          f"{month_ends[0].date()}..{month_ends[-1].date()} "
          f"x (11 US + 24 country) ...", flush=True)
    t0 = datetime.now()
    df = backfill(closes, month_ends)
    print(f"  {len(df)} stamps in {(datetime.now() - t0).total_seconds():.0f}s", flush=True)
    df = join_forward(df, closes)
    for h in HORIZONS:
        print(f"  matured {h}d: {int(df[f'fwd_ret_{h}'].notna().sum())}/{len(df)}", flush=True)

    # persist the backfill (small; TR-v0 research cohort)
    bf_path = out_dir / "backfill.parquet"
    df.to_parquet(bf_path, index=False)
    print(f"  wrote {bf_path} ({bf_path.stat().st_size/1e6:.2f} MB)", flush=True)

    print("study: decile / phase / inversion tables + month-block bootstrap CIs ...", flush=True)
    study = build_study(df)

    manifest = {
        "run_id": datetime.now(timezone.utc).isoformat() + "_" + _git_sha(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "basis": BASIS, "epoch": EPOCH, "research_only": True,
        "universe": {"us_sector": list(sc.SECTORS), "country": list(cc.COUNTRIES),
                     "skipped": "baskets + blocs (non-PIT membership; ruling A1/D2 §0)"},
        "horizons_bars": list(HORIZONS), "wf_split": str(WF_SPLIT.date()),
        "n_deciles": N_DECILES, "min_months": MIN_MONTHS,
        "bootstrap": {"draws": BOOT_DRAWS, "seed": BOOT_SEED, "blocks": "stamp months"},
        "convention": CONVENTION,
        "n_month_ends": len(month_ends), "n_stamps": int(len(df)),
        "n_matured": study["n_matured"],
        "pit_spot_checks": pit_checks, "pit_append_check": pit_append,
        "git_sha": _git_sha(),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    (out_dir / "study_tables.json").write_text(json.dumps(study, indent=2, default=str))
    print(f"  wrote {out_dir/'manifest.json'} + {out_dir/'study_tables.json'}", flush=True)

    print_verdict(study, pit_checks, pit_append)


if __name__ == "__main__":
    main()
