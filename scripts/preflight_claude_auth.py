"""scripts/preflight_claude_auth.py — OAuth preflight token-health gate (A2).

Verifies that the CLAUDE_CODE_OAUTH_TOKEN is healthy BEFORE any expensive
stage is allowed to proceed.  Resolves the token reference via
engine.neuralweb.capability_broker.resolve() — NEVER reads the value directly.

Design:
  - Cheapest-tier 1-token health call via the `claude` CLI (subprocess, short
    timeout).  If the CLI is unavailable or the call fails in any way,
    auth_ok=False is returned (fail-closed).
  - On failure, sends a Telegram notification so the operator can re-place the
    token (it has corrupted before — memory `bot-mastermind-refresh-fix`).
  - Never logs, prints, or persists the token value.

Returns:
    dict with keys:
        auth_ok (bool)  — True if the session is healthy
        reason  (str)   — human-readable explanation
        ref_name (str | None) — the env-var name (for audit; NOT the value)

NEVER-RAISE CONTRACT: all exceptions → auth_ok=False.

Usage:
    from scripts.preflight_claude_auth import check_auth

    result = check_auth(lane="metabolism-propose")
    if not result["auth_ok"]:
        journal.finish_stage(..., status="noop_paused", note=result["reason"])
        sys.exit(0)
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_CAPABILITY_ID = "claude_code_oauth"
_PING_TIMEOUT_S = 20  # seconds

# Prompt to use for the health-ping (cheapest possible — 1 output token target)
_PING_PROMPT = "Reply with the single word: pong"

# Reason prefix emitted when the CLI binary itself is absent (vs a live CLI
# reporting a dead token).  SDK-channel stages (PROPOSE/ADJUDICATE call the
# API via engine.llm_auth, never the CLI) key off check_auth()'s cli_missing
# flag to proceed: llm_auth's provider waterfall self-protects if the token
# is truly dead.  BUILD (which execs the CLI in sessions) must NOT proceed.
CLI_MISSING_PREFIX = "claude CLI not found in PATH"

# Known install locations for the claude CLI on the self-hosted runners.
# The runner daemon inherits a minimal launchd PATH that omits per-user bin
# dirs, so a bare "claude" raises FileNotFoundError even when the CLI IS
# installed (first armed PROPOSE cycle, 2026-07-13: ~/.local/bin/claude
# present but invisible to actions-runner-2).  PATH still wins when set.
_CLAUDE_BIN_CANDIDATES: tuple[str, ...] = (
    "~/.local/bin/claude",
    "~/.claude/local/claude",
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
)


def resolve_claude_bin() -> str:
    """Resolve the claude CLI binary: PATH first, then known install dirs.

    Falls back to the bare name, preserving the original FileNotFoundError
    path and its operator-facing message.  NEVER raises.
    """
    try:
        import shutil  # noqa: PLC0415
        found = shutil.which("claude")
        if found:
            return found
        for cand in _CLAUDE_BIN_CANDIDATES:
            p = Path(cand).expanduser()
            if p.is_file() and os.access(p, os.X_OK):
                return str(p)
    except Exception as exc:  # noqa: BLE001
        log.warning("preflight: resolve_claude_bin failed (%s) — using bare name", exc)
    return "claude"


def _notify_auth_failure(reason: str) -> None:
    """Best-effort Telegram notification on auth failure.  Never raises."""
    try:
        # Import notify dynamically to avoid hard dep at module load
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from scripts.notify import send_telegram  # type: ignore[import]
        send_telegram(
            f"METABOLISM ALERT: OAuth pool key health check FAILED.\n"
            f"Reason: {reason}\n"
            f"Action required: verify CLAUDE_CODE_OAUTH_TOKEN_3..7 GitHub Secrets are valid."
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("preflight_claude_auth: notify failed: %s", exc)


def _pick_pool_key(root: Path | None = None) -> tuple[str | None, str | None]:
    """Return (ref_name, token_value) for the first enabled+present+non-cooling pool key.

    Tries engine.neuralweb.key_pool first; falls back to direct env presence
    checks of CLAUDE_CODE_OAUTH_TOKEN_1..7 filtered by METAB_KEYS_ENABLED.
    Returns (None, None) when no pool key is available.  NEVER raises.
    NEVER logs token values.
    """
    try:
        from engine.neuralweb.key_pool import (  # noqa: PLC0415
            discover_present_keys, get_secret_ref, is_cooling,
        )
        for cap_id in discover_present_keys(root):
            if is_cooling(cap_id, root=root):
                continue
            ref = None
            try:
                ref = get_secret_ref(cap_id, root=root)
            except Exception:  # noqa: BLE001
                pass
            if not ref:
                suffix = cap_id.split("_")[-1]
                ref = f"CLAUDE_CODE_OAUTH_TOKEN_{suffix}" if suffix.isdigit() else None
            if not ref:
                continue
            val = os.environ.get(ref, "").strip()
            if val:
                return ref, val
        return None, None
    except Exception as exc:  # noqa: BLE001
        log.debug("preflight: key_pool import failed (%s) — direct env fallback", exc)

    # Fallback: direct env presence checks
    try:
        raw = os.environ.get("METAB_KEYS_ENABLED", "").strip()
        if raw:
            enabled_nums = {s.strip() for s in raw.split(",") if s.strip().isdigit()}
        else:
            enabled_nums = {str(i) for i in range(1, 8)}
    except Exception:  # noqa: BLE001
        enabled_nums = {str(i) for i in range(1, 8)}
    for i in range(1, 8):
        if str(i) not in enabled_nums:
            continue
        ref = f"CLAUDE_CODE_OAUTH_TOKEN_{i}"
        val = os.environ.get(ref, "").strip()
        if val:
            return ref, val
    return None, None


def check_auth(
    lane: str = "metabolism-preflight",
    root: Path | None = None,
) -> dict[str, Any]:
    """Run the OAuth preflight health check.

    Selects the first enabled+present+non-cooling pool key (CLAUDE_CODE_OAUTH_TOKEN_N)
    via key_pool.  Sets that key's VALUE in the subprocess env copy only —
    never logged, never written to disk.  Reports ref_name as the env NAME.
    Falls back to absent-key behavior when no pool key is available.

    Parameters
    ----------
    lane : str
        The calling workflow lane (for capability broker audit).
    root : Path | None
        Repo root for test isolation (None = production paths).

    Returns
    -------
    dict with keys auth_ok, reason, ref_name.
    NEVER raises.
    """
    try:
        if root is not None:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

        # Step 1: pick the best pool key (never reads the legacy single token)
        ref_name, token_value = _pick_pool_key(root=root)

        if not ref_name or not token_value:
            reason = (
                "No enabled+present pool key found (CLAUDE_CODE_OAUTH_TOKEN_1..7). "
                "Set at least one pool key in GitHub Secrets and enable it via METAB_KEYS_ENABLED."
            )
            log.warning("preflight_claude_auth: %s", reason)
            _notify_auth_failure(reason)
            return {"auth_ok": False, "reason": reason, "ref_name": None}

        # Step 2: cheapest-tier 1-token ping via claude CLI (subprocess, short timeout)
        # The subprocess env receives CLAUDE_CODE_OAUTH_TOKEN set to the pool key's
        # VALUE — in-process os.environ copy only, never logged or written.
        auth_ok, ping_reason = _run_ping_check(ref_name, token_value=token_value)

        if not auth_ok:
            _notify_auth_failure(ping_reason)
            return {
                "auth_ok": False,
                "reason": ping_reason,
                "ref_name": ref_name,
                "cli_missing": ping_reason.startswith(CLI_MISSING_PREFIX),
            }

        # Step 3: audit the successful use via capability broker (best-effort)
        try:
            from engine.neuralweb.capability_broker import audit  # type: ignore[import]
            cap_id = "claude_code_oauth_" + ref_name.split("_")[-1]
            audit(cap_id, lane, workflow="metabolism-preflight", root=root)
        except Exception:  # noqa: BLE001
            pass

        return {
            "auth_ok": True,
            "reason": f"OAuth pool key health check passed via {ref_name}",
            "ref_name": ref_name,
        }

    except Exception as exc:  # noqa: BLE001
        reason = f"preflight_claude_auth: unexpected error: {exc}"
        log.warning(reason)
        try:
            _notify_auth_failure(reason)
        except Exception:  # noqa: BLE001
            pass
        return {"auth_ok": False, "reason": reason, "ref_name": None}


def _run_ping_check(ref_name: str, *, token_value: str | None = None) -> tuple[bool, str]:
    """Execute the cheapest 1-token health ping.

    Returns (auth_ok, reason).  NEVER raises.

    Parameters
    ----------
    ref_name : str
        The env-var NAME of the key being probed (for logging; NOT the value).
    token_value : str | None
        When provided, sets CLAUDE_CODE_OAUTH_TOKEN=<value> in the subprocess
        env copy only (in-process; never logged or written to disk).  The CLI
        reads the CLAUDE_CODE_OAUTH_TOKEN env var for authentication.

    Strategy:
      1. Try `claude -p '<prompt>'` via subprocess with a private env copy.
      2. On CalledProcessError / TimeoutExpired / FileNotFoundError → auth_ok=False.
      3. Non-zero exit → auth_ok=False with stderr snippet.
      4. Empty stdout → auth_ok=False (suggests expired/corrupt session).
      5. Any output → auth_ok=True (the session is alive).
    """
    try:
        # Build a private env copy: inherit the current environment, then
        # set CLAUDE_CODE_OAUTH_TOKEN to the chosen pool key's value so the
        # CLI authenticates as that key (never passed as a CLI argument).
        import copy as _copy  # noqa: PLC0415
        subprocess_env = _copy.copy(os.environ.copy())
        if token_value:
            subprocess_env["CLAUDE_CODE_OAUTH_TOKEN"] = token_value
        result = subprocess.run(
            [resolve_claude_bin(), "-p", _PING_PROMPT],
            capture_output=True,
            text=True,
            timeout=_PING_TIMEOUT_S,
            env=subprocess_env,
        )
        if result.returncode != 0:
            stderr_snippet = result.stderr[:200] if result.stderr else "(no stderr)"
            return (
                False,
                f"claude -p ping exited {result.returncode}: {stderr_snippet}",
            )
        stdout = result.stdout.strip()
        if not stdout:
            return (
                False,
                "claude -p ping returned empty stdout — session may be corrupt or expired",
            )
        return True, f"ping ok: {stdout[:80]!r}"

    except FileNotFoundError:
        return (
            False,
            CLI_MISSING_PREFIX + " — cannot verify OAuth token health. "
            "Ensure the claude CLI is installed on the runner.",
        )
    except subprocess.TimeoutExpired:
        return (
            False,
            f"claude -p ping timed out after {_PING_TIMEOUT_S}s — "
            "possible network issue or corrupt token.",
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"ping raised {type(exc).__name__}: {exc}"


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Metabolism OAuth preflight (A2)")
    parser.add_argument("--lane", default="metabolism-preflight", help="Calling lane name")
    args = parser.parse_args()

    res = check_auth(lane=args.lane)
    print(f"auth_ok={res['auth_ok']} ref_name={res['ref_name']!r}")
    print(f"reason: {res['reason']}")
    sys.exit(0 if res["auth_ok"] else 1)
