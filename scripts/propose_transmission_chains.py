"""Emit the copy-paste PROPOSAL PACK for autonomous transmission-chain discovery (TXI-W5).

This is the ONE new "generation" surface of the TXI Loop-C closure — and it produces a
PACK, not chains. The LLM proposing happens inside the EXISTING Causal Hypothesis Factory
(CHF) brainstorm lane (`scripts/run_causal_brainstorm.py`); TXI builds NO second LLM loop
(TXI §4 CHF-R1/R2 "ride, don't re-register"). This script mirrors the shape of
`scripts/causal_brainstorm_pack.py` (self-contained text pack, all sections generated live
from committed artifacts, an absent file yields an honest '(absent — 0 rows)' line, nothing
fabricated, no LLM calls) but asks specifically for multi-hop macro→micro TRANSMISSION
CHAINS in the W1 chain schema (`knowledge/transmission/SCHEMA.md`), NOT CHF mechanism cards.

Anti-hallucination is the pack's core job: it hands the LLM the LIVE resolvable inventory —
the six registered source adapters, the actual series files on disk, the real top-level
keys of the state JSONs, and the whitelisted node-test ops/metrics — pulled DIRECTLY from
`engine.transmission_chains` and from disk, so a proposed node can only bind to a real,
collected artifact. A chain whose nodes don't resolve is REJECTED at ingest (never faked).

Proposal signals ("a cascade we don't yet track"):
  - CHF surprise queue  (data/neuralweb/causal_surprise_queue.jsonl) — unexplained tape
    anomalies / large forecast misses worth a causal story.
  - lessons ledgers     (data/metabolism/shadow/*/lessons.jsonl)     — postmortems of
    missed / unverifiable moves.
  - existing library    (knowledge/transmission/*.yaml + proposed/)  — the node-sets we
    ALREADY track, rendered as DO-NOT-REPROPOSE so the LLM proposes something NEW.

Output is stdout by default (faithful mirror of causal_brainstorm_pack, which writes
NOTHING — the runner writes it to /tmp). `--out PATH` lets the W5 runner drop it at the
CHF lane's expected input location; `--meta PATH` writes a small provenance sidecar
(generated_at / asof / pack_id) so the ingest can stamp `proposed_at` WITHOUT calling any
clock (timestamps flow through the pack metadata, per the W5 no-Date.now law).

Usage:
    python -m scripts.propose_transmission_chains [--n N] [--asof YYYY-MM-DD] \
        [--out pack.txt] [--meta pack.meta.json] > pack.txt
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Single source of truth for what a node may bind to / test — never a divergent hardcode.
from engine.transmission_chains import (  # noqa: E402
    _VALID_METRICS,
    _VALID_OPS,
    build_adapters,
    load_chains,
)

# ---------------------------------------------------------------------------
# File paths (all relative to ROOT)
# ---------------------------------------------------------------------------

_SURPRISE_QUEUE = ROOT / "data" / "neuralweb" / "causal_surprise_queue.jsonl"
_SHADOW_DIR = ROOT / "data" / "metabolism" / "shadow"
_SERIES_GROUPS = ("yahoo", "commodity", "fred")
_STATE_FILES = {
    "transmission_state": ROOT / "data" / "transmission" / "latest.json",
    "regime_state": ROOT / "data" / "regime" / "latest.json",
    "forex_state": ROOT / "data" / "forex" / "latest.json",
}

# Series we KNOW are macro-relevant (the seeds bind to these); shown first so the LLM has
# concrete anchors. The full on-disk set (rendered as a count) is the true resolvable set.
_ANCHOR_SERIES = {
    "yahoo": ["CL=F", "QQQ", "SPY", "IWM", "HYG", "LQD", "FXI", "SPHB", "TLT", "XLE", "^MOVE", "^VIX"],
    "commodity": ["signals_oil", "signals_copper", "signals_gold", "signals_complex"],
    "fred": ["T10YIE", "DGS10", "DGS2", "BAMLC0A0CM", "BAMLH0A0HYM2", "DTWEXBGS"],
}

_MAX_SURPRISE = 20
_MAX_LESSONS = 15
_MAX_SERIES_SAMPLE = 40


# ---------------------------------------------------------------------------
# Helpers (same idiom as causal_brainstorm_pack)
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def _load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _series_on_disk(group: str) -> list[str]:
    """Real series stems present in data/<group>/ (the true resolvable set for this adapter).

    Mirrors the adapter's on-disk name mangling in reverse only for display — the stems are
    shown verbatim as they sit on disk; the adapter maps '^'/'='/'/'/' ' → '_' when reading,
    so the LLM should use the market ticker (e.g. 'CL=F') and the adapter resolves the file.
    """
    d = ROOT / "data" / group
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.parquet"))


def _node_signature(chain: dict) -> frozenset:
    """A structural fingerprint of a chain's OBSERVABLE logic for dedup: the set of
    (src, canonical-test-json) tuples across its nodes. Two chains with the same node-set
    describe the same cascade regardless of slug/title, so the pack can render them as
    DO-NOT-REPROPOSE and the ingest can drop an exact-node-set duplicate.
    """
    sig = set()
    for node in (chain.get("nodes") or {}).values():
        if not isinstance(node, dict):
            continue
        src = node.get("src", "")
        test = json.dumps(node.get("test", {}), sort_keys=True, separators=(",", ":"))
        sig.add((src, test))
    return frozenset(sig)


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _section_role() -> str:
    return (
        "=== ROLE + AUTHORITY BOUNDARY (read first) ===\n"
        "You are proposing candidate macro→micro TRANSMISSION CHAINS for the Transmission\n"
        "Intelligence knowledge store. A chain is a versioned, human-auditable description of\n"
        "ONE cascade: an ordered list of observable NODES and the directed HOPS between them.\n"
        "\n"
        "HARD LAWS you MUST respect (a proposal violating any of these is dropped at ingest):\n"
        "  - A chain NEVER emits an alpha score, gate, size, rank, or escalation. It only\n"
        "    describes an observable cascade state (display/context tier). Do NOT add any\n"
        "    scoring / weight / signal / conviction field. (DNR row 45 / TXI Article 1/2.)\n"
        "  - Every node.test MUST bind to a REAL, collected artifact through one of the six\n"
        "    registered source adapters below. A node whose series/path is not in the live\n"
        "    inventory is UNRESOLVABLE and its whole chain is REJECTED — never invent a\n"
        "    series, a state path, or a detector to make a chain look green.\n"
        "  - Propose chains that are FALSIFIABLE: each needs falsifiers and a null model it\n"
        "    must beat. You propose; deterministic detectors (not you) later confirm hops.\n"
        "  - Propose something NEW: do not re-describe a cascade already in the library\n"
        "    (see DO-NOT-REPROPOSE). Chains land HYPOTHESIS-tier, display-only, and stay\n"
        "    there until a human PR promotes them — you are never granting authority."
    )


def _section_adapters() -> str:
    """The six resolvable adapters, pulled live from engine.transmission_chains.build_adapters."""
    adapters = build_adapters(ROOT / "data")
    lines = [
        "=== RESOLVABLE SOURCE ADAPTERS (node.src MUST be one of these) ===",
        "The engine registers exactly these adapters; any other src makes the node unresolvable:",
    ]
    series_adapters = []
    state_adapters = []
    for name in sorted(adapters):
        # _SeriesAdapter vs _StateAdapter — classify by the presence of a 'series' method.
        if hasattr(adapters[name], "series"):
            series_adapters.append(name)
        else:
            state_adapters.append(name)
    lines.append(f"  SERIES adapters (test uses {{series, metric, window, ...}}): {', '.join(series_adapters)}")
    lines.append(f"  STATE  adapters (test uses {{path, op, value}}):            {', '.join(state_adapters)}")
    return "\n".join(lines)


def _section_series_inventory() -> str:
    lines = [
        "=== LIVE SERIES INVENTORY (what the SERIES adapters can resolve) ===",
        "Use the market ticker verbatim (e.g. 'CL=F', '^MOVE', 'HYG'); the adapter maps the",
        "on-disk filename. Anchor series (macro-relevant, already used by seeds) first, then a",
        "sample of the full on-disk set with its true count. Only series present on disk resolve.",
    ]
    for group in _SERIES_GROUPS:
        on_disk = _series_on_disk(group)
        n = len(on_disk)
        if n == 0:
            lines.append(f"  {group}: (absent — 0 series on disk)")
            continue
        anchors = [s for s in _ANCHOR_SERIES.get(group, [])]
        # For yahoo the on-disk stems are mangled (CL=F -> CL_F); show anchors as tickers.
        sample = on_disk[:_MAX_SERIES_SAMPLE]
        lines.append(f"  {group}: {n} series on disk.")
        if anchors:
            lines.append(f"      anchors: {', '.join(anchors)}")
        more = f" … (+{n - len(sample)} more)" if n > len(sample) else ""
        lines.append(f"      on-disk stems (sample): {', '.join(sample)}{more}")
    return "\n".join(lines)


def _walk_paths(obj, prefix: str, depth: int, max_depth: int, out: list[str]) -> None:
    if depth > max_depth or not isinstance(obj, dict):
        return
    for k in sorted(obj.keys()):
        p = f"{prefix}.{k}" if prefix else k
        v = obj[k]
        if isinstance(v, dict) and depth < max_depth:
            out.append(f"{p}.*")
            _walk_paths(v, p, depth + 1, max_depth, out)
        else:
            kind = type(v).__name__ if not isinstance(v, dict) else "dict"
            out.append(f"{p}  <{kind}>")


def _section_state_inventory() -> str:
    lines = [
        "=== LIVE STATE INVENTORY (what the STATE adapters can resolve) ===",
        "A STATE-adapter node reads a dotted path into the adapter's JSON. Real top-level keys",
        "of each state file are listed below (with a shallow walk); a path not present resolves",
        "as UNRESOLVABLE, not False. Read the actual file for deep paths before proposing one.",
    ]
    for name, path in _STATE_FILES.items():
        data = _load_json(path)
        if not isinstance(data, dict):
            lines.append(f"  {name} ({path.relative_to(ROOT)}): (absent — 0 keys)")
            continue
        walked: list[str] = []
        _walk_paths(data, "", 0, 1, walked)
        # cap to keep the pack readable
        shown = walked[:60]
        more = f" … (+{len(walked) - len(shown)} more paths)" if len(walked) > len(shown) else ""
        lines.append(f"  {name} ({path.relative_to(ROOT)}): {len(data)} top-level keys.")
        lines.append("      " + "; ".join(shown) + more)
    return "\n".join(lines)


def _section_test_grammar() -> str:
    ops = ", ".join(sorted(_VALID_OPS))
    metrics = ", ".join(sorted(_VALID_METRICS))
    return (
        "=== NODE-TEST GRAMMAR (whitelisted — NO eval, NO arbitrary Python) ===\n"
        f"ops     (all tests): {ops}\n"
        f"metrics (series tests): {metrics}\n"
        "UNITS: ret / rs / ratio_ret emit PERCENT (×100); ret_bp emits BASIS POINTS; ma_slope\n"
        "emits a raw price-delta. Your threshold MUST match the metric's unit.\n"
        "  series metric:   {series: \"CL=F\", metric: ret, window: 60, op: gt, value: 25}\n"
        "  level Δ in bp:   {series: \"T10YIE\", metric: ret_bp, window: 22, op: gt, value: 15}\n"
        "  MA slope:        {series: \"CL=F\", metric: ma_slope, window: 50, lookback: 5, op: gt, value: 0}\n"
        "  rel strength:    {series: \"QQQ\", vs: \"SPY\", metric: rs, window: 63, op: lt, value: 0}\n"
        "  ratio return:    {series: \"HYG\", ratio: \"LQD\", metric: ratio_ret, window: 22, op: lt, value: -2.0}\n"
        "  state path:      {path: \"state.rates.direction\", op: eq, value: rising}\n"
        "  membership:      {path: \"transmission.headwind_for\", op: in_contains, value: \"EM equities\"}\n"
        "  boolean:         {path: \"froth_fragility.unwind_risk\", op: is_true}\n"
        "  AND / OR:        {all: [ {...}, {...} ]}   |   {any: [ {...}, {...} ]}\n"
        "'rs' REQUIRES 'vs'; 'ratio_ret' REQUIRES 'ratio'; a stray companion key is rejected."
    )


def _section_surprises() -> str:
    rows = _load_jsonl(_SURPRISE_QUEUE)
    fresh = [r for r in rows if not r.get("stale", False)]
    lines = [
        "=== UNEXPLAINED-CASCADE SIGNALS — CHF surprise queue ===",
        "Tape anomalies / large forecast misses with NO tracked cascade explaining them. Each is",
        "a candidate seed for a NEW chain — what macro→micro pathway would produce this move?",
    ]
    if not fresh:
        lines.append("  (absent — 0 fresh surprise tickets)")
        return "\n".join(lines)
    for r in fresh[:_MAX_SURPRISE]:
        desc = str(r.get("description", "")).strip()
        fam = r.get("suggested_target_family", "?")
        asof = r.get("source_asof", "?")
        lines.append(f"  - [{fam} | {asof}] {desc}")
    if len(fresh) > _MAX_SURPRISE:
        lines.append(f"  … (+{len(fresh) - _MAX_SURPRISE} more fresh tickets)")
    return "\n".join(lines)


def _iter_lessons() -> list[dict]:
    if not _SHADOW_DIR.exists():
        return []
    out: list[dict] = []
    for led in sorted(_SHADOW_DIR.glob("*/lessons.jsonl")):
        out.extend(_load_jsonl(led))
    return out


def _section_lessons() -> str:
    rows = _iter_lessons()
    # Postmortems of missed / failed moves — the 'what_failed' text is the signal.
    interesting = [r for r in rows if str(r.get("what_failed", "")).strip()]
    lines = [
        "=== MISSED-MOVE POSTMORTEMS — metabolism lessons ledgers ===",
        "What the desk failed to see or verify. A recurring miss is a candidate cascade the",
        "library doesn't yet track. (Postmortem prose only — no authority flows from these.)",
    ]
    if not interesting:
        lines.append("  (absent — 0 lessons with a recorded failure)")
        return "\n".join(lines)
    for r in interesting[:_MAX_LESSONS]:
        what = str(r.get("what_failed", "")).strip().replace("\n", " ")
        if len(what) > 240:
            what = what[:237] + "…"
        verdict = r.get("verdict", "?")
        lines.append(f"  - [{verdict}] {what}")
    if len(interesting) > _MAX_LESSONS:
        lines.append(f"  … (+{len(interesting) - _MAX_LESSONS} more lessons)")
    return "\n".join(lines)


def _section_existing_library() -> str:
    """DO-NOT-REPROPOSE: existing chains rendered by slug + title + node-set summary."""
    try:
        chains = load_chains(ROOT, include_killed=True)
    except Exception as e:  # noqa: BLE001 — the pack must never crash on a bad library file
        return f"=== DO-NOT-REPROPOSE (existing + killed chains) ===\n  (library load error: {e})"
    lines = [
        "=== DO-NOT-REPROPOSE (existing + killed chains) ===",
        "These cascades are ALREADY tracked (or already killed). Propose something with a",
        "DIFFERENT node-set / mechanism — an exact node-set match is dropped as a duplicate.",
    ]
    if not chains:
        lines.append("  (absent — 0 chains in the library)")
        return "\n".join(lines)
    for c in chains:
        slug = c.get("chain", "?")
        title = (c.get("title") or {}).get("en", "") if isinstance(c.get("title"), dict) else ""
        node_ids = ", ".join((c.get("nodes") or {}).keys())
        marker = " [killed]" if c.get("_killed") else (" [proposed]" if c.get("_proposed") else "")
        lines.append(f"  - {slug}{marker}: {title}")
        lines.append(f"      nodes: {node_ids}")
    return "\n".join(lines)


def _section_output_schema(n_requested: int) -> str:
    return f"""\
