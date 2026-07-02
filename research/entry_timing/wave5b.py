"""wave5b.py — Wave-5b registered post-gate strata (amendments #25 DONOR-UNWIND, #26 SPRING).

BINDING SPEC: research/entry_timing/WAVE5_PREREG.md §9 amendments #25 and #26 (verbatim, pre-run).
Context: WAVE5_REPORT.md §2 — E_BASED ≡ P2 identically (E_BASED entry is always i+7 = the P2 entry),
so the amendments' "E_BASED" reads are executed on the P2 columns of the wave-5 fire parquets.

These are DIAGNOSTIC post-gate reads, computed on the FROZEN wave-5 fire parquets AFTER the §6 gate
verdicts. They cannot alter the wave-5 ship decision; they are promotable to a wave-6 primary only.

Consumes:
  research/entry_timing/_out/wave5_stocks_m2d_s3d.parquet   (per-fire rows, policy fills+outcomes)
  research/entry_timing/_out/wave5_baskets_m2d_s3d.parquet
  data/stocks/*.parquet, data/baskets/ohlcv/*.parquet       (closes for donor composites)
  data/breadth/constituents.parquet + wave2 basket sector map (GICS sectors)
  data/yahoo/SPY.parquet                                     (not needed here; strata are self-contained)

Causality rules (§ leak-audit):
  - Every feature uses bars <= entry (fill) only.
  - Donor weekly bearish cross uses COMPLETED W-FRI weekly bars known at the entry date (the wave-1
    wbull `.shift(1)` prior-closed-week convention, mirrored for the bearish `xdn` cross).
  - No outcome column is ever used as an input.

Outputs:
  research/entry_timing/_out/wave5b_strata.json
  Appends '## 11. Wave-5b — registered post-gate strata (amendments #25/#26)' to WAVE5_REPORT.md.

Run: python3 research/entry_timing/wave5b.py
"""
from __future__ import annotations

import sys
import json
import warnings
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
SIG_ENG = ROOT / "research" / "signal_engine"
ENTRY_TIMING = ROOT / "research" / "entry_timing"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIG_ENG))
sys.path.insert(0, str(ENTRY_TIMING))

import tuning_harness as TH  # noqa: E402

OUT_DIR = ENTRY_TIMING / "_out"
DATA_STOCKS = ROOT / "data" / "stocks"
DATA_BASKETS = ROOT / "data" / "baskets" / "ohlcv"
BREADTH = ROOT / "data" / "breadth"

# ── amendment #25 donor params ────────────────────────────────────────────────
DONOR_LB126 = 126        # trailing 126d EW return for donor ranking
DONOR_MIN_MEMBERS = 5    # min 5 sector members to rank a sector
DONOR_WK_LOOKBACK = 4    # fresh weekly bearish cross within the trailing 4 COMPLETED W-FRI weeks
DONOR_20D = 20           # donor 20d EW return < 0 while still top-ranked

# ── amendment #26 spring params ───────────────────────────────────────────────
SPRING_PRE_LB = 10       # pre-cross 10d min = min(close[i-10 .. i-1])

# GICS sector groups: staples+healthcare vs rest (amendment #26 sub-split)
DEFENSIVE_SECTORS = {"Consumer Staples", "Health Care"}


# ══════════════════════════════════════════════════════════════════════════════
# Sector maps
# ══════════════════════════════════════════════════════════════════════════════

def load_stock_sector_map() -> dict:
    const = pd.read_parquet(BREADTH / "constituents.parquet")
    return {s: const.loc[s, "sector"] for s in const.index}


def load_basket_sector_map() -> dict:
    from wave2 import load_membership, build_basket_sector_map
    const = load_stock_sector_map()
    try:
        mem = load_membership()
        bmap = build_basket_sector_map(mem)
    except Exception:
        bmap = {}
    return {**const, **bmap}


# ══════════════════════════════════════════════════════════════════════════════
# §25 Donor sector composites (equal-weight, causal)
# ══════════════════════════════════════════════════════════════════════════════

