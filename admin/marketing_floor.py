"""Marketing floor — the operator's view *inside* the content factory.

Three read-only panels, all fail-soft (NEVER-RAISE; an unreadable file degrades
one field to ``None`` with a plain-word note, it never breaks the panel):

* :func:`floor`  — the production line. One honest count per station plus the
  named loss at each one, the ranked blockers, and tonight's authorship split.
* :func:`models` — which model wrote the words, and the OAuth key-pool
  balancer's belief state per key.
* :func:`lanes`  — the X-growth lanes (press wire, hot tape, filings, intel,
  replies) with a live/dark verdict and a freshness read each.

Why this module exists (operator, 2026-07-29): "it's like a factory with its
window panes all tinted and me as the CEO unable to see the inside." Every
number the engines already compute was being dropped on the floor — the
publisher writes a 25-counter loss ledger per run and the console rendered five
of them; the gate records a per-post reason for all 526 holds and the console
rendered a total. This module surfaces what already exists. It computes no new
truth and it never writes.

REDLINE: no secret VALUE ever crosses this boundary. The key-pool view carries
capability-id NAMES, cooling state, and load percentages only — never a token.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .marketing import (
    _CONFIG_REL,
    _CONTENT_REL,
    _SENTINEL_REL,
    _default_root,
    _plan_is_stale,
    _read_json,
    _read_jsonl,
    _read_yaml,
    arm_state,
)

# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
_OUTBOX_DIR = Path("data/marketing/outbox")
_ITEMS_REL = _OUTBOX_DIR / "items.jsonl"
_LEDGER_REL = _OUTBOX_DIR / "status_ledger.jsonl"
_ACTIVITY_REL = _OUTBOX_DIR / "activity.jsonl"
_KEY_LEDGER_REL = Path("data/metabolism/key_ledger.jsonl")
_HOT_TAPE_REL = Path("data/marketing/hot_tape_pack.json")
_RADAR_REL = Path("data/marketing/radar_report.json")
_PRESS_PUBLISHED_REL = Path("data/press/published.jsonl")
_LEARNING_HEALTH_REL = Path("data/marketing/learning/health.json")
_POST_METRICS_REL = Path("data/marketing/post_metrics.jsonl")
_REPLY_STORE_REL = Path("data/marketing/reply_queue.jsonl")
_X_INTEL_DIR = Path("data/marketing/x_intel")
_EXEMPLAR_REL = Path("data/marketing/x_intel/exemplars.json")

# The kinds the content plan is *required* to have an LLM write (the no-fallback
# law, W1 2026-07-29). A template-written post on one of these is a defect, not
# a fallback — which is exactly why the floor prints the split.
_PLANNED_KINDS = frozenset({
    "signal", "chart", "education", "macro", "receipt",
    "watchlist", "event", "congress", "insider",
})

# Publisher activity counters → plain words, in the order the operator reads
# them (biggest structural causes first). A counter absent from this map still
# renders, under its raw name — a new engine counter must never go invisible
# just because this table wasn't updated.
_ACTIVITY_WORDS: dict[str, str] = {
    "posted": "went out to X",
    "would_post": "would have gone out (dry run)",
    "failed": "failed at the API",
    # A WAIT, NOT A LOSS — and the wording is the whole point. These posts went
    # back to `approved` and the next sweep re-picks them; reading them as
    # "failed" is exactly the confusion that let three good posts be discarded
    # on 2026-07-30 without anyone noticing they were recoverable.
    "rate_limited": "waiting out a Buffer rate limit (will retry)",
    "quarantined": "pulled at dispatch",
    "skipped_no_channel": "no channel wired for that desk",
    "skipped_halt": "desk halted by the learning tripwire",
    "skipped_cap": "over the desk's daily cap",
    "skipped_cadence": "too soon after that desk's last post",
    "cadence_shadow": "spacing gate watching only (not enforcing)",
    "skipped_floor": "below the salience floor",
    "skipped_filler": "over the day's filler budget",
    "quarantined_frame": "same sentence shape as a recent post",
    "quarantined_substance": "no ticker and no number",
    "substance_shadow": "substance gate watching only (not enforcing)",
    "deferred_no_media": "waiting on its chart",
    "deferred_immediate": "held back as a breaking item",
    "deferred_cross_account": "spaced out from a sibling desk's post",
    "forward_booked": "booked into a later slot",
    # NOT the hot-tape lane — these two are the LIVE TAPE GATE, which refuses to
    # send a post whose price claim it cannot verify against a quote fresher than
    # 45 minutes. Mislabelling them "hot-tape item skipped" hid the actual reason
    # nothing posted on 2026-07-29: both approved posts were held because their
    # quotes were ~55h stale or absent from the quote universe entirely.
    "tape_quarantined": "pulled — price claim contradicted today's tape",
    "tape_skipped": "held — no fresh quote to verify the price claim",
    "pt_generated": "publish-time reads written",
    "pt_dropped": "publish-time read dropped",
    "auto_approved": "auto-approved",
    "stuck_posting": "stuck mid-post",
    # The 2026-07-30 gates, after the operator graded a batch F. Plain words
    # matter most here: these four are the ones that will move, and "why did
    # only 51 of 187 go out" has to be answerable from this page alone.
    "quarantined_bare_cashtag": "pulled — named tickers with no chart",
    "quarantined_unknown_cashtag": "pulled — named a ticker no price store knows",
    "quarantined_voice_laws": "pulled — reads machine-written",
    "quarantined_run_duplicate": "pulled — repeats a post already sent today",
    # The 2026-08-02 clock gates. Both name the DEFECT the operator reported,
    # not the check: he wrote down "Friday's move called today on a Saturday"
    # and "six posts off one stale breadth read", so those are the words. A
    # count here means the queue is holding copy that went stale while it
    # waited, which is a scheduling fault; a count in the fan-out row means the
    # plan is fanning one fact across desks, which is a supply fault. Different
    # rows because they get fixed in different places.
    "quarantined_clock": "pulled — claimed a session that was not the posting session",
    "quarantined_fact_fanout": "pulled — same fact another post already carries",
    # The wire reaper (2026-07-31). Says WHY in the operator's terms — the copy
    # was fine, the queue never moved — because a recurring count here is a
    # DISPATCH fault, not a writing fault, and the two get fixed in different
    # places. Named "aged out" rather than "expired" for the same reason
    # rate_limited is "waiting out a rate limit": the word has to carry the
    # cause, not the mechanism.
    "expired_wire": "aged out of the queue before anyone sent it",
    # The autonomous approval desk (2026-07-31). These five answer the question
    # the operator asked for when he said "closely audit them, then approve them
    # so they go out quickly without me" — which is not "how many went out" but
    # "what did the desk decide on my behalf, and what is still mine".
    #
    # `held` is the one that has to read exactly right. It does NOT mean the
    # desk judged the post bad: it means the desk had nothing to check the
    # post's numbers against and refused to bless a claim it could not verify.
    # That queue is the operator's, and calling it "rejected" would hide the
    # only work left for a human.
    "desk_approved": "audited and cleared to go out",
    "desk_quarantined": "pulled by the audit before approval",
    "desk_held": "left for you: the audit could not check its numbers",
    "desk_capped": "over this sweep's approval limit (re-audited next sweep)",
    "desk_expired": "retired as too old to still be true",
    "desk_disabled": "the audit is switched off in config",
}

# Counters that mean "a post did NOT go out because of this" — the ones that sum
# toward the night's loss. Distinct from informational counters (pt_generated,
# auto_approved) which describe work done, not work lost.
_LOSS_COUNTERS = frozenset({
    "failed", "quarantined", "skipped_no_channel", "skipped_halt",
    "skipped_cap", "skipped_cadence", "skipped_floor", "skipped_filler",
    "quarantined_frame", "quarantined_substance", "deferred_no_media",
    # Both are posts the desk wrote and nobody will ever send. Console must
    # surface the leak: without these rows the six-post breadth family would
    # shrink to one on the Floor with no line saying where the other five went.
    "quarantined_clock", "quarantined_fact_fanout",
    "deferred_immediate", "deferred_cross_account", "tape_quarantined",
    "tape_skipped", "pt_dropped", "stuck_posting",
    # A post the desk wrote and nobody sent is a loss like any other — it is
    # only invisible because it died before the dispatch loop rather than in it.
    "expired_wire",
    # The approval desk's four post-costing outcomes. `desk_approved` is
    # deliberately NOT here (it is work done, and those posts go on to be
    # counted as posted or as a dispatch-gate loss) and neither is
    # `desk_disabled` (a config state, not a post).
    "desk_quarantined", "desk_held", "desk_capped", "desk_expired",
})

# Lanes that draw an LLM on the marketing side. Config path → the lane's job in
# the operator's words. Read from config/marketing.yml; a lane whose block is
# absent reports its code default with source="code default".
_LLM_LANES: list[dict[str, Any]] = [
    {"id": "copywriter", "path": ["copywriter", "llm"],
     "name": "Post copy", "job": "Writes the words for every planned post",
     "pool_lane": "marketing-copywriter"},
    {"id": "critic", "path": ["copywriter", "llm", "critic"],
     "name": "Cold-read critic", "job": "Rejects copy that reads like a template",
     "pool_lane": "marketing-critic"},
    {"id": "copy_review", "path": ["copywriter", "llm", "review"],
     "name": "Copy review", "job": "Second read before a post reaches the gate",
     "pool_lane": "marketing-copy-review"},
    {"id": "breaking", "path": ["breaking", "llm"],
     "name": "Breaking summary", "job": "Writes the press/breaking wire posts",
     "pool_lane": "marketing-breaking"},
    {"id": "hot_tape", "path": ["hot_tape", "llm"],
     "name": "Hot-tape wire", "job": "Phrases the five-minute tape alerts",
     "pool_lane": "hot-tape-wire"},
    {"id": "reply_voice", "path": ["reply_desk", "voice"],
     "name": "Reply voice", "job": "Drafts replies in each desk's voice",
     "pool_lane": "reply-voice"},
]

# Codex tier → what the operator calls it. Sol is the writer, Terra the
# workhorse, Luna the cheap one (banned from user-facing words, 2026-07-29).
_CODEX_TIERS = {
    "gpt-5.6-sol": ("Sol", "top tier — voice work"),
    "gpt-5.6-terra": ("Terra", "mid tier — judgment and terse copy"),
    "gpt-5.6-luna": ("Luna", "cheap tier — never user-facing words"),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _age_hours(ts: Any) -> float | None:
    """Hours since an ISO timestamp. None when unparseable — never raises."""
    if not ts:
        return None
    try:
        s = str(ts).strip().replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return max(0.0, (_utcnow() - d).total_seconds() / 3600.0)
    except Exception:  # noqa: BLE001
        return None


def _age_days(date_str: Any) -> int | None:
    """Whole days since a YYYY-MM-DD. None when unparseable."""
    if not date_str:
        return None
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
        return (_utcnow().date() - d).days
    except Exception:  # noqa: BLE001
        return None


def _plan_posts(cp: dict | None) -> list[dict]:
    """Flatten the plan's per-account queues into one post list."""
    if not isinstance(cp, dict):
        return []
    out: list[dict] = []
    for acct in (cp.get("accounts") or []):
        if isinstance(acct, dict) and isinstance(acct.get("queue"), list):
            out.extend(p for p in acct["queue"] if isinstance(p, dict))
    return out


