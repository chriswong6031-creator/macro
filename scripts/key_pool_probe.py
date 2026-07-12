"""scripts/key_pool_probe.py — operator diagnostics: is each OAuth key ALIVE?

Makes ONE minimal real API call (max_tokens=1) per PRESENT key env among
CLAUDE_CODE_OAUTH_TOKEN_1/_2/_3 and the legacy CLAUDE_CODE_OAUTH_TOKEN, and
prints a per-key verdict:

    CLAUDE_CODE_OAUTH_TOKEN_1: OK
    CLAUDE_CODE_OAUTH_TOKEN_2: AUTH_FAILED (revoked/expired — rotate the secret)
    CLAUDE_CODE_OAUTH_TOKEN_3: ABSENT

REDLINE: this module NEVER reads a token value itself. All credential handling
goes through engine.llm_auth (the single sanctioned boundary): each env name is
probed via build_providers({"oauth_token_env": <name>}) + make_call. No cap_id
is attached, so no key_ledger rows are written — the probe is side-effect-free.

Exit code: 0 when every PRESENT key serves; 1 when any present key fails
(auth-dead / rate-limited / errored) so the workflow run shows a red X the
operator can see at a glance. ABSENT keys are informational only — the pool
degrades gracefully by design.

Usage:  python -m scripts.key_pool_probe [--model claude-sonnet-4-6]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("key_pool_probe")

_PROBE_ENVS = [
    "CLAUDE_CODE_OAUTH_TOKEN_1",
    "CLAUDE_CODE_OAUTH_TOKEN_2",
    "CLAUDE_CODE_OAUTH_TOKEN_3",
    "CLAUDE_CODE_OAUTH_TOKEN",   # legacy single key (waterfall fallback)
]


def probe_env(env_name: str, model: str) -> str:
    """Probe one key env. Returns 'OK' | 'ABSENT' | 'AUTH_FAILED' |
    'RATE_LIMITED' | 'ERROR:<type>'. Never raises, never logs values."""
    from engine import llm_auth

    # Fresh dead-registry per probe so one dead key never masks another
    llm_auth.clear_dead()

    providers = llm_auth.build_providers({
        "provider_order": ["oauth"],
        "oauth_token_env": env_name,
    }, opus_model=model)
    if not providers:
        return "ABSENT"

    def call_fn(client, mdl):
        client.messages.create(
            model=mdl, max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        return "ok", None

    try:
        text, reason, used = llm_auth.make_call(
            providers, call_fn, context=f"key_pool_probe:{env_name}")
    except Exception as exc:  # noqa: BLE001 — connection/5xx re-raised by design
        return f"ERROR:{type(exc).__name__}"

    if text == "ok" and used == "oauth":
        return "OK"
    if reason in ("auth_invalid_all",):
        return "AUTH_FAILED"
    if reason in ("rate_limited_all",):
        return "RATE_LIMITED"
    return f"ERROR:{reason or 'unknown'}"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Probe each OAuth pool key with one minimal API call.")
    ap.add_argument("--model", default="claude-sonnet-4-6",
                    help="Model for the 1-token probe call (default: the build lane's model).")
    args = ap.parse_args(argv)

    verdicts: dict[str, str] = {}
    for env_name in _PROBE_ENVS:
        verdicts[env_name] = probe_env(env_name, args.model)

    hints = {
        "OK": "",
        "ABSENT": " (not set — pool degrades gracefully)",
        "AUTH_FAILED": " (revoked/expired — rotate the secret)",
        "RATE_LIMITED": " (key works but is quota-cooling right now)",
    }
    print("── OAuth key pool probe ──")
    failed = []
    for env_name, verdict in verdicts.items():
        print(f"  {env_name}: {verdict}{hints.get(verdict, '')}")
        if verdict not in ("OK", "ABSENT"):
            failed.append(env_name)

    present_ok = [e for e, v in verdicts.items() if v == "OK"]
    print(f"── {len(present_ok)} key(s) serving; "
          f"{len(failed)} present-but-failing; "
          f"{sum(1 for v in verdicts.values() if v == 'ABSENT')} absent ──")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
