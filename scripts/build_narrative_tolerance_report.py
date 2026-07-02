"""W3.4 — Narrative tolerance assertion: scan 'now' prose for number claims that
disagree with the current engine values beyond a declared tolerance.

Doctrine #1 (ENGINE_FIRST): any number the curated 'now' text carries that contradicts
the engine's computed value by >tolerance is a data quality violation.

Checked dimensions (all soft-warn, never hard-fail):
  pos claim     : "cycle position NNN/100" in now text  vs  nw.pos_v2  (tolerance ±15 pts)
  rs_rank claim : "rank #N" or "RS rank #N" in now text vs  nw.rs_rank (tolerance ±3 ranks)

Output: research/cycle_masterplan/W34_NARRATIVE_TOLERANCE_REPORT.md — committed artefact
        (the build warns on violations; the report lists them for manual review).

Also logs violations at WARNING level during build (never fatal).

Usage:
    python -m scripts.build_narrative_tolerance_report
"""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

log = logging.getLogger("narrative_tolerance")

ROOT = config.ROOT

# ── regex patterns ────────────────────────────────────────────────────────────

# matches "cycle position 81/100", "position 81/100", "position 45/100"
_POS_RE = re.compile(r"(?:cycle )?position[^\d]*(\d{1,3})/100", re.IGNORECASE)

# matches "RS rank #7", "rank #7 out of", "RS #7", "#7 out of"
_RANK_RE = re.compile(r"(?:RS\s*)?rank\s*#(\d{1,2})\b", re.IGNORECASE)

# ── tolerances ────────────────────────────────────────────────────────────────
POS_TOLERANCE = 15    # cycle position points (engine pos_v2 vs now-text claim)
RANK_TOLERANCE = 3    # rank places (engine rs_rank vs now-text claim)


# ── engine data loading ───────────────────────────────────────────────────────

def _load_engine(engine_name: str) -> list[dict]:
    """Load engine records for a given cycle family."""
    if engine_name == "sector_cycles":
        from engine import sector_cycles
        d = sector_cycles.compute()
        return d.get("sectors", []) + d.get("baskets", [])
    elif engine_name == "country_cycles":
        from engine import country_cycles
        d = country_cycles.compute()
        return d.get("sectors", []) + d.get("baskets", [])
    elif engine_name == "china_sector_cycles":
        from engine import china_sector_cycles as ccc
        d = ccc.compute()
        return d.get("sectors", []) + d.get("baskets", [])
    return []


def _engine_id(rec: dict, engine_name: str) -> str:
    """Normalise a series id from an engine record.

    The engine output IDs already include the b- prefix for baskets
    (e.g. "b-ai_infra"), so we just use the 'id' field directly.
    """
    raw = rec.get("id") or rec.get("basket_id") or rec.get("sector_id") or ""
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    return str(raw).lower()


# ── per-entry check ───────────────────────────────────────────────────────────

def _check_entry(
    sid: str,
    narr_entry: dict,
    engine_now: dict | None,
    engine_name: str,
) -> list[dict]:
    """Return list of tolerance violation dicts for one narrative entry."""
    violations = []
    now_text = narr_entry.get("now", "")
    if not now_text or engine_now is None:
        return []

    # ── pos claim ──────────────────────────────────────────────────────────────
    pos_matches = _POS_RE.findall(now_text)
    engine_pos = engine_now.get("pos_v2") or engine_now.get("pos")
    if pos_matches and engine_pos is not None:
        for m in pos_matches:
            claimed = int(m)
            delta = abs(claimed - float(engine_pos))
            if delta > POS_TOLERANCE:
                violations.append({
                    "series_id": sid,
                    "engine": engine_name,
                    "dim": "pos",
                    "claimed": claimed,
                    "engine_val": round(float(engine_pos), 1),
                    "delta": round(delta, 1),
                    "tolerance": POS_TOLERANCE,
                })
                log.warning(
                    "TOLERANCE [%s %s]: pos claim %d vs engine %.1f (delta %.1f > %d)",
                    engine_name, sid, claimed, engine_pos, delta, POS_TOLERANCE)

    # ── rs_rank claim ──────────────────────────────────────────────────────────
    rank_matches = _RANK_RE.findall(now_text)
    engine_rank = engine_now.get("rs_rank")
    if rank_matches and engine_rank is not None:
        for m in rank_matches:
            claimed = int(m)
            delta = abs(claimed - int(engine_rank))
            if delta > RANK_TOLERANCE:
                violations.append({
                    "series_id": sid,
                    "engine": engine_name,
                    "dim": "rs_rank",
                    "claimed": claimed,
                    "engine_val": engine_rank,
                    "delta": delta,
                    "tolerance": RANK_TOLERANCE,
                })
                log.warning(
                    "TOLERANCE [%s %s]: rs_rank claim #%d vs engine #%d (delta %d > %d)",
                    engine_name, sid, claimed, engine_rank, delta, RANK_TOLERANCE)

    return violations


