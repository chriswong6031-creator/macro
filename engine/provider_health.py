"""Per-rung outcome telemetry for the :mod:`engine.llm_auth` provider waterfall.

WHY THIS EXISTS
---------------
``llm_auth.make_call`` walks a waterfall and returns the name of the rung that
SERVED.  Everything about the rungs it walked PAST is written to a Python
logger and then thrown away.  The ai_costs ledger has the same blind spot by
construction: :func:`llm_auth._capture_usage` books a row only on success, so a
lane whose first three rungs fail every single call books a ledger that reads
"100% DeepSeek" and contains no evidence that codex, oauth and anthropic were
ever asked, let alone why they said no.

That is exactly how the marketing copywriter ran for weeks.  ``config/marketing.yml``
puts codex FIRST on every writing lane (operator directive 2026-07-29,
"ChatGPT-first"), the drop census recorded ``unreadable_reply:deepseek+oauth``,
and there was no artifact anywhere in the repo that could say whether the codex
rung had failed, been marked dead by an earlier item, or never been built on
that host at all.  Three very different problems, one indistinguishable symptom.

This module is the missing half: ONE small row per rung ATTEMPT, plus one row
per waterfall BUILD naming the rungs that were actually constructed.  A build
row with no codex entry means the host could not see the CLI or the attached
login; an attempt row with ``error_class=usage_limit`` means the subscription
window is spent; ``timeout`` means the budget is too tight for a process spawn.

CONTRACT
--------
* NEVER raises.  Telemetry must not be able to cost a call.
* Rows are small and append-only JSONL, alongside the ai_costs ledger.
* Credentials, prompts and model replies are NEVER written here.
* Writes are skipped entirely when ``PROVIDER_HEALTH_DISABLED`` is truthy.
"""
from __future__ import annotations

import json
import logging
import os
import stat
import threading
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

#: Sits beside data/ai_costs/usage.jsonl — same lane vocabulary, same operator.
_HEALTH_REL = "data/ai_costs/provider_health.jsonl"

#: Rotate at 8 MB.  Rows are ~200 bytes, so this is ~40k attempts: several
#: months of nightlies.  An append-only store with a fixed universe of writers
#: grows forever otherwise, and this one is telemetry, not a ledger anyone
#: reconciles against — the old file is renamed, never deleted, so a forensic
#: read can still reach it.
_MAX_BYTES = 8 * 1024 * 1024

_FALSE = {"", "0", "false", "no", "off"}

# The legacy Claude OAuth rung predates capability IDs and therefore records
# its configured environment-variable *name* in the health ledger.  Collapse
# that known identifier at this secret-free source seam so downstream capacity
# projection never needs to know or emit an auth variable name.
_CAPACITY_CAP_ID_ALIASES = {
    "CLAUDE_CODE_OAUTH_TOKEN": "claude_code_oauth",
}

_write_lock = threading.Lock()


def enabled() -> bool:
    """False when the operator has switched this telemetry off."""
    return os.environ.get("PROVIDER_HEALTH_DISABLED", "").strip().lower() in _FALSE


