"""Track-Record Audit — Signal Engine Buy-Filter

MEASUREMENT TOOL: drawdown / entry-quality framing.
NOT return-alpha. NOT a verdict machine.
See research/signal_engine/CHARTER.md §2b, §3, §4.

Loads data/signal_archive/track_record.parquet and answers three questions,
all framed on forward max drawdown:
  (a) take vs block: does the buy-filter actually route worse entries to 'block'?
  (b) per-regime: where does the filter fail by regime_at_entry?
  (c) per-archetype: where does the filter fail by vol_annual_at_entry tercile?

Writes a markdown report to research/signal_engine/_track_record_audit.md
and prints it to stdout.

CLI flags:
  --strict-forward   Restrict to rows where date >= first_seen_asof minus 3 days
                     (i.e., captured live-forward, not backfill). Documents the rule.

Dependencies: pandas, numpy, pyarrow only. Python 3.
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
PARQUET = ROOT / "data" / "signal_archive" / "track_record.parquet"
OUT_MD = Path(__file__).resolve().parent / "_track_record_audit.md"

# ---------------------------------------------------------------------------
# Bootstrap CI (numpy-only, no scipy)
# ---------------------------------------------------------------------------
_RNG = np.random.default_rng(42)

def _bootstrap_ci(arr: np.ndarray, stat_fn, n_boot: int = 2000, ci: float = 0.95) -> tuple[float, float]:
    """Return (lo, hi) bootstrap CI for stat_fn(arr). Returns (nan, nan) if n<2."""
    if len(arr) < 2:
        return (float("nan"), float("nan"))
    boots = np.array([stat_fn(_RNG.choice(arr, size=len(arr), replace=True)) for _ in range(n_boot)])
    alpha = (1 - ci) / 2
    return (float(np.nanpercentile(boots, alpha * 100)), float(np.nanpercentile(boots, (1 - alpha) * 100)))


def _median_gap_ci(take_arr: np.ndarray, block_arr: np.ndarray, n_boot: int = 2000) -> tuple[float, float, float]:
    """Bootstrap CI on (median_take - median_block). Positive = take is shallower (less negative) = good.
    Returns (gap_point_estimate, ci_lo, ci_hi)."""
    if len(take_arr) < 2 or len(block_arr) < 2:
        return (float("nan"), float("nan"), float("nan"))
    gaps = []
    for _ in range(n_boot):
        t = _RNG.choice(take_arr, size=len(take_arr), replace=True)
        b = _RNG.choice(block_arr, size=len(block_arr), replace=True)
        gaps.append(np.nanmedian(t) - np.nanmedian(b))
    point = float(np.nanmedian(take_arr) - np.nanmedian(block_arr))
    return (point, float(np.nanpercentile(gaps, 2.5)), float(np.nanpercentile(gaps, 97.5)))


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
SMALL_N = 10  # warn if n < this

def _fmt_pct(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    return f"{v * 100:.1f}%"

def _fmt_n(n: int) -> str:
    warn = " ⚠ small-n" if n < SMALL_N else ""
    return f"n={n}{warn}"

def _small(n: int) -> str:
    return " **(small-n)**" if n < SMALL_N else ""

def _cell(arr, threshold: float = -0.15) -> dict:
    """Compute drawdown stats for a numpy array of drawdown values (all ≤ 0)."""
    n = int(np.sum(~np.isnan(arr)))
    if n == 0:
        return {"n": 0, "median": float("nan"), "mean": float("nan"), "tail_rate": float("nan")}
    valid = arr[~np.isnan(arr)]
    return {
        "n": n,
        "median": float(np.nanmedian(valid)),
        "mean": float(np.nanmean(valid)),
        "tail_rate": float(np.mean(valid < threshold)),
    }


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _section_a(df_entry: pd.DataFrame, lines: list[str]) -> list[str]:
    """(a) Overall take vs block drawdown comparison."""
    lines.append("## (a) Overall Take vs Block — Forward Drawdown")
    lines.append("")
    lines.append(
        "Filter earns its keep iff **take drawdowns are shallower (less negative) than block**. "
        "Tail rate = share of entries with drawdown < −15%."
    )
    lines.append("")

    for metric, label in [("fwd_mdd_60", "60-day fwd max drawdown"), ("trade_mae", "trade MAE (entry→exit)")]:
        lines.append(f"### {label}")
        sub = df_entry.dropna(subset=[metric])
        take_arr = sub.loc[sub["quality"] == "take", metric].to_numpy()
        block_arr = sub.loc[sub["quality"] == "block", metric].to_numpy()

        ct = _cell(take_arr)
        cb = _cell(block_arr)
        gap, lo, hi = _median_gap_ci(take_arr, block_arr)

        lines.append("")
        lines.append(f"| quality | n | median | mean | tail<−15% |")
        lines.append(f"|---|---|---|---|---|")
        lines.append(
            f"| **take** | {ct['n']}{_small(ct['n'])} | {_fmt_pct(ct['median'])} "
            f"| {_fmt_pct(ct['mean'])} | {_fmt_pct(ct['tail_rate'])} |"
        )
        lines.append(
            f"| **block** | {cb['n']}{_small(cb['n'])} | {_fmt_pct(cb['median'])} "
            f"| {_fmt_pct(cb['mean'])} | {_fmt_pct(cb['tail_rate'])} |"
        )
        lines.append("")

        if not np.isnan(gap):
            # Diagnostic reading, NOT a ship/kill verdict. Per CHARTER §2f/§3 this is a
            # microscope: the only call that ships/kills anything is the held-out
            # generalization gate, not a fixed gap threshold. ±0.5% is a display cutoff
            # to bucket the read, nothing more.
            reading = (
                "take drawdowns shallower than block — consistent with the filter's claim"
                if gap > 0.005
                else "no material separation between take and block drawdowns — investigate"
                if gap > -0.005
                else "separation reversed (take draws down MORE than block) — investigate"
            )
            lines.append(
                f"**Median gap (take − block): {_fmt_pct(gap)}** "
                f"(95% bootstrap CI: [{_fmt_pct(lo)}, {_fmt_pct(hi)}])"
            )
            lines.append(f"> Diagnostic reading (±0.5% display cutoff, not a ship/kill rule): {reading}")
        else:
            lines.append("> Insufficient data to compute gap CI.")
        lines.append("")

    return lines


def _section_b(df_entry: pd.DataFrame, lines: list[str]) -> list[str]:
    """(b) Per-regime take vs block comparison."""
    lines.append("## (b) Per-Regime Take vs Block — Forward Drawdown (fwd_mdd_60)")
    lines.append("")
    lines.append(
        "Cells where **block fails to avoid drawdown** (block median ≈ take median) "
        "or **take still draws down deeply** (take tail > 30%) are blind spots."
    )
    lines.append("")

    regimes = ["bull", "bear", "choppy", "unknown"]
    metric = "fwd_mdd_60"
    sub = df_entry.dropna(subset=[metric])

    lines.append(f"| regime | quality | n | median | mean | tail<−15% | blind spot? |")
    lines.append(f"|---|---|---|---|---|---|---|")

    blind_spots = []
    for regime in regimes:
        r_sub = sub[sub["regime_at_entry"] == regime]
        if len(r_sub) == 0:
            continue
        for quality in ["take", "block"]:
            arr = r_sub.loc[r_sub["quality"] == quality, metric].to_numpy()
            c = _cell(arr)
            if c["n"] == 0:
                lines.append(f"| {regime} | {quality} | 0 | — | — | — | — |")
                continue
            # Determine blind spots
            is_blind = False
            flag = ""
            if quality == "block":
                # get take for same regime
                take_arr = r_sub.loc[r_sub["quality"] == "take", metric].to_numpy()
                if len(take_arr) > 0 and not np.isnan(c["median"]) and not np.isnan(np.nanmedian(take_arr)):
                    gap = np.nanmedian(take_arr) - c["median"]  # positive = take shallower
                    if gap < 0.02:  # block not meaningfully worse than take
                        is_blind = True
                        flag = "block not avoided"
            if quality == "take" and not np.isnan(c["tail_rate"]) and c["tail_rate"] > 0.30:
                is_blind = True
                flag = "take draws down deeply"
            if is_blind:
                blind_spots.append((regime, quality, flag))
            lines.append(
                f"| {regime} | {quality} | {c['n']}{_small(c['n'])} "
                f"| {_fmt_pct(c['median'])} | {_fmt_pct(c['mean'])} "
                f"| {_fmt_pct(c['tail_rate'])} | {'**' + flag + '**' if flag else '—'} |"
            )

    lines.append("")
    if blind_spots:
        lines.append("**Identified blind spots:**")
        for regime, quality, flag in blind_spots:
            lines.append(f"- `{regime}` × `{quality}`: {flag}")
    else:
        lines.append("No clear blind spots detected (or insufficient data).")
    lines.append("")
    return lines


def _section_c(df_entry: pd.DataFrame, lines: list[str]) -> list[str]:
    """(c) Per-archetype (vol_annual_at_entry tercile) take vs block comparison."""
    lines.append("## (c) Per-Archetype Take vs Block — Forward Drawdown (fwd_mdd_60)")
    lines.append("")
    lines.append(
        "Archetype = cross-sectional tercile of `vol_annual_at_entry` (trailing-63d annualized vol). "
        "Tercile thresholds are percentiles of the entry population, NOT absolute thresholds (CHARTER §2e). "
        "Low-vol = grinders; high-vol = high-beta."
    )
    lines.append("")

    metric = "fwd_mdd_60"
    sub = df_entry.dropna(subset=[metric, "vol_annual_at_entry"])

    if len(sub) < 6:
        lines.append("Insufficient data for archetype split.")
        lines.append("")
        return lines

    # Compute cross-sectional tercile thresholds from the FULL entry population
    p33 = float(np.nanpercentile(sub["vol_annual_at_entry"].to_numpy(), 33.33))
    p67 = float(np.nanpercentile(sub["vol_annual_at_entry"].to_numpy(), 66.67))

    def archetype(vol):
        if vol <= p33:
            return "low-vol (grinder)"
        elif vol <= p67:
            return "mid-vol"
        else:
            return "high-vol (high-beta)"

    sub = sub.copy()
    sub["archetype"] = sub["vol_annual_at_entry"].apply(archetype)

    lines.append(
        f"Vol tercile thresholds (cross-sectional): p33={_fmt_pct(p33)} ann. vol, "
        f"p67={_fmt_pct(p67)} ann. vol"
    )
    lines.append("")
    lines.append(f"| archetype | quality | n | median | mean | tail<−15% |")
    lines.append(f"|---|---|---|---|---|---|")

    archetype_order = ["low-vol (grinder)", "mid-vol", "high-vol (high-beta)"]
    blind_spots = []
    for arch in archetype_order:
        a_sub = sub[sub["archetype"] == arch]
        for quality in ["take", "block"]:
            arr = a_sub.loc[a_sub["quality"] == quality, metric].to_numpy()
            c = _cell(arr)
            if c["n"] == 0:
                lines.append(f"| {arch} | {quality} | 0 | — | — | — |")
                continue
            flag = ""
            if quality == "block":
                take_arr = a_sub.loc[a_sub["quality"] == "take", metric].to_numpy()
                if len(take_arr) > 0 and not np.isnan(c["median"]) and not np.isnan(np.nanmedian(take_arr)):
                    gap = np.nanmedian(take_arr) - c["median"]
                    if gap < 0.02:
                        flag = "block not avoided"
                        blind_spots.append((arch, quality, flag))
            if quality == "take" and not np.isnan(c["tail_rate"]) and c["tail_rate"] > 0.30:
                flag = "take draws deeply"
                blind_spots.append((arch, quality, flag))
            lines.append(
                f"| {arch} | {quality} | {c['n']}{_small(c['n'])} "
                f"| {_fmt_pct(c['median'])} | {_fmt_pct(c['mean'])} "
                f"| {_fmt_pct(c['tail_rate'])} |"
            )

    lines.append("")
    if blind_spots:
        lines.append("**Identified blind spots:**")
        for arch, quality, flag in blind_spots:
            lines.append(f"- `{arch}` × `{quality}`: {flag}")
    else:
        lines.append("No clear archetype blind spots detected (or insufficient data).")
    lines.append("")
    return lines


def _section_brainstorm(df_entry: pd.DataFrame, lines: list[str]) -> list[str]:
    """Build 'TOPICS FOR TUNING / BRAINSTORM' from the weakest cells."""
    lines.append("## TOPICS FOR TUNING / BRAINSTORM")
    lines.append("")
    lines.append(
        "_The following questions are surfaced from the weakest cells above. "
        "They are the concrete agenda for the next tuning session._"
    )
    lines.append("")

    metric = "fwd_mdd_60"
    questions = []

    # Collect regime x quality cells
    sub = df_entry.dropna(subset=[metric])
    for regime in ["bull", "bear", "choppy"]:
        r_sub = sub[sub["regime_at_entry"] == regime]
        if len(r_sub) < 2:
            continue
        take_arr = r_sub.loc[r_sub["quality"] == "take", metric].to_numpy()
        block_arr = r_sub.loc[r_sub["quality"] == "block", metric].to_numpy()
        # block not materially worse than take
        if len(take_arr) >= 3 and len(block_arr) >= 3:
            gap = np.nanmedian(take_arr) - np.nanmedian(block_arr)
            if gap < 0.02:
                questions.append(
                    f"**[regime={regime}]** The filter does not meaningfully separate 'block' from 'take' "
                    f"drawdowns in the `{regime}` regime (gap={_fmt_pct(gap)}). "
                    f"Does the buy-filter need a regime-specific veto (e.g., tighten reclaim window in bear, "
                    f"relax divergence veto in choppy)? Or is sample size the limiting factor?"
                )
        # take draws deeply
        if len(take_arr) >= 3 and not np.isnan(np.mean(take_arr < -0.15)):
            tail = np.mean(take_arr < -0.15)
            if tail > 0.30:
                questions.append(
                    f"**[regime={regime}, quality=take]** {_fmt_pct(tail)} of 'take' entries in the "
                    f"`{regime}` regime draw down past −15%. What additional gate (e.g., weekly trend "
                    f"confirmation, breadth check, macro-risk overlay) would screen these out without "
                    f"discarding the good entries?"
                )

    # Archetype questions
    sub2 = df_entry.dropna(subset=[metric, "vol_annual_at_entry"])
    if len(sub2) >= 6:
        p33 = float(np.nanpercentile(sub2["vol_annual_at_entry"].to_numpy(), 33.33))
        p67 = float(np.nanpercentile(sub2["vol_annual_at_entry"].to_numpy(), 66.67))
        for arch_label, lo, hi in [
            ("low-vol (grinder)", 0, p33),
            ("mid-vol", p33, p67),
            ("high-vol (high-beta)", p67, float("inf")),
        ]:
            a_sub = sub2[
                (sub2["vol_annual_at_entry"] >= lo) & (sub2["vol_annual_at_entry"] < hi)
            ] if hi < float("inf") else sub2[sub2["vol_annual_at_entry"] >= lo]
            take_arr = a_sub.loc[a_sub["quality"] == "take", metric].to_numpy()
            block_arr = a_sub.loc[a_sub["quality"] == "block", metric].to_numpy()
            if len(take_arr) >= 3 and len(block_arr) >= 3:
                gap = np.nanmedian(take_arr) - np.nanmedian(block_arr)
                if gap < 0.02:
                    questions.append(
                        f"**[archetype={arch_label}]** In the `{arch_label}` bucket, block entries "
                        f"are not significantly worse than take (gap={_fmt_pct(gap)}). "
                        f"Should the vol/ER regime input to the filter be adapted for this archetype? "
                        f"E.g., is the Efficiency Ratio threshold miscalibrated for low-amplitude grinders?"
                    )
            if len(take_arr) >= 3 and not np.isnan(np.mean(take_arr < -0.15)):
                tail = np.mean(take_arr < -0.15)
                if tail > 0.30:
                    questions.append(
                        f"**[archetype={arch_label}, quality=take]** {_fmt_pct(tail)} of 'take' entries in "
                        f"`{arch_label}` tickers draw down past −15%. "
                        f"Does the per-archetype reclaim window or the divergence look-back need extending "
                        f"for high-vol names? Consider an ATR-percentile gate before promoting to 'take'."
                    )

    # --- Always surface the *relatively* weakest cells, even when no hard threshold
    #     tripped, so the agenda is never empty on healthy data. This is the tool's job:
    #     point the next session at where endorsed ('take') entries hurt most. Ranked by
    #     take-side deep-drawdown tail, then median depth. NOT a failure flag — the filter
    #     can still beat 'block' in the weakest cell. ---
    def _take_weakness(frame):
        arr = frame.loc[frame["quality"] == "take", metric].to_numpy()
        arr = arr[~np.isnan(arr)]
        if len(arr) < 3:
            return None
        return (float(np.median(arr)), float(np.mean(arr < -0.15)), int(len(arr)))

    weakest = []
    for regime in ["bull", "bear", "choppy"]:
        w = _take_weakness(sub[sub["regime_at_entry"] == regime])
        if w:
            weakest.append((f"regime={regime}", *w))
    sub2w = df_entry.dropna(subset=[metric, "vol_annual_at_entry"])
    if len(sub2w) >= 6:
        p33w = float(np.nanpercentile(sub2w["vol_annual_at_entry"].to_numpy(), 33.33))
        p67w = float(np.nanpercentile(sub2w["vol_annual_at_entry"].to_numpy(), 66.67))
        for label, lo, hi in [
            ("low-vol grinder", -np.inf, p33w),
            ("mid-vol", p33w, p67w),
            ("high-vol high-beta", p67w, np.inf),
        ]:
            seg = sub2w[(sub2w["vol_annual_at_entry"] > lo) & (sub2w["vol_annual_at_entry"] <= hi)]
            w = _take_weakness(seg)
            if w:
                weakest.append((f"archetype={label}", *w))
    # rank: highest deep-drawdown tail first, then deepest median
    weakest.sort(key=lambda x: (-x[2], x[1]))
    if weakest:
        lab, med, tail, n = weakest[0]
        questions.insert(0,
            f"**[weakest cell: {lab}]** Across the panel, 'take' (endorsed) entries here have "
            f"the deepest forward-drawdown profile (median {_fmt_pct(med)}, {_fmt_pct(tail)} beyond "
            f"−15%, n={n}) — this is where the filter's *kept* entries hurt most, even though it "
            f"still beats 'block' here. What extra gate (ATR/vol-percentile cap, weekly-trend or "
            f"breadth confirmation, tighter reclaim window) would shave this take-side tail without "
            f"discarding the good entries?"
        )

    # Generic questions always shown
    questions.append(
        "**[data maturation]** Many entries may still be `still_held` (outcome unresolved). "
        "As `trade_mae` and `fwd_mdd_60/180` mature, re-run this audit. "
        "Which regime × archetype cells are least mature, and could that bias the current picture?"
    )
    questions.append(
        "**[er_at_entry]** The Kaufman Efficiency Ratio (ER) is logged per entry but not yet used "
        "in the audit split. Do entries with ER > 0.5 (trending) exhibit shallower 'take' drawdowns "
        "vs entries with ER < 0.3 (choppy)? This is the CHARTER-blessed primitive for archetype detection."
    )
    questions.append(
        "**[strict-forward]** The current report includes backfill rows. "
        "Re-run with `--strict-forward` once enough live-forward rows have accumulated. "
        "Does the take-vs-block gap hold on strictly live data, or was it front-loaded on backfill?"
    )

    if not questions:
        questions.append(
            "No significant blind spots found in the current dataset. "
            "Accumulate more matured rows and re-run. "
            "Key question: does the take-vs-block gap hold with `--strict-forward`?"
        )

    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q}")
        lines.append("")

    return lines


# ---------------------------------------------------------------------------
# Main audit driver
# ---------------------------------------------------------------------------

def _load_parquet(strict_forward: bool, parquet_path: Path | None = None) -> tuple[pd.DataFrame | None, str]:
    """Load track_record.parquet, applying strict-forward filter if requested.
    Returns (df, message). df is None if unusable."""
    path = parquet_path if parquet_path is not None else PARQUET
    if not path.exists():
        return None, (
            f"**track_record.parquet not found** at `{path}`. "
            "Run `engine/track_record.py` (or `scripts/build_track_record.py`) "
            "to populate the track record before running this audit."
        )

    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        return None, f"**Failed to read parquet:** {exc}"

    if df.empty:
        return None, "**track_record.parquet exists but is empty.** No data to audit yet."

    msg_parts = [f"Loaded {len(df):,} rows from `{path.name}`."]

    # Strict-forward filter: rows where date >= first_seen_asof - 3 calendar days
    # i.e., the signal's bar date is at most 3 days before the build that first logged it
    # (backfill rows have date << first_seen_asof; live rows have date ~ first_seen_asof).
    if strict_forward:
        if "date" in df.columns and "first_seen_asof" in df.columns:
            try:
                df["_date"] = pd.to_datetime(df["date"])
                df["_asof"] = pd.to_datetime(df["first_seen_asof"])
                df = df[df["_date"] >= df["_asof"] - pd.Timedelta(days=3)].copy()
                df = df.drop(columns=["_date", "_asof"], errors="ignore")
                msg_parts.append(
                    f"--strict-forward applied: {len(df):,} rows retained "
                    "(rule: marker date >= first_seen_asof - 3 calendar days). "
                    "These rows were captured live-forward, not from historical backfill."
                )
            except Exception as exc:
                msg_parts.append(f"--strict-forward requested but could not apply: {exc}")
        else:
            msg_parts.append("--strict-forward requested but 'date'/'first_seen_asof' columns missing.")

    return df, " ".join(msg_parts)


def _filter_entry_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Return entry-only rows (buy/rebuy) with quality in {take, block}, matured fwd_mdd_60.
    Exclude outcome=='still_held' from trade MAE stats (handled in _cell calls).
    """
    entries = df[df["type"].isin(["buy", "rebuy"]) & df["quality"].isin(["take", "block"])].copy()
    n_total = len(entries)
    # For the fwd_mdd_60 analysis: include all entry rows (matured or not — NaN will be excluded in _cell)
    # For trade_mae outcome analysis: we exclude still_held in the per-section handling
    msg = f"{n_total:,} entry rows (buy/rebuy with quality=take/block)."
    n_matured_mdd = entries["fwd_mdd_60"].notna().sum()
    n_matured_mae = entries["trade_mae"].notna().sum()
    msg += (
        f" fwd_mdd_60 matured: {n_matured_mdd:,}. "
        f"trade_mae matured: {n_matured_mae:,}."
    )
    if n_matured_mdd < 10:
        msg += " **Insufficient matured data — statistics below are unreliable.**"
    return entries, msg


