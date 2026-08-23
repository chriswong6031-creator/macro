#!/usr/bin/env python3
"""Report-only CLI for the MAS-28 deterministic PR-linkage observer."""
from __future__ import annotations
import argparse, hashlib, os, pathlib, sys, tempfile
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib import pr_linkage_validator as core

def source_sha(explicit: str | None) -> str | None:
    if explicit and __import__('re').fullmatch(r"[0-9a-f]{40}", explicit): return explicit
    return None  # CLI deliberately does not invoke git; adapter may provide a build identity.

def envelope(code, component, reason, raw, source, limit=None, observed=None):
    error={"code":code,"component":component,"reason_code":reason,"limit":limit,"observed":observed}
    return {"schema":"mastermind.pr_linkage_execution_error.v1","enforcement":"REPORT_ONLY","error":error,"execution_error_hash":core.digest(error),"receipt":{"input_sha256":hashlib.sha256(raw).hexdigest() if raw is not None else None,"source_sha":source,"producer":"scripts/pr_linkage_validator.py"}}

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("input", nargs="?", default="-"); ap.add_argument("--output"); ap.add_argument("--format", choices=("json","human","github"), default="json"); ap.add_argument("--source-sha")
    a=ap.parse_args(); raw=None; src=source_sha(a.source_sha)
    try:
        raw=sys.stdin.buffer.read() if a.input=="-" else pathlib.Path(a.input).read_bytes()
        if len(raw)>1048576: raise core.ValidationError("RESOURCE_LIMIT:observation_bytes")
        observation=core.loads_strict(raw)
        manifest=core.loads_strict((ROOT/"config/pr_linkage_rules.v1.json").read_bytes())
        report=core.analyze(observation,manifest); payload=core.canonical_json(report)
        # Repeating pure analysis is a direct nondeterminism assertion.
        if payload != core.canonical_json(core.analyze(observation,manifest)): raise RuntimeError("NONDETERMINISTIC_RESULT")
        if a.format=="human": payload=(report["human"]["summary"]+"\n").encode()
        elif a.format=="github": payload="\n".join(f"::{'warning' if f['severity'] in ('ERROR','PARTIAL','WARNING') else 'notice'} title={f['code']}::{f['remediation_code']}" for f in report['semantic']['findings']).encode()
        status=0
    except core.ValidationError as e:
        reason=str(e).split(":",1)[0]; limit=observed=None
        if reason=="RESOURCE_LIMIT":
            _, key=str(e).split(":",1); limit=core.loads_strict((ROOT/"config/pr_linkage_rules.v1.json").read_bytes())["limits"].get(key); observed=(len(raw) if key=="observation_bytes" and raw else None)
            err=envelope("INPUT_RESOURCE_LIMIT_EXCEEDED","INPUT","RESOURCE_LIMIT",raw,src,limit,observed)
        else:
            component="JSON" if reason in {"INVALID_UTF8","INVALID_JSON","DUPLICATE_OBJECT_MEMBER"} else ("RULESET" if reason in {"UNSUPPORTED_RULESET_ID","RULESET_DIGEST_MISMATCH"} else "OBSERVATION")
            err=envelope("INVALID_JSON" if component=="JSON" else ("UNSUPPORTED_RULESET" if component=="RULESET" else "INVALID_OBSERVATION_SCHEMA"),component,reason,raw,src)
        payload=core.canonical_json(err); status=2
    except Exception:
        payload=core.canonical_json(envelope("INTERNAL_ERROR","EVALUATOR","EVALUATOR_INTERNAL_ERROR",raw,src)); status=3
    if a.output:
        try:
            target=pathlib.Path(a.output); fd,tmp=tempfile.mkstemp(prefix=f".{target.name}.",dir=target.parent); os.write(fd,payload); os.close(fd); os.replace(tmp,target)
        except Exception:
            sys.stderr.buffer.write(core.canonical_json(envelope("OUTPUT_WRITE_ERROR","OUTPUT","OUTPUT_WRITE_FAILED",raw,src))+b"\n"); return 3
    else: (sys.stdout if status==0 else sys.stderr).buffer.write(payload+b"\n")
    return status
if __name__ == "__main__": raise SystemExit(main())
