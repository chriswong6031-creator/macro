"""engine.marketing.sentinel — Sentinel (trust_office) W1 plan-level gate.

De-escalate only: drop/quarantine/downgrade items; never originate or upgrade content.
Fully deterministic — no LLM anywhere in this module.

Public API:
    gate_plan(plan, cfg, *, today, receipts_age_days, graded_window, exceptions) -> (plan, report)
    run_gate(root, *, plan, cfg, today, receipts_age_days, graded_window) -> report
    publish_enabled() -> bool
    mark_all_unverified(plan) -> None  (M4 helper: stamp every item sentinel_ok=False in-place)
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
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

# Sentinel schema version
_SCHEMA_VERSION = 1

# Conservative in-code defaults (all knobs are also in config/marketing.yml sentinel:)
# Base = weeks_1_2 tier: W1 has no account-age wiring, so defaults assume brand-new accounts.
# D02 actuator RAISES caps by ramp tier, never lowers. Must match config/marketing.yml sentinel:
_DEFAULT_NEAR_DUP_JACCARD = 0.50              # tightened from 0.60: "substantially similar" bar
_DEFAULT_MAX_POSTS_PER_ACCOUNT_PER_DAY = 2    # weeks_1_2 floor
_DEFAULT_MIN_MINUTES_BETWEEN_POSTS = 120       # NOT enforced at plan tier (slots have no
                                               # timestamps); it is the contract value the
                                               # D02 actuator must read from sentinel config.
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

# mirrors copywriter disclosure check — keep in sync
# Multi-word anchors match as substrings (safe — no common false-positive superstrings).
# Single-word tokens use \b word-boundary to avoid "grade" inside "upgraded",
# "historical" inside "historically", "publicly" inside "unpublically", etc.
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


def _token_set(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _jaccard(a: str, b: str) -> float:
    ta = _token_set(a)
    tb = _token_set(b)
    if not ta and not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


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


def _load_exceptions(root: Path) -> dict[str, dict]:
    """Load sentinel_exceptions.jsonl → {item_id: row}. Missing file = empty."""
    path = root / _EXCEPTIONS_REL
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

    M4 helper: called by the governor error path before writing the raw plan so
    that an ungated plan is never written without a clear sentinel_ok=False signal.
    De-escalate-only invariant: only sets False (never upgrades an existing True).
    """
    for acc in (plan.get("accounts") or []):
        for item in (acc.get("queue") or []):
            # De-escalate only: do not flip True → False; but on crash path
            # there are no existing True stamps, so this is always safe.
            if not item.get("sentinel_ok"):
                item["sentinel_ok"] = False


def _has_disclosure(text: str) -> bool:
    """Return True if text contains any required disclosure anchor.

    Multi-word anchors: substring match (no false-positive superstrings exist).
    Single-word tokens: word-boundary match (guards against "upgraded"→"grade",
    "historically"→"historical", etc.).
    mirrors copywriter disclosure check — keep in sync
    """
    lower = text.lower()
    if any(phrase in lower for phrase in _DISCLOSURE_PHRASES_MULTI):
        return True
    return any(p.search(lower) for p in _DISCLOSURE_PATTERNS_SINGLE)


# ---------------------------------------------------------------------------
# Core gate logic
# ---------------------------------------------------------------------------

