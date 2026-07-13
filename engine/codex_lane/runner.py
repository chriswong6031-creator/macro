"""engine/codex_lane/runner.py — Codex CLI wrapper (CRX-R4, CRX-R8).

Frozen cross-lane API:
    resolve_codex_bin() -> str
    run_codex(prompt, *, cwd=None, timeout_s=1500, model="",
              sandbox="workspace-write", network=True,
              extra_args=None) -> dict
    fetch_rate_limits(timeout_s=30) -> dict | None

run_codex return shape:
    {
        ok: bool,
        final_message: str,
        events_count: int,
        token_usage: dict | None,          # {input_tokens, output_tokens, total_tokens}
        rate_limits: {                     # None if never seen
            "primary":   {"used_percent": float, "resets_at": str | None} | None,
            "secondary": {"used_percent": float, "resets_at": str | None} | None,
        } | None,
        error_kind: None | "usage_limit" | "auth" | "timeout"
                  | "not_installed" | "error",
        raw_tail: str,                     # last 2000 chars of combined output
    }

fetch_rate_limits normalized shape:
    {
        "primary":   {"used_percent": float, "resets_at": str | None, "window_mins": int | None} | None,
        "secondary": {"used_percent": float, "resets_at": str | None, "window_mins": int | None} | None,
        "plan_type": str | None,
        "fetched_at": str,                 # ISO 8601 UTC
    } | None

NEVER-RAISE: every public function catches all exceptions internally.
Auth hygiene: ~/.codex/auth.json is never read; token values are never logged.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Binary resolution order (mirrors claude CLI resolver pattern — CRX-R8)
# ---------------------------------------------------------------------------

_CODEX_SEARCH_PATHS: list[str] = [
    # PATH takes priority
    "__PATH__",
    # Known install locations, cheapest first
    os.path.expanduser("~/.local/bin/codex"),
    os.path.expanduser("~/.codex/bin/codex"),
    "/opt/homebrew/bin/codex",
    "/usr/local/bin/codex",
    os.path.expanduser("~/.npm-global/bin/codex"),
    # ChatGPT desktop app bundles the codex CLI (present on the dev box)
    "/Applications/ChatGPT.app/Contents/Resources/codex",
]


def resolve_codex_bin() -> str:
    """Return the path to the codex binary.

    Search order: shutil.which("codex") (uses PATH), then known install dirs.
    Falls back to the bare string "codex" so subprocess raises FileNotFoundError
    on launch instead of at resolution time — callers do not need to handle
    resolution errors separately.

    NEVER raises.
    """
    try:
        found = shutil.which("codex")
        if found:
            return found
        for candidate in _CODEX_SEARCH_PATHS[1:]:  # skip the __PATH__ sentinel
            if Path(candidate).is_file():
                return candidate
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_lane.runner: resolve_codex_bin error: %s", exc)
    # bare fallback — FileNotFoundError on spawn surfaces as not_installed
    return "codex"


# ---------------------------------------------------------------------------
# Error-kind classification
# ---------------------------------------------------------------------------

_USAGE_LIMIT_PHRASES = (
    "usage limit",
    "rate limit",
    "quota",
    "you've hit",
    "you have reached",
    "request limit",
)
_AUTH_PHRASES = (
    "401",
    "unauthorized",
    "login",
    "not logged in",
    "authentication",
)

# New-protocol event types that indicate an error condition
_ERROR_EVENT_TYPES = ("thread.error", "turn.failed", "error")


def _classify_error(combined: str) -> str:
    """Return an error_kind string from combined stdout+stderr (lowercased)."""
    lc = combined.lower()
    for phrase in _USAGE_LIMIT_PHRASES:
        if phrase in lc:
            return "usage_limit"
    for phrase in _AUTH_PHRASES:
        if phrase in lc:
            return "auth"
    return "error"


def _classify_error_text(text: str) -> str:
    """Classify error kind from arbitrary text (new-protocol error events)."""
    lc = text.lower()
    for phrase in _USAGE_LIMIT_PHRASES:
        if phrase in lc:
            return "usage_limit"
    for phrase in _AUTH_PHRASES:
        if phrase in lc:
            return "auth"
    return "error"


# ---------------------------------------------------------------------------
# Rate-limit normalisation helpers
# ---------------------------------------------------------------------------

def _seconds_to_iso(seconds: int | float) -> str:
    """Convert a seconds-from-now offset to an ISO 8601 UTC string."""
    try:
        dt = datetime.now(tz=timezone.utc)
        from datetime import timedelta  # noqa: PLC0415
        dt = dt + timedelta(seconds=float(seconds))
        return dt.isoformat()
    except Exception:  # noqa: BLE001
        return ""


def _epoch_to_iso(epoch_seconds: int | float) -> str | None:
    """Convert a Unix epoch timestamp (seconds) to an ISO 8601 UTC string.

    Returns None on any conversion failure.
    """
    try:
        dt = datetime.fromtimestamp(float(epoch_seconds), tz=timezone.utc)
        return dt.isoformat()
    except Exception:  # noqa: BLE001
        return None


def _normalize_rate_limit_entry(entry: Any) -> dict | None:
    """Normalize a single primary/secondary rate-limit dict.

    Accepts layouts:
        {"used_percent": float, "resets_at": str}
        {"used_percent": float, "resets_in_seconds": int}
        {"used_percent": float}

    Returns None if the entry is not a dict or lacks used_percent.
    """
    if not isinstance(entry, dict):
        return None
    pct = entry.get("used_percent")
    if pct is None:
        return None
    resets_at = entry.get("resets_at") or None
    if resets_at is None:
        secs = entry.get("resets_in_seconds")
        if secs is not None:
            resets_at = _seconds_to_iso(secs)
    return {"used_percent": float(pct), "resets_at": resets_at}


def _extract_rate_limits(obj: Any) -> dict | None:
    """Extract and normalize a rate_limits structure from any event object.

    Checks: top-level, obj["info"]["rate_limits"], obj["msg"]["rate_limits"].
    Returns None when not found or malformed.
    """
    if not isinstance(obj, dict):
        return None

    # Candidate sources in preference order
    sources: list[Any] = []

    # 1. top-level rate_limits
    if "rate_limits" in obj:
        sources.append(obj["rate_limits"])

    # 2. obj["info"]["rate_limits"]
    info = obj.get("info")
    if isinstance(info, dict) and "rate_limits" in info:
        sources.append(info["rate_limits"])

    # 3. obj["msg"]["rate_limits"]
    msg = obj.get("msg")
    if isinstance(msg, dict) and "rate_limits" in msg:
        sources.append(msg["rate_limits"])

    for src in sources:
        if not isinstance(src, dict):
            continue
        primary = _normalize_rate_limit_entry(src.get("primary"))
        secondary = _normalize_rate_limit_entry(src.get("secondary"))
        if primary is not None or secondary is not None:
            return {"primary": primary, "secondary": secondary}

    return None


# ---------------------------------------------------------------------------
# Token-usage extraction
# ---------------------------------------------------------------------------

def _extract_token_usage(obj: Any) -> dict | None:
    """Extract token usage from a token_count event.

    Accepts nested layouts:
        {"info": {"usage": {"input_tokens": ..., "output_tokens": ..., "total_tokens": ...}}}
        {"usage": {"input_tokens": ..., "output_tokens": ...}}
        flat fields at top level
    Returns None if no usable token data found.
    Never logs token values.
    """
    if not isinstance(obj, dict):
        return None

    # Build candidate dicts to search — top-level, wrapped msg, and info
    candidates: list[dict] = [obj]
    # wrapped: {"id": ..., "msg": {"type": "token_count", "usage": {...}}}
    msg_inner = obj.get("msg")
    if isinstance(msg_inner, dict):
        candidates.append(msg_inner)
        usage_in_msg = msg_inner.get("usage")
        if isinstance(usage_in_msg, dict):
            candidates.append(usage_in_msg)
        info_in_msg = msg_inner.get("info")
        if isinstance(info_in_msg, dict):
            candidates.append(info_in_msg)
    info = obj.get("info")
    if isinstance(info, dict):
        candidates.append(info)
        usage_in_info = info.get("usage")
        if isinstance(usage_in_info, dict):
            candidates.append(usage_in_info)
    usage_top = obj.get("usage")
    if isinstance(usage_top, dict):
        candidates.append(usage_top)

    for c in candidates:
        inp = c.get("input_tokens") or c.get("prompt_tokens")
        out = c.get("output_tokens") or c.get("completion_tokens")
        if inp is not None and out is not None:
            total = c.get("total_tokens") or (int(inp) + int(out))
            return {
                "input_tokens": int(inp),
                "output_tokens": int(out),
                "total_tokens": int(total),
            }

    return None


# ---------------------------------------------------------------------------
# JSONL event stream parser
# ---------------------------------------------------------------------------

def _parse_jsonl(
    text: str,
) -> tuple[str, int, dict | None, dict | None, str | None]:
    """Parse a JSONL event stream from codex exec --json output.

    Returns:
        (final_message, events_count, token_usage, rate_limits, error_from_events)

    Handles both legacy shapes and the new thread-event protocol (0.144.0+):

    Legacy flat events:
        {"type": "agent_message", "message": "...", ...}
    Legacy wrapped events:
        {"id": ..., "msg": {"type": "agent_message", "text": "...", ...}, ...}

    New thread-event protocol:
        {"type": "thread.started", "thread_id": "..."}
        {"type": "turn.started"}
        {"type": "item.completed", "item": {"id": "...", "type": "agent_message", "text": "..."}}
        {"type": "turn.completed", "usage": {"input_tokens": ..., "cached_input_tokens": ...,
                                              "output_tokens": ..., "reasoning_output_tokens": ...}}
        {"type": "thread.error", "error": {"message": "..."}}
        {"type": "turn.failed", "error": {"message": "..."}}

    Keep-last semantics for final_message and token_usage.
    """
    final_message = ""
    events_count = 0
    token_usage: dict | None = None
    rate_limits: dict | None = None
    error_from_events: str | None = None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not isinstance(obj, dict):
            events_count += 1
            continue

        events_count += 1

        # Resolve the inner event dict (flat vs. wrapped)
        inner: dict = obj
        msg_wrapper = obj.get("msg")
        inner_via_msg: dict = msg_wrapper if isinstance(msg_wrapper, dict) else {}

        # Determine event type — check both layers
        event_type: str = (
            inner.get("type", "")
            or inner_via_msg.get("type", "")
        )

        # ----------------------------------------------------------------
        # New-protocol: item.completed carrying an agent_message item
        # ----------------------------------------------------------------
        if event_type == "item.completed":
            item = obj.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text_val = item.get("text", "")
                if text_val:
                    final_message = str(text_val)

        # ----------------------------------------------------------------
        # New-protocol: turn.completed carrying usage
        # ----------------------------------------------------------------
        elif event_type == "turn.completed":
            usage_obj = obj.get("usage")
            if isinstance(usage_obj, dict):
                inp = usage_obj.get("input_tokens") or usage_obj.get("prompt_tokens")
                out = usage_obj.get("output_tokens") or usage_obj.get("completion_tokens")
                if inp is not None and out is not None:
                    # cached_input_tokens and reasoning_output_tokens are additive
                    # but normalized into the existing three-key layout
                    total = usage_obj.get("total_tokens") or (int(inp) + int(out))
                    token_usage = {
                        "input_tokens": int(inp),
                        "output_tokens": int(out),
                        "total_tokens": int(total),
                    }

        # ----------------------------------------------------------------
        # New-protocol: error events — extract error text for classification.
        # An error event ALWAYS forces ok=False even when the process exits 0.
        # When no error text is available, default to "error" so the event
        # is never silently ignored.
        # ----------------------------------------------------------------
        elif event_type in _ERROR_EVENT_TYPES:
            err_obj = obj.get("error") or {}
            err_text = ""
            if isinstance(err_obj, dict):
                err_text = err_obj.get("message", "") or err_obj.get("text", "") or ""
            elif isinstance(err_obj, str):
                err_text = err_obj
            # Also check top-level message field
            if not err_text:
                err_text = obj.get("message", "") or ""
            # Always set error_from_events — default "error" when text is empty
            if err_text:
                error_from_events = _classify_error_text(str(err_text))
            else:
                error_from_events = "error"

        # ----------------------------------------------------------------
        # Legacy: Final agent message — type contains "agent_message"
        # (also handles any event where type IS "agent_message" directly)
        # ----------------------------------------------------------------
        if "agent_message" in event_type and event_type != "item.completed":
            text_val = (
                inner.get("message")
                or inner.get("text")
                or inner.get("last_agent_message")
                or inner_via_msg.get("message")
                or inner_via_msg.get("text")
                or inner_via_msg.get("last_agent_message")
                or ""
            )
            if text_val:
                final_message = str(text_val)

        # ----------------------------------------------------------------
        # Legacy: Token count — type contains "token_count"
        # ----------------------------------------------------------------
        if "token_count" in event_type:
            usage = _extract_token_usage(obj)
            if usage is not None:
                token_usage = usage

        # ----------------------------------------------------------------
        # Rate limits: check every event (both protocols)
        # ----------------------------------------------------------------
        rl = _extract_rate_limits(obj)
        if rl is not None:
            rate_limits = rl

    return final_message, events_count, token_usage, rate_limits, error_from_events


# ---------------------------------------------------------------------------
# fetch_rate_limits — JSON-RPC app-server handshake (frozen cross-lane API)
# ---------------------------------------------------------------------------

_JSONRPC_TIMEOUT_HEADROOM_S = 2  # extra seconds per read beyond deadline

_RATE_LIMITS_NORMALIZE_FIELDS = frozenset({"used_percent", "resets_at", "window_mins"})


def _normalize_rl_entry_from_appserver(entry: Any) -> dict | None:
    """Normalize a single primary/secondary entry from app-server rateLimits response.

    Input shape (from the REAL live response):
        {
            "usedPercent": 7,
            "windowDurationMins": 10080,
            "resetsAt": 1784513998,          # epoch seconds
            ...
        }
    Output shape (frozen API):
        {
            "used_percent": float,
            "resets_at": str | None,          # ISO 8601 UTC
            "window_mins": int | None,
        }
    """
    if not isinstance(entry, dict):
        return None
    pct = entry.get("usedPercent")
    if pct is None:
        return None
    resets_epoch = entry.get("resetsAt")
    resets_at = _epoch_to_iso(resets_epoch) if resets_epoch is not None else None
    window_mins_raw = entry.get("windowDurationMins")
    window_mins = int(window_mins_raw) if window_mins_raw is not None else None
    return {
        "used_percent": float(pct),
        "resets_at": resets_at,
        "window_mins": window_mins,
    }


def _readline_with_deadline(stdout: Any, deadline: float) -> str:
    """Read one line from *stdout* using a background thread, respecting *deadline*.

    Works with both real file objects (production) and StringIO mocks (tests)
    because it calls readline() in a daemon thread and joins with a timeout.

    Returns the line (possibly empty on EOF) or "" on deadline exceeded.
    NEVER raises.
    """
    import queue  # noqa: PLC0415
    import threading  # noqa: PLC0415

    q: queue.Queue = queue.Queue()

    def _reader() -> None:
        try:
            line = stdout.readline()
            q.put(line)
        except Exception:  # noqa: BLE001
            q.put("")

    t = threading.Thread(target=_reader, daemon=True)
    t.start()

    remaining = max(0.0, deadline - time.monotonic())
    try:
        return q.get(timeout=remaining)
    except queue.Empty:
        return ""


def fetch_rate_limits(timeout_s: int = 30) -> dict | None:
    """Query live rate-limit state via the codex app-server JSON-RPC interface.

    Protocol:
        1. Spawn ``codex app-server`` with stdin/stdout pipes (text mode).
        2. Send initialize request (id=1), await id=1 response.
        3. Send initialized notification.
        4. Send account/rateLimits/read request (id=2), await id=2 response.
        5. Extract and normalize rateLimits from the response.
        6. Kill the process (terminate then kill) in a finally block.

    Notification lines (those with a "method" key) are ignored while waiting
    for a response.

    Returns the FROZEN normalized shape on success:
        {
            "primary":   {"used_percent": float, "resets_at": str | None,
                          "window_mins": int | None} | None,
            "secondary": {"used_percent": float, "resets_at": str | None,
                          "window_mins": int | None} | None,
            "plan_type": str | None,
            "fetched_at": str,    # ISO 8601 UTC
        }

    Returns None on any failure (not installed, timeout, auth, malformed JSON).
    NEVER raises.
    """
    proc: subprocess.Popen | None = None  # type: ignore[type-arg]
    try:
        bin_path = resolve_codex_bin()
        fetched_at = datetime.now(tz=timezone.utc).isoformat()

        proc = subprocess.Popen(  # noqa: S603
            [bin_path, "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,  # line-buffered
        )

        deadline = time.monotonic() + timeout_s

        def _send(obj: dict) -> None:
            if proc is None or proc.stdin is None:
                return
            try:
                proc.stdin.write(json.dumps(obj) + "\n")
                proc.stdin.flush()
            except Exception:  # noqa: BLE001
                pass

        def _read_response(target_id: int) -> dict | None:
            """Read lines until we find the JSON-RPC response with id==target_id.

            Ignores notification lines (those with a 'method' key but no
            matching id).  Returns None on timeout or EOF.
            """
            if proc is None or proc.stdout is None:
                return None
            while time.monotonic() < deadline:
                raw = _readline_with_deadline(proc.stdout, deadline)
                if not raw:
                    # EOF or timeout
                    break
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                # Ignore notifications (have "method" key, no matching id)
                if obj.get("id") == target_id:
                    return obj
            return None

        # Step 2: Send initialize and await id=1 response
        _send({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "clientInfo": {"name": "crx", "title": "crx", "version": "0.1"},
            },
        })
        init_resp = _read_response(1)
        if init_resp is None:
            log.debug("codex_lane.runner.fetch_rate_limits: no initialize response")
            return None

        # Step 3: Send initialized notification (no response expected)
        _send({"jsonrpc": "2.0", "method": "initialized", "params": {}})

        # Step 4: Send account/rateLimits/read and await id=2 response
        _send({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "account/rateLimits/read",
            "params": {},
        })
        rl_resp = _read_response(2)
        if rl_resp is None:
            log.debug("codex_lane.runner.fetch_rate_limits: no rateLimits response")
            return None

        # Step 5: Extract and normalize
        result = rl_resp.get("result")
        if not isinstance(result, dict):
            log.debug("codex_lane.runner.fetch_rate_limits: result not a dict")
            return None

        # Real shape: result["rateLimits"]["primary"] / ["secondary"]
        rl_root = result.get("rateLimits") or result
        if not isinstance(rl_root, dict):
            return None

        primary = _normalize_rl_entry_from_appserver(rl_root.get("primary"))
        secondary = _normalize_rl_entry_from_appserver(rl_root.get("secondary"))
        plan_type = result.get("planType") or rl_root.get("planType")

        return {
            "primary": primary,
            "secondary": secondary,
            "plan_type": plan_type,
            "fetched_at": fetched_at,
        }

    except Exception as exc:  # noqa: BLE001
        log.debug("codex_lane.runner.fetch_rate_limits: error: %s", exc)
        return None

    finally:
        if proc is not None:
            try:
                proc.terminate()
            except Exception:  # noqa: BLE001
                pass
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------

_EMPTY_RESULT: dict = {
    "ok": False,
    "final_message": "",
    "events_count": 0,
    "token_usage": None,
    "rate_limits": None,
    "error_kind": "error",
    "raw_tail": "",
}


def run_codex(
    prompt: str,
    *,
    cwd: str | None = None,
    timeout_s: int = 1500,
    model: str = "",
    sandbox: str = "workspace-write",
    network: bool = True,
    extra_args: list[str] | None = None,
) -> dict:
    """Run ``codex exec --json`` and return a structured result dict.

    Parameters
    ----------
    prompt:
        The research prompt passed as the final positional argument.
    cwd:
        Working directory for the subprocess; defaults to the repo root
        (parent of the directory containing this file).
    timeout_s:
        Hard timeout in seconds (default 1500 = 25 min). On expiry the
        process is killed and error_kind is "timeout".
    model:
        Codex model string; flag is omitted entirely when empty.
    sandbox:
        Sandbox mode string; passed as ``--sandbox <sandbox>``.
    network:
        When True AND sandbox=="workspace-write", adds
        ``-c sandbox_workspace_write.network_access=true``.
    extra_args:
        Additional CLI arguments inserted before the prompt.

    Returns
    -------
    dict with keys: ok, final_message, events_count, token_usage,
    rate_limits, error_kind, raw_tail.

    NEVER raises.
    """
    try:
        bin_path = resolve_codex_bin()

        # Resolve effective working directory
        if cwd:
            effective_cwd = cwd
        else:
            effective_cwd = str(Path(__file__).resolve().parent.parent.parent)

        # Build arg list defensively
        args: list[str] = [bin_path, "exec", "--json"]

        # -C working directory
        args.extend(["-C", effective_cwd])

        # Headless: codex exec hard-fails outside a "trusted" git directory;
        # the sandbox flag still constrains writes (verified live on 0.144.0)
        args.append("--skip-git-repo-check")

        # Model flag: only when non-empty
        if model:
            args.extend(["-m", model])

        # Sandbox
        args.extend(["--sandbox", sandbox])

        # Network: only when sandbox is workspace-write and network=True
        if sandbox == "workspace-write" and network:
            args.extend(["-c", "sandbox_workspace_write.network_access=true"])

        # Extra args before prompt
        if extra_args:
            args.extend(extra_args)

        # Prompt LAST as positional argument
        args.append(prompt)

        log.debug(
            "codex_lane.runner: spawning codex; cwd=%s timeout_s=%d",
            effective_cwd,
            timeout_s,
        )

        try:
            proc = subprocess.run(  # noqa: S603
                args,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=effective_cwd,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            log.warning("codex_lane.runner: codex binary not found at %r", bin_path)
            return {
                **_EMPTY_RESULT,
                "error_kind": "not_installed",
                "raw_tail": f"FileNotFoundError: codex binary not found ({bin_path!r})",
            }
        except subprocess.TimeoutExpired as exc:
            raw = ""
            try:
                if exc.stdout:
                    raw += exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", errors="replace")
                if exc.stderr:
                    raw += exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
            log.warning("codex_lane.runner: subprocess timed out after %ds", timeout_s)
            return {
                **_EMPTY_RESULT,
                "error_kind": "timeout",
                "raw_tail": raw[-2000:],
            }

        combined = (proc.stdout or "") + (proc.stderr or "")
        raw_tail = combined[-2000:]

        # Parse JSONL output
        final_message, events_count, token_usage, rate_limits, error_from_events = _parse_jsonl(
            proc.stdout or ""
        )

        # Classify error from combined output
        ok = proc.returncode == 0
        error_kind: str | None = None

        if not ok:
            # Prefer error classification from event stream (new protocol);
            # fall back to combined stdout+stderr text classification
            if error_from_events is not None:
                error_kind = error_from_events
            else:
                error_kind = _classify_error(combined)
        elif error_from_events is not None:
            # Error event seen even on exit-code-0 (e.g. partial failure)
            ok = False
            error_kind = error_from_events

        log.debug(
            "codex_lane.runner: done ok=%s events=%d returncode=%d",
            ok,
            events_count,
            proc.returncode,
        )

        return {
            "ok": ok,
            "final_message": final_message,
            "events_count": events_count,
            "token_usage": token_usage,
            "rate_limits": rate_limits,
            "error_kind": error_kind,
            "raw_tail": raw_tail,
        }

    except Exception as exc:  # noqa: BLE001
        log.exception("codex_lane.runner: unexpected error in run_codex: %s", exc)
        return {
            **_EMPTY_RESULT,
            "error_kind": "error",
            "raw_tail": str(exc)[-2000:],
        }