# ---------------------------------------------------------------------------
# 1 · THE PRODUCTION LINE
# ---------------------------------------------------------------------------
def _is_model_mode(mode: Any) -> bool:
    """Is this ``_copy_mode`` value a MODEL writing, or a house lane?

    WHITELIST, NOT BLACKLIST (2026-08-01 audit, defect F4).  The old rule was
    "anything that is not deterministic/template/absent is a model", so every
    NEW deterministic lane the engine grew was silently promoted into the
    model-written share the strip exists to police.  Live 2026-08-01 by_mode was
    ``{no writer reached: 149, llm_repair: 3, llm: 2, movers_desk: 2}`` and the
    console reported "4 written by a model (llm_repair, llm, movers_desk)" —
    movers_desk is a deterministic desk lane, and its raw slug was printed to
    the operator as if it were a model name.

    A model mode is one the copywriter stamps when an LLM produced the words:
    ``llm``, ``llm_repair``, ``llm:<tier>``.  Everything else non-empty is a
    house lane and is counted, named, and reported as such.
    """
    m = str(mode or "").strip().lower()
    return bool(m) and (m == "llm" or m.startswith(("llm:", "llm_", "llm-")))


def _authorship(posts: list[dict]) -> dict:
    """Who wrote tonight's words.

    ``_copy_mode`` is stamped by the copywriter on every post it touches. The
    values that matter to the operator: an LLM mode (the law), ``deterministic``
    (a house template — a DEFECT on a planned kind since W1), a named house lane
    (deterministic too, but a lane rather than the generic template), or absent
    (the post never reached a writer).
    """
    total = len(posts)
    modes = Counter()
    template_on_planned = 0
    no_writer_on_planned = 0
    for p in posts:
        mode = p.get("_copy_mode")
        key = str(mode) if mode else "no writer reached"
        modes[key] += 1
        planned = str(p.get("type") or "") in _PLANNED_KINDS
        if not planned:
            continue
        # "A template wrote it" and "nothing wrote it" are different failures
        # with different fixes: the first is the word-salad defect, the second
        # is the no-fallback law working as designed under a dead provider.
        if mode in ("deterministic", "template"):
            template_on_planned += 1
        elif not mode:
            no_writer_on_planned += 1

    model_modes = sorted(m for m in modes if _is_model_mode(m))
    house_modes = sorted(
        m for m in modes
        if m != "no writer reached" and not _is_model_mode(m)
        and m not in ("deterministic", "template"))
    llm = sum(n for m, n in modes.items() if _is_model_mode(m))
    house = sum(modes[m] for m in house_modes)
    return {
        "total": total,
        "by_mode": dict(modes.most_common()),
        "llm_posts": llm,
        "llm_share": round(llm / total, 4) if total else None,
        # Named model modes and named deterministic house lanes, kept apart so
        # the UI never prints "written by a model (movers_desk)".
        "model_modes": model_modes,
        "house_lane_modes": house_modes,
        "house_lane_posts": house,
        "template_on_planned_kind": template_on_planned,
        "no_writer_on_planned_kind": no_writer_on_planned,
        # Stated as law, not as taste — a reviewer reading the panel should know
        # whether a non-zero number here is a defect or a design choice.
        "law": ("Planned posts are written by a model, never by a house "
                "template. A template count above zero on a planned kind is a "
                "defect, not a fallback."),
    }