def gate_plan(
    plan: dict,
    cfg: dict,
    *,
    today: str | None = None,
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

    Check sequencing (M1 — quarantine-aware):
    1. Content-level checks (lexicon, disclosure, link rule, cashtag breadth)
       — item-intrinsic, order-independent.
    2. Always-enforced classes (account_disabled, stale-receipts).
    3. First exceptions pass — restores eligible content-level violations only
       (never account_disabled / stale / kill-switch).
    4. Near-dup + shared-media, considering ONLY items still alive after steps 1–3.
       First-alive-in-plan-order survives; later alive dups quarantine.
       NOTE: if a near-dup survivor is later cap-killed in step 5, the dropped dup
       stays dropped — deliberate conservatism (near-identical content queued the
       same day is drop-worthy regardless; docket says "rewrite-or-drop the later
       item"). Cap-killed survivor does not "rescue" its dropped dup.
    5. Caps (cadence daily, same-cashtag, slot collision, media, replies) counting
       ONLY still-alive items, in queue order.
    6. Final exceptions pass for step-4/5 violations (operator allow-exception
       may exceed a cap — that is the human override by design).
    """
    import copy
    plan = copy.deepcopy(plan)

    sc = _cfg_sentinel(cfg)
    strict: bool = bool(_get(
        (cfg.get("settings") or {}) if isinstance(cfg, dict) else {},
        "auditor_strict",
        True,
    ))

    if exceptions is None:
        exceptions = {}

    now = _now_utc()
    as_of = plan.get("as_of", "")

    # Collect disabled account ids from desk_network
    disabled_accounts: list[str] = []
    desk_net = (cfg.get("desk_network") or {}) if isinstance(cfg, dict) else {}
    for acc in (desk_net.get("accounts") or []):
        if acc.get("disabled"):
            disabled_accounts.append(str(acc.get("id", "")))

    # --- build flat item list across accounts --------------------------------
    # Each element: (account_id, item_dict, account_index, queue_index)
    all_items: list[tuple[str, dict, int, int]] = []
    for ai, acc in enumerate(plan.get("accounts") or []):
        acc_id = str(acc.get("id", ""))
        for qi, item in enumerate(acc.get("queue") or []):
            all_items.append((acc_id, item, ai, qi))

    # --- knobs ---------------------------------------------------------------
    near_dup_thresh = float(_get(sc, "near_dup_jaccard", _DEFAULT_NEAR_DUP_JACCARD))
    max_posts_day = int(_get(sc, "max_posts_per_account_per_day", _DEFAULT_MAX_POSTS_PER_ACCOUNT_PER_DAY))
    max_same_cashtag = int(_get(sc, "max_same_cashtag_per_account_per_day", _DEFAULT_MAX_SAME_CASHTAG_PER_ACCOUNT_PER_DAY))
    max_replies_day = int(_get(sc, "max_replies_per_account_per_day", _DEFAULT_MAX_REPLIES_PER_ACCOUNT_PER_DAY))
    max_receipt_age = int(_get(sc, "max_receipt_age_days", _DEFAULT_MAX_RECEIPT_AGE_DAYS))
    links_allowed = bool(_get(sc, "links_allowed", _DEFAULT_LINKS_ALLOWED))
    max_media_posts_day = int(_get(sc, "max_media_posts_per_account_per_day", _DEFAULT_MAX_MEDIA_POSTS_PER_ACCOUNT_PER_DAY))
    max_cashtags_per_post = int(_get(sc, "max_cashtags_per_post", _DEFAULT_MAX_CASHTAGS_PER_POST))
    lexicon_phrases = list(_get(sc, "lexicon_phrases", _DEFAULT_LEXICON_PHRASES))
    lexicon_patterns = list(_get(sc, "lexicon_patterns", _DEFAULT_LEXICON_PATTERNS))

    # --- check state trackers ------------------------------------------------
    reasons_histogram: dict[str, int] = defaultdict(int)
    quarantined_entries: list[dict] = []

    # Per-item violation accumulator {(ai, qi): list[str]}
    violations: dict[tuple[int, int], list[str]] = defaultdict(list)

    # =========================================================================
    # STEP 1: Content-level checks (item-intrinsic, order-independent)
    # =========================================================================

    # --- Check: financial-advice lexicon -------------------------------------
    compiled_patterns = [
        re.compile(p, re.IGNORECASE) for p in lexicon_patterns
    ]
    lexicon_hits = 0

    for acc_id, item, ai, qi in all_items:
        text = _item_text(item).lower()
        # phrase check (word-boundary, case-insensitive)
        for phrase in lexicon_phrases:
            pattern = r"\b" + re.escape(phrase) + r"\b"
            if re.search(pattern, text, re.IGNORECASE):
                violations[(ai, qi)].append(f"advice_lexicon:{phrase}")
                lexicon_hits += 1
                break
        else:
            # pattern check
            for cp in compiled_patterns:
                m = cp.search(text)
                if m:
                    violations[(ai, qi)].append(f"advice_lexicon:{m.group(0)}")
                    lexicon_hits += 1
                    break

    # --- Check: disclosure law (signal items) --------------------------------
    disclosure_hits = 0

    for acc_id, item, ai, qi in all_items:
        if item.get("type") != "signal":
            continue
        text = _item_text(item)
        if not _has_disclosure(text):
            violations[(ai, qi)].append("missing_disclosure")
            disclosure_hits += 1

    # --- Check: link rule ----------------------------------------------------
    _link_re = re.compile(r"https?://|\bt\.co/", re.IGNORECASE)
    link_hits = 0

    if not links_allowed:
        for acc_id, item, ai, qi in all_items:
            text = _item_text(item)
            if _link_re.search(text):
                violations[(ai, qi)].append("link_not_allowed")
                link_hits += 1

    # --- Check: cashtag breadth (per post) -----------------------------------
    # Count DISTINCT $TICKER tokens in headline + body. If the count exceeds
    # max_cashtags_per_post, quarantine with cashtag_breadth — UNLESS the item type is
    # "theme_list". theme_list is exempt because validate_copy requires ≥4 cashtags there
    # by format. Tension: memo §2 R3 flags multi-cashtag lists as the piggybacking heuristic;
    # revisit in a later wave when theme_list volume is measurable.
    _cashtag_re = re.compile(r"\$[A-Z]{1,5}(?:\.[A-Z]{1,2})?")
    cashtag_breadth_hits = 0

    for acc_id, item, ai, qi in all_items:
        if item.get("type") == "theme_list":
            continue  # exempt — see comment above
        text = _item_text(item)
        distinct_cashtags = set(_cashtag_re.findall(text.upper()))
        if len(distinct_cashtags) > max_cashtags_per_post:
            violations[(ai, qi)].append("cashtag_breadth")
            cashtag_breadth_hits += 1

    # =========================================================================
    # STEP 2: Always-enforced classes (account_disabled, stale-receipts)
    # =========================================================================

    # --- Check: account_disabled (always enforced regardless of strict) ------
    for acc_id, item, ai, qi in all_items:
        if acc_id in disabled_accounts:
            violations[(ai, qi)].append("account_disabled")

    # --- Check: stale receipts refusal (always enforced) --------------------
    plan_refused = False
    receipts_age_check: dict[str, Any] = {
        "age_days": None if receipts_age_days is None else int(receipts_age_days),
        "max": max_receipt_age,
    }
    if receipts_age_days is not None:
        if receipts_age_days > max_receipt_age:
            plan_refused = True
            for acc_id, item, ai, qi in all_items:
                violations[(ai, qi)].append("stale_receipts_ledger")
    else:
        # Unknown age → quarantine receipt-type items only, note in report
        for acc_id, item, ai, qi in all_items:
            if item.get("type") in _RECEIPT_TYPES:
                violations[(ai, qi)].append("receipts_age_unknown")

    # =========================================================================
    # STEP 3: First exceptions pass
    # Restores eligible content-level violations only (steps 1–2 violations
    # that are not always-enforced). Never restores account_disabled / stale /
    # kill-switch.
    # =========================================================================

    always_enforced = {"account_disabled", "stale_receipts_ledger"}
    exceptions_applied_step3 = 0

    for acc_id, item, ai, qi in all_items:
        iid = str(item.get("id") or "")
        key = (ai, qi)
        if not violations[key]:
            continue
        if iid not in exceptions:
            continue
        exc_row = exceptions[iid]
        # Cannot override always-enforced reasons
        overrideable = [r for r in violations[key] if r not in always_enforced]
        non_overrideable = [r for r in violations[key] if r in always_enforced]
        if overrideable and not non_overrideable:
            violations[key] = []  # clear all — exception restores the item
            item["exception_applied"] = exc_row.get("reason", "human override")
            exceptions_applied_step3 += 1
        # If non_overrideable exist, exception cannot restore — still quarantined

    # =========================================================================
    # STEP 4: Near-dup + shared-media, considering ONLY items alive after steps 1–3
    # =========================================================================

    near_dup_pairs_checked = 0
    near_dup_hits = 0

    # surviving_cross: (acc_id, ai, qi, text) of items alive on their account
    surviving_cross: list[tuple[str, int, int, str]] = []
    chart_id_seen: dict[str, tuple[int, int]] = {}  # chart_id → (ai, qi) first alive item

    for acc_id, item, ai, qi in all_items:
        key = (ai, qi)
        # Only alive items participate in near-dup / shared-media checks.
        # A pair where one side is already dead is not coordinated posting.
        if violations[key]:
            continue

        item_text = _item_text(item)
        chart_id = item.get("chart_id")

        # Shared media check (non-null chart_id)
        if chart_id:
            if chart_id in chart_id_seen:
                prev_ai, prev_qi = chart_id_seen[chart_id]
                # Find the original account for the first item that claimed this chart_id
                prev_acc = acc_id  # default to same (no violation) if lookup fails
                for a, it, pai, pqi in all_items:
                    if pai == prev_ai and pqi == prev_qi:
                        prev_acc = a
                        break
                if prev_acc != acc_id:
                    # Different accounts sharing same chart_id → quarantine the later one
                    violations[key].append(f"shared_media:{chart_id}")
                    near_dup_hits += 1
                    continue  # quarantined; do not add to surviving_cross
            else:
                chart_id_seen[chart_id] = (ai, qi)

        # Near-dup check against alive items on DIFFERENT accounts already seen
        dup_found = False
        for prev_acc_id, prev_ai, prev_qi, prev_text in surviving_cross:
            if prev_acc_id == acc_id:
                continue  # same account — not sentinel's job
            near_dup_pairs_checked += 1
            sim = _jaccard(item_text, prev_text)
            if sim >= near_dup_thresh:
                # Find the surviving item's id
                for a, it, pai, pqi in all_items:
                    if pai == prev_ai and pqi == prev_qi:
                        surviving_id = it.get("id", f"{prev_acc_id}/{prev_qi}")
                        break
                else:
                    surviving_id = f"{prev_acc_id}/{prev_qi}"
                violations[key].append(f"near_dup:{surviving_id}")
                near_dup_hits += 1
                dup_found = True
                break

        if not dup_found:
            surviving_cross.append((acc_id, ai, qi, item_text))

    # =========================================================================
    # STEP 5: Caps, counting ONLY still-alive items, in queue order
    # =========================================================================

    # Per-account counters
    posts_by_account: dict[str, int] = defaultdict(int)
    cashtag_by_account: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    slot_by_account: dict[str, set[str]] = defaultdict(set)
    replies_by_account: dict[str, int] = defaultdict(int)
    media_count_by_account: dict[str, int] = defaultdict(int)

    cadence_stats: dict[str, Any] = {
        "cadence_cap_daily_hits": 0,
        "cashtag_cap_hits": 0,
        "slot_collision_hits": 0,
        "reply_cap_hits": 0,
    }
    media_cap_hits = 0

    for acc_id, item, ai, qi in all_items:
        key = (ai, qi)
        # Only alive items consume cap slots
        if violations[key]:
            continue

        item_type = item.get("type", "")
        cashtag = str(item.get("cashtag") or "").strip()
        slot = str(item.get("slot") or "").strip()

        # media cap (counted first so a media item that also hits post cap is counted)
        if item.get("chart_id") is not None:
            if media_count_by_account[acc_id] >= max_media_posts_day:
                violations[key].append("media_cap_daily")
                media_cap_hits += 1
                continue
            media_count_by_account[acc_id] += 1

        # reply cap
        if item_type == "reply":
            if replies_by_account[acc_id] >= max_replies_day:
                violations[key].append("cadence_cap_daily")
                cadence_stats["reply_cap_hits"] += 1
                continue
            replies_by_account[acc_id] += 1

        # daily post cap
        if posts_by_account[acc_id] >= max_posts_day:
            violations[key].append("cadence_cap_daily")
            cadence_stats["cadence_cap_daily_hits"] += 1
            continue
        posts_by_account[acc_id] += 1

        # cashtag cap
        if cashtag:
            if cashtag_by_account[acc_id][cashtag] >= max_same_cashtag:
                violations[key].append(f"cashtag_cap:{cashtag}")
                cadence_stats["cashtag_cap_hits"] += 1
                posts_by_account[acc_id] -= 1  # didn't really count
                continue
            cashtag_by_account[acc_id][cashtag] += 1

        # slot collision (one item per (account, slot))
        if slot:
            if slot in slot_by_account[acc_id]:
                violations[key].append(f"slot_collision:{slot}")
                cadence_stats["slot_collision_hits"] += 1
                posts_by_account[acc_id] -= 1
                if cashtag:
                    cashtag_by_account[acc_id][cashtag] -= 1
                continue
            slot_by_account[acc_id].add(slot)

    # =========================================================================
    # STEP 5b: Cherry-pick detector (alive-items only, on receipt items)
    # =========================================================================

    cherry_pick_status: str
    cherry_pick_extra: dict[str, Any] = {}

    if graded_window is None:
        cherry_pick_status = "skipped"
    else:
        cherry_pick_status = "run"
        # Collect loss/mixed tickers from graded_window
        loss_tickers: set[str] = set()
        for gw in graded_window:
            if gw.get("outcome") in {"loss", "mixed"}:
                t = str(gw.get("ticker") or "")
                if t:
                    loss_tickers.add(t.upper())

        if loss_tickers:
            # Find alive receipt items in plan and what tickers they show
            plan_receipt_tickers_win: set[str] = set()
            plan_receipt_tickers_all: set[str] = set()
            receipt_items_by_key: list[tuple[int, int]] = []

            for acc_id, item, ai, qi in all_items:
                if violations[(ai, qi)]:
                    continue  # dead items don't participate
                if item.get("type") not in _RECEIPT_TYPES:
                    continue
                ticker = str(item.get("ticker") or "").upper()
                cashtag_val = str(item.get("cashtag") or "").upper().lstrip("$")
                t = ticker or cashtag_val
                if t:
                    plan_receipt_tickers_all.add(t)
                    # Determine if this is a "win" receipt (no loss_pct in item, or explicitly win)
                    # We check if the ticker is NOT in loss_tickers
                    if t not in loss_tickers:
                        plan_receipt_tickers_win.add(t)
                receipt_items_by_key.append((ai, qi))

            # Cherry pick: has loss in window, plan shows win receipts but none of the loss tickers
            if plan_receipt_tickers_win and not (loss_tickers & plan_receipt_tickers_all):
                for ai, qi in receipt_items_by_key:
                    violations[(ai, qi)].append("cherry_pick_suspected")
                cherry_pick_extra["cherry_pick_detected"] = True
                cherry_pick_extra["loss_tickers_missing"] = sorted(loss_tickers)
            else:
                cherry_pick_extra["cherry_pick_detected"] = False

        cherry_pick_extra["loss_tickers_in_window"] = sorted(loss_tickers) if loss_tickers else []

    # =========================================================================
    # STEP 6: Final exceptions pass for step-4/5 violations
    # An operator allow-exception may exceed a cap — that is the human override
    # by design. This pass runs after all caps/near-dup are computed so it only
    # touches the step-4/5 additions that slipped past the first exceptions pass.
    # =========================================================================

    exceptions_applied_step6 = 0

    for acc_id, item, ai, qi in all_items:
        iid = str(item.get("id") or "")
        key = (ai, qi)
        if not violations[key]:
            continue
        if iid not in exceptions:
            continue
        # Skip items already restored by step 3 (they have no violations left)
        # Skip items that already had exception_applied set (step 3 handled them)
        if item.get("exception_applied"):
            continue
        exc_row = exceptions[iid]
        # Cannot override always-enforced reasons
        overrideable = [r for r in violations[key] if r not in always_enforced]
        non_overrideable = [r for r in violations[key] if r in always_enforced]
        if overrideable and not non_overrideable:
            violations[key] = []  # clear all — exception restores the item
            item["exception_applied"] = exc_row.get("reason", "human override")
            exceptions_applied_step6 += 1
        # If non_overrideable exist, exception cannot restore — still quarantined

    exceptions_applied = exceptions_applied_step3 + exceptions_applied_step6

    # --- Annotate items + build report data ----------------------------------
    total = len(all_items)
    passed_count = 0
    quarantined_count = 0
    warnings_items_count = 0  # N2: number of ITEMS carrying warnings (not sum of strings)

    for acc_id, item, ai, qi in all_items:
        key = (ai, qi)
        item_violations = violations[key]
        acc_data = plan["accounts"][ai]

        if not item_violations:
            item["sentinel_ok"] = True
            passed_count += 1
        else:
            if strict:
                # Always-enforced + plan_refused always quarantine regardless of strict flag
                item["sentinel_ok"] = False
                item["status"] = "quarantined"
                item["sentinel_reasons"] = item_violations
                quarantined_count += 1
                for r in item_violations:
                    r_key = r.split(":")[0]
                    reasons_histogram[r_key] += 1
                quarantined_entries.append({
                    "id": item.get("id", ""),
                    "account": acc_id,
                    "slot": item.get("slot", ""),
                    "type": item.get("type", ""),
                    "cashtag": item.get("cashtag", ""),
                    "headline": (item.get("headline") or "")[:120],
                    "reasons": item_violations,
                })
            else:
                # Non-strict: annotate warnings only (except always-enforced which still quarantine)
                always_v = [v for v in item_violations if v in always_enforced or plan_refused]
                soft_v = [v for v in item_violations if v not in always_enforced and not plan_refused]
                if always_v:
                    item["sentinel_ok"] = False
                    item["status"] = "quarantined"
                    item["sentinel_reasons"] = always_v
                    if soft_v:
                        item["sentinel_warnings"] = soft_v
                    quarantined_count += 1
                    for r in always_v:
                        r_key = r.split(":")[0]
                        reasons_histogram[r_key] += 1
                    quarantined_entries.append({
                        "id": item.get("id", ""),
                        "account": acc_id,
                        "slot": item.get("slot", ""),
                        "type": item.get("type", ""),
                        "cashtag": item.get("cashtag", ""),
                        "headline": (item.get("headline") or "")[:120],
                        "reasons": always_v,
                    })
                else:
                    item["sentinel_ok"] = True
                    item["sentinel_warnings"] = soft_v
                    passed_count += 1
                    if soft_v:
                        warnings_items_count += 1  # count items with warnings, not strings
                    for r in soft_v:
                        r_key = r.split(":")[0] + "_warning"
                        reasons_histogram[r_key] += 1

    # --- Determine plan_status -----------------------------------------------
    # "pass"              = gate ran cleanly (strict mode; quarantines are expected/intended)
    # "pass_with_warnings" = non-strict mode with violations annotated as warnings
    # "refused"           = stale receipts; entire plan rejected
    if plan_refused:
        plan_status = "refused"
    elif not strict and (warnings_items_count > 0 or quarantined_count > 0):
        plan_status = "pass_with_warnings"
    else:
        plan_status = "pass"

    # Build report
    report: dict = {
        "schema_version": _SCHEMA_VERSION,
        "produced_by": "sentinel",
        "produced_at": now,
        "as_of": as_of,
        "plan_status": plan_status,
        "publish_enabled": publish_enabled(),
        "auditor_strict": strict,
        "counts": {
            "items": total,
            "passed": passed_count,
            "quarantined": quarantined_count,
            # warnings = number of ITEMS carrying warnings (not sum of violation strings)
            "warnings": warnings_items_count,
            "exceptions_applied": exceptions_applied,
        },
        "reasons_histogram": dict(reasons_histogram),
        "quarantined": quarantined_entries,
        "checks": {
            "near_dup": {
                "pairs_checked": near_dup_pairs_checked,
                "hits": near_dup_hits,
            },
            "cadence": cadence_stats,
            "lexicon": {"hits": lexicon_hits},
            "disclosure": {"hits": disclosure_hits},
            "cherry_pick": {
                "status": cherry_pick_status,
                **cherry_pick_extra,
            },
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
        "notes": [],
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
    today: str | None = None,
    receipts_age_days: int | float | None = None,
    graded_window: list[dict] | None = None,
) -> dict:
    """Load plan+cfg+exceptions from disk if not given, gate, atomically write
    annotated plan back to data/marketing/content_plan.json and report to
    data/marketing/sentinel_report.json.

    Returns report. Callable from the governor AND from the future D01 fastlane.

    FAIL CLOSED: if gate_plan raises, write a minimal error report and re-raise
    so the caller can decide whether to crash.
    """
    r = _repo_root(root)
    now = _now_utc()

    # Load config from disk if not supplied
    if cfg is None:
        try:
            import yaml  # noqa: PLC0415
            cfg_path = r / _CONFIG_REL
            with open(cfg_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception as exc:  # noqa: BLE001
            log.warning("sentinel.run_gate: could not load cfg: %s", exc)
            cfg = {}

    # Load plan from disk if not supplied
    if plan is None:
        try:
            plan_path = r / _CONTENT_PLAN_REL
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("sentinel.run_gate: could not load plan: %s", exc)
            plan = {"accounts": [], "as_of": ""}

    # Load exceptions
    exceptions = _load_exceptions(r)

    try:
        annotated_plan, report = gate_plan(
            plan, cfg,
            today=today,
            receipts_age_days=receipts_age_days,
            graded_window=graded_window,
            exceptions=exceptions,
        )
    except Exception as exc:  # noqa: BLE001
        # FAIL CLOSED: write a minimal error report so the nightly does not
        # silently publish an ungated plan.
        err_report = {
            "schema_version": _SCHEMA_VERSION,
            "produced_by": "sentinel",
            "produced_at": now,
            "as_of": (plan or {}).get("as_of", ""),
            "plan_status": "error",
            "publish_enabled": publish_enabled(),
            "auditor_strict": True,
            "counts": {"items": 0, "passed": 0, "quarantined": 0, "warnings": 0, "exceptions_applied": 0},
            "reasons_histogram": {},
            "quarantined": [],
            "checks": {},
            "notes": [f"sentinel gate raised: {exc}"],
        }
        _write_json_atomic(r / _SENTINEL_REPORT_REL, err_report)
        raise

    # Write annotated plan (overwrites content_plan.json atomically)
    _write_json_atomic(r / _CONTENT_PLAN_REL, annotated_plan)
    # Write report
    _write_json_atomic(r / _SENTINEL_REPORT_REL, report)

    return report
