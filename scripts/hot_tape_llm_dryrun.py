"""scripts/hot_tape_llm_dryrun.py — PR evidence for the Hot Tape P2 wire desk.

Runs the golden FactPackets (tests/fixtures/hot_tape_golden_packets.json)
through engine.marketing.hot_tape_llm.phrase_or_fallback and prints a markdown
report you paste into a PR body:

  * **Before/after pairs** — the radar's deterministic wire template (BEFORE)
    against whatever actually shipped (AFTER). When the model served, that is
    the phrasing difference the whole phase exists to buy. When it fell back,
    BEFORE == AFTER, which is the promise: a fired event always posts.
  * **Fallback rate** — the module's own counters. A lane whose model copy is
    rejected every time is a PROMPT to fix, not a model to retry; a lane at 0%
    fallback on a live key has not been stressed yet.
  * **Validator rejection demo** — three copy shapes the gates must refuse:
    an invented number, the corpus's hedged 95-view anti-example, and a
    directive call (gate 0.4).

ARMING. The provider path needs BOTH `hot_tape.llm.enabled` (config.yml, on)
and `MARKETING_LLM_ENABLED=1` in the environment. This script REFUSES to set
that flag for you: an evidence run that silently arms itself is not evidence.
Export it (with a credential) in the shell you run this from, or pass --offline
for the fallback-path smoke test, which touches no provider at all.

Usage
-----
    MARKETING_LLM_ENABLED=1 python scripts/hot_tape_llm_dryrun.py
    python scripts/hot_tape_llm_dryrun.py --offline
    python scripts/hot_tape_llm_dryrun.py --offline --json-out /tmp/hot_tape.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE = ROOT / "tests" / "fixtures" / "hot_tape_golden_packets.json"

#: A packet that matches the corpus control case, so the hedged post's ONLY
#: defect is the hedge — the 9% is a real engine-computed number.
_MU_PACKET = {
    "cashtag": "$MU",
    "cashtags": ["$MU"],
    "name": "Micron",
    "trigger": "mover_drop",
    "as_of": "2026-07-28T18:05:00Z",
    "direction": "down",
    "pct_day": -9.0,
}


def _load_packets() -> list[dict]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return list(data.get("packets") or [])


def _fence(text: str) -> str:
    return text.replace("\n", " ").strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--offline", action="store_true",
                    help="skip every provider call; exercise the fallback path only")
    ap.add_argument("--json-out", metavar="PATH",
                    help="write the raw per-packet results as JSON")
    args = ap.parse_args()

    from engine.marketing import hot_tape_llm as htl

    armed = os.environ.get("MARKETING_LLM_ENABLED", "").strip().lower() in ("1", "true", "yes")
    if not args.offline and not armed:
        print("REFUSING TO RUN: MARKETING_LLM_ENABLED is not set.\n"
              "  The provider path is armed by the CALLER, never by this script — "
              "an evidence run that arms itself is not evidence.\n"
              "  Run:  MARKETING_LLM_ENABLED=1 python scripts/hot_tape_llm_dryrun.py\n"
              "  Or:   python scripts/hot_tape_llm_dryrun.py --offline",
              file=sys.stderr)
        return 2

    # --offline disables the lane through the same config knob the operator uses,
    # so the fallback path under test is the real one, not a special case.
    cfg = {"enabled": False} if args.offline else None

    htl.reset_stats()
    results: list[dict] = []
    for entry in _load_packets():
        out = htl.phrase_or_fallback(
            entry["packet"], entry.get("trigger", ""), entry["fallback_text"],
            link=entry.get("link"), links_allowed=entry.get("links_allowed", True),
            cfg=cfg,
        )
        results.append({
            "id": entry.get("id", ""),
            "trigger": entry.get("trigger", ""),
            "before": entry["fallback_text"],
            "after": out["text"],
            "mode": out["mode"],
            "provider": out["provider"],
            "latency_ms": out["latency_ms"],
            "violations": out["violations"],
        })

    mode_label = "OFFLINE (no provider touched)" if args.offline else "LIVE waterfall"
    print(f"## Hot Tape P2 — LLM wire desk dry run ({mode_label})")
    print()

    print("### Before/after pairs")
    print()
    for r in results:
        changed = "changed" if r["after"] != r["before"] else "unchanged (template posted)"
        print(f"**{r['id']} · `{r['trigger']}`** — mode `{r['mode']}`, "
              f"provider `{r['provider']}`, {r['latency_ms']} ms, {changed}")
        print(f"- BEFORE (template): {_fence(r['before'])}")
        print(f"- AFTER  (posted):   {_fence(r['after'])}")
        if r["violations"]:
            print(f"- rejected because: {'; '.join(r['violations'])}")
        print()

    stats = htl.fallback_stats()
    print("### Fallback rate")
    print()
    print(f"- attempts: **{stats['calls']}**")
    print(f"- model copy shipped (`llm`): **{stats['llm']}**")
    print(f"- rejected by the gates (`fallback_validation`): **{stats['fallback_validation']}**")
    print(f"- no provider / call failed (`fallback_provider`): **{stats['fallback_provider']}**")
    print(f"- lane disarmed (`off`): **{stats['off']}**")
    print(f"- fallback rate: **{stats['fallback_rate'] * 100:.1f}%**")
    print()

    print("### Validator rejection demo")
    print()
    packets = {e["id"]: e["packet"] for e in _load_packets()}
    demos = [
        ("invented number (gate 0.3)",
         "$SNDK falls over -17% on the day and is now -56% from its record high.",
         packets["P1"]),
        ("hedged, stat-free — the corpus's 95-view control case",
         htl.ANTI_EXEMPLAR, _MU_PACKET),
        ("directive call (gate 0.4)",
         "$SNDK -17% today. Buy the dip here, we are long into the close.",
         packets["P1"]),
    ]
    for label, text, packet in demos:
        violations = htl.validate_wire_copy(text, packet)
        print(f"**{label}**")
        print(f"- copy: {_fence(text)}")
        print(f"- violations: {violations}")
        print()

    if args.json_out:
        payload = {"mode": "offline" if args.offline else "live",
                   "results": results, "stats": stats}
        Path(args.json_out).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"_raw results written to {args.json_out}_")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