def _dup_attractors(posts: list[dict], limit: int = 12) -> list[dict]:
    """Rank the posts that killed the most siblings as near-duplicates.

    The gate walks desks in order and holds a post that reads too close to one
    already cleared, recording ``near_dup:<winner-post-id>``. One flagship post
    can therefore quietly kill dozens of satellite posts — a ranking the
    operator has never been shown, and the single biggest lever on desk yield.
    """
    kills: Counter[str] = Counter()
    victims: dict[str, list[str]] = {}
    for p in posts:
        for reason in (p.get("sentinel_reasons") or []):
            m = re.match(r"^near_dup:(.+)$", str(reason))
            if not m:
                continue
            winner = m.group(1).strip()
            kills[winner] += 1
            victims.setdefault(winner, []).append(str(p.get("id") or "?"))

    by_id = {str(p.get("id")): p for p in posts}
    rows: list[dict] = []
    for post_id, n in kills.most_common(limit):
        src = by_id.get(post_id) or {}
        vic = victims.get(post_id) or []
        rows.append({
            "post_id": post_id,
            "account": src.get("account"),
            "kind": src.get("type"),
            "headline": src.get("headline"),
            "killed": n,
            "victim_desks": [d for d, _ in Counter(
                (by_id.get(v) or {}).get("account") or "?" for v in vic
            ).most_common()],
        })
    return rows


def _desk_yield(cp: dict | None) -> list[dict]:
    """Per-desk pass rate through the gate, worst yield first.

    This is where the desk-ordered dedup shows up as an injustice: the desk
    evaluated first keeps its posts, the ones after it collide against them.
    """
    rows: list[dict] = []
    for acct in (cp.get("accounts") or []) if isinstance(cp, dict) else []:
        if not isinstance(acct, dict):
            continue
        q = [p for p in (acct.get("queue") or []) if isinstance(p, dict)]
        if not q:
            continue
        passed = sum(1 for p in q if p.get("status") == "drafted")
        held = len(q) - passed
        near_dup = sum(
            1 for p in q
            if any(str(r).startswith("near_dup:") for r in (p.get("sentinel_reasons") or []))
        )
        capped = sum(
            1 for p in q
            if any(str(r) == "cadence_cap_daily" for r in (p.get("sentinel_reasons") or []))
        )
        rows.append({
            "account": acct.get("id"),
            "name": acct.get("name"),
            "planned": len(q),
            "passed": passed,
            "held": held,
            "held_near_dup": near_dup,
            "held_cap": capped,
            "yield": round(passed / len(q), 4) if q else None,
        })
    rows.sort(key=lambda r: (r.get("yield") if r.get("yield") is not None else 1.0))
    return rows


def _last_activity(repo: Path) -> dict | None:
    """The most recent publisher run's counter row."""
    rows = _read_jsonl(repo / _ACTIVITY_REL) or []
    for row in reversed(rows):
        if isinstance(row, dict) and row.get("lane"):
            return row
    return None


def _activity_ledger(row: dict | None) -> dict:
    """Turn one publisher activity row into a plain-word loss ledger.

    Every counter the engine wrote is reported — a counter missing from
    :data:`_ACTIVITY_WORDS` renders under its raw name rather than vanishing,
    so a new engine gate cannot ship invisible.
    """
    if not isinstance(row, dict):
        return {"present": False, "lines": [], "lost_total": None,
                "note": "The publisher has not logged a run on this machine yet."}

    lines: list[dict] = []
    lost = 0
    for key, val in row.items():
        if key in ("at", "lane", "backend", "cap", "account", "halted_accounts"):
            continue
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            continue
        n = int(val)
        is_loss = key in _LOSS_COUNTERS
        if is_loss:
            lost += n
        lines.append({
            "key": key,
            "word": _ACTIVITY_WORDS.get(key, key.replace("_", " ")),
            "n": n,
            "is_loss": is_loss,
            "mapped": key in _ACTIVITY_WORDS,
        })
    # "Went out to X" leads unconditionally — sorted by size it would sink into
    # the dimmed zeroes on exactly the night the operator most needs to see it,
    # which is the tinted-window defect in miniature. Everything after it sorts
    # biggest-first; zero rows are kept and dimmed, never dropped.
    _pin = {"posted": 0, "would_post": 1}
    lines.sort(key=lambda r: (_pin.get(r["key"], 2), -r["n"],
                              not r["is_loss"], r["key"]))
    return {
        "present": True,
        "at": row.get("at"),
        "lane": row.get("lane"),
        "backend": row.get("backend"),
        "account": row.get("account"),
        "halted_accounts": row.get("halted_accounts") or [],
        "posted": row.get("posted"),
        "lost_total": lost,
        "lines": lines,
    }


def _station(sid: str, name: str, what: str, out: int | None,
             prior: int | None, loss_word: str | None = None,
             goto: str | None = None, detail: str | None = None) -> dict:
    """One station on the line: what arrived, what left, what died here.

    NON-MONOTONE COUNTERS ARE NEVER CLAMPED (2026-08-01 audit, defect F1).
    These counters are written by different passes over different post sets:
    ``written`` counts plan posts carrying ``_copy_mode`` while ``cleared`` is
    the sentinel's ``counts.passed`` measured over the WHOLE plan queue.  On the
    live 2026-08-01 plan that produced a station taking 7 in and emitting 137
    out.  The old body did ``lost = max(0, prior - out)``, which turned that
    impossible transition into a confident "nothing lost here" and then let the
    NEXT station charge a fabricated 128-post loss to an enqueue gap that does
    not exist (defect F2).  A funnel that silently clamps a non-monotone pair is
    a lie in layout form.

    So: when ``out > in`` the station is marked ``odd`` and publishes NO loss and
    NO yield, and every station from there down carries ``chain_ok: False`` —
    their own ``lost`` is arithmetic over a denominator that means something
    different, and callers (the blocker ranker, the UI) must refuse to spend it.
    """
    odd = (isinstance(out, int) and isinstance(prior, int) and out > prior)
    lost = None
    if isinstance(out, int) and isinstance(prior, int) and not odd:
        lost = prior - out
    yld = None
    if isinstance(out, int) and isinstance(prior, int) and prior > 0 and not odd:
        yld = round(out / prior, 4)
    return {
        "id": sid, "name": name, "what": what,
        "in": prior, "out": out, "lost": lost, "yield": yld,
        "loss_word": loss_word, "goto": goto, "detail": detail,
        "odd": odd,
        "odd_note": (
            f"{name} reports {out} out of {prior} in. These two counters were "
            "written by different passes over different post sets, so they do "
            "not nest — read them on their own, not as a chain."
        ) if odd else None,
        # Set by floor() once the whole line is built: False from the first odd
        # station onward, because everything downstream inherits its denominator.
        "chain_ok": True,
    }


