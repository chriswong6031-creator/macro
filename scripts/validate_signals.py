"""Validate the signal-engine outputs against the §7 signal→chart contract.

The signal engine writes two shapes (CHARTER §7): per-ticker chart-marker files
site/signals/<TICKER>.json and the brain leaf data/signal_archive/mtf_signals_latest.json.
research/signal_engine/SCHEMA.json is the SINGLE SOURCE OF TRUTH for both — shared verbatim
with the charting web-app so the two workstreams can never drift.

This is a SAFETY GATE, not signal logic: it asserts every emitted file matches the schema AND
two cross-field rules the schema can't express as cleanly:
  1. markers within a file are strictly date-sorted ascending;
  2. `quality` appears ONLY on buy/rebuy markers (never sell/cut).
It writes data/quality/signals_audit.json {asof, files_checked, n_markers, errors:[...]} and
exits non-zero with a clear message on ANY violation, so a malformed write aborts the build
(wired right after scripts/build_signal_quality.py in .github/workflows/daily.yml).
"""
from __future__ import annotations

import sys
import json
import glob
import argparse
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "research" / "signal_engine" / "SCHEMA.json"
SIGNALS_DIR = ROOT / "site" / "signals"
LEAF_PATH = ROOT / "data" / "signal_archive" / "mtf_signals_latest.json"
AUDIT_PATH = ROOT / "data" / "quality" / "signals_audit.json"

_QUALITY_TYPES = {"buy", "rebuy"}   # the only marker types that may carry `quality`


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    return json.loads(Path(path).read_text())