def build_report(df: pd.DataFrame, load_msg: str, strict_forward: bool) -> list[str]:
    """Build the full markdown report as a list of lines."""
    lines: list[str] = []

    # Header
    lines.append("# Signal Engine Track-Record Audit")
    lines.append("")
    lines.append(
        "> **MEASUREMENT, drawdown/entry-quality framing, NOT return-alpha, NOT a verdict machine.**  "
    )
    lines.append(
        "> See `research/signal_engine/CHARTER.md` §2b (risk tool, not return engine), "
        "§3 (forward-only generalization), §4 (tripwires).  "
    )
    lines.append(
        "> The filter's job: route entries with worse forward drawdowns to 'block', "
        "better ones to 'take'. Return / P&L are secondary context only."
    )
    lines.append("")
    lines.append(f"**Data:** {load_msg}")
    if strict_forward:
        lines.append(
            "**Mode:** `--strict-forward` (live-forward rows only; "
            "rule: marker date >= first_seen_asof − 3 calendar days)"
        )
    else:
        lines.append(
            "**Mode:** full history (includes historical backfill). "
            "Use `--strict-forward` for live-forward-only analysis."
        )
    lines.append("")

    entries, entry_msg = _filter_entry_rows(df)
    lines.append(f"**Scope:** {entry_msg}")
    lines.append("")

    # Maturation note
    n_matured = int(entries["fwd_mdd_60"].notna().sum())
    if n_matured < 10:
        lines.append("")
        lines.append(
            "---\n"
            "**INSUFFICIENT MATURED DATA** — fewer than 10 entries have a matured `fwd_mdd_60`. "
            "The statistics below are illustrative only. "
            "Re-run this audit after more forward data has accrued (allow 60+ trading days "
            "from the entry dates, then re-run `build_track_record.py`)."
        )
        lines.append("")
        # Still fall through and show tables with n/a values rather than crashing

    lines.append("---")
    lines.append("")

    # Coverage summary table
    lines.append("## Coverage Summary")
    lines.append("")
    lines.append("| metric | n |")
    lines.append("|---|---|")
    lines.append(f"| total rows in parquet | {len(df):,} |")
    lines.append(f"| entry rows (buy/rebuy, quality=take/block) | {len(entries):,} |")
    lines.append(f"| entry rows, quality=take | {(entries['quality']=='take').sum():,} |")
    lines.append(f"| entry rows, quality=block | {(entries['quality']=='block').sum():,} |")
    lines.append(f"| fwd_mdd_60 matured | {n_matured:,} |")
    lines.append(f"| trade_mae matured | {int(entries['trade_mae'].notna().sum()):,} |")
    lines.append(f"| outcome=still_held | {int((entries.get('outcome','') == 'still_held').sum()):,} |")
    if "regime_at_entry" in entries.columns:
        for r in ["bull", "bear", "choppy", "unknown"]:
            rn = int((entries["regime_at_entry"] == r).sum())
            lines.append(f"| regime_at_entry={r} | {rn:,} |")
    lines.append("")

    # For trade_mae: exclude still_held (outcome is the trade-level result)
    if "outcome" in entries.columns:
        entries_mae = entries[entries["outcome"] != "still_held"].copy()
    else:
        entries_mae = entries.copy()

    # Inject trade_mae from the non-still_held subset back into 'entries' temporarily
    # by NaN-ing still_held trade_mae
    entries = entries.copy()
    if "outcome" in entries.columns:
        entries.loc[entries["outcome"] == "still_held", "trade_mae"] = np.nan

    # Section (a)
    lines = _section_a(entries, lines)

    # Section (b)
    if "regime_at_entry" not in entries.columns:
        lines.append("## (b) Per-Regime — regime_at_entry column not found in parquet")
        lines.append("")
    else:
        lines = _section_b(entries, lines)

    # Section (c)
    if "vol_annual_at_entry" not in entries.columns:
        lines.append("## (c) Per-Archetype — vol_annual_at_entry column not found in parquet")
        lines.append("")
    else:
        lines = _section_c(entries, lines)

    # Brainstorm
    lines.append("---")
    lines.append("")
    lines = _section_brainstorm(entries, lines)

    lines.append("---")
    lines.append("")
    lines.append(
        "*Generated by `research/signal_engine/track_record_audit.py`. "
        "Re-run after each `build_track_record.py` cycle.*"
    )
    lines.append("")

    return lines