# ── main ──────────────────────────────────────────────────────────────────────

def run(engines: list[str] | None = None) -> list[dict]:
    """Run tolerance check across all (or specified) engines.  Returns violations list."""
    if engines is None:
        engines = ["sector_cycles", "country_cycles", "china_sector_cycles"]

    from scripts._narrative_epoch import resolve_narratives

    all_violations: list[dict] = []

    for engine_name in engines:
        data_dir_map = {
            "sector_cycles":       ROOT / "data" / "sector_cycles",
            "country_cycles":      ROOT / "data" / "country_cycles",
            "china_sector_cycles": ROOT / "data" / "china_sector_cycles",
        }
        narr_res = resolve_narratives(engine_name, data_dir_map[engine_name], "narratives")
        narr_map = narr_res["map"]  # flat {sid: entry}

        # load engine now values
        try:
            records = _load_engine(engine_name)
        except Exception as e:  # noqa: BLE001
            log.warning("tolerance: engine %s unavailable (%s) — skipping", engine_name, e)
            continue

        # build {sid: now} engine map
        engine_now_map: dict[str, dict] = {}
        for rec in records:
            sid = _engine_id(rec, engine_name)
            nw = rec.get("now")
            if sid and nw:
                engine_now_map[sid] = nw

        for sid, entry in narr_map.items():
            if not isinstance(entry, dict):
                continue
            engine_now = engine_now_map.get(sid)
            violations = _check_entry(sid, entry, engine_now, engine_name)
            all_violations.extend(violations)

    return all_violations


def write_report(violations: list[dict]) -> Path:
    """Write the tolerance report markdown."""
    out_dir = ROOT / "research" / "cycle_masterplan"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "W34_NARRATIVE_TOLERANCE_REPORT.md"

    today = date.today().isoformat()
    lines: list[str] = [
        "# W3.4 Narrative Tolerance Report",
        "",
        f"Generated: {today}  ",
        "Dimensions checked: `pos` (±15 pts, claimed vs `nw.pos_v2`), `rs_rank` (±3 ranks, claimed vs `nw.rs_rank`)  ",
        "Trigger: `>tolerance` → soft WARN in build log; no hard failure.  ",
        "",
    ]

    if not violations:
        lines += [
            "## Result: 0 violations",
            "",
            "All curated `now` text numbers are within tolerance of the engine values "
            "(or engine data was unavailable for comparison).",
            "",
        ]
    else:
        lines += [
            f"## Result: {len(violations)} violation(s)",
            "",
            "| Engine | Series | Dim | Claimed | Engine | Delta | Tolerance |",
            "|--------|--------|-----|---------|--------|-------|-----------|",
        ]
        for v in sorted(violations, key=lambda x: (-x["delta"], x["engine"], x["series_id"])):
            lines.append(
                f"| {v['engine']} | `{v['series_id']}` | {v['dim']} "
                f"| {v['claimed']} | {v['engine_val']} | {v['delta']} | ±{v['tolerance']} |"
            )
        lines += [
            "",
            "### Action required",
            "",
            "Each violation above means the curated `now` text carries a stale number. "
            "Update the narrative's `now` field (re-run the relevant cause-research agent) "
            "OR bump `as_of` and note the deliberate discrepancy in `prev_revision`. "
            "The numbers diverge when the engine re-dates turns (epoch flip) or the market "
            "moves substantially since the prose was authored.",
            "",
        ]

    lines += [
        "---",
        f"*Auto-generated by `scripts/build_narrative_tolerance_report.py` on {today}*",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Tolerance report written: %s (%d violations)", out_path.name, len(violations))
    return out_path


def main() -> int:
    violations = run()
    write_report(violations)
    if violations:
        log.warning("%d tolerance violation(s) found — see research/cycle_masterplan/W34_NARRATIVE_TOLERANCE_REPORT.md",
                    len(violations))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