def health_path() -> Path:
    """Absolute path of the provider-health ledger for this checkout.

    ``PROVIDER_HEALTH_PATH`` overrides it outright (tests, appliances).
    Otherwise it follows ai_costs' own state root so a deployment that keeps
    mutable telemetry outside an immutable checkout keeps both together.
    """
    override = os.environ.get("PROVIDER_HEALTH_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    try:
        from lib import ai_costs as _ac  # noqa: PLC0415

        base = _ac._state_root()  # noqa: SLF001 — one owner, deliberate reuse
    except Exception:  # noqa: BLE001
        base = Path(__file__).resolve().parent.parent
    return Path(base) / _HEALTH_REL


def classify_error(exc: BaseException | None) -> str:
    """Map an exception to a stable, low-cardinality error class.

    The classes are the operator's decision tree, not the SDK's taxonomy:

    ``auth``          the credential is dead.  Re-login / rotate the secret.
    ``usage_limit``   the credential is fine and the window is spent.  Wait.
    ``timeout``       the rung did not answer inside its budget.  Raise it.
    ``not_installed`` the rung's binary/endpoint is absent on THIS host.
    ``unsupported``   the request shape is one this rung cannot serve.
    ``transport``     connection/5xx.  Usually transient.
    ``error``         classified by nothing above; read ``detail``.
    """
    if exc is None:
        return ""
    msg = str(exc).lower()
    name = type(exc).__name__.lower()

    # Order matters: the Codex CLI's usage-limit message also contains "login"
    # in its remediation sentence, and misreading a spent window as a dead
    # credential is what marks a healthy rung dead for the rest of the process.
    if ("usage limit" in msg or "quota" in msg or "429" in msg
            or "rate limit" in msg or "rate_limit" in msg
            or "ratelimit" in name):
        return "usage_limit"
    if ("401" in msg or "unauthorized" in msg or "authentication" in msg
            or "403" in msg or "forbidden" in msg
            or "authentication" in name or "permissiondenied" in name):
        return "auth"
    if "timeout" in msg or "timed out" in msg or "timeout" in name:
        return "timeout"
    if "not installed" in msg or "no such file" in msg or "filenotfound" in name:
        return "not_installed"
    if "unsupported" in msg or "unsupportedinput" in name:
        return "unsupported"
    if ("529" in msg or "overloaded" in msg or "connection" in msg
            or "connect" in name or "apiconnection" in name):
        return "transport"
    return "error"


def _append(row: dict) -> None:
    """Append one row.  NEVER raises."""
    if not enabled():
        return
    try:
        path = health_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _write_lock:
            try:
                if path.exists() and path.stat().st_size > _MAX_BYTES:
                    path.replace(path.with_suffix(path.suffix + ".1"))
            except Exception:  # noqa: BLE001 — rotation is best effort
                pass
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False,
                                    separators=(",", ":"), default=str) + "\n")
    except Exception as exc:  # noqa: BLE001 — telemetry never costs a call
        log.debug("provider_health: append failed (%s)", exc)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_attempt(
    *,
    lane: str,
    context: str,
    rung: str,
    ok: bool,
    latency_ms: int,
    cap_id: str | None = None,
    model: str | None = None,
    error_class: str = "",
    detail: str = "",
) -> None:
    """Record ONE rung attempt.  NEVER raises.

    ``detail`` is truncated hard: it exists so an ``error`` class is readable,
    not so the ledger can carry a stack trace or a model reply.
    """
    _append({
        "ts": _now(),
        "event": "attempt",
        "lane": str(lane or "unknown"),
        "context": str(context or ""),
        "rung": str(rung or "unknown"),
        "cap_id": str(cap_id or "") or None,
        "model": str(model or "") or None,
        "ok": bool(ok),
        "error_class": str(error_class or ""),
        "latency_ms": max(0, int(latency_ms)),
        **({"detail": str(detail)[:200]} if detail else {}),
    })


def record_waterfall(*, lane: str, context: str, rungs: list[dict]) -> None:
    """Record the rung list a waterfall was BUILT with.  NEVER raises.

    This is the row that answers "was codex even a candidate on that host".
    An empty ``rungs`` list is the armed-but-mute case and is worth a row of
    its own — an absent rung and a failing rung are different outages.
    """
    try:
        names = [
            {"rung": str(p.get("name") or "?"),
             "cap_id": str(p.get("cap_id") or "") or None,
             "model": str(p.get("model") or "") or None}
            for p in (rungs or [])
        ]
    except Exception:  # noqa: BLE001
        names = []
    _append({
        "ts": _now(),
        "event": "waterfall",
        "lane": str(lane or "unknown"),
        "context": str(context or ""),
        "n_rungs": len(names),
        "rungs": names,
    })


