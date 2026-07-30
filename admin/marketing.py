"""admin/marketing.py — Marketing NW lobe admin page.

Panel payloads for GET /api/marketing/{overview,departments,channels,campaigns,
experiments,lobes,content,radar}.  All sources are fail-soft (try/except → None/[]).
Panels read only committed artifacts; they never write.

The single source of truth is data/neuralweb/marketing_state.json (marketing.state/v1).
Radar additionally reads data/marketing/radar_report.json + cashtag_tiers.json.
config/marketing.yml is read for the settings echo.

All public functions return {"ok": True, ...} or {"ok": False, "error": ...}.
If the state file is absent they return ok:True with empty/null sections and
an honest accruing note — so the page renders gracefully on day 0.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _is_stale(as_of: str | None) -> bool:
    """True when the plan's as_of is more than one day behind today (UTC).

    Fail-soft: an absent or unparseable as_of is treated as NOT stale (no false
    "stale" banner on a plan we simply can't date)."""
    if not as_of:
        return False
    try:
        d = datetime.strptime(str(as_of)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False
    return d < (datetime.now(timezone.utc).date() - timedelta(days=1))

_HERE = Path(__file__).resolve().parent


def _default_root() -> Path:
    """Repo root for panel reads when no explicit ``root=`` is passed.

    Resolves through admin.paths.ROOT so a seeded dev/demo run
    (MACRO_ADMIN_ROOT=<tmp> python -m admin) points every panel at the fixture
    tree without threading a root through the server. Fail-soft to the package
    grandparent if paths can't be imported.
    """
    try:
        from .paths import ROOT  # noqa: PLC0415
        return ROOT
    except Exception:  # noqa: BLE001
        return _HERE.parent


# Module-level default kept for back-compat; call sites use _default_root() so the
# MACRO_ADMIN_ROOT override is honoured even when this module was imported early.
_ROOT = _HERE.parent

_STATE_REL    = Path("data/neuralweb/marketing_state.json")
_GROWTH_EVENTS_REL = Path("data/marketing/growth_events.jsonl")
_CONTENT_REL  = Path("data/marketing/content_plan.json")
_INTELLIGENCE_REL = Path("data/marketing/press/intelligence.json")
_INTELLIGENCE_LIVE = Path("/var/lib/macro-live/public/live/intelligence.json")
_LAB_REL      = Path("data/marketing/lab_rollup.json")
_SENTINEL_REL = Path("data/marketing/sentinel_report.json")
_ALLIES_REL   = Path("data/marketing/allies_targets.jsonl")
_KITS_REL     = Path("data/marketing/allies_kits")
_CONFIG_REL   = Path("config/marketing.yml")

# Per-post metrics ledger (scripts/marketing_metrics_poll.py, append-only). One
# row per (remote_id, poll date); the LATEST row per remote_id is joined into
# the publisher's recent-posted table by external_id.
_POST_METRICS_REL = Path("data/marketing/post_metrics.jsonl")

# N-floor (docket D03 §Traps + small-N humility): a reach cell backed by fewer
# than this many posts is display-only — never allowed to crown a winner.
_LAB_N_FLOOR = 20

_RADAR_REL = Path("data/marketing/radar_report.json")
_TIERS_REL = Path("data/marketing/cashtag_tiers.json")

# Operator-written control files (this admin owns these two writes).
#  - sentinel_exceptions.jsonl: append-only "allow this held post at the next gate"
#  - account_overrides.json: per-account on/off + note the engine merges next run
_SENTINEL_EXC_REL   = Path("data/marketing/sentinel_exceptions.jsonl")
_ACCT_OVERRIDES_REL = Path("data/marketing/account_overrides.json")

# The three fixed publish slots (UTC, weekdays). Surfaced on the pipeline block +
# Publisher countdown so "next slot" is one honest source, not a magic string.
_PUBLISH_SLOTS_UTC = ("14:00", "17:30", "20:15")

# Beacon SEO control plane (data/marketing/seo/, built by a parallel engine lane).
_SEO_AUDIT_REL       = Path("data/marketing/seo/seo_audit.json")
_SEO_ORDERS_REL      = Path("data/marketing/seo/seo_work_orders.json")
_SEO_SCORECARD_REL   = Path("data/marketing/seo/seo_scorecard.json")
_SEO_HISTORY_REL     = Path("data/marketing/seo/seo_history.jsonl")

# GitHub Actions repo variable that arms/disarms the nightly SEO Director run.
_SEO_DIRECTOR_VAR = "SEO_DIRECTOR_ENABLED"

_SEO_ACCRUING_NOTE = (
    "No audit yet — the first crawl runs Sunday 15:00 UTC (seo-director.yml) "
    "or on demand via Run audit now. This page fills in once it lands."
)

_ACCRUING_NOTE = (
    "marketing_state.json not yet written — "
    "accruing after first nightly governor run."
)
_CONTENT_ACCRUING_NOTE = (
    "content_plan.json not yet written — "
    "accruing after first nightly governor run."
)
# Content Studio payload was ~363KB, most of it internal underscore-prefixed
# post keys the browser render never reads (the full Prophet ``_plan`` alone is
# ~80KB across the queue).  We strip underscore keys per post before shipping,
# keeping only the small flags the render surfaces as plain-word badges
# (``_live_gate_fail`` → "signal demoted", ``_copy_violations`` → caution chip).
_CONTENT_POST_KEEP = frozenset({"_live_gate_fail", "_copy_violations"})


def _strip_post_internals(post: dict) -> dict:
    """Drop internal underscore-prefixed keys from a queue post, keeping the
    small whitelist the Content Studio render reads.  Non-dict rows pass
    through untouched (fail-soft)."""
    if not isinstance(post, dict):
        return post
    return {
        k: v for k, v in post.items()
        if not k.startswith("_") or k in _CONTENT_POST_KEEP
    }
_LAB_WAITING_NOTE = (
    "No live posts yet — the Lab starts measuring once Broadcast goes live (W1). "
    "The hypotheses below are seeded and waiting for evidence."
)
_SENTINEL_ACCRUING_NOTE = (
    "sentinel_report.json not yet written — "
    "first nightly after D08 merge bakes it."
)
_ALLIES_ACCRUING_NOTE = (
    "allies_targets.jsonl not yet written — "
    "accruing after the allies engine scores its first candidates."
)

# MKT-D11: paper-only in W1 — no referral codes issued yet; the cut % is an
# operator decision governed by MNZ pricing (#2923/#2943), not an invented margin.
_ALLIES_REFERRAL_NOTE = (
    "Paper-only in W1 — no codes issued; cut % is an operator decision "
    "(MNZ #2923/#2943 pricing)."
)
# The gate that makes the whole page honest: nothing here reaches out.
_ALLIES_OPERATOR_GATE = (
    "Every transition past candidate is an operator-only action. "
    "This page records decisions; it never contacts anyone."
)
_RADAR_ACCRUING_NOTE = (
    "Radar hasn't produced its nightly report yet — "
    "this fills in after the first nightly run."
)


# ---------------------------------------------------------------------------
# IO helpers (all fail-soft)
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file into a list of dicts. Fail-soft: [] if absent/unreadable;
    one malformed line is skipped, not fatal."""
    try:
        if not path.exists():
            return []
        out: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(obj, dict):
                out.append(obj)
        return out
    except Exception:  # noqa: BLE001
        return []


def _read_yaml(path: Path) -> dict:
    try:
        import yaml  # noqa: PLC0415
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:  # noqa: BLE001
        return {}


def _state(root: Path) -> dict | None:
    return _read_json(root / _STATE_REL)


# ---------------------------------------------------------------------------
# Panel builders
# ---------------------------------------------------------------------------

def overview(root=None) -> dict:
    """CMO office view: lobe lifecycle, mandate, north-star, CMO portfolio,
    opportunity queue depth, self-improvement loop, guardrail checklist."""
    repo = Path(root) if root is not None else _default_root()
    try:
        # The pipeline block is the operator's "what's happening tonight" hero —
        # computed from whatever files exist, fail-soft to nulls. It is always
        # present (even on day 0) so the CMO Office can lead with it.
        pipeline = _pipeline_block(repo)
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "lobe": None,
                "north_star": None,
                "cmo": None,
                "authority_level": None,
                "mandate": None,
                "pipeline": pipeline,
            }
        return {
            "ok": True,
            "lobe": s.get("lobe"),
            "north_star": s.get("north_star"),
            "cmo": s.get("cmo"),
            "authority_level": (s.get("lobe") or {}).get("authority_level"),
            "mandate": (s.get("lobe") or {}).get("mandate"),
            "as_of": s.get("as_of"),
            "waves": s.get("waves"),
            "notes": s.get("notes"),
            "pipeline": pipeline,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.overview failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Pipeline-tonight block (CMO Office hero) — computed from existing files
# ---------------------------------------------------------------------------

def _next_publish_slot_utc(now=None) -> str | None:
    """Next weekday publish slot as an ISO-8601 UTC string.

    Walks the three fixed daily slots (14:00 / 17:30 / 20:15 UTC); if all of
    today's have passed (or it's the weekend) rolls to the next weekday's first
    slot. Returns None only if the datetime math fails (never raises).
    """
    try:
        from datetime import datetime, timedelta, timezone  # noqa: PLC0415
        now = now or datetime.now(timezone.utc)
        slots = []
        for hhmm in _PUBLISH_SLOTS_UTC:
            hh, mm = (int(x) for x in hhmm.split(":"))
            slots.append((hh, mm))
        # scan today then up to 7 following days for the first weekday slot > now
        for day_offset in range(0, 8):
            day = (now + timedelta(days=day_offset)).date()
            # Mon..Fri == 0..4
            if day.weekday() >= 5:
                continue
            for hh, mm in slots:
                cand = datetime(day.year, day.month, day.day, hh, mm, tzinfo=timezone.utc)
                if cand > now:
                    return cand.strftime("%Y-%m-%dT%H:%M:%SZ")
        return None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Publisher ARM state — the kill-switch is now a GitHub repo VARIABLE
# (MARKETING_PUBLISH_ENABLED: "1" = armed, "0"/absent = dark), the single source
# of truth the marketing-publish.yml workflow reads. The admin process env is
# NOT that source (it is never set on the operator's Mac), so the panel must read
# the API truth here and only fall back to the local env when the API is
# unreachable. Fail-soft: any error degrades to enabled:null with an honest note.
# ---------------------------------------------------------------------------

_ARM_VARIABLE = "MARKETING_PUBLISH_ENABLED"


def _env_kill_on() -> bool:
    """Local-env reading of the kill-switch (the OLD display source, kept only as
    a last-resort fallback when the GitHub API is unreachable)."""
    import os  # noqa: PLC0415
    return str(os.environ.get(_ARM_VARIABLE, "")).strip().lower() in {"1", "true", "yes"}


def arm_state() -> dict:
    """Read the publisher kill-switch from the GitHub repo VARIABLE (API truth).

    Returns a dict the panel renders directly:
      {enabled: bool|None, source: str, error: str|None, note: str}

    - enabled True  when the variable value is in {"1","true","yes"}
    - enabled False when the variable exists with any other value (e.g. "0")
    - enabled None  when the variable is not set yet (404) OR the API is
      unreachable (no token / requests missing / owner-repo undetected). The two
      are distinguished by `error`: None → "not set yet = dark"; a message →
      state genuinely unknown and we fell back to the local env read.

    source is "github_variable" on an API read, "local_env (fallback)" when the
    API is unreachable and we report the process-env reading instead. Never
    raises; never contains any secret.
    """
    try:
        from . import github_api  # noqa: PLC0415
        avail = github_api.available()
        # API reachable only when the lib + owner/repo + a token are all present.
        if not (avail.get("ok") and avail.get("has_token")):
            # Cannot read the variable — fall back to the local env reading, but
            # label the state as unknown-from-API so the UI is honest.
            return {
                "enabled": _env_kill_on() or None,
                "source": "local_env (fallback)",
                "error": "GitHub API unavailable (no token/lib) — arm state unknown; "
                         "the runner follows the repo variable regardless.",
                "note": "state unknown — showing local env reading only",
            }
        val = github_api.get_repo_variable(_ARM_VARIABLE)
        if val is None:
            # 404 (variable never created) OR a transient non-200. get_repo_variable
            # collapses both to None; treat as dark with an honest note. This is
            # the common first-run state.
            return {
                "enabled": None,
                "source": "github_variable",
                "error": None,
                "note": "variable not set yet = dark",
            }
        enabled = str(val).strip().lower() in {"1", "true", "yes"}
        return {
            "enabled": enabled,
            "source": "github_variable",
            "error": None,
            "note": "armed — posting at the next slot" if enabled
                    else "disarmed — dry-run only",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "enabled": None,
            "source": "local_env (fallback)",
            "error": f"arm-state read failed: {exc}",
            "note": "state unknown",
        }


def arm_publisher(enabled) -> dict:
    """Arm/disarm the live publisher by writing the MARKETING_PUBLISH_ENABLED repo
    VARIABLE ("1" armed / "0" dark). Mirrors the SEO-director toggle plumbing.

    Fail-soft: returns {ok, enabled, note} on success; {ok:False, error, note} with
    an honest message when the GitHub token/API is unavailable or the write fails.
    Never raises. The workflow env resolves this variable at run start, so the
    change takes effect from the NEXT scheduled slot.
    """
    try:
        en = bool(enabled)
        from . import github_api  # noqa: PLC0415
        if not github_api.token():
            return {
                "ok": False,
                "enabled": None,
                "error": "No GitHub token configured. Set GH_TOKEN in "
                         "/etc/macro-admin.env (needs Variables read/write) to arm "
                         "or disarm the publisher — or edit the "
                         "MARKETING_PUBLISH_ENABLED repo variable by hand.",
                "note": "GitHub token required",
            }
        new_value = "1" if en else "0"
        ok = github_api.set_repo_variable(_ARM_VARIABLE, new_value)
        if not ok:
            err = getattr(github_api, "_last_set_variable_error", None) or (
                "Failed to update MARKETING_PUBLISH_ENABLED — check that GH_TOKEN "
                "has Variables write permission.")
            return {"ok": False, "enabled": None, "error": err,
                    "note": "variable write failed"}
        out = {
            "ok": True,
            "enabled": en,
            "variable_value": new_value,
            "note": "Publisher ARMED — approved, due items post at the next slot."
                    if en else
                    "Publisher DISARMED — every path reverts to dry-run.",
        }
        if not en:
            # DISARM MEANS STOP. Writing the variable only prevents NEW sends;
            # publish.max_forward_book_min hands posts to Buffer up to an hour
            # ahead, and those fire on Buffer's schedule no matter what this
            # variable says. On 2026-07-28 the operator disarmed 61 seconds
            # after a sweep booked five posts and all five still went out —
            # three of them already known-defective — recoverable only by hand
            # in the Buffer UI. So the toggle now also dispatches the recall.
            #
            # FAIL-SOFT AND SUBORDINATE: the disarm itself already succeeded, so
            # a failed recall dispatch must not report the disarm as failed. It
            # degrades to ok:True with an honest `recall` block telling the
            # operator to run it by hand — never a silent swallow.
            out["recall"] = recall_pending()
            if out["recall"].get("ok"):
                out["note"] = ("Publisher DISARMED — every path reverts to dry-run, "
                               "and a recall run was dispatched to cancel posts "
                               "already booked at Buffer but not yet sent.")
            else:
                out["note"] = ("Publisher DISARMED — every path reverts to dry-run. "
                               "WARNING: the recall of already-booked posts could not "
                               "be dispatched (" + str(out["recall"].get("error") or
                                                       "unknown error") +
                               "). Posts already handed to Buffer WILL still send — "
                               "delete them in the Buffer queue or run "
                               "`python -m scripts.marketing_recall --recall-pending "
                               "--live`.")
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.arm_publisher failed: %s", exc)
        return {"ok": False, "enabled": None, "error": str(exc),
                "note": "arm write failed"}


_PUBLISH_WORKFLOW = "marketing-publish.yml"
# Outbox ids are machine-generated slugs (ob-2026-07-25-15098c35f1, or a fastlane
# TICKER-quarter-source triple). Anything outside this alphabet is not an id we
# produced. The leading-dash rejection matters on its own: the runner passes the
# value to argparse, where "-x" would be read as a FLAG, not an id.
_ITEM_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_MAX_POST_NOW_IDS = 5


def post_now(item_id) -> dict:
    """BREAKING DISPATCH — send one (or a few) outbox items right now.

    Dispatches marketing-publish.yml with the `post_now_item` input, which makes
    that run: restrict itself to these ids, approve them regardless of the
    auto-approve config, skip the humanizing jitter, and hand Buffer a concrete
    share-now dueAt instead of parking them in Buffer's queue. Every SAFETY gate
    still runs in the runner — copy validation, the live tape gate, the channel
    check, the daily cap, and the 10-minute global floor (a breaking item that
    lands inside the floor is booked at last_post + 10m rather than dropped).

    Fail-soft: returns {ok: False, error, note} with an actionable message and
    never raises. Requires a GH token with Actions: write.
    """
    try:
        raw = str(item_id or "").strip()
        ids = [p.strip() for p in raw.split(",") if p.strip()]
        if not ids:
            return {"ok": False, "error": "no item id given", "note": "nothing to post"}
        if len(ids) > _MAX_POST_NOW_IDS:
            return {"ok": False,
                    "error": f"too many ids ({len(ids)}) — post now takes at most "
                             f"{_MAX_POST_NOW_IDS} at a time",
                    "note": "breaking dispatch is for one or two posts, not a batch"}
        bad = [i for i in ids if not _ITEM_ID_RE.match(i) or len(i) > 120]
        if bad:
            return {"ok": False, "error": f"not a valid outbox item id: {bad[0]!r}",
                    "note": "id rejected"}

        from . import github_api  # noqa: PLC0415
        if not github_api.token():
            return {
                "ok": False,
                "error": "No GitHub token configured. Set GH_TOKEN in "
                         "/etc/macro-admin.env (needs Actions: read & write) to "
                         "dispatch a breaking post.",
                "note": "GitHub token required",
            }

        # An unarmed publisher would run this dispatch as a dry-run and post
        # nothing. Say so up front rather than letting the operator watch a run
        # go green having sent nothing.
        arm = arm_state()
        if arm.get("enabled") is False:
            return {"ok": False,
                    "error": "The publisher is DISARMED — a dispatch now would "
                             "dry-run and post nothing. Arm it in the Publisher "
                             "panel first.",
                    "note": "kill-switch off"}

        res = github_api.dispatch(workflow=_PUBLISH_WORKFLOW, ref="main",
                                  inputs={"post_now_item": ",".join(ids)})
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error") or "dispatch failed",
                    "note": "could not start the publisher run"}
        return {
            "ok": True,
            "item_ids": ids,
            "dispatched": True,
            "note": ("Breaking run dispatched. The item posts within a couple of "
                     "minutes unless a safety gate holds it — check the run in "
                     "Actions. A post that went out in the last 10 minutes pushes "
                     "this one to that mark."),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.post_now failed: %s", exc)
        return {"ok": False, "error": str(exc), "note": "post-now dispatch failed"}


def recall_pending() -> dict:
    """KILL-SWITCH RECALL — cancel every post booked at Buffer but not yet sent.

    Dispatches marketing-publish.yml with `recall_pending`, which runs
    scripts.marketing_recall instead of the publisher. That runner cancels only
    bookings whose send time is still in the FUTURE and only moves an item out
    of `posted` on a confirmed backend delete, so a post that already went out
    is never touched and never resurrected.

    Deliberately NOT gated on arm_state(): unlike post_now(), which correctly
    refuses to dispatch a send while the publisher is disarmed, this is the
    action an operator takes BECAUSE they just disarmed. Requiring the switch to
    be on would make it unusable in its only real scenario. arm_publisher(False)
    calls this automatically; it is also exposed on its own so a recall can be
    re-run after a failed dispatch without toggling the switch again.

    Fail-soft: returns {ok: False, error, note} with an actionable message and
    never raises. Requires a GH token with Actions: write.
    """
    try:
        from . import github_api  # noqa: PLC0415
        if not github_api.token():
            return {
                "ok": False,
                "error": "No GitHub token configured. Set GH_TOKEN in "
                         "/etc/macro-admin.env (needs Actions: read & write) to "
                         "dispatch a recall.",
                "note": "GitHub token required",
            }
        # "true" as a STRING, not a JSON boolean: that is what the Actions UI
        # sends for a `type: boolean` input and what the dispatch API accepts
        # across both its typed and untyped input handling. A raw boolean can be
        # rejected 422 depending on the endpoint's mood; the string never is,
        # and the workflow expression reads it as truthy either way.
        res = github_api.dispatch(workflow=_PUBLISH_WORKFLOW, ref="main",
                                  inputs={"recall_pending": "true"})
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error") or "dispatch failed",
                    "note": "could not start the recall run"}
        return {
            "ok": True,
            "dispatched": True,
            "note": ("Recall dispatched. Posts already booked at Buffer that have "
                     "not sent yet are cancelled within a couple of minutes — check "
                     "the run in Actions. Anything already sent stays sent; the run "
                     "goes RED if a cancel failed, which means those posts are still "
                     "scheduled and need deleting in the Buffer queue."),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.recall_pending failed: %s", exc)
        return {"ok": False, "error": str(exc), "note": "recall dispatch failed"}


# Cap on the accepted Buffer token length. A Buffer personal token is short
# (~40 chars); this is a sanity bound against a paste of the wrong thing, not a
# format check. The value is treated as radioactive: stdin-only, never argv,
# never logged, never echoed back.
_MAX_TOKEN_LEN = 500


def set_buffer_token(token) -> dict:
    """Set the BUFFER_TOKEN repo SECRET by shelling to `gh secret set BUFFER_TOKEN`,
    passing the token on STDIN (never argv, never logged, never returned).

    `gh` is authenticated on the operator's local Mac; this is a local-only path
    (the deployed VPS has no `gh` login), so it REFUSES in deployed mode with an
    honest fallback instruction. Returns {ok, note} ONLY — the token value never
    appears in the response. Refuses empty/whitespace tokens.

    Fail-soft: a missing/unauthenticated `gh` returns ok:False with the manual
    GitHub-UI fallback. Never raises. Never persists the token anywhere except
    the `gh secret set` call's stdin.
    """
    try:
        # radioactive: strip + cap, then discard the local name ASAP.
        tok = str(token or "").strip()
        if not tok:
            return {"ok": False, "error": "token is empty — paste the Buffer "
                                          "personal API token, then Save."}
        if len(tok) > _MAX_TOKEN_LEN:
            return {"ok": False, "error": f"token too long (> {_MAX_TOKEN_LEN} "
                                          "chars) — check you pasted only the token."}

        from . import settings  # noqa: PLC0415
        if settings.deployed():
            return {
                "ok": False,
                "error": "Setting the Buffer token from the panel is disabled in "
                         "deployed mode (it shells out to a locally-authenticated "
                         "`gh`). Set it at GitHub → Settings → Secrets and "
                         "variables → Actions → BUFFER_TOKEN.",
            }

        import subprocess  # noqa: PLC0415
        from .paths import ROOT  # noqa: PLC0415
        try:
            proc = subprocess.run(
                ["gh", "secret", "set", "BUFFER_TOKEN"],
                input=tok,               # STDIN — never argv, never logged
                capture_output=True, text=True, timeout=30, cwd=str(ROOT),
            )
        except FileNotFoundError:
            return {
                "ok": False,
                "error": "`gh` (GitHub CLI) is not installed on the admin host. "
                         "Install it and run `gh auth login`, or set BUFFER_TOKEN "
                         "at GitHub → Settings → Secrets and variables → Actions.",
            }
        except Exception as sexc:  # noqa: BLE001
            # Do NOT include the token or the subprocess input in any message.
            return {"ok": False, "error": f"`gh secret set` failed to run: {sexc}"}
        finally:
            # Best-effort scrub of the local reference (Python strings are
            # immutable, so this only drops the name — the real guarantee is that
            # `tok` never leaves this function except via `gh`'s stdin).
            tok = ""

        if proc.returncode != 0:
            # gh writes auth/permission errors to stderr; surface a trimmed,
            # token-free tail so the operator can act (gh never echoes the value).
            stderr = (proc.stderr or "").strip()[-300:]
            return {
                "ok": False,
                "error": "Could not set the secret via `gh` "
                         + (f"({stderr}). " if stderr else ". ")
                         + "Check `gh auth status`, or set BUFFER_TOKEN at "
                           "GitHub → Settings → Secrets and variables → Actions.",
            }

        out = {"ok": True, "note": "Token saved to repo secrets (BUFFER_TOKEN)."}
        # Truthful present-check, best-effort: a `gh secret list` grep. Never
        # fails the request on its own (fail-soft) and never reads the value.
        try:
            lst = subprocess.run(
                ["gh", "secret", "list"],
                capture_output=True, text=True, timeout=15, cwd=str(ROOT),
            )
            if lst.returncode == 0:
                out["token_present"] = "BUFFER_TOKEN" in (lst.stdout or "")
        except Exception:  # noqa: BLE001
            pass
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.set_buffer_token failed: %s", exc)
        return {"ok": False, "error": "token save failed (unexpected error)"}


def _pipeline_block(repo: Path) -> dict:
    """Five-stage pipeline snapshot for the CMO Office hero: Plan → Gate →
    Outbox → Publisher → Posted. Every field is fail-soft: a missing file
    degrades its stage to null + an honest note, never raises.
    """
    out: dict[str, Any] = {
        "plan": None, "gate": None, "outbox": None,
        "publisher": None, "receipts": None,
    }

    # --- Plan (content_plan.json) ---
    try:
        cp = _read_json(repo / _CONTENT_REL)
        if cp is None:
            out["plan"] = {"present": False, "as_of": None, "produced_at": None,
                           "items": None, "stale": None}
        else:
            n_items = 0
            for acct in (cp.get("accounts") or []):
                if isinstance(acct, dict) and isinstance(acct.get("queue"), list):
                    n_items += len(acct["queue"])
            out["plan"] = {
                "present": True,
                "as_of": cp.get("as_of"),
                "produced_at": cp.get("produced_at"),
                "items": (cp.get("summary") or {}).get("total_posts", n_items),
                # Prefer the engine's own freshness flag when the sibling adds it;
                # otherwise fall back to a date compare against today (UTC).
                "stale": _plan_is_stale(cp),
            }
    except Exception:  # noqa: BLE001
        out["plan"] = {"present": False, "as_of": None, "produced_at": None,
                       "items": None, "stale": None}

    # --- Gate + Outbox + Receipts, computed from sentinel + outbox fold ---
    try:
        rpt = _read_json(repo / _SENTINEL_REL)
        if rpt is None:
            out["gate"] = {"present": False, "passed": None,
                           "held_policy": None, "trimmed": None}
        else:
            counts = rpt.get("counts") or {}
            q = rpt.get("quarantined") or []
            policy_q = [x for x in q if x.get("class") != "overflow"]
            over_q = [x for x in q if x.get("class") == "overflow"]
            out["gate"] = {
                "present": True,
                "passed": counts.get("passed", (counts.get("items") or 0)
                          - len(policy_q) - len(over_q) if counts else None),
                "held_policy": counts.get("quarantined_policy", len(policy_q)),
                "trimmed": counts.get("quarantined_overflow", len(over_q)),
            }
    except Exception:  # noqa: BLE001
        out["gate"] = {"present": False, "passed": None,
                       "held_policy": None, "trimmed": None}

    try:
        ob = outbox(repo)
        if ob.get("note") and not (ob.get("accounts") or []):
            # outbox dir has never existed → honest "first fill" stage
            out["outbox"] = {"present": False, "queued": None, "approved": None,
                             "posted_today": None}
            out["receipts"] = {"present": False, "total_posted": None}
        else:
            summ = ob.get("summary") or {}
            # posted "today": count posted history rows dated as of the max plan day;
            # simplest honest proxy = total posted in the summary.
            out["outbox"] = {
                "present": True,
                "queued": summ.get("queued", 0),
                "approved": summ.get("approved", 0),
                "posted_today": summ.get("posted", 0),
            }
            out["receipts"] = {"present": True,
                               "total_posted": summ.get("posted", 0)}
    except Exception:  # noqa: BLE001
        out["outbox"] = {"present": False, "queued": None, "approved": None,
                         "posted_today": None}
        out["receipts"] = {"present": False, "total_posted": None}

    # --- Publisher (armed? next slot? kill switch?) ---
    try:
        import os  # noqa: PLC0415
        cfg = _read_yaml(repo / _CONFIG_REL)
        pub_cfg = (cfg.get("publish") or {}) if isinstance(cfg, dict) else {}
        channels_cfg = pub_cfg.get("channels") or {}
        any_channel = any(str(cid or "").strip() for cid in channels_cfg.values())
        token_present = bool(os.environ.get("BUFFER_TOKEN", "").strip())
        # Kill-switch = the GitHub repo VARIABLE (API truth), NOT the admin process
        # env (which is never set on the operator's Mac). arm_state() falls back to
        # the local env read only when the API is unreachable. `armed` requires the
        # kill-switch ON — treat unknown (None) as NOT armed for this glance.
        armv = arm_state()
        kill = armv.get("enabled") is True
        out["publisher"] = {
            "present": True,
            "armed": bool(token_present and any_channel and kill),
            "token_present": token_present,
            "any_channel_set": any_channel,
            "kill_switch": kill,
            "arm_state": armv,
            "next_slot_utc": _next_publish_slot_utc(),
            "slots_utc": list(_PUBLISH_SLOTS_UTC),
        }
    except Exception:  # noqa: BLE001
        out["publisher"] = {"present": False, "armed": False, "next_slot_utc": None,
                            "kill_switch": None, "slots_utc": list(_PUBLISH_SLOTS_UTC)}

    return out


def _plan_is_stale(cp: dict) -> bool | None:
    """Is the content plan stale? Prefers the engine's own ``stale`` flag (added
    by the sibling correctness PR); otherwise compares as_of to today (UTC).
    Returns None when neither signal is available."""
    if not isinstance(cp, dict):
        return None
    if isinstance(cp.get("stale"), bool):
        return cp["stale"]
    as_of = cp.get("as_of")
    if not as_of:
        return None
    try:
        from datetime import date, datetime, timezone  # noqa: PLC0415
        d = datetime.strptime(str(as_of)[:10], "%Y-%m-%d").date()
        today = datetime.now(timezone.utc).date()
        return d < today
    except Exception:  # noqa: BLE001
        return None


def departments(root=None) -> dict:
    """Department portfolio: one record per department + authority ladder."""
    repo = Path(root) if root is not None else _default_root()
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "departments": [],
                "authority_ladder": [],
            }
        return {
            "ok": True,
            "departments": s.get("departments") or [],
            "authority_ladder": s.get("authority_ladder") or [],
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.departments failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def channels(root=None) -> dict:
    """Desk network: accounts, distinctness, actuation path; publication ledger;
    corrections count."""
    repo = Path(root) if root is not None else _default_root()
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "desk_network": None,
                "publications": None,
                "corrections": None,
            }
        pipeline = s.get("pipeline") or {}
        # Publisher channel-id presence per account (drives the "channel wired ✓"
        # pill) + the operator override file so the On/Off toggle reflects reality.
        cfg = _read_yaml(repo / _CONFIG_REL)
        pub_cfg = (cfg.get("publish") or {}) if isinstance(cfg, dict) else {}
        channels_cfg = pub_cfg.get("channels") or {}
        channel_set = {str(a): bool(str(cid or "").strip())
                       for a, cid in channels_cfg.items()}
        overrides = _read_json(repo / _ACCT_OVERRIDES_REL) or {}
        return {
            "ok": True,
            "desk_network": s.get("desk_network"),
            "publications": pipeline.get("publications"),
            "corrections": (pipeline.get("publications") or {}).get("corrections"),
            "channels_set": channel_set,
            "overrides": overrides if isinstance(overrides, dict) else {},
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.channels failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def campaigns(root=None) -> dict:
    """Opportunity bus + campaigns table + pipeline summary."""
    repo = Path(root) if root is not None else _default_root()
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "opportunities": None,
                "campaigns": None,
                "pipeline": None,
            }
        pipeline = s.get("pipeline") or {}
        return {
            "ok": True,
            "opportunities": pipeline.get("opportunities"),
            "campaigns": pipeline.get("campaigns"),
            "pipeline": pipeline,
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.campaigns failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def experiments(root=None) -> dict:
    """Experiment registry + trial-variant selector + north-star window."""
    repo = Path(root) if root is not None else _default_root()
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "experiments": None,
                "trial_variants": ["7_trading_days", "14_calendar_days", "value_moment_limited"],
                "north_star": None,
            }
        pipeline = s.get("pipeline") or {}
        cfg = _read_yaml(repo / _CONFIG_REL)
        active_variant = (cfg.get("settings") or {}).get("trial_variant", "7_trading_days")
        return {
            "ok": True,
            "experiments": pipeline.get("experiments"),
            "trial_variants": ["7_trading_days", "14_calendar_days", "value_moment_limited"],
            "active_trial_variant": active_variant,
            "north_star": s.get("north_star"),
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.experiments failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Ad Central — creative fan-out, split tests, budget allocation.
# research/AD_CENTRAL_MASTERPLAN.md; engine/marketing/ad_central.py
# ─────────────────────────────────────────────────────────────────────────────

# The operator arm of the G-A triple gate. Phase 1 ships with no UI action that
# can set it — arming is Phase 5, behind an operator ruling. The env var exists so
# the gate is exercisable end-to-end; it alone still cannot authorise a cent,
# because settings.paid_enabled and a non-zero envelope are independent arms.
_ADS_ARMED_ENV = "MARKETING_ADS_ARMED"


def ad_central(root=None) -> dict:
    """Ad Central: the spend gate, every split test, and today's budget plan.

    Reads the arena ledgers under data/marketing/ad_central/ and returns the
    payload `engine.marketing.ad_central.state` builds. Degrades to an honest
    empty state — an arena with no data reads as "still gathering", never as a
    broken panel.
    """
    repo = Path(root) if root is not None else _default_root()
    try:
        import os  # noqa: PLC0415
        from engine.marketing import ad_central as _ac  # noqa: PLC0415
        armed = str(os.environ.get(_ADS_ARMED_ENV, "")).strip().lower() in {"1", "true", "yes"}
        payload = _ac.state(repo, cfg=_read_yaml(repo / _CONFIG_REL), operator_armed=armed)
        payload["as_of"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return payload
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.ad_central failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def lobes(root=None) -> dict:
    """Engines-by-department; provenance modes + claims summary; growth-event spine."""
    repo = Path(root) if root is not None else _default_root()
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "engines_by_department": [],
                "provenance": None,
                "growth_events": None,
            }
        # Build engines-by-department index from department records
        depts = s.get("departments") or []
        engines_by_dept = [
            {
                "department_id":   d.get("id"),
                "department_name": d.get("name"),
                "engines":         d.get("engines") or [],
                "lifecycle_state": d.get("lifecycle_state"),
                "authority_level": d.get("authority_level"),
            }
            for d in depts
        ]
        pipeline = s.get("pipeline") or {}
        growth_events = pipeline.get("growth_events")
        # BUG-FIX: the state file's baked-in `observed` count includes shadow
        # seed rows (event_id "seed-…", mode "shadow"), overstating real
        # observations. Recompute from the raw spine so a seeded-but-live-empty
        # page reads honestly, and surface the seed count separately.
        if isinstance(growth_events, dict):
            rows = _read_jsonl(repo / _GROWTH_EVENTS_REL)
            observed = len([
                r for r in rows
                if r.get("mode") != "shadow"
                and not str(r.get("event_id", "")).startswith("seed-")
            ])
            seeded = len(rows) - observed
            growth_events = {
                **growth_events,
                "observed": observed,
                "seeded": seeded,
                "seed_note": (
                    "Seeded, awaiting real events." if observed == 0 and seeded > 0
                    else None
                ),
            }
        return {
            "ok": True,
            "engines_by_department": engines_by_dept,
            "provenance": s.get("provenance"),
            "growth_events": growth_events,
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.lobes failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _intelligence_snapshot(repo: Path, *, allow_live: bool) -> dict | None:
    """The RAW Intelligence Desk snapshot, read from the canonical path list.

    ONE reader for two callers. ``content()`` renders it; ``intelligence_approve``
    re-reads it server-side so an approval is always against the desk's own copy
    of the draft and never against text the browser sent back. Both must resolve
    the same file or the review gate is reviewing something else.

    On the VPS the desk lives in the external live plane; tests and dev runs use
    the gitignored repo fallback. ``allow_live`` is False whenever the caller
    pinned an explicit ``root=`` — a seeded fixture tree must never silently read
    the host's live snapshot. Fail-soft: None when nothing on the list parses as
    the desk schema.
    """
    paths: list[Path] = []
    if allow_live:
        paths.append(_INTELLIGENCE_LIVE)
    paths.append(repo / _INTELLIGENCE_REL)
    for path in paths:
        candidate = _read_json(path)
        if (
            isinstance(candidate, dict)
            and candidate.get("schema") == "intelligence.desk/v1"
        ):
            return candidate
    return None


def content(root=None) -> dict:
    """Content Studio panel: reads data/marketing/content_plan.json.

    Returns {ok, content_types, accounts, featured_charts, distinctness, summary}.
    Fail-soft with honest note when the file is absent (accruing state).
    """
    repo = Path(root) if root is not None else _default_root()
    try:
        # The intraday Intelligence Desk is independent of the nightly content
        # plan. Only the already-public story contract is exposed, capped again
        # for the operator console.
        intelligence = None
        _candidate = _intelligence_snapshot(repo, allow_live=(root is None))
        if _candidate is not None:
            intelligence = {
                "schema": _candidate.get("schema"),
                "updated_at": _candidate.get("updated_at"),
                "health": _candidate.get("health") or {},
                "stories": [
                    row for row in (_candidate.get("stories") or [])[:24]
                    if isinstance(row, dict)
                ],
            }
        cp = _read_json(repo / _CONTENT_REL)
        if cp is None:
            return {
                "ok": True,
                "note": _CONTENT_ACCRUING_NOTE,
                "content_types": [],
                "accounts": [],
                "featured_charts": [],
                "distinctness": None,
                "summary": None,
                "intelligence": intelligence,
            }
        plan_as_of = cp.get("as_of")

        # slot_datetime resolves a plan slot to its real advisory post time (the
        # D2..D7 slots used to all read day-1). Fail-soft: if the helper can't be
        # imported, posts simply carry no display_time.
        try:
            from engine.marketing.outbox import slot_datetime as _slot_dt
        except Exception:  # noqa: BLE001
            _slot_dt = None

        # Usage fold (staleness fix, 2026-07-27): join each plan post to its
        # outbox item so a post that was actually USED shows its real status
        # instead of a forever-"drafted" badge. Two maps off fold_state:
        #   plan_post_id → (usage, at)   — exact, via source.plan_post_id (new emits)
        #   (account, normalized text) → (usage, at)  — fallback for historical
        #     items emitted before source.plan_post_id was stamped.
        # Folded outbox status → a plain usage word: posted/posting → "posted",
        # approved → "approved", queued → "queued", quarantined → "quarantined".
        # Any exception → serve the plan with no usage fields (never break panel).
        _usage_by_plan_id: dict[str, tuple[str, str | None]] = {}
        _usage_by_text: dict[tuple[str, str], tuple[str, str | None]] = {}
        try:
            from engine.marketing.outbox import (  # noqa: PLC0415
                fold_state as _fold_state, _normalize_text as _norm,
            )

            def _usage_word(status: str) -> str | None:
                if status in ("posted", "posting"):
                    return "posted"
                if status == "approved":
                    return "approved"
                if status == "queued":
                    return "queued"
                if status == "quarantined":
                    return "quarantined"
                if status == "recalled":
                    # Booked, then cancelled before it sent. NOT "posted" — it
                    # reached nobody — and not "drafted" either, which would hide
                    # that the copy got as far as the backend queue.
                    return "recalled"
                return None  # failed / unknown → treat as never-usefully-emitted

            _st = _fold_state(repo)
            _items = _st.get("items") or {}
            _statuses = _st.get("status") or {}
            _last = _st.get("last") or {}
            for _iid, _it in _items.items():
                if not isinstance(_it, dict):
                    continue
                _word = _usage_word(_statuses.get(_iid, "queued"))
                if _word is None:
                    continue
                _at = str((_last.get(_iid) or {}).get("at") or "") or None
                _src = _it.get("source") if isinstance(_it.get("source"), dict) else {}
                _ppid = _src.get("plan_post_id") if isinstance(_src, dict) else None
                if _ppid is not None:
                    _usage_by_plan_id[str(_ppid)] = (_word, _at)
                _tkey = (str(_it.get("account") or ""), _norm(str(_it.get("text") or "")))
                _usage_by_text[_tkey] = (_word, _at)
        except Exception as _fold_exc:  # noqa: BLE001 — usage is best-effort
            log.warning("marketing.content: usage fold skipped (%s)", _fold_exc)
            _usage_by_plan_id = {}
            _usage_by_text = {}

        def _fold_usage(p: dict, acct_id: str) -> dict:
            """Stamp usage/usage_at onto a plan post dict (best-effort)."""
            try:
                from engine.marketing.outbox import _normalize_text as _norm2  # noqa: PLC0415
            except Exception:  # noqa: BLE001
                return p
            hit = None
            _pid = p.get("id")
            if _pid is not None:
                hit = _usage_by_plan_id.get(str(_pid))
            if hit is None:
                parts = [str(p.get("headline") or "").strip(),
                         str(p.get("body") or "").strip()]
                _text = "\n\n".join(x for x in parts if x)
                hit = _usage_by_text.get((str(acct_id or ""), _norm2(_text)))
            if hit is None:
                return p
            usage, usage_at = hit
            out = {**p, "usage": usage}
            if usage_at:
                out["usage_at"] = usage_at
            return out

        def _stamp(post: dict, acct_id: str = "") -> dict:
            p = _strip_post_internals(post)
            if _slot_dt is not None and isinstance(p, dict):
                p = {**p, "display_time": _slot_dt(plan_as_of or "", str(p.get("slot") or ""))}
            if isinstance(p, dict):
                p = _fold_usage(p, acct_id)
            return p

        # Strip internal underscore-prefixed keys from every queued post before
        # shipping to the browser — the render reads none of the big ones (the
        # full Prophet ``_plan`` was ~80KB across the queue).  Small whitelisted
        # flags survive (see _CONTENT_POST_KEEP).  Each post also gets a
        # display_time (its real advisory post datetime) for the UI.
        accounts = []
        _posted_7d = 0
        for acct in (cp.get("accounts") or []):
            if isinstance(acct, dict) and isinstance(acct.get("queue"), list):
                _acct_id = str(acct.get("id") or acct.get("name") or "")
                _q = [_stamp(p, _acct_id) for p in acct["queue"]]
                _posted_7d += sum(
                    1 for p in _q if isinstance(p, dict) and p.get("usage") == "posted")
                acct = {**acct, "queue": _q}
            accounts.append(acct)

        return {
            "ok": True,
            "content_types": cp.get("content_types") or [],
            "accounts": accounts,
            "featured_charts": cp.get("featured_charts") or [],
            "distinctness": cp.get("distinctness"),
            "summary": cp.get("summary"),
            # Intraday event → evidence → draft queue. Separate from the nightly
            # plan and from the publisher; every draft remains review-gated.
            "intelligence": intelligence,
            # Count of plan posts that were actually posted in the last 7 days —
            # feeds the "posted (7d)" summary tile so an operator can see at a
            # glance that content is being used, not stale.
            "posted_7d": _posted_7d,
            "as_of": plan_as_of,
            "produced_at": cp.get("produced_at"),
            # A plan is stale once its as_of falls more than a day behind today —
            # the UI banners this so an operator never mistakes a stalled nightly
            # plan for fresh content.
            "stale": _is_stale(plan_as_of),
            "source": cp.get("source"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.content failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def lab(root=None) -> dict:
    """Growth Science Lab panel: reads data/marketing/lab_rollup.json.

    The Lab grades the zero-follower playbook hypotheses against real reach
    data.  Until Broadcast (W1) posts live, the file is absent or n_posts=0 —
    that is a first-class *waiting* state, not an error: we still surface the
    seeded hypotheses so the operator sees what will be measured.

    Returns {ok, waiting, note, as_of, n_posts, n_rows, n_orphans,
             hypotheses, cells, top_posts, n_floor}.

    N-floor enforcement (docket §Traps): every reach cell is tagged
    ``below_floor`` when its post count is under _LAB_N_FLOOR, so the page can
    never visually crown a winner under the floor.  We tag rather than drop —
    small-sample cells stay visible, greyed and labelled.
    """
    repo = Path(root) if root is not None else _default_root()
    try:
        rollup = _read_json(repo / _LAB_REL)

        # Absent file OR zero posts → honest waiting state.  Seeded hypotheses
        # are read from the rollup when present so the operator sees the bench.
        if rollup is None or int(rollup.get("n_posts") or 0) <= 0:
            hyps = _lab_hypotheses((rollup or {}).get("hypotheses") or [])
            return {
                "ok": True,
                "waiting": True,
                "note": _LAB_WAITING_NOTE,
                "as_of": (rollup or {}).get("as_of"),
                "n_posts": int((rollup or {}).get("n_posts") or 0),
                "n_rows": int((rollup or {}).get("n_rows") or 0),
                "n_orphans": int((rollup or {}).get("n_orphans") or 0),
                "n_unmeasured": int((rollup or {}).get("n_unmeasured") or 0),
                "hypotheses": hyps,
                "cells": [],
                "top_posts": [],
                "n_floor": _LAB_N_FLOOR,
            }

        cells = _lab_cells(rollup.get("cells") or [])
        return {
            "ok": True,
            "waiting": False,
            "as_of": rollup.get("as_of"),
            "n_posts": int(rollup.get("n_posts") or 0),
            "n_rows": int(rollup.get("n_rows") or 0),
            "n_orphans": int(rollup.get("n_orphans") or 0),
            "n_unmeasured": int(rollup.get("n_unmeasured") or 0),
            "hypotheses": _lab_hypotheses(rollup.get("hypotheses") or []),
            "cells": cells,
            "top_posts": rollup.get("top_posts") or [],
            "n_floor": _LAB_N_FLOOR,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.lab failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _lab_hypotheses(raw: list) -> list:
    """Normalise hypothesis records, defaulting an unknown state to the cautious
    ``seeding`` bucket (never a fake ``confirmed``)."""
    out = []
    for hyp_item in raw or []:
        state = (hyp_item.get("state") or "seeding").lower()
        if state not in ("seeding", "confirmed", "refuted"):
            state = "seeding"
        out.append({
            "id": hyp_item.get("id"),
            "title": hyp_item.get("title") or hyp_item.get("id") or "Hypothesis",
            "state": state,
            "n_evidence": int(hyp_item.get("n_evidence") or 0),
            "note": hyp_item.get("note") or "",
        })
    return out


def _lab_cells(raw: list) -> list:
    """Tag each reach cell with ``below_floor`` (n < _LAB_N_FLOOR).  Cells stay
    in the list either way — the floor suppresses the *verdict*, not the row."""
    out = []
    for cell in raw or []:
        n = int(cell.get("n") or 0)
        dims = cell.get("dims") or {}
        out.append({
            "dims": dims,
            "n": n,
            "below_floor": n < _LAB_N_FLOOR,
            "med_impressions": cell.get("med_impressions"),
            "med_likes": cell.get("med_likes"),
            "med_replies": cell.get("med_replies"),
            "med_reposts": cell.get("med_reposts"),
        })
    return out


def allies(root=None) -> dict:
    """Allies (ecosystem) cockpit — MKT-D11 W1.

    Reads the deterministically-scored target ledger
    (data/marketing/allies_targets.jsonl, one JSON/line), folds the operator
    status ledger (data/operator/allies_status.jsonl) over it, and returns the
    targets sorted by score (desc) with their current status + history.

    **Read-only + gated:** this panel never contacts anyone. Status past
    ``candidate`` is an operator-only action recorded by allies_store; the panel
    only *shows* where each target stands. Fail-soft: missing ledger → ok:True
    with the standard accruing note and empty sections.
    """
    from . import allies_store  # noqa: PLC0415 — lazy to keep import graph flat

    repo = Path(root) if root is not None else _default_root()
    try:
        targets = _read_jsonl(repo / _ALLIES_REL)
        if not targets:
            return {
                "ok": True,
                "note": _ALLIES_ACCRUING_NOTE,
                "as_of": None,
                "targets": [],
                "counts": {"total": 0, "by_kind": {}, "by_verdict": {}, "by_status": {}},
                "referral_note": _ALLIES_REFERRAL_NOTE,
                "operator_gate": _ALLIES_OPERATOR_GATE,
            }

        fold = allies_store.fold_status(targets)
        kits_dir = repo / _KITS_REL

        folded: list[dict] = []
        for t in targets:
            tid = str(t.get("target_id") or "")
            f = fold.get(tid, {"status": allies_store.SEED_STATUS, "history": []})
            kit_path = t.get("kit_path")
            kit_available = False
            if kit_path:
                # Trust the seed's declared path but resolve it under the repo;
                # never let a crafted path escape the repo (defence in depth —
                # the file is engine-authored, but the panel stays paranoid).
                try:
                    kp = (repo / str(kit_path)).resolve()
                    kit_available = kp.is_file() and str(kp).startswith(str(repo.resolve()))
                except Exception:  # noqa: BLE001
                    kit_available = False
            elif tid:
                kit_available = (kits_dir / f"{tid}.md").is_file()

            row = dict(t)
            row["status"] = f["status"]
            row["status_history"] = f["history"]
            row["kit_available"] = bool(kit_available)
            folded.append(row)

        # Sort by score desc; None scores sink to the bottom deterministically.
        folded.sort(key=lambda r: (r.get("score") is not None, r.get("score") or 0.0), reverse=True)

        # Counts (honest tallies — no derived claims).
        by_kind: dict[str, int] = {}
        by_verdict: dict[str, int] = {}
        by_status: dict[str, int] = {}
        as_of = None
        for r in folded:
            by_kind[r.get("kind") or "unknown"] = by_kind.get(r.get("kind") or "unknown", 0) + 1
            v = r.get("outreach_verdict") or "unknown"
            by_verdict[v] = by_verdict.get(v, 0) + 1
            s = r.get("status") or allies_store.SEED_STATUS
            by_status[s] = by_status.get(s, 0) + 1
            seeded = r.get("seeded_utc")
            if seeded and (as_of is None or str(seeded) > str(as_of)):
                as_of = seeded

        return {
            "ok": True,
            "as_of": as_of,
            "targets": folded,
            "counts": {
                "total": len(folded),
                "by_kind": by_kind,
                "by_verdict": by_verdict,
                "by_status": by_status,
            },
            "referral_note": _ALLIES_REFERRAL_NOTE,
            "operator_gate": _ALLIES_OPERATOR_GATE,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.allies failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def allies_kit(root=None, target_id=None) -> dict:
    """Return one target's materials-kit markdown.

    target_id is sanitised to [a-z0-9-] by the *server* before it reaches here;
    this function additionally refuses anything with a path separator or "..".
    Fail-soft: unknown/absent kit → ok:True with markdown="" and a note.
    """
    repo = Path(root) if root is not None else _default_root()
    tid = str(target_id or "")
    # Belt-and-braces: never trust a raw id for a filesystem read.
    if (not tid) or ("/" in tid) or ("\\" in tid) or (".." in tid):
        return {"ok": False, "error": "invalid target_id"}
    try:
        p = repo / _KITS_REL / f"{tid}.md"
        if not p.is_file():
            return {
                "ok": True,
                "target_id": tid,
                "markdown": "",
                "note": "No kit rendered for this target yet.",
            }
        return {"ok": True, "target_id": tid, "markdown": p.read_text(encoding="utf-8")}
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.allies_kit failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _opportunity_pipeline(root: Path) -> dict | None:
    """Pull the scored opportunity-queue block out of marketing state.

    Mirrors the shape campaigns() exposes (pipeline.opportunities). Returns
    None when state is absent so radar() can render an honest empty block.
    """
    s = _state(root)
    if s is None:
        return None
    pipeline = s.get("pipeline") or {}
    return pipeline.get("opportunities")


def radar(root=None) -> dict:
    """Radar (intelligence department) admin view — "what we could be posting
    but aren't".

    Reads data/marketing/radar_report.json + data/marketing/cashtag_tiers.json
    and joins the scored opportunity queue from marketing_state.json.  All three
    sources are fail-soft: a missing file degrades that section to null/empty,
    never raises.

    When the radar report itself is absent (first nightly hasn't run) returns
    ok:True with available:False and a plain-word note so the page renders an
    honest accruing state on day 0.

    Response keys: ok, available, note?, as_of, produced_at, feeds, posted_recent,
    surplus, queue, tiers_summary, cadence, opportunities, universe_n.
    """
    repo = Path(root) if root is not None else _default_root()
    try:
        report = _read_json(repo / _RADAR_REL)
        tiers  = _read_json(repo / _TIERS_REL)
        opportunities = _opportunity_pipeline(repo)

        if report is None:
            # First nightly hasn't produced the report. Still surface the
            # opportunity queue if state exists — it's the one live signal on day 0.
            return {
                "ok": True,
                "available": False,
                "note": _RADAR_ACCRUING_NOTE,
                "as_of": None,
                "produced_at": None,
                "feeds": [],
                "posted_recent": None,
                "surplus": [],
                "queue": None,
                "tiers_summary": None,
                "cadence": None,
                "opportunities": opportunities,
                "universe_n": (tiers or {}).get("universe_n"),
                "tiers": (tiers or {}).get("tiers"),
                "tickers": (tiers or {}).get("tickers"),
            }

        return {
            "ok": True,
            "available": True,
            "as_of": report.get("as_of"),
            "produced_at": report.get("produced_at"),
            "feeds": report.get("feeds") or [],
            "posted_recent": report.get("posted_recent"),
            "surplus": report.get("surplus") or [],
            "queue": report.get("queue"),
            "tiers_summary": report.get("tiers_summary"),
            "cadence": report.get("cadence"),
            "opportunities": opportunities,
            # Full cashtag-tier universe (fail-soft: null when the tiers file is absent).
            "universe_n": (tiers or {}).get("universe_n"),
            "tiers": (tiers or {}).get("tiers"),
            "tickers": (tiers or {}).get("tickers"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.radar failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def department(root=None, dept_id=None) -> dict:
    """Single-department detail payload.

    Returns mission/tagline/formal_name, engines [{id,name,does}], scorecard,
    authority, model mix, wave, retirement test.
    Fail-soft: returns ok:True with note if state absent or dept not found.
    """
    repo = Path(root) if root is not None else _default_root()
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "department": None,
            }
        depts = s.get("departments") or []
        if dept_id is None:
            return {
                "ok": True,
                "note": "dept_id required",
                "department": None,
            }
        dept = next((d for d in depts if d.get("id") == dept_id), None)
        if dept is None:
            return {
                "ok": True,
                "note": f"Department '{dept_id}' not found (accruing or unknown id).",
                "department": None,
            }
        return {
            "ok": True,
            "department": dept,
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.department failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def sentinel(root=None) -> dict:
    """Sentinel trust_office gate report: reads data/marketing/sentinel_report.json.

    Returns the report plus a small derived summary (top reasons by frequency).
    Fail-soft: returns ok:True with honest note when the file is absent.
    JSON only — no HTML/design surface.
    """
    repo = Path(root) if root is not None else _default_root()
    try:
        rpt = _read_json(repo / _SENTINEL_REL)
        if rpt is None:
            return {
                "ok": True,
                "note": _SENTINEL_ACCRUING_NOTE,
                "plan_status": None,
                "publish_enabled": None,
                "counts": None,
                "top_reasons": [],
                "quarantined": [],
            }
        # Derive top reasons from reasons_histogram
        histogram = rpt.get("reasons_histogram") or {}
        top_reasons = sorted(histogram.items(), key=lambda x: x[1], reverse=True)[:10]
        quarantined = rpt.get("quarantined") or []
        # Partition by class: "policy" = real ban-risk/content flags the operator
        # reviews; "overflow" = capacity trims (plan over-generates by design).
        # Entries without a class (pre-split reports) count as policy — conservative.
        policy_q = [q for q in quarantined if q.get("class") != "overflow"]
        overflow_q = [q for q in quarantined if q.get("class") == "overflow"]
        return {
            "ok": True,
            "plan_status": rpt.get("plan_status"),
            "publish_enabled": rpt.get("publish_enabled"),
            "auditor_strict": rpt.get("auditor_strict"),
            "as_of": rpt.get("as_of"),
            "produced_at": rpt.get("produced_at"),
            "counts": rpt.get("counts"),
            "top_reasons": [{"reason": r, "count": c} for r, c in top_reasons],
            # The cleared-to-post list (account, type, cashtag, headline, slot,
            # display_time). Added by the sibling engine PR — passed through when
            # present so the render can list the posts, not just a count. None when
            # tonight's report predates the engine fix (render shows the count).
            "passed": rpt.get("passed"),
            "quarantined": quarantined,
            "policy_quarantined": policy_q,
            "overflow_quarantined": overflow_q,
            "checks": rpt.get("checks"),
            "notes": rpt.get("notes") or [],
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.sentinel failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _caps_by_account(cfg: dict, repo, *, as_of: str | None = None) -> dict:
    """Per-account daily post cap: the base ceiling narrowed by each desk's D08
    age-ramp tier.

    The scalar ``cap`` every payload already carries is the BASE number and stays
    exactly as it was (frozen contract). This is ADDITIVE: without it a panel
    shows "unlimited" next to a week-1 desk whose real allowance is 2. -1 still
    means unlimited. Fail-soft: {} when the ramp cannot be resolved.
    """
    try:
        from engine.marketing import outbox as _ob  # noqa: PLC0415
        from engine.marketing.accounts import effective_accounts  # noqa: PLC0415
        from engine.marketing.sentinel import resolve_ramp  # noqa: PLC0415
        ref = as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # announce=False: an admin page render must never write to the CI
        # annotation stream — the nightly gate owns those warnings.
        ramp = resolve_ramp(cfg or {}, ref, root=repo, announce=False)
        return {
            str(acc.get("id", "")): _ob.effective_cap_for(
                cfg, str(acc.get("id", "")), ref, root=repo, ramp=ramp)
            for acc in effective_accounts(cfg, repo) if acc.get("id")
        }
    except Exception as exc:  # noqa: BLE001 — a display extra must never 500 a panel
        log.warning("marketing._caps_by_account: %s", exc)
        return {}


def _seo_director_state() -> dict:
    """Read the SEO Director on/off state from the GitHub Actions repo variable.

    Returns {"enabled": true|false|null, "note": str|None}. This is the honest-
    unknown contract (docket §11.1: unknown ≠ zero) — when there is no GitHub
    token the state is UNKNOWN (null), never rendered as "off". Fully fail-soft:
    a missing token, an import error, or a network failure all degrade to
    enabled:null with a plain-word note rather than raising.
    """
    try:
        from admin import github_api  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return {"enabled": None,
                "note": "GitHub API unavailable — director state can't be read here."}
    try:
        if not github_api.token():
            return {"enabled": None,
                    "note": "No GitHub token configured — the director's on/off "
                            "state is unknown from here (not the same as off)."}
        raw = github_api.get_repo_variable(_SEO_DIRECTOR_VAR)
        if raw is None:
            # Variable never set: the workflow gate is `vars.SEO_DIRECTOR_ENABLED
            # == 'true'`, so unset means scheduled runs stay DARK (D12A R5 —
            # opt-in, mirrors CODEX_MODE). Manual "Run now" still works.
            return {"enabled": False,
                    "note": f"{_SEO_DIRECTOR_VAR} not set — scheduled runs off "
                            "(manual runs still work). Toggle on to arm the "
                            "weekly loop."}
        return {"enabled": str(raw).strip().lower() == "true", "note": None}
    except Exception as exc:  # noqa: BLE001
        log.warning("seo director state read failed: %s", exc)
        return {"enabled": None,
                "note": "Couldn't reach GitHub to read director state — try again."}


def seo(root=None) -> dict:
    """Beacon SEO control plane — the operator's window on site SEO health.

    Reads four committed artifacts from data/marketing/seo/ (all fail-soft):
      - seo_audit.json       — health score, per-family census, sitemap + crawl
      - seo_work_orders.json — priority-ordered, falsifiable fix tickets
      - seo_scorecard.json   — score + severity counts + deltas vs prior run
      - seo_history.jsonl    — score + issue trend, one line per audit

    Also reads the SEO_DIRECTOR_ENABLED GitHub Actions variable for the nightly
    director's on/off state (network read, fully fail-soft — null when unknown).

    When the audit itself is absent (no crawl has run) returns ok:True with
    available:False and a plain-word accruing note, so the page renders an
    honest day-0 state — never an error, never a fake-healthy zero.

    Search Console is deliberately reported as an explicit unavailable state
    (search_console.connected:false) rather than zeroed: unknown ≠ zero.

    Response keys: ok, available, note?, as_of, health_score, census, sitemap,
    crawl_infra, issues, work_orders, scorecard, history, director,
    search_console.
    """
    repo = Path(root) if root is not None else _default_root()
    try:
        audit     = _read_json(repo / _SEO_AUDIT_REL)
        orders    = _read_json(repo / _SEO_ORDERS_REL)
        scorecard = _read_json(repo / _SEO_SCORECARD_REL)
        history   = _read_jsonl(repo / _SEO_HISTORY_REL)
        director  = _seo_director_state()

        # Search Console is a future integration — always reported as an
        # explicit unavailable slot, never as healthy zero (docket §11.1).
        search_console = {
            "connected": False,
            "note": "Search Console credentials not configured — data unavailable.",
            "hint": "Add a Search Console service account to surface clicks, "
                    "impressions, and index coverage here.",
        }

        if audit is None:
            # No crawl has run. Still surface anything that exists (history,
            # scorecard) so the trend can start filling before the first full audit.
            return {
                "ok": True,
                "available": False,
                "note": _SEO_ACCRUING_NOTE,
                "as_of": None,
                "health_score": None,
                "census": None,
                "sitemap": None,
                "crawl_infra": None,
                "issues": [],
                "work_orders": (orders or {}).get("orders") or [],
                "scorecard": scorecard,
                "history": history,
                "director": director,
                "search_console": search_console,
            }

        return {
            "ok": True,
            "available": True,
            "as_of": audit.get("as_of"),
            "health_score": audit.get("health_score"),
            "census": audit.get("census"),
            "sitemap": audit.get("sitemap"),
            "crawl_infra": audit.get("crawl_infra"),
            "issues": audit.get("issues") or [],
            "work_orders": (orders or {}).get("orders") or [],
            "scorecard": scorecard,
            "history": history,
            "director": director,
            "search_console": search_console,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.seo failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def settings(root=None) -> dict:
    """Echo of config/marketing.yml top-level knobs. Read-only."""
    repo = Path(root) if root is not None else _default_root()
    try:
        cfg = _read_yaml(repo / _CONFIG_REL)
        s_block = cfg.get("settings") or {}
        return {
            "ok": True,
            "settings": {
                "trial_variant":      s_block.get("trial_variant", "7_trading_days"),
                "desk_network_stage": s_block.get("desk_network_stage", "A"),
                "paid_enabled":       bool(s_block.get("paid_enabled", False)),
                "auditor_strict":     bool(s_block.get("auditor_strict", True)),
                "north_star_window_days": int(s_block.get("north_star_window_days", 90)),
            },
            "positioning": cfg.get("positioning") or {},
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.settings failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Outbox panel (D02 W0, Lane B)
# ---------------------------------------------------------------------------

_OUTBOX_EMPTY_NOTE = (
    "outbox empty — items accrue when the nightly governor runs "
    "with MARKETING_OUTBOX_ENABLED=1."
)

_TERMINAL_STATUSES = frozenset({"posted", "failed", "quarantined", "recalled"})
# "posting" = W1 publisher in-flight marker (approved→posting before the network
# call); surfaced so a crashed/stuck post is visible on the panel, not dropped.
# "recalled" = booked at the backend, then CANCELLED before it sent
# (scripts/marketing_recall.py). Terminal — it never went out and can never
# re-send; see the TRANSITIONS note in engine/marketing/outbox.py.
_STATUS_KEYS = ("queued", "approved", "held", "posting", "posted", "failed",
                "quarantined", "recalled")


def _zero_counts() -> dict:
    return {k: 0 for k in _STATUS_KEYS}


def outbox(root=None) -> dict:
    """Posting-queue panel.

    Reads data/marketing/outbox/{items.jsonl,status_ledger.jsonl,decisions.jsonl}
    via engine.marketing.outbox public API.  Fail-soft: ok:True on absent files,
    ok:False only on unexpected exceptions.

    Frozen payload contract: see D02 W0 Lane B spec.
    """
    repo = Path(root) if root is not None else _default_root()
    try:
        from engine.marketing import outbox as _ob  # noqa: PLC0415

        # Config for effective_cap + the Sentinel contract echo
        cfg = _read_yaml(repo / _CONFIG_REL)
        sentinel = _ob.sentinel_contract(cfg)
        cap = sentinel["effective_cap"]

        # One-pass fold of items + ledger + decisions (fail-soft → empty)
        state = _ob.fold_state(repo)
        items = [state["items"][i] for i in state["order"]]
        statuses = state["status"]
        decisions = state["decisions"]
        activity = list(reversed(_ob.read_activity(repo, n=8)))

        # Empty state
        if not items:
            return {
                "ok": True,
                "note": _OUTBOX_EMPTY_NOTE,
                "as_of": None,
                "cap": cap,
                "caps_by_account": _caps_by_account(cfg, repo),
                "sentinel": sentinel,
                "summary": _zero_counts() | {"total": 0},
                "accounts": [],
                "history": [],
                "activity": activity,
                "decision_log": [],
            }

        # Compute effective status per item (folded status + held overlay)
        def _effective_status(item_id: str, folded: str, decision: str | None) -> str:
            """Held = queued status AND latest decision is 'hold'."""
            if folded == "queued" and decision == "hold":
                return "held"
            return folded

        # Build item enriched dicts
        enriched: list[dict] = []
        for item in items:
            item_id = item.get("id", "")
            folded = statuses.get(item_id, item.get("status", "queued"))
            dec_row = decisions.get(item_id)
            dec_val = dec_row.get("decision") if dec_row else None
            decided_at = dec_row.get("at") if dec_row else None
            eff = _effective_status(item_id, folded, dec_val)
            last_row = state["last"].get(item_id)
            last_transition_at = last_row.get("at") if last_row else None
            receipt = last_row.get("receipt") if last_row else None
            enriched.append({
                "id": item_id,
                "as_of": item.get("as_of"),
                "kind": item.get("kind"),
                "text": item.get("text"),
                "media": item.get("media") or [],
                "scheduled_at": item.get("scheduled_at"),
                "slot": item.get("slot"),
                "priority": item.get("priority"),
                "provenance": item.get("provenance"),
                "status": folded,               # ledger-folded status (not held overlay)
                "decision": dec_val,
                "decided_at": decided_at,
                "created_at": item.get("created_at"),
                "last_transition_at": last_transition_at,
                "attempts": state["attempts"].get(item_id, 0),
                "receipt": receipt,
                "_effective": eff,
                "_account": item.get("account", ""),
            })

        # Max as_of across items
        as_of_vals = [e["as_of"] for e in enriched if e.get("as_of")]
        max_as_of = max(as_of_vals) if as_of_vals else None

        # Summary counts
        summary_counts = _zero_counts()
        for e in enriched:
            eff = e["_effective"]
            if eff in summary_counts:
                summary_counts[eff] += 1
        summary = {"total": len(enriched)} | summary_counts

        # Group by account, ordered by account id
        acct_map: dict[str, list] = {}
        for e in enriched:
            acct = e["_account"]
            acct_map.setdefault(acct, []).append(e)

        accounts_out: list[dict] = []
        for acct_id in sorted(acct_map.keys()):
            acct_items = acct_map[acct_id]
            # Sort by scheduled_at then id
            acct_items.sort(key=lambda x: (x.get("scheduled_at") or "", x.get("id") or ""))
            acct_counts = _zero_counts()
            for e in acct_items:
                eff = e["_effective"]
                if eff in acct_counts:
                    acct_counts[eff] += 1
            # Build item dicts (drop internal keys)
            items_out = [
                {k: v for k, v in e.items() if not k.startswith("_")}
                for e in acct_items
            ]
            accounts_out.append({
                "id": acct_id,
                "counts": acct_counts,
                "items": items_out,
            })

        # History: terminal items, newest first by last_transition_at
        terminal = [
            e for e in enriched
            if e["status"] in _TERMINAL_STATUSES
        ]
        terminal.sort(
            key=lambda x: (x.get("last_transition_at") or ""),
            reverse=True,
        )
        history_out = [
            {
                "id": e["id"],
                "account": e["_account"],
                "kind": e["kind"],
                "text": e["text"],
                "status": e["status"],
                "at": e["last_transition_at"],
                "receipt": e["receipt"],
            }
            for e in terminal[:50]
        ]

        # Per-item decision log — the operator's audit trail (holds/approvals +
        # actuator transitions), which the pipeline `activity` (run tallies) does
        # not surface. Derived from the rows fold_state already read; no extra IO
        # beyond the two cheap reads below.
        id_meta = {e["id"]: (e["_account"], e.get("kind") or "") for e in enriched}
        decision_log = _build_decision_log(
            _ob.read_decisions(repo), _ob.read_ledger(repo), id_meta, limit=12)

        return {
            "ok": True,
            "as_of": max_as_of,
            "cap": cap,
            "caps_by_account": _caps_by_account(cfg, repo, as_of=max_as_of),
            "sentinel": sentinel,
            "summary": summary,
            "accounts": accounts_out,
            "history": history_out,
            "activity": activity,
            "decision_log": decision_log,
        }

    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.outbox failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _build_decision_log(all_decisions: list, ledger: list, id_meta: dict,
                        limit: int = 12) -> list:
    """Merge decision + ledger rows into one newest-first per-item audit trail.

    Complements the pipeline `activity` feed (run tallies): this answers "what
    has been decided/done to each post, and by whom". Each event:
    {type, id, account, kind, at, actor, detail}. `type` is "approve"/"hold"
    (operator decisions) or "posted"/"failed"/"approved"/"quarantined"
    (actuator transitions). Rows for ids absent from id_meta still appear with
    account/kind = "" — the audit trail never silently drops an event.
    Fail-soft: never raises; malformed rows are skipped.
    """
    events: list[dict] = []
    for row in all_decisions or []:
        item_id = row.get("id")
        if not item_id:
            continue
        acct, kind = id_meta.get(item_id, ("", ""))
        events.append({
            "type": row.get("decision") or "decision",
            "id": item_id, "account": acct, "kind": kind,
            "at": row.get("at"), "actor": row.get("actor"), "detail": row.get("note"),
        })
    for row in ledger or []:
        item_id = row.get("id")
        if not item_id:
            continue
        acct, kind = id_meta.get(item_id, ("", ""))
        events.append({
            "type": row.get("to") or "transition",
            "id": item_id, "account": acct, "kind": kind,
            "at": row.get("at"), "actor": row.get("actor"), "detail": row.get("note"),
        })
    # Newest first; rows with no timestamp sort last (empty string).
    events.sort(key=lambda e: (e.get("at") or ""), reverse=True)
    return events[:limit]


# ---------------------------------------------------------------------------
# Publisher panel (D02 W1) — the live-publish control plane
# ---------------------------------------------------------------------------

_PUBLISHER_EMPTY_NOTE = (
    "Nothing has moved through the publisher yet. Items reach it once the "
    "outbox has APPROVED, DUE posts; the runner posts them when armed "
    "(MARKETING_PUBLISH_ENABLED=1 + --live). Dark until then."
)

# Recent posted-items window surfaced with their receipts.
def _latest_metrics_by_remote_id(repo: Path) -> dict[str, dict]:
    """Fold post_metrics.jsonl to the LATEST row per remote_id (Buffer post id).

    Append-only ledger: each poll appends a dated row; the newest (by polled_at,
    then file order as tiebreak) is the current analytics view. Fail-soft — an
    absent/unreadable ledger yields {} so the join is a silent no-op. Returns
    {remote_id: {metrics: {...}, external_url: str|None}} for the console join.
    """
    out: dict[str, dict] = {}
    best_ts: dict[str, str] = {}
    for row in _read_jsonl(repo / _POST_METRICS_REL):
        rid = str(row.get("remote_id") or "").strip()
        if not rid:
            continue
        ts = str(row.get("polled_at") or "")
        # Newest wins; equal/earlier polled_at from a later file line also wins
        # (>=) so a same-timestamp re-poll's last row is the one shown.
        if rid in best_ts and ts < best_ts[rid]:
            continue
        best_ts[rid] = ts
        metrics = row.get("metrics")
        out[rid] = {
            "metrics": metrics if isinstance(metrics, dict) else {},
            "external_url": row.get("external_url") or None,
        }
    return out


_PUBLISHER_RECENT_N = 10


def publisher(root=None) -> dict:
    """Publisher control-plane panel — the live-publish half of the desk network.

    Reads data/marketing/outbox/{items,status_ledger,activity}.jsonl via the
    engine.marketing.outbox public API (fail-soft) and config/marketing.yml for
    the publish block. NEVER echoes the Buffer token — only its presence as a
    boolean (env BUFFER_TOKEN).

    Returns:
      status_counts   — items by status (queued/approved/posting/posted/failed/
                        quarantined) across all accounts.
      recent_posted   — up to _PUBLISHER_RECENT_N most-recent `posted` items with
                        their receipt external_id/url, newest first.
      stuck_posting   — items left in `posting` (in-flight marker from a crashed
                        run) — surfaced PROMINENTLY; each needs a human look.
      quarantined     — quarantined items with the reason recorded on the
                        transition that quarantined them.
      activity        — the last few publisher_* activity rows (run tallies).
      config          — backend, cap, channel-id-set?, auto_approve, links_allowed,
                        require_approval, and token_present (bool only).

    Fail-soft: ok:True with empty sections + note on a cold outbox; ok:False only
    on an unexpected exception.
    """
    repo = Path(root) if root is not None else _default_root()
    try:
        from engine.marketing import outbox as _ob  # noqa: PLC0415
        import os  # noqa: PLC0415

        cfg = _read_yaml(repo / _CONFIG_REL)
        sentinel = _ob.sentinel_contract(cfg)
        cap = sentinel["effective_cap"]
        pub_cfg = (cfg.get("publish") or {}) if isinstance(cfg, dict) else {}
        channels = pub_cfg.get("channels") or {}
        links_allowed = pub_cfg.get("links_allowed") or {}
        # A channel is "set" when its id is a non-empty string.
        channel_set = {
            str(acct): bool(str(cid or "").strip())
            for acct, cid in channels.items()
        }

        def _parse_bool(v, default=False):
            if isinstance(v, bool):
                return v
            if v is None:
                return default
            return str(v).strip().lower() in {"1", "true", "yes"}

        config = {
            "backend": str(pub_cfg.get("backend") or "buffer"),
            "cap": cap,
            "caps_by_account": _caps_by_account(cfg, repo),
            "require_approval": _parse_bool(pub_cfg.get("require_approval"), True),
            "auto_approve": _parse_bool(pub_cfg.get("auto_approve"), False),
            "channels_set": channel_set,
            "any_channel_set": any(channel_set.values()),
            "links_allowed": {str(a): _parse_bool(v) for a, v in links_allowed.items()},
            # Token presence ONLY — the value is NEVER surfaced.
            "token_present": bool(os.environ.get("BUFFER_TOKEN", "").strip()),
        }

        # Kill-switch ARM state read from the GitHub repo VARIABLE (API truth),
        # env fallback when unreachable. The panel's armed/dark pill + ARM toggle
        # render from this, NOT from the admin process env (which is never set on
        # the operator's Mac — the pre-existing "always shows shadow" display bug).
        arm = arm_state()

        state = _ob.fold_state(repo)
        items = state["items"]
        statuses = state["status"]
        last = state["last"]
        order = state["order"]

        # Empty state — cold outbox.
        if not order:
            return {
                "ok": True,
                "note": _PUBLISHER_EMPTY_NOTE,
                "as_of": None,
                "config": config,
                "arm_state": arm,
                "status_counts": {k: 0 for k in _STATUS_KEYS if k != "held"},
                "recent_posted": [],
                "stuck_posting": [],
                "quarantined": [],
                "activity": [],
            }

        # Status counts (folded status; 'held' is an outbox overlay, not a
        # publisher state, so it is excluded here).
        status_counts = {k: 0 for k in _STATUS_KEYS if k != "held"}
        for iid in order:
            s = statuses.get(iid, items[iid].get("status", "queued"))
            if s in status_counts:
                status_counts[s] += 1

        # Latest per-post analytics (impressions/likes/… + x.com permalink),
        # keyed by Buffer post id == the receipt's external_id. Fail-soft {}.
        metrics_by_rid = _latest_metrics_by_remote_id(repo)

        def _row(iid: str) -> dict:
            it = items.get(iid, {})
            lr = last.get(iid) or {}
            rec = lr.get("receipt")
            rec = rec if isinstance(rec, dict) else None
            external_id = (rec or {}).get("external_id")
            external_url = (rec or {}).get("external_url")
            # Join fetched metrics + backfill the permalink (createPost never
            # returns one; the poller's post() query does). Front-end renders
            # `metrics`/`external_url` only when present, so absent = unchanged.
            met = metrics_by_rid.get(str(external_id or "").strip()) if external_id else None
            row = {
                "id": iid,
                "account": it.get("account", ""),
                "kind": it.get("kind"),
                "text": it.get("text"),
                "at": lr.get("at"),
                "note": lr.get("note"),
                "external_id": external_id,
                "external_url": external_url or (met or {}).get("external_url"),
                "backend": (rec or {}).get("backend"),
            }
            if met and met.get("metrics"):
                row["metrics"] = met["metrics"]
            return row

        posted = [_row(i) for i in order if statuses.get(i) == "posted"]
        posted.sort(key=lambda r: (r.get("at") or ""), reverse=True)
        recent_posted = posted[:_PUBLISHER_RECENT_N]

        stuck_posting = [_row(i) for i in order if statuses.get(i) == "posting"]
        stuck_posting.sort(key=lambda r: (r.get("at") or ""), reverse=True)

        quarantined = [_row(i) for i in order if statuses.get(i) == "quarantined"]
        quarantined.sort(key=lambda r: (r.get("at") or ""), reverse=True)

        # Publisher activity rows only (publisher_live / publisher_dry_run),
        # newest first. Read a wider window then filter to keep the last few.
        activity = [
            a for a in reversed(_ob.read_activity(repo, n=40))
            if str(a.get("lane", "")).startswith("publisher")
        ][:8]

        as_of_vals = [items[i].get("as_of") for i in order if items[i].get("as_of")]
        max_as_of = max(as_of_vals) if as_of_vals else None

        return {
            "ok": True,
            "as_of": max_as_of,
            "config": config,
            "arm_state": arm,
            "status_counts": status_counts,
            "recent_posted": recent_posted,
            "stuck_posting": stuck_posting,
            "quarantined": quarantined,
            "activity": activity,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.publisher failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def publisher_dryrun(root=None, account=None) -> dict:
    """Run the publisher in DRY-RUN and return the "would post" report.

    Thin wrapper over scripts.marketing_publisher.dry_run_report — an in-process
    entrypoint that makes NO network call and NO ledger write (it never invokes
    transition() or _append_activity()). Fail-soft: any error → ok:False.
    """
    repo = Path(root) if root is not None else _default_root()
    try:
        from scripts.marketing_publisher import dry_run_report  # noqa: PLC0415
        acct = account if (account and str(account).strip()) else None
        return dry_run_report(root=repo, account=acct)
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.publisher_dryrun failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def decide_outbox(item_id: str, decision: str, note: str | None = None, root=None) -> bool:
    """Thin wrapper: record an operator approve/hold decision via engine outbox API.

    Returns True on success, False on unknown id or invalid decision.
    Never raises.
    """
    try:
        from engine.marketing import outbox as _ob  # noqa: PLC0415
        repo = Path(root) if root is not None else _default_root()
        return _ob.record_decision(item_id, decision, actor="admin", root=repo, note=note)
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.decide_outbox failed: %s", exc)
        return False


def reject_outbox(item_id: str, reason: str | None = None, root=None) -> dict:
    """REJECT one outbox item: kill it AND record why.

    Hold is a reversible DECISION on a still-queued post, so a held item stays in
    the review rail — which is correct, but it left the operator no way to say
    "this one is bad, and here is what is wrong with it". Reject is the verdict:
    the item transitions to `quarantined` (terminal, drops out of the rail) and a
    row lands in data/marketing/rejections.jsonl for the review sheet.

    The ledger write is best-effort and deliberately AFTER the transition: a
    failure to record feedback must never leave a rejected post still queued.
    Returns {"ok": bool, ...}; never raises.
    """
    try:
        from engine.marketing import outbox as _ob  # noqa: PLC0415
        from engine.marketing import rejections as _rej  # noqa: PLC0415
        repo = Path(root) if root is not None else _default_root()

        iid = str(item_id or "").strip()
        if not iid:
            return {"ok": False, "error": "id required"}

        state = _ob.fold_state(repo)
        item = (state.get("items") or {}).get(iid)
        if item is None:
            return {"ok": False, "error": "unknown item id"}
        status = str((state.get("status") or {}).get(iid) or "queued")

        ok = _ob.transition(iid, "quarantined", actor="admin", root=repo,
                            note=(str(reason or "").strip() or "rejected by operator"))
        if not ok:
            return {"ok": False,
                    "error": f"cannot reject an item that is {status!r}",
                    "note": "posted and quarantined items are terminal"}

        row = _rej.record(item, reason=reason, actor="admin", root=repo)
        return {"ok": True, "id": iid, "rejected": True, "logged": bool(row),
                "note": None if row else
                        "rejected, but the feedback row could not be written"}
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.reject_outbox failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def rejections_pending(root=None) -> dict:
    """Rejections awaiting export — what the rejection box shows."""
    try:
        from engine.marketing import rejections as _rej  # noqa: PLC0415
        repo = Path(root) if root is not None else _default_root()
        rows = _rej.pending(repo)
        return {"ok": True, "count": len(rows), "rejections": rows}
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.rejections_pending failed: %s", exc)
        return {"ok": False, "error": str(exc), "count": 0, "rejections": []}


def export_rejections(root=None, *, mark: bool = True) -> dict:
    """Render pending rejections as a markdown review sheet.

    With mark=True (the default, and what the Export button sends) the exported
    ids are stamped so they leave the box — the operator asked not to mix
    already-reviewed rejections with new ones. The rows stay in the ledger; only
    the VIEW is cleared, because that corpus is the whole point of the loop.
    """
    try:
        from datetime import datetime, timezone  # noqa: PLC0415
        from engine.marketing import rejections as _rej  # noqa: PLC0415
        repo = Path(root) if root is not None else _default_root()
        rows = _rej.pending(repo)
        if not rows:
            return {"ok": False, "error": "nothing to export — no pending rejections",
                    "count": 0}
        stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        md = _rej.render_markdown(rows, generated_at=stamp)
        marked = False
        if mark:
            marked = _rej.mark_exported([str(r.get("id")) for r in rows], root=repo)
        return {"ok": True, "count": len(rows), "markdown": md, "cleared": marked,
                "filename": f"rejected-posts-{stamp[:10]}.md",
                "note": None if (marked or not mark) else
                        "exported, but the box could not be cleared"}
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.export_rejections failed: %s", exc)
        return {"ok": False, "error": str(exc), "count": 0}


def decide_outbox_batch(item_ids: list, decision: str, note: str | None = None,
                        root=None) -> dict:
    """Record one decision for many items (bulk approve/hold from the admin).

    Returns {"decided": n, "results": {id: bool}}. Order preserved; each id is
    validated independently so one unknown id never blocks the rest.
    Never raises.
    """
    results: dict[str, bool] = {}
    try:
        from engine.marketing import outbox as _ob  # noqa: PLC0415
        repo = Path(root) if root is not None else _default_root()
        for item_id in item_ids:
            if not isinstance(item_id, str) or not item_id:
                continue
            results[item_id] = _ob.record_decision(
                item_id, decision, actor="admin", root=repo, note=note)
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.decide_outbox_batch failed: %s", exc)
    return {"decided": sum(1 for v in results.values() if v), "results": results}


# ---------------------------------------------------------------------------
# Operator write actions (the three writes this admin owns into data/marketing:
# the sentinel exception ledger, the account override file, and the Intelligence
# Desk approve click that appends ONE canonical item to the outbox)
# ---------------------------------------------------------------------------

#: Provenance + source.lane stamped on every item this approve path enqueues.
#: One string, so a query for "what did the desk queue" is exact rather than a
#: guess at which producer wrote a row.
_INTEL_LANE = "intelligence_desk"

#: Plain-word detail per non-"queued" enqueue verdict. Keyed by the exact string
#: outbox.enqueue returns so a new verdict shows up as its own slug rather than
#: being folded into a neighbour's sentence.
_INTEL_ENQUEUE_DETAIL: dict[str, str] = {
    "duplicate": ("this draft is already in the outbox; the second click "
                  "queued nothing"),
    "cross_account_duplicate": ("another desk already has near-identical copy "
                                "in the queue"),
    "cap_exceeded": ("that desk has used its posts for the day; the cap is a "
                     "sentinel setting, not a bug"),
}


#: The one file a queued item MUST reach for the publisher to post it. An item
#: with no transition rows folds as `queued`, so this row alone is postable —
#: which is what makes the single-file API delivery below sufficient.
_INTEL_ITEMS_REL = "data/marketing/outbox/items.jsonl"

#: Review N6: `outbox.enqueue` writes ONLY items.jsonl — the earlier three-ledger
#: tuple here rested on a false premise and its scoped commit would have SWEPT
#: whatever unrelated dirt other lanes had left on the status/activity ledgers
#: of a shared checkout onto main. Delivery commits exactly the one file the
#: enqueue wrote. (gitops._ALLOWED_PATHS keeps all three outbox ledgers listed —
#: harmless, and a future path that really writes them can opt in explicitly.)
_INTEL_OUTBOX_LEDGERS = (_INTEL_ITEMS_REL,)

#: Plain-word sentence per failed API-delivery step (github_api's ``step`` key).
#: Keyed by step rather than by parsing the error so a new failure mode reads as
#: itself instead of being folded into a neighbour's sentence.
_INTEL_API_STEP_WHY: dict[str, str] = {
    "unavailable": "this machine has no working link to the shared queue",
    "read": "the step that reads the shared queue on main failed",
    "too_large": "the shared queue file on main is too big to update this way",
    "write": "the step that writes the row to main failed",
}


def _intel_refuse(reason: str, detail: str, **extra) -> dict:
    """The ONE refusal shape for the approve path: {ok:false, reason, detail}.

    ``reason`` is a stable machine slug naming the gate that fired (the UI keys
    its message off it); ``detail`` is the plain-word sentence an operator reads.
    Every early return below goes through here so no caller has to guess whether
    a refusal carries ``error`` or ``reason``.
    """
    return {"ok": False, "reason": reason, "detail": detail, **extra}


def _intel_deliver(item: dict) -> tuple[bool, str]:
    """Get a queued item OUT of this checkout and onto main, however this host can.

    The queue the operator just wrote to is NOT the queue the publisher reads.
    The publisher runs in GitHub Actions off the git-tracked outbox ON MAIN; the
    admin writes to whatever checkout it is running in. A row that never leaves
    that disk is a post that never happens, and — worse — it looks queued in the
    panel the whole time.

    Two hosts, two mechanisms, chosen by ``settings.deployed()`` — the same
    predicate the account toggle switches on, so the two write paths can't
    disagree about which machine they are:

    * DEPLOYED VPS -> the GitHub Contents API (``_intel_deliver_via_api``). git
      is not an option there at all: the checkout has no authenticated remote,
      and ``app/deploy/update.sh`` resets it ``--hard`` to origin/main every few
      minutes, so a local commit is not slow delivery — it is DELETED delivery,
      taking the row with it.
    * Authenticated local checkout -> scoped commit + ONE plain push
      (``gitops.commit_paths``): no rebase retry, because this checkout may be
      occupied by other agents and a rebase rewrites it under them (review N6).
      A push refused by a racing press-wire commit is reported, not forced.

    Exactly one is attempted per call. Never both: a fallback would either write
    the same row twice or spend a doomed git shell-out on every VPS approval.
    (A ``root=``-pinned call never gets here — see the call site.)

    Returns ``(delivered, note)``. ``delivered`` is True ONLY when the row is on
    main. Every other outcome returns False plus a plain-word sentence — this
    never raises and never un-queues: the item is on disk and real either way,
    and the honest thing to tell the operator is "queued here, not delivered".
    """
    item_id = str(item.get("id") or "")
    try:
        from . import settings  # noqa: PLC0415
        is_deployed = settings.deployed()
    except Exception as exc:  # noqa: BLE001
        # Unreadable deploy mode falls to git, which refuses honestly on a host
        # that can't push — a wrong guess here costs a note, never a bad write.
        log.warning("intelligence_approve: could not read deploy mode: %s", exc)
        is_deployed = False
    if is_deployed:
        return _intel_deliver_via_api(item, item_id)
    return _intel_deliver_via_git(item_id)


def _intel_deliver_via_api(item: dict, item_id: str) -> tuple[bool, str]:
    """Deployed-VPS delivery: append this item's row to items.jsonl ON main.

    Only the ITEMS row is delivered, not the three ledgers the git path commits.
    That is sufficient, not a shortcut: the publisher folds an item carrying no
    transition rows as ``queued``, so the row alone is postable — and one file is
    one atomic commit, where three would be three chances to half-land.

    The row is serialized EXACTLY as ``engine/marketing/ledgers.append_jsonl``
    wrote it locally (compact separators, ensure_ascii=False). Byte-identical
    matters: main's copy and this checkout's copy are the same append-only file,
    and a re-serialized row would show up as a diff in a file whose merge driver
    is union. A test pins this against the line the local enqueue actually wrote.

    Idempotency is the on-main id check, not the local one. A re-click after a
    slow response is the ordinary case; a re-click after the 3-minute deploy pull
    reset the checkout is the dangerous one, because the local duplicate guard's
    memory went with it — and the item id is a content hash, so the second click
    rebuilds the SAME id. Asking main is the only question that survives a reset.
    """
    try:
        from . import github_api  # noqa: PLC0415
        line = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        res = github_api.append_jsonl_line(
            _INTEL_ITEMS_REL, line,
            f"admin: intelligence desk approve {item_id}",
            # Compact-form id field: items.jsonl is written only by
            # ledgers.append_jsonl (and by this line), so the spacing is exact.
            if_absent=f'"id":{json.dumps(item_id)}')
    except Exception as exc:  # noqa: BLE001
        log.warning("intelligence_approve: API delivery step failed: %s", exc)
        return False, ("It has NOT reached the publisher, so it will not post "
                       f"until it does: the delivery step failed ({exc}). It is "
                       "still queued on this machine, so you can approve it "
                       "again later.")
    if res.get("ok") and res.get("appended"):
        return True, ("It has reached the shared queue on main, so the publisher "
                      "will see it on its next sweep.")
    if res.get("ok"):
        # already_present: the row is on main, which is the only thing the word
        # "delivered" claims. Say it was already there rather than let a second
        # click read as a second post.
        return True, ("It was already on the shared queue on main, so the "
                      "publisher will see it on its next sweep — this click "
                      "queued nothing twice.")
    step = str(res.get("step") or "")
    why = _INTEL_API_STEP_WHY.get(step, "the delivery step reported no result")
    err = str(res.get("error") or "").strip().rstrip(".")
    if err:
        why = f"{why} ({err})"
    # A too-large ledger is the one failure a retry cannot clear: rotation is a
    # different job. Don't send the operator back to a button that can't work.
    tail = (" Rotating the shared queue is what fixes this — approving again "
            "will not."
            if step == "too_large" else
            " It is still queued on this machine until the next deploy pull "
            "resets the checkout, and you can approve it again later.")
    return False, (f"It has NOT reached the publisher, so it will not post "
                   f"until it does: {why}.{tail}")


def _intel_deliver_via_git(item_id: str) -> tuple[bool, str]:
    """Local authenticated checkout: scoped commit of items.jsonl + ONE push.

    Review N6: no fetch/rebase retry loop here, deliberately. This branch runs
    only on a non-deployed checkout — which per repo law is often OCCUPIED by
    other agents mid-work — and a rebase rewrites the WHOLE checkout's history
    out from under them to win a push race over one ledger row. A single plain
    push either lands or refuses; a refusal is reported honestly and the row
    stays committed locally for the operator (or the checkout's owner) to push
    when the tree is theirs. The deployed VPS never takes this branch at all
    (Contents API), so the retry loop bought robustness exactly where it could
    do the most collateral damage.
    """
    try:
        from . import gitops  # noqa: PLC0415
        res = gitops.commit_paths(
            list(_INTEL_OUTBOX_LEDGERS),
            message=f"admin: intelligence desk approve {item_id}",
            push=True,
            confirm=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("intelligence_approve: delivery step failed: %s", exc)
        return False, ("It is queued on this machine, but the step that sends it "
                       f"to the publisher failed ({exc}), so it has not been "
                       "delivered yet.")
    if res.get("pushed"):
        return True, "It has reached the shared queue, so the publisher will see it."
    # NOT "it will go out later". A non-delivery is not a delay: the publisher
    # reads main and only main, and nothing re-tries this write afterwards. Say
    # that it will not post, and name the step that stopped it.
    why = str(res.get("warning") or res.get("error")
              or "the delivery step reported no result").strip().rstrip(".")
    return False, ("It has NOT reached the publisher, so it will not post until "
                   f"it does: {why}.")


def intelligence_approve(story_id, draft_id, root=None, *, now=None) -> dict:
    """Queue ONE Intelligence Desk draft into the outbox. The click IS the gate.

    Nothing on this path auto-approves: the endpoint only runs because an
    operator pressed a button on a draft they were looking at. What it does NOT
    do is trust that button. The story and the draft are re-read from the desk
    snapshot server-side and the text that reaches the outbox is the desk's own,
    so a tampered or merely stale browser payload cannot post copy no gate saw.

    The chain is the CANONICAL one ``engine/marketing/press_lane.py`` runs, in
    its order, because a second emission path with its own gate order is how a
    lane quietly ends up with weaker guards than the one it copied:

        language law -> value gate stamp -> make_item -> validate_item
        -> one-owner story lock -> enqueue (id / text / near-dup / cap guards)

    A successful enqueue is then DELIVERED (``_intel_deliver``): the outbox the
    publisher reads is the one on MAIN, not this checkout, so the approve click
    owns getting the row there — by commit+push on an authenticated checkout, or
    by the GitHub Contents API on the deployed VPS, which has no git credentials
    and whose checkout is reset --hard every few minutes. Delivery is reported,
    never enforced — a failure leaves the item queued and returns
    ``delivered: False`` with a plain-word note, because the item is real on disk
    either way and un-queueing it would be the actual data loss. A ``root=``
    pinned call attempts no delivery and carries no ``delivered`` key.

    GATES REFUSE WHEN THEY CANNOT RUN. This is publish-adjacent, so the polarity
    is the opposite of the display-tier panels above: a gate whose import or read
    fails returns a refusal, never a pass. That is a deliberate divergence from
    press_lane, which proceeds when the story lock cannot be consulted so an
    automated wire is never silently stopped. Here there is a human at the other
    end of the click who can be told, and told is better than posted.

    Returns {"ok": True, item_id, account, note, delivered?} or the
    ``_intel_refuse`` shape. Never raises.
    """
    try:
        sid = str(story_id or "").strip()
        did = str(draft_id or "").strip()
        if not sid or not did:
            return _intel_refuse("bad_request",
                                 "story_id and draft_id are both required")

        repo = Path(root) if root is not None else _default_root()

        # ── 1. Re-read the desk snapshot SERVER-SIDE ──────────────────────────
        snapshot = _intelligence_snapshot(repo, allow_live=(root is None))
        if snapshot is None:
            return _intel_refuse(
                "no_snapshot",
                "the Intelligence Desk snapshot is not readable right now, so "
                "there is nothing to approve against")

        story = next(
            (row for row in (snapshot.get("stories") or [])
             if isinstance(row, dict) and str(row.get("id") or "") == sid),
            None)
        if story is None:
            return _intel_refuse(
                "story_not_found",
                f"story {sid} is no longer in the desk snapshot; it may have "
                f"aged out since the page loaded")

        draft = next(
            (row for row in (story.get("drafts") or [])
             if isinstance(row, dict) and str(row.get("id") or "") == did),
            None)
        if draft is None:
            return _intel_refuse(
                "draft_not_found",
                f"draft {did} is no longer on that story; the desk replaces a "
                f"draft when the copy changes, so reload the queue")

        # ── 2. Review-only. needs_edit is NOT approvable ──────────────────────
        status = str(draft.get("status") or "").strip()
        if status != "review":
            return _intel_refuse(
                "not_reviewable",
                f"this draft is marked {status or 'unset'}, not ready for "
                f"review; only a review draft may be queued")

        text = str(draft.get("text") or "").strip()
        if not text:
            return _intel_refuse("empty_draft", "the draft carries no text")

        headline = str(story.get("headline") or "").strip()
        source_url = str(draft.get("source_url") or "").strip()

        # ── 3. House language law (doctrine v3 §9a) ───────────────────────────
        try:
            from engine.marketing.copywriter import (  # noqa: PLC0415
                banned_language as _banned_language,
            )
            violations = list(_banned_language(text))
        except Exception as exc:  # noqa: BLE001 — a gate that cannot run REFUSES
            log.warning("intelligence_approve: language gate unavailable: %s", exc)
            return _intel_refuse(
                "gate_unavailable",
                f"the house language gate could not run ({exc}); nothing was queued")
        if violations:
            return _intel_refuse(
                "banned_language",
                "the house language law refused this copy: "
                + ", ".join(str(v) for v in violations[:4]),
                violations=[str(v) for v in violations])

        cfg = _read_yaml(repo / _CONFIG_REL)

        # ── 4. Which desk owns this emission (XG-W2 config routing) ───────────
        # A story that carries no machine event_class routes to the module's own
        # fallback rather than to the string "none": an unclassified story is not
        # a class, and routing it as one would let a future config row silently
        # capture everything the classifier could not label.
        event_class = str(story.get("event_class") or "").strip()
        try:
            from engine.marketing import wire_routing as _wr  # noqa: PLC0415
            account = str(
                _wr.route(event_class, cfg=cfg, root=repo) if event_class
                else _wr.default_account(cfg)
            ).strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("intelligence_approve: routing unavailable: %s", exc)
            return _intel_refuse(
                "routing_unavailable",
                f"could not resolve which desk owns this post ({exc})")
        if not account:
            return _intel_refuse("routing_unavailable",
                                 "the wire routing table resolved no account")

        try:
            from engine.marketing import outbox as _ob  # noqa: PLC0415
            from engine.marketing import story_lock as _sl  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            log.warning("intelligence_approve: outbox path unavailable: %s", exc)
            return _intel_refuse(
                "outbox_unavailable",
                f"the canonical outbox path could not be loaded ({exc})")

        ts = now if now is not None else datetime.now(timezone.utc)
        as_of = ts.astimezone(timezone.utc).strftime("%Y-%m-%d")

        # ── 5. Build the item through the canonical path ──────────────────────
        # story_key rides on `source` because that is where the one-owner lock
        # reads it back from (story_lock.item_story_key) — an item enqueued
        # without it locks nothing, and the next desk to draw the same story
        # would be waved through.
        lock_key = _sl.story_key(cluster_key=sid, event_id=did, headline=headline)
        source: dict = {
            "lane": _INTEL_LANE,
            "story_id": sid,
            "draft_id": did,
            "url": source_url or None,
            "story_key": lock_key,
        }

        # Gift-Grip-Proof verdict rides on every emission (charter §0). The gate
        # must score the STRING THAT SHIPS (review N4): make_item posts `text`
        # alone — there is no headline+body composition on this lane — so
        # `headline` is empty here or the verdict is measured on copy that never
        # reaches X. The STORY headline still goes in as `source_headline`, which
        # is the upstream wire line the informational-surplus test compares
        # against ("we rewrote the headline" is not an answer).
        would_block = _ob.stamp_value_gate(
            source,
            headline="",
            body=text,
            kind="breaking",
            has_media=False,
            source_headline=headline,
            citation=source_url,
            cfg=cfg,
        )
        verdict = source.get("value_gate") or {}
        if _ob._value_gate_enforced(cfg):
            # stamp_value_gate is fail-soft by design (a downed gate must not
            # silence the automated desks). With enforcement ARMED that softness
            # is wrong here: an unevaluated gate is not a passed gate.
            if str(verdict.get("verdict") or "") == "error":
                return _intel_refuse(
                    "gate_unavailable",
                    "the value gate is armed to block but could not evaluate "
                    f"this post ({verdict.get('error')})")
            if would_block:
                return _intel_refuse(
                    "value_gate",
                    "the value gate abstained: "
                    + (", ".join(str(r) for r in (verdict.get("reasons") or []))
                       or "no reason recorded"),
                    violations=[str(r) for r in (verdict.get("reasons") or [])])

        try:
            item = _ob.make_item(
                account=account,
                kind="breaking",
                text=text,
                as_of=as_of,
                media=[],
                scheduled_at="immediate",
                priority=1,
                provenance=_INTEL_LANE,
                source=source,
                now=ts,
            )
        except ValueError as exc:
            return _intel_refuse("item_invalid", str(exc))

        errors = _ob.validate_item(item)
        if errors:
            return _intel_refuse("item_invalid", str(errors[0]))

        # ── 6. One conversation, one owner (cross-account lock) ───────────────
        try:
            lock = _sl.check(account, lock_key, _ob.read_items_all(repo),
                             now=ts, cfg=cfg)
        except Exception as exc:  # noqa: BLE001 — see the polarity note above
            log.warning("intelligence_approve: story lock unavailable: %s", exc)
            return _intel_refuse(
                "gate_unavailable",
                f"the one-owner story lock could not run ({exc}); nothing was queued")
        if not lock.allowed:
            return _intel_refuse(
                "story_locked",
                f"{lock.owner} already has this story inside the one-owner "
                f"window; two desks may not post the same conversation",
                owner=lock.owner)

        # ── 7. Enqueue (id dedup, text dedup, near-dup radar, daily cap) ──────
        # `duplicate` is NOT a dead end (review N5): the row already exists on
        # THIS disk, but the first click's DELIVERY may have failed — returning
        # here made that failure permanent, because every retry the note invited
        # refused as duplicate before ever reaching delivery again. Both delivery
        # paths are idempotent (the API append checks main for the id; the git
        # path's scoped commit no-ops on a clean file), so a duplicate falls
        # through to delivery instead of returning.
        result = str(_ob.enqueue(item, repo, cfg=cfg))
        duplicate_requeue = result == "duplicate"
        if result != "queued" and not duplicate_requeue:
            if result.startswith("invalid:"):
                return _intel_refuse("item_invalid", result.split(":", 1)[1])
            return _intel_refuse(result, _INTEL_ENQUEUE_DETAIL.get(
                result, f"the outbox refused this item ({result})"))

        # The note says what happens NEXT. Naming the item and the desk is the
        # caller's job (the admin card prints both), so this does not repeat it.
        note = ("Nothing posts now: it waits for the publisher's own gates "
                "exactly like every other outbox item.")
        if duplicate_requeue:
            note = ("This draft was already queued on this machine, so the "
                    "click queued nothing twice; delivery was re-checked. "
                    + note)
        # HONEST ABOUT THE PICTURE. `breaking` sits OUTSIDE the publisher's
        # _CHART_BEARING_KINDS, so a ticker-bearing item on this lane is not
        # deferred for a missing chart the way a signal/watchlist post is — it
        # ships bare. Say so rather than let the operator assume the
        # every-ticker-post-is-charted law covers this queue.
        if [t for t in (story.get("tickers") or []) if str(t or "").strip()]:
            note += (" This one names tickers and will go out as text only: "
                     "breaking sits outside the publisher's chart-bearing "
                     "kinds, so no chart is attached.")

        payload = {
            "ok": True,
            "item_id": item["id"],
            "account": account,
            "story_id": sid,
            "draft_id": did,
        }
        if duplicate_requeue:
            payload["reason"] = "duplicate"

        # ── 8. DELIVERY: the enqueue above wrote to THIS disk, not to main ────
        # Only the default repo root is a real checkout the publisher's copy of
        # the outbox descends from. A root=-pinned call is a test or a dev tool
        # writing into a scratch tree git knows nothing about, so it must never
        # shell out to git — and it gets no `delivered` key at all, because a
        # delivery that was never attempted is not a delivery that failed.
        if root is None:
            delivered, delivery_note = _intel_deliver(item)
            payload["delivered"] = delivered
            note += " " + delivery_note

        payload["note"] = note
        return payload
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.intelligence_approve failed: %s", exc)
        return _intel_refuse("error", str(exc))


def sentinel_allow(item_id, reason, root=None) -> dict:
    """Record an operator exception: "let this held post through at the next gate".

    Appends one row to data/marketing/sentinel_exceptions.jsonl. The gate reads
    the file on its next nightly run — this write does NOT publish anything; it
    changes what the *next* gate will pass. Fail-soft: returns {"ok": False,
    "error": ...} on bad input or a write failure, never raises.
    """
    try:
        # ledger rows are unbounded-append; cap operator input so one paste
        # can't balloon the file
        iid = str(item_id or "").strip()[:200]
        rsn = str(reason or "").strip()[:500]
        if not iid:
            return {"ok": False, "error": "item_id required"}
        if not rsn:
            return {"ok": False, "error": "reason required — say why this post is safe to allow"}
        from datetime import datetime, timezone  # noqa: PLC0415
        repo = Path(root) if root is not None else _default_root()
        path = repo / _SENTINEL_EXC_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "item_id": iid,
            "allow": True,
            "reason": rsn,
            "actor": "operator",
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return {
            "ok": True,
            "item_id": iid,
            "note": "Exception recorded. It takes effect at the next nightly gate — "
                    "nothing posts now.",
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.sentinel_allow failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _accounts_toggle_via_api(aid: str, entry: dict) -> dict:
    """Deployed-mode desk toggle: read data/marketing/account_overrides.json from
    main via the GitHub Contents API, merge this one account's override, and commit
    it straight back to main. Read-modify-write against the on-main copy means a
    single toggle never drops another desk's override. Never raises."""
    from . import github_api  # noqa: PLC0415
    rel = str(_ACCT_OVERRIDES_REL).replace("\\", "/")
    gf = github_api.get_file(rel)
    if not gf.get("ok"):
        return {"ok": False, "error": f"could not read {rel} on main: {gf.get('error')}"}
    current: dict = {}
    if gf.get("content"):
        try:
            parsed = json.loads(gf["content"])
            if isinstance(parsed, dict):
                current = parsed
        except Exception:  # noqa: BLE001 — a corrupt file must not wedge the toggle
            current = {}
    current[aid] = entry
    new_content = json.dumps(current, ensure_ascii=False, indent=2) + "\n"
    msg = f"admin: account override {aid} enabled={entry['enabled']}"
    pf = github_api.put_file(rel, new_content, msg, sha=gf.get("sha"))
    if not pf.get("ok"):
        return {"ok": False, "error": f"commit failed: {pf.get('error')}"}
    return {
        "ok": True, "account_id": aid, "enabled": entry["enabled"],
        "overrides": current, "pushed": True, "via": "github_api",
        "commit_sha": pf.get("commit_sha"),
        "note": ("Override committed to main via the GitHub API. The next nightly "
                 f"plan will treat {aid} as {'on' if entry['enabled'] else 'off'}."),
    }


def accounts_toggle(account_id, enabled, note=None, root=None,
                    push: bool = True) -> dict:
    """Turn a desk account on/off via the operator override file, then try to
    commit+push that one file so the nightly runner picks it up.

    Local checkout: read-modify-write the override file + git commit+push it.
    Deployed VPS (no git auth): commit the override to main via the GitHub
    Contents API instead (``_accounts_toggle_via_api``) — no longer refused.

    Read-modify-write of data/marketing/account_overrides.json (atomic replace),
    shape ``{"<account_id>": {"enabled": bool, "note": str, "at": iso}}``. Then
    best-effort git commit+push of *only* that file (via admin.gitops). If push
    fails the override is still saved locally and the return carries
    ``pushed: False`` + an honest note. Fail-soft: never raises.
    """
    try:
        aid = str(account_id or "").strip()[:100]
        if not aid:
            return {"ok": False, "error": "account_id required"}
        en = bool(enabled)
        from datetime import datetime, timezone  # noqa: PLC0415
        repo = Path(root) if root is not None else _default_root()
        # only accept ids that exist in config; fail-open when config is unreadable
        cfg = _read_yaml(repo / _CONFIG_REL)
        known = [str(a.get("id") or "").strip()
                 for a in ((cfg.get("desk_network") or {}).get("accounts") or [])
                 if isinstance(a, dict)] if isinstance(cfg, dict) else []
        if known and aid not in known:
            return {"ok": False, "error": f"unknown account '{aid}'"}
        entry = {
            "enabled": en,
            "note": str(note or "").strip()[:500],
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        # Deployed VPS admin has no authenticated git working tree, so persist the
        # override by committing it to main via the GitHub Contents API — the same
        # tokened path the variable/dispatch controls already use. Read-modify-write
        # is done against the file ON main so a single-account toggle never clobbers
        # the other accounts' overrides.
        from . import settings  # noqa: PLC0415
        if settings.deployed():
            return _accounts_toggle_via_api(aid, entry)

        path = repo / _ACCT_OVERRIDES_REL
        path.parent.mkdir(parents=True, exist_ok=True)

        # read-modify-write (local checkout path)
        current = _read_json(path)
        if not isinstance(current, dict):
            current = {}
        current[aid] = entry
        # atomic replace: write a temp sibling then os.replace
        import os  # noqa: PLC0415
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        os.replace(str(tmp), str(path))

        result = {"ok": True, "account_id": aid, "enabled": en,
                  "overrides": current}

        # Best-effort commit+push of just this file so it reaches the runner.
        if push:
            try:
                from . import gitops  # noqa: PLC0415
                rel = str(_ACCT_OVERRIDES_REL).replace("\\", "/")
                git_res = gitops.commit_paths(
                    [rel],
                    message=f"admin: account override {aid} enabled={en}",
                    push=True, confirm=True)
                result["pushed"] = bool(git_res.get("pushed"))
                result["git"] = git_res
                if not git_res.get("pushed"):
                    result["note"] = (
                        "Override saved locally. It will not reach the nightly runner "
                        "until this file is pushed to main — "
                        + str(git_res.get("warning") or git_res.get("error") or
                              "push not available from this checkout") + ".")
                else:
                    result["note"] = ("Override saved and pushed. The next nightly plan "
                                      f"will treat {aid} as {'on' if en else 'off'}.")
            except Exception as gexc:  # noqa: BLE001
                result["pushed"] = False
                result["note"] = ("Override saved locally; the commit/push step failed "
                                  f"({gexc}). It will not reach the runner until pushed.")
        else:
            result["pushed"] = False
            result["note"] = "Override saved locally (push skipped)."
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.accounts_toggle failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Reply desk (XG-W4)
#
# The reply queue is a SEPARATE store from the outbox and lives in HOST state
# (~/.mastermind/reply_desk), not the repo: Buffer cannot post replies, so a
# reply must never be mistaken for a postable outbox item, and the M1 is the
# nightly render host so nothing may write inside the checkout intraday.
#
# `store` here is the host-state root (reply_queue.state_dir), NOT the repo root
# — the two are different directories and conflating them is how a poller ends
# up dirtying the render tree.
# ---------------------------------------------------------------------------

def reply_queue(root=None, *, store=None, now=None) -> dict:
    """Reply-queue panel payload: per-account two-zone rail + dial + caps.

    Expiry runs first, so a draft whose window has closed is never presented
    for approval. A stale reply is dead, not a backlog item.

    ``now`` is injectable so expiry and the daily-send count are testable
    against a fixed clock rather than the wall clock.
    """
    try:
        from engine.marketing import reply_queue as _rq  # noqa: PLC0415
        from engine.marketing import sentinel as _sentinel  # noqa: PLC0415

        repo = Path(root) if root is not None else _default_root()
        cfg = _read_yaml(repo / "config" / "marketing.yml")
        ts = now or datetime.now(timezone.utc)

        # Same order as reply_export.sweep: release leases FIRST so an item
        # whose desktop session died is reclaimable, then expire. Expiring
        # before releasing would leave an in-flight item unreachable.
        #
        # skip_ids is NOT optional here. A panel read that releases a lease whose
        # receipt is still pending drops the item to `queued`, which has no edge
        # to `sent` — so ingest then fails with illegal_transition and a reply
        # that is already PUBLIC goes permanently uncounted while the cap hands
        # its slot back. Opening the admin page must not be able to do that.
        from engine.marketing import reply_export as _rx  # noqa: PLC0415

        released = _rq.release_expired_claims(now=ts, root=store,
                                              skip_ids=_rx.pending_receipt_ids(store))
        killed = _rq.expire_due(now=ts, root=store)

        state = _rq.fold_state(store)
        outcomes = _rq.outcomes(store)
        accounts: dict[str, dict] = {}

        for iid, item in state["items"].items():
            status = state["status"].get(iid, "queued")
            acc_id = str(item.get("account") or "unknown")
            block = accounts.setdefault(acc_id, {
                "id": acc_id, "awaiting": [], "approved": [], "done": [],
                "mode": _rq.resolve_mode(cfg, acc_id), "counts": {},
            })
            block["counts"][status] = block["counts"].get(status, 0) + 1

            row = {
                "id": iid,
                "status": status,
                "account": acc_id,
                "target_url": item.get("target_url"),
                "parent_author": item.get("parent_author"),
                "parent_excerpt": item.get("parent_excerpt"),
                "draft": item.get("draft"),
                "alt_drafts": item.get("alt_drafts") or [],
                "family": item.get("family"),
                "tier": item.get("tier"),
                "score": item.get("score"),
                "score_components": item.get("score_components") or {},
                "chart": item.get("chart"),
                "expires_at": item.get("expires_at"),
                "created_at": item.get("created_at"),
                "outcome": outcomes.get(iid) or {},
                "claim": state["claims"].get(iid),
                "attempts": state["attempts"].get(iid, 0),
            }
            if status == "queued":
                block["awaiting"].append(row)
            elif status in {"approved", "claimed", "failed"}:
                block["approved"].append(row)
            else:
                block["done"].append(row)

        for block in accounts.values():
            block["awaiting"].sort(key=lambda r: -float(r.get("score") or 0.0))
            block["approved"].sort(key=lambda r: -float(r.get("score") or 0.0))
            block["done"] = sorted(block["done"],
                                   key=lambda r: str(r.get("created_at") or ""),
                                   reverse=True)[:20]
            block["cap"] = _sentinel.reply_send_cap(cfg, block["id"], mode=block["mode"])
            block["sent_today"] = _rq.sends_today(
                block["id"], ts.strftime("%Y-%m-%d"), store)

        return {
            "ok": True,
            "store": str(_rq.state_dir(store)),
            "modes_enabled": sorted(_rq.SHIPPABLE_MODES),
            "hard_ceiling": _sentinel.REPLY_HARD_CEILING_PER_ACCOUNT_PER_DAY,
            "summary": _rq.summary(store),
            "accounts": sorted(accounts.values(), key=lambda a: a["id"]),
            "expired_now": killed,
            "released_now": released,
            "note": (
                "Replies never post from this repo. At M0 nothing exports; at M1 "
                "items you approve are handed to the desktop session, which is the "
                "only sender. See docs/reply_desk_runbook.md."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.reply_queue failed: %s", exc)
        return {"ok": False, "error": str(exc), "accounts": [], "summary": {}}


def decide_reply(item_id: str, decision: str, note: str | None = None,
                 root=None, *, store=None) -> dict:
    """Approve or hold one reply draft.

    Approve moves the item to `approved`; at M1 the next export tick hands it to
    the desktop session. Hold is a no-op transition that records the operator
    looked and chose not to send yet, keeping the item in the rail.
    """
    try:
        from engine.marketing import reply_queue as _rq  # noqa: PLC0415

        iid = str(item_id or "").strip()
        if not iid:
            return {"ok": False, "error": "id required"}
        if decision not in {"approve", "hold"}:
            return {"ok": False, "error": "decision must be 'approve' or 'hold'"}

        state = _rq.fold_state(store)
        if iid not in state["items"]:
            return {"ok": False, "error": "unknown item id"}

        if decision == "hold":
            logged = _rq.hold(iid, actor="admin", root=store, note=note)
            return {"ok": True, "id": iid, "decision": "hold",
                    "status": state["status"].get(iid), "logged": bool(logged),
                    "note": "held in the rail; approve when the read is right"}

        ok = _rq.approve(iid, root=store, note=note)
        if not ok:
            return {"ok": False,
                    "error": f"cannot approve an item that is "
                             f"{state['status'].get(iid)!r}"}
        return {"ok": True, "id": iid, "decision": "approve", "status": "approved"}
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.decide_reply failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def reject_reply(item_id: str, reason: str | None = None, root=None, *, store=None) -> dict:
    """REJECT one reply draft, with a reason.

    Rejections are the taste corpus: they are the only signal that says what this
    desk should sound like. Rejecting also RELEASES the thread's one-owner lock,
    so a sibling desk may legitimately take a conversation this one declined.
    """
    try:
        from engine.marketing import reply_queue as _rq  # noqa: PLC0415

        iid = str(item_id or "").strip()
        if not iid:
            return {"ok": False, "error": "id required"}

        state = _rq.fold_state(store)
        item = state["items"].get(iid)
        if item is None:
            return {"ok": False, "error": "unknown item id"}
        status = state["status"].get(iid, "queued")

        if not _rq.reject(iid, root=store, reason=reason):
            return {"ok": False,
                    "error": f"cannot reject an item that is {status!r}",
                    "note": "sent, rejected and expired items are terminal"}

        # Feedback is best-effort and deliberately AFTER the kill: a failure to
        # record the reason must never leave a bad draft still approvable.
        #
        # It lands in the reply desk's OWN corpus in host state, not
        # data/marketing/rejections.jsonl — the operator doing this runs the
        # admin on the M1, which is the nightly render host, so an intraday
        # write into the checkout is exactly what this desk is built to avoid.
        row = False
        try:
            row = _rq.record_rejection(item, reason=reason, actor="admin", root=store)
        except Exception as rexc:  # noqa: BLE001
            log.warning("marketing.reject_reply: feedback row failed: %s", rexc)

        return {"ok": True, "id": iid, "rejected": True, "logged": bool(row),
                "thread_released": True,
                "note": None if row else
                        "rejected, but the feedback row could not be written"}
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.reject_reply failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Learning + account health (XG-W6)
#
# The operator console half of the ONE feedback loop. Three panels:
#
#   learning_scorecard()  the weekly hook x format x register x account grid,
#                         the cold-start bottleneck table, and the learned-rule
#                         VERSION LOG shipped alongside it (charter §8).
#   account_health()      per-account health cards, the network tripwire verdict,
#                         the halt registry, and the blind-identity eval's
#                         pre-registration (status: not_run — it gates nothing).
#   clear_halt()          the operator's ONLY way to end a halt. The monitor
#                         cannot clear its own trip.
#
# NOTHING ON THESE PANELS IS USER-FACING. No score, label, health verdict or
# halt reason appears anywhere in site/; these are admin-console reads.
# ---------------------------------------------------------------------------

_HALTS_REL = Path("data/marketing/learning/halts.json")


def learning_scorecard(root=None) -> dict:
    """The weekly scorecard + the learned-rule version log.

    Fail-soft: a repo with no consolidated labels returns ok:True with an empty
    scorecard and a note. That is the honest cold-start state — the metrics poll
    is dark without BUFFER_TOKEN and the reply desk has sent nothing — not an
    error to surface as a red panel.
    """
    try:
        from engine.marketing import labels as _labels  # noqa: PLC0415
        from engine.marketing import learned_rules as _rules  # noqa: PLC0415

        repo = Path(root) if root is not None else _default_root()
        cfg = _read_yaml(repo / _CONFIG_REL)
        card = _labels.load_scorecard(repo)
        rows = _labels.load_labels(repo)
        return {
            "ok": True,
            "consumers": list(_labels.CONSUMERS),
            "dims": list(_labels.DIMS),
            "scorecard": card,
            "n_labels": len(rows),
            "n_labelled": sum(1 for r in rows if r.get("label") is not None),
            "n_null": sum(1 for r in rows if r.get("label") is None),
            "rules": {
                "enabled": _rules.enabled(cfg),
                "active": _rules.active(repo),
                # The version log ships ALONGSIDE the scorecards (charter §8) — a
                # rule whose history you cannot see is a rule you cannot argue
                # with. Newest first for the panel.
                "log": list(reversed(_rules.history(repo)))[:100],
            },
            "note": (
                "Operator console only. No score or label here is user-facing. "
                "Cells below the n-floor read 'seeding' and make no ranking claim."
                if card else
                "No labels consolidated yet — the metrics poll is dark without "
                "BUFFER_TOKEN and the reply desk has sent nothing. Empty is the "
                "honest state, not a failure."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.learning_scorecard failed: %s", exc)
        return {"ok": False, "error": str(exc), "scorecard": {}, "rules": {}}


def account_health(root=None, *, store=None) -> dict:
    """Per-account health cards + network tripwire + the halt registry.

    Read-only: this NEVER trips or clears a halt. Opening a panel must not be
    able to silence a desk, and it must not be able to un-silence one either —
    the nightly trips, the operator clears, and the panel only shows.
    """
    try:
        from engine.marketing import blind_identity as _bie  # noqa: PLC0415
        from engine.marketing import health_monitor as _hm  # noqa: PLC0415

        repo = Path(root) if root is not None else _default_root()
        report = _hm.load_health(repo)
        halts = _hm.load_halts(repo)
        return {
            "ok": True,
            "metrics": list(_hm.METRICS),
            "tripwires": list(_hm.TRIPWIRES),
            "health": report,
            "halted": [
                {"account": acc, **{k: v for k, v in rec.items() if k != "evidence"}}
                for acc, rec in sorted(halts.items())
            ],
            "halt_count": len(halts),
            # Pre-registered, NOT RUN, and gating nothing. Surfaced so the panel
            # never implies a >=80% number is enforcing something.
            "blind_identity": {
                "prereg_id": _bie.PREREG["id"],
                "status": _bie.PREREG["status"],
                "chance_baseline": _bie.CHANCE_BASELINE,
                "charter_target": _bie.PREREG["charter_target"],
                "gates_nothing": _bie.GATES_NOTHING,
                "doc": "docs/blind_identity_eval_prereg.md",
            },
            "note": (
                "A halted account is blocked on BOTH rails (posts and replies) and "
                "every other desk keeps running. Only an operator can clear a halt."
                if halts else
                "No account is halted. Health verdicts here are surfaced, not "
                "enforced — account_action defaults to 'warn'."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.account_health failed: %s", exc)
        return {"ok": False, "error": str(exc), "health": {}, "halted": []}


def clear_halt(account_id: str, actor: str = "admin", note=None, root=None,
               push: bool = True) -> dict:
    """Operator-clear ONE halted account. The only way a halt ends.

    Same persistence posture as ``accounts_toggle``: the halt registry is a
    TRACKED file because both rails must see it and they run on different
    machines, so a deployed admin commits through the GitHub Contents API and a
    local checkout commits+pushes the one file. A clear that never reaches main
    is undone by the VPS's next pull, so an unpushed clear reports honestly
    instead of looking successful.
    """
    try:
        from datetime import datetime, timezone  # noqa: PLC0415

        from engine.marketing import health_monitor as _hm  # noqa: PLC0415

        aid = str(account_id or "").strip()[:100]
        if not aid:
            return {"ok": False, "error": "account_id required"}
        who = str(actor or "").strip()[:100]
        if not who:
            return {"ok": False, "error": "actor required — a cleared halt needs an owner"}

        repo = Path(root) if root is not None else _default_root()
        from . import settings  # noqa: PLC0415
        if settings.deployed():
            return _clear_halt_via_api(aid, who, note)

        res = _hm.clear(aid, actor=who, now=datetime.now(timezone.utc),
                        note=note, root=repo)
        if not res.get("ok"):
            return res

        if push:
            try:
                from . import gitops  # noqa: PLC0415
                git_res = gitops.commit_paths(
                    [str(_HALTS_REL).replace("\\", "/")],
                    message=f"admin: clear halt on {aid} (by {who})",
                    push=True, confirm=True)
                res["pushed"] = bool(git_res.get("pushed"))
                res["git"] = git_res
                res["note"] = (
                    f"Halt on {aid} cleared and pushed. Both rails see it on the "
                    "next pull."
                    if git_res.get("pushed") else
                    "Halt cleared LOCALLY ONLY. Until this file reaches main the "
                    "VPS's next pull will restore the halt — "
                    + str(git_res.get("warning") or git_res.get("error")
                          or "push not available from this checkout") + "."
                )
            except Exception as gexc:  # noqa: BLE001
                res["pushed"] = False
                res["note"] = ("Halt cleared locally; the commit/push step failed "
                               f"({gexc}). The next pull will restore it.")
        else:
            res["pushed"] = False
            res["note"] = "Halt cleared locally (push skipped)."
        return res
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.clear_halt failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _clear_halt_via_api(aid: str, actor: str, note) -> dict:
    """Deployed-mode halt clear: read the registry off main, clear ONE account,
    commit it straight back. Read-modify-write against the ON-MAIN copy, so
    clearing one desk never resurrects or drops another desk's halt."""
    from datetime import datetime, timezone  # noqa: PLC0415

    from . import github_api  # noqa: PLC0415

    rel = str(_HALTS_REL).replace("\\", "/")
    gf = github_api.get_file(rel)
    if not gf.get("ok"):
        return {"ok": False, "error": f"could not read {rel} on main: {gf.get('error')}"}
    blob: dict = {}
    if gf.get("content"):
        try:
            parsed = json.loads(gf["content"])
            if isinstance(parsed, dict):
                blob = parsed
        except Exception:  # noqa: BLE001
            blob = {}
    accounts = blob.get("accounts")
    if not isinstance(accounts, dict) or not isinstance(accounts.get(aid), dict):
        return {"ok": False, "error": "not_halted", "account": aid}
    if accounts[aid].get("state") != "halted":
        return {"ok": False, "error": "not_halted", "account": aid}

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    accounts[aid] = {**accounts[aid], "state": "cleared", "cleared_at": ts,
                     "cleared_by": actor,
                     "clear_note": (str(note).strip()[:500] if note else None)}
    blob["accounts"] = accounts
    blob["log"] = (blob.get("log") or [])[-199:] + [
        {"at": ts, "account": aid, "action": "clear", "actor": actor, "note": note}
    ]
    pf = github_api.put_file(
        rel,
        json.dumps(blob, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        f"admin: clear halt on {aid} (by {actor})", sha=gf.get("sha"))
    if not pf.get("ok"):
        return {"ok": False, "error": f"commit failed: {pf.get('error')}"}
    return {"ok": True, "account": aid, "state": "cleared", "cleared_at": ts,
            "pushed": True, "via": "github_api", "commit_sha": pf.get("commit_sha"),
            "note": f"Halt on {aid} cleared on main. Both rails see it on the next pull."}


_RULES_ACTIVE_REL = Path("data/marketing/learning/rules_active.json")


def rollback_learned_rule(version_id: str, actor: str = "admin", root=None,
                          push: bool = True) -> dict:
    """Undo one applied learned rule. The rollback path charter §8 requires.

    Same persistence posture as ``clear_halt``, and for the same reason: the
    learned-rule store is a TRACKED file on a checkout the VPS ``git pull``s
    every three minutes, so a rollback written locally and never pushed is
    simply undone. Worse than the halt case — the store is nightly-advanced, so
    an unpushed rollback is RE-APPLIED rather than merely reverted.

    Deployed admin therefore commits through the GitHub Contents API; a local
    checkout commits+pushes the one file; and a rollback that did not reach main
    says so instead of reporting a success it did not achieve.
    """
    try:
        from datetime import datetime, timezone  # noqa: PLC0415

        from engine.marketing import learned_rules as _rules  # noqa: PLC0415

        vid = str(version_id or "").strip()
        if not vid:
            return {"ok": False, "error": "version_id required"}
        who = str(actor or "").strip()[:100] or "admin"
        repo = Path(root) if root is not None else _default_root()

        from . import settings  # noqa: PLC0415
        if settings.deployed():
            return _rollback_rule_via_api(vid, who)

        res = _rules.rollback(vid, now=datetime.now(timezone.utc), root=repo, actor=who)
        if not res.get("ok"):
            return res

        if push:
            try:
                from . import gitops  # noqa: PLC0415
                git_res = gitops.commit_paths(
                    [str(_RULES_ACTIVE_REL).replace("\\", "/"),
                     "data/marketing/learning/rules_log.jsonl"],
                    message=f"admin: roll back learned rule {vid} (by {who})",
                    push=True, confirm=True)
                res["pushed"] = bool(git_res.get("pushed"))
                res["git"] = git_res
                res["note"] = (
                    "Rolled back and pushed."
                    if git_res.get("pushed") else
                    "Rolled back LOCALLY ONLY. The store is nightly-advanced, so "
                    "until this reaches main the next nightly RE-APPLIES the rule — "
                    + str(git_res.get("warning") or git_res.get("error")
                          or "push not available from this checkout") + "."
                )
            except Exception as gexc:  # noqa: BLE001
                res["pushed"] = False
                res["note"] = ("Rolled back locally; the commit/push step failed "
                               f"({gexc}). The next nightly will re-apply the rule.")
        else:
            res["pushed"] = False
            res["note"] = "Rolled back locally (push skipped)."
        return res
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.rollback_learned_rule failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _rollback_rule_via_api(vid: str, actor: str) -> dict:
    """Deployed-mode rollback: read rules_active.json off main, undo ONE
    version, commit it straight back. Read-modify-write against the ON-MAIN
    copy so a rollback never drops another path's rule."""
    from datetime import datetime, timezone  # noqa: PLC0415

    from . import github_api  # noqa: PLC0415

    rel = str(_RULES_ACTIVE_REL).replace("\\", "/")
    gf = github_api.get_file(rel)
    if not gf.get("ok"):
        return {"ok": False, "error": f"could not read {rel} on main: {gf.get('error')}"}
    blob: dict = {}
    if gf.get("content"):
        try:
            parsed = json.loads(gf["content"])
            if isinstance(parsed, dict):
                blob = parsed
        except Exception:  # noqa: BLE001
            blob = {}
    rules = blob.get("rules")
    if not isinstance(rules, dict):
        return {"ok": False, "error": "unknown_or_inactive_version", "version_id": vid}

    match = next(((k, v) for k, v in rules.items()
                  if isinstance(v, dict) and str(v.get("version_id")) == vid), None)
    if match is None:
        return {"ok": False, "error": "unknown_or_inactive_version", "version_id": vid}

    key, entry = match
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    revert = entry.get("revert") or {}
    if revert.get("present"):
        # Re-apply the previous value AS A RULE, so the active set stays a
        # complete description of current state and remains rollback-able.
        rules[key] = {**entry, "value": revert.get("value"),
                      "revert": {"present": True, "value": entry.get("value")},
                      "state": "active", "applied_at": ts, "applied_by": actor,
                      "rolled_back_from": vid}
        outcome = {"path": key, "action": "restored", "value": revert.get("value")}
    else:
        rules.pop(key, None)
        outcome = {"path": key, "action": "deleted", "value": None}
    blob["rules"] = rules
    blob["updated_at"] = ts

    pf = github_api.put_file(
        rel, json.dumps(blob, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        f"admin: roll back learned rule {vid} (by {actor})", sha=gf.get("sha"))
    if not pf.get("ok"):
        return {"ok": False, "error": f"commit failed: {pf.get('error')}"}
    return {"ok": True, "version_id": vid, "restored": outcome, "pushed": True,
            "via": "github_api", "commit_sha": pf.get("commit_sha"),
            "note": f"Rolled back on main. {key} is now "
                    f"{outcome['action']} for the next nightly."}
