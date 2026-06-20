"""Promote LLM-extracted candidate edges into the curated TrumpFlow graph — the human gate.

The extractor (engine/trumpflow/extract.py) writes low-confidence candidate edges to
data/trumpflow/extracted_edges.jsonl with a verbatim citation. They are NEVER auto-merged
— a human reviews them here and promotes the good ones into data/trumpflow/intel.json,
where the deterministic graph queries pick them up.

Usage:
    python -m scripts.promote_trumpflow_candidates                 # list pending candidates
    python -m scripts.promote_trumpflow_candidates --approve 0,2   # promote #0 and #2
    python -m scripts.promote_trumpflow_candidates --approve-all   # promote every matchable one

A candidate is promotable only when BOTH its src and dst free-text names resolve to an
existing node id in intel.json (so the graph stays consistent) — otherwise it's reported
as needing a new entity added by hand first. Promoted candidates are appended to
intel.json edges (provenance INFERRED, the citation kept as the note) and removed from the
candidate file.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.trumpflow import extract  # noqa: E402
from lib import config  # noqa: E402

_INTEL = ("data", "trumpflow", "intel.json")
_NORM = re.compile(r"[^a-z0-9]+")


def _norm(s: str) -> str:
    return _NORM.sub(" ", (s or "").lower()).strip()


def load_intel(root=None) -> dict:
    p = (Path(root) if root else config.ROOT).joinpath(*_INTEL)
    return json.loads(p.read_text()) if p.exists() else {}


def match_node(name: str, intel: dict) -> str | None:
    """Resolve a free-text src/dst name to an existing node id (person/entity/theme)."""
    n = _norm(name)
    if not n:
        return None
    nodes = []
    for p in intel.get("people", []):
        nodes.append((p["id"], _norm(p.get("name", "")), _norm(p["id"])))
    for e in intel.get("entities", []):
        nodes.append((e["id"], _norm(e.get("name", "")), _norm(e["id"])))
    for tid, t in intel.get("themes", {}).items():
        nodes.append(("theme:" + tid, _norm(t.get("en", "")), _norm(tid)))
    # exact-ish then substring match on name or id
    for nid, nm, nidn in nodes:
        if n == nm or n == nidn:
            return nid
    for nid, nm, nidn in nodes:
        if nm and (n in nm or nm in n):
            return nid
    return None


def promote(candidates: list[dict], indices: set[int] | None, intel: dict) -> tuple[list, list, list]:
    """Return (new_edges, promoted_candidate_keys, skipped[(key, reason)])."""
    new_edges, promoted, skipped = [], [], []
    existing = {(e["src"], e["rel"], e["dst"]) for e in intel.get("edges", [])}
    for i, c in enumerate(candidates):
        if indices is not None and i not in indices:
            continue
        ckey = f"{c.get('src')}|{c.get('rel')}|{c.get('dst')}"
        src = match_node(c.get("src", ""), intel)
        dst = match_node(c.get("dst", ""), intel)
        if not src or not dst:
            missing = ", ".join(x for x, ok in (("src", src), ("dst", dst)) if not ok)
            skipped.append((ckey, f"no node id for {missing} — add the entity to intel.json first"))
            continue
        if (src, c["rel"], dst) in existing:
            skipped.append((ckey, "edge already in graph"))
            continue
        new_edges.append({
            "src": src, "rel": c["rel"], "dst": dst,
            "provenance": "INFERRED", "confidence": float(c.get("confidence", 0.5)),
            "note": (c.get("citation") or "")[:200], "url": c.get("url"),
            "promoted_at": datetime.now(timezone.utc).date().isoformat(), "source": "llm_extract",
        })
        promoted.append(ckey)
    return new_edges, promoted, skipped


def _write_intel(intel: dict, root=None) -> None:
    p = (Path(root) if root else config.ROOT).joinpath(*_INTEL)
    p.write_text(json.dumps(intel, indent=2, ensure_ascii=False))


def _rewrite_candidates(remaining: list[dict], root=None) -> None:
    p = extract._path(root)
    p.write_text("".join(json.dumps(c, default=str) + "\n" for c in remaining))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--approve", default="", help="comma-separated candidate indices to promote")
    ap.add_argument("--approve-all", action="store_true")
    args = ap.parse_args()

    intel = load_intel()
    candidates = extract.load_candidates()
    if not candidates:
        print("No pending candidate edges (data/trumpflow/extracted_edges.jsonl is empty).")
        print("Enable the extractor with `trumpflow.extract: true` + DEEPSEEK_API_KEY to generate some.")
        return 0

    if not args.approve and not args.approve_all:
        print(f"{len(candidates)} pending candidate edge(s):\n")
        for i, c in enumerate(candidates):
            nid_s, nid_d = match_node(c.get("src", ""), intel), match_node(c.get("dst", ""), intel)
            flag = "✓ promotable" if (nid_s and nid_d) else "✗ needs a new entity in intel.json"
            print(f"  [{i}] {c.get('src')} -{c.get('rel')}-> {c.get('dst')}   [{flag}]")
            print(f"       cite: \"{(c.get('citation') or '')[:90]}\"  src={c.get('source_type')}")
        print("\nPromote with --approve 0,1  or  --approve-all")
        return 0

    indices = None if args.approve_all else {int(x) for x in args.approve.split(",") if x.strip().isdigit()}
    new_edges, promoted, skipped = promote(candidates, indices, intel)
    if new_edges:
        intel.setdefault("edges", []).extend(new_edges)
        _write_intel(intel)
        remaining = [c for c in candidates if f"{c.get('src')}|{c.get('rel')}|{c.get('dst')}" not in set(promoted)]
        _rewrite_candidates(remaining)
    print(f"promoted {len(new_edges)} edge(s) into intel.json; {len(skipped)} skipped")
    for k, reason in skipped:
        print(f"  skip {k}: {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