def floor(root=None) -> dict:  # noqa: PLR0912, PLR0915
    """The production line, tonight's losses, and the ranked blockers."""
    repo = Path(root) if root is not None else _default_root()
    try:
        cp = _read_json(repo / _CONTENT_REL)
        rpt = _read_json(repo / _SENTINEL_REL)
        posts = _plan_posts(cp)
        as_of = (cp or {}).get("as_of") if isinstance(cp, dict) else None

        # --- station counts -------------------------------------------------
        planned = len(posts) or None
        # The plan's own summary has been drifting from its queue length (1184
        # claimed vs 997 real on 2026-07-29). Lead with the queue — it is the
        # thing that exists — and report the claim so the drift is visible
        # rather than silently authoritative.
        claimed = ((cp or {}).get("summary") or {}).get("total_posts") if isinstance(cp, dict) else None
        written = sum(1 for p in posts if p.get("_copy_mode")) if posts else None
        counts = (rpt or {}).get("counts") or {} if isinstance(rpt, dict) else {}
        cleared = counts.get("passed")
        if cleared is None and posts:
            cleared = sum(1 for p in posts if p.get("status") == "drafted")
        held_policy = counts.get("quarantined_policy")
        trimmed = counts.get("quarantined_overflow")

        items = _read_jsonl(repo / _ITEMS_REL) or []
        ledger = _read_jsonl(repo / _LEDGER_REL) or []
        final: dict[str, dict] = {}
        for row in ledger:
            if isinstance(row, dict) and row.get("id"):
                final[str(row["id"])] = row

        def _status(it: dict) -> str:
            row = final.get(str(it.get("id")))
            return str((row or {}).get("to") or it.get("status") or "queued")

        today_items = [it for it in items
                       if isinstance(it, dict) and it.get("as_of") == as_of]
        enqueued = len(today_items) if as_of else None
        by_status = Counter(_status(it) for it in today_items)
        live = by_status.get("posted", 0) + by_status.get("posting", 0)
        awaiting = by_status.get("queued", 0)
        approved = by_status.get("approved", 0)

        # --- glance answers (defect F6) --------------------------------------
        # ``publisher`` and ``awaiting_review`` were being computed and shipped
        # with ZERO readers in app.js. The Floor's answer bar reads this block:
        # five figures for the operator's five standing questions. Every value is
        # None when it is not measurable — the UI prints an em dash and "not
        # measured", never a 0, because a 0 reads as "checked, nothing there".
        _all_final = Counter(
            str((final.get(str(it.get("id"))) or {}).get("to")
                or it.get("status") or "queued")
            for it in items if isinstance(it, dict))
        posted_recent_at: list[str] = []
        for row in ledger:
            if isinstance(row, dict) and row.get("to") == "posted" and row.get("at"):
                posted_recent_at.append(str(row["at"]))
        posted_recent_at.sort()
        _today_utc = _utcnow().strftime("%Y-%m-%d")
        posted_today = sum(1 for a in posted_recent_at if a[:10] == _today_utc)
        # 72h window: the honest evidence that the plant CAN post, used to
        # de-escalate the host-local "Nothing can post" blocker (defect F5).
        _cut = (_utcnow() - timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%SZ")
        posted_recently = any(a >= _cut for a in posted_recent_at)
        today_block = {
            "going_out": (awaiting + approved) if enqueued is not None else None,
            "awaiting_review": awaiting if enqueued is not None else None,
            "went_out_today": posted_today,
            "last_post_at": posted_recent_at[-1] if posted_recent_at else None,
            "blocked_total": _all_final.get("quarantined", 0) + _all_final.get("failed", 0),
            "blocked_today": sum(
                1 for it in today_items
                if _status(it) in ("quarantined", "failed")),
            "posted_recently": posted_recently,
        }

        act = _last_activity(repo)
        ledger_block = _activity_ledger(act)

        line = [
            _station("planned", "Planned", "slots the allocator opened",
                     planned, None, goto="marketing_content",
                     detail=(f"plan file claims {claimed}" if isinstance(claimed, int)
                             and isinstance(planned, int) and claimed != planned else None)),
            _station("written", "Written", "posts that got words",
                     written, planned, "never reached a writer",
                     goto="marketing_content"),
            _station("cleared", "Cleared", "passed the ban-risk gate",
                     cleared, written, "held or trimmed at the gate",
                     goto="marketing_sentinel",
                     detail=(f"{held_policy} held to read, {trimmed} trimmed by caps"
                             if held_policy is not None and trimmed is not None else None)),
            _station("enqueued", "Queued", "reached the outbox rail",
                     enqueued, cleared, "cleared but never enqueued",
                     goto="marketing_outbox"),
            _station("dispatched", "Dispatched", "survived the publish sweep",
                     (live + approved) or 0 if enqueued is not None else None,
                     enqueued, "pulled at dispatch", goto="marketing_publish",
                     detail=(f"{ledger_block.get('lost_total')} lost across "
                             f"{len(ledger_block.get('lines') or [])} counters"
                             if ledger_block.get("present") else None)),
            _station("live", "Live on X", "actually posted",
                     live if enqueued is not None else None,
                     (live + approved) or 0 if enqueued is not None else None,
                     "approved but still waiting", goto="marketing_publish"),
        ]

        # Propagate the non-monotone break down the line (defect F1/F2). The
        # first station whose out exceeds its in changed the denominator; from
        # there down, a `lost` figure is arithmetic over two different post sets
        # and must not be spent by the blocker ranker or drawn as a leak.
        _chain = True
        for st in line:
            if st.get("odd"):
                _chain = False
            st["chain_ok"] = _chain
        line_odd = [st["id"] for st in line if st.get("odd")]

        # The break point = the station that loses the most POSTS, not the
        # biggest percentage. A late station with 2 in and 0 out is a 100% loss
        # and is nobody's emergency; the station shedding 404 posts is where the
        # operator should walk. Share only breaks ties.
        break_at = None
        worst: tuple[int, float] = (0, 0.0)
        for st in line:
            if not (isinstance(st["in"], int) and isinstance(st["lost"], int)):
                continue
            if st["lost"] <= 0:
                continue
            # A loss measured downstream of a non-monotone station is arithmetic
            # over a denominator that means something else. Never crown it the
            # biggest leak — that is how the 128-post phantom enqueue gap became
            # the operator's rank-1 instruction (defect F2).
            if not st.get("chain_ok", True):
                continue
            share = st["lost"] / st["in"] if st["in"] > 0 else 0.0
            if (st["lost"], share) > worst:
                worst, break_at = (st["lost"], share), st["id"]

        authorship = _authorship(posts)
        pub = _publisher_state(repo)
        blockers = _blockers(repo, line=line, authorship=authorship, pub=pub,
                             rpt=rpt, cp=cp, ledger_block=ledger_block,
                             break_at=break_at,
                             posted_recently=posted_recently)

        return {
            "ok": True,
            "as_of": as_of,
            "produced_at": (cp or {}).get("produced_at") if isinstance(cp, dict) else None,
            "plan_stale": _plan_is_stale(cp) if isinstance(cp, dict) else None,
            "plan_claimed_total": claimed,
            "line": line,
            "break_at": break_at,
            # Stations whose out exceeds their in. Non-empty => the UI must print
            # the "these counters do not nest" sentence instead of a chain verdict.
            "line_odd": line_odd,
            "today": today_block,
            "blockers": blockers,
            "authorship": authorship,
            "publisher": pub,
            "dispatch_ledger": ledger_block,
            "loss": {
                "attractors": _dup_attractors(posts),
                "by_desk": _desk_yield(cp),
                "gate_reasons": _gate_reasons(posts),
            },
            "auditor": _auditor_block(cp),
            "awaiting_review": awaiting,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"floor panel error: {exc}"}


def _auditor_block(cp: dict | None) -> dict:
    """What the batch auditor pulled from tonight's plan, and why.

    The auditor is the operator's stand-in — it cuts posts that read like a bot,
    repeat each other, lecture, or say nothing. Showing only its counts would
    reproduce the exact defect this console was built to fix, so the cut posts
    travel with their text and the reason.
    """
    # The plan's copy census lives under `content.copy` — there is no top-level
    # `report` key and there never has been in any committed vintage. Reading
    # `report.copy.auditor` made this panel report "not run yet" on a plan whose
    # auditor had in fact cut 10 posts, which is the exact class of silent-null
    # defect this module exists to eliminate. Caught by reading a real plan.
    content = ((cp or {}).get("content") or {}) if isinstance(cp, dict) else {}
    blk = ((content.get("copy") or {}).get("auditor") or {}) if isinstance(content, dict) else {}
    if not isinstance(blk, dict) or not blk:
        return {"present": False,
                "note": "The batch auditor has not run over a plan on this host yet."}

    cuts = [c for c in (blk.get("cuts") or []) if isinstance(c, dict)]
    by_reason: Counter[str] = Counter()
    for c in cuts:
        for code in (c.get("codes") or ["unspecified"]):
            by_reason[str(code)] += 1
    words = {
        "bot_voice": "reads like a machine",
        "repetitive": "says what another post already said",
        "lectures": "talks down to the reader",
        "no_thesis": "a stat dump with no argument",
        "makes_no_sense": "does not parse on its own",
        "has_errors": "numbers or output that are wrong",
        "no_value": "true but worthless",
        # Added with the auditor's `esoteric` criterion (2026-08-01). Without a
        # word here the fallback prints the raw slug, and a raw slug on an
        # operator surface is the banned vocabulary the design doctrine names.
        "esoteric": "gestures at macro without naming a print",
    }
    kept, cut = int(blk.get("kept") or 0), int(blk.get("cut") or 0)
    total = kept + cut
    return {
        "present": True,
        "ran": bool(blk.get("ran")),
        "kept": kept,
        "cut": cut,
        "unaudited": int(blk.get("unaudited") or 0),
        "cut_share": round(cut / total, 4) if total else None,
        "error": blk.get("error"),
        "by_reason": [{"code": k, "word": words.get(k, k.replace("_", " ")), "n": v}
                      for k, v in by_reason.most_common()],
        "notes": blk.get("notes") or {},
        "cuts": cuts[:40],
        # A high cut rate is not the auditor being harsh — it is the writer being
        # handed material it cannot say anything new about. Say so, because the
        # operator's next move differs completely between the two readings.
        "verdict": (
            "The auditor is doing the work the supply should be doing: more than "
            "a third of the day was cut. Look upstream at the content mix, not "
            "at the gate." if total and cut / total > 0.33 else
            "Cut rate is in a normal band." if total else
            "Nothing audited yet."),
    }


def _gate_reasons(posts: list[dict]) -> list[dict]:
    """Gate hold reasons, collapsed to families and counted.

    ``near_dup:<id>`` reasons collapse into one family — the per-attractor
    detail lives in :func:`_dup_attractors`, so this stays readable.
    """
    fam: Counter[str] = Counter()
    for p in posts:
        for reason in (p.get("sentinel_reasons") or []):
            s = str(reason)
            fam["near_dup" if s.startswith("near_dup:") else s] += 1
    words = {
        "near_dup": "reads too close to another desk's post",
        "cadence_cap_daily": "over that desk's daily post cap",
        "cashtag_cap": "too many cashtags in one post",
        "slot_collision": "two posts booked into one slot",
        "lexicon": "used a banned phrase",
        "disclosure": "missing a required disclosure",
        "link_rule": "carried a link where links are off",
        "media_cap": "over the desk's daily chart cap",
    }
    return [{"reason": k, "word": words.get(k, k.replace("_", " ")), "n": v}
            for k, v in fam.most_common(14)]


def _publisher_state(repo: Path) -> dict:
    """Is the publisher able to post at all, and if not, exactly what is missing."""
    import os  # noqa: PLC0415
    try:
        cfg = _read_yaml(repo / _CONFIG_REL)
        pub_cfg = (cfg.get("publish") or {}) if isinstance(cfg, dict) else {}
        channels = pub_cfg.get("channels") or {}
        wired = sorted(cid for cid, v in channels.items() if str(v or "").strip())
        token = bool(os.environ.get("BUFFER_TOKEN", "").strip())
        armv = arm_state()
        kill = armv.get("enabled") is True
        # HOST SCOPE IS PART OF THE FACT (2026-08-01 audit, defect F5).
        # ``token_present`` reads THIS process's environment and ``arm_state()``
        # needs a GitHub token to read the repo variable.  On the operator's Mac
        # both come back false/None while the self-hosted runner posts daily —
        # and the Floor rendered that as a rank-1 "Nothing can post" STOP.  A
        # host-local absence is evidence about this host, not about the plant,
        # so it ships labelled and the blocker ranker de-escalates it whenever
        # the ledger shows posts actually going out.
        arm_readable = armv.get("enabled") is not None
        return {
            "backend": pub_cfg.get("backend"),
            "token_present": token,
            "token_scope": "this admin host",
            "arm_readable": arm_readable,
            "channels_wired": wired,
            "channels_total": len(channels),
            "kill_switch_on": kill,
            "arm_state": armv,
            "armed": bool(token and wired and kill),
            # True when every negative in this dict is a local blindness rather
            # than an observed "off".
            "host_local_only": bool(not token or not arm_readable),
        }
    except Exception as exc:  # noqa: BLE001
        return {"armed": False, "error": f"publisher state unreadable: {exc}"}


def _blockers(repo: Path, *, line: list[dict], authorship: dict, pub: dict,
              rpt: dict | None, cp: dict | None,
              ledger_block: dict, break_at: str | None = None,
              posted_recently: bool = False) -> list[dict]:  # noqa: PLR0912, PLR0915
    """What is stopping the factory right now, worst first.

    Each blocker states the cost in posts where a cost is knowable, and names
    the exact next action. A blocker with no action the operator can take says
    so instead of inventing one.
    """
    out: list[dict] = []

    def add(sev: str, title: str, why: str, fix: str, *,
            cost: int | None = None, goto: str | None = None,
            owner: str = "operator") -> None:
        out.append({"severity": sev, "title": title, "why": why, "fix": fix,
                    "cost": cost, "goto": goto, "owner": owner})

    # --- the publisher itself -------------------------------------------
    if not pub.get("armed"):
        missing = []
        if not pub.get("token_present"):
            missing.append("the Buffer token is not set on this host")
        if not pub.get("channels_wired"):
            missing.append("no desk has a channel id wired")
        if not pub.get("kill_switch_on"):
            arm = pub.get("arm_state") or {}
            if arm.get("enabled") is None:
                missing.append("the publish switch state is unknown "
                               "(no GitHub token to read the repo variable)")
            else:
                missing.append("the publish switch is off")
        # DE-ESCALATE A HOST-LOCAL BLINDNESS (2026-08-01 audit, defect F5).
        # Every negative above can be a fact about the ADMIN process rather than
        # about the plant: the operator's Mac has neither BUFFER_TOKEN nor a
        # GitHub token, while the self-hosted runner posts daily. Rendering that
        # as a rank-1 "Nothing can post" STOP told the operator the exact
        # opposite of the truth. When the ledger shows posts inside the last 72h,
        # this is a console blindness, and it says so.
        if posted_recently and pub.get("host_local_only"):
            add("watch", "This console cannot see the publish switch",
                "Posts went out in the last three days, so the publisher is "
                "working. What is missing is local: " + "; ".join(missing) + ". "
                "Those are facts about this admin process, not about the runner "
                "that actually posts.",
                "Nothing to fix in the plant. To read the switch from here, give "
                "this host a GitHub token; the Publisher page shows the same "
                "checklist with the same caveat.",
                goto="marketing_publish")
        else:
            add("stop", "Nothing can post",
                "The publisher is dark: " + "; ".join(missing) + ".",
                "Open the Publisher checklist and clear each line. Until then the "
                "whole line downstream of the gate is decorative.",
                goto="marketing_publish")

    # --- the line's own arithmetic --------------------------------------
    # Surfaced as a blocker, not swallowed: an operator reading a funnel needs
    # to know when two of its counters were written by different passes. The
    # honest fix is upstream measurement, so this one names no button.
    _odd = [st for st in line if st.get("odd")]
    if _odd:
        st = _odd[0]
        add("watch", "Two stations on this line do not nest",
            st.get("odd_note") or (
                f"{st['name']} reports more out than in."),
            "There is nothing to clear here — the counters need to be measured "
            "over the same post set upstream. Until then read the stations from "
            f"{st['name']} onward on their own, not as a chain.",
            owner="engine")

    # --- desks switched off ---------------------------------------------
    disabled = (((rpt or {}).get("checks") or {}).get("kill_switch") or {}).get("accounts_disabled") or []
    if disabled:
        add("high", f"{len(disabled)} desks switched off",
            "These desks are wired but disabled, so their planned posts are "
            "written and gated and then thrown away: " + ", ".join(map(str, disabled)) + ".",
            "Turn a desk back on in Channels & Desks, or drop it from the plan "
            "so the allocator stops spending model calls on it.",
            cost=None, goto="marketing_channels")

    # --- authorship law -------------------------------------------------
    tmpl = authorship.get("template_on_planned_kind") or 0
    if tmpl:
        add("high", "House templates are writing planned posts",
            f"{tmpl} planned posts carry template copy, not model copy. A "
            "planned post is meant to be written by a model or dropped loudly — "
            "template copy here is the word-salad defect, not a safe fallback.",
            "Check the Model Desk. If every provider is refusing, the honest "
            "outcome is an empty queue, not template filler.",
            cost=tmpl, goto="marketing_models")
    nowriter = authorship.get("no_writer_on_planned_kind") or 0
    if nowriter:
        # RANK MUST AGREE WITH THE LINE (2026-08-01 audit, defect F3). The line
        # tagged `written` as the "biggest leak" in loud copy while this — the
        # blocker for that exact loss — sat at severity `watch`, ranked 5th of 6.
        # One screen said "start here" and "this is fine" about the same 149
        # posts. Whichever station the line crowns, its blocker leads.
        add("high" if break_at == "written" else "watch",
            "Some planned posts never reached a writer",
            f"{nowriter} planned posts have no writer stamp at all — they were "
            "allocated a slot and then dropped before any model saw them.",
            "This is the no-fallback law behaving correctly under a dead "
            "provider. The fix is provider capacity on the Model Desk, not the plan.",
            cost=nowriter, goto="marketing_models")

    # --- the dedup attractor -------------------------------------------
    posts = _plan_posts(cp)
    attractors = _dup_attractors(posts, limit=1)
    if attractors and (attractors[0].get("killed") or 0) >= 10:
        a = attractors[0]
        add("high", "One post is killing dozens",
            f"{a['killed']} posts were held as near-duplicates of a single "
            f"{a.get('account') or '?'} post — \"{a.get('headline') or a['post_id']}\". "
            "The gate walks desks in order, so the desk read first keeps its "
            "post and every desk after it collides against it.",
            "Read the collision list on Sentinel. If the duplicates are the "
            "same fact told six ways, the fix is upstream fact supply, not the gate.",
            cost=a.get("killed"), goto="marketing_sentinel")

    # --- cleared but never enqueued ------------------------------------
    for st in line:
        if st["id"] != "enqueued":
            continue
        # DO NOT SPEND A FIGURE FROM A BROKEN CHAIN (2026-08-01 audit, defect F2).
        # This blocker's cost is `cleared - enqueued`. On the live plan `cleared`
        # was the sentinel's count over the WHOLE queue (137) while `written` had
        # measured 7, so the 128 charged here was ~130 posts that never got copy
        # at all — already charged upstream to the `written` station AND to the
        # "never reached a writer" blocker. Triple-counted, and it sent the
        # operator hunting an enqueue gap that does not exist. When the upstream
        # chain is not comparable, this blocker does not fire at all.
        if not st.get("chain_ok", True):
            continue
        if isinstance(st.get("lost"), int) and st["lost"] > 0:
            add("high", "Cleared posts never reached the rail",
                f"{st['lost']} posts passed the gate and never became outbox "
                "items, so no human ever saw them and they cannot post.",
                "Compare the gate's cleared count with the enqueue step in the "
                "nightly publish log — the two should match or the gap should be "
                "an explained trim.",
                cost=st["lost"], goto="marketing_outbox")

    # --- dispatch losses ------------------------------------------------
    if ledger_block.get("present"):
        big = [ln for ln in (ledger_block.get("lines") or [])
               if ln["is_loss"] and ln["n"] > 0]
        if big:
            top = big[0]
            add("watch", "Posts are dying at dispatch",
                f"The last publish sweep lost {ledger_block.get('lost_total')} "
                f"items; the biggest single cause was \"{top['word']}\" ({top['n']}).",
                "The full counter list is on this page under “Where tonight's "
                "posts went”. Each counter is a gate you can loosen in config.",
                cost=ledger_block.get("lost_total"), goto="marketing_publish")
        elif ledger_block.get("posted") == 0:
            add("watch", "The sweep ran and posted nothing",
                "The publisher woke, found nothing eligible, and logged zeroes "
                "across every counter. That is an empty rail, not a blocked one.",
                "Look upstream: the queue station on this line is where to walk.",
                goto="marketing_outbox")

    # --- staleness ------------------------------------------------------
    if isinstance(cp, dict) and _plan_is_stale(cp):
        add("watch", "Tonight's plan is yesterday's",
            f"The plan on disk is dated {cp.get('as_of')} — the nightly "
            "governor has not written a fresh one.",
            "Check the nightly run. Everything on this page describes the old "
            "plan until it re-bakes.",
            goto="marketing_content")

    ht = _read_json(repo / _HOT_TAPE_REL)
    if isinstance(ht, dict):
        age = _age_days(ht.get("trade_date"))
        if age is not None and age >= 2:
            add("watch", "The hot-tape pack is stale",
                f"The tape pack's trade date is {ht.get('trade_date')} "
                f"({age} days old), so the five-minute lane is reacting to old prices.",
                "Check the hot-tape build step in the nightly.",
                goto="marketing_lanes")

    order = {"stop": 0, "high": 1, "watch": 2}
    out.sort(key=lambda b: (order.get(b["severity"], 3), -(b.get("cost") or 0)))
    for i, b in enumerate(out, 1):
        b["rank"] = i
    return out


# ---------------------------------------------------------------------------
# 2 · MODEL DESK — who writes the words, and the key-pool balancer
# ---------------------------------------------------------------------------
def _dig(cfg: Any, path: list[str]) -> dict | None:
    node = cfg
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, dict) else None


