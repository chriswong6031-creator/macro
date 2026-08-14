"""Per-name dossiers — the artifact the operator actually reads (§14 PR-1 row).

The PR-1 "not done unless" row says *dossiers reviewed by operator*, so these are
built to be eyeballed, not parsed: an identity header that states where the history
came from and what hygiene found, the fingerprint snapshot with raw values beside
universe percentiles, the episode table with its resolutions, the state shares by
year, and one chart per name showing the episode structure against the price.

Everything here is display-tier and authority-free. There is no expert content, no
ordering of names, and no "best" anything — W1 has no fit result by law.

Two honest-reading rules the layout enforces:

* **Raw beside percentile.** A percentile alone hides whether a name is at the 90th
  percentile of a tight distribution or a wild one; the raw value alone hides
  whether 0.31 is high. Both columns, always.
* **Coverage and instability are columns, not footnotes.** A masked feature reads as
  ``—`` with its mask stated, and an ``unstable`` feature is marked inline, because
  an unstable value that looks like a clean number is worse than a null.

``matplotlib`` is imported *inside* the render function: the module must stay
importable in a bare pandas/numpy environment (the test job installs no plotting
stack), and nothing but chart rendering needs it.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from engine.stock_identity import episodes as ep_mod
from engine.stock_identity import fingerprint as fp_mod
from engine.stock_identity import state as state_mod

log = logging.getLogger(__name__)

#: Episode-span fill colors, by type. Chosen for legibility on a light chart, and
#: deliberately not a red/green semantic pair — an episode is not good or bad.
_SPAN_COLORS = {
    "reset_decline": "#c8d6e5",
    "reclaim": "#cfe3cf",
    "failed_breakdown": "#efe0c4",
}
_STATE_COLORS = {
    "structural_uptrend": "#4a7c59",
    "controlled_pullback": "#8fb996",
    "range": "#b8b8b8",
    "breakdown": "#b5651d",
    "deep_washout": "#8b2f2f",
    "recovery_reclaim": "#4a6fa5",
    "post_event_dislocation": "#6b4a8b",
    "vol_transition": "#c9a227",
}

_SVG_SIZE_LIMIT_BYTES = 300_000


def _fmt(v: Any, nd: int = 4) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, float):
        if abs(v) >= 1e6:
            return f"{v:.3e}"
        return f"{v:.{nd}f}"
    return str(v)


def _fmt_date(v: Any) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)) or pd.isna(v):
        return "—"
    return str(pd.Timestamp(v).date())


def render_markdown(
    *,
    symbol: str,
    plane_id: str,
    snapshot_row: Mapping[str, Any],
    hygiene: Mapping[str, Any],
    raw: Mapping[str, Any],
    percentiles: Mapping[str, Any],
    coverage: Mapping[str, bool],
    unstable: Mapping[str, bool],
    catalog: pd.DataFrame,
    state_shares: pd.DataFrame,
    constants_meta: Mapping[str, Any],
    chart_rel: str | None,
    pilot_role: str = "",
) -> str:
    """The dossier body. Pure text — no plotting, no I/O."""
    L: list[str] = []
    L.append(f"# {symbol} — Identity Atlas v0 dossier")
    L.append("")
    L.append(
        "Descriptive behavioral read. **Zero authority**: nothing on this page ranks, "
        "sizes, gates, originates a signal, or escalates. No expert content exists in "
        "W1 by law. Episode *resolutions* use future data by design — they are a "
        "research-time labeling instrument, never a live surface."
    )
    L.append("")

    # ---------------- identity header ----------------
    L.append("## Identity")
    L.append("")
    L.append("| field | value |")
    L.append("|---|---|")
    L.append(f"| pilot role | {pilot_role or '—'} |")
    L.append(f"| price plane | `{plane_id}` |")
    L.append(f"| first print | {_fmt_date(snapshot_row.get('first_date'))} |")
    L.append(f"| last print | {_fmt_date(snapshot_row.get('last_date'))} |")
    L.append(f"| sessions | {snapshot_row.get('n_rows')} |")
    L.append(f"| `open` available | {bool(snapshot_row.get('has_open'))} |")
    L.append(f"| sector stratum | {snapshot_row.get('sector', 'UNKNOWN')} |")
    L.append(
        f"| cap stratum | {snapshot_row.get('cap_bucket', 'UNKNOWN')} "
        "(dollar-ADV tercile **proxy** — no per-name cap store is tracked) |"
    )
    L.append(f"| vol stratum | {snapshot_row.get('vol_tercile', 'UNKNOWN')} |")
    L.append(f"| epoch key | `epoch_0` (listing-to-date; epoch detector: none/provisional) |")
    L.append(f"| tape ended | {bool(snapshot_row.get('tape_ended', False))} |")
    if snapshot_row.get("terminated_reason"):
        L.append(f"| terminated reason | {snapshot_row.get('terminated_reason')} |")
    L.append("")
    L.append(
        "**Survivor-only cohort:** the allowed price planes retain no ceased tapes; no "
        "dead name could be included (registration §2). Any cohort comparison this name "
        "appears in is a comparison among survivors and cannot name who is missing."
    )
    L.append("")

    L.append("### Ticker-identity hygiene (§9.6)")
    L.append("")
    flags = list(hygiene.get("flags") or [])
    if not flags:
        L.append("No reused-ticker, rename, fixup, or delisting flag on this symbol.")
    else:
        L.append("| flag | resolution |")
        L.append("|---|---|")
        notes = hygiene.get("notes") or {}
        for f in flags:
            L.append(f"| `{f}` | {notes.get(f, '—')} |")
    L.append("")
    L.append(
        f"**First-print sanity:** `{hygiene.get('first_print_sanity')}` — "
        f"{hygiene.get('first_print_note')}"
    )
    L.append("")

    # ---------------- fingerprint ----------------
    L.append("## Behavioral fingerprint v0 (snapshot at asof)")
    L.append("")
    L.append(
        "Percentiles are PIT ranks against the contemporaneous evaluated universe. "
        "`—` is a coverage mask (the value is unavailable, which is not a low rank). "
        "`unstable` marks an adjacent-window quartile jump: the windows disagree, so "
        "the number is reported flagged rather than averaged into a clean-looking one."
    )
    L.append("")
    L.append("### Metric block")
    L.append("")
    L.append(
        "The only block any future distance or map may read. Label-free by "
        "construction: no sector, industry, cap bucket, plane, or basket member here, "
        "and no gap-family member (the gap family is structurally unavailable on the "
        "open-less curated plane, so the plane law excludes it from this block "
        "universe-wide)."
    )
    L.append("")
    L.append("| feature | family | raw | universe pct | covered | unstable |")
    L.append("|---|---|---:|---:|:--:|:--:|")
    for f in fp_mod.METRIC_FEATURES:
        n = f["name"]
        L.append(
            f"| `{n}` | {f['family']} | {_fmt(raw.get(n))} | "
            f"{_fmt(percentiles.get(n), 1)} | "
            f"{'yes' if coverage.get(n) else 'no'} | "
            f"{'**unstable**' if unstable.get(n) else ''} |"
        )
    L.append("")
    L.append("### Diagnostic block")
    L.append("")
    L.append(
        "Census and baseline use only — never a distance input, never a map input."
    )
    L.append("")
    L.append("| feature | raw | universe pct | covered |")
    L.append("|---|---:|---:|:--:|")
    for f in fp_mod.DIAGNOSTIC_FEATURES:
        n = f["name"]
        L.append(
            f"| `{n}` | {_fmt(raw.get(n))} | "
            f"{_fmt(percentiles.get(n), 1) if n in fp_mod.DIAGNOSTIC_NUMERIC else '—'} | "
            f"{'yes' if coverage.get(n, raw.get(n) is not None) else 'no'} |"
        )
    L.append("")

    # ---------------- episodes ----------------
    L.append("## Identity-episode catalog")
    L.append("")
    L.append(
        "Built with no expert event anywhere in its construction. Censored episodes "
        "are kept: a decline that never prints a durable low is the case that would "
        "otherwise silently disappear from every downstream count."
    )
    L.append("")
    if catalog is None or catalog.empty:
        L.append("_no episodes catalogued for this name_")
    else:
        L.append(
            "| type | tier | start | anchor | end | depth % | depth ATR | sessions | "
            "resolution | censored |"
        )
        L.append("|---|---:|---|---|---|---:|---:|---:|---|:--:|")
        for r in catalog.itertuples(index=False):
            L.append(
                f"| {r.episode_type} | {r.tier} | {_fmt_date(r.start_date)} | "
                f"{_fmt_date(r.anchor_date)} | {_fmt_date(r.end_date)} | "
                f"{100.0 * float(r.depth_pct):.1f} | {_fmt(float(r.depth_atr), 2)} | "
                f"{int(r.duration_sessions)} | {r.resolution} | "
                f"{'yes' if bool(r.censored) else 'no'} |"
            )
        L.append("")
        summ = ep_mod.summarize(catalog)
        L.append(
            f"**{summ['n_episodes']} episodes**, {summ['n_censored']} censored; "
            f"by type {summ['by_type']}; by tier {summ['by_tier']}."
        )
    L.append("")

    # ---------------- states ----------------
    L.append("## State shares by year")
    L.append("")
    L.append(
        "Eight mutually-exclusive bars-only states, first-match-wins precedence. "
        f"Gap basis on this plane: `{constants_meta.get('gap_basis', 'n/a')}` — a "
        "close-to-close proxy absorbs the whole session's move, not just the "
        "overnight jump, so cross-plane comparisons of the dislocation share carry "
        "that caveat."
    )
    L.append("")
    if state_shares is None or state_shares.empty:
        L.append("_no state history_")
    else:
        cols = [c for c in state_mod.STATES if c in state_shares.columns]
        L.append("| year | " + " | ".join(c.replace("_", " ") for c in cols) + " |")
        L.append("|---:|" + "---:|" * len(cols))
        for year, row in state_shares.iterrows():
            cells = " | ".join(f"{100.0 * float(row[c]):.0f}%" for c in cols)
            L.append(f"| {year} | {cells} |")
    L.append("")

    if chart_rel:
        L.append("## Episode map")
        L.append("")
        L.append(
            f"![{symbol} episode map]({chart_rel})"
        )
        L.append("")
        L.append(
            "Log price with the 200DMA, episode spans shaded by type, durable lows "
            "marked, and the daily state strip beneath."
        )
        L.append("")

    L.append("---")
    L.append("")
    L.append(
        f"Constants: `{constants_meta.get('constants_sha256', 'n/a')}` · "
        f"fingerprint spec: `{constants_meta.get('fingerprint_spec_hash', 'n/a')}` · "
        f"partition: `{constants_meta.get('partition_procedure_sha256', 'n/a')}` · "
        f"asof {constants_meta.get('asof', 'n/a')}"
    )
    L.append("")
    return "\n".join(L)


def render_chart(
    *,
    symbol: str,
    df: pd.DataFrame,
    states: pd.Series,
    catalog: pd.DataFrame,
    out_path: Path,
) -> Path:
    """Write the episode map. Returns the path actually written.

    SVG by default; a name whose vector output exceeds the size limit (very long
    histories with a dense state strip) falls back to PNG for that name only, so the
    repo never carries a multi-megabyte vector.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt

    # Collinear-point simplification and text-as-text keep a 60-year daily path from
    # serializing every one of its ~16,000 vertices at full precision.
    matplotlib.rcParams["path.simplify"] = True
    matplotlib.rcParams["path.simplify_threshold"] = 1.0
    matplotlib.rcParams["svg.fonttype"] = "none"

    close = df["close"].astype(float)
    sma200 = close.rolling(200, min_periods=200).mean()

    fig, (ax, ax_s) = plt.subplots(
        2, 1, figsize=(12.0, 6.4), sharex=True,
        gridspec_kw={"height_ratios": [7, 1], "hspace": 0.06},
    )

    for r in catalog.itertuples(index=False) if catalog is not None and not catalog.empty else []:
        color = _SPAN_COLORS.get(r.episode_type, "#dddddd")
        ax.axvspan(
            pd.Timestamp(r.start_date), pd.Timestamp(r.end_date),
            color=color, alpha=0.55 if not bool(r.censored) else 0.28,
            linewidth=0, zorder=0,
        )

    ax.plot(close.index, close.to_numpy(), color="#1b1b1b", linewidth=0.9, zorder=3, label="close")
    ax.plot(
        sma200.index, sma200.to_numpy(), color="#2f6f9f", linewidth=1.0,
        zorder=2, label="200DMA",
    )
    ax.set_yscale("log")

    if catalog is not None and not catalog.empty:
        lows = catalog[
            (catalog["episode_type"] == "reset_decline")
            & (catalog["resolution"] == "durable_low")
            & catalog["anchor_date"].notna()
        ]
        if len(lows):
            ax.scatter(
                [pd.Timestamp(d) for d in lows["anchor_date"]],
                [float(p) for p in lows["anchor_price"]],
                marker="v", s=42, color="#8b2f2f", zorder=5, label="durable low",
            )

    ax.set_title(
        f"{symbol} — identity-episode map (descriptive; zero authority)",
        fontsize=11, loc="left",
    )
    ax.grid(True, which="major", axis="y", alpha=0.18, linewidth=0.6)
    ax.set_ylabel("price (log)")
    handles = [
        mpatches.Patch(color=_SPAN_COLORS[t], label=t.replace("_", " "))
        for t in ep_mod.EPISODE_TYPES
    ]
    ax.legend(
        handles=handles + list(ax.get_legend_handles_labels()[0]),
        fontsize=7, loc="upper left", framealpha=0.85, ncol=3,
    )

    # State strip as RUN-LENGTH spans, not one marker per session. A per-session scatter
    # emits one SVG element per bar — ~12,000 of them on a deep name, which pushed the
    # vector past 2 MB and forced a raster fallback. Contiguous runs collapse that to a
    # few hundred rectangles with identical information.
    st = states.reindex(close.index).fillna("range")
    idx = close.index
    vals = st.to_numpy()
    if len(vals):
        run_start = 0
        for i in range(1, len(vals) + 1):
            if i == len(vals) or vals[i] != vals[run_start]:
                ax_s.axvspan(
                    idx[run_start], idx[min(i, len(idx) - 1)],
                    color=_STATE_COLORS.get(str(vals[run_start]), "#cccccc"),
                    linewidth=0,
                )
                run_start = i
    ax_s.set_xlim(idx[0], idx[-1])
    ax_s.set_ylim(0, 1)
    ax_s.set_yticks([])
    ax_s.set_ylabel("state", fontsize=8)
    ax_s.grid(False)
    for spine in ("top", "right", "left"):
        ax_s.spines[spine].set_visible(False)
    ax_s.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax_s.xaxis.set_major_formatter(mdates.ConciseDateFormatter(mdates.AutoDateLocator()))

    state_handles = [
        mpatches.Patch(color=c, label=s.replace("_", " ")) for s, c in _STATE_COLORS.items()
    ]
    ax_s.legend(handles=state_handles, fontsize=6, loc="upper center", ncol=8,
                bbox_to_anchor=(0.5, -0.35), framealpha=0.0)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="svg", bbox_inches="tight")
    plt.close(fig)

    if out_path.stat().st_size > _SVG_SIZE_LIMIT_BYTES:
        log.info(
            "%s: svg %d bytes exceeds the %d-byte commit limit — writing png instead",
            symbol, out_path.stat().st_size, _SVG_SIZE_LIMIT_BYTES,
        )
        out_path.unlink()
        return _render_raster(
            symbol=symbol, df=df, states=states, catalog=catalog,
            out_path=out_path.with_suffix(".png"),
        )
    return out_path


