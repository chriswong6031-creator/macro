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

import inspect
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


def _lane_weekly_ceiling_pct(lane: str) -> float | None:
    """Weekly-utilisation ceiling (%) above which a pool key is DE-PRIORITISED for
    this lane (never excluded — soft ordering only).

    Mastermind chat lanes (``brain-*``) may lean on a key up to 95% weekly (operator
    2026-07-25) — higher than the metabolism BUILD loop's 85% (budget_gate
    ``weekly_key_stop_pct``) — leaving a small subscription reserve. Other lanes get
    None here (the build loop enforces its own 85% hard stop separately).
    Env override: ``MASTERMIND_WEEKLY_CEILING_PCT``. NEVER raises."""
    try:
        if not str(lane or "").startswith("brain"):
            return None
        raw = os.environ.get("MASTERMIND_WEEKLY_CEILING_PCT", "").strip()
        if raw:
            v = float(raw)
            if 0 < v <= 100:
                return v
        return 95.0
    except Exception:  # noqa: BLE001
        return 95.0


def _weekly_pct(cap_id: str) -> float | None:
    """Latest known weekly utilisation % for a pool key (reported ratelimit headers,
    else estimated), or None when unknown. NEVER raises."""
    try:
        from engine.metabolism import budget_gate as _bg  # noqa: PLC0415
        pw = _bg.key_budget(cap_id).get("pct_weekly")
        return float(pw) if pw is not None else None
    except Exception:  # noqa: BLE001
        return None