def build_sector_composites(data_dir: Path, sector_map: dict, min_bars: int) -> dict:
    """Build per-GICS-sector equal-weight composite close series on a common daily calendar.

    For each sector, take all sector-mapped panel names with >= min_bars closes; normalize each
    to its first valid close = 1.0; equal-weight average across members (a member contributes to a
    day only where it has data). Returns:
      {sector: pd.Series(ew_composite, index=DatetimeIndex), 'members': {sector: [tickers]}}
    plus a per-day member-count frame so the donor ranking can enforce min-5-members AT bar i.
    """
    from collections import defaultdict as dd
    by_sector = dd(list)
    files = sorted(data_dir.glob("*.parquet"))
    for fp in files:
        t = fp.stem
        sec = sector_map.get(t)
        if sec is None:
            continue
        try:
            daily = pd.read_parquet(fp)["close"].dropna()
        except Exception:
            continue
        if len(daily) < min_bars:
            continue
        by_sector[sec].append((t, daily))

    comps: dict = {}
    members: dict = {}
    counts: dict = {}
    for sec, lst in by_sector.items():
        if len(lst) < DONOR_MIN_MEMBERS:
            # still build it, but ranking will enforce the live per-day member floor
            pass
        norm_list = []
        for t, daily in lst:
            first = daily.iloc[0]
            if first <= 0 or np.isnan(first):
                continue
            norm_list.append(daily / first)
        if not norm_list:
            continue
        wide = pd.concat(norm_list, axis=1)
        ew = wide.mean(axis=1, skipna=True)
        cnt = wide.notna().sum(axis=1)
        comps[sec] = ew
        counts[sec] = cnt
        members[sec] = [t for t, _ in lst]
    return {"comps": comps, "counts": counts, "members": members}


def build_donor_timeline(comp_bundle: dict) -> pd.DataFrame:
    """Per calendar day, resolve the donor sector (top-1 by trailing 126d EW return with >=5 live
    members at that day) and the two donor_unwind legs. Returns a daily frame indexed by date:
      columns: donor (sector), donor_ret126, donor_unwind_wk (bool), donor_unwind_20d (bool),
               donor_unwind (bool = wk OR 20d).

    Causality: at day d we use each sector composite's value at d and at d-126/d-20 (bars <= d),
    and the weekly bearish cross uses only COMPLETED W-FRI weekly bars known at/before d (the wave-1
    prior-closed-week `.shift(1)` convention, mirrored for the bearish xdn cross).
    """
    comps = comp_bundle["comps"]
    counts = comp_bundle["counts"]

    # union daily calendar
    all_idx = None
    for s in comps.values():
        all_idx = s.index if all_idx is None else all_idx.union(s.index)
    all_idx = all_idx.sort_values()

    # align each sector composite + count + trailing returns + weekly bearish-cross-daily
    sec_ret126 = {}
    sec_ret20 = {}
    sec_cnt = {}
    sec_wk_bear_recent = {}   # daily bool: a completed-weekly bearish cross within trailing 4 wks
    for sec, ew in comps.items():
        ewa = ew.reindex(all_idx)
        sec_ret126[sec] = ewa / ewa.shift(DONOR_LB126) - 1.0
        sec_ret20[sec] = ewa / ewa.shift(DONOR_20D) - 1.0
        sec_cnt[sec] = counts[sec].reindex(all_idx).fillna(0)

        # weekly RSI-MACD bearish cross on the donor composite (completed-week convention)
        wk = ew.resample("W-FRI").last().dropna()
        wmacd, wsig = TH.rsi_macd(wk)
        wbear = TH.xdn(wmacd, wsig).fillna(False)          # weekly bearish cross
        # only COMPLETED weeks known at the entry date: shift(1) = prior closed week (no repaint),
        # mirroring wave1/tuning_harness wbull `.shift(1)` convention. A bearish cross printed on
        # weekly bar w is only "known/actionable" once that week has CLOSED, i.e. one week later.
        wbear_known = wbear.shift(1).fillna(False)
        # "within the trailing 4 completed W-FRI weeks": rolling any() over 4 completed weeks
        wbear_recent = wbear_known.rolling(DONOR_WK_LOOKBACK, min_periods=1).max().fillna(0).astype(bool)
        # map weekly -> daily by ffill (state held until the next completed week is known)
        sec_wk_bear_recent[sec] = wbear_recent.reindex(all_idx, method="ffill").fillna(False)

    ret126_df = pd.DataFrame(sec_ret126, index=all_idx)
    cnt_df = pd.DataFrame(sec_cnt, index=all_idx)
    ret20_df = pd.DataFrame(sec_ret20, index=all_idx)
    wkbear_df = pd.DataFrame(sec_wk_bear_recent, index=all_idx)

    # donor = top-1 sector by ret126 among sectors with >=5 live members at that day
    elig = cnt_df >= DONOR_MIN_MEMBERS
    ret126_elig = ret126_df.where(elig)

    # idxmax raises on all-NA rows: compute only on rows with >=1 eligible sector, NaN elsewhere.
    any_elig = ret126_elig.notna().any(axis=1)
    donor = pd.Series(np.nan, index=all_idx, dtype=object)
    if any_elig.any():
        donor.loc[any_elig] = ret126_elig.loc[any_elig].idxmax(axis=1)
    rows = []
    for d in all_idx:
        dn = donor.loc[d]
        if not isinstance(dn, str):
            rows.append((d, None, np.nan, False, False, False))
            continue
        r126 = float(ret126_df.at[d, dn])
        r20 = float(ret20_df.at[d, dn])
        wk_bear = bool(wkbear_df.at[d, dn])
        leg_wk = wk_bear
        leg_20 = bool(r20 < 0)   # donor 20d EW return < 0 while still top-ranked (dn IS top-ranked)
        unwind = bool(leg_wk or leg_20)
        rows.append((d, dn, r126, leg_wk, leg_20, unwind))

    tl = pd.DataFrame(rows, columns=["date", "donor", "donor_ret126",
                                     "donor_unwind_wk", "donor_unwind_20d", "donor_unwind"])
    tl = tl.set_index("date")
    return tl


