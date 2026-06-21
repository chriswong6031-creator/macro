"""Promote a FORMING-NARRATIVE candidate into a curated thematic basket — HUMAN-IN-THE-LOOP.

The narrative-emergence radar (engine.narrative_emergence) surfaces coherent, tightening
groups of names our models see forming. This CLI turns ONE of those candidates into a
ready-to-review membership.json basket entry: name, thesis, an etf_proxy guess, and the full
constituent list with dated rationales. It NEVER auto-adds — by default it writes a proposal
file (and prints the block) for you to eyeball and paste; pass --write to insert it into the
region's membership.json (refusing to clobber an existing id unless --force).

Why human-in-the-loop: detection is noisy (~half of flags are real, persistent themes) and a
basket is a curated, dated, auditable object. The radar proposes; a human disposes.

Usage:
  python -m scripts.promote_candidate --region us                 # list current candidates
  python -m scripts.promote_candidate --region us --rank 1        # scaffold #1 (dry-run)
  python -m scripts.promote_candidate --region china --signature b912341a681b --write
  python -m scripts.promote_candidate --region us --rank 2 --id ai_robotics --write
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("promote_candidate")

# region → (membership.json dir, site basketdata folder)
_REGION = {
    "us":     ("baskets",        "basketdata"),
    "china":  ("baskets_china",  "chinabasketdata"),
    "hk":     ("baskets_hk",     "hkbasketdata"),
    "canada": ("baskets_canada", "canadabasketdata"),
    "intl":   ("baskets_intl",   "intlbasketdata"),
}

# US sector → SPDR sector-ETF proxy GUESS (human verifies). Other regions: no guess.
_US_SECTOR_ETF = {
    "Information Technology": "XLK", "Health Care": "XLV", "Financials": "XLF",
    "Energy": "XLE", "Consumer Discretionary": "XLY", "Consumer Staples": "XLP",
    "Industrials": "XLI", "Materials": "XLB", "Utilities": "XLU",
    "Real Estate": "XLRE", "Communication Services": "XLC",
}


def _slug(name: str, sig: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    s = re.sub(r"^(emerging|cross_sector_cluster|cross_sector|new_cluster)_?", "", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return (s or f"forming_{sig}")[:40]


def _emergence(region: str) -> dict | None:
    _md, folder = _REGION[region]
    p = config.ROOT / "site" / folder / "narrative_emergence.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.error("could not read %s (%s)", p, e)
        return None


def _full_constituents(region: str, signature: str) -> list[dict] | None:
    """Re-derive the chosen cluster's FULL constituent list from the radar (the emergence
    JSON keeps only the top recommended names). Matches by the same constituent-set hash."""
    try:
        from engine import theme_discovery as td
        from engine.narrative_emergence import _signature
        rad = td.discover_candidates(region)
        for cand in (rad or {}).get("candidates", []):
            if _signature(cand) == signature:
                return cand.get("constituents") or []
    except Exception as e:  # noqa: BLE001
        log.error("radar re-derivation failed (%s)", e)
    return None


def _scaffold(region: str, nv: dict, members: list[dict], basket_id: str) -> dict:
    today = date.today().isoformat()
    top_sector = (nv.get("novelty") or {}).get("top_sector") or "—"
    proxy = _US_SECTOR_ETF.get(top_sector) if region == "us" else None
    rec = {r["ticker"] for r in (nv.get("recommended") or [])}
    return {
        "name": nv["name_en"], "name_zh": nv["name_zh"],
        "theme": top_sector, "category": top_sector,
        "etf_proxy": proxy,
        "etf_proxy_note": ("GUESS from the dominant sector — verify or clear before use."
                           if proxy else "No proxy guessed — set one or leave null."),
        "created": today, "curated": today,
        "thesis": (f"{nv['why_en']} Surfaced by the forming-narrative radar at emergence "
                   f"score {nv['score']} ({nv['score_label']['en']}). REVIEW REQUIRED: "
                   f"detection is noisy and early-entry edge is ~0 — confirm the theme is "
                   f"real and durable before trusting this basket."),
        "weighting": "equal",
        "members": [
            {"ticker": m["ticker"], "added": today, "removed": None,
             "rationale": (f"{m.get('name') or m['ticker']} — {m.get('sector') or '—'}; "
                           + ("clean-entry pick from the radar" if m["ticker"] in rec
                              else "co-moving cluster member"))}
            for m in members
        ],
        "changelog": [{"date": today, "action": "scaffolded",
                       "note": f"Auto-scaffolded from the forming-narrative radar (sig {nv['signature']}). "
                               "Human review pending."}],
        "tags": ["forming-narrative", f"radar-{nv['signature']}"],
        "_provenance": {"source": "narrative_emergence.radar", "region": region,
                        "signature": nv["signature"], "emergence_score": nv["score"],
                        "auto_scaffolded": True, "needs_human_review": True},
    }


def _list(em: dict) -> None:
    print(f"\nForming-narrative candidates — {em.get('market_en')} (as of {em.get('as_of')}):\n")
    for i, nv in enumerate(em.get("narratives", []), 1):
        recs = ", ".join(r["ticker"] for r in (nv.get("recommended") or [])[:5])
        print(f"  #{i}  score {nv['score']:>4} [{nv['score_label']['en']:<12}] "
              f"sig {nv['signature']}  {nv['name_en']}")
        print(f"        watch: {recs}")
    print("\nScaffold one with:  --rank N   (dry-run) ;  add --write to insert into membership.json\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Promote a forming-narrative candidate to a basket.")
    ap.add_argument("--region", default="us", choices=list(_REGION))
    ap.add_argument("--rank", type=int, help="1-based rank from the emergence list")
    ap.add_argument("--signature", help="pick by signature instead of rank")
    ap.add_argument("--id", help="override the generated basket id")
    ap.add_argument("--write", action="store_true",
                    help="insert into the region's membership.json (default: proposal file only)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing basket id")
    args = ap.parse_args(argv)

    em = _emergence(args.region)
    if not em or not em.get("narratives"):
        log.error("no forming-narrative candidates for %s — run the baskets build first.", args.region)
        return 1
    if args.rank is None and not args.signature:
        _list(em)
        return 0

    if args.signature:
        nv = next((n for n in em["narratives"] if n["signature"] == args.signature), None)
    else:
        nv = em["narratives"][args.rank - 1] if 1 <= args.rank <= len(em["narratives"]) else None
    if not nv:
        log.error("candidate not found (rank/signature out of range).")
        return 1

    members = _full_constituents(args.region, nv["signature"])
    if not members:
        log.warning("could not re-derive full constituents; falling back to recommended names.")
        members = [{"ticker": r["ticker"], "name": r.get("name"), "sector": r.get("sector")}
                   for r in (nv.get("recommended") or [])]
    basket_id = (args.id or _slug(nv["name_en"], nv["signature"]))
    basket = _scaffold(args.region, nv, members, basket_id)

    md_dir = config.data_dir() / _REGION[args.region][0]
    mem_path = md_dir / "membership.json"

    if not args.write:
        prop_dir = md_dir / "proposals"
        prop_dir.mkdir(parents=True, exist_ok=True)
        out = prop_dir / f"{basket_id}.json"
        out.write_text(json.dumps({basket_id: basket}, indent=2, ensure_ascii=False))
        print(json.dumps({basket_id: basket}, indent=2, ensure_ascii=False))
        log.info("DRY-RUN: wrote proposal -> %s (review, then re-run with --write or paste into membership.json)", out)
        return 0

    if not mem_path.exists():
        log.error("membership.json not found at %s", mem_path)
        return 1
    doc = json.loads(mem_path.read_text())
    baskets = doc.setdefault("baskets", {})
    if not isinstance(baskets, dict):
        log.error("membership.json baskets is not a dict — refuse to edit (%s)", mem_path)
        return 1
    if basket_id in baskets and not args.force:
        log.error("basket id '%s' already exists — pass --force to overwrite or --id to rename.", basket_id)
        return 1
    baskets[basket_id] = basket
    mem_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    log.info("WROTE basket '%s' into %s (%d members). Review the diff, set etf_proxy, then rebuild.",
             basket_id, mem_path, len(basket["members"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