def _oauth_pool_candidates(lane: str, ceiling_pct: float | None = None) -> list[tuple[str, str]]:
    """Return [(cap_id, env_var_name)] for pool keys usable for `lane`.

    Ordering (best first): under-ceiling before over-ceiling, then non-cooling
    before cooling, then ascending 5h-window load. The weekly ceiling is a soft
    de-prioritisation (a key over 95% still gets tried when nothing better exists,
    then the caller falls to the degraded models) — see _lane_weekly_ceiling_pct.
    ``ceiling_pct`` (from config, MNZ-R12) wins when given; else the lane default.
    NEVER raises — any pool/broker error degrades to an empty list (legacy
    single-key behavior).
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
        # Lane-aware weekly ceiling (Mastermind 95% vs build loop 85%): keys past the
        # ceiling sort AFTER under-ceiling keys but are still returned (fail-open).
        # Config value (MNZ-R12) wins; else the lane default.
        ceiling = ceiling_pct if ceiling_pct is not None else _lane_weekly_ceiling_pct(lane)
        if ceiling is not None:
            over = {cap_id: ((_weekly_pct(cap_id) or 0.0) >= ceiling) for cap_id, _ in allowed}
        else:
            over = {cap_id: False for cap_id, _ in allowed}
        return sorted(allowed, key=lambda c: (over[c[0]], cool[c[0]], load[c[0]]))
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
#   name      (str)  — "oauth" | "codex" | "anthropic" | "deepseek" (logging)
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
        elif name == "codex":
            ai_provider = "codex"
            cost_basis = "subscription"
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

def _client_tuning_kwargs(cfg: dict) -> dict:
    """Optional SDK client tuning read from cfg — {} when neither key is present.

    ``client_max_retries`` (int): the SDK retries the SAME credential twice by
    default, so one dead/429 key costs ~2.4s before the waterfall even sees it
    (probe: 4.23s default vs 0.49s at 0). For a multi-key waterfall the FAILOVER
    CHAIN is the retry, so a lane that walks its own keys sets this to 0.
    ``client_timeout_s`` (float): SDK default is 600s — a hung candidate can
    otherwise stall a user-facing turn for ten minutes.

    Absent keys are OMITTED (never passed as None) so every existing consumer
    builds byte-identical clients. An unusable value is logged and dropped —
    a bad config line must never fail client construction.

    WHAT max_retries DOES **NOT** COVER (measured while building the 07-31
    empty-text guard; house memory "SDK retries defeat failover walks"). The
    anthropic SDK retries on transport failures and on 408/409/429/5xx only —
    it inspects the HTTP status, never the body. The outage response was a
    clean **HTTP 200** carrying a thinking block and no text, so no value of
    max_retries would ever have retried it, and `max_retries=0` (what
    engine/marketing/copywriter.py's v2 lane sets) does not disable a retry
    that was never going to happen. That is why the empty-text recovery had to
    be built explicitly in `empty_text_diagnosis` / `empty_text_retry_plan`
    rather than bought from the client. max_retries remains the wrong lever for
    HARD errors too, for the original reason: the failover chain is this
    module's retry, and an SDK that retries the same dead credential twice
    just delays the walk.
    """
    out: dict = {}
    retries = cfg.get("client_max_retries")
    if retries is not None:
        try:
            out["max_retries"] = int(retries)
        except (TypeError, ValueError):
            log.warning("llm_auth: client_max_retries=%r is not an int — SDK default kept", retries)
    timeout_s = cfg.get("client_timeout_s")
    if timeout_s is not None:
        try:
            secs = float(timeout_s)
        except (TypeError, ValueError):
            log.warning("llm_auth: client_timeout_s=%r is not a number — SDK default kept", timeout_s)
        else:
            try:
                import httpx  # noqa: PLC0415
                out["timeout"] = httpx.Timeout(secs, connect=5.0)
            except Exception:  # noqa: BLE001 — httpx absent/stubbed: a plain float is accepted too
                out["timeout"] = secs
    return out


class _NoThinkingMessages:
    """`messages` proxy that defaults DeepSeek's thinking mode OFF.

    An explicit `thinking=` (or one already inside `extra_body`) always wins, so
    a lane that genuinely wants reasoning simply asks for it.
    """

    def __init__(self, inner: "Any") -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> "Any":
        return getattr(self._inner, name)

    def create(self, **kw: "Any") -> "Any":
        extra = dict(kw.get("extra_body") or {})
        if "thinking" not in kw and "thinking" not in extra:
            extra["thinking"] = {"type": "disabled"}
            kw["extra_body"] = extra
        return self._inner.create(**kw)


class _DeepSeekClient:
    """Thin pass-through wrapper; only `.messages` behaves differently."""

    #: Read by `empty_text_retry_plan`. A client that ALREADY sends
    #: thinking=disabled on every call cannot be recovered by sending it again —
    #: for this one the useful second attempt is a bigger output budget.
    thinking_disabled_by_default = True

    def __init__(self, inner: "Any") -> None:
        self._inner = inner
        self.messages = _NoThinkingMessages(inner.messages)

    def __getattr__(self, name: str) -> "Any":
        return getattr(self._inner, name)


def _deepseek_no_thinking(client: "Any") -> "Any":
    """Wrap a DeepSeek client so it stops spending the caller's budget thinking.

    THE OUTAGE THIS FIXES (2026-07-31). `deepseek-v4-pro` — llm_auth's default
    DeepSeek model — returns a ThinkingBlock BEFORE the text block on the
    Anthropic-compat endpoint and bills roughly 4x the output tokens for it
    (probed live 2026-07-26). Callers here pass a SMALL `max_tokens` because
    they want one short answer: the marketing copywriter sends 400, enough for a
    post and nowhere near enough for a post plus the model's reasoning. The
    response hits the cap mid-thought and comes back carrying NO text block.

    Every symptom pointed away from the cause. llm_auth logged "provider
    'deepseek' served after fallback" — the call genuinely succeeded. The
    callers' extraction was correct (they filter every block of type=="text"
    rather than reading content[0], so this was not the classic content[0] bug).
    The post was simply dropped at stage=provider with "provider returned no
    text", which reads as an outage. On the 2026-07-31 nightly that was 914 of
    915 planned posts and a content plan with total_posts=0.

    FIXED HERE RATHER THAN IN THE CALLERS. Eleven sites across engine/marketing
    and engine/press build their own request and hand it to make_call; patching
    the one that was on fire would leave ten carrying the defect and every future
    lane inheriting it. The provider is the thing that thinks, so the provider is
    where it is turned off — and a lane that wants reasoning still gets it by
    passing `thinking` explicitly, which this never overrides.

    Wrapping rather than subclassing keeps every other attribute (usage hooks,
    `with_options`, `close`) pointing at the real client. Fail-soft: if the
    client has no `.messages` at all (a stub in a test), the original is
    returned untouched.
    """
    try:
        if getattr(client, "messages", None) is None:
            return client
        return _DeepSeekClient(client)
    except Exception as exc:  # noqa: BLE001
        log.warning("llm_auth: could not wrap DeepSeek client (%s) — "
                    "thinking stays at its default", exc)
        return client


# --------------------------------------------------------------------------- #
# Empty-text responses: the GENERIC form of the 2026-07-30/31 outage
# --------------------------------------------------------------------------- #
#
# `_deepseek_no_thinking` above fixes the instance. This block fixes the CLASS.
#
# What actually happened, twice: a provider answered HTTP 200, spent the whole
# `max_tokens` budget on a reasoning block, and returned a response carrying no
# text block at all. `make_call` cannot see that — a call that does not raise is
# a success, so the waterfall STOPS at the provider that served nothing and the
# three healthy rungs below it are never tried. 914 of 915 planned posts died
# that way on 07-30 and again on 07-31, through green CI both nights.
#
# Nothing about that is DeepSeek-specific. Any Anthropic-compatible endpoint
# that emits reasoning ahead of text under a small output cap produces exactly
# this shape, and this repo points eleven call sites at four providers with a
# per-item cap in the low hundreds of tokens. So the DETECTION and the RECOVERY
# PLAN live here, provider-agnostic and reusable, while the decision of how many
# extra calls an item may buy stays with the caller (a nightly batch of 915
# items and a single user-facing turn cannot share that budget).

#: `stop_reason` values meaning "the answer was cut off because the output
#: budget ran out". Anthropic says "max_tokens"; the compat endpoints in front
#: of other model families report the same condition under their own spelling,
#: and an unknown spelling must not silently read as a clean stop.
TOKEN_EXHAUSTION_STOP_REASONS = frozenset({
    "max_tokens", "max_output_tokens", "max_completion_tokens", "length",
})

#: Content-block types that carry REASONING rather than the answer. A response
#: made only of these is a model that thought and never spoke.
REASONING_BLOCK_TYPES = frozenset({"thinking", "redacted_thinking", "reasoning"})

#: The one extra_body switch that turns reasoning off on the Anthropic-compatible
#: endpoints that support it.
THINKING_DISABLED_EXTRA_BODY: dict = {"thinking": {"type": "disabled"}}


def response_text(resp: "Any") -> str:
    """Every text block of an Anthropic-shaped response, concatenated.

    NEVER raises: a response object that does not have the expected shape reads
    as "no text", which is the same thing the caller would have to do anyway.
    Filtering on ``type == "text"`` (rather than reading ``content[0]``) is
    deliberate — it is what makes a leading thinking block a MISSING ANSWER
    rather than a crash, and it is why the 07-31 outage looked like a success.
    """
    try:
        return "".join(
            str(getattr(b, "text", "") or "")
            for b in (getattr(resp, "content", None) or [])
            if str(getattr(b, "type", "")) == "text"
        )
    except Exception:  # noqa: BLE001 — a diagnosis helper must never be the fault
        return ""


def empty_text_diagnosis(resp: "Any") -> dict | None:
    """``None`` when the response carries text; otherwise WHY it did not.

    Returns ``{"blocks", "stop_reason", "reasoning_only", "token_exhausted",
    "retryable"}``. ``retryable`` is the caller's go/no-go for spending ONE more
    call on the same provider.

    THE `retryable` RULE IS DELIBERATELY WIDER THAN THE OBSERVED FAULT. The
    07-31 response was reasoning-only AND stop_reason=max_tokens, so an
    ``and`` would have caught it. It is an ``or`` here because both halves are
    independently diagnostic: a reasoning-only body is the thinking fault
    whatever the endpoint chose to call its stop reason (several compat layers
    report "end_turn" after truncating), and a truncated response with no text
    is a budget fault whatever blocks it happens to carry. The cost of the
    widening is bounded by the caller — one extra call — and the cost of the
    narrowing was two dark nights.
    """
    if response_text(resp):
        return None
    try:
        blocks = [str(getattr(b, "type", "?") or "?")
                  for b in (getattr(resp, "content", None) or [])]
    except Exception:  # noqa: BLE001
        blocks = []
    stop_reason = str(getattr(resp, "stop_reason", "") or "")
    reasoning_only = bool(blocks) and all(b in REASONING_BLOCK_TYPES for b in blocks)
    token_exhausted = stop_reason in TOKEN_EXHAUSTION_STOP_REASONS
    return {
        "blocks": blocks,
        "stop_reason": stop_reason or "?",
        "reasoning_only": reasoning_only,
        "token_exhausted": token_exhausted,
        "retryable": bool(reasoning_only or token_exhausted),
    }


def _innermost_messages(client: "Any") -> "Any":
    """Walk `.messages` through this module's proxy wrappers to the real API.

    `_DeepSeekClient` puts a `_NoThinkingMessages` proxy in front of the SDK's
    `messages`, and that proxy's ``create(**kw)`` accepts anything. Sniffing the
    proxy would therefore answer questions about the WRAPPER rather than about
    the endpoint. The loop is bounded so a self-referential stub cannot hang a
    nightly.
    """
    msgs = getattr(client, "messages", None)
    for _ in range(4):
        inner = getattr(msgs, "_inner", None)
        if inner is None:
            break
        msgs = inner
    return msgs


def client_supports_thinking_switch(client: "Any") -> bool:
    """True when this client's ``messages.create`` takes an ``extra_body`` kwarg.

    EXPLICIT PARAMETER ONLY — a bare ``**kwargs`` does NOT count, and that
    distinction is the whole point. `engine.codex_provider._Messages.create`
    takes ``**kwargs`` and silently discards everything it does not recognise,
    so a ``**kwargs``-accepting signature would advertise a switch that does
    nothing and turn the one retry we allow into a byte-identical repeat of the
    call that just failed. The real Anthropic SDK names ``extra_body`` in its
    signature; that name is the capability.
    """
    create = getattr(_innermost_messages(client), "create", None)
    if create is None:
        return False
    try:
        params = inspect.signature(create).parameters
    except (TypeError, ValueError):  # builtins / C-level callables
        return False
    return "extra_body" in params


def empty_text_retry_plan(client: "Any", max_tokens: int) -> dict:
    """How to ask ONE more time after a textless response.

    Returns ``{"how", "max_tokens", "extra_body"}``:

      * ``thinking_disabled`` — the endpoint takes the extra_body switch, so the
        cheapest fix is to stop paying for reasoning we discard;
      * ``max_tokens_doubled`` — it does not (or it already sends the switch on
        every call), so buy enough budget for the reasoning AND the answer.

    A client that already defaults thinking off is routed to the doubling branch
    on purpose: sending a switch that is already set is a repeat of the failed
    call, not a retry.
    """
    if (client_supports_thinking_switch(client)
            and not getattr(client, "thinking_disabled_by_default", False)):
        return {"how": "thinking_disabled",
                "max_tokens": int(max_tokens),
                "extra_body": dict(THINKING_DISABLED_EXTRA_BODY)}
    try:
        doubled = max(1, int(max_tokens) * 2)
    except (TypeError, ValueError):
        doubled = int(max_tokens or 1)
    return {"how": "max_tokens_doubled", "max_tokens": doubled, "extra_body": None}


def providers_after(providers: list[dict], name: str | None) -> list[dict]:
    """The tail of the waterfall BELOW the provider named ``name``.

    The order is the one `build_providers` already produced — a caller doing a
    one-rung failover must not re-derive it, because that order carries pool
    balancing and cross-process cooling that a fresh guess would throw away.
    An unknown name yields [] rather than the whole list: failing over to the
    provider that just failed is worse than dropping the item.
    """
    if not providers or not name:
        return []
    for i, p in enumerate(providers):
        if p.get("name") == name:
            return list(providers[i + 1:])
    return []


def first_usable(providers: list[dict]) -> dict | None:
    """The first descriptor `make_call` would actually try, or None.

    Same three gates make_call applies (credential present, client built, not
    marked dead this process) so a caller that wants exactly ONE more attempt
    can hand make_call a one-element list and get one attempt rather than a
    silent skip.
    """
    for p in providers or []:
        if not p.get("cred") or p.get("client") is None:
            continue
        if is_dead(str(p.get("name", "")), str(p.get("env_var", ""))):
            continue
        return p
    return None


def build_providers(
    cfg: dict,
    *,
    opus_model: str | None = None,
    deepseek_model: str | None = None,
    extra_headers: dict | None = None,
) -> list[dict]:
    """Build a provider list from a brain's config dict.

    Handles the standard provider waterfall:
        oauth pool → attached Codex account → anthropic → deepseek

    When a lane has no OAuth rung (for example DeepSeek-first brain-fast),
    Codex is appended as the final fallback.  A host without the Codex CLI and
    an attached login omits that rung without affecting existing providers.

    Reads credentials via lib.config.secret() so they are NEVER hardcoded.
    Returns only providers whose credential is present (non-empty).

    Parameters
    ----------
    cfg:
        Brain config dict with standard keys:
          provider_order    (list[str])  — Codex is auto-inserted unless disabled
          oauth_token_env   (str)        — env-var for OAuth token
          api_key_env       (str)        — env-var for Anthropic API key
          deepseek_key_env  (str)        — env-var for DeepSeek key
          deepseek_base_url (str)        — DeepSeek API base URL
          opus_model        (str)        — model id for oauth/anthropic providers
          deepseek_model    (str)        — model id for deepseek provider
          codex_source_model (str)       — model id for attached Codex provider
          codex_reasoning_effort (str)   — Codex reasoning effort (e.g. high)
          client_max_retries (int|None)  — SDK max_retries for every client built
                                           here; absent → SDK default (2)
          client_timeout_s  (float|None) — per-request timeout in seconds;
                                           absent → SDK default (600s)
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

    configured_order = list(
        cfg.get("provider_order") or ["oauth", "anthropic", "deepseek"]
    )
    opus = opus_model or cfg.get("opus_model", "claude-opus-4-8")
    ds_model = deepseek_model or cfg.get("deepseek_model", "deepseek-v4-pro")
    ds_base = cfg.get("deepseek_base_url", DEEPSEEK_DEFAULT_BASE)
    # Treat the attached account like another subscription token: immediately
    # after the OAuth pool, before metered API providers. DeepSeek-only/Anthropic-
    # only lanes keep their existing order and receive Codex as the last resort.
    order = list(configured_order)
    if "codex" not in order and cfg.get("codex_provider", True) is not False:
        if "oauth" in order:
            order.insert(order.index("oauth") + 1, "codex")
        else:
            order.append("codex")

    codex_source_model = cfg.get("codex_source_model")
    if not codex_source_model:
        if any(p in configured_order for p in ("oauth", "anthropic")):
            codex_source_model = opus
        else:
            codex_source_model = ds_model
    # Latency guards for every client built below — {} unless the caller's cfg opts in.
    tuning = _client_tuning_kwargs(cfg)

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
            # NOTE: httpx is imported LAZILY, inside the fallback branch that is
            # the only place it is actually used (the `response: httpx.Response`
            # annotation below is never evaluated — this module is
            # `from __future__ import annotations`).  Do NOT hoist it back up
            # here: this whole block is wrapped in a blanket `except Exception`
            # that returns None, so an eager import turned ANY transient failure
            # of that first heavyweight import into "the credential does not
            # exist" and silently deleted the provider from the waterfall.  The
            # usage-capture hook is an optimisation; it must never cost a key.
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
                    import httpx  # noqa: PLC0415
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
                **tuning,
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
            _ceiling = cfg.get("oauth_weekly_ceiling_pct")  # MNZ-R12: config, not literal
            if lane:
                for cap_id, ref_env in _oauth_pool_candidates(lane, ceiling_pct=_ceiling):
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

        elif p == "codex":
            try:
                from engine import codex_provider as _codex  # noqa: PLC0415
                if not _codex.is_available():
                    continue
                codex_timeout = cfg.get(
                    "codex_timeout_s",
                    cfg.get("client_timeout_s", 180),
                )
                codex_effort = str(cfg.get("codex_reasoning_effort") or "").strip()
                if codex_effort:
                    client = _codex.CodexClient(
                        timeout_s=int(float(codex_timeout)),
                        reasoning_effort=codex_effort,
                    )
                else:
                    client = _codex.CodexClient(timeout_s=int(float(codex_timeout)))
                out.append({
                    "name": "codex",
                    "env_var": _codex.CODEX_ENV_ID,
                    "cred": "attached",
                    "client": client,
                    "model": _codex.translate_model(str(codex_source_model)),
                    "source_model": str(codex_source_model),
                    "cap_id": _codex.CODEX_CAPABILITY_ID,
                })
            except Exception as e:  # noqa: BLE001
                log.warning("llm_auth: Codex provider init failed (%s)", e)

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
                                             **({"default_headers": hdrs} if hdrs else {}),
                                             **tuning)
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
                def _deepseek_usage_hook(response) -> None:
                    try:
                        from engine.neuralweb import key_pool as _kp  # noqa: PLC0415
                        _kp.record_usage_headers(
                            "deepseek_api_key",
                            dict(response.headers),
                            response.status_code,
                        )
                    except Exception as _hook_exc:  # noqa: BLE001
                        log.debug("llm_auth: DeepSeek usage hook failed (%s)", _hook_exc)

                http_client = None
                try:
                    http_client = anthropic.DefaultHttpxClient(
                        event_hooks={"response": [_deepseek_usage_hook]}
                    )
                except Exception:  # noqa: BLE001
                    http_client = None
                client_kwargs = {"api_key": key, "base_url": ds_base, **tuning}
                if http_client is not None:
                    client_kwargs["http_client"] = http_client
                client = _deepseek_no_thinking(anthropic.Anthropic(**client_kwargs))
                out.append({"name": "deepseek", "env_var": env, "cred": key,
                             "client": client, "model": ds_model,
                             "cap_id": "deepseek_api_key"})
            except Exception as e:  # noqa: BLE001
                log.warning("llm_auth: deepseek client init failed (%s)", e)

    # Cross-process cooldown: keep every configured provider as a last resort,
    # but move a key that another process recently rate-limited/auth-failed
    # behind all non-cooling candidates. Stable sort preserves the configured
    # waterfall within each group.
    if cfg.get("respect_provider_cooling", True):
        try:
            from engine.neuralweb.key_pool import is_cooling as _is_cooling  # noqa: PLC0415
            out.sort(key=lambda prov: bool(
                prov.get("cap_id") and _is_cooling(str(prov["cap_id"]))
            ))
        except Exception as e:  # noqa: BLE001
            log.debug("llm_auth: provider cooldown ordering failed (%s)", e)

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


