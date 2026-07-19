"""engine.marketing.sentinel — Sentinel (trust_office) W1 plan-level gate.

De-escalate only: drop/quarantine/downgrade items; never originate or upgrade
content. Fully deterministic — no LLM anywhere in this module.

Public API:
    gate_plan(plan, cfg, *, receipts_age_days, graded_window, exceptions)
        -> (annotated_plan, report)                    # pure, no I/O
    run_gate(root, *, plan, cfg, ...) -> report        # loads, gates, writes
    receipts_context(root) -> (age_days, graded_window)
    load_exceptions(root) -> {item_id: row}
    publish_enabled() -> bool                          # global kill-switch
    mark_all_unverified(plan) -> None                  # crash-path stamp
    error_report(as_of=..., exc=...) -> dict           # fail-closed report shape
    write_report(root, report) -> Path
    reason_class(reason) -> "policy" | "overflow"

Reason classes: every quarantine reason is either
  * "overflow" — a capacity trim (daily/media/cashtag/slot caps). The content
    plan deliberately over-generates; the gate keeping the postable N is
    expected every night and needs no human attention.
  * "policy"   — a real ban-risk or content flag (lexicon, near-dup, shared
    media, disclosure, links, cherry-pick, stale receipts, disabled account).
    These are what the operator reviews.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths (relative to repo root)
# ---------------------------------------------------------------------------
_CONTENT_PLAN_REL = Path("data") / "marketing" / "content_plan.json"
_SENTINEL_REPORT_REL = Path("data") / "marketing" / "sentinel_report.json"
_EXCEPTIONS_REL = Path("data") / "marketing" / "sentinel_exceptions.jsonl"
_CONFIG_REL = Path("config") / "marketing.yml"
_PROPHET_INDEX_REL = Path("site") / "prophet" / "index.json"

# ---------------------------------------------------------------------------
# Kill-switch
# ---------------------------------------------------------------------------

def publish_enabled() -> bool:
    """Global kill-switch.

    Returns True only if env MARKETING_PUBLISH_ENABLED is in
    {"1", "true", "yes"} (case-insensitive). Default False.
    The D02 actuator must check this per item before publishing.
    """
    val = os.environ.get("MARKETING_PUBLISH_ENABLED", "").strip().lower()
    return val in {"1", "true", "yes"}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCHEMA_VERSION = 1

# Conservative in-code defaults (all knobs are also in config/marketing.yml sentinel:)
# Base = weeks_1_2 tier: W1 has no account-age wiring, so defaults assume brand-new
# accounts. D02 actuator RAISES caps by ramp tier, never lowers. A drift-guard test
# asserts these match config/marketing.yml sentinel:.
_DEFAULT_NEAR_DUP_JACCARD = 0.50              # "substantially similar" policy bar
_DEFAULT_MAX_POSTS_PER_ACCOUNT_PER_DAY = 2    # weeks_1_2 floor
_DEFAULT_MIN_MINUTES_BETWEEN_POSTS = 120       # NOT enforced at plan tier (slots have
                                               # no timestamps); contract value the D02
                                               # actuator must read from sentinel config.
                                               # weeks_1_2 = 120; relax to 90 at week 5+.
_DEFAULT_MAX_SAME_CASHTAG_PER_ACCOUNT_PER_DAY = 1  # weeks_1_2 floor
_DEFAULT_MAX_REPLIES_PER_ACCOUNT_PER_DAY = 0
_DEFAULT_MAX_RECEIPT_AGE_DAYS = 7
_DEFAULT_LINKS_ALLOWED = False                 # forbidden until week 5 (D08 R2)
_DEFAULT_MAX_MEDIA_POSTS_PER_ACCOUNT_PER_DAY = 1   # weeks_1_2 floor (D08 R4)
_DEFAULT_MAX_CASHTAGS_PER_POST = 3             # per-post breadth cap (D08 R3)
_DEFAULT_MAX_NEW_FOLLOWS_PER_ACCOUNT_PER_DAY = 0   # follow churn = fastest ban trigger (D08 R7)

# Financial-advice lexicon — defense-in-depth at the plan layer.
# Some overlap with copywriter._BANNED_VOCAB is intentional (different layers).

# Mirrors the copywriter disclosure check (validate_copy §6) — keep the anchor
# SET in sync, but sentinel matches single-word tokens with \b word boundaries
# where copywriter substring-matches. That asymmetry is deliberate: copywriter's
# substring match accepts "grade" inside "upgraded"; the plan-level gate must not.
_DISCLOSURE_PHRASES_MULTI: tuple[str, ...] = (
    "size appropriately",
    "not financial advice",
    "not a guarantee",
    "do your own",
    "position sizing",
    "track it",
    "what would change",
)
_DISCLOSURE_PATTERNS_SINGLE: tuple[re.Pattern, ...] = tuple(
    re.compile(r"\b" + word + r"\b", re.IGNORECASE)
    for word in ("historical", "publicly", "grade", "receipt")
)

_DEFAULT_LEXICON_PHRASES: list[str] = [
    "you should buy",
    "you should sell",
    "get in now",
    "get in before",
    "guaranteed",
    "can't lose",
    "cannot lose",
    "sure thing",
    "easy money",
    "risk-free",
    "risk free",
    "free money",
    "no-brainer",
    "back up the truck",
    "load up",
    "all-in",
    "to the moon",
    "price target guaranteed",
]

_DEFAULT_LEXICON_PATTERNS: list[str] = [
    r"\b(will|going to|gonna)\s+(hit|reach|touch|double|triple|10x)\b",
    r"\bcan'?t\s+(go|drop|fall)\b",
]

# Item types considered "receipt" for stale-receipts logic
_RECEIPT_TYPES: frozenset[str] = frozenset({"receipt"})

# Reasons the operator exception queue can NEVER override.
_ALWAYS_ENFORCED: frozenset[str] = frozenset({"account_disabled", "stale_receipts_ledger"})

# Capacity-trim reason heads (everything else is a policy flag).
_OVERFLOW_REASON_HEADS: frozenset[str] = frozenset({
    "cadence_cap_daily",
    "reply_cap_daily",
    "media_cap_daily",
    "cashtag_cap",
    "slot_collision",
})


def reason_class(reason: str) -> str:
    """Classify a quarantine reason: "overflow" (capacity trim) or "policy" (real flag)."""
    head = reason.split(":", 1)[0]
    return "overflow" if head in _OVERFLOW_REASON_HEADS else "policy"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _write_json_atomic(path: Path, obj: dict) -> None:
    """Atomic write via temp file in the same directory (same pattern as governor)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, prefix=".tmp_sentinel_", suffix=".json"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise


