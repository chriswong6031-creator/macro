"""scripts/report_importance_duel.py — the champion-challenger-placebo scoreboard
(W3, spec D6 / §4 W3 measurement plumbing).

The artifact the integrator runs to read the duel. It reads the SAME ledger the
nightly grader writes (data/qledger/claims.jsonl + grades.jsonl) and prints, per
horizon (5 / 21 / 63d), the mean forward |excess| and honest n_dates of three
tapes side by side:

    CHAMPION  — the hand importance formula's bands
                (family "china_news", extra.importance_band HIGH / LOW).
    CHALLENGER— the novelty-first v0 bands, per lane
                (family "us_importance_v0" / "cn_importance_v0", extra.band
                HIGH / LOW).
    PLACEBO   — the null tape (is_placebo=True), overall |excess|.

The question the scoreboard answers (D6 kill criterion): does either importance
formula's HIGH band move MORE (larger |excess|) than its LOW band AND more than
the placebo null? The CURRENT SCOREBOARD FACT the challenger targets: at 5d, the
hand china_news HIGH band |excess| (6.30%) is indistinguishable from placebo
(6.17%) — a coin flip dressed as a signal. A challenger earns its keep only by
opening a gap the champion cannot.

|excess| is the salience magnitude metric (direction=0 claims have no hit-rate —
§2.3), matching qledger._placebo_magnitude. n_dates is the honest independent-date
count (qledger._date_cluster / [P1]) — NOT the overlapping-observation count — so
a spread that looks significant on n_obs but rests on 3 dates is exposed as such.

READ-ONLY. Writes nothing to the ledger. Optionally emits JSON for the integrator
to diff across nights.

Usage:
    python scripts/report_importance_duel.py [--root PATH] [--json]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine import qledger as q  # noqa: E402

# The three tapes and how each names its HIGH/LOW band in the claim's extra{}.
_CHAMPION_FAMILY = "china_news"
_CHAMPION_BAND_KEY = "importance_band"
# The W4 PIT-correct challenger families are the primary duel tapes.
# The W3 biased families (without "_pit") are included for comparison so the
# integrator can see how much the echo_stats look-ahead / tz-mixed NaT bugs
# inflated scores.
_CHALLENGER_FAMILIES = (
    "us_importance_v0_pit",   # W4 PIT-correct (primary)
    "cn_importance_v0_pit",   # W4 PIT-correct (primary)
    "us_importance_v0",       # W3 biased (look-ahead echo_stats) — audit only
    "cn_importance_v0",       # W3 biased (tz-mixed NaT + look-ahead) — audit only
)
_CHALLENGER_BAND_KEY = "band"


def _band_of(claim: dict) -> str | None:
    """The HIGH/LOW band tag for a claim, reading whichever key its family uses.
    Normalises case so 'High'/'HIGH' collapse. None when untagged."""
    fam = claim.get("claim_family")
    key = _CHALLENGER_BAND_KEY if fam in _CHALLENGER_FAMILIES else _CHAMPION_BAND_KEY
    v = claim.get(key)
    if v is None:
        return None
    v = str(v).upper()
    return v if v in ("HIGH", "LOW") else None


def _slice_stats(claims: list[dict], grades: list[dict],
                 family: str, band: str | None, horizon_d: int,
                 placebo: bool = False) -> dict:
    """Mean |excess| + honest n_dates for one (family, band, horizon) slice.

    band=None with placebo=True selects the placebo null (any family, is_placebo).
    Otherwise selects non-placebo claims of `family` whose band tag == `band`.
    """
    cid_meta = {c["claim_id"]: c for c in claims if c.get("claim_id")}

    abs_sum = 0.0
    n_obs = 0
    dates: set[str] = set()
    for g in grades:
        if int(g.get("horizon_d", -1)) != horizon_d:
            continue
        c = cid_meta.get(g.get("claim_id"))
        if c is None:
            continue
        if placebo:
            if not c.get("is_placebo"):
                continue
        else:
            if c.get("is_placebo"):
                continue
            if c.get("claim_family") != family:
                continue
            if _band_of(c) != band:
                continue
        exc = g.get("excess")
        if exc is None:
            continue
        abs_sum += abs(float(exc))
        n_obs += 1
        dates.add(q._date_cluster(c.get("asof")))

    n_dates = len(dates)
    return {
        "mean_abs_excess": round(abs_sum / n_obs, 6) if n_obs else None,
        "n_obs": n_obs,
        "n_dates": n_dates,
        "state": q.derive_state(n_dates),
    }


def build_report(root: Path | str | None = None) -> dict:
    """Assemble the full duel payload from the ledger. Pure/read-only.

    The report includes BOTH the W3 biased families (us/cn_importance_v0) and the
    W4 PIT-correct families (us/cn_importance_v0_pit) so the integrator can
    measure the look-ahead bias quantitatively: the gap between the biased and
    pit-correct HIGH band |excess| is the artefact of the W3 bugs.
    """
    root = Path(root) if root else _ROOT
    claims = q.load_claims(root)
    grades = q.load_grades(root)

    out: dict = {"grade_horizons": list(q.GRADE_HORIZONS), "by_horizon": {}}
    for h in q.GRADE_HORIZONS:
        row: dict = {}
        # champion — hand china_news bands
        row["champion_china_news"] = {
            "HIGH": _slice_stats(claims, grades, _CHAMPION_FAMILY, "HIGH", h),
            "LOW": _slice_stats(claims, grades, _CHAMPION_FAMILY, "LOW", h),
        }
        # challenger — v0 bands per lane (both W3 biased and W4 PIT-correct)
        for fam in _CHALLENGER_FAMILIES:
            row[f"challenger_{fam}"] = {
                "HIGH": _slice_stats(claims, grades, fam, "HIGH", h),
                "LOW": _slice_stats(claims, grades, fam, "LOW", h),
            }
        # placebo null
        row["placebo"] = _slice_stats(claims, grades, "", None, h, placebo=True)
        out["by_horizon"][str(h)] = row
    return out


def _fmt_pct(v) -> str:
    return f"{v * 100:6.2f}%" if isinstance(v, (int, float)) else "   n/a"


def _print_report(rep: dict) -> None:
    print("=" * 86)
    print("IMPORTANCE DUEL — champion (hand) vs challenger (novelty-v0) vs placebo")
    print("_pit = W4 PIT-correct (asof-filtered echo_stats + utc=True tz parse)")
    print("metric: mean |forward excess vs bench|  ·  n = honest independent dates")
    print("=" * 86)
    _tape_rows = [
        ("CHAMPION hand china_news",          "champion_china_news"),
        ("CHALLENGER us_v0_pit [W4]",         "challenger_us_importance_v0_pit"),
        ("CHALLENGER cn_v0_pit [W4]",         "challenger_cn_importance_v0_pit"),
        ("CHALLENGER us_v0 [W3 biased]",      "challenger_us_importance_v0"),
        ("CHALLENGER cn_v0 [W3 biased]",      "challenger_cn_importance_v0"),
    ]
    _verdict_tapes = [
        ("hand",        "champion_china_news"),
        ("v0-US-pit",   "challenger_us_importance_v0_pit"),
        ("v0-CN-pit",   "challenger_cn_importance_v0_pit"),
        ("v0-US-biased","challenger_us_importance_v0"),
        ("v0-CN-biased","challenger_cn_importance_v0"),
    ]
    for h in rep["grade_horizons"]:
        block = rep["by_horizon"].get(str(h))
        if not block:
            continue
        print(f"\n── horizon {h}d " + "─" * 70)
        header = f"  {'tape':<34} {'HIGH |excess|':>14} {'LOW |excess|':>14} "
        print(header + f"{'HIGH n_dates':>12}")
        for label, key in _tape_rows:
            slc = block.get(key, {})
            hi = slc.get("HIGH", {})
            lo = slc.get("LOW", {})
            print(f"  {label:<34} {_fmt_pct(hi.get('mean_abs_excess')):>14} "
                  f"{_fmt_pct(lo.get('mean_abs_excess')):>14} "
                  f"{str(hi.get('n_dates', 0)):>12}  [{hi.get('state','?')}]")
        pb = block.get("placebo", {})
        print(f"  {'PLACEBO null (overall)':<34} {_fmt_pct(pb.get('mean_abs_excess')):>14} "
              f"{'—':>14} {str(pb.get('n_dates', 0)):>12}  [{pb.get('state','?')}]")

        # verdict line
        pb_x = pb.get("mean_abs_excess")
        verdicts = []
        for label, key in _verdict_tapes:
            slc = block.get(key, {})
            hi = (slc.get("HIGH") or {}).get("mean_abs_excess")
            lo = (slc.get("LOW") or {}).get("mean_abs_excess")
            if hi is None:
                verdicts.append(f"{label}: no grades yet")
                continue
            beats_placebo = (pb_x is not None and hi > pb_x)
            beats_low = (lo is not None and hi > lo)
            verdicts.append(
                f"{label}: HIGH>{'placebo v' if beats_placebo else 'placebo x'}"
                f" {'LOW v' if beats_low else 'LOW x'}")
        print("  verdict: " + " | ".join(verdicts))
    print("\n" + "=" * 86)
    print("Kill criterion (D6): novelty-v0 (_pit) must open a HIGH-LOW gap the hand")
    print("formula cannot, AND clear the placebo null, over n_dates >= 25.")
    print("Bias check: compare _pit vs biased [W3] to quantify look-ahead inflation.")
    print("=" * 86)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="Repo root (default: auto)")
    parser.add_argument("--json", action="store_true", help="Emit JSON, no table")
    args = parser.parse_args()

    rep = build_report(args.root)
    if args.json:
        import json
        print(json.dumps(rep, indent=2))
    else:
        _print_report(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
