"""Phase-B gate re-run harness: re-evaluate three pre-registered options gates
against the ThetaData historical store with mandatory era splits.

Gates (from OPTIONS_ALPHA_MASTERPLAN §4):
  S-DOI  — ΔOI 5d persistence rank-IC vs forward 5d/10d returns
  S-CWIV — Cremers-Weinbaum call−put IV spread (needs per-contract IV)
  S-XZZ  — Xing-Zhang-Zhao OTM-put skew (needs per-contract IV)

Era splits (LIVE_ORDER_FLOW_BRAINSTORM §8.4):
  2012-15 / 2016-19 / 2020-22 / 2023→

Gate criteria are UNCHANGED from the §4 registry (HAC t>2, breadth floors).
Thresholds are hardcoded from the registry with a comment citing it — no
result-dependent choices.

Usage:
    python -m scripts.rerun_options_gates_thetadata           # full run
    python -m scripts.rerun_options_gates_thetadata --smoke   # mechanics only
    python -m scripts.rerun_options_gates_thetadata --store /path/to/store

Outputs (full run only — never written in --smoke mode):
    data/options_flow/gate_doi_thetadata.json
    data/options_ivspread/gate_thetadata.json
    data/options_skew/gate_thetadata.json
    reports/options-gates-thetadata-rerun.md
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Project root on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import validation as V  # noqa: E402
from engine.thetadata_store import (  # noqa: E402
    doi_series, iv_coverage, make_chain_provider, universe,
)

log = logging.getLogger("rerun_options_gates")

# --------------------------------------------------------------------------- #
# Constants — unchanged from OPTIONS_ALPHA_MASTERPLAN §4 registry              #
# --------------------------------------------------------------------------- #

# S-DOI: cross-sectional rank-IC gate (OPTIONS_ALPHA_MASTERPLAN §4)
_DOI_HORIZONS = [5, 10]          # forward return windows (trading days)
_DOI_MIN_DATES = 60              # §4: "HAC t>2 @60 dates"
_DOI_MIN_NAMES = 5               # HARNESS CHOICE (not a §4 threshold): §4 registers only
                                 # the 60-date floor; this floor is set by the harness to
                                 # exclude single-name dates during thin-backfill runs.
_DOI_T_BAR = 2.0                 # §4: HAC t > 2

# S-CWIV / S-XZZ: same gate shape as existing validators
# (LIVE_ORDER_FLOW_BRAINSTORM §4 + OPTIONS_ALPHA_MASTERPLAN §4)
_IV_MIN_DATES = 120              # §4: "120 dates × 15 names"
_IV_MIN_NAMES = 15               # §4 cross-sectional breadth floor
_IV_T_BAR = 2.0                  # §4: HAC t > 2

# Era boundaries (LIVE_ORDER_FLOW_BRAINSTORM §8.4)
_ERAS = [
    ("2012-15", "2012-01-01", "2015-12-31"),
    ("2016-19", "2016-01-01", "2019-12-31"),
    ("2020-22", "2020-01-01", "2022-12-31"),
    ("2023+",   "2023-01-01", "2099-12-31"),
]


def _era(date_str: str) -> str:
    for label, lo, hi in _ERAS:
        if lo <= date_str <= hi:
            return label
    return "unknown"


def _era_filter(dates: list[str], lo: str, hi: str) -> list[str]:
    return [d for d in dates if lo <= d <= hi]


# --------------------------------------------------------------------------- #
# Forward return source (TR closes from equity_factors)                        #
# --------------------------------------------------------------------------- #
# Using equity_factors._closes("broad") which provides dividend-adjusted
# total-return closes from the breadth caches. Choice documented here:
#
#  DESIGN NOTE — Total-Return closes for cross-sectional rank-IC:
#    TR closes are correct for cross-sectional RANK-IC (Spearman correlation).
#    The rank-IC only cares about the ORDERING of returns across names on the
#    same date; dividend adjustments shift all names in the same direction and
#    do not distort cross-sectional rankings meaningfully for 5-10d windows.
#    IMPORTANT: these TR closes must NEVER be compared to strike levels (strikes
#    are nominal prices, not TR-adjusted); they are purely a forward-return source.

def _get_tr_closes() -> pd.DataFrame:
    """Dividend-adjusted TR closes from breadth caches. Returns empty frame gracefully."""
    try:
        from engine import equity_factors  # noqa: PLC0415
        df = equity_factors._closes("broad")
        if df is None or df.empty:
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        return df
    except Exception as e:  # noqa: BLE001
        log.warning("TR closes unavailable (%s) — S-DOI will run without forward-return validation", e)
        return pd.DataFrame()


# --------------------------------------------------------------------------- #
# S-DOI: ΔOI 5-day persistence rank-IC                                         #
# --------------------------------------------------------------------------- #

def _doi_ic_panel(roots: list[str], tr_closes: pd.DataFrame,
                  window: int = 5, store: str | None = None) -> pd.DataFrame:
    """Build (date, root, doi_z, fwd_ret_5, fwd_ret_10) panel.

    doi_z is the ΔOI z-score computed with the oi[t-1] law (see doi_series).
    Forward returns are TR-close based: fwd_ret_h = close[t+h]/close[t] - 1.
    """
    rows = []
    for root in roots:
        s = doi_series(root, put_call="both", window=window, store=store)
        if s.empty or "doi_z" not in s.columns:
            continue
        s = s.set_index("date")["doi_z"].dropna()
        if s.empty:
            continue
        for d, z in s.items():
            if not np.isfinite(z):
                continue
            rows.append({"date": str(d), "root": root, "doi_z": float(z)})

    if not rows:
        return pd.DataFrame(columns=["date", "root", "doi_z", "fwd_ret_5", "fwd_ret_10"])

    panel = pd.DataFrame(rows)

    # Attach forward returns if TR closes are available
    if not tr_closes.empty:
        for h in [5, 10]:
            fwd_map: dict[str, dict[str, float]] = {}
            for sym in panel["root"].unique():
                if sym not in tr_closes.columns:
                    continue
                s = tr_closes[sym].dropna()
                dates = list(s.index)
                for i, d in enumerate(dates):
                    if i + h < len(dates):
                        ret = s.iloc[i + h] / s.iloc[i] - 1.0
                        if np.isfinite(ret):
                            fwd_map.setdefault(d, {})[sym] = float(ret)
            # flatten
            rows_fwd = [(d, sym, v) for d, sv in fwd_map.items() for sym, v in sv.items()]
            if rows_fwd:
                fwd_df = pd.DataFrame(rows_fwd, columns=["date", "root", f"fwd_ret_{h}"])
                panel = panel.merge(fwd_df, on=["date", "root"], how="left")
            else:
                panel[f"fwd_ret_{h}"] = np.nan
    else:
        panel["fwd_ret_5"] = np.nan
        panel["fwd_ret_10"] = np.nan

    return panel


def _doi_era_stats(panel: pd.DataFrame, h: int, min_names: int,
                   lo: str, hi: str) -> dict:
    """Per-era cross-sectional rank-IC stats for S-DOI at horizon h."""
    sub = panel[(panel["date"] >= lo) & (panel["date"] <= hi)].copy()
    if sub.empty or f"fwd_ret_{h}" not in sub.columns:
        return {"n_dates": 0, "n_names_avg": 0, "excluded_dates": 0}

    sub = sub.dropna(subset=["doi_z", f"fwd_ret_{h}"])
    if sub.empty:
        return {"n_dates": 0, "n_names_avg": 0, "excluded_dates": 0}

    ics = []
    excluded = 0
    dates = sorted(sub["date"].unique())
    for d in dates:
        day = sub[sub["date"] == d]
        if len(day) < min_names:
            excluded += 1
            continue
        ic = V.rank_ic(day["doi_z"].values, day[f"fwd_ret_{h}"].values)
        if np.isfinite(ic):
            ics.append(ic)

    if not ics:
        return {"n_dates": 0, "n_names_avg": 0, "excluded_dates": excluded}

    avg_n = float(sub.groupby("date")["root"].count().mean())
    summ = V.ic_summary(np.array(ics), periods_per_year=max(1, 252 // h))
    return {
        "n_dates": len(ics),
        "n_names_avg": round(avg_n, 1),
        "excluded_dates": excluded,
        "mean_ic": summ.get("mean_ic"),
        "ic_vol": summ.get("ic_vol"),
        "hac_t": summ.get("t_hac"),   # ic_summary returns t_hac
        "hit": summ.get("hit"),
    }


def run_s_doi(roots: list[str], tr_closes: pd.DataFrame,
              store: str | None = None, smoke: bool = False) -> dict:
    """Run S-DOI gate. Returns gate dict (scored:false always — machine only)."""
    log.info("S-DOI: building ΔOI panel for %d roots", len(roots))
    panel = _doi_ic_panel(roots, tr_closes, window=5, store=store)
    n_dates_total = panel["date"].nunique() if not panel.empty else 0
    n_names_total = panel["root"].nunique() if not panel.empty else 0

    log.info("S-DOI panel: %d dates × %d roots (%d rows)",
             n_dates_total, n_names_total, len(panel))

    has_fwd = not panel.empty and panel["fwd_ret_5"].notna().any()
    if not has_fwd:
        log.warning("S-DOI: no forward returns available (TR closes absent or no root overlap) "
                    "— era stats will show n_dates=0")

    era_stats: dict[str, dict] = {}
    for era_label, lo, hi in _ERAS:
        era_stats[era_label] = {
            h: _doi_era_stats(panel, h, _DOI_MIN_NAMES, lo, hi)
            for h in _DOI_HORIZONS
        }

    # Pooled stats
    pooled: dict[int, dict] = {}
    for h in _DOI_HORIZONS:
        pooled[h] = _doi_era_stats(panel, h, _DOI_MIN_NAMES, "2012-01-01", "2099-12-31")

    # Gate verdict (scored always False — machine only; verdicts after backfill completes)
    gate = {
        "schema": "options_doi.gate.v1",
        "signal": "S-DOI",
        "store": "thetadata_eod",
        "reconstructed": True,
        "scored": False,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "n_dates_total": int(n_dates_total),
        "n_names_total": int(n_names_total),
        "has_forward_returns": bool(has_fwd),
        "era_stats": {era: {str(h): v for h, v in hs.items()}
                      for era, hs in era_stats.items()},
        "pooled": {str(h): pooled[h] for h in _DOI_HORIZONS},
        "gate_criteria": {
            "source": "OPTIONS_ALPHA_MASTERPLAN §4 — unchanged",
            "min_dates": _DOI_MIN_DATES,
            "min_names_per_date": _DOI_MIN_NAMES,
            "min_names_note": "harness choice; §4 registers only the 60-date floor",
            "hac_t_bar": _DOI_T_BAR,
            "horizons": _DOI_HORIZONS,
        },
        "iv_coverage": None,  # S-DOI does not require IV
        "note": (
            "[SMOKE] " if smoke else ""
        ) + (
            "S-DOI ΔOI persistence: scored:false — machine only. "
            "Verdicts after backfill completes. "
            "OI timing law applied: doi_series() uses oi[t-1] (shift(1)) per "
            "LIVE_ORDER_FLOW_BRAINSTORM §8 ¶1. "
            "Forward returns: TR closes from equity_factors._closes('broad') "
            "— dividend-adjusted, cross-sectional rank-IC use only, "
            "MUST NOT be compared to strike levels. "
            "BS-inversion fallback for pre-greeks era: REGISTERED FUTURE EXTENSION, not built."
        ),
    }
    return gate


# --------------------------------------------------------------------------- #
# S-CWIV and S-XZZ: IV-dependent cross-sectional gates                         #
# --------------------------------------------------------------------------- #

def _iv_panel_for_gate(
    gate: str,  # "cwiv" or "xzz"
    roots: list[str],
    iv_cov: dict[str, dict],
    store: str | None = None,
) -> tuple[pd.DataFrame, str, str]:
    """Build (date, underlying, signal, spot) panel using thetadata chain provider.

    Returns (panel, first_iv_date, last_iv_date).

    The chain provider maps thetadata store frames to the polygon_gex chain schema
    that engine.options_skew / engine.options_ivspread expect.
    """
    from engine import options_skew as XZZ   # noqa: PLC0415
    from engine import options_ivspread as CW  # noqa: PLC0415

    provider = make_chain_provider(store=store, require_iv=True)

    # Determine IV-covered date range across all roots
    if not iv_cov:
        log.warning("%s: no greeks IV coverage found in store", gate.upper())
        return pd.DataFrame(), "", ""

    all_first = [v["first"] for v in iv_cov.values()]
    all_last = [v["last"] for v in iv_cov.values()]
    global_first = min(all_first)
    global_last = max(all_last)

    log.info("%s: IV coverage window %s → %s across %d roots",
             gate.upper(), global_first, global_last, len(iv_cov))

    # Enumerate all unique dates in the store for roots that have greeks
    iv_roots = [r for r in roots if r in iv_cov]
    all_dates: set[str] = set()
    base_path = None
    try:
        from engine.thetadata_store import store_root  # noqa: PLC0415
        base_path = store_root(store) / "greeks"
    except Exception:  # noqa: BLE001
        pass

    if base_path is not None and base_path.exists():
        for r in iv_roots:
            rdir = base_path / r
            if rdir.exists():
                for f in sorted(rdir.glob("*.parquet")):
                    try:
                        df = pd.read_parquet(f, columns=["date"])
                        dates = pd.to_datetime(df["date"]).dt.date.astype(str).unique()
                        all_dates.update(dates)
                    except Exception:  # noqa: BLE001
                        pass

    if not all_dates:
        log.warning("%s: could not enumerate dates from greeks store", gate.upper())
        return pd.DataFrame(), global_first, global_last

    sorted_dates = sorted(all_dates)
    rows = []

    compute_fn = XZZ.skew_map if gate == "xzz" else CW.ivspread_map
    signal_key = "skew" if gate == "xzz" else "ivspread"

    for d in sorted_dates:
        day_roots = [r for r in iv_roots
                     if iv_cov.get(r, {}).get("first", "9999") <= d <=
                        iv_cov.get(r, {}).get("last", "0000")]
        if not day_roots:
            continue
        day_map: dict[str, dict] = {}
        for r in day_roots:
            chain_frame = provider(d, r)
            if chain_frame is None or chain_frame.empty:
                continue
            if gate == "xzz":
                m = compute_fn(chain_frame)  # type: ignore[call-arg]
            else:
                m = compute_fn(chain_frame, relative=False)  # type: ignore[call-arg]
            day_map.update(m)

        if not day_map:
            continue
        for sym, m in day_map.items():
            sv = m.get(signal_key)
            spot = m.get("spot")
            if sv is not None and np.isfinite(sv) and spot is not None:
                rows.append({"date": d, "underlying": sym, signal_key: sv, "spot": float(spot)})

    panel = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["date", "underlying", signal_key, "spot"])
    return panel, global_first, global_last


def _iv_fwd_ic(panel: pd.DataFrame, signal_col: str, lo: str, hi: str,
               min_names: int) -> dict:
    """Per-era rank-IC stats for IV-based cross-sectional gates (CWIV or XZZ)."""
    sub = panel[(panel["date"] >= lo) & (panel["date"] <= hi)].copy()
    if sub.empty:
        return {"n_dates": 0, "n_names_avg": 0, "excluded_dates": 0}

    # Build spot matrix for forward returns
    spot = sub.pivot_table(index="date", columns="underlying", values="spot")
    sig = sub.pivot_table(index="date", columns="underlying", values=signal_col)
    spot = spot.sort_index()
    sig = sig.sort_index()
    dates = list(spot.index)
    spy = spot["SPY"] if "SPY" in spot.columns else None

    ics, excluded = [], 0
    # Use a default horizon of 5 days (matches the validator scripts)
    for h in [5]:
        for i, d0 in enumerate(dates):
            if i + h >= len(dates):
                break
            d1 = dates[i + h]
            fwd = spot.loc[d1] / spot.loc[d0] - 1.0
            if spy is not None and float(spy.loc[d1]) > 0 and float(spy.loc[d0]) > 0:
                fwd = fwd - (float(spy.loc[d1]) / float(spy.loc[d0]) - 1.0)
            sg = sig.loc[d0]
            names = [c for c in sg.index if c != "SPY"
                     and np.isfinite(sg.get(c, float("nan")))
                     and np.isfinite(fwd.get(c, float("nan")))]
            if len(names) < min_names:
                excluded += 1
                continue
            ic = V.rank_ic(sg[names].values, fwd[names].values)
            if np.isfinite(ic):
                ics.append(ic)

    if not ics:
        return {"n_dates": 0, "n_names_avg": 0, "excluded_dates": excluded}

    avg_n = float(sub.groupby("date")["underlying"].count().mean())
    summ = V.ic_summary(np.array(ics), periods_per_year=max(1, 252 // 5))
    return {
        "n_dates": len(ics),
        "n_names_avg": round(avg_n, 1),
        "excluded_dates": excluded,
        "mean_ic": summ.get("mean_ic"),
        "ic_vol": summ.get("ic_vol"),
        "hac_t": summ.get("t_hac"),
        "hit": summ.get("hit"),
    }


def run_s_cwiv_or_xzz(
    gate: str,
    roots: list[str],
    iv_cov: dict[str, dict],
    store: str | None = None,
    smoke: bool = False,
) -> dict:
    """Run S-CWIV or S-XZZ gate. Returns gate dict (scored:false always)."""
    assert gate in ("cwiv", "xzz")
    signal_col = "ivspread" if gate == "cwiv" else "skew"
    gate_id = "S-CWIV" if gate == "cwiv" else "S-XZZ"
    schema = f"options_{gate}.gate.v1"

    log.info("%s: building IV panel...", gate_id)
    panel, first_iv, last_iv = _iv_panel_for_gate(gate, roots, iv_cov, store)

    n_dates = panel["date"].nunique() if not panel.empty else 0
    n_names = panel["underlying"].nunique() if not panel.empty else 0
    log.info("%s panel: %d dates × %d names (%d rows)", gate_id, n_dates, n_names, len(panel))

    era_stats: dict[str, dict] = {}
    for era_label, lo, hi in _ERAS:
        era_stats[era_label] = _iv_fwd_ic(panel, signal_col, lo, hi, _IV_MIN_NAMES)

    pooled = _iv_fwd_ic(panel, signal_col, "2012-01-01", "2099-12-31", _IV_MIN_NAMES)

    gate_dict = {
        "schema": schema,
        "signal": gate_id,
        "store": "thetadata_eod",
        "reconstructed": True,
        "scored": False,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "n_dates": int(n_dates),
        "n_names": int(n_names),
        "iv_coverage": {
            "first": first_iv,
            "last": last_iv,
            "n_roots_with_iv": len(iv_cov),
            "per_root": iv_cov,
        },
        "era_stats": era_stats,
        "pooled": pooled,
        "gate_criteria": {
            "source": "OPTIONS_ALPHA_MASTERPLAN §4 — unchanged",
            "min_dates": _IV_MIN_DATES,
            "min_names_per_date": _IV_MIN_NAMES,
            "hac_t_bar": _IV_T_BAR,
        },
        "note": (
            "[SMOKE] " if smoke else ""
        ) + (
            f"{gate_id} cross-sectional gate: scored:false — machine only. "
            "Verdicts after backfill completes. "
            "Requires per-contract IV from greeks tier — runs only on "
            "greeks-IV-covered date range (printed above). "
            "BS-inversion fallback for pre-greeks era: REGISTERED FUTURE EXTENSION, not built. "
            "OI timing law (oi[t-1]) applied inside chain provider; "
            "OI-weighted CW metric computed in options_ivspread engine (unchanged). "
        ),
    }
    return gate_dict


# --------------------------------------------------------------------------- #
# Refactored validator panel-providers (injected)                              #
# --------------------------------------------------------------------------- #
# The existing validate_options_skew.py / validate_options_ivspread.py
# build_panel() functions are refactored (in those scripts) to accept an
# optional `chain_provider` argument. When None (default), they use the
# current polygon_gex accrual store as before (byte-compatible). When
# --store thetadata is passed, they switch to the thetadata chain provider
# via this harness.


# --------------------------------------------------------------------------- #
# Thin-universe handling and smoke mode                                         #
# --------------------------------------------------------------------------- #

def _check_thin_universe(roots: list[str], min_names: int) -> None:
    """Warn prominently if universe is thinner than the gate breadth floor."""
    if len(roots) < min_names:
        log.warning(
            "THIN UNIVERSE: store has %d roots but gate breadth floor is %d names/date. "
            "Dates with fewer than %d names are excluded and tallied in era_stats.excluded_dates. "
            "This is expected during backfill — full verdicts require a broad cross-section.",
            len(roots), min_names, min_names,
        )


# --------------------------------------------------------------------------- #
# Output writers                                                                #
# --------------------------------------------------------------------------- #

def _write_gate(path: Path, gate: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(gate, indent=2, default=str))
    log.info("wrote %s (scored=%s)", path, gate.get("scored"))


def _write_report(gates: dict[str, dict], store_path: str,
                  iv_cov: dict, smoke: bool) -> Path:
    """Write markdown report with era tables per gate + decay-commentary stub."""
    try:
        from lib import config  # noqa: PLC0415
        rdir = Path(__file__).resolve().parent.parent / "reports"
    except Exception:  # noqa: BLE001
        rdir = Path("reports")
    rdir.mkdir(parents=True, exist_ok=True)
    p = rdir / "options-gates-thetadata-rerun.md"

    lines = [
        "# Options Gates ThetaData Re-run Report",
        "",
        f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        f"_Store: `{store_path}`_",
        "",
    ]

    if smoke:
        lines += [
            "> **SMOKE MODE** — mechanics proof only. No gate JSON files written.",
            "> Results carry no verdict weight.",
            "",
        ]

    # IV coverage summary
    lines += [
        "## IV Coverage",
        "",
        "Greeks IV (required for S-CWIV and S-XZZ) is only available from the greeks "
        "tier of the store. Vendor greeks history starts later than EOD/OI "
        "(empty through ≥2015; exact start year in backfill logs).",
        "",
    ]
    if iv_cov:
        lines += ["| Root | First IV date | Last IV date | N dates |", "|---|---|---|---|"]
        for r, v in sorted(iv_cov.items()):
            lines.append(f"| {r} | {v['first']} | {v['last']} | {v['n_dates']} |")
    else:
        lines.append("_No greeks IV data found in store._")
    lines.append("")

    # Per-gate tables
    for gate_id, gate in gates.items():
        lines += [f"## {gate_id}", ""]

        era_stats = gate.get("era_stats", {})
        pooled = gate.get("pooled", {})

        if gate_id == "S-DOI":
            for h in _DOI_HORIZONS:
                lines += [
                    f"### S-DOI: {h}-day horizon",
                    "",
                    "| Era | N dates | Avg names | Mean IC | HAC-t | Hit | Excluded dates |",
                    "|---|---|---|---|---|---|---|",
                ]
                for era_label, _, _ in _ERAS:
                    es = era_stats.get(era_label, {}).get(str(h), {})
                    lines.append(
                        f"| {era_label} | {es.get('n_dates',0)} | "
                        f"{es.get('n_names_avg','—')} | "
                        f"{_fmt(es.get('mean_ic'))} | "
                        f"{_fmt(es.get('hac_t'))} | "
                        f"{_fmt(es.get('hit'))} | "
                        f"{es.get('excluded_dates',0)} |"
                    )
                # pooled
                ps = pooled.get(str(h), {})
                lines.append(
                    f"| **pooled** | **{ps.get('n_dates',0)}** | "
                    f"**{ps.get('n_names_avg','—')}** | "
                    f"**{_fmt(ps.get('mean_ic'))}** | "
                    f"**{_fmt(ps.get('hac_t'))}** | "
                    f"**{_fmt(ps.get('hit'))}** | "
                    f"{ps.get('excluded_dates',0)} |"
                )
                lines.append("")
        else:
            # S-CWIV / S-XZZ
            lines += [
                "| Era | N dates | Avg names | Mean IC | HAC-t | Hit | Excluded dates |",
                "|---|---|---|---|---|---|---|",
            ]
            for era_label, _, _ in _ERAS:
                es = era_stats.get(era_label, {})
                lines.append(
                    f"| {era_label} | {es.get('n_dates',0)} | "
                    f"{es.get('n_names_avg','—')} | "
                    f"{_fmt(es.get('mean_ic'))} | "
                    f"{_fmt(es.get('hac_t'))} | "
                    f"{_fmt(es.get('hit'))} | "
                    f"{es.get('excluded_dates',0)} |"
                )
            lines.append(
                f"| **pooled** | **{pooled.get('n_dates',0)}** | "
                f"**{pooled.get('n_names_avg','—')}** | "
                f"**{_fmt(pooled.get('mean_ic'))}** | "
                f"**{_fmt(pooled.get('hac_t'))}** | "
                f"**{_fmt(pooled.get('hit'))}** | "
                f"{pooled.get('excluded_dates',0)} |"
            )
            lines.append("")

    # Decay commentary stub
    lines += [
        "## Post-publication Decay Commentary",
        "",
        "_To be completed after full backfill. Template:_",
        "",
        "McLean-Pontiff (2016) document ~50% average post-publication decay for "
        "cross-sectional equity signals. The three gates here are 2006–2016 vintage "
        "(CW 2010, XZZ 2010, GPP demand-pressure). Era-split results above directly "
        "address decay: a claim alive only pre-2016 is dead per "
        "LIVE_ORDER_FLOW_BRAINSTORM §8.4.",
        "",
        "| Gate | Pre-2016 strongest era | Post-2020 era | Decay signal |",
        "|---|---|---|---|",
        "| S-DOI  | _fill after run_ | _fill_ | _fill_ |",
        "| S-CWIV | _fill_ | _fill_ | _fill_ |",
        "| S-XZZ  | _fill_ | _fill_ | _fill_ |",
        "",
        "---",
        "_Report generated by `scripts/rerun_options_gates_thetadata.py`._",
    ]

    p.write_text("\n".join(lines))
    log.info("wrote report: %s", p)
    return p


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    return f"{v:.4f}" if isinstance(v, float) else str(v)


# --------------------------------------------------------------------------- #
# Main entry point                                                              #
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=None,
                        help="ThetaData store root override (default: canonical resolver — "
                             "THETADATA_STORE env, then data_dir()/thetadata_eod, then ops-wt)")
    parser.add_argument("--smoke", action="store_true",
                        help="Smoke mode: run mechanics on whatever store exists; "
                             "clearly label output SMOKE; do NOT write gate JSON files")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    if args.smoke:
        log.info("=" * 60)
        log.info("SMOKE MODE — mechanics proof only; no gate JSON files written")
        log.info("=" * 60)

    # Resolve store root — WP-RESOLVER: --store CLI wins, else the canonical
    # resolver chain (THETADATA_STORE env → data_dir()/thetadata_eod → ops-wt,
    # content-checked). Fail-loud contract: in a real (non-smoke) run, a missing
    # store exits nonzero WITHOUT writing gate JSON files.
    from engine.thetadata_store import resolve_thetadata_store  # noqa: PLC0415
    if args.store:
        sroot = Path(args.store)
    else:
        sroot = resolve_thetadata_store(
            required=False, purpose="rerun_options_gates_thetadata")
    if sroot is None or not sroot.exists():
        if args.smoke:
            log.warning("[SMOKE] no ThetaData store resolves — nothing to run; "
                        "exiting 0 (smoke mode writes no gate files anyway)")
            return
        log.error("no ThetaData store resolves — exiting nonzero (gate JSON files "
                  "NOT written). Set THETADATA_STORE env or use --store to point "
                  "at the ops store.")
        sys.exit(1)
    store_arg = str(sroot)
    log.info("Store root: %s", sroot)

    # Universe
    roots = universe(store=store_arg)
    log.info("Roots in store: %s", roots)

    if not roots:
        if args.smoke:
            log.warning("[SMOKE] No roots found in store. Exiting 0.")
            return
        log.error("No roots found in store — exiting nonzero (gate JSON files "
                  "NOT written). Set THETADATA_STORE env or use --store to point "
                  "at the ops store.")
        sys.exit(1)

    # IV coverage
    iv_cov = iv_coverage(store=store_arg)
    log.info("IV coverage: %d roots with greeks", len(iv_cov))
    if iv_cov:
        for r, v in sorted(iv_cov.items()):
            log.info("  %s: %s → %s (%d dates)", r, v["first"], v["last"], v["n_dates"])
    else:
        log.info("  (no greeks data found — S-CWIV and S-XZZ will have empty panels)")

    # Thin-universe check
    _check_thin_universe(roots, _DOI_MIN_NAMES)
    _check_thin_universe(roots, _IV_MIN_NAMES)

    # TR closes for S-DOI forward returns
    tr_closes = _get_tr_closes()
    if tr_closes.empty:
        log.warning("TR closes not available — S-DOI will compute ΔOI series "
                    "but cannot compute forward-return rank-IC")
    else:
        log.info("TR closes: %d dates × %d names", len(tr_closes), len(tr_closes.columns))

    # Run gates
    doi_gate = run_s_doi(roots, tr_closes, store=store_arg, smoke=args.smoke)
    cwiv_gate = run_s_cwiv_or_xzz("cwiv", roots, iv_cov, store=store_arg, smoke=args.smoke)
    xzz_gate = run_s_cwiv_or_xzz("xzz", roots, iv_cov, store=store_arg, smoke=args.smoke)

    all_gates = {"S-DOI": doi_gate, "S-CWIV": cwiv_gate, "S-XZZ": xzz_gate}

    # Print summary
    print("\n" + "=" * 60)
    if args.smoke:
        print("[SMOKE] Options Gates ThetaData Re-run — mechanics proof")
    else:
        print("Options Gates ThetaData Re-run — results")
    print("=" * 60)
    print(f"Store: {sroot}")
    print(f"Roots: {roots}")
    print(f"IV coverage: {len(iv_cov)} roots with greeks")
    print()
    for gid, g in all_gates.items():
        print(f"  {gid}: n_dates={g.get('n_dates', g.get('n_dates_total', 0))} "
              f"scored={g.get('scored')}")
    print()

    # Write outputs (not in smoke mode)
    if not args.smoke:
        try:
            from lib import config  # noqa: PLC0415
            ddir = config.data_dir()
        except Exception:  # noqa: BLE001
            ddir = Path("data")

        _write_gate(ddir / "options_flow" / "gate_doi_thetadata.json", doi_gate)
        _write_gate(ddir / "options_ivspread" / "gate_thetadata.json", cwiv_gate)
        _write_gate(ddir / "options_skew" / "gate_thetadata.json", xzz_gate)
        _write_report(all_gates, str(sroot), iv_cov, smoke=False)
        log.info("Done. Gate files written. Verdicts pending full backfill completion.")
    else:
        log.info("[SMOKE] No gate JSON files written (smoke mode).")
        # Still write the report with SMOKE label for the PR body
        _write_report(all_gates, str(sroot), iv_cov, smoke=True)
        log.info("[SMOKE] Report written (labeled SMOKE).")


if __name__ == "__main__":
    main()