def _insufficient_report(msg: str) -> list[str]:
    """Minimal report when data cannot be loaded."""
    lines = []
    lines.append("# Signal Engine Track-Record Audit")
    lines.append("")
    lines.append(
        "> MEASUREMENT, drawdown/entry-quality framing, NOT return-alpha, NOT a verdict machine."
    )
    lines.append("")
    lines.append(f"## Status: {msg}")
    lines.append("")
    lines.append(
        "No statistics can be computed. "
        "Populate the track record by running "
        "`python engine/track_record.py` (or `scripts/build_track_record.py`), "
        "then re-run this audit."
    )
    lines.append("")
    lines.append("## TOPICS FOR TUNING / BRAINSTORM")
    lines.append("")
    lines.append(
        "1. **[bootstrap]** Once the parquet is populated, does the take-vs-block "
        "median drawdown gap hold at the 95% bootstrap CI level across all 110 names?"
    )
    lines.append("")
    lines.append(
        "2. **[regime]** In which of bull/bear/choppy does the buy-filter fail to separate "
        "'take' from 'block' drawdowns? Bear regimes are the high-stakes case."
    )
    lines.append("")
    lines.append(
        "3. **[archetype]** Do high-vol (high-beta) names violate the filter's "
        "reclaim-and-hold assumption? An ATR-percentile gate might be needed."
    )
    lines.append("")
    lines.append(
        "4. **[strict-forward]** Once live-forward rows accumulate, "
        "does the gap hold with `--strict-forward`? Backfill rows are out-of-sample "
        "but the design was tuned on some of these names."
    )
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Signal Engine Track-Record Audit. "
            "MEASUREMENT — drawdown/entry-quality framing, NOT return-alpha, NOT a verdict machine. "
            "See CHARTER.md §2b, §3, §4."
        )
    )
    parser.add_argument(
        "--strict-forward",
        action="store_true",
        default=False,
        help=(
            "Restrict to rows captured live-forward: marker date >= first_seen_asof - 3 calendar days. "
            "Rows where date << first_seen_asof are historical backfill (excluded in this mode)."
        ),
    )
    parser.add_argument(
        "--parquet",
        default=str(PARQUET),
        help=f"Path to track_record.parquet (default: {PARQUET})",
    )
    parser.add_argument(
        "--out",
        default=str(OUT_MD),
        help=f"Path to write the markdown report (default: {OUT_MD})",
    )
    args = parser.parse_args()

    # Use CLI-overridden paths (avoid global mutation — Python scoping)
    parquet_path = Path(args.parquet)
    out_path = Path(args.out)

    df, load_msg = _load_parquet(args.strict_forward, parquet_path=parquet_path)

    if df is None:
        report_lines = _insufficient_report(load_msg)
    else:
        report_lines = build_report(df, load_msg, args.strict_forward)

    report = "\n".join(report_lines)
    print(report)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\n[audit] Report written to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
