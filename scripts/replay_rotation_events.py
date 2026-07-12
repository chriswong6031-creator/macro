"""scripts/replay_rotation_events.py — RC-R8 point-in-time replay census (Rotation Command W2).

Steps engine.rotation_events.step_pairs VERBATIM (the production lifecycle) over every
session since 2014-11, each evaluation on the trailing WINDOW bars of every series — the
exact construction frozen in research/ROTATION_COMMAND_S1_S2_PREREG.md §2.1. Produces:

  data/rotation_events/replay_census.parquet   one row per EVENT (created, closed, receipts)
  data/rotation_events/replay_episodes.parquet one row per EPISODE (prereg §2.4 clustering)
  data/rotation_events/replay_forward.parquet  forward outcomes (T+1-close basis, §2.3)
  data/rotation_events/episode_ruler.json      RC-R10 honest late-ruler (descriptive)
  data/rotation_events/s1_s2_results.json      the pre-registered S1/S2 statistics

Survivorship honesty (§2.2): legs are AS CONSTITUTED TODAY; every statistic is era-split
(modern ≥ 2023-05-01 vs reconstructed). Run manually (one-off backfill + prereg evaluation):

    python -m scripts.replay_rotation_events            # full run
    python -m scripts.replay_rotation_events --bench 40 # timing probe only
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import basket_index, rotation_events as re_, sector_legs  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("replay_rotation_events")

WINDOW = 420                 # trailing bars per evaluation (≥ all signature lookbacks)
WARMUP_START = "2014-11-01"  # stepping starts here; events COUNTED from COUNT_START
COUNT_START = "2015-01-01"
SEV_RANK = {"major": 0, "notable": 1, "standard": 2}
MODERN_ERA = "2023-05-01"    # basket seed date (prereg §2.2)
UNIVERSE_END = "2026-04-30"  # prereg §2.5 (June-2026 case zero excluded)


def _win(s: pd.Series, cut) -> pd.Series:
    s2 = s.loc[:cut]
    return s2.iloc[-WINDOW:] if len(s2) > WINDOW else s2


def _truncate(sectors: dict, cut) -> dict:
    return {k: {"cfg": s["cfg"], "etf_close": _win(s["etf_close"], cut),
                "legs": {lk: _win(ls, cut) for lk, ls in s["legs"].items()},
                "leg_meta": {}}
            for k, s in sectors.items()}


def run_replay(sectors: dict, limit: int | None = None) -> tuple[pd.DataFrame, dict]:
    """Daily lifecycle replay. Returns (census_df, timing)."""
    cal = sorted({d for s in sectors.values() for d in s["etf_close"].dropna().index})
    cal = [d for d in cal if str(d.date()) >= WARMUP_START]
    if limit:
        cal = cal[:limit]
    state: dict = {}
    rows: dict[tuple, dict] = {}          # (pair_id, started) -> event row
    t0 = time.time()
    for i, cut in enumerate(cal):
        state, act, created, closed = re_.step_pairs(_truncate(sectors, cut), state)
        for pid in created:
            ev = next((e for e in act if e["id"] == pid), None)
            if ev is None:
                continue
            rows[(pid, ev["started"])] = {
                "pair_id": pid, "sector": ev["sector"],
                "from_leg": ev["from_leg"]["key"], "to_leg": ev["to_leg"]["key"],
                "severity": ev["severity"], "started": ev["started"],
                "created_asof": ev["asof"],
                "blowoff_dd": ev["receipts"]["blowoff"]["drawdown_pct"],
                "turn_off_low": ev["receipts"]["turn"]["off_low_pct"],
                "closed_asof": None, "close_reason": None, "day_n_final": None,
            }
        for c in closed:
            key = (c["pair_id"], c["started"])
            if key in rows:
                rows[key].update(closed_asof=c["closed_asof"],
                                 close_reason=c["reason"], day_n_final=c["day_n"])
        if i % 250 == 0:
            log.info("replay %s (%d/%d) — %d events, %.0fs",
                     cut.date(), i, len(cal), len(rows), time.time() - t0)
    census = pd.DataFrame(list(rows.values()))
    if not census.empty:
        census = census[census["started"] >= COUNT_START].reset_index(drop=True)
    return census, {"sessions": len(cal), "secs": round(time.time() - t0, 1)}


def cluster_episodes(census: pd.DataFrame, sectors: dict) -> pd.DataFrame:
    """Prereg §2.4: per sector, transitively overlapping [started, end] intervals → one
    EPISODE; representative = highest severity, then earliest started, then pair id."""
    if census.empty:
        return pd.DataFrame()
    ttl = re_.PARAMS["ttl_sessions"]
    out = []
    for skey, grp in census.groupby("sector"):
        etf_cal = [str(d.date()) for d in sectors[skey]["etf_close"].dropna().index]
        pos = {d: i for i, d in enumerate(etf_cal)}
        g = grp.copy()
        g["s_pos"] = g["started"].map(pos)
        g["e_pos"] = g.apply(
            lambda r: pos.get(r["closed_asof"], (pos.get(r["started"], 0) + ttl))
            if r["closed_asof"] else pos.get(r["started"], 0) + ttl, axis=1)
        g = g.dropna(subset=["s_pos"]).sort_values("s_pos")
        cluster, end = [], -1
        clusters = []
        for _, r in g.iterrows():
            if cluster and r["s_pos"] > end:
                clusters.append(cluster)
                cluster, end = [], -1
            cluster.append(r)
            end = max(end, r["e_pos"])
        if cluster:
            clusters.append(cluster)
        for cl in clusters:
            rep = sorted(cl, key=lambda r: (SEV_RANK.get(r["severity"], 3),
                                            r["started"], r["pair_id"]))[0]
            out.append({**{k: rep[k] for k in ("pair_id", "sector", "from_leg", "to_leg",
                                               "severity", "started", "created_asof",
                                               "closed_asof", "close_reason",
                                               "blowoff_dd", "turn_off_low")},
                        "n_events": len(cl),
                        "pairs": ";".join(sorted({r["pair_id"] for r in cl})),
                        "era": "modern" if rep["started"] >= MODERN_ERA else "reconstructed"})
    return pd.DataFrame(out).sort_values("started").reset_index(drop=True)


# --------------------------------------------------------------- forward outcomes ----

def _fwd(s: pd.Series, entry_date: str, h: int, entry_offset: int = 1) -> float | None:
    """Prereg §2.3: from the (entry_offset)-th close AFTER entry_date to +h more closes."""
    s = s.dropna()
    dates = [str(d.date()) for d in s.index]
    try:
        i = dates.index(entry_date)
    except ValueError:
        return None
    a, b = i + entry_offset, i + entry_offset + h
    if b >= len(s):
        return None
    base = float(s.iloc[a])
    return float(s.iloc[b]) / base - 1.0 if base else None


def _maxdd(s: pd.Series, entry_date: str, h: int, entry_offset: int = 1) -> float | None:
    s = s.dropna()
    dates = [str(d.date()) for d in s.index]
    try:
        i = dates.index(entry_date)
    except ValueError:
        return None
    a = i + entry_offset
    if a + h >= len(s):
        return None
    base = float(s.iloc[a])
    seg = s.iloc[a + 1:a + h + 1]
    return float(seg.min()) / base - 1.0 if base else None


def forward_outcomes(episodes: pd.DataFrame, sectors: dict) -> pd.DataFrame:
    spy_df = basket_index._load_member_ohlcv("SPY")
    spy = spy_df["close"].dropna()
    rows = []
    for _, ep in episodes.iterrows():
        sec = sectors[ep["sector"]]
        leg = sec["legs"].get(ep["to_leg"])
        etf = sec["etf_close"]
        if leg is None:
            continue
        d = ep["created_asof"]
        row = dict(ep)
        for h in (10, 20, 60):
            f = _fwd(leg, d, h)
            row[f"fwd{h}"] = f
            fe = _fwd(etf, d, h)
            fs = _fwd(spy, d, h)
            row[f"x_sector_{h}"] = (f - fe) if (f is not None and fe is not None) else None
            row[f"x_spy_{h}"] = (f - fs) if (f is not None and fs is not None) else None
        row["maxdd20"] = _maxdd(leg, d, 20)
        # S2 delayed-entry counterfactual (prereg §2.6.4): entry at T+11 close
        row["fwd20_delayed"] = _fwd(leg, d, 20, entry_offset=11)
        row["maxdd20_delayed"] = _maxdd(leg, d, 20, entry_offset=11)
        # RC-R10 ruler ingredients: to-leg max run from the STARTED close within 30 sessions
        leg_d = leg.dropna()
        dates = [str(x.date()) for x in leg_d.index]
        if ep["started"] in dates:
            i = dates.index(ep["started"])
            seg = leg_d.iloc[i:i + 31]
            if len(seg) > 5:
                base = float(seg.iloc[0])
                row["run_peak_pct"] = float(seg.max()) / base - 1.0
                row["run_peak_sessions"] = int(np.argmax(seg.to_numpy()))
        rows.append(row)
    return pd.DataFrame(rows)


# ------------------------------------------------------------- prereg evaluation ----

def _boot_p(vals: np.ndarray, n_boot: int = 10_000, seed: int = 20260712) -> float:
    """One-sided bootstrap: P(median ≤ 0) over episode resamples (prereg §3)."""
    rng = np.random.default_rng(seed)
    meds = np.median(rng.choice(vals, size=(n_boot, len(vals)), replace=True), axis=1)
    return float((meds <= 0).mean())


def _sign_p(vals: np.ndarray) -> float:
    """One-sided exact sign test (P(#positive ≥ observed | p=.5), zeros dropped)."""
    from math import comb
    v = vals[vals != 0]
    n, k = len(v), int((v > 0).sum())
    if n == 0:
        return 1.0
    return float(sum(comb(n, j) for j in range(k, n + 1)) / 2 ** n)


def evaluate_prereg(fw: pd.DataFrame) -> dict:
    """The frozen S1/S2 rulers (research/ROTATION_COMMAND_S1_S2_PREREG.md §3-§4)."""
    uni = fw[(fw["started"] <= UNIVERSE_END)].copy()

    def s1_stats(df: pd.DataFrame) -> dict:
        x = df["x_sector_20"].dropna().to_numpy()
        if not len(x):
            return {"n": 0}
        return {"n": int(len(x)), "median_pp": round(float(np.median(x)) * 100, 2),
                "mean_pp": round(float(np.mean(x)) * 100, 2),
                "wr": round(float((x > 0).mean()), 3),
                "false_fire": round(float((df["fwd20"].dropna() < -0.05).mean()), 3),
                "p_boot": _boot_p(x) if len(x) >= 5 else None}

    s1_all, s1_mod = s1_stats(uni), s1_stats(uni[uni["era"] == "modern"])
    s2u = uni.dropna(subset=["fwd20", "fwd20_delayed"]).copy()
    d = (s2u["fwd20"] - s2u["fwd20_delayed"]).to_numpy()
    dd_ok = None
    if len(s2u):
        dd_diff = (s2u["maxdd20"] - s2u["maxdd20_delayed"]).dropna()
        dd_ok = bool(np.median(dd_diff) >= -0.02) if len(dd_diff) else None
    s2 = {"n": int(len(d)),
          "median_diff_pp": round(float(np.median(d)) * 100, 2) if len(d) else None,
          "wr": round(float((d > 0).mean()), 3) if len(d) else None,
          "p_sign": _sign_p(d) if len(d) else None,
          "p_boot": _boot_p(d) if len(d) >= 5 else None,
          "maxdd_clause_ok": dd_ok}

    # BH-FDR across the 2-hypothesis family (q=0.10)
    p1 = s1_all.get("p_boot")
    p2 = s2.get("p_sign")
    adj = {}
    if p1 is not None and p2 is not None:
        pairs = sorted([("s1", p1), ("s2", p2)], key=lambda t: t[1])
        a0 = min(1.0, pairs[0][1] * 2)
        a1 = min(1.0, pairs[1][1])
        adj = {pairs[0][0]: round(min(a0, a1), 4), pairs[1][0]: round(a1, 4)}

    def s1_verdict() -> str:
        if s1_all["n"] < 20:
            return "ACCRUE"
        if s1_all["median_pp"] <= -1.0:
            return "KILL"
        modern_ok = (s1_mod.get("n", 0) >= 5 and (s1_mod.get("median_pp") or -9) >= 0)
        go = (s1_all["median_pp"] >= 1.0 and s1_all["wr"] >= 0.55
              and (adj.get("s1", 1.0) < 0.10) and s1_all["false_fire"] <= 0.25)
        if go and s1_mod.get("n", 0) < 5:
            return "ACCRUE"          # modern clause can't be checked yet (prereg §4)
        return "GO" if (go and modern_ok) else "NO-GO"

    def s2_verdict() -> str:
        if s2["n"] < 20:
            return "ACCRUE"
        if (s2["median_diff_pp"] or 0) <= -1.0:
            return "KILL"
        go = ((s2["median_diff_pp"] or -9) >= 1.0 and (adj.get("s2", 1.0) < 0.10)
              and bool(s2["maxdd_clause_ok"]))
        return "GO" if go else "NO-GO"

    return {"prereg": "research/ROTATION_COMMAND_S1_S2_PREREG.md",
            "universe": {"start": COUNT_START, "end": UNIVERSE_END,
                         "june_2026_excluded": True},
            "s1": {"all": s1_all, "modern": s1_mod, "p_adj": adj.get("s1"),
                   "verdict": s1_verdict()},
            "s2": {**s2, "p_adj": adj.get("s2"), "verdict": s2_verdict()}}


def build_ruler(fw: pd.DataFrame) -> dict:
    """RC-R10 descriptive episode ruler (all episodes incl. post-2026-05, watermarked)."""
    def dist(df):
        r = df["run_peak_pct"].dropna()
        s = df["run_peak_sessions"].dropna()
        if len(r) < 5:
            return {"n": int(len(r))}
        return {"n": int(len(r)),
                "run_pct": {"p25": round(float(r.quantile(.25)) * 100, 1),
                            "median": round(float(r.median()) * 100, 1),
                            "p75": round(float(r.quantile(.75)) * 100, 1)},
                "sessions_to_peak": {"median": int(s.median()),
                                     "p75": int(s.quantile(.75))}}
    return {"schema": "episode_ruler.v1",
            "watermark": "leg membership as of 2026 — reconstructed era is approximation; "
                         "descriptive only, never a gate (RC-R10)",
            "all": dist(fw), "modern": dist(fw[fw["era"] == "modern"]),
            "reconstructed": dist(fw[fw["era"] == "reconstructed"])}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", type=int, default=0, help="timing probe: N sessions only")
    args = ap.parse_args(argv)

    sectors = sector_legs.sector_closes()
    log.info("legs resolved: %d sectors", len(sectors))
    census, timing = run_replay(sectors, limit=args.bench or None)
    log.info("replay done: %s — %d events", timing, len(census))
    if args.bench:
        return 0

    d = config.data_dir() / "rotation_events"
    d.mkdir(parents=True, exist_ok=True)
    census.to_parquet(d / "replay_census.parquet", index=False)
    episodes = cluster_episodes(census, sectors)
    episodes.to_parquet(d / "replay_episodes.parquet", index=False)
    log.info("episodes: %d (from %d events)", len(episodes), len(census))

    fw = forward_outcomes(episodes, sectors)
    fw.to_parquet(d / "replay_forward.parquet", index=False)

    ruler = build_ruler(fw)
    (d / "episode_ruler.json").write_text(json.dumps(ruler, indent=1))
    results = evaluate_prereg(fw)
    (d / "s1_s2_results.json").write_text(json.dumps(results, indent=1))
    log.info("S1: %s | S2: %s", results["s1"]["verdict"], results["s2"]["verdict"])
    print(json.dumps(results, indent=1))
    print(json.dumps(ruler, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
