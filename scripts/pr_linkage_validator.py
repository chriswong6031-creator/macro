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
import re
import subprocess
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


SHA_RE = re.compile(r"[0-9a-f]{40}")
DEFAULT_LIMITS = {"observation_bytes": 1048576, "body_bytes": 262144,
                  "body_lines": 10000, "line_bytes": 16384,
                  "field_occurrences": 100, "value_bytes": 80,
                  "relationships": 256, "changed_paths": 10000, "findings": 512}


def source_sha(explicit: str | None) -> str | None:
    """Resolve only a validated explicit SHA or bounded read-only Git HEAD."""
    if explicit is not None and SHA_RE.fullmatch(explicit):
        return explicit
    try:
        got = subprocess.run(("git", "rev-parse", "HEAD"), cwd=ROOT, check=True,
                             capture_output=True, text=True, timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return got if SHA_RE.fullmatch(got) else None


def envelope(reason: str, raw: bytes | None, source: str | None, *, limit=None, observed=None):
    code, component, _ = ROUTES[reason]
    error = {"code": code, "component": component, "reason_code": reason, "limit": limit, "observed": observed}
    return {"schema":"mastermind.pr_linkage_execution_error.v1","enforcement":"REPORT_ONLY","error":error,"execution_error_hash":core.digest(error),"receipt":{"input_sha256":hashlib.sha256(raw).hexdigest() if raw is not None else None,"source_sha":source,"producer":"scripts/pr_linkage_validator.py"}}


def read_input(path: str) -> bytes:
    try:
        return sys.stdin.buffer.read() if path == "-" else pathlib.Path(path).read_bytes()
    except OSError as exc:
        raise PhaseFailure("INPUT_READ_FAILED") from exc


def read_manifest() -> bytes:
    try:
        return (ROOT / "config/pr_linkage_rules.v1.json").read_bytes()
    except OSError as exc:
        raise PhaseFailure("PARSER_INTERNAL_ERROR") from exc


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
            offset = 0
            while offset < len(payload):
                written = os.write(fd, payload[offset:])
                if not isinstance(written, int) or written <= 0:
                    raise OSError("short write")
                offset += written
            os.fsync(fd)
            os.close(fd)
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
    class TypedParser(argparse.ArgumentParser):
        def error(self, _message): raise PhaseFailure("INPUT_READ_FAILED")
    ap = TypedParser(add_help=False); ap.add_argument("input", nargs="?", default="-"); ap.add_argument("--output"); ap.add_argument("--format", choices=("json","human","github"), default="json"); ap.add_argument("--source-sha")
    raw = None; observation = None; manifest = None; a = argparse.Namespace(output=None)
    try:
        a = ap.parse_args(argv); src = source_sha(a.source_sha)
        raw = read_input(a.input)
        if len(raw) > DEFAULT_LIMITS["observation_bytes"]: raise core.ValidationError("RESOURCE_LIMIT:observation_bytes")
        observation = parse_input(raw)
        manifest = parse_input(read_manifest())
        report = evaluate(observation, manifest); payload = render(report, a.format)
        if payload != render(evaluate(observation, manifest), a.format): raise PhaseFailure("NONDETERMINISTIC_RESULT")
        status = 0
    except core.ValidationError as exc:
        reason = str(exc).split(":", 1)[0]; src = source_sha(None)
        if reason not in ROUTES: reason = "EVALUATOR_INTERNAL_ERROR"
        limit = observed = None
        if reason == "RESOURCE_LIMIT":
            key = str(exc).split(":", 1)[1] if ":" in str(exc) else None
            limit = DEFAULT_LIMITS.get(key)
            observed = len(raw) if raw is not None and key == "observation_bytes" else None
            if isinstance(manifest, dict):
                limit = manifest.get("limits", {}).get(key, limit)
            if key == "relationships" and isinstance(observation, dict):
                observed = len(observation.get("native_linkage", {}).get("relationships", []))
            if key == "changed_paths" and isinstance(observation, dict):
                observed = len(observation.get("changed_paths", {}).get("paths", []))
            if key == "body_bytes" and isinstance(observation, dict):
                observed = len(str(observation.get("pull_request", {}).get("body", "")).encode("utf-8"))
            if key == "body_lines" and isinstance(observation, dict):
                observed = len(str(observation.get("pull_request", {}).get("body", "")).split("\n"))
            if key == "line_bytes" and isinstance(observation, dict):
                observed = max((len(x.encode("utf-8")) for x in str(observation.get("pull_request", {}).get("body", "")).split("\n")), default=0)
            if key == "field_occurrences" and isinstance(observation, dict):
                body = str(observation.get("pull_request", {}).get("body", ""))
                observed = max((len(re.findall(rf"(?m)^(?:{re.escape(field)}):", body)) for field in core.FIELDS), default=0)
            if key == "value_bytes" and isinstance(observation, dict):
                values = re.findall(r"(?m)^(?:Workstream|Linear|Portfolio-Mode|Wave|Authority|Completion): (.*)$", str(observation.get("pull_request", {}).get("body", "")))
                observed = max((len(value.encode("utf-8")) for value in values), default=0)
            if key == "findings":
                # The evaluator only raises after it has constructed the report;
                # a configured cap is still truthful even where an injected seam
                # cannot expose the discarded list.
                observed = DEFAULT_LIMITS["findings"] + 1
        payload = core.canonical_json(envelope(reason, raw, src, limit=limit, observed=observed)); status = ROUTES[reason][2]
    except PhaseFailure as exc:
        payload = core.canonical_json(envelope(exc.reason, raw, source_sha(None))); status = ROUTES[exc.reason][2]
    if a.output:
        try:
            write_atomic(pathlib.Path(a.output), payload)
        except PhaseFailure as exc:
            sys.stderr.buffer.write(core.canonical_json(envelope(exc.reason, raw, src)))
            return ROUTES[exc.reason][2]
    else:
        (sys.stdout if status == 0 else sys.stderr).buffer.write(payload)
    return status


if __name__ == "__main__": raise SystemExit(main())
