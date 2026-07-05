"""Ingest a folder of brainstorm-pack JSON outputs; dedup + validate; prep for screening.

The high-volume path for external brainstorm (200-500 specs): the operator saves
each ChatGPT/Codex reply as a .json file in --inbox (a JSON list of compound
specs; a file may contain several concatenated lists). This tool:

  1. parses every *.json (tolerant of multiple concatenated JSON arrays),
  2. deduplicates by CANONICAL entry_rule — drops exact repeats within the batch
     AND anything whose rule already exists in the live registry,
  3. reassigns a unique id on id-collision (keeps the rule),
  4. validates grammar + columns (drops invalid),
  5. flags scale-suspect specs (stochrsi threshold on the 0-1 scale) and
     coverage-limited specs (conditioned on a 2021+-only column -> un-promotable),
  6. writes a scratch compounds dir ready for:
        python -m scripts.oracle_screen --all-pending --compounds-dir <out> \
            --data-dir <MAIN>/data --dry-run

Nothing here is promoted or committed; it only prepares a scratch screen set and
prints a summary. Usage:
    python -m scripts.oracle_ingest_brainstorm --inbox research/oracle_inbox \
        --out /tmp/oracle_ingest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.oracle.compounds import validate_rule, load_registry  # noqa: E402
from engine.oracle.panel import COLUMN_SCHEMA  # noqa: E402

# 2021+-only columns (see memory oracle-panel-column-coverage): a rule that
# conditions on any of these cannot clear the era gate and is un-promotable.
RECENT_ONLY = {"breadth_50", "cohesion", "cohesion_chg", "turnover_z", "cohesion_rebuild"}
# stochrsi columns live on a 0-100 scale; a numeric threshold < 1 is a scale bug.
STO_COLS = {"stochrsi_w_k", "stochrsi_w_d"}


def _parse_json_multi(text: str) -> list:
    """Parse a file that may contain one or several concatenated JSON arrays."""
    out = []
    dec = json.JSONDecoder()
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        try:
            val, end = dec.raw_decode(text, i)
        except json.JSONDecodeError:
            break
        out.extend(val if isinstance(val, list) else [val])
        i = end
    return out


def _rule_cols(rule: dict, acc: set) -> set:
    if "all" in rule:
        for s in rule["all"]:
            _rule_cols(s, acc)
    elif "any" in rule:
        for s in rule["any"]:
            _rule_cols(s, acc)
    elif "col" in rule:
        acc.add(rule["col"])
        if "value_col" in rule:
            acc.add(rule["value_col"])
    return acc


def _scale_suspect(rule: dict) -> bool:
    """True if a stochrsi column is compared to a numeric threshold < 1 (0-1 bug)."""
    hits = []
    def walk(r):
        if "all" in r:
            for s in r["all"]:
                walk(s)
        elif "any" in r:
            for s in r["any"]:
                walk(s)
        elif r.get("col") in STO_COLS and "value" in r and abs(r["value"]) < 1:
            hits.append(True)
    walk(rule)
    return bool(hits)


def _canonical(rule: dict) -> str:
    return json.dumps(rule, sort_keys=True, separators=(",", ":"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inbox", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("/tmp/oracle_ingest"))
    ap.add_argument("--registry-dir", type=Path, default=ROOT / "data" / "oracle" / "compounds")
    args = ap.parse_args()

    valid_cols = set(COLUMN_SCHEMA)
    seen = {_canonical(c["entry_rule"]): c.get("id", "?")
            for c in load_registry(args.registry_dir) if c.get("entry_rule")}
    seen_ids = set(seen.values())

    parsed = dropped_dup = dropped_invalid = 0
    kept, recent_only, scale_flagged = [], [], []
    for fp in sorted(args.inbox.glob("*.json")):
        for spec in _parse_json_multi(fp.read_text()):
            parsed += 1
            rule = spec.get("entry_rule")
            if not isinstance(rule, dict):
                dropped_invalid += 1
                continue
            key = _canonical(rule)
            if key in seen:
                dropped_dup += 1
                continue
            try:
                validate_rule(rule)
            except Exception:
                dropped_invalid += 1
                continue
            cols = _rule_cols(rule, set())
            if cols - valid_cols:
                dropped_invalid += 1
                continue
            seen[key] = spec.get("id", "?")
            # unique id
            cid = spec.get("id") or f"ING{len(kept)}"
            base, k = cid, 1
            while cid in seen_ids:
                cid = f"{base}__{k}"; k += 1
            seen_ids.add(cid)
            row = {"id": cid, "family": spec.get("family", "ING"),
                   "name": spec.get("name", cid),
                   "entry_rule": rule, "universe": {"tier": "s"},
                   "horizons": [21, 63], "status": "exploratory",
                   "lineage": spec.get("lineage", "ingest")}
            kept.append(row)
            if cols & RECENT_ONLY:
                recent_only.append(cid)
            if _scale_suspect(rule):
                scale_flagged.append(cid)

    args.out.mkdir(parents=True, exist_ok=True)
    reg = args.out / "compounds"
    reg.mkdir(exist_ok=True)
    with (reg / "registry.jsonl").open("w") as f:
        for r in kept:
            f.write(json.dumps(r) + "\n")
    (reg / "trial_ledger.jsonl").write_text("")

    print(f"parsed={parsed}  unique-valid={len(kept)}  "
          f"dropped_dup={dropped_dup}  dropped_invalid={dropped_invalid}")
    print(f"  2021+-only (un-promotable, probe-only): {len(recent_only)}")
    print(f"  scale-suspect (stochrsi 0-1 threshold): {len(scale_flagged)}"
          + (f" -> {scale_flagged[:8]}" if scale_flagged else ""))
    print(f"wrote {len(kept)} specs -> {reg}/registry.jsonl")
    print(f"screen: python -m scripts.oracle_screen --all-pending "
          f"--compounds-dir {reg} --data-dir <MAIN>/data --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