def models(root=None) -> dict:
    """Per-lane model routing plus the OAuth key-pool balancer's belief state."""
    repo = Path(root) if root is not None else _default_root()
    try:
        cfg = _read_yaml(repo / _CONFIG_REL) or {}
        lanes: list[dict] = []
        for spec in _LLM_LANES:
            node = _dig(cfg, spec["path"]) or {}
            order = node.get("provider_order") or ["codex", "oauth", "anthropic", "deepseek"]
            codex_model = node.get("codex_source_model") or "gpt-5.6-terra"
            tier, tier_word = _CODEX_TIERS.get(str(codex_model), (str(codex_model), ""))
            lanes.append({
                "id": spec["id"],
                "name": spec["name"],
                "job": spec["job"],
                "config_path": ".".join(spec["path"]),
                "configured": bool(node),
                "enabled": node.get("enabled") if "enabled" in node else None,
                "provider_order": list(order),
                "first_choice": (list(order) or [None])[0],
                "codex_model": codex_model,
                "codex_tier": tier,
                "codex_tier_word": tier_word,
                "effort": node.get("codex_reasoning_effort") or "medium",
                "pool_lane": node.get("oauth_pool_lane") or spec["pool_lane"],
                "source": "config/marketing.yml" if node else "code default",
            })

        pool = _pool_health(repo)
        return {
            "ok": True,
            "as_of": _utcnow().strftime("%Y-%m-%d"),
            "lanes": lanes,
            "waterfall": [
                {"rung": "codex", "name": "ChatGPT (Codex)",
                 "what": "Primary. Idle capacity and generous limits — the "
                         "operator's default for all marketing authorship."},
                {"rung": "oauth", "name": "Claude key pool",
                 "what": "Fallback, load-balanced across the OAuth keys below."},
                {"rung": "anthropic", "name": "Anthropic API key",
                 "what": "Fallback behind the pool, if a key is set."},
                {"rung": "deepseek", "name": "DeepSeek",
                 "what": "Last rung before the lane goes quiet."},
            ],
            "pool": pool,
            "ledger": _key_ledger(repo),
            "law": ("A lane that exhausts every rung writes nothing and says so. "
                    "It never falls back to a house template."),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"model desk error: {exc}"}


