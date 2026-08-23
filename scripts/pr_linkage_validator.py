#!/usr/bin/env python3
"""Report-only CLI for the MAS-28 deterministic PR-linkage observer.

All I/O is deliberately held here.  The named phase functions are test seams, not
extension points: they make every frozen execution route observable and typed.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib import pr_linkage_validator as core


class PhaseFailure(RuntimeError):
    def __init__(self, reason: str): self.reason = reason


ROUTES = {
    "INVALID_UTF8": ("INVALID_JSON", "JSON", 2), "INVALID_JSON": ("INVALID_JSON", "JSON", 2),
    "DUPLICATE_OBJECT_MEMBER": ("INVALID_JSON", "JSON", 2), "UNKNOWN_KEY": ("INVALID_OBSERVATION_SCHEMA", "OBSERVATION", 2),
    "MISSING_KEY": ("INVALID_OBSERVATION_SCHEMA", "OBSERVATION", 2), "TYPE_MISMATCH": ("INVALID_OBSERVATION_SCHEMA", "OBSERVATION", 2),
    "INVALID_SNAPSHOT_STATE": ("INVALID_OBSERVATION_SCHEMA", "OBSERVATION", 2), "EPOCH_RECEIPT_RULESET_MISMATCH": ("INVALID_OBSERVATION_SCHEMA", "OBSERVATION", 2),
    "INVALID_BODY_ENCODING": ("INVALID_OBSERVATION_SCHEMA", "PARSER", 2), "RESOURCE_LIMIT": ("INPUT_RESOURCE_LIMIT_EXCEEDED", "INPUT", 2),
    "UNSUPPORTED_RULESET_ID": ("UNSUPPORTED_RULESET", "RULESET", 2), "RULESET_DIGEST_MISMATCH": ("UNSUPPORTED_RULESET", "RULESET", 2),
    "INPUT_READ_FAILED": ("INTERNAL_ERROR", "INPUT", 3), "PARSER_INTERNAL_ERROR": ("INTERNAL_ERROR", "PARSER", 3),
    "EVALUATOR_INTERNAL_ERROR": ("INTERNAL_ERROR", "EVALUATOR", 3), "RENDERER_INTERNAL_ERROR": ("INTERNAL_ERROR", "RENDERER", 3),
    "OUTPUT_TEMP_CREATE_FAILED": ("OUTPUT_WRITE_ERROR", "OUTPUT", 3), "OUTPUT_WRITE_FAILED": ("OUTPUT_WRITE_ERROR", "OUTPUT", 3),
    "OUTPUT_REPLACE_FAILED": ("OUTPUT_WRITE_ERROR", "OUTPUT", 3), "NONDETERMINISTIC_RESULT": ("NONDETERMINISTIC_RESULT", "DETERMINISM", 3),
}


def source_sha(explicit: str | None) -> str | None:
    import re
    return explicit if explicit and re.fullmatch(r"[0-9a-f]{40}", explicit) else None


def envelope(reason: str, raw: bytes | None, source: str | None, *, limit=None, observed=None):
    code, component, _ = ROUTES[reason]
    error = {"code": code, "component": component, "reason_code": reason, "limit": limit, "observed": observed}
    return {"schema":"mastermind.pr_linkage_execution_error.v1","enforcement":"REPORT_ONLY","error":error,"execution_error_hash":core.digest(error),"receipt":{"input_sha256":hashlib.sha256(raw).hexdigest() if raw is not None else None,"source_sha":source,"producer":"scripts/pr_linkage_validator.py"}}


def read_input(path: str) -> bytes:
    try:
        return sys.stdin.buffer.read() if path == "-" else pathlib.Path(path).read_bytes()
    except OSError as exc:
        raise PhaseFailure("INPUT_READ_FAILED") from exc


def parse_input(raw: bytes):
    try:
        return core.loads_strict(raw)
    except core.ValidationError:
        raise
    except Exception as exc:
        raise PhaseFailure("PARSER_INTERNAL_ERROR") from exc


def evaluate(observation, manifest):
    try:
        return core.analyze(observation, manifest)
    except core.ValidationError:
        raise
    except Exception as exc:
        raise PhaseFailure("EVALUATOR_INTERNAL_ERROR") from exc


def render(report, fmt: str) -> bytes:
    try:
        if fmt == "json": return core.canonical_json(report)
        if fmt == "human": return (report["human"]["summary"] + "\n").encode()
        return "\n".join(f"::{'warning' if f['severity'] in ('ERROR','PARTIAL','WARNING') else 'notice'} title={f['code']}::{f['remediation_code']}" for f in report["semantic"]["findings"]).encode()
    except Exception as exc:
        raise PhaseFailure("RENDERER_INTERNAL_ERROR") from exc


def write_atomic(target: pathlib.Path, payload: bytes) -> None:
    tmp = None
    try:
        try:
            fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        except Exception as exc:
            raise PhaseFailure("OUTPUT_TEMP_CREATE_FAILED") from exc
        try:
            os.write(fd, payload); os.close(fd)
        except Exception as exc:
            try: os.close(fd)
            except Exception: pass
            raise PhaseFailure("OUTPUT_WRITE_FAILED") from exc
        try:
            os.replace(tmp, target)
        except Exception as exc:
            raise PhaseFailure("OUTPUT_REPLACE_FAILED") from exc
    finally:
        if tmp:
            try: pathlib.Path(tmp).unlink(missing_ok=True)
            except Exception: pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("input", nargs="?", default="-"); ap.add_argument("--output"); ap.add_argument("--format", choices=("json","human","github"), default="json"); ap.add_argument("--source-sha")
    a = ap.parse_args(argv); raw = None; src = source_sha(a.source_sha)
    try:
        raw = read_input(a.input)
        if len(raw) > 1048576: raise core.ValidationError("RESOURCE_LIMIT:observation_bytes")
        observation = parse_input(raw)
        manifest = parse_input((ROOT / "config/pr_linkage_rules.v1.json").read_bytes())
        report = evaluate(observation, manifest); payload = render(report, a.format)
        if payload != render(evaluate(observation, manifest), a.format): raise PhaseFailure("NONDETERMINISTIC_RESULT")
        status = 0
    except core.ValidationError as exc:
        reason = str(exc).split(":", 1)[0]
        if reason not in ROUTES: reason = "EVALUATOR_INTERNAL_ERROR"
        limit = observed = None
        if reason == "RESOURCE_LIMIT":
            key = str(exc).split(":", 1)[1] if ":" in str(exc) else None
            limit = {"observation_bytes":1048576}.get(key)
            observed = len(raw) if raw is not None and key == "observation_bytes" else None
        payload = core.canonical_json(envelope(reason, raw, src, limit=limit, observed=observed)); status = ROUTES[reason][2]
    except PhaseFailure as exc:
        payload = core.canonical_json(envelope(exc.reason, raw, src)); status = ROUTES[exc.reason][2]
    if a.output:
        try:
            write_atomic(pathlib.Path(a.output), payload)
        except PhaseFailure as exc:
            sys.stderr.buffer.write(core.canonical_json(envelope(exc.reason, raw, src)) + b"\n")
            return ROUTES[exc.reason][2]
    else:
        (sys.stdout if status == 0 else sys.stderr).buffer.write(payload + b"\n")
    return status


if __name__ == "__main__": raise SystemExit(main())