def write_report(root: Path | str | None, report: dict) -> Path:
    """Atomically write the sentinel report to its canonical path. Returns the path."""
    path = _repo_root(root) / _SENTINEL_REPORT_REL
    _write_json_atomic(path, report)
    return path


def _token_set(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"\w+", text.lower()))


def _jaccard_sets(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _item_text(item: dict) -> str:
    headline = str(item.get("headline") or "")
    body = str(item.get("body") or "")
    return f"{headline} {body}"


def _cfg_sentinel(cfg: dict) -> dict:
    """Extract the sentinel config block, falling back to an empty dict."""
    return (cfg.get("sentinel") or {}) if isinstance(cfg, dict) else {}


def _get(block: dict, key: str, default: Any) -> Any:
    v = block.get(key)
    return v if v is not None else default


def _cap(block: dict, key: str, default: int) -> int:
    """Read a non-negative integer cap knob (bad values fall back to default)."""
    try:
        return max(0, int(_get(block, key, default)))
    except (TypeError, ValueError):
        return default


def load_exceptions(root: Path | str | None = None) -> dict[str, dict]:
    """Load sentinel_exceptions.jsonl → {item_id: row}. Missing file = empty.

    Rows are operator allow-exceptions: {"item_id": ..., "allow": true, "reason": ...}.
    Later lines win for the same item_id.
    """
    path = _repo_root(root) / _EXCEPTIONS_REL
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            iid = row.get("item_id")
            if iid and row.get("allow"):
                out[str(iid)] = row
    except Exception as exc:  # noqa: BLE001
        log.warning("sentinel: failed to load exceptions: %s", exc)
    return out


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mark_all_unverified(plan: dict) -> None:
    """Stamp every queue item in plan with sentinel_ok=False in-place.

    Crash-path helper: called by the governor before writing a raw plan so an
    ungated plan is never written without a clear sentinel_ok=False signal.
    De-escalate-only invariant: only sets False (never upgrades to True).
    """
    for acc in (plan.get("accounts") or []):
        for item in (acc.get("queue") or []):
            if not item.get("sentinel_ok"):
                item["sentinel_ok"] = False


def error_report(*, as_of: str = "", exc: BaseException | str = "") -> dict:
    """The fail-closed report written when the gate itself crashed.

    plan_status "error" tells every consumer (admin, D02 actuator) that the
    plan is UNGATED and must not be published.
    """
    return {
        "schema_version": _SCHEMA_VERSION,
        "produced_by": "sentinel",
        "produced_at": _now_utc(),
        "as_of": as_of,
        "plan_status": "error",
        "publish_enabled": publish_enabled(),
        "auditor_strict": True,
        "counts": {
            "items": 0, "passed": 0, "quarantined": 0,
            "quarantined_policy": 0, "quarantined_overflow": 0,
            "warnings": 0, "exceptions_applied": 0,
        },
        "reasons_histogram": {},
        "quarantined": [],
        "checks": {},
        "notes": [f"sentinel gate raised: {exc}"],
    }


def _has_disclosure(text: str) -> bool:
    """True if text contains any required disclosure anchor.

    Multi-word anchors: substring match (no false-positive superstrings exist).
    Single-word tokens: word-boundary match (guards against "upgraded"→"grade",
    "historically"→"historical", etc.). Mirrors validate_copy §6 — keep the
    anchor set in sync.
    """
    lower = text.lower()
    if any(phrase in lower for phrase in _DISCLOSURE_PHRASES_MULTI):
        return True
    return any(p.search(lower) for p in _DISCLOSURE_PATTERNS_SINGLE)


def receipts_context(root: Path | str | None = None) -> tuple[int | None, list[dict] | None]:
    """Derive (receipts_age_days, graded_window) from the Prophet index.

    Single read of site/prophet/index.json.

    receipts_age_days = age in days of the NEWEST _signal_date across plans
    (None when unavailable — the gate then quarantines receipt items only,
    printed honestly in the report).

    graded_window = the full graded outcome set for the same window via
    receipt_source.graded_receipts, as [{"ticker", "outcome"}] (None when
    uncomputable — the gate skips cherry-pick, printed honestly).
    """
    r = _repo_root(root)
    try:
        idx = json.loads((r / _PROPHET_INDEX_REL).read_text(encoding="utf-8"))
        plans = idx.get("plans") or []
    except Exception as exc:  # noqa: BLE001
        log.warning("sentinel.receipts_context: prophet index unreadable: %s", exc)
        return None, None

    today = datetime.now(timezone.utc).date()
    ages: list[int] = []
    for p in plans:
        sd = str(p.get("_signal_date") or "")[:10]
        if not sd:
            continue
        try:
            days = (today - date.fromisoformat(sd)).days
        except ValueError:
            continue
        # Future-dated signals are corrupt data — skipping them fails closed
        # (a negative age would make the ledger read fresher than reality).
        if days >= 0:
            ages.append(days)
    age_days = min(ages) if ages else None

    graded_window: list[dict] | None = None
    try:
        from engine.marketing.chart_render import load_closes  # noqa: PLC0415
        from engine.marketing.receipt_source import graded_receipts  # noqa: PLC0415
        graded = graded_receipts(
            plans,
            closes_loader=lambda t: load_closes(t, r, n=90),
            today=today.isoformat(),
        )
        graded_window = [{"ticker": g["ticker"], "outcome": g["kind"]} for g in graded]
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "sentinel.receipts_context: graded window uncomputable — cherry-pick will be skipped: %s",
            exc,
        )
    return age_days, graded_window