def _pool_health(repo: Path) -> dict:
    """Per-key balancer state from key_pool.usage_snapshot().

    Carries capability-id NAMES, cooling state and load only. No token value
    crosses this boundary (capability redline).
    """
    try:
        from engine.neuralweb.key_pool import (  # noqa: PLC0415
            POOL_CAPABILITY_IDS,
            usage_snapshot,
        )
    except Exception:  # noqa: BLE001
        return {"available": False,
                "note": "The key-pool module is not importable in this "
                        "environment, so per-key load cannot be read here."}
    try:
        rows = usage_snapshot(repo) or []
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "note": f"key pool read failed: {exc}"}

    # usage_snapshot covers the balanced Claude pool AND the single-key
    # providers (codex, deepseek). They are different things and must not share
    # a heading: only the pool rows are load-balanced, so filing codex_account
    # under "Claude key pool" would misreport what the balancer does.
    pool_ids = set(POOL_CAPABILITY_IDS or ())

    keys: list[dict] = []
    providers: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        present = bool(r.get("present"))
        cooling = bool(r.get("cooling"))
        enabled = r.get("enabled")
        if not present:
            state, word = "absent", "not set on this host"
        elif cooling:
            state, word = "cooling", "rate-limited — resting"
        elif enabled is False:
            state, word = "off", "switched off"
        else:
            state, word = "ready", "ready to serve"
        row = {
            "key_id": r.get("key_id"),
            "state": state,
            "state_word": word,
            "present": present,
            "enabled": enabled,
            "cooling": cooling,
            "cool_kind": r.get("cool_kind"),
            "reset_hint": r.get("reset_hint"),
            # Load figures are meaningless for a key that is not set here — an
            # absent key's "0 tokens this window" reads as idle capacity when
            # the truth is there is no key at all.
            "window_5h_est_tokens": r.get("window_5h_est_tokens") if present else None,
            "weekly_est_tokens": r.get("weekly_est_tokens") if present else None,
            "window_5h_sessions": r.get("window_5h_sessions") if present else None,
            "weekly_sessions": r.get("weekly_sessions") if present else None,
            "last_outcome": r.get("last_outcome"),
            "last_ts": r.get("last_ts"),
        }
        (keys if str(r.get("key_id")) in pool_ids else providers).append(row)

    order = {"ready": 0, "cooling": 1, "off": 2, "absent": 3}
    keys.sort(key=lambda k: (order.get(k["state"], 4), str(k["key_id"])))
    providers.sort(key=lambda k: (order.get(k["state"], 4), str(k["key_id"])))
    ready = sum(1 for k in keys if k["state"] == "ready")
    return {
        "available": True,
        "keys": keys,
        "providers": providers,
        "ready": ready,
        "cooling": sum(1 for k in keys if k["state"] == "cooling"),
        "absent": sum(1 for k in keys if k["state"] == "absent"),
        "total": len(keys),
        "verdict": ("The pool can serve a fallback call." if ready else
                    "No key in the pool can serve right now — a lane that "
                    "reaches this rung falls through to the next one."),
    }