# --------------------------------------------------------------------------- #
# Deliberation model selector (PR-R8 — Prophet / Fable grant)
# --------------------------------------------------------------------------- #

def deliberation_spend_today(
    delib_model_id: str,
    root=None,
) -> dict:
    """Return today's token + USD spend for the deliberation model.

    Reads only today's rows (days=1 via read_usage) so the result is truly
    today-scoped, not a 30-day aggregate.  Matches any model whose lower-case
    id starts with *delib_model_id* lower-case, or contains "fable".

    Returns {tokens: int, usd: float}.  Never raises — returns zeros on error.
    """
    try:
        import pathlib as _pl  # noqa: PLC0415
        _root = _pl.Path(root) if root is not None else _pl.Path(__file__).resolve().parent.parent
        from lib import ai_costs as _ac  # noqa: PLC0415
        rows = _ac.read_usage(root=_root, days=1)
        delib_lower = str(delib_model_id or "").lower()
        tokens = 0
        usd = 0.0
        for row in rows:
            mk = str(row.get("model") or "").lower()
            if "fable" in mk or (delib_lower and mk.startswith(delib_lower)):
                tokens += int(row.get("input_tokens") or 0) + int(row.get("output_tokens") or 0)
                usd += float(row.get("est_cost_usd") or 0.0)
        return {"tokens": tokens, "usd": round(usd, 6)}
    except Exception as exc:  # noqa: BLE001
        log.debug("deliberation_spend_today: failed (%s) → zeros", exc)
        return {"tokens": 0, "usd": 0.0}


