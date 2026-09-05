"""scripts/build_capability_health.py — F13 V1 adapter for engine.capability_health.

THE ADAPTER, NOT THE CONTRACT. Every rule about what a capability's state MEANS lives in
the pure resolver :mod:`engine.capability_health`; this file only goes and looks, exactly
the way ``scripts/build_output_health.py`` relates to ``engine/output_health.py``.

RECEIPT SOURCES, PER TYPE
--------------------------
``output_health_artifact``
    Composed READ-ONLY off :func:`scripts.build_output_health.build` — the same public
    entry point ``admin/intelligence_os.py`` calls. Neither ``engine/output_health.py``
    nor ``scripts/build_output_health.py`` is edited by F13; this module only imports and
    reads their already-resolved view. The already-judged ``state``/``assessment_status``
    ride through verbatim (an ``output_health_artifact`` fact is an upstream VERDICT, not
    raw clocks — see the engine module's docstring on why that fold never re-derives it).
``nightly_lane``
    Read from ``data/run_status.json``: a named key under ``sources`` (per-source
    ``status``/``checked_at``/``last_date``), or the literal ``__global__`` for the
    top-level ``last_run`` heartbeat. ``__global__`` NEVER supplies ``last_successful`` —
    ``scripts/collect.py`` writes ``last_run`` unconditionally once the collect pass
    reaches that line, so it proves an attempt reached that point, never a verified
    success (see the registry's own comment on this).
``provider_rung`` / ``sentinel_probe``
    Declared in the closed receipt-source vocabulary and accepted by registry
    validation, but NOT wired to a live fetch in this V1 build: none of the seed cohort's
    five capabilities declares one (see ``config/capability_health.yml``'s header
    comment for the two commission candidates dropped for lack of a verifiable receipt).
    Additive later, per the frozen commission's "5-8 entries is right; additive later".

WRITES ONE ARTIFACT. Deterministic, no network, no GH API. Default output path is
``data/capability_health/state.json`` under ``--root`` — the production nightly default.
``--out`` and ``--receipts-root`` exist so a sparse worktree or a test can point both the
destination and the receipt reads somewhere that is never ``data/`` or ``site/``.

Usage
-----
  python3 scripts/build_capability_health.py --summary
  python3 scripts/build_capability_health.py --out /tmp/state.json --receipts-root /tmp/rr
  python3 scripts/build_capability_health.py --now 2026-09-04T00:00:00+00:00 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from engine.capability_health import (  # noqa: E402
    resolve_capability_health,
    validate_registry,
)

REGISTRY_REL = Path("config") / "capability_health.yml"
DEFAULT_OUT_REL = Path("data") / "capability_health" / "state.json"
RUN_STATUS_REL = Path("data") / "run_status.json"

_KNOWN_TYPES_WITH_LOADERS = {"output_health_artifact", "nightly_lane"}


def _load_yaml(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return doc if isinstance(doc, dict) else None


def _load_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def load_registry(root: Path) -> list[dict[str, Any]]:
    """The parsed ``capabilities`` list, or ``[]`` when the registry is unreadable."""
    doc = _load_yaml(root / REGISTRY_REL)
    if not isinstance(doc, dict):
        return []
    return [c for c in (doc.get("capabilities") or []) if isinstance(c, dict)]


def output_health_facts(
    root: Path, refs: list[str], *, now: datetime
) -> dict[str, dict[str, Any]]:
    """One fact per requested ``output_health_artifact`` id.

    Composed off :func:`scripts.build_output_health.build` — reads only, never edits
    output_health's own modules. A refused/missing/crashed build resolves every requested
    ref to ``readable=False`` rather than raising: a receipt source must never be able to
    take down the whole capability-health build.
    """
    if not refs:
        return {}
    from scripts import build_output_health as OH_BUILD  # noqa: PLC0415

    try:
        view = OH_BUILD.build(root, now=now, limit_artifacts=sorted(set(refs)))
    except SystemExit:
        return {ref: {"readable": False} for ref in refs}
    except Exception:  # noqa: BLE001 — a receipt source must never crash the build
        return {ref: {"readable": False} for ref in refs}

    by_id = {row.get("artifact_id"): row for row in view.get("outputs") or []}
    out: dict[str, dict[str, Any]] = {}
    for ref in refs:
        rec = by_id.get(ref)
        if rec is None:
            out[ref] = {"readable": False}
            continue
        out[ref] = {
            "readable": True,
            "corrupt": False,
            "state": rec.get("state"),
            "assessment_status": rec.get("assessment_status"),
            "data_as_of": rec.get("source_asof"),
        }
    return out


def nightly_lane_facts(receipts_root: Path, refs: list[str]) -> dict[str, dict[str, Any]]:
    """One fact per requested ``nightly_lane`` ref, from ``data/run_status.json``."""
    doc = _load_json(receipts_root / RUN_STATUS_REL)
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(doc, dict):
        for ref in refs:
            out[ref] = {"readable": False}
        return out
    sources = doc.get("sources") if isinstance(doc.get("sources"), dict) else {}
    for ref in refs:
        if ref == "__global__":
            last_run = doc.get("last_run")
            out[ref] = (
                {"readable": False}
                if not last_run
                else {"readable": True, "corrupt": False, "last_attempted": last_run}
            )
            continue
        entry = sources.get(ref)
        if not isinstance(entry, dict):
            out[ref] = {"readable": False}
            continue
        status = str(entry.get("status") or "")
        checked_at = entry.get("checked_at")
        fact: dict[str, Any] = {"readable": True, "corrupt": False}
        if checked_at:
            fact["last_attempted"] = checked_at
            if status == "ok":
                fact["last_successful"] = checked_at
        if entry.get("last_date"):
            fact["data_as_of"] = entry.get("last_date")
        out[ref] = fact
    return out


def gather_receipts(
    root: Path,
    capabilities: list[dict[str, Any]],
    *,
    now: datetime,
    receipts_root: Path,
) -> dict[str, list[dict[str, Any] | None]]:
    """Every declared receipt source, read exactly once per unique ref."""
    oh_refs: list[str] = []
    lane_refs: list[str] = []
    for cap in capabilities:
        for decl in cap.get("receipt_sources") or []:
            if not isinstance(decl, dict):
                continue
            typ, ref = decl.get("type"), decl.get("ref")
            if not isinstance(ref, str):
                continue
            if typ == "output_health_artifact":
                oh_refs.append(ref)
            elif typ == "nightly_lane":
                lane_refs.append(ref)

    oh_facts = output_health_facts(root, oh_refs, now=now)
    lane_facts = nightly_lane_facts(receipts_root, lane_refs)

    receipts: dict[str, list[dict[str, Any] | None]] = {}
    for cap in capabilities:
        cid = str(cap.get("id"))
        facts: list[dict[str, Any] | None] = []
        for decl in cap.get("receipt_sources") or []:
            if not isinstance(decl, dict):
                facts.append({"readable": False})
                continue
            typ, ref = decl.get("type"), decl.get("ref")
            if typ == "output_health_artifact":
                facts.append(oh_facts.get(ref, {"readable": False}))
            elif typ == "nightly_lane":
                facts.append(lane_facts.get(ref, {"readable": False}))
            else:
                # provider_rung / sentinel_probe / an unknown type — no live loader in
                # V1 (see module docstring). An absent fact reads as unreadable; the
                # resolver never invents a verdict for a source it cannot fetch.
                facts.append({"readable": False})
        receipts[cid] = facts
    return receipts


def build(
    root: Path,
    *,
    now: datetime,
    receipts_root: Path | None = None,
    previous: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Gather receipts and resolve. Reads only; writes nothing. Deterministic, no network."""
    capabilities = load_registry(root)

    for problem in validate_registry(capabilities):
        # GitHub annotation law (CLAUDE.md §Ops): bare print, NEVER a logger — a
        # log.warning(...) call here would swallow the "::warning" prefix and GitHub
        # would silently drop the annotation.
        print(f"::warning title=capability_health_registry::{problem}", flush=True)

    rroot = receipts_root if receipts_root is not None else root
    receipts = gather_receipts(root, capabilities, now=now, receipts_root=rroot)
    return resolve_capability_health(
        capabilities=capabilities, receipts=receipts, previous=previous, now=now
    )