def _validator_for(schema: dict, defname: str) -> Draft202012Validator:
    """A validator that checks a document against schema['$defs'][defname].

    The wrapper keeps `$defs` in-document so the internal `$ref`s resolve, and pins the root
    to the chosen definition via allOf. format_checker enables real `date` validation.
    """
    root = dict(schema)
    root["allOf"] = [{"$ref": f"#/$defs/{defname}"}]
    return Draft202012Validator(root, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _schema_errors(validator: Draft202012Validator, doc, where: str) -> list[str]:
    out = []
    for e in sorted(validator.iter_errors(doc), key=lambda x: list(x.absolute_path)):
        loc = "/".join(str(p) for p in e.absolute_path) or "(root)"
        out.append(f"{where}: schema: at {loc}: {e.message}")
    return out


def check_markers(markers: list, where: str) -> list[str]:
    """Cross-field rules over a marker list: quality-placement + strict ascending dates.

    Schema validation should run first; this layer adds clearer, contract-specific messages
    and the ordering check (which JSON Schema cannot express). Defensive against shapes the
    schema already rejected so a single bad file yields one clear error, not a stack trace.
    """
    out: list[str] = []
    prev_date = None
    prev_raw = None
    for i, m in enumerate(markers):
        if not isinstance(m, dict):
            continue  # schema already flagged it
        mtype = m.get("type")
        # Rule 2: `quality`/`reason` are buy-filter verdict fields — present on buy/rebuy ONLY,
        # and REQUIRED there (the chart reads quality to render solid/hollow/provisional).
        if mtype in _QUALITY_TYPES:
            if "quality" not in m:
                out.append(f"{where}: markers[{i}]: `quality` missing on type '{mtype}' "
                           f"(required on buy/rebuy — must be take | block | pending)")
        else:
            if "quality" in m:
                out.append(f"{where}: markers[{i}]: `quality` present on type '{mtype}' "
                           f"(allowed only on buy/rebuy)")
            if "reason" in m:
                out.append(f"{where}: markers[{i}]: `reason` present on type '{mtype}' "
                           f"(allowed only on buy/rebuy)")
        # Rule 1: strict ascending dates (each 3D bar emits at most one marker).
        raw = m.get("date")
        if not isinstance(raw, str):
            continue  # schema already flagged non-string date
        try:
            cur = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            out.append(f"{where}: markers[{i}]: date '{raw}' is not a valid YYYY-MM-DD date")
            continue
        if prev_date is not None and not (cur > prev_date):
            out.append(f"{where}: markers[{i}]: date '{raw}' not strictly after "
                       f"previous marker '{prev_raw}' (markers must be date-sorted ascending)")
        prev_date, prev_raw = cur, raw
    return out


def check_date_list(dates: list, where: str, field: str) -> list[str]:
    """A bare ascending date-string list (e.g. `risk_flags`) — valid dates, strictly ascending.

    risk_flags is the display-only trail-breach layer (kept OUT of `markers`); the schema declares
    it ascending, which JSON Schema cannot assert — so the gate enforces it here.
    """
    out: list[str] = []
    prev = prev_raw = None
    for i, raw in enumerate(dates):
        if not isinstance(raw, str):
            continue  # schema already flagged a non-string
        try:
            cur = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            out.append(f"{where}: {field}[{i}]: '{raw}' is not a valid YYYY-MM-DD date")
            continue
        if prev is not None and not (cur > prev):
            out.append(f"{where}: {field}[{i}]: '{raw}' not strictly after previous '{prev_raw}' "
                       f"({field} must be date-sorted ascending)")
        prev, prev_raw = cur, raw
    return out


def validate_ticker_doc(doc, schema: dict, where: str) -> list[str]:
    errs = _schema_errors(_validator_for(schema, "perTicker"), doc, where)
    if isinstance(doc, dict):
        if isinstance(doc.get("markers"), list):
            errs += check_markers(doc["markers"], where)
        if isinstance(doc.get("risk_flags"), list):
            errs += check_date_list(doc["risk_flags"], where, "risk_flags")
        if isinstance(doc.get("early_markers"), list):
            errs += check_date_list(doc["early_markers"], where, "early_markers")
    return errs


def validate_brain_leaf(doc, schema: dict, where: str) -> list[str]:
    errs = _schema_errors(_validator_for(schema, "brainLeaf"), doc, where)
    if isinstance(doc, dict) and isinstance(doc.get("signals"), list):
        for s in doc["signals"]:
            if isinstance(s, dict) and isinstance(s.get("last"), dict):
                # `last` is a single marker — same quality-placement / date-validity rules.
                tkr = s.get("ticker", "?")
                errs += check_markers([s["last"]], f"{where}: signal {tkr}.last")
    return errs


def run(signals_dir: Path = SIGNALS_DIR, leaf_path: Path = LEAF_PATH,
        audit_path: Path = AUDIT_PATH, schema_path: Path = SCHEMA_PATH) -> int:
    schema = load_schema(schema_path)
    errors: list[str] = []
    files_checked = 0
    n_markers = 0
    asof = None
    file_stems: set[str] = set()

    # Per-ticker chart-marker files.
    for fp in sorted(glob.glob(str(Path(signals_dir) / "*.json"))):
        files_checked += 1
        file_stems.add(Path(fp).stem)
        rel = str(Path(fp).relative_to(ROOT)) if str(fp).startswith(str(ROOT)) else fp
        try:
            doc = json.loads(Path(fp).read_text())
        except json.JSONDecodeError as e:
            errors.append(f"{rel}: not valid JSON ({e})")
            continue
        if isinstance(doc, dict) and isinstance(doc.get("markers"), list):
            n_markers += len(doc["markers"])
        errors += validate_ticker_doc(doc, schema, rel)

    # Brain leaf.
    leaf_path = Path(leaf_path)
    if leaf_path.exists():
        files_checked += 1
        rel = str(leaf_path.relative_to(ROOT)) if str(leaf_path).startswith(str(ROOT)) else str(leaf_path)
        try:
            leaf = json.loads(leaf_path.read_text())
            if isinstance(leaf, dict):
                asof = leaf.get("asof")
            errors += validate_brain_leaf(leaf, schema, rel)
            # Cross-shape consistency: every ticker the leaf claims MUST have its per-ticker
            # marker file (build_signal_quality writes both together). Catches a partial/
            # inconsistent write where the leaf lists names whose chart file never landed. We
            # only require leaf ⊆ files (NOT the reverse) so a stale extra file from a shrunk
            # universe doesn't false-fail the build.
            if isinstance(leaf, dict) and isinstance(leaf.get("signals"), list):
                leaf_tickers = {s.get("ticker") for s in leaf["signals"]
                                if isinstance(s, dict) and s.get("ticker")}
                for t in sorted(leaf_tickers - file_stems):
                    errors.append(f"{rel}: brain leaf lists ticker '{t}' but its per-ticker file "
                                  f"{t}.json is missing (partial/inconsistent write)")
        except json.JSONDecodeError as e:
            errors.append(f"{rel}: not valid JSON ({e})")
    else:
        errors.append(f"brain leaf missing: {leaf_path}")

    audit = {"asof": asof, "files_checked": files_checked,
             "n_markers": n_markers, "errors": errors}
    audit_path = Path(audit_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, indent=1))

    if errors:
        print(f"signal contract VIOLATED — {len(errors)} error(s) across {files_checked} "
              f"file(s); see {audit_path.relative_to(ROOT) if str(audit_path).startswith(str(ROOT)) else audit_path}",
              file=sys.stderr)
        for e in errors[:40]:
            print(f"  - {e}", file=sys.stderr)
        if len(errors) > 40:
            print(f"  ... and {len(errors) - 40} more", file=sys.stderr)
        return 1
    print(f"signal contract OK — {files_checked} file(s), {n_markers} markers validated "
          f"against {schema_path.name} (asof {asof})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate signal-engine outputs against the §7 contract.")
    ap.add_argument("--signals-dir", default=str(SIGNALS_DIR))
    ap.add_argument("--leaf", default=str(LEAF_PATH))
    ap.add_argument("--audit", default=str(AUDIT_PATH))
    ap.add_argument("--schema", default=str(SCHEMA_PATH))
    a = ap.parse_args(argv)
    return run(Path(a.signals_dir), Path(a.leaf), Path(a.audit), Path(a.schema))


if __name__ == "__main__":
    sys.exit(main())
