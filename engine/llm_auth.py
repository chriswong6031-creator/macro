"""engine/llm_auth.py — Shared LLM provider waterfall with 401-fallback.

W5 ITEM 1 FIX: when a provider returns a 401 authentication_error (expired
OAuth token, revoked key, wrong token type) the provider is marked dead FOR
THE REST OF THE PROCESS and the waterfall retries with the next provider.

WHY NEEDED
----------
GitHub Actions run 28587360655 showed every whitehouse-sentinel model call
failing with:
    401 authentication_error: Invalid bearer token
Because the CLAUDE_CODE_OAUTH_TOKEN repo secret was expired. The old
waterfall selected OAuth (token env-var EXISTS), built the client, and only
failed at call-time — but the exception was caught as a generic "llm_error"
and never triggered a retry to the next provider. DEEPSEEK_API_KEY is a valid
secret, so the desk would have worked if the waterfall degraded properly.

HOW THE FIX WORKS
-----------------
_try_call() wraps one model call. When the caught exception is an Anthropic
AuthenticationError (HTTP 401), it marks that provider dead in a module-level
set (dead providers are keyed by (provider_name, env_var)) and raises
_AuthDead so the caller can loop to the next provider.

All brain modules call make_call(providers, model_fn, call_fn) which:
  1. Iterates providers in waterfall order.
  2. Skips dead ones.
  3. On _AuthDead: marks dead, continues.
  4. On success: returns (text, degraded_reason, provider_used).
  5. On all-dead: returns (None, "no_provider", None).

degraded_reason semantics (for health lines and brain artifacts):
  • "auth_invalid:<provider>" — that provider gave a 401; fell back to next.
  • "no_provider"            — all providers unavailable (no key or all dead).
  • "llm_error"             — call failed for a non-auth reason.
  • "auth_invalid_all"      — every provider 401'd; no working provider found.
  • None                    — success.

SAFE IN CI: the dead-provider set is process-scoped (module-level dict). A
process restart clears it. Multiple brain modules running in the same process
share the dead set, which is the correct behaviour — if the OAuth token is
expired, all brains should skip it immediately after the first failure.

Do NOT log token values. The provider name and env-var NAME are logged;
the token string is never logged.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any, Callable

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Token sanitization
# --------------------------------------------------------------------------- #
_PRINTABLE_ASCII_RE = re.compile(r"^[\x21-\x7E]+$")


def _sanitize_token(tok: str, env: str) -> str | None:
    """Collapse internal whitespace and validate printable ASCII.

    Legitimate API tokens never contain whitespace.  A token pasted with a
    line-wrap arrives with embedded ``\\n`` / spaces that produce an illegal
    HTTP Authorization header, which the Anthropic SDK surfaces as a generic
    "Connection error."

    Returns the sanitized token, or ``None`` if it is still invalid after
    sanitization (non-printable / non-ASCII chars → provider must be skipped).
    Logs a WARNING when the token was changed (secret should be re-set) or when
    it is completely invalid.
    """
    sanitized = "".join(tok.split())  # collapse ALL internal whitespace
    if sanitized != tok:
        log.warning(
            "llm_auth: credential in %s contained whitespace/newlines — "
            "whitespace removed; token will be used but the GitHub secret "
            "should be re-set to avoid this (pasted with a line-wrap?)",
            env,
        )
    if not sanitized:
        log.warning(
            "llm_auth: credential in %s is empty after whitespace removal — "
            "skipping provider",
            env,
        )
        return None
    if not _PRINTABLE_ASCII_RE.match(sanitized):
        log.warning(
            "llm_auth: credential in %s contains non-printable/non-ASCII "
            "characters — re-set the GitHub secret; skipping provider",
            env,
        )
        return None
    return sanitized

# --------------------------------------------------------------------------- #
# process-scoped dead-provider registry (thread-safe)
# --------------------------------------------------------------------------- #
_dead_lock = threading.Lock()
_dead_providers: set[str] = set()   # keys: "<provider>:<env_var>"


def _dead_key(provider: str, env_var: str) -> str:
    return f"{provider}:{env_var}"


def mark_dead(provider: str, env_var: str) -> None:
    """Mark a provider+env_var combo as dead for this process lifetime."""
    key = _dead_key(provider, env_var)
    with _dead_lock:
        _dead_providers.add(key)
    log.warning("llm_auth: provider '%s' (env=%s) marked dead (401) for this process",
                provider, env_var)


def is_dead(provider: str, env_var: str) -> bool:
    with _dead_lock:
        return _dead_key(provider, env_var) in _dead_providers


def clear_dead() -> None:
    """Clear the dead-provider registry. Useful for tests."""
    with _dead_lock:
        _dead_providers.clear()


# --------------------------------------------------------------------------- #
# sentinel exception — 401 from a provider; caller should try the next one
# --------------------------------------------------------------------------- #
class _AuthDead(Exception):
    pass


# --------------------------------------------------------------------------- #
# 401 detection helpers
# --------------------------------------------------------------------------- #
def _is_auth_error(exc: BaseException) -> bool:
    """Return True when the exception represents an HTTP 401 authentication failure.

    We check two ways:
      1. isinstance against anthropic.AuthenticationError (when the SDK is
         available and the exception is properly typed).
      2. String-match on the exception message for the canonical 401 signature
         (fallback when the SDK is not installed or for subclassed exceptions).
    """
    # Method 1: SDK-typed check (avoids hard dependency on anthropic at import time)
    try:
        import anthropic
        if isinstance(exc, anthropic.AuthenticationError):
            return True
    except (ImportError, AttributeError):
        pass
    # Method 2: message-based fallback
    msg = str(exc).lower()
    return "401" in msg and ("authentication" in msg or "invalid bearer" in msg
                              or "auth_token" in msg or "unauthorized" in msg)


# --------------------------------------------------------------------------- #
# provider descriptor (what each brain passes in)
# --------------------------------------------------------------------------- #
# A provider descriptor is a plain dict with keys:
#   name      (str)  — "oauth" | "anthropic" | "deepseek" (for logging)
#   env_var   (str)  — the env-var name whose presence enables this provider
#   cred      (str)  — the actual credential value (NOT logged)
#   client    (Any)  — a pre-built anthropic.Anthropic client for this provider
#   model     (str)  — model id to use for this provider


def make_call(
    providers: list[dict],
    call_fn: Callable[[Any, str], tuple[str | None, str | None]],
    *,
    context: str = "",
) -> tuple[str | None, str | None, str | None]:
    """Run call_fn(client, model) against the provider waterfall with 401-fallback.

    Parameters
    ----------
    providers:
        Ordered list of provider descriptors (see above). Only providers whose
        cred is non-empty are tried. Dead providers are skipped.
    call_fn:
        Callable(client, model) → (text | None, degraded_reason | None).
        Should NOT catch exceptions — this function catches them.
    context:
        Short string for log messages (e.g. "whitehouse_brain").

    Returns
    -------
    (text, degraded_reason, provider_used)
        text:           the model reply, or None on failure.
        degraded_reason: None on success; one of the reason strings above.
        provider_used:   provider name string ("oauth" / "anthropic" / "deepseek"),
                         or None when no provider could serve.
    """
    last_auth_reason: str | None = None
    any_tried = False

    for p in providers:
        name = p.get("name", "unknown")
        env_var = p.get("env_var", "")
        cred = p.get("cred") or ""
        client = p.get("client")
        model = p.get("model", "")

        if not cred or client is None:
            continue  # provider not configured / no key

        if is_dead(name, env_var):
            log.debug("llm_auth[%s]: skipping dead provider '%s'", context, name)
            continue

        any_tried = True
        try:
            text, reason = call_fn(client, model)
            # Success path
            if last_auth_reason:
                # We fell back from at least one dead provider; surface that in reason
                log.info("llm_auth[%s]: provider '%s' served after fallback from dead provider(s)",
                         context, name)
            return text, reason, name
        except Exception as exc:  # noqa: BLE001
            if _is_auth_error(exc):
                mark_dead(name, env_var)
                last_auth_reason = f"auth_invalid:{name}"
                log.warning(
                    "llm_auth[%s]: provider '%s' returned 401 (env=%s); "
                    "marking dead and trying next provider. "
                    "Check that the secret has not expired.",
                    context, name, env_var,
                )
                continue
            # Non-auth exception: let the brain's own except handle it
            raise

    # All providers exhausted
    if not any_tried:
        return None, "no_provider", None
    if last_auth_reason:
        return None, "auth_invalid_all", None
    return None, "no_provider", None


# --------------------------------------------------------------------------- #
# convenience: build provider list from waterfall config + lib.config secrets
# --------------------------------------------------------------------------- #
def build_providers(
    cfg: dict,
    *,
    opus_model: str | None = None,
    deepseek_model: str | None = None,
    extra_headers: dict | None = None,
) -> list[dict]:
    """Build a provider list from a brain's config dict.

    Handles the standard three-provider waterfall:
        oauth → anthropic → deepseek

    Reads credentials via lib.config.secret() so they are NEVER hardcoded.
    Returns only providers whose credential is present (non-empty).

    Parameters
    ----------
    cfg:
        Brain config dict with standard keys:
          provider_order    (list[str])  — defaults to ["oauth","anthropic","deepseek"]
          oauth_token_env   (str)        — env-var for OAuth token
          api_key_env       (str)        — env-var for Anthropic API key
          deepseek_key_env  (str)        — env-var for DeepSeek key
          deepseek_base_url (str)        — DeepSeek API base URL
          opus_model        (str)        — model id for oauth/anthropic providers
          deepseek_model    (str)        — model id for deepseek provider
    opus_model:
        Override for the Claude model id (oauth / anthropic providers).
    deepseek_model:
        Override for the DeepSeek model id.
    extra_headers:
        Additional headers to attach to every client (merged with oauth beta).
    """
    from lib import config as _config

    OAUTH_BETA = "oauth-2025-04-20"
    DEEPSEEK_DEFAULT_BASE = "https://api.deepseek.com/anthropic"

    order = cfg.get("provider_order") or ["oauth", "anthropic", "deepseek"]
    opus = opus_model or cfg.get("opus_model", "claude-opus-4-8")
    ds_model = deepseek_model or cfg.get("deepseek_model", "deepseek-v4-pro")
    ds_base = cfg.get("deepseek_base_url", DEEPSEEK_DEFAULT_BASE)

    out: list[dict] = []
    for p in order:
        if p == "oauth":
            env = cfg.get("oauth_token_env", "CLAUDE_CODE_OAUTH_TOKEN")
            tok = _config.secret(env)
            if not tok:
                continue
            tok = _sanitize_token(tok, env)
            if tok is None:
                continue
            try:
                import anthropic
                hdrs = {"anthropic-beta": OAUTH_BETA}
                if extra_headers:
                    hdrs.update(extra_headers)
                client = anthropic.Anthropic(api_key=None, auth_token=tok,
                                             default_headers=hdrs)
                out.append({"name": "oauth", "env_var": env, "cred": tok,
                             "client": client, "model": opus})
            except Exception as e:  # noqa: BLE001
                log.warning("llm_auth: oauth client init failed (%s)", e)

        elif p == "anthropic":
            env = cfg.get("api_key_env", "ANTHROPIC_API_KEY")
            key = _config.secret(env)
            if not key:
                continue
            key = _sanitize_token(key, env)
            if key is None:
                continue
            try:
                import anthropic
                hdrs = dict(extra_headers) if extra_headers else {}
                client = anthropic.Anthropic(api_key=key,
                                             **({"default_headers": hdrs} if hdrs else {}))
                out.append({"name": "anthropic", "env_var": env, "cred": key,
                             "client": client, "model": opus})
            except Exception as e:  # noqa: BLE001
                log.warning("llm_auth: anthropic client init failed (%s)", e)

        elif p == "deepseek":
            env = cfg.get("deepseek_key_env", "DEEPSEEK_API_KEY")
            key = _config.secret(env)
            if not key:
                continue
            key = _sanitize_token(key, env)
            if key is None:
                continue
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=key, base_url=ds_base)
                out.append({"name": "deepseek", "env_var": env, "cred": key,
                             "client": client, "model": ds_model})
            except Exception as e:  # noqa: BLE001
                log.warning("llm_auth: deepseek client init failed (%s)", e)

    return out
