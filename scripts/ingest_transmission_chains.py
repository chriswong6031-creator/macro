"""Ingest CHF-lane transmission-chain proposals → hypothesis-tier YAMLs (TXI-W5 Loop C).

This rides the SHAPE of `scripts/causal_ingest_brainstorm.py` (an --inbox of *.json reply
files, tolerant multi-JSON parse via _parse_json_multi, dry-run DEFAULT with --write as the
explicit opt-in, banned-word check reusing the CHF word list, a rejects ledger) but writes
TRANSMISSION-CHAIN YAMLs, not CHF mechanism cards — the two artifacts and schemas differ, so
this is a sibling ingest, not a call into causal_ingest_brainstorm.ingest().

Flow per candidate chain (a JSON object in the inbox):
  1. sanitize-check banned words on every string leaf (RUL-CC-5, reusing causal_schema).
  2. slug hygiene: 'chain' slug is normalized to a safe stem; the file is named <slug>.yaml
     (the engine validator REQUIRES slug == filename stem).
  3. Article 1/2 guard: reject any candidate carrying an authority field (score/rank/gate/
     size/weight/escalate/conviction/alpha) — a chain never emits authority.
  4. dedup: an exact node-set match against the existing library (incl. proposed/ + killed/)
     is dropped as a duplicate (the same cascade, re-proposed).
  5. materialize the candidate into the W1 chain dict, stamping rev:0, tier:hypothesis,
     source:chf_proposal, proposed_at:<from --proposed-at OR the --meta sidecar; NEVER a
     clock call on the chain>, then run it through the ENGINE validator:
       - engine.transmission_chains.validate_chain (structural — fail-loud) AND
       - a node-resolution pass (evaluate_chain) so an UNRESOLVABLE node (a series/path not
         on disk) rejects the whole chain.
     Any failure → REJECTED to data/transmission/proposal_rejects.jsonl with a reason string;
     the YAML is NEVER written. A valid chain → knowledge/transmission/proposed/<slug>.yaml.

Proposed chains are DISPLAY-TIER and behind promotion: W1 auto-compiles their state and W3
auto-backtests them on the next cycle (the loader now globs proposed/), but they stay
`hypothesis` and never arm on a signal surface / gain authority until a human PR moves them
out of proposed/ (TXI-R5: humans stay at chain-library review + promotion).

Usage:
    python -m scripts.ingest_transmission_chains --inbox DIR [--meta pack.meta.json] \
        [--proposed-at YYYY-MM-DD] [--write]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.transmission_chains as tc  # noqa: E402
from scripts.propose_transmission_chains import _node_signature  # noqa: E402 (DRY: one sig fn)

# Reuse the CHF banned-word list (single source of truth) but not its card structure.
try:
    from engine.neuralweb.causal_schema import _contains_banned  # noqa: E402
except Exception:  # noqa: BLE001 — degrade gracefully if the CHF module moves
    def _contains_banned(text: str) -> list:  # type: ignore[misc]
        return []

_PROPOSED_DIR = ROOT / "knowledge" / "transmission" / "proposed"
_REJECTS_LEDGER = ROOT / "data" / "transmission" / "proposal_rejects.jsonl"

# Article 1/2: a chain NEVER emits authority. Any of these top-level (or nested) keys on a
# candidate is a hard reject — the LLM tried to grant the graph a score/rank/size/gate.
_FORBIDDEN_AUTHORITY_KEYS = frozenset({
    "score", "scores", "rank", "ranking", "gate", "gates", "size", "sizing",
    "weight", "weights", "escalate", "escalation", "conviction", "alpha",
    "signal_strength", "conviction_score", "alpha_score",
})

# Keys the ingest STAMPS — a candidate may not smuggle its own values for these.
_STAMPED_KEYS = ("rev", "tier", "source", "proposed_at")

_SLUG_RE = re.compile(r"[^a-z0-9_]+")


# ---------------------------------------------------------------------------
# Helpers (idiom mirrors causal_ingest_brainstorm)
# ---------------------------------------------------------------------------

def _parse_json_multi(text: str) -> list:
    """Parse a file that may contain one or several concatenated JSON arrays/objects."""
    out: list = []
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


def _slugify(raw: str) -> str:
    s = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    s = _SLUG_RE.sub("", s)
    return s.strip("_")


def _iter_string_leaves(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_string_leaves(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _iter_string_leaves(v)


def _find_forbidden_keys(obj) -> list:
    """Recursively collect any authority FIELD present in the candidate — an authority key
    (score/rank/gate/size/weight/alpha/…) whose value is a SCALAR (number/bool/str). An
    authority field that grants power is always a value, never a container, so a *node id* or
    an *exposure_screen flag* that happens to be named e.g. 'gate'/'size' (its value is the
    node/screen BODY dict) is correctly NOT flagged — only a real scalar authority field is.
    """
    found: list = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if (isinstance(k, str) and k.lower() in _FORBIDDEN_AUTHORITY_KEYS
                    and not isinstance(v, (dict, list, tuple))):
                found.append(k)
            found.extend(_find_forbidden_keys(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            found.extend(_find_forbidden_keys(v))
    return found


def _resolve_proposed_at(meta_path: Path | None, cli_value: str | None) -> str:
    """proposed_at comes from the CLI arg, else the pack meta sidecar's proposed_at/asof,
    else the pack meta generated_at — NEVER a fresh clock read stamped onto the chain.
    (A last-resort wall time is only used when NO provenance is supplied at all, and it is
    logged as such; the caller/runner always passes --meta or --proposed-at in practice.)"""
    if cli_value:
        return cli_value
    if meta_path and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            for key in ("proposed_at", "asof", "generated_at"):
                if meta.get(key):
                    return str(meta[key])
        except (json.JSONDecodeError, OSError):
            pass
    return datetime.now(timezone.utc).date().isoformat()


def _existing_signatures() -> set:
    """Node-set fingerprints of every chain already in the library (seeds + proposed + killed),
    so a re-proposed cascade is dropped."""
    sigs: set = set()
    try:
        for c in tc.load_chains(ROOT, include_killed=True):
            sigs.add(_node_signature(c))
    except Exception:  # noqa: BLE001 — a bad library file must not crash ingest
        pass
    return sigs


def _to_yaml(chain: dict) -> str:
    import yaml
    header = (
        "# TXI-W5 auto-proposed chain (Loop C, source: chf_proposal). HYPOTHESIS-tier,\n"
        "# display-only: W1 compiles its state + W3 backtests it, but it never arms on a\n"
        "# signal surface / gains authority until a human PR promotes it out of proposed/.\n"
        "# Do NOT hand-edit here — re-propose or promote via PR (TXI-R5 / DNR row 45).\n"
    )
    body = yaml.safe_dump(chain, sort_keys=False, allow_unicode=True, width=100)
    return header + body


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def _reject(stats: dict, rejects: list, *, slug: str, reason: str, detail: str = "") -> None:
    stats["rejected"] += 1
    rejects.append({
        "schema": "txi.proposal_reject.v1",
        "slug": slug,
        "reason": reason,
        "detail": detail,
    })
    print(f"  REJECT {slug or '(no-slug)'}: {reason}" + (f" — {detail}" if detail else ""))


def ingest(
    inbox: Path,
    *,
    proposed_at: str,
    write: bool = False,
    ingested_at: str | None = None,
) -> dict:
    """Materialize valid proposed chains to knowledge/transmission/proposed/, reject the rest
    to data/transmission/proposal_rejects.jsonl. Returns a stats dict. FAIL-SOFT: one bad
    candidate never aborts the batch. ``write=False`` (default) is the dry-run: nothing is
    written to disk (no YAMLs, no rejects ledger)."""
    ingested_at = ingested_at or datetime.now(timezone.utc).isoformat()
    stats = {"parsed": 0, "accepted": 0, "rejected": 0, "dup": 0, "dry_run": not write}
    rejects: list = []
    accepted_paths: list = []

    # Gather candidates from every *.json in the inbox (tolerant of multi-JSON files).
    candidates: list = []
    if inbox.exists():
        for jf in sorted(inbox.glob("*.json")):
            try:
                candidates.extend(_parse_json_multi(jf.read_text(encoding="utf-8")))
            except OSError:
                continue
    stats["parsed"] = len(candidates)

    existing_sigs = _existing_signatures()
    seen_this_batch: set = set()
    seen_slugs: set = set()  # slugs accepted earlier in THIS batch (collision guard)

    for raw in candidates:
        if not isinstance(raw, dict):
            _reject(stats, rejects, slug="", reason="not_a_json_object",
                    detail=f"got {type(raw).__name__}")
            continue

        slug = _slugify(raw.get("chain", ""))
        if not slug:
            _reject(stats, rejects, slug="", reason="missing_or_empty_slug",
                    detail=repr(raw.get("chain")))
            continue

        # ---- banned words (RUL-CC-5) ----
        bad_words: set = set()
        for leaf in _iter_string_leaves(raw):
            bad_words.update(_contains_banned(leaf))
        if bad_words:
            _reject(stats, rejects, slug=slug, reason="banned_words",
                    detail=", ".join(sorted(bad_words)))
            continue

        # ---- Article 1/2: no authority field anywhere ----
        forbidden = _find_forbidden_keys(raw)
        if forbidden:
            _reject(stats, rejects, slug=slug, reason="authority_field_forbidden",
                    detail=", ".join(sorted(set(forbidden))))
            continue

        # ---- build the chain dict, stamping the tier/provenance (candidate can't smuggle) ----
        chain = {k: v for k, v in raw.items() if k not in _STAMPED_KEYS}
        chain["chain"] = slug
        chain["rev"] = 0
        chain["tier"] = "hypothesis"
        chain["source"] = "chf_proposal"
        chain["proposed_at"] = proposed_at
        prov = chain.get("provenance")
        if not isinstance(prov, dict):
            prov = {}
        prov.setdefault("added_by", "chf_proposal")
        chain["provenance"] = prov

        filename = f"{slug}.yaml"

        # ---- structural validation (fail-loud on malformed / unknown op / slug≠stem) ----
        try:
            tc.validate_chain(chain, filename)
        except tc.ChainSchemaError as e:
            _reject(stats, rejects, slug=slug, reason="schema_invalid", detail=str(e))
            continue
        except Exception as e:  # noqa: BLE001 — any parse-time surprise is a reject, never a write
            _reject(stats, rejects, slug=slug, reason="validate_error",
                    detail=f"{type(e).__name__}: {e}")
            continue

        # ---- node resolution: an UNRESOLVABLE node (series/path not on disk) rejects ----
        try:
            adapters = tc.build_adapters(ROOT / "data")
            result = tc.evaluate_chain(chain, adapters, asof=proposed_at)
            per_chain = result.get("per_chain", {})
            unresolved = per_chain.get("unresolved_nodes") or []
            if not unresolved:
                # fall back to scanning nodes[] for any not-resolved node (defensive)
                unresolved = [
                    {"id": nd.get("id"), "reason": nd.get("unresolved_reason", "unresolved")}
                    for nd in per_chain.get("nodes", [])
                    if not nd.get("resolved", False) and nd.get("unresolved_reason")
                ]
        except Exception as e:  # noqa: BLE001
            _reject(stats, rejects, slug=slug, reason="resolution_error",
                    detail=f"{type(e).__name__}: {e}")
            continue

        if unresolved:
            detail = "; ".join(f"{u.get('id')}: {u.get('reason')}" for u in unresolved)
            _reject(stats, rejects, slug=slug, reason="unresolvable_node", detail=detail)
            continue

        # ---- dedup: exact node-set match against library OR earlier in this batch ----
        sig = _node_signature(chain)
        if sig in existing_sigs or sig in seen_this_batch:
            stats["dup"] += 1
            _reject(stats, rejects, slug=slug, reason="duplicate_node_set",
                    detail="an existing/earlier chain has the same node-set")
            # note: dup is counted in BOTH stats['dup'] and the reject ledger; it is a reject.
            continue
        # ---- slug-collision guard: a DIFFERENT chain must never clobber an accepted YAML ----
        # (dedup above only catches identical node-sets; two DIFFERENT chains sharing a
        # normalized slug would both "accept" and the second write_text would overwrite the
        # first — silently destroying a distinct proposal awaiting human review, both within
        # a batch and across weekly runs). Refuse the collision instead of overwriting.
        existing_yaml = _PROPOSED_DIR / filename
        collides_on_disk = False
        if existing_yaml.exists():
            try:
                import yaml as _yaml
                prior = _yaml.safe_load(existing_yaml.read_text(encoding="utf-8")) or {}
                collides_on_disk = _node_signature(prior) != sig
            except Exception:  # noqa: BLE001 — an unreadable prior is treated as a collision
                collides_on_disk = True
        if slug in seen_slugs or collides_on_disk:
            _reject(stats, rejects, slug=slug, reason="slug_collision",
                    detail="a different chain already holds this slug in proposed/ "
                           "(same slug, different node-set) — not overwriting")
            continue
        seen_this_batch.add(sig)
        seen_slugs.add(slug)

        # ---- ACCEPT: write the hypothesis-tier YAML ----
        stats["accepted"] += 1
        accepted_paths.append(filename)
        if write:
            _PROPOSED_DIR.mkdir(parents=True, exist_ok=True)
            existing_yaml.write_text(_to_yaml(chain), encoding="utf-8")
        print(f"  ACCEPT {slug}: hypothesis-tier → knowledge/transmission/proposed/{filename}"
              + ("" if write else "  (dry-run — not written)"))

    # ---- rejects ledger (append; write mode only) ----
    if write and rejects:
        _REJECTS_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with _REJECTS_LEDGER.open("a", encoding="utf-8") as fh:
            for r in rejects:
                r = {**r, "proposed_at": proposed_at, "ingested_at": ingested_at}
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    stats["accepted_files"] = accepted_paths
    stats["rejects"] = rejects
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Ingest CHF-lane transmission-chain proposals.")
    ap.add_argument("--inbox", type=Path, required=True,
                    help="Directory of *.json reply files (the CHF lane's chain output).")
    ap.add_argument("--meta", type=Path, default=None,
                    help="Pack provenance sidecar (pack.meta.json) — supplies proposed_at.")
    ap.add_argument("--proposed-at", type=str, default=None, metavar="YYYY-MM-DD",
                    help="Explicit proposed_at stamp (overrides --meta). NEVER a clock call.")
    ap.add_argument("--dry-run", action="store_true", default=True,
                    help="Parse + validate + report, write nothing (DEFAULT).")
    ap.add_argument("--write", action="store_true", default=False,
                    help="Actually write the accepted YAMLs + rejects ledger (opt-in).")
    args = ap.parse_args(argv)

    write = bool(args.write)  # --write overrides the dry-run default
    proposed_at = _resolve_proposed_at(args.meta, args.proposed_at)

    stats = ingest(args.inbox, proposed_at=proposed_at, write=write)
    print(
        f"ingest: parsed={stats['parsed']} accepted={stats['accepted']} "
        f"rejected={stats['rejected']} (dup={stats['dup']}) "
        f"dry_run={stats['dry_run']} proposed_at={proposed_at}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