# ---------------------------------------------------------------------------
# Core gate logic
# ---------------------------------------------------------------------------

def gate_plan(
    plan: dict,
    cfg: dict,
    *,
    receipts_age_days: int | float | None = None,
    graded_window: list[dict] | None = None,
    exceptions: dict[str, dict] | None = None,
) -> tuple[dict, dict]:
    """Pure gate: returns (annotated_plan, report).

    Mutation only ever de-escalates:
    - items may be quarantined (status → "quarantined", sentinel_ok → False)
    - passing items get sentinel_ok → True annotated
    - item type/headline/body are NEVER modified
    - no new items are originated

    Check sequencing (quarantine-aware — dead items consume no slots):
    1. Content-level checks (lexicon, disclosure, link rule, cashtag breadth)
       — item-intrinsic, order-independent. ALL hits are recorded, not just
       the first (the operator sees the full reason list).
    2. Always-enforced classes (account_disabled, stale-receipts refusal).
    3. Exceptions pass — restores eligible check-violations. Never restores
       an item carrying an always-enforced reason.
    4. Near-dup + shared-media across accounts, over items still alive after
       steps 1–3 (a pair with a dead side is not coordinated posting).
       First-alive-in-plan-order survives. If a near-dup survivor is later
       cap-killed in step 5 the dropped dup stays dropped — deliberate
       conservatism: near-identical content queued the same day is drop-worthy
       regardless (docket: "rewrite-or-drop the later item").
    5. Caps (daily, reply, same-cashtag, slot collision, media) counting ONLY
       still-alive items, in queue order. Check-then-commit: an item that
       fails any cap consumes NO slots at all.
    6. Final exceptions pass for step-4/5 violations (an operator allow may
       exceed a cap — human override by design). Net effect: an item with an
       allow-exception stays quarantined ONLY if it carries an always-enforced
       reason.
    """
    plan = copy.deepcopy(plan)

    sc = _cfg_sentinel(cfg)
    settings = (cfg.get("settings") or {}) if isinstance(cfg, dict) else {}
    strict: bool = bool(_get(settings, "auditor_strict", True))
    exceptions = exceptions or {}

    as_of = plan.get("as_of", "")

    # Disabled account ids from desk_network (per-account kill-switch)
    desk_net = (cfg.get("desk_network") or {}) if isinstance(cfg, dict) else {}
    disabled_accounts: list[str] = [
        str(acc.get("id", ""))
        for acc in (desk_net.get("accounts") or [])
        if acc.get("disabled")
    ]

    # Flat item list: (account_id, item_dict, account_index, queue_index)
    all_items: list[tuple[str, dict, int, int]] = []
    for ai, acc in enumerate(plan.get("accounts") or []):
        acc_id = str(acc.get("id", ""))
        for qi, item in enumerate(acc.get("queue") or []):
            all_items.append((acc_id, item, ai, qi))

    # --- knobs ---------------------------------------------------------------
    near_dup_thresh = float(_get(sc, "near_dup_jaccard", _DEFAULT_NEAR_DUP_JACCARD))
    max_posts_day = _cap(sc, "max_posts_per_account_per_day", _DEFAULT_MAX_POSTS_PER_ACCOUNT_PER_DAY)
    max_same_cashtag = _cap(sc, "max_same_cashtag_per_account_per_day", _DEFAULT_MAX_SAME_CASHTAG_PER_ACCOUNT_PER_DAY)
    max_replies_day = _cap(sc, "max_replies_per_account_per_day", _DEFAULT_MAX_REPLIES_PER_ACCOUNT_PER_DAY)
    max_receipt_age = _cap(sc, "max_receipt_age_days", _DEFAULT_MAX_RECEIPT_AGE_DAYS)
    links_allowed = bool(_get(sc, "links_allowed", _DEFAULT_LINKS_ALLOWED))
    max_media_posts_day = _cap(sc, "max_media_posts_per_account_per_day", _DEFAULT_MAX_MEDIA_POSTS_PER_ACCOUNT_PER_DAY)
    max_cashtags_per_post = _cap(sc, "max_cashtags_per_post", _DEFAULT_MAX_CASHTAGS_PER_POST)
    lexicon_phrases = list(_get(sc, "lexicon_phrases", _DEFAULT_LEXICON_PHRASES))
    lexicon_patterns = list(_get(sc, "lexicon_patterns", _DEFAULT_LEXICON_PATTERNS))

    # Per-item violation accumulator {(ai, qi): list[str]}
    violations: dict[tuple[int, int], list[str]] = defaultdict(list)
    notes: list[str] = []

    # =========================================================================
    # STEP 1: Content-level checks (item-intrinsic, order-independent)
    # =========================================================================

    # --- financial-advice lexicon: record EVERY hit --------------------------
    phrase_res = [
        (phrase, re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE))
        for phrase in lexicon_phrases
    ]
    pattern_res = [re.compile(p, re.IGNORECASE) for p in lexicon_patterns]
    lexicon_hits = 0

    for _acc_id, item, ai, qi in all_items:
        text = _item_text(item)
        hits = [f"advice_lexicon:{phrase}" for phrase, cre in phrase_res if cre.search(text)]
        for cre in pattern_res:
            m = cre.search(text)
            if m:
                hits.append(f"advice_lexicon:{m.group(0)}")
        if hits:
            violations[(ai, qi)].extend(hits)
            lexicon_hits += len(hits)

    # --- disclosure law (signal items) ---------------------------------------
    disclosure_hits = 0
    for _acc_id, item, ai, qi in all_items:
        if item.get("type") != "signal":
            continue
        if not _has_disclosure(_item_text(item)):
            violations[(ai, qi)].append("missing_disclosure")
            disclosure_hits += 1

    # --- link rule -----------------------------------------------------------
    link_re = re.compile(r"https?://|\bt\.co/", re.IGNORECASE)
    link_hits = 0
    if not links_allowed:
        for _acc_id, item, ai, qi in all_items:
            if link_re.search(_item_text(item)):
                violations[(ai, qi)].append("link_not_allowed")
                link_hits += 1

    # --- cashtag breadth (per post) ------------------------------------------
    # Distinct $TICKER tokens in headline+body (case-sensitive: real cashtags are
    # uppercase; "$oil" is prose, "$200" is a price — neither matches).
    # theme_list is exempt: validate_copy requires ≥4 member cashtags there by
    # format. Tension: memo §2 R3 flags multi-cashtag lists as the piggybacking
    # heuristic; revisit when theme_list volume is measurable.
    cashtag_re = re.compile(r"\$[A-Z]{1,5}(?:\.[A-Z]{1,2})?\b")
    cashtag_breadth_hits = 0
    for _acc_id, item, ai, qi in all_items:
        if item.get("type") == "theme_list":
            continue
        distinct = set(cashtag_re.findall(_item_text(item)))
        if len(distinct) > max_cashtags_per_post:
            violations[(ai, qi)].append("cashtag_breadth")
            cashtag_breadth_hits += 1

    # =========================================================================
    # STEP 2: Always-enforced classes (never exception-overridable)
    # =========================================================================

    for acc_id, _item, ai, qi in all_items:
        if acc_id in disabled_accounts:
            violations[(ai, qi)].append("account_disabled")

    plan_refused = False
    receipts_age_check: dict[str, Any] = {
        "age_days": None if receipts_age_days is None else int(receipts_age_days),
        "max": max_receipt_age,
    }
    if receipts_age_days is None:
        # Unknown age → we cannot back receipts; quarantine receipt items only.
        for _acc_id, item, ai, qi in all_items:
            if item.get("type") in _RECEIPT_TYPES:
                violations[(ai, qi)].append("receipts_age_unknown")
        notes.append("receipts ledger age unknown — receipt items quarantined")
    elif receipts_age_days > max_receipt_age:
        plan_refused = True
        for _acc_id, _item, ai, qi in all_items:
            violations[(ai, qi)].append("stale_receipts_ledger")
        notes.append(
            f"plan refused: graded-receipts ledger stale "
            f"({int(receipts_age_days)}d > {max_receipt_age}d)"
        )

    # =========================================================================
    # STEP 3 / STEP 6: exceptions passes
    # =========================================================================

    exception_restored_ids: set[str] = set()

    def _apply_exceptions() -> None:
        """Restore items with an operator allow-exception.

        Never restores an item carrying an always-enforced reason. Restored
        item ids are tracked in a set so the report counts each item once even
        if it is restored in both passes.
        """
        for _acc_id, item, ai, qi in all_items:
            key = (ai, qi)
            if not violations[key]:
                continue
            iid = str(item.get("id") or "")
            row = exceptions.get(iid)
            if row is None:
                continue
            if any(r in _ALWAYS_ENFORCED for r in violations[key]):
                continue
            violations[key] = []
            item["exception_applied"] = row.get("reason", "human override")
            exception_restored_ids.add(iid)

    _apply_exceptions()  # step 3: content-level restorations before structural checks

    # =========================================================================
    # STEP 4: Near-dup + shared-media across accounts (alive items only)
    # =========================================================================

    near_dup_pairs_checked = 0
    near_dup_hits = 0
    shared_media_hits = 0

    # Alive survivors so far: (account_id, item_id, token_set)
    surviving_cross: list[tuple[str, str, frozenset[str]]] = []
    chart_id_seen: dict[str, str] = {}  # chart_id → first alive account_id

    for acc_id, item, ai, qi in all_items:
        key = (ai, qi)
        if violations[key]:
            continue  # dead items are not coordinated posting

        chart_id = item.get("chart_id")
        if chart_id:
            first_acc = chart_id_seen.get(chart_id)
            if first_acc is not None and first_acc != acc_id:
                violations[key].append(f"shared_media:{chart_id}")
                shared_media_hits += 1
                continue
            chart_id_seen.setdefault(chart_id, acc_id)

        item_id = str(item.get("id") or f"{acc_id}/{qi}")
        tokens = _token_set(_item_text(item))
        dup_of: str | None = None
        for prev_acc, prev_id, prev_tokens in surviving_cross:
            if prev_acc == acc_id:
                continue  # same-account dups are copywriter's job
            near_dup_pairs_checked += 1
            if _jaccard_sets(tokens, prev_tokens) >= near_dup_thresh:
                dup_of = prev_id
                break
        if dup_of is not None:
            violations[key].append(f"near_dup:{dup_of}")
            near_dup_hits += 1
        else:
            surviving_cross.append((acc_id, item_id, tokens))

    # =========================================================================
    # STEP 5: Caps — check-then-commit over alive items, in queue order
    # =========================================================================

    posts_by_account: dict[str, int] = defaultdict(int)
    cashtag_by_account: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    slot_by_account: dict[str, set[str]] = defaultdict(set)
    replies_by_account: dict[str, int] = defaultdict(int)
    media_by_account: dict[str, int] = defaultdict(int)

    cadence_stats: dict[str, int] = {
        "cadence_cap_daily_hits": 0,
        "cashtag_cap_hits": 0,
        "slot_collision_hits": 0,
        "reply_cap_hits": 0,
    }
    media_cap_hits = 0

    for acc_id, item, ai, qi in all_items:
        key = (ai, qi)
        if violations[key]:
            continue  # dead items consume no slots

        cashtag = str(item.get("cashtag") or "").strip()
        slot = str(item.get("slot") or "").strip()
        is_reply = item.get("type") == "reply"
        has_media = bool(item.get("chart_id"))

        # Decide every cap first; commit counters only if the item survives —
        # a killed item must never waste a slot a clean sibling needed.
        reason: str | None = None
        if has_media and media_by_account[acc_id] >= max_media_posts_day:
            reason = "media_cap_daily"
            media_cap_hits += 1
        elif is_reply and replies_by_account[acc_id] >= max_replies_day:
            reason = "reply_cap_daily"
            cadence_stats["reply_cap_hits"] += 1
        elif posts_by_account[acc_id] >= max_posts_day:
            reason = "cadence_cap_daily"
            cadence_stats["cadence_cap_daily_hits"] += 1
        elif cashtag and cashtag_by_account[acc_id][cashtag] >= max_same_cashtag:
            reason = f"cashtag_cap:{cashtag}"
            cadence_stats["cashtag_cap_hits"] += 1
        elif slot and slot in slot_by_account[acc_id]:
            reason = f"slot_collision:{slot}"
            cadence_stats["slot_collision_hits"] += 1

        if reason is not None:
            violations[key].append(reason)
            continue

        if has_media:
            media_by_account[acc_id] += 1
        if is_reply:
            replies_by_account[acc_id] += 1
        posts_by_account[acc_id] += 1
        if cashtag:
            cashtag_by_account[acc_id][cashtag] += 1
        if slot:
            slot_by_account[acc_id].add(slot)

    # =========================================================================
    # STEP 5b: Cherry-pick detector (alive receipt items vs graded window)
    # =========================================================================
    # PARTIAL detector (W1, documented in the docket status line): fires only
    # when the window has losses and the plan shows win receipts with ZERO of
    # the loss tickers. A plan showing some losers passes.

    cherry_pick: dict[str, Any] = {}
    if graded_window is None:
        cherry_pick["status"] = "skipped"
        notes.append("cherry-pick check skipped — graded window unavailable")
    else:
        cherry_pick["status"] = "run"
        loss_tickers = {
            str(gw.get("ticker") or "").upper()
            for gw in graded_window
            if gw.get("outcome") in {"loss", "mixed"} and gw.get("ticker")
        }
        cherry_pick["loss_tickers_in_window"] = sorted(loss_tickers)
        cherry_pick["cherry_pick_detected"] = False

        if loss_tickers:
            receipt_keys: list[tuple[int, int]] = []
            shown_tickers: set[str] = set()
            for _acc_id, item, ai, qi in all_items:
                if violations[(ai, qi)] or item.get("type") not in _RECEIPT_TYPES:
                    continue
                t = (str(item.get("ticker") or "") or
                     str(item.get("cashtag") or "").lstrip("$")).upper()
                if t:
                    shown_tickers.add(t)
                    receipt_keys.append((ai, qi))
            wins_shown = shown_tickers - loss_tickers
            if wins_shown and not (shown_tickers & loss_tickers):
                for key in receipt_keys:
                    violations[key].append("cherry_pick_suspected")
                cherry_pick["cherry_pick_detected"] = True
                cherry_pick["loss_tickers_missing"] = sorted(loss_tickers)

    _apply_exceptions()  # step 6: operator allow may exceed a cap / clear structural flags

    # =========================================================================
    # Annotate items + build report
    # =========================================================================

    reasons_histogram: dict[str, int] = defaultdict(int)
    quarantined_entries: list[dict] = []
    passed_count = 0
    quarantined_count = 0
    quarantined_policy = 0
    quarantined_overflow = 0
    warnings_items_count = 0  # number of ITEMS carrying warnings (not violation strings)

    def _quarantine(item: dict, acc_id: str, reasons: list[str]) -> None:
        nonlocal quarantined_count, quarantined_policy, quarantined_overflow
        cls = ("policy" if any(reason_class(r) == "policy" for r in reasons)
               else "overflow")
        item["sentinel_ok"] = False
        item["status"] = "quarantined"
        item["sentinel_reasons"] = reasons
        quarantined_count += 1
        if cls == "policy":
            quarantined_policy += 1
        else:
            quarantined_overflow += 1
        for r in reasons:
            reasons_histogram[r.split(":", 1)[0]] += 1
        quarantined_entries.append({
            "id": item.get("id", ""),
            "account": acc_id,
            "slot": item.get("slot", ""),
            "type": item.get("type", ""),
            "cashtag": item.get("cashtag", ""),
            "headline": (item.get("headline") or "")[:120],
            "class": cls,
            "reasons": reasons,
        })

    for acc_id, item, ai, qi in all_items:
        item_violations = violations[(ai, qi)]

        if not item_violations:
            item["sentinel_ok"] = True
            passed_count += 1
            continue

        if strict or plan_refused:
            _quarantine(item, acc_id, item_violations)
            continue

        # Non-strict: always-enforced reasons still quarantine; the rest are warnings.
        hard = [v for v in item_violations if v in _ALWAYS_ENFORCED]
        soft = [v for v in item_violations if v not in _ALWAYS_ENFORCED]
        if hard:
            if soft:
                item["sentinel_warnings"] = soft
            _quarantine(item, acc_id, hard)
        else:
            item["sentinel_ok"] = True
            item["sentinel_warnings"] = soft
            passed_count += 1
            warnings_items_count += 1
            for r in soft:
                reasons_histogram[r.split(":", 1)[0] + "_warning"] += 1

    if plan_refused:
        plan_status = "refused"
    elif not strict and (warnings_items_count > 0 or quarantined_count > 0):
        plan_status = "pass_with_warnings"
    else:
        plan_status = "pass"

    report: dict = {
        "schema_version": _SCHEMA_VERSION,
        "produced_by": "sentinel",
        "produced_at": _now_utc(),
        "as_of": as_of,
        "plan_status": plan_status,
        "publish_enabled": publish_enabled(),
        "auditor_strict": strict,
        "counts": {
            "items": len(all_items),
            "passed": passed_count,
            "quarantined": quarantined_count,
            "quarantined_policy": quarantined_policy,
            "quarantined_overflow": quarantined_overflow,
            "warnings": warnings_items_count,
            "exceptions_applied": len(exception_restored_ids),
        },
        "reasons_histogram": dict(reasons_histogram),
        "quarantined": quarantined_entries,
        "checks": {
            "near_dup": {
                "pairs_checked": near_dup_pairs_checked,
                "hits": near_dup_hits,
                "shared_media_hits": shared_media_hits,
            },
            "cadence": cadence_stats,
            "lexicon": {"hits": lexicon_hits},
            "disclosure": {"hits": disclosure_hits},
            "cherry_pick": cherry_pick,
            "stale_receipts": receipts_age_check,
            "kill_switch": {
                "env": publish_enabled(),
                "accounts_disabled": disabled_accounts,
            },
            "media_cap": {
                "max_media_posts_per_account_per_day": max_media_posts_day,
                "hits": media_cap_hits,
            },
            "cashtag_breadth": {
                "max_cashtags_per_post": max_cashtags_per_post,
                "hits": cashtag_breadth_hits,
            },
            "link_rule": {
                "links_allowed": links_allowed,
                "hits": link_hits,
            },
        },
        "notes": notes,
    }

    return plan, report


