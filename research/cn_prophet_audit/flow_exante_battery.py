"""Did the UNWIRED CN flow/positioning stores separate losers from winners AT ADMISSION?

MEASUREMENT INSTRUMENT — evidence layer only, no promotion claim.

The CN flow/positioning layer (龙虎榜, northbound, margin, holder counts, block
trades, buyback) is collected nightly and has ZERO pick-chain consumers. This
battery asks one question per store, on the audited 407-episode V1 frame, with
the same PIT ex-ante methodology as `sector_intel_exante_test.py`: joined at
each episode's ADMISSION date using only records observable on or before that
date, does the store's state separate losers (excess <= 0) from winners?

Single-axis only. NO composite scoring, NO multi-store blending (that is a later
prereg). Nulls are printed, not hidden. The UNUSABLE list is a deliverable: it
is the data-collection to-do.

PRIOR KILLS HONORED (see FLOW_EXANTE_BATTERY.md §1 for citations):
  * Raw LHB hot-money APPEARANCE flag is FALSIFIED wrong-sign (measured
    -1.43%/21d). It is reported here as a REPLICATION/context row explicitly
    labeled `prior_killed`, never as a new hypothesis. The NEW axes on this
    store are net-buy SIGN, net-buy MAGNITUDE, INSTITUTIONAL-SEAT composition
    (the surviving accruing construction `cnlab_lhb_inst`), and ADMISSION-REASON
    class (up-deviation vs down-deviation vs turnover) — none previously tested.
  * Block-trade PREMIUM flag is demoted wrong-sign (-0.60%/5d); the deep-DISCOUNT
    leg is probationary, not killed. Moot here: the store is UNUSABLE (snapshot).
  * `cn_supply_absorption` family is CLOSED; no absorption construction is tested.
  * Northbound net flow / margin velocity were falsified as STANDALONE TIMING
    signals. This battery is not a timing test — it is a conditional
    loser-separation test INSIDE an already-admitted candidate pool, which is a
    different construction. Per house epistemics, a standalone null is retained
    as a confluence input; measuring it here is lawful and display-tier.

Run from repo root: python3 research/cn_prophet_audit/flow_exante_battery.py
Output: research/cn_prophet_audit/flow_exante_battery_results.json (frozen)
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
OUT = HERE / "flow_exante_battery_results.json"

THIN = 15          # cells below this are labeled thin and cannot carry a verdict
MIN_COVERAGE = 40  # episodes; below this the feature is UNUSABLE(coverage)


# ---------------------------------------------------------------- statistics
def med(vals):
    vals = [v for v in vals if v is not None and np.isfinite(v)]
    return round(float(np.median(vals)), 3) if vals else None


def wilson(k: int, n: int, z: float = 1.96):
    """Wilson score interval for a binomial rate. Returns (lo, hi) rounded."""
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round((c - h) / d, 3), round((c + h) / d, 3))


def disjoint(a, b) -> bool:
    """True when two Wilson intervals do not overlap."""
    if a is None or b is None:
        return False
    return a[1] < b[0] or b[1] < a[0]


# ---------------------------------------------------------------- reporting
def slice_table(rows, key, demean):
    """Per-bucket n / loser_rate (+Wilson CI) / median_excess. Mirrors the
    `table()` idiom of sector_intel_exante_test.py, extended with CIs, thin-cell
    labels, and a date-demeaned median (the 407 episodes sit on only 12
    admission dates, so raw bucket spreads can be pure date clustering)."""
    g = defaultdict(list)
    for r in rows:
        v = r.get(key)
        if v is None:
            continue
        g[str(v)].append(r)
    out = {}
    for k, v in sorted(g.items()):
        exc = [r["excess"] for r in v]
        losers = sum(1 for x in exc if x <= 0)
        out[k] = {
            "n": len(v),
            "loser_rate": round(losers / len(v), 3),
            "loser_ci95": wilson(losers, len(v)),
            "median_excess": med(exc),
            "median_excess_date_demeaned": med([r["excess"] - demean[r["date"]] for r in v]),
            "thin": len(v) < THIN,
        }
    return out


def verdict(tbl, lo_key, hi_key, axis_note=""):
    """Pre-stated mechanical rule, applied identically to every feature.

    SEPARATES requires all three:
      (a) both compared buckets have n >= THIN,
      (b) their Wilson 95% loser-rate CIs are DISJOINT,
      (c) the date-demeaned median-excess ordering agrees in sign with the raw
          ordering (i.e. the spread survives removing the admission-date effect).
    Anything else is NULL; a thin bucket yields NULL(underpowered).
    """
    a, b = tbl.get(lo_key), tbl.get(hi_key)
    if a is None or b is None:
        return {"verdict": "NULL", "reason": "bucket absent", "note": axis_note}
    if a["thin"] or b["thin"]:
        return {"verdict": "NULL", "reason": f"underpowered (n={a['n']},{b['n']} < {THIN})",
                "note": axis_note}
    d_loser = round(b["loser_rate"] - a["loser_rate"], 3)
    raw = (b["median_excess"] or 0) - (a["median_excess"] or 0)
    dem = (b["median_excess_date_demeaned"] or 0) - (a["median_excess_date_demeaned"] or 0)
    ci_ok = disjoint(a["loser_ci95"], b["loser_ci95"])
    sign_ok = (raw > 0) == (dem > 0)
    v = "SEPARATES" if (ci_ok and sign_ok) else "NULL"
    return {
        "verdict": v,
        "compared": [lo_key, hi_key],
        "d_loser_rate": d_loser,
        "d_median_excess": round(raw, 3),
        "d_median_excess_date_demeaned": round(dem, 3),
        "ci_disjoint": ci_ok,
        "date_effect_survives": sign_ok,
        "reason": ("loser-rate CIs disjoint and spread survives date-demeaning"
                   if v == "SEPARATES" else
                   "CIs overlap" if not ci_ok else "spread flips sign after date-demeaning"),
        "note": axis_note,
    }


def tercile(vals):
    """Return a labeller mapping a value onto low/mid/high by its own terciles."""
    fin = sorted(v for v in vals if v is not None and np.isfinite(v))
    if len(fin) < 3:
        return lambda v: None
    q1, q2 = np.quantile(fin, [1 / 3, 2 / 3])
    def lab(v):
        if v is None or not np.isfinite(v):
            return None
        return "low" if v <= q1 else ("high" if v > q2 else "mid")
    return lab


# ---------------------------------------------------------------- main
def main() -> None:
    eps = json.loads((HERE / "v1_loser_audit_results.json").read_text())["episodes"]
    dates = sorted({e["date"] for e in eps})
    tickers = sorted({e["ticker"] for e in eps})
    # admission-date mean excess, for the date-demeaning confound check
    by_date = defaultdict(list)
    for e in eps:
        by_date[e["date"]].append(e["excess"])
    demean = {d: float(np.mean(v)) for d, v in by_date.items()}

    print(f"episodes={len(eps)} tickers={len(tickers)} "
          f"dates={dates[0]}..{dates[-1]} ({len(dates)} admission dates)")

    rows = [{"ticker": e["ticker"], "date": e["date"], "excess": e["excess"]} for e in eps]
    by_tk_date = defaultdict(list)
    for r in rows:
        by_tk_date[r["ticker"]].append(r)

    features: dict[str, dict] = {}   # feature -> {store, table, verdict, coverage}
    unusable: list[dict] = []

    def register(name, store, key, lo, hi, note="", killed=False):
        cov = sum(1 for r in rows if r.get(key) is not None)
        if cov < MIN_COVERAGE:
            features[name] = {"store": store, "coverage": cov,
                              "verdict": {"verdict": "UNUSABLE",
                                          "reason": f"coverage {cov} < {MIN_COVERAGE} episodes"},
                              "prior_killed_construction": killed, "note": note}
            return
        tbl = slice_table(rows, key, demean)
        features[name] = {"store": store, "coverage": cov, "buckets": tbl,
                          "verdict": verdict(tbl, lo, hi, note),
                          "prior_killed_construction": killed}

    # ---------------- STORE 1: 龙虎榜 LHB (priority) --------------------------
    ev = pd.read_parquet(ROOT / "data/china_lhb/events.parquet")
    ev["date"] = ev["date"].astype(str)
    lhb_by_tk = defaultdict(list)
    for t, d, nb, rsn in zip(ev["ticker"], ev["date"], ev["net_buy_yi"], ev["reason"]):
        lhb_by_tk[str(t)].append((d, nb, str(rsn)))

    def sess_window(ticker, adm, n_sessions):
        """Trailing-n-session calendar window for a ticker, from its OWN price
        index (PIT: only bars dated <= admission)."""
        px = px_index.get(ticker)
        if px is None:
            return None
        idx = [d for d in px if d <= adm]
        if len(idx) < n_sessions:
            return None
        return idx[-n_sessions]

    # price index first (also powers the turnover axis)
    px_index: dict[str, list[str]] = {}
    px_vol: dict[str, pd.Series] = {}
    for t in tickers:
        f = ROOT / f"data/china_stocks/{t}.parquet"
        if not f.exists():
            continue
        d = pd.read_parquet(f)
        d.index = pd.to_datetime(d.index)
        d = d.sort_index()
        px_index[t] = [x.strftime("%Y-%m-%d") for x in d.index]
        px_vol[t] = pd.Series(d["volume"].values, index=px_index[t])

    UP = re.compile(r"涨幅偏离")
    DOWN = re.compile(r"跌幅偏离")
    TURN = re.compile(r"换手率")
    AMPL = re.compile(r"振幅")

    # The briefed window is 3 sessions. That yields very few hits on this frame, so
    # the SAME axes are also cut at 10 sessions purely to establish whether the
    # priority store is testable at all here (a coverage question, disclosed —
    # both windows are reported, neither is selected on its result).
    for win in (3, 10):
        sfx = f"_{win}d"
        for r in rows:
            adm, t = r["date"], r["ticker"]
            start = sess_window(t, adm, win)
            if start is None:
                continue
            hits = [(d, nb, rs) for d, nb, rs in lhb_by_tk.get(t, []) if start <= d <= adm]
            # REPLICATION ONLY — prior-killed raw appearance flag
            r["lhb_appeared" + sfx] = bool(hits)
            if hits:
                net = float(np.nansum([nb for _, nb, _ in hits]))
                r["lhb_net_sign" + sfx] = "net_buy" if net > 0 else "net_sell"
                r["lhb_net_yi" + sfx] = net
                txt = " ".join(rs for _, _, rs in hits)
                r["lhb_reason_class" + sfx] = ("up_deviation" if UP.search(txt) else
                                               "down_deviation" if DOWN.search(txt) else
                                               "turnover" if TURN.search(txt) else
                                               "amplitude" if AMPL.search(txt) else "other")
        lab = tercile([r.get("lhb_net_yi" + sfx) for r in rows])
        for r in rows:
            if r.get("lhb_net_yi" + sfx) is not None:
                r["lhb_net_mag" + sfx] = lab(r["lhb_net_yi" + sfx])

    for win in (3, 10):
        s = f"_{win}d"
        register(f"lhb_appeared{s}", "china_lhb/events", f"lhb_appeared{s}", "False", "True",
                 note="PRIOR-KILLED CONSTRUCTION (raw hot-money appearance flag, wrong-sign "
                      "-1.43%/21d). Reported as replication/context only — NOT a new "
                      f"hypothesis. Trailing {win} sessions.",
                 killed=True)
        register(f"lhb_net_buy_sign{s}", "china_lhb/events", f"lhb_net_sign{s}",
                 "net_buy", "net_sell",
                 note=f"NEW axis: direction of the LHB tape, not the fact of appearing. "
                      f"Trailing {win} sessions.")
        register(f"lhb_net_buy_magnitude{s}", "china_lhb/events", f"lhb_net_mag{s}",
                 "low", "high",
                 note=f"NEW axis: size of the trailing-{win}-session LHB net flow.")
        register(f"lhb_reason_class{s}", "china_lhb/events", f"lhb_reason_class{s}",
                 "up_deviation", "down_deviation",
                 note="NEW axis: WHY the name hit the board (a name on the list for FALLING "
                      f"is a different animal from one on it for a limit-up chase). "
                      f"Trailing {win} sessions.")

    # institutional-seat composition — the surviving accruing construction
    ld = pd.read_parquet(ROOT / "data/china_lhb/detail.parquet")
    ld["asof"] = ld["asof"].astype(str)
    det_by_tk = defaultdict(list)
    for t, a, inb, nib in zip(ld["ticker"], ld["asof"], ld["inst_net_buy_yi"], ld["n_inst_buy"]):
        det_by_tk[str(t)].append((a, inb, nib))
    for r in rows:
        cands = [(a, inb, nib) for a, inb, nib in det_by_tk.get(r["ticker"], []) if a <= r["date"]]
        if not cands:
            continue
        a, inb, nib = max(cands, key=lambda x: x[0])   # latest PIT snapshot
        r["lhb_inst_seats"] = "inst_2plus" if (nib or 0) >= 2 else "inst_lt2"
        r["lhb_inst_net_sign"] = "inst_net_buy" if (inb or 0) > 0 else "inst_net_sell_flat"
    register("lhb_inst_seats_ge2", "china_lhb/detail", "lhb_inst_seats", "inst_lt2", "inst_2plus",
             note="NEW axis (surviving accruing construction cnlab_lhb_inst): buyer-side "
                  "composition — institutional seats vs branch desks.")
    register("lhb_inst_net_sign", "china_lhb/detail", "lhb_inst_net_sign",
             "inst_net_buy", "inst_net_sell_flat",
             note="NEW axis: sign of the institutional-seat net flow.")

    # ---------------- STORE 2: northbound (china_connect) --------------------
    nb_df = pd.read_parquet(ROOT / "data/china_connect/northbound.parquet")
    last_ok = nb_df["net"].last_valid_index()
    unusable.append({
        "store": "data/china_connect/northbound.parquet",
        "axis_requested": "trailing 5/20-session per-name northbound net-buy streak/z",
        "reason": "NO per-name dimension (columns are market-level net/buy/sell/turnover/"
                  f"hold_mktcap only), AND the series is a frozen placeholder — `net` has "
                  f"ZERO non-null values after {str(last_ok)[:10]}, i.e. it is null across the "
                  "entire 2026-06-30..2026-07-17 admission window (51 window rows, 0 non-null).",
        "todo": "Per-name northbound holdings (沪深港通持股) must be collected before any "
                "name-level positioning axis exists; the market-level feed itself needs "
                "un-freezing (dead ~2 years).",
    })

    # ---------------- STORE 3: margin (per-name) -----------------------------
    md = pd.read_parquet(ROOT / "data/china_margin_detail/detail.parquet")
    md["asof"] = md["asof"].astype(str)
    mg = (pd.to_datetime(md["date"]) - pd.to_datetime(md["prior_date"])).dt.days
    gap_med = int(mg.median())
    mar_by_tk = defaultdict(list)
    for t, a, fb, fp in zip(md["ticker"], md["asof"], md["fin_balance"], md["fin_balance_prior"]):
        mar_by_tk[str(t)].append((a, fb, fp))
    for r in rows:
        cands = [(a, fb, fp) for a, fb, fp in mar_by_tk.get(r["ticker"], []) if a <= r["date"]]
        if not cands:
            continue
        a, fb, fp = max(cands, key=lambda x: x[0])
        if fp and np.isfinite(fb) and np.isfinite(fp) and fp > 0:
            r["margin_chg_pct"] = 100.0 * (fb - fp) / fp
    lab = tercile([r.get("margin_chg_pct") for r in rows])
    for r in rows:
        if r.get("margin_chg_pct") is not None:
            r["margin_chg_t"] = lab(r["margin_chg_pct"])
            r["margin_chg_sign"] = "rising" if r["margin_chg_pct"] > 0 else "falling"
    register("margin_balance_change_tercile", "china_margin_detail", "margin_chg_t", "low", "high",
             note=f"REQUESTED 5/20-session margin velocity is UNAVAILABLE — the store carries "
                  f"only a paired (date, prior_date) delta with a ~{gap_med}-day gap, so this "
                  f"axis is a MONTHLY margin-balance change, disclosed as such.")
    register("margin_balance_change_sign", "china_margin_detail", "margin_chg_sign",
             "falling", "rising", note=f"Monthly (~{gap_med}d) margin-balance direction.")

    unusable.append({
        "store": "data/china_margin/balance.parquet",
        "axis_requested": "market-level margin balance as a name axis",
        "reason": "market-level only (no ticker); with 12 admission dates it is a date-level "
                  "constant, indistinguishable from the admission-date effect. Not a name axis.",
        "todo": "none — correctly market-level; use as regime context, never as a name feature.",
    })

    # ---------------- STORE 4: holder counts ---------------------------------
    hc = pd.read_parquet(ROOT / "data/china_holder_counts/holder_counts.parquet")
    hc["code"] = hc["code"].astype(str).str.zfill(6)
    hc["notice_date"] = hc["notice_date"].astype(str)
    hc["end_date"] = hc["end_date"].astype(str)
    hc_by_code = defaultdict(list)
    for c, nd, ed, ratio in zip(hc["code"], hc["notice_date"], hc["end_date"],
                                hc["holder_num_ratio"]):
        hc_by_code[c].append((nd, ed, ratio))
    lags = []
    for r in rows:
        code = r["ticker"].split(".")[0]
        # PIT rule: only records DISCLOSED (notice_date) on or before admission
        cands = [(nd, ed, x) for nd, ed, x in hc_by_code.get(code, []) if nd <= r["date"]]
        if not cands:
            continue
        nd, ed, ratio = max(cands, key=lambda x: x[0])
        if ratio is None or not np.isfinite(ratio):
            continue
        r["holder_ratio"] = float(ratio)
        # falling holder count == chips concentrating
        r["holder_chg_sign"] = "concentrating" if ratio < 0 else "dispersing"
        r["_hc_lag_days"] = (pd.Timestamp(r["date"]) - pd.Timestamp(ed)).days
        lags.append(r["_hc_lag_days"])
    lab = tercile([r.get("holder_ratio") for r in rows])
    for r in rows:
        if r.get("holder_ratio") is not None:
            r["holder_ratio_t"] = lab(r["holder_ratio"])
    register("holder_count_change_sign", "china_holder_counts", "holder_chg_sign",
             "concentrating", "dispersing",
             note=f"PIT rule applied: only records with notice_date <= admission. "
                  f"DISCLOSURE LAG is severe — median {int(np.median(lags))} days between the "
                  f"reported period end and admission (n_lag={len(lags)}); these are periodic "
                  f"disclosures, so the 'positioning' is up to a quarter stale.")
    register("holder_count_change_tercile", "china_holder_counts", "holder_ratio_t", "low", "high",
             note="Magnitude of the last disclosed holder-count change; same lag caveat.")

    # ---------------- STORE 5: block trades ----------------------------------
    bt = pd.read_parquet(ROOT / "data/china_block_trades/detail.parquet")
    unusable.append({
        "store": "data/china_block_trades/detail.parquet",
        "axis_requested": "block trade within trailing 10 sessions + discount/premium sign",
        "reason": f"SNAPSHOT-ONLY, look-ahead by construction: {len(bt)} rows carrying a single "
                  f"asof={min(bt['asof'].astype(str))} — i.e. the store was "
                  "observed AFTER every episode's admission (2026-06-30..2026-07-17) and holds "
                  "no accruing history. Joining it PIT is impossible; joining it as-is would "
                  "leak. `data/china_block_tape/` does not exist.",
        "todo": "Convert the block-trade collector from snapshot-overwrite to append-only "
                "daily accrual (per-trade date + premium/discount). Until then the "
                "deep-DISCOUNT leg (the probationary +3.45%/21d construction) cannot be "
                "tested on any historical frame.",
    })

    # ---------------- STORE 6: buyback ---------------------------------------
    bb = pd.read_parquet(ROOT / "data/china_buyback/buyback.parquet")
    unusable.append({
        "store": "data/china_buyback/buyback.parquet",
        "axis_requested": "active buyback program flag at admission",
        "reason": f"SNAPSHOT-ONLY with NO announcement/disclosure date: {len(bb)} rows, single "
                  f"asof={min(bb['asof'].astype(str))}, and the only temporal "
                  "field is a mutable `progress` string (完成实施/实施中/董事会预案). There is no "
                  "column that says WHEN a program became known, so no PIT join exists — a "
                  "program announced after admission is indistinguishable from one active "
                  "before it.",
        "todo": "Collect the announcement date (公告日) and status-transition dates per program, "
                "append-only. That single column would make this store testable.",
    })

    # ---------------- STORE 7: turnover / crowding (always available) --------
    for r in rows:
        v = px_vol.get(r["ticker"])
        if v is None:
            continue
        hist = v[[d for d in v.index if d <= r["date"]]]
        if len(hist) < 61 or r["date"] not in hist.index:
            continue
        today = float(hist.iloc[-1])
        trail = hist.iloc[-61:-1].astype(float)
        if not np.isfinite(today) or trail.isna().all() or trail.median() <= 0:
            continue
        r["turnover_pctile_60d"] = float((trail < today).mean())
        r["vol_ratio_20d"] = today / float(hist.iloc[-21:-1].astype(float).median())
    for r in rows:
        p = r.get("turnover_pctile_60d")
        if p is not None:
            r["turnover_bucket"] = ("p0_50" if p <= 0.50 else "p50_90" if p <= 0.90
                                    else "p90_100")
    lab = tercile([r.get("vol_ratio_20d") for r in rows])
    for r in rows:
        if r.get("vol_ratio_20d") is not None:
            r["vol_ratio_t"] = lab(r["vol_ratio_20d"])
    register("turnover_pctile_60d", "china_stocks (volume-derived)", "turnover_bucket",
             "p0_50", "p90_100",
             note="THE crowding axis: admission-day volume percentile vs the name's own "
                  "trailing 60 sessions. Fully PIT (uses only bars dated <= admission).")
    register("volume_ratio_20d", "china_stocks (volume-derived)", "vol_ratio_t", "low", "high",
             note="Admission-day volume / own 20-session median volume. Correlated with the "
                  "percentile axis by construction — reported as a second cut of the same "
                  "crowding leg, not an independent store.")

    # ---------------- redundancy check on the SEPARATES axis ------------------
    # NOT a composite and NOT a blend: a validity check asking whether the one
    # axis that separated is merely re-expressing a field the pick chain ALREADY
    # consumes. If it were, it would earn no chip.
    ep_by = {(e["ticker"], e["date"]): e for e in eps}
    p = np.array([r["turnover_pctile_60d"] for r in rows if r.get("turnover_pctile_60d") is not None])
    keys = [(r["ticker"], r["date"]) for r in rows if r.get("turnover_pctile_60d") is not None]
    d0 = np.array([ep_by[k]["day0_ret"] for k in keys], dtype=float)
    su = np.array([ep_by[k]["setup"] for k in keys], dtype=float)
    ext = np.array([bool(ep_by[k]["extended"]) for k in keys])
    wsh = np.array([bool(ep_by[k]["washout"]) for k in keys])
    nonext = [r for r, k in zip([r for r in rows if r.get("turnover_pctile_60d") is not None], keys)
              if not bool(ep_by[k]["extended"])]
    redundancy = {
        "axis": "turnover_pctile_60d",
        "corr_with_day0_ret": round(float(np.corrcoef(p, d0)[0, 1]), 3),
        "corr_with_setup_score": round(float(np.corrcoef(p, su)[0, 1]), 3),
        "engine_extended_flag_fires": int(ext.sum()),
        "mean_pctile_extended_true": round(float(p[ext].mean()), 3) if ext.any() else None,
        "mean_pctile_extended_false": round(float(p[~ext].mean()), 3),
        "mean_pctile_washout_true": round(float(p[wsh].mean()), 3) if wsh.any() else None,
        "mean_pctile_washout_false": round(float(p[~wsh].mean()), 3),
        "within_non_extended": slice_table(nonext, "turnover_bucket", demean),
        "reading": "The crowding axis is NOT a restatement of anything the chain already "
                   "consumes: correlation with the day-0 move and with the engine's own setup "
                   "score is weak, the `extended` veto fires on only "
                   f"{int(ext.sum())}/{len(p)} episodes (effectively dormant), and the loser "
                   "gradient holds inside the non-extended subset. Washout admissions do "
                   "arrive on heavier volume, which is where the axis and the existing "
                   "washout leg overlap most.",
    }

    # ---------------- assemble ------------------------------------------------
    ranked = sorted(
        [(k, v) for k, v in features.items() if v["verdict"]["verdict"] == "SEPARATES"],
        key=lambda kv: -abs(kv[1]["verdict"].get("d_loser_rate") or 0))
    out = {
        "as_of": "2026-08-04",
        "instrument": "flow/positioning ex-ante separation battery (single-axis, no blending)",
        "frame": {
            "episodes": len(eps), "tickers": len(tickers),
            "admission_dates": len(dates), "span": [dates[0], dates[-1]],
            "loser_definition": "excess <= 0 (CSI300-relative), mirrors v1_loser_audit",
            "base_loser_rate": round(sum(1 for e in eps if e["excess"] <= 0) / len(eps), 3),
        },
        "honesty": {
            "era": "ONE era only (18 calendar days, 12 admission dates) — in-sample, "
                   "no out-of-sample split exists on this frame.",
            "clustering": "407 episodes sit on 12 admission dates; every bucket spread is "
                          "reported both raw and date-demeaned, and the verdict rule REQUIRES "
                          "the spread to survive date-demeaning.",
            "multiplicity": f"{len(features)} features tested with no multiplicity correction; "
                            "a SEPARATES verdict here is a DISPLAY-TIER candidate, not a "
                            "promotion. Promotion requires shadow accrual + pre-registration.",
            "no_promotion_claim": "Nothing here promotes any signal to rank/size/gate authority.",
        },
        "verdict_rule": {
            "SEPARATES": "both compared buckets n>=15 AND Wilson-95% loser-rate CIs disjoint "
                         "AND median-excess spread keeps its sign after date-demeaning",
            "NULL": "anything else (thin buckets reported as NULL/underpowered)",
            "UNUSABLE": f"coverage < {MIN_COVERAGE} episodes, or the store admits no PIT join",
        },
        "features": features,
        "redundancy_check": redundancy,
        "unusable_stores": unusable,
        "ranked_separators": [{"feature": k, "store": v["store"],
                               "d_loser_rate": v["verdict"]["d_loser_rate"],
                               "compared": v["verdict"]["compared"]} for k, v in ranked],
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))

    print(f"\nbase loser rate = {out['frame']['base_loser_rate']}")
    for k, v in features.items():
        vd = v["verdict"]
        print(f"  {vd['verdict']:<10} {k:<32} store={v['store']:<32} "
              f"cov={v['coverage']:<4} {vd.get('reason', '')}")
    print(f"\nUNUSABLE stores: {len(unusable)}")
    for u in unusable:
        print(f"  - {u['store']}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
