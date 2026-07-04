"""W1 S13 phase-0 — US Within-Sector Reversal Sleeve on the deep panel.

Pre-registration: research/species/W1_S13_PREREG.md (committed BEFORE this run;
trial family `s13_reversal_sleeve`, m=2 configs: formation ∈ {21, 63} trading
days). Everything else is FIXED — any new knob is a new §8-recorded trial.

Construction (per prereg):
  * Monthly rebalance at month-end close t (PIT era 1996-07 → last full month).
  * Universe: PIT S&P-500 members at t (sp500_pit_membership) ∩ deep-panel names
    priced at t and t−f (deep matrix UNION recovered delisted names).
  * Within each current-GICS sector with ≥5 eligible names: deepest quintile by
    formation return, equal weight. Hygiene-only screens. assert_no_gate.
  * Fills honor §1.2 (never same-bar): entry = first close STRICTLY AFTER t;
    exit = first close strictly after the next rebalance. A name with no exit
    print grades at its last available close (delisting = the honest loss).
  * Benchmark: SPY over the identical entry→exit window.

Verdict metrics (per prereg): mean monthly excess vs SPY, HAC t, deflated
Sharpe (n_trials=2) + dsr_verdict, block-bootstrap CI; era splits for the
pre-registered kill criteria K1 (modern 2002→), K2 (2024→ mega-cap flip),
K3 (single-name concentration >50% of cumulative excess), K4 (within-sector
IC sign sanity). Safety-net axes per fire: terminal_state at clean8_21
(primary, rotational) and clean15_126 (context grid).

Usage:
  python -m scripts.s13_reversal_phase0            # both registered configs
  python -m scripts.s13_reversal_phase0 --formation 21
Output: research/species/_s13_phase0_out.json + stdout tables.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import grading                    # noqa: E402
from engine.trial_ledger import TrialLedger   # noqa: E402
from engine.validation import (               # noqa: E402
    block_bootstrap_ci, deflated_sharpe, dsr_verdict, ic_summary, rank_ic,
)
from engine.equity_factors import _names_sectors   # noqa: E402
from lib import config, store                 # noqa: E402

PIT_START = pd.Timestamp("1996-07-01")
MODERN_START = pd.Timestamp("2002-01-01")
FLIP_START = pd.Timestamp("2024-01-01")
MIN_SECTOR_NAMES = 5
# DSR multiple-testing N comes from the trial ledger (the honest path — counted
# at generation, cannot be understated); family registered by the prereg commit.
_LEDGER = TrialLedger(family="s13_reversal_sleeve")


def assert_no_gate(params: dict) -> None:
    """§1.5 invariant (CN-sleeve law, ported): membership must be a pure function
    of within-sector reversal fuel + hygiene. Any timing/confirmation/regime key
    in the config is a phase-0 violation."""
    forbidden = {"gate", "confirm", "turn", "macd", "stoch", "rsi", "quality",
                 "trend", "regime", "timing", "signal", "veto"}
    for k in params:
        kl = str(k).lower()
        if any(f in kl for f in forbidden):
            raise ValueError(f"assert_no_gate: forbidden config key {k!r} — "
                             "the CN sleeve died this way (§1.5)")


def _load_panel() -> pd.DataFrame:
    data = config.data_dir()
    deep = pd.read_parquet(data / "breadth" / "_closes_deep.parquet").sort_index()
    dl_p = data / "breadth" / "_closes_delisted.parquet"
    if dl_p.exists():
        dl = pd.read_parquet(dl_p).sort_index()
        new_cols = [c for c in dl.columns if c not in deep.columns]
        deep = pd.concat([deep, dl[new_cols]], axis=1).sort_index()
    return deep


def _load_membership() -> pd.DataFrame:
    m = pd.read_parquet(config.data_dir() / "breadth" / "sp500_pit_membership.parquet")
    m["start_date"] = pd.to_datetime(m["start_date"])
    m["end_date"] = pd.to_datetime(m["end_date"])
    return m


def _eligible(membership: pd.DataFrame, d: pd.Timestamp) -> set:
    mask = (membership["start_date"] <= d) & (
        membership["end_date"].isna() | (membership["end_date"] >= d))
    return set(membership.loc[mask, "ticker"])


def _spy_close() -> pd.Series:
    df = store.read("yahoo", "SPY")
    return df["close"].dropna().sort_index()


def _month_ends(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    s = pd.Series(index=index, data=index)
    return list(s.groupby([index.year, index.month]).max())


def _fill_after(close: pd.Series, t: pd.Timestamp):
    """First (date, price) strictly after t — the §1.2 next-bar fill."""
    fwd = close[close.index > t]
    if not len(fwd):
        return None, None
    return fwd.index[0], float(fwd.iloc[0])


def run_config(panel, membership, spy, sectors, formation: int) -> dict:
    params = {"species": "S13", "formation_days": formation, "quintile": "deepest",
              "weighting": "ew", "rebalance": "monthly",
              "universe": "pit_sp500_deep", "min_sector_names": MIN_SECTOR_NAMES,
              "fill": "next_close_after_rebalance", "screens": "hygiene_only"}
    assert_no_gate(params)

    idx = panel.index
    rebs = [t for t in _month_ends(idx) if t >= PIT_START]
    rebs = rebs[:-1]  # the last month-end has no forward month yet

    sleeve_rows = []          # per-rebalance: {date, n, ret, spy, excess, coverage, contribs}
    fires = []                # per-constituent: (ticker, entry_ts) for safety-net axes
    ic_rows = []              # within-sector IC per rebalance (K4)

    for i, t in enumerate(rebs):
        t_next = rebs[i + 1] if i + 1 < len(rebs) else None
        members = _eligible(membership, t)
        px_t = panel.loc[:t].iloc[-1]
        loc_t = idx.get_indexer([t])[0]
        loc_f = loc_t - formation
        if loc_f < 0:
            continue
        px_f = panel.iloc[loc_f]

        elig, form_ret, sect = [], {}, {}
        n_member_priced = 0
        for tk in members:
            if tk not in panel.columns:
                continue
            p0, p1 = px_f.get(tk), px_t.get(tk)
            if pd.isna(p0) or pd.isna(p1) or not p0:
                continue
            n_member_priced += 1
            sec = (sectors.get(tk) or (None, None))[1]
            if not sec:
                continue
            elig.append(tk)
            form_ret[tk] = float(p1 / p0 - 1.0)
            sect[tk] = sec

        coverage = n_member_priced / max(1, len(members))
        picks: list[str] = []
        for sec in set(sect.values()):
            names = [tk for tk in elig if sect[tk] == sec]
            if len(names) < MIN_SECTOR_NAMES:
                continue
            names.sort(key=lambda k: form_ret[k])
            q = max(1, int(round(len(names) / 5.0)))
            picks.extend(names[:q])

        # K4 within-sector IC: formation return vs forward month, sector-demeaned
        if t_next is not None and len(elig) >= 30:
            fwd_ret = {}
            for tk in elig:
                _, e0 = _fill_after(panel[tk].dropna(), t)
                _, e1 = _fill_after(panel[tk].dropna(), t_next)
                if e0 and e1:
                    fwd_ret[tk] = e1 / e0 - 1.0
            common = [tk for tk in fwd_ret if tk in form_ret]
            if len(common) >= 30:
                f = pd.Series({k: form_ret[k] for k in common})
                r = pd.Series({k: fwd_ret[k] for k in common})
                sec_s = pd.Series({k: sect[k] for k in common})
                f_dm = f - f.groupby(sec_s).transform("mean")
                r_dm = r - r.groupby(sec_s).transform("mean")
                ic_rows.append({"date": str(t.date()), "ic": rank_ic(f_dm, r_dm)})

        if not picks or t_next is None:
            continue

        rets, contribs = [], {}
        for tk in picks:
            ser = panel[tk].dropna()
            fill_ts, e0 = _fill_after(ser, t)
            if e0 is None:
                continue
            _, e1 = _fill_after(ser, t_next)
            if e1 is None:
                e1 = float(ser.iloc[-1])   # delisted mid-month: last print = honest loss
            r = e1 / e0 - 1.0
            rets.append(r)
            contribs[tk] = r
            fires.append((tk, fill_ts))
        if not rets:
            continue

        s_fill_ts, s0 = _fill_after(spy, t)
        _, s1 = _fill_after(spy, t_next)
        if s0 is None or s1 is None:
            continue
        spy_r = s1 / s0 - 1.0
        sleeve_r = float(np.mean(rets))
        sleeve_rows.append({"date": str(t.date()), "n": len(rets),
                            "ret": sleeve_r, "spy": spy_r,
                            "excess": sleeve_r - spy_r,
                            "coverage": round(coverage, 4),
                            "contribs": contribs})

    df = pd.DataFrame(sleeve_rows).set_index("date")
    df.index = pd.to_datetime(df.index)

    def _era(d0=None, d1=None):
        s = df["excess"]
        if d0 is not None:
            s = s[s.index >= d0]
        if d1 is not None:
            s = s[s.index < d1]
        if len(s) < 12:
            return {"n_months": len(s), "note": "too few months"}
        mean_m = float(s.mean())
        # HAC t via ic_summary's machinery (monthly periodicity)
        summ = ic_summary(s.tolist(), periods_per_year=12)
        sr_m = mean_m / (float(s.std(ddof=1)) or 1e-9)
        # kurt: pandas .kurt() is EXCESS kurtosis; the PSR formula wants raw → +3
        d = deflated_sharpe(sr_m, float(s.skew()), float(s.kurt()) + 3.0,
                            len(s), ledger=_LEDGER, family="s13_reversal_sleeve",
                            trading_year=12)
        boot = block_bootstrap_ci(s.values, block=3, B=2000, ann=12)
        return {"n_months": len(s), "mean_monthly_excess": round(mean_m, 5),
                "ann_excess": round(mean_m * 12, 4),
                "hac_t": summ.get("t_hac"), "sharpe_monthly": round(sr_m, 3),
                "dsr": (d or {}).get("dsr"), "dsr_n_trials": (d or {}).get("n_trials"),
                "dsr_verdict": (dsr_verdict((d or {}).get("dsr"))
                                if (d or {}).get("dsr") is not None else None),
                "boot_sharpe_ci": (boot or {}).get("sharpe_ci"),
                "boot_sharpe_gt0_prob": (boot or {}).get("sharpe_gt0_prob")}

    # K3 concentration: single-name share of cumulative PIT-era excess
    total_excess = df["excess"].sum()
    name_contrib: dict[str, float] = {}
    for _, row in df.iterrows():
        n = row["n"]
        for tk, r in row["contribs"].items():
            name_contrib[tk] = name_contrib.get(tk, 0.0) + (r - row["spy"]) / n
    top_name, top_share = None, None
    if name_contrib and total_excess:
        top_name = max(name_contrib, key=lambda k: abs(name_contrib[k]))
        top_share = name_contrib[top_name] / total_excess

    # K4 IC summary
    ics = [r["ic"] for r in ic_rows if r["ic"] is not None and np.isfinite(r["ic"])]
    ic_sum = ic_summary(ics, periods_per_year=12) if len(ics) >= 24 else {"note": "thin"}

    # Safety-net axes (both classes; promotion keys on clean8_21 — rotational)
    states8: dict[str, int] = {}
    states15: dict[str, int] = {}
    fire_sample = fires if len(fires) <= 20000 else fires[:: max(1, len(fires) // 20000)]
    for tk, fill_ts in fire_sample:
        ser = panel[tk].dropna()
        sig_loc = ser.index.get_indexer([fill_ts])[0] - 1
        if sig_loc < 0:
            continue
        sig_date = ser.index[sig_loc]
        for states, mult, hor in ((states8, grading.LIFTOFF_8, grading.LIFTOFF_HORIZON_21),
                                  (states15, grading.LIFTOFF_15, grading.LIFTOFF_HORIZON_126)):
            ts = grading.terminal_state(ser, sig_date, liftoff_mult=mult,
                                        liftoff_horizon=hor)
            st = ts.get("state")
            if st:
                states[str(st)] = states.get(str(st), 0) + 1

    def _pct(states: dict) -> dict:
        tot = sum(states.values()) or 1
        return {k: round(v / tot * 100, 2) for k, v in sorted(states.items())} | {"n_fires": tot}

    return {
        "formation_days": formation,
        "n_rebalances": len(df),
        "avg_names_per_month": round(float(df["n"].mean()), 1),
        "avg_member_price_coverage": round(float(df["coverage"].mean()), 4),
        "eras": {
            "pit_full_1996_2026": _era(),
            "modern_2002_2026_K1": _era(MODERN_START),
            "pre_flip_2002_2023": _era(MODERN_START, FLIP_START),
            "flip_2024_2026_K2": _era(FLIP_START),
        },
        "K3_concentration": {"top_name": top_name,
                             "top_share_of_cum_excess": (round(top_share, 4)
                                                         if top_share is not None else None)},
        "K4_within_sector_ic": ic_sum,
        "terminal_states_clean8_21_pct": _pct(states8),
        "terminal_states_clean15_126_pct": _pct(states15),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--formation", type=int, choices=(21, 63), default=None)
    args = ap.parse_args()

    panel = _load_panel()
    membership = _load_membership()
    spy = _spy_close()
    sectors = _names_sectors("broad")
    print(f"panel {panel.shape}, membership intervals {len(membership)}, "
          f"sectors mapped {len(sectors)}", flush=True)

    out = {}
    for f in ([args.formation] if args.formation else [21, 63]):
        print(f"=== formation {f}d ===", flush=True)
        out[f"formation_{f}"] = run_config(panel, membership, spy, sectors, f)
        print(json.dumps(out[f"formation_{f}"], indent=1, default=str), flush=True)

    dst = Path("research/species/_s13_phase0_out.json")
    dst.write_text(json.dumps(out, indent=1, default=str))
    print(f"wrote {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