# ---------------------------------------------------------------------------
# run_gate: disk I/O wrapper
# ---------------------------------------------------------------------------

def run_gate(
    root: Path | str | None = None,
    *,
    plan: dict | None = None,
    cfg: dict | None = None,
    receipts_age_days: int | float | None = None,
    graded_window: list[dict] | None = None,
) -> dict:
    """Load plan+cfg+exceptions from disk if not given, gate, atomically write
    the annotated plan back to data/marketing/content_plan.json and the report
    to data/marketing/sentinel_report.json.

    Returns the report. Callable from the governor AND from the D01 fastlane.

    FAIL CLOSED: if the plan is unreadable or gate_plan raises, an error report
    is written and the exception re-raised. content_plan.json is never
    overwritten with a fabricated plan.
    """
    r = _repo_root(root)

    if cfg is None:
        try:
            import yaml  # noqa: PLC0415
            with open(r / _CONFIG_REL, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception as exc:  # noqa: BLE001
            # Missing config degrades to the (conservative) in-code defaults.
            log.warning("sentinel.run_gate: could not load cfg: %s", exc)
            cfg = {}

    if plan is None:
        try:
            plan = json.loads((r / _CONTENT_PLAN_REL).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("sentinel.run_gate: content plan unreadable: %s", exc)
            write_report(r, error_report(exc=f"content plan unreadable: {exc}"))
            raise

    try:
        annotated_plan, report = gate_plan(
            plan,
            cfg,
            receipts_age_days=receipts_age_days,
            graded_window=graded_window,
            exceptions=load_exceptions(r),
        )
    except Exception as exc:  # noqa: BLE001
        write_report(r, error_report(as_of=plan.get("as_of", ""), exc=exc))
        raise

    _write_json_atomic(r / _CONTENT_PLAN_REL, annotated_plan)
    write_report(r, report)
    return report
