"""Build the Oracle episode catalog (O2) — Tier S and/or Tier M.

Reads panel parquets from data/oracle/ (written by build_oracle_panel.py),
runs the hysteresis state machine over every node, and writes:

  data/oracle/episodes_s.parquet — Tier S episode catalog (sector ETFs, 1998→)
  data/oracle/episodes_m.parquet — Tier M episode catalog (subsectors+themes, 2021→)
  research/ORACLE_EPISODE_ATLAS.md  — auto-generated summary (--atlas flag)

IMPORTANT: This script runs ON THE MAC off the nightly render path.  It
consumes panel parquets that may live on R2; the --data-dir flag points it
at the Mac's canonical data/ store.

Usage
-----
  python scripts/build_oracle_episodes.py [--tier {s,m,all}]
                                           [--data-dir /path/to/data]
                                           [--atlas]

  --atlas   also write research/ORACLE_EPISODE_ATLAS.md (factual tables only)

Design notes
------------
* build_episodes() is a pure function in engine.oracle.episodes — this script
  is the I/O shell that loads panels, writes parquets, and dispatches the atlas.
* rotation_groups.json is consumed when present (P2a parallel PR); absent file
  degrades gracefully to node-level overlap pairing with a logged warning.
* No network calls; offline-safe.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import config  # noqa: E402
from engine.oracle.episodes import build_episodes, EPISODE_CFG  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# --data-dir override (same pattern as build_oracle_panel.py)
_DATA_DIR_OVERRIDE: Path | None = None


def _data_dir() -> Path:
    return _DATA_DIR_OVERRIDE if _DATA_DIR_OVERRIDE is not None else config.data_dir()


def _oracle_dir() -> Path:
    d = _data_dir() / "oracle"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_panel(tier: str) -> pd.DataFrame:
    path = _oracle_dir() / f"panel_{tier}.parquet"
    if not path.exists():
        log.error("Panel not found: %s — run build_oracle_panel.py first", path)
        return pd.DataFrame()
    log.info("Loading panel_%s (%s)...", tier, path)
    return pd.read_parquet(path)


def _load_rotation_groups() -> dict | None:
    """Load rotation_groups.json if present (P2a output).  Degrade gracefully."""
    rg_path = _oracle_dir() / "rotation_groups.json"
    if rg_path.exists():
        try:
            with open(rg_path) as f:
                groups = json.load(f)
            log.info("Loaded rotation_groups.json (%d groups)", len(groups))
            return groups
        except Exception as e:
            log.warning("rotation_groups.json load failed (%s) — using fallback pairing", e)
    else:
        log.info(
            "rotation_groups.json not found at %s — using same-panel overlap pairing "
            "(P2a parallel PR builds this; degrade is by design)", rg_path
        )
    return None


def _build_tier(tier: str, rotation_groups: dict | None) -> pd.DataFrame:
    panel = _load_panel(tier)
    if panel.empty:
        log.warning("Empty panel for tier=%s — skipping", tier)
        return pd.DataFrame()

    n_nodes = panel.index.get_level_values("node").nunique()
    n_rows = len(panel)
    dates = panel.index.get_level_values("date")
    log.info("Tier %s: %d nodes, %d rows, %s → %s",
             tier.upper(), n_nodes, n_rows, dates.min().date(), dates.max().date())

    episodes = build_episodes(panel, rotation_groups=rotation_groups, tier=tier)

    if episodes.empty:
        log.warning("No episodes detected for tier=%s", tier)
        return episodes

    log.info(
        "Tier %s: %d episodes detected (%d IN / %d OUT), %d two-sided",
        tier.upper(),
        len(episodes),
        (episodes["direction"] == "in").sum(),
        (episodes["direction"] == "out").sum(),
        (episodes["two_sided"] == True).sum(),  # noqa: E712 — NA-safe
    )

    out_path = _oracle_dir() / f"episodes_{tier}.parquet"
    episodes.to_parquet(out_path, index=False)
    log.info("Written: %s", out_path)

    return episodes


# ---------------------------------------------------------------------------
# Atlas generation
# ---------------------------------------------------------------------------

def _atlas_distribution_table(s: pd.Series, label: str) -> str:
    """Mini distribution summary table for the atlas."""
    if s.dropna().empty:
        return f"*{label}: no data*\n"
    desc = s.dropna().describe(percentiles=[0.10, 0.25, 0.50, 0.75, 0.90, 0.95])
    lines = [f"**{label}** (n={int(desc['count'])})",
             "| Stat | Value |",
             "|------|-------|"]
    for stat in ["min", "10%", "25%", "50%", "75%", "90%", "95%", "max"]:
        if stat in desc.index:
            lines.append(f"| {stat} | {desc[stat]:.3f} |")
    return "\n".join(lines) + "\n"


def _top20_table(df: pd.DataFrame) -> str:
    """Top-20 largest episodes by duration, with key fields."""
    if df.empty:
        return "*No episodes.*\n"
    cols_avail = [c for c in
                  ["node", "direction", "onset_date", "duration", "peak_accel_z",
                   "outcome_rs_63d", "outcome_mature_63d"]
                  if c in df.columns]
    top = df.nlargest(20, "duration")[cols_avail].copy()
    # Format dates
    if "onset_date" in top.columns:
        top["onset_date"] = top["onset_date"].dt.strftime("%Y-%m-%d")
    return top.to_markdown(index=False, floatfmt=".3f") + "\n"


def _two_sided_table(df: pd.DataFrame) -> str:
    """All two-sided episodes (paired IN/OUT rotations)."""
    ts = df[df["two_sided"] == True].copy()  # noqa: E712
    if ts.empty:
        return "*No two-sided episodes detected.*\n"
    cols_avail = [c for c in
                  ["node", "direction", "onset_date", "duration", "paired_episode_id"]
                  if c in ts.columns]
    if "onset_date" in ts.columns:
        ts = ts.copy()
        ts["onset_date"] = ts["onset_date"].dt.strftime("%Y-%m-%d")
    return ts[cols_avail].to_markdown(index=False) + "\n"


def _write_atlas(eps_s: pd.DataFrame, eps_m: pd.DataFrame, manifest_s: dict | None, manifest_m: dict | None) -> Path:
    """Write research/ORACLE_EPISODE_ATLAS.md."""
    atlas_path = ROOT / "research" / "ORACLE_EPISODE_ATLAS.md"

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Oracle Episode Atlas",
        "",
        f"*Auto-generated by `scripts/build_oracle_episodes.py` — {now_str}.*",
        "*Factual tables only — no narrative claims.  Validated edges live in the Phase-3 gauntlet.*",
        "",
        "---",
        "",
        "## Honesty header",
        "",
        "| Item | Value |",
        "|------|-------|",
    ]

    # Survivorship watermark
    m_flag = "YES — Tier-M membership = 2026-06 snapshot; historical composition approximated"
    s_flag = "NO — Tier-S uses real ETF prices + PIT-SP1500 membership"
    lines.append(f"| Tier-M survivorship watermark | {m_flag} |")
    lines.append(f"| Tier-S survivorship watermark | {s_flag} |")
    lines.append(f"| Tier-S label caveat | GICS labels applied backward (current→history) — "
                 f"affects member legs, not ETF-level RS/velocity |")
    lines.append(f"| Episode detection | Hysteresis state machine with 5d accel_z smoothing "
                 f"(see EPISODE_CFG in engine/oracle/episodes.py) |")
    lines.append(f"| Outcomes | Forward RS only; NaN + outcome_mature=False when window extends past last panel date |")
    lines.append("")

    # Tier S summary
    lines += [
        "---",
        "",
        "## Tier S — Sector ETFs (1998 → 2026, survivorship-CLEAN)",
        "",
    ]
    if eps_s.empty:
        lines.append("*No episodes detected for Tier S.*")
    else:
        n_in = (eps_s["direction"] == "in").sum()
        n_out = (eps_s["direction"] == "out").sum()
        pairing_unavailable = bool(eps_s.get("pairing_unavailable", pd.Series(dtype=bool)).any())
        n_2s = (eps_s["two_sided"] == True).sum()  # noqa: E712 — NA-safe
        n_confirmed = eps_s["confirmed_date"].notna().sum()
        n_undeniable = eps_s["undeniable_date"].notna().sum()
        n_exhausted = eps_s["exhausted_date"].notna().sum()
        lines += [
            f"**Episodes:** {len(eps_s)} total ({n_in} IN / {n_out} OUT)",
            (f"**Two-sided pairs:** UNAVAILABLE — rotation_groups.json absent/unparseable; "
             f"pairing requires the complex backbone (no relationship-free fallback)"
             if pairing_unavailable else f"**Two-sided pairs:** {n_2s}"),
            f"**Tier breakdown:** onset={len(eps_s)}, confirmed={n_confirmed}, "
            f"undeniable={n_undeniable}, exhausted={n_exhausted} (open={len(eps_s)-n_exhausted})",
            "",
            _atlas_distribution_table(eps_s["duration"], "Episode duration (sessions)"),
            "",
            _atlas_distribution_table(eps_s["peak_accel_z"], "Peak |accel_z|"),
            "",
        ]
        if "outcome_rs_63d" in eps_s.columns:
            lines.append(_atlas_distribution_table(
                eps_s.loc[eps_s.get("outcome_mature_63d", False) == True, "outcome_rs_63d"],
                "Outcome: +63d RS-change (mature episodes only)"
            ))
            lines.append("")

        lines += ["### Top 20 episodes by duration (Tier S)", ""]
        lines.append(_top20_table(eps_s))
        lines += ["### Two-sided episodes (Tier S)", ""]
        lines.append(_two_sided_table(eps_s))

    # Tier M summary
    lines += [
        "---",
        "",
        "## Tier M — Subsectors + Themes + Baskets (2021 → 2026, survivorship-FLAGGED)",
        "",
        "> **SURVIVORSHIP WARNING:** Tier-M membership reflects the 2026-06 snapshot of",
        "> `themes_tree.json`.  Historical member composition is approximated.  All pattern",
        "> claims on Tier-M nodes are DECLARED HINDSIGHT until Tier-L accrual matures them.",
        "",
    ]
    if eps_m.empty:
        lines.append("*No episodes detected for Tier M.*")
    else:
        n_in = (eps_m["direction"] == "in").sum()
        n_out = (eps_m["direction"] == "out").sum()
        n_2s = eps_m["two_sided"].sum()
        n_confirmed = eps_m["confirmed_date"].notna().sum()
        n_undeniable = eps_m["undeniable_date"].notna().sum()
        n_exhausted = eps_m["exhausted_date"].notna().sum()
        lines += [
            f"**Episodes:** {len(eps_m)} total ({n_in} IN / {n_out} OUT)",
            (f"**Two-sided pairs:** UNAVAILABLE — rotation_groups.json absent/unparseable; "
             f"pairing requires the complex backbone (no relationship-free fallback)"
             if pairing_unavailable else f"**Two-sided pairs:** {n_2s}"),
            f"**Tier breakdown:** onset={len(eps_m)}, confirmed={n_confirmed}, "
            f"undeniable={n_undeniable}, exhausted={n_exhausted} (open={len(eps_m)-n_exhausted})",
            "",
            _atlas_distribution_table(eps_m["duration"], "Episode duration (sessions)"),
            "",
            _atlas_distribution_table(eps_m["peak_accel_z"], "Peak |accel_z|"),
            "",
        ]
        if "outcome_rs_63d" in eps_m.columns:
            mature_mask = eps_m.get("outcome_mature_63d", pd.Series(False, index=eps_m.index)) == True  # noqa: E712
            lines.append(_atlas_distribution_table(
                eps_m.loc[mature_mask, "outcome_rs_63d"],
                "Outcome: +63d RS-change (mature episodes only)"
            ))
            lines.append("")

        lines += ["### Top 20 episodes by duration (Tier M)", ""]
        lines.append(_top20_table(eps_m))
        lines += ["### Two-sided episodes (Tier M)", ""]
        lines.append(_two_sided_table(eps_m))

    # EPISODE_CFG snapshot
    lines += [
        "---",
        "",
        "## Detection parameters (EPISODE_CFG snapshot)",
        "",
        "| Parameter | Value | Provenance |",
        "|-----------|-------|------------|",
    ]
    provenance = {
        "accel_z_smooth_days": "accel_z raw median run = 2d; 5d suppresses noise",
        "onset_accel_z_threshold": "panel_s q87 of accel_z ≈ 1.0",
        "onset_positive_days_in_5": "majority-positive 5d window",
        "confirmed_consecutive_onset_days": "mirrors smoothing window",
        "confirmed_cohesion_chg_threshold": "panel_m cohesion_chg q75 = 0.056",
        "undeniable_rs_in_direction": "RS must flip sign in onset direction",
        "undeniable_breadth_threshold": "breadth_50 q50 ≈ 0.53 → threshold 0.50",
        "mature_rs_pctile_threshold": "q80 of trailing 252d rank = 0.80",
        "mature_fading_accel_z_threshold": "below ~q75/1.2 ≈ 0.50",
        "exhausted_accel_z_counter_threshold": "counter-directional band",
        "exhausted_days_in_5": "3-of-5 confirmation",
        "hysteresis_gap_days": "one trading week re-arm gap",
        "min_duration_before_exhaustion": "prevents zero-length episodes",
        "outcome_horizons": "5/21/63d = weekly/monthly/quarterly",
        "two_sided_min_overlap_sessions": "≥5 session co-movement",
    }
    for k, v in EPISODE_CFG.items():
        prov = provenance.get(k, "see EPISODE_CFG docstring")
        lines.append(f"| `{k}` | {v} | {prov} |")

    lines += [""]

    atlas_path.parent.mkdir(parents=True, exist_ok=True)
    atlas_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("Atlas written: %s", atlas_path)
    return atlas_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build Oracle episode catalog (O2)")
    p.add_argument("--tier", choices=["s", "m", "f", "all"], default="all")
    p.add_argument("--data-dir", type=Path, help="Override data directory (default: lib.config)")
    p.add_argument("--atlas", action="store_true", help="Also write ORACLE_EPISODE_ATLAS.md")
    return p.parse_args()


def main() -> None:
    global _DATA_DIR_OVERRIDE
    args = _parse_args()

    if args.data_dir:
        _DATA_DIR_OVERRIDE = args.data_dir
        log.info("Data dir override: %s", _DATA_DIR_OVERRIDE)

    rotation_groups = _load_rotation_groups()

    eps_s = pd.DataFrame()
    eps_m = pd.DataFrame()

    if args.tier in ("s", "all"):
        eps_s = _build_tier("s", rotation_groups)

    if args.tier in ("m", "all"):
        eps_m = _build_tier("m", rotation_groups)

    if args.tier in ("f", "all"):
        _build_tier("f", rotation_groups)

    if args.atlas:
        # Load manifest if available (for survivorship watermark)
        manifest_path = _oracle_dir() / "manifest.json"
        manifest = None
        if manifest_path.exists():
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
            except Exception:
                pass

        _write_atlas(
            eps_s,
            eps_m,
            manifest_s=manifest.get("tier_s") if manifest else None,
            manifest_m=manifest.get("tier_m") if manifest else None,
        )

    log.info("Done.")


if __name__ == "__main__":
    main()