def _render_raster(
    *, symbol: str, df: pd.DataFrame, states: pd.Series, catalog: pd.DataFrame, out_path: Path
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt

    close = df["close"].astype(float)
    sma200 = close.rolling(200, min_periods=200).mean()
    fig, ax = plt.subplots(figsize=(12.0, 5.4))
    for r in catalog.itertuples(index=False) if catalog is not None and not catalog.empty else []:
        ax.axvspan(
            pd.Timestamp(r.start_date), pd.Timestamp(r.end_date),
            color=_SPAN_COLORS.get(r.episode_type, "#dddddd"),
            alpha=0.55 if not bool(r.censored) else 0.28, linewidth=0, zorder=0,
        )
    ax.plot(close.index, close.to_numpy(), color="#1b1b1b", linewidth=0.9, zorder=3)
    ax.plot(sma200.index, sma200.to_numpy(), color="#2f6f9f", linewidth=1.0, zorder=2)
    ax.set_yscale("log")
    ax.set_title(f"{symbol} — identity-episode map", fontsize=11, loc="left")
    ax.legend(
        handles=[
            mpatches.Patch(color=_SPAN_COLORS[t], label=t.replace("_", " "))
            for t in ep_mod.EPISODE_TYPES
        ],
        fontsize=7, loc="upper left", ncol=3,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return out_path


def write_dossier(
    *,
    symbol: str,
    out_dir: Path,
    markdown: str,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{symbol}.md"
    p.write_text(markdown, encoding="utf-8")
    return p
