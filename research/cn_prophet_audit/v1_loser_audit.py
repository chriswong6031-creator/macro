"""China Prophet V1 (cn_standout_v1 / board_definition='legacy') loser forensics.

MEASUREMENT INSTRUMENT, not a signal. Mirrors research/prophet_us_audit/
runner_exclusion_audit.py: production code paths over committed stores, frozen
results committed next to the script. Consumed by the CN loser-audit masterplan.

What it does
------------
1. Rebuilds the exact V1 episode set the shipped ledger grades (P0 discipline:
   engine.track_scoring.build_episodes over data/china_standout_track/board.parquet
   legacy rows, T+1 fill via engine.china_standout_track._t1_fill, H=10 forced
   verdict, CSI300-relative) and asserts it reproduces the shipped headline
   (n_matured 407, win 68.6%) before any new number is printed.
2. Enriches every matured episode with admission-day board fields (rank/tier/
   setup/extension/washout/coiled/entry_status/ab_tier/narrative) and
   admission-day price character (trailing returns, drawdown-from-high, MA
   distances, day-0 pop/limit-up, T+1 gap, volume surge).
3. Walks the 10-session forward path per episode: MAE/MFE, worst day,
   limit-down days, loss anatomy (crash / bleed / pop_fade / chop).
4. Aggregates loser-vs-winner contrasts, date/sector clustering, and costed
   counterfactual filters (losers removed vs winners forfeited — a filter that
   cuts winners is priced, not assumed).
5. Retro-applies the cn_prophet_v2 featured gates to the field-covered subset
   (2026-07-07+) to measure which loser cohorts V2 would already exclude.

Run from repo root:  python3 research/cn_prophet_audit/v1_loser_audit.py
Outputs: research/cn_prophet_audit/v1_loser_audit_results.json (frozen)
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine import china_standout_track as cst  # noqa: E402
from engine import track_scoring as ts  # noqa: E402

H = 10  # the shipped CN horizon (forced verdict)
OUT = Path(__file__).parent / "v1_loser_audit_results.json"

# A-share daily price-limit thresholds by listing board (approx, non-ST):
#   688* (STAR) and 300* (ChiNext): ±20%  → detect at |ret| ≥ 0.185
#   main boards (60*/00*):          ±10%  → detect at |ret| ≥ 0.095
def limit_threshold(ticker: str) -> float:
    code = ticker.split(".")[0]
    return 0.185 if code.startswith(("300", "688")) else 0.095


def pct(a: float | None, nd: int = 4) -> float | None:
    return None if a is None or not np.isfinite(a) else round(float(a), nd)


def load_board() -> pd.DataFrame:
    df = pd.read_parquet(ROOT / "data/china_standout_track/board.parquet")
    return df[df["board_definition"] == "legacy"].copy()


def sector_lookup() -> dict[str, dict]:
    led = json.loads((ROOT / "site/factordata/cn_track_ledger.json").read_text())
    look: dict[str, dict] = {}
    for r in led.get("prior_record", {}).get("rows", []):
        look[r["t"]] = {"nm": r.get("nm"), "sec": r.get("sec")}
    return look


def admission_character(pdf: pd.DataFrame, d0: pd.Timestamp) -> dict:
    """Price character AT the board date d0 (all trailing, no lookahead)."""
    out: dict = {}
    closes = pd.to_numeric(pdf["close"], errors="coerce").dropna()
    hist = closes[closes.index <= d0]
    if len(hist) < 22:
        return out
    c0 = float(hist.iloc[-1])
    prev = float(hist.iloc[-2])
    out["day0_ret"] = pct(c0 / prev - 1.0)
    for n, key in ((5, "trail_5"), (21, "trail_21"), (63, "trail_63")):
        if len(hist) > n:
            out[key] = pct(c0 / float(hist.iloc[-1 - n]) - 1.0)
    hi252 = float(hist.iloc[-252:].max()) if len(hist) >= 30 else None
    if hi252:
        out["dd_from_high"] = pct(c0 / hi252 - 1.0)
    for n, key in ((20, "vs_ma20"), (50, "vs_ma50"), (200, "vs_ma200")):
        if len(hist) >= n:
            out[key] = pct(c0 / float(hist.iloc[-n:].mean()) - 1.0)
    # day-0 limit-up: close at that day's high AND day move ≥ board limit
    row0 = pdf.loc[d0] if d0 in pdf.index else None
    if row0 is not None and pd.notna(row0.get("high")):
        out["day0_at_high"] = bool(float(row0["high"]) == c0)
    # volume surge: day-0 volume vs trailing 20d average (excluding day 0)
    if "volume" in pdf.columns:
        vol = pd.to_numeric(pdf["volume"], errors="coerce").dropna()
        vh = vol[vol.index <= d0]
        if len(vh) >= 21 and float(vh.iloc[-21:-1].mean()) > 0:
            out["vol_surge"] = pct(float(vh.iloc[-1]) / float(vh.iloc[-21:-1].mean()), 2)
    # consecutive up-days into admission
    ups = 0
    for i in range(len(hist) - 1, 0, -1):
        if float(hist.iloc[i]) > float(hist.iloc[i - 1]):
            ups += 1
        else:
            break
    out["consec_up"] = ups
    return out


def forward_path(pdf: pd.DataFrame, d0: pd.Timestamp, fill: float, ticker: str) -> dict:
    """Forward 10-session path anatomy from the T+1 fill (window includes fill bar)."""
    closes = pd.to_numeric(pdf["close"], errors="coerce").dropna()
    fwd = closes[closes.index > d0]
    if fwd.empty:
        return {}
    win = fwd.iloc[: H + 1]  # fill bar + H sessions (include_fill_bar=True convention)
    rets = win.to_numpy(dtype=float) / fill - 1.0
    daily = np.array(win.pct_change().to_numpy(dtype=float), copy=True)
    if d0 in closes.index:
        daily[0] = float(win.iloc[0]) / float(closes.loc[d0]) - 1.0
    th = limit_threshold(ticker)
    out = {
        "mae": pct(float(np.min(rets))),
        "mfe": pct(float(np.max(rets))),
        "day_of_min": int(np.argmin(rets)),
        "day_of_max": int(np.argmax(rets)),
        "worst_day": pct(float(np.nanmin(daily))),
        "n_limit_down": int(np.nansum(daily <= -th)),
        "n_limit_up_fwd": int(np.nansum(daily >= th)),
        "first3": pct(float(rets[min(3, len(rets) - 1)])),
        # T+1 gap: fill vs board-date close (chase premium paid at open)
        "t1_gap": pct(fill / float(closes.loc[d0]) - 1.0) if d0 in closes.index else None,
    }
    mae, mfe = out["mae"] or 0.0, out["mfe"] or 0.0
    if mae <= -0.12 and out["day_of_min"] <= 5:
        shape = "crash"
    elif mae <= -0.08:
        shape = "bleed"
    elif mfe >= 0.05 and rets[-1] < 0:
        shape = "pop_fade"
    else:
        shape = "chop"
    out["shape"] = shape
    return out


def build_sector_rel(look: dict[str, dict], bench: pd.Series | None) -> dict[str, pd.Series]:
    """PIT sector peer-relative 20d trend, from the episode universe itself.

    For each sector: equal-weight mean of member 20d trailing returns (board-era
    names as the peer set), minus the CSI300 20d trailing return, per session.
    Self-contained proxy — no external sector index needed.
    """
    members: dict[str, list[str]] = defaultdict(list)
    for tk, meta in look.items():
        if meta.get("sec"):
            members[meta["sec"]].append(tk)
    out: dict[str, pd.Series] = {}
    bench_r20 = (bench / bench.shift(20) - 1.0) if bench is not None else None
    for sec, tks in members.items():
        cols = []
        for tk in tks:
            pdf = cst._price_frame(tk)  # noqa: SLF001
            if pdf is None or "close" not in pdf:
                continue
            c = pd.to_numeric(pdf["close"], errors="coerce").dropna()
            cols.append((c / c.shift(20) - 1.0).rename(tk))
        if not cols:
            continue
        panel = pd.concat(cols, axis=1)
        ew = panel.mean(axis=1, skipna=True)
        out[sec] = (ew - bench_r20.reindex(ew.index)) if bench_r20 is not None else ew
    return out


def main() -> None:
    board = load_board()
    look = sector_lookup()
    bench = cst._bench_close()  # noqa: SLF001
    sector_rel = build_sector_rel(look, bench)

    board_days: dict[str, set[str]] = defaultdict(set)
    admit: dict[tuple[str, str], dict] = {}
    for _, r in board.iterrows():
        d, tk = str(r["date"]), str(r["ticker"])
        board_days[d].add(tk)
        admit[(d, tk)] = r.to_dict()

    episodes = []
    n_locked = n_skipped = 0
    for ep in ts.build_episodes(board_days):
        tk, d0s = ep["ticker"], ep["entry_date"]
        d0 = pd.Timestamp(d0s)
        pdf = cst._price_frame(tk)  # noqa: SLF001
        if pdf is None or "close" not in pdf:
            n_skipped += 1
            continue
        fill, locked, pinned = cst._t1_fill(pdf, d0)  # noqa: SLF001
        if locked:
            n_locked += 1
        closes = pd.to_numeric(pdf["close"], errors="coerce").dropna()
        after = closes.index[closes.index > d0]
        sc = None
        if fill is not None and len(after):
            sc = ts.score_from_fill(closes, after[0], float(fill), H,
                                    bench_close=bench, include_fill_bar=True)
        if sc is None:
            n_skipped += 1
            continue
        matured = bool(sc["matured"]) and not locked
        rec = {
            "ticker": tk, "date": d0s, "matured": matured,
            "excess": pct(sc.get("excess")), "pnl": pct(sc.get("pnl")),
            "held": sc.get("held"), "exit_reason": sc.get("exit_reason"),
            "pinned_ref": bool(pinned),
            "sector": (look.get(tk) or {}).get("sec"),
            "name": (look.get(tk) or {}).get("nm"),
        }
        a = admit.get((d0s, tk)) or {}
        rec.update({
            "rank": a.get("board_rank"),
            "tier": a.get("tier") if pd.notna(a.get("tier")) else None,
            "setup": pct(a.get("setup")),
            "extended": bool(a.get("extended")),
            "washout": bool(a.get("washout")),
            "coiled": bool(a.get("coiled")) if a.get("coiled") is not None else None,
            "ticks": None if pd.isna(a.get("ticks")) else float(a.get("ticks")),
            "ext_score": None if pd.isna(a.get("ext_score")) else float(a.get("ext_score")),
            "entry_status": a.get("entry_status") if isinstance(a.get("entry_status"), str) else None,
            "hold_state": a.get("hold_state") if isinstance(a.get("hold_state"), str) else None,
            "stage": a.get("stage") if isinstance(a.get("stage"), str) else None,
            "narr_theme": a.get("narr_theme") if isinstance(a.get("narr_theme"), str) else None,
            "narr_level": a.get("narr_level") if isinstance(a.get("narr_level"), str) else None,
            "ab_tier": a.get("ab_tier") if isinstance(a.get("ab_tier"), str) else None,
        })
        if matured:
            rec.update(admission_character(pdf, d0))
            if fill is not None:
                rec.update(forward_path(pdf, d0, float(fill), tk))
            sec_ser = sector_rel.get(str(rec.get("sector")))
            if sec_ser is not None:
                hist = sec_ser[sec_ser.index <= d0].dropna()
                if len(hist):
                    rec["sector_rel20"] = pct(float(hist.iloc[-1]))
                if len(hist) >= 6:
                    rec["sector_rel20_slope5"] = pct(float(hist.iloc[-1] - hist.iloc[-6]))
        rec["initial_stock"] = d0s == "2026-06-30"
        episodes.append(rec)

    mat = [e for e in episodes if e["matured"] and e["excess"] is not None]
    losers = [e for e in mat if e["excess"] <= 0]
    winners = [e for e in mat if e["excess"] > 0]
    win_rate = len(winners) / len(mat) if mat else None

    print(f"episodes={len(episodes)} matured={len(mat)} "
          f"win={100 * win_rate:.1f}% losers={len(losers)} "
          f"locked={n_locked} skipped={n_skipped}")
    # P0 reproduction gate — shipped ledger: n_matured=407, win 68.6%
    assert len(mat) == 407, f"matured {len(mat)} != shipped 407"
    assert abs(100 * win_rate - 68.6) < 0.15, f"win {100 * win_rate:.2f} != shipped 68.6"

    def med(rows, key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return pct(float(np.median(vals))) if vals else None

    def share(rows, key, val=True):
        vals = [r.get(key) for r in rows if r.get(key) is not None]
        return pct(sum(1 for v in vals if v == val) / len(vals)) if vals else None

    contrast_keys = [
        "trail_5", "trail_21", "trail_63", "dd_from_high", "vs_ma20", "vs_ma50",
        "vs_ma200", "day0_ret", "vol_surge", "consec_up", "t1_gap", "setup",
        "ext_score", "ticks", "mae", "mfe", "worst_day", "pnl", "excess",
        "sector_rel20", "sector_rel20_slope5",
    ]
    contrasts = {k: {"losers": med(losers, k), "winners": med(winners, k)}
                 for k in contrast_keys}
    contrasts["extended_share"] = {"losers": share(losers, "extended"),
                                   "winners": share(winners, "extended")}
    contrasts["washout_share"] = {"losers": share(losers, "washout"),
                                  "winners": share(winners, "washout")}
    contrasts["day0_at_high_share"] = {"losers": share(losers, "day0_at_high"),
                                       "winners": share(winners, "day0_at_high")}
    contrasts["pinned_ref_share"] = {"losers": share(losers, "pinned_ref"),
                                     "winners": share(winners, "pinned_ref")}

    def strat(rows, key):
        groups: dict = defaultdict(list)
        for r in rows:
            groups[str(r.get(key))].append(r)
        out = {}
        for k, g in sorted(groups.items()):
            gm = [r for r in g if r["excess"] is not None]
            if not gm:
                continue
            out[k] = {
                "n": len(gm),
                "loser_rate": pct(sum(1 for r in gm if r["excess"] <= 0) / len(gm)),
                "median_excess": med(gm, "excess"),
                "median_pnl": med(gm, "pnl"),
            }
        return out

    by_date = strat(mat, "date")
    for d, blk in by_date.items():
        if bench is not None:
            b = bench[bench.index > pd.Timestamp(d)]
            if len(b) > H:
                blk["csi300_fwd10"] = pct(float(b.iloc[H] / b.iloc[0] - 1.0))

    # date × sector loser cells (≥3 matured, ≥60% losers)
    cells: dict = defaultdict(list)
    for r in mat:
        cells[(r["date"], str(r["sector"]))].append(r)
    clusters = [
        {"date": d, "sector": s, "n": len(g),
         "losers": sum(1 for r in g if r["excess"] <= 0),
         "median_excess": med(g, "excess"),
         "tickers": [r["ticker"] for r in g]}
        for (d, s), g in cells.items()
        if len(g) >= 3 and sum(1 for r in g if r["excess"] <= 0) / len(g) >= 0.6
    ]
    clusters.sort(key=lambda c: (c["median_excess"] or 0))

    # counterfactual filters — losers removed vs winners forfeited, costed
    def cost(name, fn, base=mat):
        hit = [r for r in base if fn(r)]
        kept = [r for r in base if not fn(r)]
        return {
            "filter": name,
            "n_removed": len(hit),
            "losers_removed": sum(1 for r in hit if r["excess"] <= 0),
            "winners_removed": sum(1 for r in hit if r["excess"] > 0),
            "removed_median_excess": med(hit, "excess"),
            "kept_n": len(kept),
            "kept_win_rate": pct(sum(1 for r in kept if r["excess"] > 0) / len(kept))
            if kept else None,
            "kept_median_excess": med(kept, "excess"),
        }

    base_stats = {"n": len(mat), "win_rate": pct(win_rate),
                  "median_excess": med(mat, "excess")}
    filters = [
        cost("extended_true", lambda r: r["extended"]),
        cost("day0_limit_or_high_close", lambda r: r.get("day0_at_high") is True
             and (r.get("day0_ret") or 0) >= limit_threshold(r["ticker"]) * 0.95),
        cost("day0_pop_ge5", lambda r: (r.get("day0_ret") or 0) >= 0.05),
        cost("vol_surge_ge4x", lambda r: (r.get("vol_surge") or 0) >= 4.0),
        cost("t1_gap_ge3", lambda r: (r.get("t1_gap") or 0) >= 0.03),
        cost("trail21_ge25", lambda r: (r.get("trail_21") or 0) >= 0.25),
        cost("consec_up_ge5", lambda r: (r.get("consec_up") or 0) >= 5),
        cost("vs_ma20_ge15", lambda r: (r.get("vs_ma20") or 0) >= 0.15),
        cost("rank_gt_40", lambda r: (r.get("rank") or 0) > 40),
        cost("tier_T3", lambda r: r.get("tier") == "T3"),
        cost("pinned_ref", lambda r: r.get("pinned_ref") is True),
        cost("sector_rel20_neg", lambda r: (r.get("sector_rel20") or 0) < 0
             and r.get("sector_rel20") is not None),
        cost("sector_rel20_pos_and_falling",
             lambda r: r.get("sector_rel20") is not None
             and r["sector_rel20"] > 0.02
             and (r.get("sector_rel20_slope5") or 0) < 0),
        cost("sector_hot_rel20_ge5", lambda r: (r.get("sector_rel20") or 0) >= 0.05),
        cost("chase_composite",
             lambda r: ((r.get("day0_at_high") is True
                         and (r.get("day0_ret") or 0) >= limit_threshold(r["ticker"]) * 0.95)
                        or (r.get("t1_gap") or 0) >= 0.03
                        or (r.get("trail_21") or 0) >= 0.25)),
    ]

    # limit-down / gap-risk anatomy among matured episodes
    def agg_path(rows):
        return {
            "n": len(rows),
            "any_limit_down": sum(1 for r in rows if (r.get("n_limit_down") or 0) >= 1),
            "worst_day_le_-7": sum(1 for r in rows if (r.get("worst_day") or 0) <= -0.07),
            "median_worst_day": med(rows, "worst_day"),
            "median_mae": med(rows, "mae"),
            "median_mfe": med(rows, "mfe"),
        }

    path_anatomy = {"losers": agg_path(losers), "winners": agg_path(winners)}

    # fresh-only view (excludes the 2026-06-30 initial board stock)
    fresh = [r for r in mat if not r.get("initial_stock")]
    fresh_stats = {
        "n": len(fresh),
        "win_rate": pct(sum(1 for r in fresh if r["excess"] > 0) / len(fresh)) if fresh else None,
        "median_excess": med(fresh, "excess"),
        "loser_rate_initial_stock": pct(
            sum(1 for r in mat if r.get("initial_stock") and r["excess"] <= 0)
            / max(1, sum(1 for r in mat if r.get("initial_stock")))),
    }

    # same-day sector-cohort cap counterfactual (V2 caps featured at 4/sector;
    # V1 had no sector logic at all): drop same-date same-sector episode entries
    # beyond the 4 best-ranked.
    cap_removed = []
    for (dt, sec), g in cells.items():
        if len(g) > 4:
            cap_removed.extend(
                sorted(g, key=lambda r: (r.get("rank") or 999))[4:])
    cap_ids = {(r["ticker"], r["date"]) for r in cap_removed}
    sector_cap_cf = cost("sector_cap_4_per_day",
                         lambda r: (r["ticker"], r["date"]) in cap_ids)
    filters.append(sector_cap_cf)

    # board rank-IC on matured episodes (rank vs excess; NEGATIVE = well-ordered)
    rank_ic = None
    ics = []
    for dt, g in pd.DataFrame(mat).groupby("date"):
        sub = g.dropna(subset=["rank", "excess"])
        if sub["rank"].nunique() >= 5:
            ics.append(float(sub["rank"].rank().corr(sub["excess"].rank())))
    if ics:
        rank_ic = {"mean_rank_ic": pct(float(np.mean(ics))), "n_dates": len(ics)}

    # V2 featured-gate retro on the field-covered subset (entry_status present)
    v2_sub = [r for r in mat if r.get("entry_status")]
    v2_gate = None
    if v2_sub:
        feat = [r for r in v2_sub
                if r["entry_status"] in ("buy_now", "partial") and not r["extended"]]
        excl = [r for r in v2_sub if r not in feat]
        v2_gate = {
            "n_covered": len(v2_sub),
            "covered_win_rate": pct(sum(1 for r in v2_sub if r["excess"] > 0) / len(v2_sub)),
            "featured_like": {"n": len(feat),
                              "win_rate": pct(sum(1 for r in feat if r["excess"] > 0) / len(feat)) if feat else None,
                              "median_excess": med(feat, "excess")},
            "excluded_like": {"n": len(excl),
                              "win_rate": pct(sum(1 for r in excl if r["excess"] > 0) / len(excl)) if excl else None,
                              "median_excess": med(excl, "excess")},
            "by_entry_status": strat(v2_sub, "entry_status"),
        }

    # repeat admissions: second-episode outcomes conditioned on first-episode result
    by_tk: dict = defaultdict(list)
    for r in sorted(mat, key=lambda x: x["date"]):
        by_tk[r["ticker"]].append(r)
    # BUILDABLE leg discipline (PROPHET_LEARNING_LOOP): condition only on what is
    # knowable at re-admission. The prior verdict is knowable when the prior episode's
    # H+1-session window has fully elapsed before the re-admission date.
    trading_days = sorted({r["date"] for r in episodes})
    day_idx = {d: i for i, d in enumerate(trading_days)}
    seq = {"after_loss": [], "after_win": [],
           "after_resolved_loss": [], "after_unresolved_prior": []}
    for tk, g in by_tk.items():
        for i in range(1, len(g)):
            prior, cur = g[i - 1], g[i]
            (seq["after_loss"] if prior["excess"] <= 0 else seq["after_win"]).append(cur)
            gap_board_days = day_idx.get(cur["date"], 0) - day_idx.get(prior["date"], 0)
            resolved = gap_board_days >= 8  # ~11 sessions incl. non-board days; conservative
            if resolved and prior["excess"] <= 0:
                seq["after_resolved_loss"].append(cur)
            elif not resolved:
                seq["after_unresolved_prior"].append(cur)
    readmit = {
        k: {"n": len(v),
            "win_rate": pct(sum(1 for r in v if r["excess"] > 0) / len(v)) if v else None,
            "median_excess": med(v, "excess")}
        for k, v in seq.items()
    }

    out = {
        "as_of": "2026-08-03",
        "definition": "cn_standout_v1 (board_definition='legacy')",
        "reproduction": {"episodes": len(episodes), "matured": len(mat),
                         "win_rate": pct(win_rate), "losers": len(losers),
                         "n_locked": n_locked, "n_skipped": n_skipped,
                         "shipped": {"n_matured": 407, "win_pct": 68.6}},
        "base": base_stats,
        "loss_anatomy": dict(Counter(r.get("shape") for r in losers)),
        # NOTE: score_from_fill returns pnl/excess in PERCENT units (4.44 = +4.44%).
        # Locally computed path/character features (mae, mfe, trail_*, …) are decimals.
        "abs_vs_rel_losers": {
            "abs_loss_le_-5pct": sum(1 for r in losers if (r["pnl"] or 0) <= -5.0),
            "abs_loss_le_-10pct": sum(1 for r in losers if (r["pnl"] or 0) <= -10.0),
            "abs_loss_le_-15pct": sum(1 for r in losers if (r["pnl"] or 0) <= -15.0),
            "abs_positive_rel_lag": sum(1 for r in losers if (r["pnl"] or 0) > 0),
        },
        "contrasts": contrasts,
        "by_tier": strat(mat, "tier"),
        "by_sector": strat(mat, "sector"),
        "by_date": by_date,
        "path_anatomy": path_anatomy,
        "fresh_only": fresh_stats,
        "by_entry_status": strat(mat, "entry_status"),
        "by_ab_tier": strat(mat, "ab_tier"),
        "by_narr_level": strat(mat, "narr_level"),
        "by_stage": strat(mat, "stage"),
        "loser_clusters_date_sector": clusters,
        "counterfactual_filters": filters,
        "board_rank_ic": rank_ic,
        "v2_featured_gate_retro": v2_gate,
        "readmission": readmit,
        # early-tell: does the first-3-session mark separate eventual losers?
        "first3_tell": {
            "P_loser_given_first3_le_-3": pct(
                (lambda g: sum(1 for r in g if r["excess"] <= 0) / len(g) if g else None)(
                    [r for r in mat if (r.get("first3") or 0) <= -0.03])),
            "n_first3_le_-3": sum(1 for r in mat if (r.get("first3") or 0) <= -0.03),
            "P_loser_given_first3_gt_0": pct(
                (lambda g: sum(1 for r in g if r["excess"] <= 0) / len(g) if g else None)(
                    [r for r in mat if (r.get("first3") or 0) > 0])),
            "median_final_pnl_losers_first3_le_-3": med(
                [r for r in losers if (r.get("first3") or 0) <= -0.03], "pnl"),
            "median_first3_losers": med(losers, "first3"),
            "median_first3_winners": med(winners, "first3"),
        },
        "worst_20": sorted(losers, key=lambda r: r["excess"])[:20],
        # compact per-episode table for downstream reuse (W0 nightly engine seed)
        "episodes": [
            {k: r.get(k) for k in (
                "ticker", "date", "sector", "rank", "tier", "setup", "extended",
                "washout", "entry_status", "stage", "narr_level", "ab_tier",
                "excess", "pnl", "mae", "mfe", "first3", "worst_day",
                "n_limit_down", "shape", "day0_ret", "day0_at_high", "t1_gap",
                "trail_5", "trail_21", "trail_63", "dd_from_high", "vs_ma20",
                "initial_stock", "pinned_ref")}
            for r in mat
        ],
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    print(f"wrote {OUT}")
    print(json.dumps({k: out[k] for k in ("base", "loss_anatomy", "abs_vs_rel_losers")},
                     indent=1))


if __name__ == "__main__":
    main()