def deliberation_model(default: str = "claude-opus-4-8") -> str:
    """Return the configured deliberation model if the daily token budget is not
    exhausted; fall back to *default* on any error or when Fable is disabled.

    Logic (all fail-soft — any error returns *default*):
      1. Read config.yml prophet.fable_enabled.  False → return default.
      2. Read config.yml llm_models.deliberation.  Absent → return default.
      3. Sum today's input+output tokens for the deliberation model prefix via
         deliberation_spend_today() (days=1 window — truly today-scoped).
      4. Compare against prophet.deliberation_daily_token_cap.
         Exhausted → return default.
      5. Return the deliberation model id.

    Callers keep their original model as the FALLBACK when the waterfall cannot
    serve the returned model (make_call handles 401/429; model-not-found must be
    detected by the caller on a text/reason basis — see standout_auditor,
    propose, adjudicate retry wrappers).
    """
    try:
        # --- read config ---
        import sys as _sys
        import pathlib as _pl
        _root = _pl.Path(__file__).resolve().parent.parent
        _root_str = str(_root)
        if _root_str not in _sys.path:
            _sys.path.insert(0, _root_str)

        from lib import config as _config  # noqa: PLC0415
        cfg = _config.load() if hasattr(_config, "load") else {}

        # Prefer lib.config; fall back to reading config.yml directly
        if not cfg:
            import yaml as _yaml  # noqa: PLC0415
            _cfg_path = _root / "config.yml"
            if _cfg_path.exists():
                cfg = _yaml.safe_load(_cfg_path.read_text(encoding="utf-8")) or {}

        prophet_cfg = cfg.get("prophet") or {}
        if not prophet_cfg.get("fable_enabled", False):
            log.debug("deliberation_model: fable_enabled=false → default")
            return default

        delib = (cfg.get("llm_models") or {}).get("deliberation") or ""
        if not delib:
            log.debug("deliberation_model: llm_models.deliberation absent → default")
            return default

        cap = int(prophet_cfg.get("deliberation_daily_token_cap") or 0)
        if cap <= 0:
            log.debug("deliberation_model: cap=0 → default")
            return default

        # --- check today's budget (days=1 window, not 30d aggregate) ---
        spend = deliberation_spend_today(delib, root=_root)
        today_tokens = spend["tokens"]

        if today_tokens >= cap:
            log.info(
                "deliberation_model: daily budget exhausted (%d >= %d tokens) → default",
                today_tokens, cap,
            )
            return default

        log.debug(
            "deliberation_model: returning %s (budget %d/%d used)",
            delib, today_tokens, cap,
        )
        return delib

    except Exception as exc:  # noqa: BLE001
        log.debug("deliberation_model: failed (%s) → default", exc)
        return default