# ══════════════════════════════════════════════════════════════════════════════
# §26 Spring feature (price-only, causal; on P2 entries which enter at i+7)
# ══════════════════════════════════════════════════════════════════════════════

def compute_spring_flags(fires: pd.DataFrame, data_dir: Path, entry_off: int = 7) -> pd.Series:
    """spring on P2 entries (entry at entry_j = i+entry_off = i+7):
       spring = (min close in [i+1 .. entry_j] < pre-cross 10d min min(close[i-10..i-1]))
                AND (close[entry_j] > that pre-cross 10d min).
    never-BROKEN is guaranteed by P2 (the fire produced a P2 entry). Price-only (amendment #26).
    Causal: uses close[i-10..i-1] (pre-cross) and close[i+1..i+7] (through the entry bar) only.
    Returns a boolean Series aligned to `fires.index` (NaN-safe -> False where uncomputable).
    """
    out = pd.Series(False, index=fires.index)
    cache: dict = {}
    for ridx, r in fires.iterrows():
        t = r["ticker"]
        i = int(r["sig_idx"])
        if t not in cache:
            try:
                cache[t] = pd.read_parquet(data_dir / f"{t}.parquet")["close"].dropna().to_numpy()
            except Exception:
                cache[t] = None
        c = cache[t]
        if c is None:
            continue
        entry_j = i + entry_off
        n = len(c)
        if i - SPRING_PRE_LB < 0 or entry_j >= n:
            continue
        pre_min = float(np.min(c[i - SPRING_PRE_LB:i]))   # close[i-10 .. i-1]
        if pre_min <= 0 or np.isnan(pre_min):
            continue
        win = c[i + 1:entry_j + 1]                        # close[i+1 .. i+7]
        if len(win) == 0:
            continue
        min_win = float(np.min(win))
        close_entry = float(c[entry_j])
        spring = (min_win < pre_min) and (close_entry > pre_min)
        out.at[ridx] = bool(spring)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Stratified rate tables
# ══════════════════════════════════════════════════════════════════════════════

