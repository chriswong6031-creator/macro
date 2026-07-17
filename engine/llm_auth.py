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


def mark_dead(provider: str, env_var: str, reason: str = "401") -> None:
    """Mark a provider+env_var combo as dead for this process lifetime."""
    key = _dead_key(provider, env_var)
    with _dead_lock:
        _dead_providers.add(key)
    log.warning("llm_auth: provider '%s' (env=%s) marked dead (%s) for this process",
                provider, env_var, reason)


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
    if "401" in msg and ("authentication" in msg or "invalid bearer" in msg
                         or "auth_token" in msg or "unauthorized" in msg):
        return True
    # 403 — revoked/disabled credential (PermissionDeniedError). A key that is
    # forbidden is as dead as one that fails 401: skip it and try the next.
    try:
        import anthropic
        if isinstance(exc, anthropic.PermissionDeniedError):
            return True
    except (ImportError, AttributeError):
        pass
    return "403" in msg and ("forbidden" in msg or "permission" in msg)


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Return True when the exception represents a 429 rate-limit / quota
    exhaustion or a 529 overloaded error — conditions where the CREDENTIAL is
    fine but this key/endpoint cannot serve right now, so the waterfall should
    try the next provider instead of failing the stage."""
    try:
        import anthropic
        if isinstance(exc, anthropic.RateLimitError):
            return True
    except (ImportError, AttributeError):
        pass
    msg = str(exc).lower()
    return ("429" in msg or "rate_limit" in msg or "rate limit" in msg
            or "usage limit" in msg or "quota" in msg
            or "529" in msg or "overloaded" in msg)


# --------------------------------------------------------------------------- #
# OAuth key pool bridge (CLAUDE_CODE_OAUTH_TOKEN_1/2/3 failover)
# --------------------------------------------------------------------------- #
# When a brain config carries "oauth_pool_lane": "<lane>", the single "oauth"
# waterfall entry expands into one provider per POOL key that is (a) present in
# the environment, (b) authorized for that lane by the capability broker, and
# (c) ordered so non-cooling keys come first (lowest 5h-window load first) and
# cooling keys last (a rate-limited key is still a better last resort than a
# hard stage failure).  The legacy single CLAUDE_CODE_OAUTH_TOKEN follows the
# pool, then anthropic/deepseek as before.  Net effect: an offline / revoked /
# rate-limited key never strands a stage while any working key remains.


def _oauth_pool_candidates(lane: str) -> list[tuple[str, str]]:
    """Return [(cap_id, env_var_name)] for pool keys usable for `lane`.

    Ordering: non-cooling keys by ascending 5h-window load, then cooling keys
    by ascending load (emergency fallback).  NEVER raises — any pool/broker
    error degrades to an empty list (legacy single-key behavior).
    REDLINE: returns capability ids and env-var NAMES only, never values.
    """
    try:
        from engine.neuralweb.capability_broker import resolve as _resolve
        from engine.neuralweb.key_pool import (
            discover_present_keys, is_cooling, window_load,
        )

        allowed: list[tuple[str, str]] = []
        for cap_id in discover_present_keys():
            try:
                res = _resolve(cap_id, lane=lane)
                if res.get("allowed") and res.get("ref_name"):
                    allowed.append((cap_id, res["ref_name"]))
            except Exception as exc:  # noqa: BLE001
                log.warning("llm_auth: broker resolve(%s, lane=%s) failed: %s",
                            cap_id, lane, exc)
        cool = {cap_id: bool(is_cooling(cap_id)) for cap_id, _ in allowed}
        load = {cap_id: int(window_load(cap_id)) for cap_id, _ in allowed}
        return sorted(allowed, key=lambda c: (cool[c[0]], load[c[0]]))
    except Exception as exc:  # noqa: BLE001
        log.warning("llm_auth: _oauth_pool_candidates(lane=%s) failed: %s", lane, exc)
        return []


def _note_pool_success(p: dict, context: str, est_tokens: int = 0) -> None:
    """Record a successful session for a pool-backed provider (resolves any
    stale cooling row).  No-op for non-pool providers.  NEVER raises."""
    cap_id = p.get("cap_id")
    if not cap_id:
        return
    try:
        from engine.neuralweb.key_pool import record_session
        record_session(cap_id, est_tokens=est_tokens, stage=context or "llm", outcome="ok")
    except Exception as exc:  # noqa: BLE001
        log.debug("llm_auth: record_session(%s) failed: %s", cap_id, exc)


def _cool_pool_key(p: dict, kind: str) -> None:
    """Persist a cooling row for a pool-backed provider so OTHER processes skip
    the key too ("window" = 5h 429, "auth" = 24h re-probe for a revoked/expired
    token).  No-op for non-pool providers.  NEVER raises."""
    cap_id = p.get("cap_id")
    if not cap_id:
        return
    try:
        from engine.neuralweb.key_pool import mark_cooling
        mark_cooling(cap_id, cool_kind=kind)
    except Exception as exc:  # noqa: BLE001
        log.debug("llm_auth: mark_cooling(%s, %s) failed: %s", cap_id, kind, exc)


# --------------------------------------------------------------------------- #
# provider descriptor (what each brain passes in)
# --------------------------------------------------------------------------- #
# A provider descriptor is a plain dict with keys:
#   name      (str)  — "oauth" | "anthropic" | "deepseek" (for logging)
#   env_var   (str)  — the env-var name whose presence enables this provider
#   cred      (str)  — the actual credential value (NOT logged)
#   client    (Any)  — a pre-built anthropic.Anthropic client for this provider
#   model     (str)  — model id to use for this provider
#   cap_id    (str)  — OPTIONAL: key-pool capability id when this provider is a
#                      pool key (enables ledger cooling/accounting)


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
    saw_rate_limit = False
    last_exc: BaseException | None = None
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
            log.debug("llm_auth[%s]: skipping dead provider '%s' (env=%s)",
                      context, name, env_var)
            continue

        any_tried = True
        try:
            result = call_fn(client, model)
            text, reason = result[0], result[1]
            # Success path
            if last_auth_reason or saw_rate_limit or last_exc is not None:
                # We fell back from at least one failed provider; surface that
                log.info("llm_auth[%s]: provider '%s' (env=%s) served after fallback",
                         context, name, env_var)
            # --- usage capture (NEVER-RAISE) -----------------------------------
            # call_fn may return a 3-tuple (text, reason, resp) where resp is the
            # raw SDK response object (has .usage attribute).  Existing callers
            # return 2-tuples; they are unaffected (len check is backward-compat).
            _resp_obj = result[2] if len(result) > 2 else None
            _usage_obj = getattr(_resp_obj, "usage", None) if _resp_obj is not None else None
            _capture_usage(p, _usage_obj, context)
            # -------------------------------------------------------------------
            in_tok = int(getattr(_usage_obj, "input_tokens", 0) or 0)
            out_tok = int(getattr(_usage_obj, "output_tokens", 0) or 0)
            _note_pool_success(p, context, est_tokens=in_tok + out_tok)
            return text, reason, name
        except Exception as exc:  # noqa: BLE001
            if _is_auth_error(exc):
                mark_dead(name, env_var, reason="auth")
                _cool_pool_key(p, "auth")
                last_auth_reason = f"auth_invalid:{name}"
                log.warning(
                    "llm_auth[%s]: provider '%s' returned 401/403 (env=%s); "
                    "marking dead and trying next provider. "
                    "Check that the secret has not expired.",
                    context, name, env_var,
                )
                continue
            if _is_rate_limit_error(exc):
                mark_dead(name, env_var, reason="rate_limited")
                _cool_pool_key(p, "window")
                saw_rate_limit = True
                log.warning(
                    "llm_auth[%s]: provider '%s' rate-limited/overloaded (env=%s); "
                    "cooling and trying next provider.",
                    context, name, env_var,
                )
                continue
            # Unexpected (connection / 5xx / SDK) error: remember it, but keep
            # walking the waterfall — a different key or endpoint may still
            # serve.  If nothing serves, the LAST such error is re-raised so
            # single-provider callers see exactly the legacy behavior.
            last_exc = exc
            log.warning(
                "llm_auth[%s]: provider '%s' (env=%s) failed (%s: %s); "
                "trying next provider.",
                context, name, env_var, type(exc).__name__, exc,
            )
            continue

    # All providers exhausted
    if last_exc is not None:
        raise last_exc
    if saw_rate_limit:
        return None, "rate_limited_all", None
    if not any_tried:
        return None, "no_provider", None
    if last_auth_reason:
        return None, "auth_invalid_all", None
    return None, "no_provider", None


# --------------------------------------------------------------------------- #
# Usage capture helper (called on every successful make_call)
# --------------------------------------------------------------------------- #

def _capture_usage(p: dict, usage_obj, context: str) -> None:
    """Record one AI usage row to lib.ai_costs.  NEVER raises.

    Parameters
    ----------
    p:          provider descriptor (has "name", "cap_id", and optional
                "usage_lane", "usage_cycle_id", "usage_stage" injected by
                build_providers callers via the cfg dict that built it).
    usage_obj:  raw anthropic Usage object (or None).  Expected attributes:
                input_tokens, output_tokens, cache_read_input_tokens,
                cache_creation_input_tokens — all optional (getattr, default 0).
    context:    the make_call context string (used as stage fallback).
    """
    try:
        # When the SDK returns no usage object (2-tuple legacy path), skip the
        # ledger write entirely — a zero-token row is noise and creates
        # metabolism duplicates when propose/adjudicate also record directly.
        if usage_obj is None:
            return

        in_tok = int(getattr(usage_obj, "input_tokens", 0) or 0)
        out_tok = int(getattr(usage_obj, "output_tokens", 0) or 0)
        cr_tok = int(getattr(usage_obj, "cache_read_input_tokens", 0) or 0)
        cc_tok = int(getattr(usage_obj, "cache_creation_input_tokens", 0) or 0)

        name = p.get("name", "unknown")
        # Map provider name → provider vocabulary
        if name in ("oauth",):
            ai_provider = "claude_oauth"
            cost_basis = "subscription"
        elif name == "anthropic":
            ai_provider = "claude_api"
            cost_basis = "metered"
        elif name == "deepseek":
            ai_provider = "deepseek"
            cost_basis = "metered"
        else:
            ai_provider = "claude_oauth"
            cost_basis = "subscription"

        lane = p.get("usage_lane") or p.get("_usage_lane") or "unknown"
        cap_id = p.get("cap_id")
        key_id: str | None
        if cap_id:
            key_id = cap_id
        elif name in ("oauth",):
            key_id = "legacy"
        else:
            key_id = None

        model = p.get("model") or None
        cycle_id = str(p.get("usage_cycle_id") or "")
        stage = str(p.get("usage_stage") or context or "")

        from lib import ai_costs as _ac  # noqa: PLC0415
        _ac.record_usage(
            lane=lane,
            provider=ai_provider,
            model=model,
            key_id=key_id,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cache_read_tokens=cr_tok,
            cache_creation_tokens=cc_tok,
            cost_basis=cost_basis,
            cycle_id=cycle_id,
            stage=stage,
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("llm_auth: _capture_usage failed: %s", exc)


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

    def _mk_oauth_provider(env: str, cap_id: str | None = None) -> dict | None:
        """Build one oauth provider descriptor from an env-var NAME, or None."""
        tok = _config.secret(env)
        if not tok:
            return None
        tok = _sanitize_token(tok, env)
        if tok is None:
            return None
        try:
            import anthropic  # noqa: PLC0415
            import httpx  # noqa: PLC0415
            hdrs = {"anthropic-beta": OAUTH_BETA}
            if extra_headers:
                hdrs.update(extra_headers)

            # V10 usage-header capture: attach a response event hook that
            # records anthropic-ratelimit-* headers from every response.
            # The key identity for the hook is cap_id (pool key) or "legacy".
            _hook_key_id = cap_id if cap_id else "legacy"

            def _usage_hook(response: httpx.Response) -> None:  # type: ignore[name-defined]
                try:
                    from engine.neuralweb import key_pool as _kp  # noqa: PLC0415
                    _kp.record_usage_headers(
                        _hook_key_id,
                        dict(response.headers),
                        response.status_code,
                    )
                except Exception as _hook_exc:  # noqa: BLE001
                    log.debug(
                        "llm_auth: usage hook failed for key_id=%s (%s)",
                        _hook_key_id, _hook_exc,
                    )

            # Build the httpx client with the usage hook.  Both construction
            # paths are wrapped: if the hook-bearing client cannot be built
            # (e.g. mocked SDK in tests, env without httpx), we fall back to
            # no custom http_client so existing call paths remain unaffected.
            http_client = None
            try:
                http_client = anthropic.DefaultHttpxClient(
                    event_hooks={"response": [_usage_hook]}
                )
            except Exception:  # noqa: BLE001
                try:
                    # Fallback: plain httpx.Client mirroring the SDK's default
                    # timeout (600s read) so long Opus completions are not
                    # silently truncated; getattr guards stubbed SDK in tests.
                    http_client = httpx.Client(
                        timeout=getattr(
                            anthropic, "DEFAULT_TIMEOUT",
                            httpx.Timeout(600.0, connect=5.0),
                        ),
                        event_hooks={"response": [_usage_hook]},
                    )
                except Exception:  # noqa: BLE001
                    http_client = None  # give up on the hook; call still works

            client_kwargs: dict = {
                "api_key": None,
                "auth_token": tok,
                "default_headers": hdrs,
            }
            if http_client is not None:
                client_kwargs["http_client"] = http_client
            client = anthropic.Anthropic(**client_kwargs)
            prov = {"name": "oauth", "env_var": env, "cred": tok,
                    "client": client, "model": opus}
            if cap_id:
                prov["cap_id"] = cap_id
            return prov
        except Exception as e:  # noqa: BLE001
            log.warning("llm_auth: oauth client init failed for env=%s (%s)", env, e)
            return None

    out: list[dict] = []
    for p in order:
        if p == "oauth":
            # Pool expansion (CLAUDE_CODE_OAUTH_TOKEN_1/2/3): opt-in via
            # cfg["oauth_pool_lane"].  Pool keys authorized for that lane come
            # first (best-available ordering).
            #
            # LEGACY DEPRECATION (V11):
            # • Pool-aware consumers (cfg["oauth_pool_lane"] set): when at
            #   least one pool key is present and enabled, the legacy
            #   CLAUDE_CODE_OAUTH_TOKEN slot is SUPPRESSED entirely; it is only
            #   added as a last resort when zero pool keys are in the
            #   environment.  A single log.warning is emitted in that case.
            # • Non-pool consumers (cfg["oauth_pool_lane"] not set): the legacy
            #   env slot is EXPANDED so it iterates all present+enabled pool
            #   keys too (ordered by window_load, cooling-aware) — this ensures
            #   no consumer anywhere depends on the deprecated token.
            pool_envs: set[str] = set()
            lane = cfg.get("oauth_pool_lane") or ""
            if lane:
                for cap_id, ref_env in _oauth_pool_candidates(lane):
                    prov = _mk_oauth_provider(ref_env, cap_id=cap_id)
                    if prov is not None:
                        pool_envs.add(ref_env)
                        out.append(prov)
                # Legacy slot: add ONLY when no pool keys resolved (last resort)
                _legacy_enabled = True
                try:
                    from engine.neuralweb import key_pool as _kp  # noqa: PLC0415
                    _legacy_enabled = _kp.is_enabled("legacy")
                except Exception as _e:  # noqa: BLE001
                    log.debug("llm_auth: key_pool.is_enabled('legacy') failed (%s) — including legacy", _e)
                env = cfg.get("oauth_token_env", "CLAUDE_CODE_OAUTH_TOKEN")
                if env and env not in pool_envs:
                    if pool_envs:
                        # Pool keys are present — suppress legacy entirely
                        pass
                    elif _legacy_enabled:
                        # Zero pool keys in env — add legacy as last resort and warn
                        log.warning(
                            "llm_auth: no pool keys present; falling back to legacy "
                            "CLAUDE_CODE_OAUTH_TOKEN — this token is deprecated; "
                            "set CLAUDE_CODE_OAUTH_TOKEN_3..7 secrets to remove this warning"
                        )
                        prov = _mk_oauth_provider(env)
                        if prov is not None:
                            out.append(prov)
            else:
                # Non-pool consumer: expand the legacy env to also iterate all
                # present+enabled pool keys so no consumer relies on the legacy
                # single token.  Pool keys come first (cooling-aware ordering:
                # non-cooling keys sorted by ascending 5h-window load, cooling
                # last) — mirrors _oauth_pool_candidates ordering.
                _pool_added: set[str] = set()
                try:
                    from engine.neuralweb import key_pool as _kp  # noqa: PLC0415
                    # Collect (cap_id, ref_env) pairs for all present keys
                    _candidates: list[tuple[str, str]] = []
                    for cap_id in _kp.discover_present_keys():
                        try:
                            ref_env = _kp.get_secret_ref(cap_id)
                        except Exception:  # noqa: BLE001
                            ref_env = None
                        if not ref_env:
                            # fall back: derive ref from cap_id shape
                            # e.g. "claude_code_oauth_3" → CLAUDE_CODE_OAUTH_TOKEN_3
                            suffix = cap_id.split("_")[-1]
                            ref_env = f"CLAUDE_CODE_OAUTH_TOKEN_{suffix}" if suffix.isdigit() else None
                        if ref_env:
                            _candidates.append((cap_id, ref_env))
                    # Sort: non-cooling first (lowest window_load first), cooling last
                    _cool_map = {}
                    _load_map = {}
                    for cap_id, _ in _candidates:
                        try:
                            _cool_map[cap_id] = bool(_kp.is_cooling(cap_id))
                        except Exception:  # noqa: BLE001
                            _cool_map[cap_id] = False
                        try:
                            _load_map[cap_id] = int(_kp.window_load(cap_id))
                        except Exception:  # noqa: BLE001
                            _load_map[cap_id] = 0
                    _candidates.sort(key=lambda c: (_cool_map[c[0]], _load_map[c[0]]))
                    for cap_id, ref_env in _candidates:
                        if ref_env not in _pool_added:
                            prov = _mk_oauth_provider(ref_env, cap_id=cap_id)
                            if prov is not None:
                                _pool_added.add(ref_env)
                                out.append(prov)
                except Exception as _e:  # noqa: BLE001
                    log.debug("llm_auth: non-pool oauth expansion failed (%s) — legacy-only", _e)
                # Legacy env — only add when not already covered by pool expansion
                env = cfg.get("oauth_token_env", "CLAUDE_CODE_OAUTH_TOKEN")
                if env and env not in _pool_added:
                    prov = _mk_oauth_provider(env)
                    if prov is not None:
                        out.append(prov)

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

    # Inject usage attribution metadata from cfg into every provider descriptor.
    # _capture_usage() reads these keys to populate the ai_costs ledger row.
    _usage_lane = cfg.get("usage_lane") or ""
    _usage_cycle_id = cfg.get("usage_cycle_id") or ""
    _usage_stage = cfg.get("usage_stage") or ""
    if _usage_lane:
        for prov in out:
            prov["usage_lane"] = _usage_lane
            if _usage_cycle_id:
                prov["usage_cycle_id"] = _usage_cycle_id
            if _usage_stage:
                prov["usage_stage"] = _usage_stage

    return out