=== OUTPUT FORMAT (strict) ===
Return a JSON ARRAY only — no prose, no markdown, no explanations outside the JSON.
Propose up to {n_requested} chains. Each element MUST conform to this schema (the W1 chain
schema; see knowledge/transmission/SCHEMA.md). A chain that fails structural validation OR
whose nodes don't resolve is REJECTED — it never becomes a tracked chain.

{{
  "chain": "<stable_slug>",              // lowercase snake_case; becomes the filename stem
  "title": {{"en": "...", "zh": "..."}},   // short bilingual title
  "nodes": {{                             // 2..6 observable boolean states
    "<node_id>": {{
      "src": "<one of the RESOLVABLE adapters>",
      "title": {{"en": "...", "zh": "..."}},
      "test": {{ ... }}                    // per NODE-TEST GRAMMAR above; MUST resolve
    }}
  }},
  "hops": [                              // ordered; hop k connects node k to node k+1
    {{
      "from": "<node_id>", "to": "<node_id>",
      "sign": "+" | "-",
      "lag_d": [lo, hi],                 // confirmation window in CALENDAR days
      "condition": {{"en": "...", "zh": "..."}},  // the regime where the hop should work
      "mechanism": {{"en": "...", "zh": "..."}},  // the causal story
      "prior": "theory (...)"            // strength-prior source; documentary
    }}
  ],
  "falsifiers": [                        // structured falsifiers are auto-checked on an armed episode
    {{"when": {{ ...node-test... }}, "note": "what a fired falsifier means"}}
  ],
  "null_model": "the naive baseline this chain must beat at promotion",
  "exposure_screens": {{}},               // may be {{}} — W2 resolves per-name blast; declared only
  "provenance": {{
    "theory": ["..."], "episodes": ["..."],
    "added_by": "chf_proposal"
  }}
}}