AXES = ["stop5", "clean15", "dead_money"]


def _cell_stats(sub: pd.DataFrame, policy: str) -> dict:
    pre = f"{policy}__"
    mask = sub[pre + "fill_idx"].notna()
    s = sub[mask]
    n = int(len(s))
    d = {"n": n}
    for ax in AXES:
        col = pre + ax
        if col in s.columns and n > 0:
            v = s[col].dropna()
            d[ax] = round(float(v.mean()) * 100, 2) if len(v) else None
        else:
            d[ax] = None
    d["n_names"] = int(s["ticker"].nunique()) if n > 0 else 0
    return d


def stratify(fires: pd.DataFrame, policy: str, cell_col: str, cells: list) -> dict:
    out = {}
    for cell in cells:
        sub = fires[fires[cell_col] == cell]
        out[str(cell)] = _cell_stats(sub, policy)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def attach_donor(fires: pd.DataFrame, policy: str, donor_tl: pd.DataFrame) -> pd.DataFrame:
    """Attach donor cell at each entry's FILL date (bars<=fill only). Returns fires with a
    per-policy `donor_unwind_{policy}` column and `donor_{policy}` sector (None where no fill)."""
    pre = f"{policy}__"
    fd = pd.to_datetime(fires[pre + "fill_date"])
    tl_idx = donor_tl.index
    # searchsorted: last donor-timeline day at/before the fill date (bars<=fill)
    pos = tl_idx.searchsorted(fd.values, side="right") - 1
    unwind = np.full(len(fires), np.nan, dtype=object)
    donor = np.full(len(fires), None, dtype=object)
    uw_arr = donor_tl["donor_unwind"].to_numpy()
    dn_arr = donor_tl["donor"].to_numpy()
    for k in range(len(fires)):
        if pd.isna(fd.iloc[k]):
            continue
        p = pos[k]
        if p < 0:
            continue
        unwind[k] = "intact" if not bool(uw_arr[p]) else "cracking"
        donor[k] = dn_arr[p]
    fires = fires.copy()
    fires[f"donor_cell_{policy}"] = unwind
    fires[f"donor_sec_{policy}"] = donor
    return fires