def summarize_attempts(rows: list[dict]) -> dict[str, dict]:
    """Fold attempt rows into ``{rung: {ok, fail, <error_class>: n}}``.

    Pure function over already-read rows so callers (the nightly funnel line,
    a future admin page) share one shape.  Non-attempt rows are ignored.
    """
    out: dict[str, dict] = {}
    for row in rows or []:
        if not isinstance(row, dict) or row.get("event") != "attempt":
            continue
        rung = str(row.get("rung") or "unknown")
        bucket = out.setdefault(rung, {"ok": 0, "fail": 0})
        if row.get("ok"):
            bucket["ok"] += 1
            continue
        bucket["fail"] += 1
        cls = str(row.get("error_class") or "error")
        bucket[cls] = int(bucket.get(cls, 0)) + 1
    return out


def read_rows(*, lane: str | None = None, limit: int = 5000) -> list[dict]:
    """Read the tail of the ledger.  Returns [] on any failure.  NEVER raises."""
    try:
        path = health_path()
        if not path.exists():
            return []
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()[-max(1, int(limit)):]
    except Exception as exc:  # noqa: BLE001
        log.debug("provider_health: read failed (%s)", exc)
        return []
    rows: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except (TypeError, ValueError):
            continue
        if not isinstance(row, dict):
            continue
        if lane and str(row.get("lane") or "") != lane:
            continue
        rows.append(row)
    return rows


def capacity_health_observations(
    *,
    root: Path | None = None,
    limit: int = 5000,
) -> dict:
    """Return a strict, secret-free view of provider-attempt telemetry.

    ``read_rows`` intentionally preserves the historic NEVER-RAISE display
    contract and therefore cannot distinguish an absent ledger from an
    unreadable or corrupt one.  Capacity projection needs that distinction so
    unknown source quality never becomes a healthy/available fact.  This seam
    reads the same owning ledger but returns only the bounded fields consumed by
    provider capacity; ``detail`` and all raw exception text are discarded.
    """
    path = (Path(root) / _HEALTH_REL) if root is not None else health_path()
    result = {"quality": "ok", "rows": [], "codes": []}
    try:
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            result["quality"] = "missing"
            result["codes"] = ["PROVIDER_HEALTH_UNKNOWN"]
            return result
        except OSError:
            result["quality"] = "unreadable"
            result["codes"] = ["SOURCE_UNREADABLE", "PROVIDER_HEALTH_UNKNOWN"]
            return result
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            result["quality"] = "unreadable"
            result["codes"] = ["SOURCE_UNREADABLE", "PROVIDER_HEALTH_UNKNOWN"]
            return result
        lines = path.read_text(encoding="utf-8").splitlines()[-max(1, int(limit)):]
    except Exception:  # noqa: BLE001
        result["quality"] = "unreadable"
        result["codes"] = ["SOURCE_UNREADABLE", "PROVIDER_HEALTH_UNKNOWN"]
        return result

    safe_rows: list[dict] = []
    corrupt = False
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            corrupt = True
            continue
        if not isinstance(row, dict):
            corrupt = True
            continue
        if row.get("event") != "attempt":
            continue
        ts = row.get("ts")
        if (
            not isinstance(ts, str)
            or not ts.strip()
            or not isinstance(row.get("ok"), bool)
        ):
            corrupt = True
            continue
        raw_cap_id = str(row.get("cap_id") or "") or None
        safe_rows.append({
            "ts": ts,
            "rung": str(row.get("rung") or "unknown"),
            "cap_id": _CAPACITY_CAP_ID_ALIASES.get(raw_cap_id, raw_cap_id),
            "ok": bool(row.get("ok")),
            "error_class": str(row.get("error_class") or ""),
        })

    if corrupt:
        # A partial tail cannot establish that the newest attempt was healthy.
        result["quality"] = "corrupt"
        result["codes"] = ["SOURCE_CORRUPT", "PROVIDER_HEALTH_UNKNOWN"]
        return result
    result["rows"] = safe_rows
    if not safe_rows:
        result["codes"] = ["PROVIDER_HEALTH_UNKNOWN"]
    return result
