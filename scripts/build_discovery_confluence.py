"""scripts/build_discovery_confluence.py — W9 discovery-confluence runner.

Runs the two W9 legs and emits their join artifact:
  • engine/edgar_phrase_velocity.py  → site/basketdata/phrase_velocity.json
  • engine/theme_adoption.py         → site/basketdata/github_adoption.json
  • join                             → data/neuralweb/discovery_confluence.json

Confluence join rule: a theme is flagged as a "discovery candidate" when BOTH
  (a) at least one phrase in phrase_velocity has velocity_z > 0 with ≥2 filers, AND
  (b) the basket's star_velocity_7d_z is non-null and positive.

Themes with only one leg positive are listed as "single-leg acceleration" (weaker signal).
Novel phrase clusters (no theme home) are passed through directly from the EDGAR leg.

DISPLAY-ONLY / WATCHLIST. Authority: all may_* false; is_context_only=true.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)

AUTHORITY = {
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "is_context_only": True,
    "framing": "discovery_confluence_watchlist",
    "rotation_calls": False,
    "short_calls": False,
    "honesty_note": (
        "Two-source confluence: EDGAR phrase acceleration + GitHub adoption velocity. "
        "Both legs must accelerate for a confluence flag. Detection is noisy — "
        "~half of flags are real. Early-entry edge ≈ 0. "
        "Candidate for curated review only — never auto-promoted."
    ),
}


def _theme_phrase_accelerating(phrase_result: dict, theme_id: str) -> bool:
    """True when the theme has at least one phrase with velocity_z > 0 and ≥2 recent filers."""
    tdata = (phrase_result.get("themes") or {}).get(theme_id, {})
    for pr in tdata.get("top_accelerating", []):
        if pr.get("velocity_z") is not None and pr["velocity_z"] > 0 and pr.get("recent_filers", 0) >= 2:
            return True
    return False


def _basket_adoption_positive(adoption_result: dict, basket_id: str) -> bool:
    """True when the basket has a positive star_velocity_7d_z."""
    bdata = (adoption_result.get("baskets") or {}).get(basket_id, {})
    z = bdata.get("star_velocity_7d_z")
    return z is not None and z > 0


def build_confluence(
    as_of: date | None = None,
    out_path: Path | None = None,
) -> dict:
    """Compute and write discovery_confluence.json.

    Returns the confluence dict. Always exits cleanly.
    """
    from engine.edgar_phrase_velocity import compute_phrase_velocity, write_site_projection as write_pv
    from engine.theme_adoption import compute_theme_adoption, write_site_projection as write_ta
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        yaml = None  # type: ignore[assignment]

    as_of = as_of or date.today()
    ts = datetime.now(timezone.utc).isoformat()

    if out_path is None:
        out_path = config.ROOT / "data" / "neuralweb" / "discovery_confluence.json"

    log.info("build_discovery_confluence: running edgar_phrase_velocity (as_of=%s)", as_of)
    phrase_result = compute_phrase_velocity(as_of=as_of)
    pv_path = write_pv(phrase_result)

    log.info("build_discovery_confluence: running theme_adoption")
    adoption_result = compute_theme_adoption(as_of=as_of)
    ta_path = write_ta(adoption_result)

    # ── Load theme → baskets mapping ──────────────────────────────────────
    theme_to_baskets: dict[str, list[str]] = {}
    if yaml is not None:
        try:
            cw_path = config.ROOT / "config" / "theme_crosswalk.yml"
            if cw_path.exists():
                with open(cw_path) as f:
                    cw = yaml.safe_load(f)
                theme_to_baskets = {
                    t["id"]: t.get("basket_ids", [])
                    for t in cw.get("themes", [])
                    if "id" in t
                }
        except Exception as exc:  # noqa: BLE001
            log.warning("build_discovery_confluence: crosswalk load failed: %s", exc)

    # ── Join: identify confluence + single-leg candidates ────────────────
    both_legs: list[dict] = []
    single_leg_phrase: list[dict] = []
    single_leg_adoption: list[dict] = []

    all_theme_ids = list(phrase_result.get("themes", {}).keys())

    for theme_id in sorted(all_theme_ids):
        phrase_accel = _theme_phrase_accelerating(phrase_result, theme_id)
        # Check any basket for this theme
        t_baskets = theme_to_baskets.get(theme_id, [])
        adoption_pos = any(_basket_adoption_positive(adoption_result, bid) for bid in t_baskets)

        tdata = (phrase_result.get("themes") or {}).get(theme_id, {})
        top_phrases = tdata.get("top_accelerating", [])

        entry: dict = {
            "theme_id": theme_id,
            "baskets": t_baskets,
            "phrase_accelerating": phrase_accel,
            "adoption_positive": adoption_pos,
            "top_phrases": top_phrases[:3],
            "basket_z_scores": {
                bid: (adoption_result.get("baskets") or {}).get(bid, {}).get("star_velocity_7d_z")
                for bid in t_baskets
            },
        }

        if phrase_accel and adoption_pos:
            entry["confidence"] = "both_legs"
            both_legs.append(entry)
        elif phrase_accel:
            entry["confidence"] = "phrase_only"
            single_leg_phrase.append(entry)
        elif adoption_pos:
            entry["confidence"] = "adoption_only"
            single_leg_adoption.append(entry)

    # Novel phrases from EDGAR leg
    novel_phrases = phrase_result.get("novel_phrases", [])

    confluence: dict = {
        "schema": "discovery_confluence.v1",
        "as_of": as_of.isoformat(),
        "generated_at": ts,
        "authority": AUTHORITY,
        "honesty_header": AUTHORITY["honesty_note"],
        "sources": {
            "phrase_velocity": str(pv_path),
            "github_adoption": str(ta_path),
        },
        "confluence_candidates": both_legs,
        "single_leg_phrase": single_leg_phrase,
        "single_leg_adoption": single_leg_adoption,
        "novel_phrase_clusters": novel_phrases,
        "summary": {
            "both_legs_count": len(both_legs),
            "single_leg_phrase_count": len(single_leg_phrase),
            "single_leg_adoption_count": len(single_leg_adoption),
            "novel_phrase_count": len(novel_phrases),
            "themes_evaluated": len(all_theme_ids),
            "note": (
                f"{len(both_legs)} themes show confluence (both legs accelerating). "
                f"{len(single_leg_phrase)} show phrase-only acceleration. "
                f"{len(single_leg_adoption)} show adoption-only positive. "
                f"{len(novel_phrases)} novel phrase clusters with no theme home."
            ),
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(confluence, f, ensure_ascii=False, indent=2)
    log.info("build_discovery_confluence: wrote -> %s", out_path)
    return confluence


def main() -> int:
    import argparse  # noqa: PLC0415

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(
        description="build_discovery_confluence — W9 two-source join (off render path)"
    )
    p.add_argument("--as-of", default=None, help="ISO date for PIT cutoff")
    p.add_argument("--out", default=None, help="Override output path")
    args = p.parse_args()

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    out_path = Path(args.out) if args.out else None
    result = build_confluence(as_of=as_of, out_path=out_path)

    s = result.get("summary", {})
    print(f"as_of: {result['as_of']}")
    print(f"both-leg confluence: {s.get('both_legs_count', 0)} themes")
    print(f"phrase-only: {s.get('single_leg_phrase_count', 0)} themes")
    print(f"adoption-only: {s.get('single_leg_adoption_count', 0)} themes")
    print(f"novel phrases: {s.get('novel_phrase_count', 0)}")
    return 0


if __name__ == "__main__":
    from lib.procutil import hard_exit  # noqa: PLC0415
    hard_exit(main())