def _key_ledger(repo: Path, tail: int = 60) -> dict:
    """Recent balancer decisions from the key ledger.

    The ledger is the balancer's audit trail: one row per accepted call or
    cooling event. It answers "is the load actually spread" — the question the
    operator asked when he pointed at the dashboard.
    """
    rows = _read_jsonl(repo / _KEY_LEDGER_REL) or []
    if not rows:
        return {"present": False, "rows": 0,
                "note": "No balancer decisions recorded on this host yet."}
    by_key: Counter[str] = Counter()
    by_outcome: Counter[str] = Counter()
    by_stage: Counter[str] = Counter()
    for r in rows:
        if not isinstance(r, dict):
            continue
        by_key[str(r.get("key_id") or "?")] += 1
        by_outcome[str(r.get("outcome") or "?")] += 1
        by_stage[str(r.get("stage") or "?")] += 1
    recent = [r for r in rows[-tail:] if isinstance(r, dict)]
    recent.reverse()
    return {
        "present": True,
        "rows": len(rows),
        "by_key": dict(by_key.most_common()),
        "by_outcome": dict(by_outcome.most_common()),
        "by_stage": dict(by_stage.most_common()),
        "recent": [{
            "ts": r.get("ts"), "key_id": r.get("key_id"), "stage": r.get("stage"),
            "outcome": r.get("outcome"), "cool_kind": r.get("cool_kind"),
            "reset_hint": r.get("reset_hint"), "est_tokens": r.get("est_tokens"),
        } for r in recent],
        "last_at": (rows[-1] or {}).get("ts") if isinstance(rows[-1], dict) else None,
    }


