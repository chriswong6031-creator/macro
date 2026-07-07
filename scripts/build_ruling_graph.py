"""build_ruling_graph.py — Deterministic compiler for config/ruling_graph.yml.

RUL-CL-1: config/ruling_graph.yml is the single canonical store; this script
produces two deterministic build products:
  - site/neuralwebdata/ruling_graph.json  (public_research rows only, RUL-CL-9)
  - docs/NEURAL_WEB_CASE_LAW.md          (all rows, for git review surface)

RUL-CL-4: Every source_quote is verified to be a verbatim substring of its
source_doc file. Any quote not found causes a HARD failure (exit 1).

RUL-CL-12: The graph itself is display-only (authority_ceiling: A1_EXPLAIN);
this script never gates, ranks, or scores anything.

Usage
-----
  python scripts/build_ruling_graph.py           # build + write outputs
  python scripts/build_ruling_graph.py --check   # regenerate to temp, diff, exit 1 on mismatch
  python scripts/build_ruling_graph.py --root /path/to/repo
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_RULING_GRAPH_YML = ROOT / "config" / "ruling_graph.yml"
_OUT_JSON = ROOT / "site" / "neuralwebdata" / "ruling_graph.json"
_OUT_MD = ROOT / "docs" / "NEURAL_WEB_CASE_LAW.md"
_EXPERIMENTS_REGISTRY = ROOT / "data" / "experiments" / "registry_seed.json"


# ---------------------------------------------------------------------------
# Vocabulary (must match meta in ruling_graph.yml; RUL-CL-2)
# ---------------------------------------------------------------------------
_VALID_STATUSES = frozenset({
    "active_law", "adopted", "residue_adopted", "deferred", "killed",
    "no_build", "duplicate", "blocked", "superseded",
})
_VALID_OBJECT_KINDS = frozenset({
    "constitution", "process", "lobe", "rail", "wave", "study", "context",
    "data_contract", "signal_family",
})
_VALID_AUTHORITY = frozenset({
    "A0_OBSERVE", "A1_EXPLAIN", "A2_ATTEND", "A3_DE_ESCALATE",
    "A4_QUARANTINE", "A5_GOVERN_TIERS", "A6_TUNE", "A7_ORIGINATE",
})
_VALID_PRIVACY = frozenset({"public_research", "internal_only"})
_VALID_PRECEDENCE_RANKS = frozenset(range(1, 8))  # 1..7 (RUL-CL-5)

# Statuses that require a quote-verified ruling (for W1/dead-idea scan)
_DEAD_STATUSES = frozenset({"killed", "no_build", "deferred", "duplicate", "blocked"})

# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _load_yml(yml_path: Path) -> dict:
    with yml_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_experiment_ids(path: Path) -> set[str]:
    """Load experiment ids from data/experiments/registry_seed.json.  Returns empty set on error."""
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_bytes())
        return {e["id"] for e in data.get("experiments", []) if "id" in e}
    except Exception:
        return set()


# ---------------------------------------------------------------------------
# Validator (HARD exits on error)
# ---------------------------------------------------------------------------

def validate(data: dict, root: Path) -> list[str]:
    """Return list of HARD error messages.  Empty list = clean.

    Does NOT call sys.exit; caller decides how to handle.
    """
    errors: list[str] = []
    meta = data.get("meta", {})
    rulings: list[dict] = data.get("rulings", [])

    public_denylist: list[str] = [t.lower() for t in meta.get("public_token_denylist", [])]
    known_fdr_families: set[str] = set(meta.get("known_fdr_families", []))

    # --- unique ruling_ids (RUL-CL-3) ---
    seen_ids: set[str] = set()
    dup_ids: list[str] = []
    for r in rulings:
        rid = r.get("ruling_id", "")
        if rid in seen_ids:
            dup_ids.append(rid)
        seen_ids.add(rid)
    if dup_ids:
        errors.append(f"HARD: duplicate ruling_ids: {dup_ids}")

    # Build index for supersession checks
    valid_ids = seen_ids

    # Load experiment registry for RUL-CL-8 HARD check
    exp_ids = _load_experiment_ids(root / "data" / "experiments" / "registry_seed.json")

    for r in rulings:
        rid = r.get("ruling_id", "<missing>")
        prefix = f"[{rid}]"

        # --- vocab: status (RUL-CL-2) ---
        status = r.get("status")
        if status not in _VALID_STATUSES:
            errors.append(f"HARD {prefix}: status {status!r} not in valid vocab")

        # --- vocab: object_kind (RUL-CL-2) ---
        ok = r.get("object_kind")
        if ok not in _VALID_OBJECT_KINDS:
            errors.append(f"HARD {prefix}: object_kind {ok!r} not in valid vocab")

        # --- vocab: authority_ceiling (nullable) ---
        ac = r.get("authority_ceiling")
        if ac is not None and ac not in _VALID_AUTHORITY:
            errors.append(f"HARD {prefix}: authority_ceiling {ac!r} not in valid vocab")

        # --- vocab: privacy_class (RUL-CL-9) ---
        pc = r.get("privacy_class")
        if pc not in _VALID_PRIVACY:
            errors.append(f"HARD {prefix}: privacy_class {pc!r} not in valid vocab")

        # --- owner_program required (docs page groups by owner) ---
        if not r.get("owner_program"):
            errors.append(f"HARD {prefix}: owner_program is missing or null")

        # --- fdr_family must be registered in meta.known_fdr_families ---
        # (keeps H1's generated-artifact exclusion in check_ruling_conflicts sound)
        fam = r.get("fdr_family")
        if fam is not None and fam not in known_fdr_families:
            errors.append(
                f"HARD {prefix}: fdr_family {fam!r} not in meta.known_fdr_families"
            )

        # --- precedence_rank in 1..7 (RUL-CL-5) ---
        pr = r.get("precedence_rank")
        if pr not in _VALID_PRECEDENCE_RANKS:
            errors.append(f"HARD {prefix}: precedence_rank {pr!r} must be int in 1..7")

        # --- source_quote verbatim in source_doc (RUL-CL-4) ---
        sq = r.get("source_quote")
        sd = r.get("source_doc")
        if sq and sd:
            src_path = root / sd
            if not src_path.exists():
                errors.append(f"HARD {prefix}: source_doc not found: {sd}")
            else:
                src_text = src_path.read_text(encoding="utf-8", errors="replace")
                # Normalize whitespace for folded-block comparison
                sq_norm = " ".join(sq.split())
                src_norm = " ".join(src_text.split())
                if sq_norm not in src_norm:
                    errors.append(
                        f"HARD {prefix}: source_quote not found verbatim in {sd}. "
                        f"First 80 chars of quote: {sq_norm[:80]!r}"
                    )
        elif not sq:
            errors.append(f"HARD {prefix}: source_quote is missing (RUL-CL-4)")
        elif not sd:
            errors.append(f"HARD {prefix}: source_doc is missing")

        # --- supersedes/superseded_by reference existing ids ---
        for ref_id in (r.get("supersedes") or []):
            if ref_id and ref_id not in valid_ids:
                errors.append(f"HARD {prefix}: supersedes references unknown ruling_id {ref_id!r}")
        for ref_id in (r.get("superseded_by") or []):
            if ref_id and ref_id not in valid_ids:
                errors.append(f"HARD {prefix}: superseded_by references unknown ruling_id {ref_id!r}")

        # --- RUL-CL-8: clocked rows + experiment_ref ---
        cbo = r.get("come_back_on")
        eref = r.get("experiment_ref")
        if cbo and eref and eref not in exp_ids:
            errors.append(
                f"HARD {prefix}: experiment_ref {eref!r} not found in "
                f"data/experiments/registry_seed.json (RUL-CL-8)"
            )

        # --- RUL-CL-9: public rows must not contain denylist tokens ---
        if pc == "public_research" and public_denylist:
            # Serialize the full row and check for denylist tokens
            row_text = json.dumps(r, ensure_ascii=False).lower()
            for token in public_denylist:
                if token.lower() in row_text:
                    errors.append(
                        f"HARD {prefix}: public row contains denylist token {token!r} "
                        f"(RUL-CL-9 — competitor/held-book vocabulary forbidden in public rows)"
                    )

    return errors


def warn_checks(data: dict, root: Path) -> None:
    """Emit WARN messages to stderr for soft issues.  Never fatal."""
    rulings: list[dict] = data.get("rulings", [])
    for r in rulings:
        rid = r.get("ruling_id", "<missing>")
        cbo = r.get("come_back_on")
        eref = r.get("experiment_ref")
        # RUL-CL-8 WARN: clocked row with no experiment_ref
        if cbo and not eref:
            print(
                f"  [WARN] [{rid}]: come_back_on={cbo!r} but experiment_ref is null "
                f"(RUL-CL-8 — prefer experiments registry entry for clocks)",
                file=sys.stderr,
            )


# ---------------------------------------------------------------------------
# Emitters (byte-deterministic — no timestamps; source_sha256 instead)
# ---------------------------------------------------------------------------

def _emit_json(data: dict, yml_path: Path) -> str:
    """Generate site JSON (public_research rows only, RUL-CL-9).

    Returns the JSON string (not written to disk here).
    """
    meta = data.get("meta", {})
    rulings: list[dict] = data.get("rulings", [])

    source_sha256 = _sha256_file(yml_path)
    public_rows = [r for r in rulings if r.get("privacy_class") == "public_research"]

    out = {
        "schema": meta.get("schema", "neuralweb.ruling_graph.v1"),
        "source_sha256": source_sha256,
        "precedence_order": meta.get("precedence_order", []),
        "n_rulings_total": len(rulings),
        "n_rulings_public": len(public_rows),
        "rulings": public_rows,
    }
    return json.dumps(out, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def _format_row_md(r: dict) -> str:
    """Format a single ruling row as a compact markdown section."""
    rid = r.get("ruling_id", "")
    title = r.get("title", "")
    status = r.get("status", "")
    ok = r.get("object_kind", "")
    ruling_text = r.get("ruling", "").strip()
    scope = (r.get("scope_fence") or "").strip()
    forbidden = r.get("forbidden_actions") or []
    unblock = (r.get("unblock_condition") or "").strip()
    cbo = r.get("come_back_on")
    eref = r.get("experiment_ref")
    sd = r.get("source_doc", "")
    sq = " ".join((r.get("source_quote") or "").split())
    sup = r.get("supersedes") or []
    supby = r.get("superseded_by") or []
    nondelegable = r.get("nondelegable", False)

    lines = [
        f"### {rid}",
        "",
        f"**{title}**",
        "",
        f"- Status: `{status}` | Kind: `{ok}` | Nondelegable: `{nondelegable}`",
    ]
    ac = r.get("authority_ceiling")
    if ac:
        lines.append(f"- Authority ceiling: `{ac}`")
    lines.append("")
    lines.append(f"**Ruling:** {ruling_text}")

    if scope:
        lines += ["", f"**Scope fence:** {scope}"]

    if forbidden:
        lines += ["", "**Forbidden actions:**"]
        for fa in forbidden:
            lines.append(f"  - {fa}")

    if unblock:
        lines += ["", f"**Unblock condition:** {unblock}"]

    if cbo:
        clock_str = f"**Come back on:** {cbo}"
        if eref:
            clock_str += f" (experiment: `{eref}`)"
        lines += ["", clock_str]

    lines += ["", f"**Source:** `{sd}`"]
    if sq:
        lines += [f"> {sq}"]

    if sup:
        lines += ["", f"**Supersedes:** {', '.join(f'`{x}`' for x in sup)}"]
    if supby:
        lines += ["", f"**Superseded by:** {', '.join(f'`{x}`' for x in supby)}"]

    owner = r.get("owner_program", "")
    lines += ["", f"*Owner program: {owner}*", ""]
    return "\n".join(lines)


def _emit_md(data: dict, yml_path: Path) -> str:
    """Generate docs/NEURAL_WEB_CASE_LAW.md (all rows).

    Returns the markdown string (not written to disk).
    """
    meta = data.get("meta", {})
    rulings: list[dict] = data.get("rulings", [])
    source_sha256 = _sha256_file(yml_path)

    lines: list[str] = []

    # Header
    lines += [
        "<!-- DO NOT EDIT BY HAND — regenerate with: python3 scripts/build_ruling_graph.py -->",
        "<!-- Source: config/ruling_graph.yml -->",
        f"<!-- source_sha256: {source_sha256} -->",
        "",
        "# Neural Web Case Law",
        "",
        "> This document is a generated reference for all rulings in the ruling graph.",
        "> It is the git-side review surface (all rows, including internal_only).",
        "> The public site JSON at `site/neuralwebdata/ruling_graph.json` carries",
        "> only `public_research` rows.",
        "",
        f"Total rulings: {len(rulings)}",
        "",
    ]

    # Precedence legend
    lines += ["## Precedence Order", ""]
    for i, p in enumerate(meta.get("precedence_order", []), start=1):
        lines.append(f"{i}. `{p}`")
    lines.append("")

    # Vocabulary legend
    lines += [
        "## Vocabulary",
        "",
        "### Status",
        "",
    ]
    for s in meta.get("status_vocab", []):
        lines.append(f"- `{s}`")
    lines += ["", "### Object Kind", ""]
    for ok in meta.get("object_kind_vocab", []):
        lines.append(f"- `{ok}`")
    lines += ["", "### Authority", ""]
    for a in meta.get("authority_vocab", []):
        lines.append(f"- `{a}`")
    lines.append("")

    # Index table
    lines += [
        "## Index",
        "",
        "| ID | Title | Status | Kind | Owner |",
        "|---|---|---|---|---|",
    ]
    for r in rulings:
        rid = r.get("ruling_id", "")
        title = r.get("title", "")
        if len(title) > 60:
            # cut at a word boundary so truncation never splits a token
            # (a mid-token cut once produced a phantom fdr_family for H1)
            title = title[:60].rsplit(" ", 1)[0] + "…"
        status = r.get("status", "")
        ok = r.get("object_kind", "")
        owner = r.get("owner_program", "")
        lines.append(f"| [{rid}](#{rid.lower().replace('-', '-')}) | {title} | `{status}` | `{ok}` | {owner} |")
    lines.append("")

    # Group by owner_program
    by_owner: dict[str, list[dict]] = defaultdict(list)
    for r in rulings:
        owner = r.get("owner_program", "unknown")
        by_owner[owner].append(r)

    lines += ["## Rulings by Owner Program", ""]
    for owner in sorted(by_owner.keys(), key=lambda k: (k is None, k or "")):
        rows = by_owner[owner]
        lines += [f"### {owner}", ""]
        for r in rows:
            lines.append(_format_row_md(r))
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build(root: Path = ROOT, yml_path: Path | None = None) -> tuple[str, str]:
    """Load, validate, and generate outputs.  Returns (json_str, md_str).

    Calls sys.exit(1) on HARD validation errors.
    """
    if yml_path is None:
        yml_path = root / "config" / "ruling_graph.yml"

    data = _load_yml(yml_path)

    errors = validate(data, root)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print(f"\n::error::build_ruling_graph: {len(errors)} HARD error(s). Fix before merging.",
              file=sys.stderr)
        sys.exit(1)

    warn_checks(data, root)

    json_str = _emit_json(data, yml_path)
    md_str = _emit_md(data, yml_path)
    return json_str, md_str


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--root", type=Path, default=ROOT,
        help="Repo root (default: parent of scripts/)",
    )
    ap.add_argument(
        "--check", action="store_true",
        help="Regenerate to temp files and diff; exit 1 on mismatch (for CI/tests)",
    )
    args = ap.parse_args()

    root = args.root.resolve()
    yml_path = root / "config" / "ruling_graph.yml"
    out_json = root / "site" / "neuralwebdata" / "ruling_graph.json"
    out_md = root / "docs" / "NEURAL_WEB_CASE_LAW.md"

    json_str, md_str = build(root=root, yml_path=yml_path)

    if args.check:
        ok = True

        # Check JSON
        if out_json.exists():
            committed_json = out_json.read_text(encoding="utf-8")
            if committed_json != json_str:
                print(
                    f"::error::MISMATCH: {out_json} is out of date with {yml_path}.\n"
                    f"Run: python3 scripts/build_ruling_graph.py",
                    file=sys.stderr,
                )
                ok = False
            else:
                print(f"OK: {out_json} is up to date")
        else:
            print(f"::error::MISSING: {out_json} does not exist; run build first.", file=sys.stderr)
            ok = False

        # Check MD
        if out_md.exists():
            committed_md = out_md.read_text(encoding="utf-8")
            if committed_md != md_str:
                print(
                    f"::error::MISMATCH: {out_md} is out of date with {yml_path}.\n"
                    f"Run: python3 scripts/build_ruling_graph.py",
                    file=sys.stderr,
                )
                ok = False
            else:
                print(f"OK: {out_md} is up to date")
        else:
            print(f"::error::MISSING: {out_md} does not exist; run build first.", file=sys.stderr)
            ok = False

        return 0 if ok else 1

    # Write outputs
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json_str, encoding="utf-8")
    print(f"wrote {out_json}")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md_str, encoding="utf-8")
    print(f"wrote {out_md}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