def run_panel(panel: str) -> dict:
    if panel == "stocks":
        data_dir = DATA_STOCKS
        min_bars = 1500
        sector_map = load_stock_sector_map()
    else:
        data_dir = DATA_BASKETS
        min_bars = 1000
        sector_map = load_basket_sector_map()

    fp = OUT_DIR / f"wave5_{panel}_m2d_s3d.parquet"
    fires = pd.read_parquet(fp)
    fires["sig_date"] = pd.to_datetime(fires["sig_date"])

    # entry-ticker sector (for spring sub-split + honesty)
    fires["ticker_sector"] = fires["ticker"].map(sector_map)

    result: dict = {"panel": panel, "n_fires": int(len(fires))}

    # ── donor coverage ────────────────────────────────────────────────────────
    print(f"[{panel}] building sector composites...")
    comp_bundle = build_sector_composites(data_dir, sector_map, min_bars)
    n_secs = len(comp_bundle["comps"])
    sec_member_counts = {s: len(m) for s, m in comp_bundle["members"].items()}
    print(f"[{panel}] sectors with composites: {n_secs} -> {sec_member_counts}")
    donor_tl = build_donor_timeline(comp_bundle)
    result["donor_meta"] = {
        "n_sectors": n_secs,
        "sector_member_counts": sec_member_counts,
        "n_ticker_sector_mapped": int(fires["ticker_sector"].notna().sum()),
        "n_ticker_total": int(len(fires)),
    }

    # ── #25 DONOR-UNWIND: P2, E_RETEST, E_FRESH stratified by {intact, cracking} ──
    donor_res = {}
    donor_policies = ["P2", "E_RETEST", "E_FRESH"]
    fires_d = fires
    for pol in donor_policies:
        fires_d = attach_donor(fires_d, pol, donor_tl)

    for pol in donor_policies:
        cell_col = f"donor_cell_{pol}"
        strat = stratify(fires_d, pol, cell_col, ["intact", "cracking"])
        # time halves (pre/post 2020) on fill_date
        fd = pd.to_datetime(fires_d[f"{pol}__fill_date"])
        pre_mask = fd < pd.Timestamp("2020-01-01")
        halves = {}
        for half, mask in [("pre2020", pre_mask), ("post2020", ~pre_mask & fd.notna())]:
            sub = fires_d[mask]
            halves[half] = stratify(sub, pol, cell_col, ["intact", "cracking"])
        # 2025+ cell (owner's episode)
        ep_mask = fd >= pd.Timestamp("2025-01-01")
        ep = stratify(fires_d[ep_mask], pol, cell_col, ["intact", "cracking"])
        donor_res[pol] = {"full": strat, "time_halves": halves, "y2025plus": ep}
    result["donor_unwind"] = donor_res

    # ── donor-unwind registered predictions (#25) ─────────────────────────────
    # PREDICTION (P2 == E_BASED): clean15 concentrates in CRACKING (donor-unwind) cells;
    #   dead_money concentrates in INTACT (donor-intact) cells. Must hold FULL panel (2012+).
    def _pred_donor(res_pol):
        f = res_pol["full"]
        cr, it = f.get("cracking", {}), f.get("intact", {})
        c15_ok = (cr.get("clean15") is not None and it.get("clean15") is not None
                  and cr["clean15"] > it["clean15"])
        dm_ok = (cr.get("dead_money") is not None and it.get("dead_money") is not None
                 and it["dead_money"] > cr["dead_money"])
        return {"clean15_concentrates_cracking": bool(c15_ok),
                "dead_money_concentrates_intact": bool(dm_ok),
                "cracking_clean15": cr.get("clean15"), "intact_clean15": it.get("clean15"),
                "cracking_dead_money": cr.get("dead_money"), "intact_dead_money": it.get("dead_money")}
    result["donor_predictions"] = {pol: _pred_donor(donor_res[pol]) for pol in donor_policies}

    # ── #26 SPRING: on P2 entries (entry at i+7) ──────────────────────────────
    print(f"[{panel}] computing spring flags on P2 entries...")
    p2_mask = fires["P2__fill_idx"].notna()
    spring = compute_spring_flags(fires, data_dir, entry_off=7)
    fires["spring"] = spring
    # spring only meaningful where a P2 entry exists
    fires["spring_cell"] = np.where(p2_mask, np.where(fires["spring"], "spring", "no_spring"), None)

    spring_full = stratify(fires[p2_mask], "P2", "spring_cell", ["spring", "no_spring"])

    # sub-split by GICS group: defensive (staples+healthcare) vs rest
    fires["def_group"] = np.where(
        fires["ticker_sector"].isin(DEFENSIVE_SECTORS), "staples_healthcare", "rest")
    spring_by_group = {}
    for grp in ["staples_healthcare", "rest"]:
        sub = fires[p2_mask & (fires["def_group"] == grp)]
        spring_by_group[grp] = stratify(sub, "P2", "spring_cell", ["spring", "no_spring"])

    # vol quintile (ATR63% basis atrp_i at fire bar) — low-ATR read ~ registered low-beta prediction
    p2f = fires[p2_mask].copy()
    p2f["vol_q"] = pd.qcut(p2f["atrp_i"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
    spring_by_vol = {}
    for q in [1, 2, 3, 4, 5]:
        sub = p2f[p2f["vol_q"] == q]
        spring_by_vol[f"q{q}"] = stratify(sub, "P2", "spring_cell", ["spring", "no_spring"])

    result["spring"] = {"full": spring_full, "by_gics_group": spring_by_group, "by_vol_quintile": spring_by_vol}

    # ── spring registered prediction (#26) ─────────────────────────────────────
    # PREDICTION: spring-present P2 entries have higher clean15 / lower dead_money than no-spring;
    #   effect expected strongest in low-beta/staples cohorts.
    def _pred_spring(strat):
        sp, ns = strat.get("spring", {}), strat.get("no_spring", {})
        c15_ok = (sp.get("clean15") is not None and ns.get("clean15") is not None
                  and sp["clean15"] > ns["clean15"])
        dm_ok = (sp.get("dead_money") is not None and ns.get("dead_money") is not None
                 and sp["dead_money"] < ns["dead_money"])
        return {"clean15_higher_spring": bool(c15_ok), "dead_money_lower_spring": bool(dm_ok),
                "spring_clean15": sp.get("clean15"), "no_spring_clean15": ns.get("clean15"),
                "spring_dead_money": sp.get("dead_money"), "no_spring_dead_money": ns.get("dead_money"),
                "spring_n": sp.get("n"), "no_spring_n": ns.get("n")}
    result["spring_predictions"] = {
        "full": _pred_spring(spring_full),
        "staples_healthcare": _pred_spring(spring_by_group["staples_healthcare"]),
        "low_vol_q1": _pred_spring(spring_by_vol["q1"]),
    }

    return result


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    # stocks: full GICS coverage (211/212). baskets: donor computable (composites from mapped
    # subset); spring GICS sub-split honest about basket sector coverage.
    for panel in ["stocks", "baskets"]:
        try:
            results[panel] = run_panel(panel)
            print(f"[{panel}] done.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            results[panel] = {"_error": repr(e)}

    (OUT_DIR / "wave5b_strata.json").write_text(json.dumps(results, indent=2, default=str))
    print(f"wrote {OUT_DIR / 'wave5b_strata.json'}")

    append_report(results)
    return results


# ══════════════════════════════════════════════════════════════════════════════
# Report section
# ══════════════════════════════════════════════════════════════════════════════

def _fmt(v):
    return "—" if v is None else f"{v:.2f}"


def _donor_table(donor_res: dict, pol: str) -> str:
    f = donor_res[pol]["full"]
    lines = [f"| {pol} | cell | stop5 | clean15 | dead_money | n | names |",
             "|---|---|---|---|---|---|---|"]
    for cell in ["intact", "cracking"]:
        c = f.get(cell, {})
        lines.append(f"| | {cell} | {_fmt(c.get('stop5'))} | {_fmt(c.get('clean15'))} | "
                     f"{_fmt(c.get('dead_money'))} | {c.get('n',0)} | {c.get('n_names',0)} |")
    return "\n".join(lines)


def _donor_half_table(donor_res: dict, pol: str) -> str:
    h = donor_res[pol]["time_halves"]
    lines = [f"| {pol} half | cell | stop5 | clean15 | dead_money | n |",
             "|---|---|---|---|---|---|"]
    for half in ["pre2020", "post2020"]:
        for cell in ["intact", "cracking"]:
            c = h[half].get(cell, {})
            lines.append(f"| {half} | {cell} | {_fmt(c.get('stop5'))} | {_fmt(c.get('clean15'))} | "
                         f"{_fmt(c.get('dead_money'))} | {c.get('n',0)} |")
    ep = donor_res[pol]["y2025plus"]
    for cell in ["intact", "cracking"]:
        c = ep.get(cell, {})
        lines.append(f"| 2025+ | {cell} | {_fmt(c.get('stop5'))} | {_fmt(c.get('clean15'))} | "
                     f"{_fmt(c.get('dead_money'))} | {c.get('n',0)} |")
    return "\n".join(lines)


def _spring_table(strat: dict, label: str) -> str:
    lines = [f"| {label} | cell | stop5 | clean15 | dead_money | n | names |",
             "|---|---|---|---|---|---|---|"]
    for cell in ["spring", "no_spring"]:
        c = strat.get(cell, {})
        lines.append(f"| | {cell} | {_fmt(c.get('stop5'))} | {_fmt(c.get('clean15'))} | "
                     f"{_fmt(c.get('dead_money'))} | {c.get('n',0)} | {c.get('n_names',0)} |")
    return "\n".join(lines)


def append_report(results: dict):
    rp = ENTRY_TIMING / "WAVE5_REPORT.md"
    txt = rp.read_text()
    marker = "## 11. Wave-5b — registered post-gate strata (amendments #25/#26)"
    if marker in txt:
        txt = txt[:txt.index(marker)].rstrip() + "\n\n"

    L = []
    L.append(marker)
    L.append("")
    L.append("> **Discipline & honesty.** These are DIAGNOSTIC post-gate reads computed on the FROZEN "
             "wave-5 fire parquets *after* the §6 gate verdicts (all of which FAILED — nothing shipped). "
             "They cannot alter the wave-5 ship decision and are **promotable to a wave-6 primary only**. "
             "Multiplicity: 2 registered stratum families (#25 donor-unwind, 2 cells; #26 spring, 2 cells). "
             "Every feature uses bars ≤ entry (fill) only; the donor weekly bearish cross uses only "
             "COMPLETED W-FRI weeks (wave-1 `.shift(1)` prior-closed-week convention, mirrored for `xdn`); "
             "no outcome column is an input.")
    L.append("")
    L.append("**Structural note carried from §2:** `E_BASED ≡ P2` exactly (E_BASED always enters at i+7 = "
             "the P2 entry), so the amendments' *E_BASED* reads are executed on the **P2** columns. The "
             "amendments predict where the (identical) P2/E_BASED clean15 and dead_money concentrate.")
    L.append("")

    for panel in ["stocks", "baskets"]:
        r = results.get(panel, {})
        if "_error" in r:
            L.append(f"### {panel}: ERROR {r['_error']}")
            continue
        dm = r.get("donor_meta", {})
        L.append(f"### 11.{'A' if panel=='stocks' else 'B'} Panel: {panel}")
        L.append("")
        L.append(f"Donor composites: {dm.get('n_sectors')} GICS sectors "
                 f"({dm.get('sector_member_counts')}). Entry-ticker GICS coverage: "
                 f"{dm.get('n_ticker_sector_mapped')}/{dm.get('n_ticker_total')} fires "
                 f"({100*dm.get('n_ticker_sector_mapped',0)/max(1,dm.get('n_ticker_total',1)):.0f}%). "
                 + ("Full coverage — donor + spring-group both clean."
                    if panel == "stocks" else
                    "Donor cell is a MARKET-WIDE feature (independent of the entry ticker's own sector) so "
                    "it is computable for ALL basket entries from the mapped-subset composites; the spring "
                    "GICS sub-split is honest about the ~21% sector-mapped basket subset (unmapped baskets "
                    "fall in `rest`)."))
        L.append("")

        # #25 donor-unwind
        L.append("#### #25 DONOR-UNWIND — {intact, cracking} × {P2, E_RETEST, E_FRESH}")
        L.append("")
        L.append("`cracking` = donor_unwind TRUE (fresh weekly RSI-MACD bearish cross on the top-1 "
                 "126d-EW-return GICS sector within the trailing 4 completed weeks, OR donor 20d EW "
                 "return < 0 while still top-ranked). `intact` = otherwise.")
        L.append("")
        dres = r.get("donor_unwind", {})
        for pol in ["P2", "E_RETEST", "E_FRESH"]:
            L.append(_donor_table(dres, pol))
            L.append("")
        L.append("**Time halves + 2025+ (owner's episode), per policy:**")
        L.append("")
        for pol in ["P2", "E_RETEST", "E_FRESH"]:
            L.append(_donor_half_table(dres, pol))
            L.append("")
        # predictions
        dp = r.get("donor_predictions", {})
        L.append("**Registered prediction #25 (two-sided, FULL panel):** clean15 concentrates in "
                 "`cracking`; dead_money concentrates in `intact`. Held?")
        L.append("")
        L.append("| policy | clean15↑ in cracking | dead_money↑ in intact | crack c15 / intact c15 | crack dm / intact dm |")
        L.append("|---|---|---|---|---|")
        for pol in ["P2", "E_RETEST", "E_FRESH"]:
            p = dp.get(pol, {})
            L.append(f"| {pol} | {'HELD' if p.get('clean15_concentrates_cracking') else 'FAILED'} | "
                     f"{'HELD' if p.get('dead_money_concentrates_intact') else 'FAILED'} | "
                     f"{_fmt(p.get('cracking_clean15'))} / {_fmt(p.get('intact_clean15'))} | "
                     f"{_fmt(p.get('cracking_dead_money'))} / {_fmt(p.get('intact_dead_money'))} |")
        L.append("")

        # #26 spring
        L.append("#### #26 SPRING — P2 entries, {spring, no_spring}")
        L.append("")
        L.append("`spring` = (min close in [i+1..i+7] < pre-cross 10d min `min(close[i-10..i-1])`) AND "
                 "(close[i+7] > that 10d min) — undercut the SHALLOW low and reclaimed it by entry. "
                 "never-BROKEN guaranteed by P2. Price-only (H4 falsification bars volume legs).")
        L.append("")
        sp = r.get("spring", {})
        L.append(_spring_table(sp.get("full", {}), "full"))
        L.append("")
        L.append("**By GICS group (staples+healthcare vs rest):**")
        L.append("")
        for grp in ["staples_healthcare", "rest"]:
            L.append(_spring_table(sp.get("by_gics_group", {}).get(grp, {}), grp))
            L.append("")
        L.append("**By vol quintile (ATR63% at fire bar; q1 = lowest ATR ~ registered low-beta read):**")
        L.append("")
        lines = ["| vol_q | cell | stop5 | clean15 | dead_money | n |", "|---|---|---|---|---|---|"]
        for q in ["q1", "q2", "q3", "q4", "q5"]:
            g = sp.get("by_vol_quintile", {}).get(q, {})
            for cell in ["spring", "no_spring"]:
                c = g.get(cell, {})
                lines.append(f"| {q} | {cell} | {_fmt(c.get('stop5'))} | {_fmt(c.get('clean15'))} | "
                             f"{_fmt(c.get('dead_money'))} | {c.get('n',0)} |")
        L.append("\n".join(lines))
        L.append("")
        spp = r.get("spring_predictions", {})
        L.append("**Registered prediction #26 (two-sided):** spring-present higher clean15 / lower "
                 "dead_money than no-spring; strongest in low-beta/staples. Held?")
        L.append("")
        L.append("| cohort | clean15 higher (spring) | dead_money lower (spring) | spring c15 / no c15 | spring dm / no dm | n spring / no |")
        L.append("|---|---|---|---|---|---|")
        for coh, lbl in [("full", "full"), ("staples_healthcare", "staples+healthcare"), ("low_vol_q1", "low-vol q1")]:
            p = spp.get(coh, {})
            L.append(f"| {lbl} | {'HELD' if p.get('clean15_higher_spring') else 'FAILED'} | "
                     f"{'HELD' if p.get('dead_money_lower_spring') else 'FAILED'} | "
                     f"{_fmt(p.get('spring_clean15'))} / {_fmt(p.get('no_spring_clean15'))} | "
                     f"{_fmt(p.get('spring_dead_money'))} / {_fmt(p.get('no_spring_dead_money'))} | "
                     f"{p.get('spring_n',0)} / {p.get('no_spring_n',0)} |")
        L.append("")

    L.append("#### Honesty note")
    L.append("")
    L.append("- Post-gate diagnostic reads only; **promotable to wave-6 primaries, never a wave-5 ship "
             "input.** The wave-5 gates (§6) already failed and nothing shipped.")
    L.append("- Point estimates are raw cell means (pp). No block-bootstrap lower bound is applied here "
             "(these are exploratory strata, not gate clauses); a wave-6 promotion MUST re-impose the §4 "
             "90% clustered lower-bound discipline before any of these signs is read as real.")
    L.append("- A registered prediction is marked HELD only if the point-estimate inequality holds on the "
             "FULL panel (2012+); the pre/post-2020 halves are shown so a 2025-only regime effect cannot "
             "masquerade as a mechanism (amendment #25 explicitly requires the full-panel hold).")
    L.append("")

    txt = txt.rstrip() + "\n\n" + "\n".join(L) + "\n"
    rp.write_text(txt)
    print(f"appended §11 to {rp}")


if __name__ == "__main__":
    main()