# ---------------------------------------------------------------------------
# 3 · X LANES — the growth lanes, live or dark
# ---------------------------------------------------------------------------
def _lane(lid: str, name: str, what: str, *, state: str, state_word: str,
          fresh: str | None = None, detail: str | None = None,
          numbers: dict | None = None, goto: str | None = None) -> dict:
    return {"id": lid, "name": name, "what": what, "state": state,
            "state_word": state_word, "fresh": fresh, "detail": detail,
            "numbers": numbers or {}, "goto": goto}


def lanes(root=None) -> dict:  # noqa: PLR0912, PLR0915
    """One row per X-growth lane: is it running, how fresh, what did it last do.

    These lanes shipped across the E-waves and had no console surface at all —
    the operator could not tell a live lane from a dead one.
    """
    repo = Path(root) if root is not None else _default_root()
    try:
        rows: list[dict] = []

        # --- nightly plan lane ---------------------------------------------
        cp = _read_json(repo / _CONTENT_REL)
        if isinstance(cp, dict):
            stale = _plan_is_stale(cp)
            n = len(_plan_posts(cp))
            rows.append(_lane(
                "plan", "Nightly plan", "Writes the whole day's posts before dawn",
                state="stale" if stale else "live",
                state_word="running on an old plan" if stale else "fresh tonight",
                fresh=cp.get("as_of"),
                numbers={"posts": n},
                detail=f"{n} posts planned for {cp.get('as_of')}",
                goto="marketing_content"))
        else:
            rows.append(_lane("plan", "Nightly plan",
                              "Writes the whole day's posts before dawn",
                              state="dark", state_word="no plan on disk",
                              goto="marketing_content"))

        # --- hot tape ------------------------------------------------------
        ht = _read_json(repo / _HOT_TAPE_REL)
        if isinstance(ht, dict):
            age = _age_days(ht.get("trade_date"))
            rows.append(_lane(
                "hot_tape", "Hot tape", "Reacts to moving names every five minutes",
                state="stale" if (age or 0) >= 2 else "live",
                state_word=(f"tape is {age} days old" if (age or 0) >= 2
                            else "tape is current"),
                fresh=ht.get("trade_date"),
                numbers={"tickers": ht.get("n_tickers")},
                detail=f"{ht.get('n_tickers')} names in the pack, built {ht.get('built_at')}",
                goto="marketing_radar"))
        else:
            rows.append(_lane("hot_tape", "Hot tape",
                              "Reacts to moving names every five minutes",
                              state="dark", state_word="no tape pack on disk"))

        # --- press / breaking wire -----------------------------------------
        press = _read_jsonl(repo / _PRESS_PUBLISHED_REL) or []
        if press:
            last = press[-1] if isinstance(press[-1], dict) else {}
            age_h = _age_hours(last.get("published_at") or last.get("at") or last.get("ts"))
            rows.append(_lane(
                "press", "Press wire", "Turns policy and press headlines into posts",
                state="live" if (age_h is not None and age_h <= 48) else "quiet",
                state_word=(f"last item {age_h:.0f}h ago" if age_h is not None
                            else "last item time unknown"),
                fresh=str(last.get("published_at") or last.get("at") or "")[:19] or None,
                numbers={"published": len(press)},
                detail=f"{len(press)} press items published all-time"))
        else:
            rows.append(_lane("press", "Press wire",
                              "Turns policy and press headlines into posts",
                              state="accruing", state_word="nothing published yet",
                              detail="The wire runs in Actions; this host holds no "
                                     "published rows."))

        # --- replies -------------------------------------------------------
        replies = _read_jsonl(repo / _REPLY_STORE_REL) or []
        rows.append(_lane(
            "replies", "Reply desk", "Drafts replies in each desk's own voice",
            state="live" if replies else "accruing",
            state_word=f"{len(replies)} drafts on file" if replies else "no drafts yet",
            numbers={"drafts": len(replies)},
            goto="marketing_reply_queue"))

        # --- competitive intel + exemplars ---------------------------------
        intel_files = []
        try:
            d = repo / _X_INTEL_DIR
            if d.is_dir():
                intel_files = sorted(p.name for p in d.iterdir() if p.is_file())
        except Exception:  # noqa: BLE001
            intel_files = []
        ex = _read_json(repo / _EXEMPLAR_REL)
        if intel_files or isinstance(ex, dict):
            active = (ex or {}).get("active_version") if isinstance(ex, dict) else None
            rows.append(_lane(
                "intel", "Competitive intel", "Harvests what works on other desks",
                state="live" if active else "shadow",
                state_word=("promoted set in use" if active
                            else "harvesting — nothing promoted"),
                numbers={"files": len(intel_files)},
                detail=("A harvested set only becomes active when you pin it in "
                        "config; nothing promotes itself.")))
        else:
            rows.append(_lane("intel", "Competitive intel",
                              "Harvests what works on other desks",
                              state="accruing", state_word="no harvest on disk yet"))

        # --- filings -------------------------------------------------------
        filing_kinds = Counter()
        for p in _plan_posts(cp):
            k = str(p.get("type") or "")
            if k in ("congress", "insider"):
                filing_kinds[k] += 1
        rows.append(_lane(
            "filings", "Filing desk", "Posts disclosed congress and insider trades",
            state="live" if filing_kinds else "dark",
            state_word=(f"{sum(filing_kinds.values())} filing posts in tonight's plan"
                        if filing_kinds else "no filing posts planned tonight"),
            numbers=dict(filing_kinds),
            detail=("Every filing post must carry its reporting lag — a disclosed "
                    "trade is weeks old news by the time it is public."),
            goto="marketing_content"))

        # --- engagement measurement ----------------------------------------
        metrics = _read_jsonl(repo / _POST_METRICS_REL) or []
        nonzero = 0
        for m in metrics:
            if not isinstance(m, dict):
                continue
            mm = m.get("metrics") or {}
            if any((mm.get(k) or 0) for k in ("likes", "impressions", "reposts", "comments")):
                nonzero += 1
        rows.append(_lane(
            "measure", "Engagement readback", "Reads what the posts actually did",
            state="live" if nonzero else "accruing",
            state_word=(f"{nonzero} of {len(metrics)} posts have any engagement"
                        if metrics else "no readings yet"),
            numbers={"polled": len(metrics), "with_engagement": nonzero},
            detail=("Every reading is zero so far. That is an honest reading of a "
                    "cold-start account, not a broken poller — but it means no "
                    "learning signal can be scored yet."
                    if metrics and not nonzero else None),
            goto="marketing_learning"))

        # --- learning tripwires --------------------------------------------
        health = _read_json(repo / _LEARNING_HEALTH_REL)
        if isinstance(health, dict):
            halted = health.get("halted") or []
            rows.append(_lane(
                "learning", "Learning tripwires", "Halts a desk that is going wrong",
                state="tripped" if halted else "live",
                state_word=(f"{len(halted)} desks halted" if halted
                            else "watching — nothing halted"),
                fresh=health.get("as_of"),
                numbers={"halted": len(halted)},
                goto="marketing_health"))

        order = {"dark": 0, "tripped": 1, "stale": 2, "quiet": 3,
                 "accruing": 4, "shadow": 5, "live": 6}
        rows.sort(key=lambda r: order.get(r["state"], 9))
        return {
            "ok": True,
            "as_of": _utcnow().strftime("%Y-%m-%d"),
            "lanes": rows,
            "counts": dict(Counter(r["state"] for r in rows)),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"lanes panel error: {exc}"}
