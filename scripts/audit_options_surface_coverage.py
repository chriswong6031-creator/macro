"""Coverage audit for the W2 SURFACE builder roster.

Reads the T1 ThetaData EOD store (greeks + oi tiers) and prints, per roster root:
  - first/last greeks date
  - per-year row counts (greeks rows + oi rows)
  - PASS/FAIL against the coverage floor:
      greeks AND oi present for 2017 → current year (inclusive)
      QQQ may go back further (2012+) — still PASS
      SPXW may start later — report honestly

The roster FREEZES to passing roots. Output is committed as
reports/artifacts/options_surface_coverage.md.

Usage:
    python -m scripts.audit_options_surface_coverage [--store /path/to/store]
    python -m scripts.audit_options_surface_coverage --markdown > /tmp/out.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Candidate roster (masterplan §3 P2 Layer 2 / research/RATES_INFLATION…)
# ---------------------------------------------------------------------------
CANDIDATE_ROSTER: list[str] = [
    "SPX", "SPXW",                              # index native
    "SPY", "QQQ", "IWM", "DIA",                 # broad index ETFs
    "XLB", "XLC", "XLE", "XLF", "XLI",          # SPDR sector ETFs
    "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",  # SPDR sector ETFs (cont.)
    "SMH", "XBI", "KRE",                         # industry ETFs
]

# Minimum year for coverage PASS.  QQQ can start earlier (2012); SPXW may
# start later — we accept the actual start year for those two.
MIN_YEAR = 2017
CURRENT_YEAR = date.today().year

# Roots whose early start year is below MIN_YEAR but still acceptable.
# These pass as long as they have ≥MIN_YEAR → CURRENT_YEAR coverage.
EARLY_OK_ROOTS: set[str] = {"QQQ"}

# Roots allowed to start AFTER MIN_YEAR (start year is reported honestly).
LATE_START_ALLOWED: set[str] = {"SPXW", "XLC"}  # XLC launched 2018-06-18; complete from listing

# ── ops-wt store fallback path (same constant as engine/thetadata_store.py) ─
_OPS_WT_STORE = Path("/Users/chriswong/theta-ops-wt/data/thetadata_eod")


def _resolve_store(override: str | None = None) -> Path:
    """Resolve the T1 store, mirroring engine/thetadata_store.resolve_thetadata_store."""
    if override:
        return Path(override)
    env = os.environ.get("THETADATA_STORE")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from lib import config  # noqa: PLC0415
        p = config.data_dir() / "thetadata_eod"
        if p.is_dir() and any((p / t).is_dir() for t in ("eod", "oi", "greeks")):
            return p
    except Exception:  # noqa: BLE001
        pass
    if _OPS_WT_STORE.is_dir():
        return _OPS_WT_STORE
    raise RuntimeError(
        f"T1 store not found. Set THETADATA_STORE or use --store. "
        f"Tried: {_OPS_WT_STORE}"
    )


def _year_counts(tier_root: Path) -> dict[int, int]:
    """Map year → row count for one (tier, root) directory."""
    if not tier_root.exists():
        return {}
    counts: dict[int, int] = {}
    for f in sorted(tier_root.glob("*.parquet")):
        try:
            year = int(f.stem)
        except ValueError:
            continue
        try:
            import pandas as pd  # noqa: PLC0415
            df = pd.read_parquet(f, columns=["date"])
            counts[year] = len(df)
        except Exception:  # noqa: BLE001
            counts[year] = -1   # unreadable
    return counts


def _greeks_date_range(tier_root: Path) -> tuple[str | None, str | None]:
    """First and last date with non-null implied_vol in the greeks tier."""
    if not tier_root.exists():
        return None, None
    try:
        import pandas as pd  # noqa: PLC0415
        frames = []
        for f in sorted(tier_root.glob("*.parquet")):
            try:
                df = pd.read_parquet(f, columns=["date", "implied_vol"])
                df = df[df["implied_vol"].notna() & (df["implied_vol"] > 0)]
                if not df.empty:
                    frames.append(df[["date"]])
            except Exception:  # noqa: BLE001
                continue
        if not frames:
            return None, None
        all_dates = pd.concat(frames)["date"]
        all_dates = pd.to_datetime(all_dates).dt.date
        return str(all_dates.min()), str(all_dates.max())
    except Exception:  # noqa: BLE001
        return None, None


def _assess(root: str, greeks_counts: dict[int, int], oi_counts: dict[int, int]) -> str:
    """Return 'PASS' or 'FAIL' with a reason string."""
    if not greeks_counts and not oi_counts:
        return "FAIL — root absent from both greeks and oi tiers"
    if not greeks_counts:
        return "FAIL — greeks tier absent"
    if not oi_counts:
        return "FAIL — oi tier absent"

    # Determine the effective minimum year (SPXW: use its actual start; others: MIN_YEAR)
    if root in LATE_START_ALLOWED:
        effective_min = min(greeks_counts) if greeks_counts else MIN_YEAR
    else:
        effective_min = MIN_YEAR

    missing_greeks = [y for y in range(effective_min, CURRENT_YEAR + 1)
                      if greeks_counts.get(y, 0) <= 0]
    missing_oi = [y for y in range(effective_min, CURRENT_YEAR + 1)
                  if oi_counts.get(y, 0) <= 0]

    if missing_greeks and missing_oi:
        return f"FAIL — missing greeks+oi for years: {missing_greeks + missing_oi}"
    if missing_greeks:
        return f"FAIL — missing greeks for years: {missing_greeks}"
    if missing_oi:
        return f"FAIL — missing oi for years: {missing_oi}"

    # QQQ going back further than MIN_YEAR is fine
    start = min(greeks_counts) if greeks_counts else effective_min
    if root in LATE_START_ALLOWED and start > MIN_YEAR:
        return f"PASS (greeks start {start} — later start accepted for {root})"
    return "PASS"


def run_audit(store_path: Path) -> dict:
    """Run the coverage audit and return a structured result dict."""
    results: dict[str, dict] = {}

    for root in CANDIDATE_ROSTER:
        greeks_dir = store_path / "greeks" / root
        oi_dir = store_path / "oi" / root

        greeks_counts = _year_counts(greeks_dir)
        oi_counts = _year_counts(oi_dir)
        first_date, last_date = _greeks_date_range(greeks_dir)

        verdict = _assess(root, greeks_counts, oi_counts)

        results[root] = {
            "verdict": verdict,
            "greeks_first": first_date,
            "greeks_last": last_date,
            "greeks_years": greeks_counts,
            "oi_years": oi_counts,
        }

    return results


def _render_markdown(results: dict, store_path: Path, run_at: str) -> str:
    lines = [
        "# Options Surface Coverage Audit — W2 SURFACE",
        "",
        f"**Generated:** {run_at}  ",
        f"**Store:** `{store_path}`  ",
        f"**Coverage floor:** greeks + oi present {MIN_YEAR}→{CURRENT_YEAR} (inclusive)  ",
        f"**Roster size:** {len(CANDIDATE_ROSTER)} candidates",
        "",
        "## Roster Assessment",
        "",
        "| Root | Verdict | Greeks first | Greeks last | Years (G+OI) |",
        "|------|---------|-------------|-------------|-------------|",
    ]

    passing: list[str] = []
    failing: list[str] = []

    for root, info in results.items():
        v = info["verdict"]
        gf = info["greeks_first"] or "—"
        gl = info["greeks_last"] or "—"
        gy = sorted(info["greeks_years"].keys())
        oy = sorted(info["oi_years"].keys())
        # Compact year summary: greeks years + oi years
        gy_str = f"G:{gy[0]}–{gy[-1]}" if gy else "G:—"
        oy_str = f"OI:{oy[0]}–{oy[-1]}" if oy else "OI:—"
        lines.append(f"| {root} | {v} | {gf} | {gl} | {gy_str} {oy_str} |")
        if v.startswith("PASS"):
            passing.append(root)
        else:
            failing.append(root)

    lines.extend([
        "",
        "## Per-Root Row Counts",
        "",
    ])

    for root, info in results.items():
        lines.append(f"### {root} — {info['verdict']}")
        lines.append("")
        gy = info["greeks_years"]
        oy = info["oi_years"]
        all_years = sorted(set(list(gy.keys()) + list(oy.keys())))
        if all_years:
            lines.append(f"| Year | Greeks rows | OI rows |")
            lines.append(f"|------|------------|---------|")
            for yr in all_years:
                g_cnt = gy.get(yr, "—")
                o_cnt = oy.get(yr, "—")
                lines.append(f"| {yr} | {g_cnt} | {o_cnt} |")
        else:
            lines.append("_(no data)_")
        lines.append("")

    lines.extend([
        "## Frozen Roster",
        "",
        f"Passing roots ({len(passing)}): " + ", ".join(passing),
        "",
        f"Failing roots ({len(failing)}): " + (", ".join(failing) if failing else "none"),
        "",
        "The builder constant `SURFACE_ROSTER` in `scripts/build_options_surface.py` "
        "is initialized from the passing set above.  Audit date: "
        f"`{run_at[:10]}`.",
        "",
    ])

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", help="Override T1 store path")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    ap.add_argument("--markdown", action="store_true", help="Print markdown to stdout")
    args = ap.parse_args()

    try:
        store = _resolve_store(args.store)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"Auditing T1 store: {store}", file=sys.stderr)

    results = run_audit(store)
    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if args.json:
        print(json.dumps({"run_at": run_at, "store": str(store), "results": results}, indent=2))
        return 0

    md = _render_markdown(results, store, run_at)

    # Always write to reports/artifacts/
    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / "reports" / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "options_surface_coverage.md"
    out_path.write_text(md)
    print(f"Coverage audit written to: {out_path}", file=sys.stderr)

    # Summary to stdout
    passing = [r for r, i in results.items() if i["verdict"].startswith("PASS")]
    failing = [r for r, i in results.items() if not i["verdict"].startswith("PASS")]
    print(f"PASS ({len(passing)}): {', '.join(passing)}")
    print(f"FAIL ({len(failing)}): {', '.join(failing) if failing else 'none'}")

    if args.markdown:
        print(md)

    # Return 0 even if some roots fail — audit is informational, not a gate blocker.
    # The builder's SURFACE_ROSTER freezes to the passing set.
    return 0


if __name__ == "__main__":
    sys.exit(main())
