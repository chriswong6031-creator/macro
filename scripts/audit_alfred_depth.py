"""Audit FRED/ALFRED point-in-time (PIT) vintage depth for the base-effect / nowcast series.

The base-effect forward-regime kernel (see research/HEDGEYE_UPGRADE_MASTER_PLAN.md, Section A)
is only *honest* on point-in-time vintage data — using today's revised PAYEMS/INDPRO/CPI back-
populates knowledge the market did not have at the time. Before a line of engine/base_effect.py
is written, we need to know which of the series it consumes actually have usable vintage depth in
data/fred_vintage/vintages.parquet, which are shallow, and which are absent entirely (and must
fall back to latest-revision with an explicit revised=True flag).

This is a read-only audit of the local vintage store. Pass --probe-missing to additionally hit
the ALFRED API (needs FRED_API_KEY) and report whether absent series are fetchable so we can
decide on a backfill.

Usage:
    python -m scripts.audit_alfred_depth
    python -m scripts.audit_alfred_depth --series CPIAUCSL,PCEPILFE --probe-missing
    python -m scripts.audit_alfred_depth --output data/fred_vintage/alfred_depth_audit.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.fred import load_vintages  # noqa: E402
from lib import config  # noqa: E402

# The series the base-effect / DFM / recession-nowcast legs read (Section A.1/A.2 of the plan).
# Grouped so the summary can speak to what each engine leg can/can't do point-in-time.
BASE_EFFECT_SERIES = {
    # core inflation levels the base-effect kernel differences into YoY (the Fed's target set)
    "CPIAUCSL": "headline CPI level (base-effect inflation)",
    "CPILFESL": "core CPI level (base-effect inflation)",
    "PCEPILFE": "core PCE level (base-effect inflation — the Fed's target)",
    "PPIFIS": "PPI final demand (base-effect inflation, optional)",
    "STICKCPIM157SFRBATL": "Atlanta sticky CPI (persistent-inflation direction)",
    "FLEXCPIM157SFRBATL": "Atlanta flexible CPI",
    # growth levels
    "INDPRO": "industrial production level (base-effect growth)",
    "PAYEMS": "nonfarm payrolls level (base-effect growth)",
    "WEI": "Weekly Economic Index (growth nowcast)",
    "GDPNOW": "Atlanta Fed GDPNow (growth nowcast)",
    # recession / labor nowcast
    "ICSA": "initial jobless claims (labor nowcast)",
    "SAHMREALTIME": "real-time Sahm rule (recession nowcast)",
    "RECPROUSM156N": "NY Fed recession probability",
}

# first-vintage cutoffs for the verdict — a base-effect signal needs several non-overlapping
# comparison cycles to validate its disclosed inversion stat, so pre-2010 is "OK", 2010-2015
# is "THIN", post-2015 is "SHALLOW" (<~2 recessions of PIT history).
_OK_BEFORE = pd.Timestamp("2010-01-01")
_THIN_BEFORE = pd.Timestamp("2015-01-01")


def _verdict(present: bool, earliest: pd.Timestamp | None) -> str:
    if not present or earliest is None:
        return "ABSENT"
    if earliest < _OK_BEFORE:
        return "OK"
    if earliest < _THIN_BEFORE:
        return "THIN"
    return "SHALLOW"


def audit(series: dict[str, str], vintages: pd.DataFrame | None) -> list[dict]:
    rows: list[dict] = []
    for sid, role in series.items():
        if vintages is None:
            rows.append({"series": sid, "role": role, "present": False,
                         "earliest_vintage": None, "latest_vintage": None,
                         "n_vintages": 0, "n_periods": 0, "verdict": "ABSENT"})
            continue
        sub = vintages[vintages["series"] == sid]
        if sub.empty:
            rows.append({"series": sid, "role": role, "present": False,
                         "earliest_vintage": None, "latest_vintage": None,
                         "n_vintages": 0, "n_periods": 0, "verdict": "ABSENT"})
            continue
        earliest = sub["realtime_start"].min()
        latest = sub["realtime_start"].max()
        rows.append({
            "series": sid, "role": role, "present": True,
            "earliest_vintage": earliest.date().isoformat(),
            "latest_vintage": latest.date().isoformat(),
            "n_vintages": int(sub["realtime_start"].nunique()),
            "n_periods": int(sub["period"].nunique()),
            "verdict": _verdict(True, earliest),
        })
    return rows


def probe_alfred(sids: list[str]) -> dict[str, dict]:
    """Hit the ALFRED API for series absent from the store, to confirm they are fetchable and
    report the earliest available realtime (vintage) date, so a backfill decision is informed."""
    out: dict[str, dict] = {}
    try:
        from collectors.fred import FredAdapter
        adapter = FredAdapter()
    except Exception as e:  # pragma: no cover - environment dependent
        return {s: {"error": f"adapter init failed: {e}"} for s in sids}
    if not config.secret("FRED_API_KEY"):
        return {s: {"error": "FRED_API_KEY not set"} for s in sids}
    for sid in sids:
        try:
            df = adapter._fetch_vintage_one(sid, adapter.cfg.get("vintage_realtime_start", "1997-01-01"))
            if df is None or df.empty:
                out[sid] = {"fetchable": False, "note": "ALFRED returned no rows"}
            else:
                out[sid] = {
                    "fetchable": True,
                    "earliest_vintage": pd.to_datetime(df["realtime_start"]).min().date().isoformat(),
                    "n_rows": int(len(df)),
                }
        except Exception as e:
            out[sid] = {"fetchable": False, "error": str(e)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--series", default=None, help="comma-separated series to audit (default: the base-effect set)")
    ap.add_argument("--probe-missing", action="store_true", help="hit ALFRED for absent series (needs FRED_API_KEY)")
    ap.add_argument("--output", default=None, help="write the audit JSON here (default: stdout table only)")
    args = ap.parse_args()

    if args.series:
        series = {s.strip(): "(custom)" for s in args.series.split(",") if s.strip()}
    else:
        series = BASE_EFFECT_SERIES

    vintages = load_vintages()
    if vintages is None:
        print("WARNING: vintage store not found at data/fred_vintage/vintages.parquet — every series ABSENT",
              file=sys.stderr)
    else:
        print(f"loaded vintage store: {len(vintages):,} rows, {vintages['series'].nunique()} series",
              file=sys.stderr)

    rows = audit(series, vintages)

    # human-readable table to stderr so stdout stays clean for JSON piping
    w = max(len(r["series"]) for r in rows)
    print("\n{:<{w}}  {:<8}  {:<12}  {:>9}  {}".format("SERIES", "VERDICT", "EARLIEST", "N_VINT", "ROLE", w=w),
          file=sys.stderr)
    print("-" * (w + 60), file=sys.stderr)
    for r in rows:
        print("{:<{w}}  {:<8}  {:<12}  {:>9}  {}".format(
            r["series"], r["verdict"], r["earliest_vintage"] or "-", r["n_vintages"], r["role"], w=w),
            file=sys.stderr)

    absent = [r["series"] for r in rows if r["verdict"] == "ABSENT"]
    shallow = [r["series"] for r in rows if r["verdict"] in ("SHALLOW", "THIN")]
    ok = [r["series"] for r in rows if r["verdict"] == "OK"]

    print("\nSUMMARY:", file=sys.stderr)
    print(f"  PIT-OK (pre-2010 vintages): {', '.join(ok) or 'none'}", file=sys.stderr)
    print(f"  THIN/SHALLOW (post-2010):   {', '.join(shallow) or 'none'}", file=sys.stderr)
    print(f"  ABSENT (no PIT path today): {', '.join(absent) or 'none'}", file=sys.stderr)
    print("\n  => base-effect legs on ABSENT series must fall back to latest-revision with revised=True;",
          file=sys.stderr)
    print("     THIN/SHALLOW legs can be PIT but validate on <2 cycles (small-sample caveat).", file=sys.stderr)

    probe = {}
    if args.probe_missing and absent:
        print(f"\nprobing ALFRED for {len(absent)} absent series...", file=sys.stderr)
        probe = probe_alfred(absent)
        for sid, info in probe.items():
            print(f"  {sid}: {info}", file=sys.stderr)

    report = {
        "generated_utc": pd.Timestamp.now("UTC").isoformat(),
        "store_rows": int(len(vintages)) if vintages is not None else 0,
        "store_series": int(vintages["series"].nunique()) if vintages is not None else 0,
        "rows": rows,
        "summary": {"ok": ok, "thin_or_shallow": shallow, "absent": absent},
        "alfred_probe": probe,
        "note": ("Base-effect on ABSENT series (notably core PCE/CPI) has no point-in-time path in "
                 "the local store today; route those latest-revision with revised=True (the base "
                 "period is a settled historical print, so a deterministic base signal is still "
                 "defensible) and label them in the UI. See plan §2 S3."),
    }
    payload = json.dumps(report, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(payload)
        print(f"\nwrote {args.output}", file=sys.stderr)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