def render_summary(view: dict[str, Any]) -> str:
    summary = view["summary"]
    lines = [
        f"capability health ({view['schema']}) — {summary['n_capabilities']} capabilities, "
        f"observed_at {view['generated']['observed_at']}",
        f"  state:      {summary['by_state']}",
        f"  assessment: {summary['by_assessment_status']}",
    ]
    if summary["reason_codes"]:
        top = sorted(summary["reason_codes"].items(), key=lambda kv: (-kv[1], kv[0]))[:12]
        lines.append("  top reason codes:")
        lines += [f"    {count:>5}  {code}" for code, count in top]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--receipts-root", type=Path, default=None,
        help="override where receipt files (data/run_status.json, ...) are read from "
             "— sparse worktrees / tests / evidence runs",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="output artifact path; default <root>/data/capability_health/state.json",
    )
    parser.add_argument(
        "--now", default=None,
        help="ISO instant to resolve against (offset-bearing); default now(UTC)",
    )
    parser.add_argument("--json", action="store_true", help="also print the full JSON view")
    parser.add_argument("--summary", action="store_true", help="print the summary only; skip the write")
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc) if args.now is None else datetime.fromisoformat(args.now)
    view = build(args.root, now=now, receipts_root=args.receipts_root)

    if args.summary:
        print(render_summary(view))
        return 0

    out_path = args.out if args.out is not None else (args.root / DEFAULT_OUT_REL)
    text = json.dumps(view, indent=2, sort_keys=True, default=str)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    tmp.replace(out_path)

    print(render_summary(view))
    if args.json:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