DO NOT set rev / tier / source / proposed_at — the ingest stamps rev:0, tier:hypothesis,
source:chf_proposal, and proposed_at from the pack metadata. DO NOT add any field that
scores, ranks, sizes, gates, or escalates.
"""


# ---------------------------------------------------------------------------
# Pack assembly
# ---------------------------------------------------------------------------

def build_pack(n_requested: int = 12, asof: str | None = None) -> str:
    """Build and return the transmission-chain proposal pack as a string.

    All sections are generated live from committed artifacts + the engine's own resolvable
    inventory. No LLM calls, no file writes (the runner writes the returned string).
    """
    header = [
        "=" * 72,
        "TRANSMISSION-CHAIN PROPOSAL PACK (TXI-W5 Loop C)",
        f"asof: {asof or '(unset)'}   |   requesting up to {n_requested} chains",
        "This pack rides the EXISTING CHF brainstorm lane — it is NOT a second LLM loop.",
        "=" * 72,
    ]
    sections = [
        "\n".join(header),
        _section_role(),
        _section_adapters(),
        _section_series_inventory(),
        _section_state_inventory(),
        _section_test_grammar(),
        _section_surprises(),
        _section_lessons(),
        _section_existing_library(),
        _section_output_schema(n_requested),
        "=" * 72,
        "END OF PACK — paste above into the CHF brainstorm lane; return a JSON array only.",
        "=" * 72,
    ]
    return "\n\n".join(sections)


def build_meta(n_requested: int, asof: str | None, generated_at: str) -> dict:
    """Provenance sidecar so the ingest can stamp proposed_at WITHOUT a clock call."""
    iso_week = None
    if asof:
        try:
            iso_week = "{}-W{:02d}".format(*datetime.fromisoformat(asof).isocalendar()[:2])
        except ValueError:
            iso_week = None
    return {
        "schema": "txi.proposal_pack_meta.v1",
        "pack_id": f"txi-{iso_week or 'nowk'}-proposal",
        "asof": asof,
        "generated_at": generated_at,
        "n_requested": n_requested,
        "iso_week": iso_week,
        # proposed_at is the timestamp the ingest stamps on materialized chains; keep it
        # equal to asof (the data date) when provided, else the generated_at wall time.
        "proposed_at": asof or generated_at,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Emit the TXI-W5 transmission-chain proposal pack.")
    ap.add_argument("--n", type=int, default=12, metavar="N",
                    help="Max number of chains to request (default: 12)")
    ap.add_argument("--asof", type=str, default=None, metavar="YYYY-MM-DD",
                    help="Data date; flows into pack metadata as proposed_at (no clock call). ")
    ap.add_argument("--out", type=Path, default=None, metavar="PATH",
                    help="Write the pack to PATH instead of stdout (the runner's drop location).")
    ap.add_argument("--meta", type=Path, default=None, metavar="PATH",
                    help="Write the provenance sidecar JSON to PATH (pack_id / asof / proposed_at).")
    args = ap.parse_args(argv)

    # generated_at is the wall clock ONLY for provenance stamping of the pack itself; the
    # chains' proposed_at comes from --asof when supplied (see build_meta).
    generated_at = datetime.now(timezone.utc).isoformat()
    pack = build_pack(n_requested=args.n, asof=args.asof)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(pack + "\n", encoding="utf-8")
    else:
        sys.stdout.write(pack)
        sys.stdout.write("\n")

    if args.meta is not None:
        meta = build_meta(args.n, args.asof, generated_at)
        args.meta.parent.mkdir(parents=True, exist_ok=True)
        args.meta.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
