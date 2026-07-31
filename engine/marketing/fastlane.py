"""engine.marketing.fastlane — Pure, testable loop body for the earnings fast lane.

Processes a batch of raw earnings events through the full pipeline:
  poll → dedupe → eligibility → copy generation → validate → card render → emit outbox.

Public API:
    run_tick(events, *, root, now, universe=None) -> TickResult

TickResult is a dict with three keys:
    {
        "emitted":     list[dict],   # events that produced an outbox item
        "skipped":     list[dict],   # events not processed (dedupe / ineligible)
        "quarantined": list[dict],   # events processed but with copy violations
    }

Each entry in emitted / skipped / quarantined is a dict with at least:
    {"id": str, "ticker": str, "reason": str | None}

Outbox contract (D02 → XG-W2):
    This emitter used to hand-roll `data/marketing/outbox/<id>.json` with its own
    schema ({"text": {"headline", "body"}, "priority": "high", "provenance": {…}}).
    Nothing read that file — the publisher folds items.jsonl — so every earnings
    emission also skipped the id-dedup, text-dedup and near-dup guards that live
    in outbox.enqueue().  XG-W2 moved the lane onto the canonical path:
    outbox.make_item() → outbox.validate_item() → outbox.enqueue(), kind
    "earnings" (admitted to outbox.KINDS in the same wave), text FLATTENED to the
    real post string (outbox.compose_text), the rich event record
    carried in `source`, and the account RESOLVED from the wire_routing config
    map instead of a module constant.

Ledger:
    data/marketing/fastlane_seen.jsonl is daemon-local state.  It is append-only
    and must NEVER be committed (enforced via .gitignore).  The file is loaded at
    the start of each run_tick call so deduplication survives daemon restarts.

Universe eligibility:
    When universe=None the ticker set is derived cheaply from
    site/marketdata/sp500_heatmap.json (the same source movers_source.py uses).
    An injectable universe set is used in tests to avoid filesystem reads.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_SEEN_LEDGER_PATH = Path("data/marketing/fastlane_seen.jsonl")
_QUARANTINE_LEDGER_PATH = Path("data/marketing/fastlane_quarantine.jsonl")
_OUTBOX_DIR = Path("data/marketing/outbox")
_MEDIA_DIR = _OUTBOX_DIR / "media"

# XG-W2: the earnings lane's account is resolved from the same `wire_routing:`
# config map the press lane uses (class "earnings"), so a second hardcoded
# account cannot quietly outlive the first. The map ships routing earnings to
# flagship, i.e. today's behaviour, expressed as config instead of a constant.
_FALLBACK_ACCOUNT = "flagship"

# Earnings is a breaking-class post: it sorts ahead of the ladder. The publisher
# orders by (priority, scheduled_at, id) with a default of 5, so 1 is first.
# The pre-XG-W2 raw writer wrote the string "high", which make_item rejects.
_EARNINGS_PRIORITY = 1

# Bump this constant whenever the copy template changes so that previously
# quarantined events are retried against the new template.
TEMPLATE_VERSION = 2


# ─────────────────────────────────────────────────────────────────────────────
# Session-window tagging
# ─────────────────────────────────────────────────────────────────────────────

def _session_window(when_iso: str) -> str:
    """Tag an event's market-session window.

    Returns "premarket", "rth", or "postmarket" based on Eastern Time.
    Falls back to "rth" if parsing fails (fail-soft).

    Premarket:   before 09:30 ET
    RTH:         09:30–16:00 ET
    Post-market: after  16:00 ET
    """
    try:
        from zoneinfo import ZoneInfo  # Python 3.9+
        et = ZoneInfo("America/New_York")
        dt_utc = datetime.fromisoformat(when_iso).replace(tzinfo=timezone.utc)
        dt_et = dt_utc.astimezone(et)
        hour_min = dt_et.hour * 60 + dt_et.minute
        if hour_min < 9 * 60 + 30:
            return "premarket"
        if hour_min >= 16 * 60:
            return "postmarket"
        return "rth"
    except Exception:  # noqa: BLE001
        return "rth"


# ─────────────────────────────────────────────────────────────────────────────
# Seen-ledger helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_seen(root: Path) -> set[str]:
    """Load the append-only seen-ledger and return the set of event ids."""
    path = root / _SEEN_LEDGER_PATH
    if not path.exists():
        return set()
    seen: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                seen.add(str(rec["id"]))
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        logger.warning("[fastlane] seen-ledger load error: %s", exc)
    return seen


def _append_seen(root: Path, event_id: str, *, dry_run: bool = False) -> None:
    """Append one id record to the seen-ledger (create parent dirs as needed)."""
    if dry_run:
        return
    path = root / _SEEN_LEDGER_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": event_id}) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.error("[fastlane] seen-ledger append error: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Quarantine ledger helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_quarantined(root: Path) -> set[tuple[str, int]]:
    """Load quarantine ledger; return set of (event_id, template_version) pairs."""
    path = root / _QUARANTINE_LEDGER_PATH
    if not path.exists():
        return set()
    result: set[tuple[str, int]] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                result.add((str(rec["event_id"]), int(rec["template_version"])))
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        logger.warning("[fastlane] quarantine-ledger load error: %s", exc)
    return result


def _append_quarantine(
    root: Path,
    event_id: str,
    reasons: list[str],
    *,
    dry_run: bool = False,
) -> None:
    """Append a quarantine record to the separate quarantine ledger."""
    if dry_run:
        return
    path = root / _QUARANTINE_LEDGER_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "event_id": event_id,
            "template_version": TEMPLATE_VERSION,
            "reasons": reasons,
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.error("[fastlane] quarantine-ledger append error: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Universe loader
# ─────────────────────────────────────────────────────────────────────────────

def _load_universe(root: Path) -> set[str] | None:
    """Derive eligible tickers cheaply from site/marketdata/sp500_heatmap.json.

    Returns a set of uppercase ticker strings on success.
    Returns None when the file is missing or broken, signalling that the
    universe is *unavailable* (as opposed to genuinely empty).  Callers must
    treat None fail-closed — skip all events when the universe cannot be loaded.
    """
    path = root / "site" / "marketdata" / "sp500_heatmap.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        tiles: list[dict] = data.get("tiles") or []
        return {str(t.get("t", "")).upper() for t in tiles if t.get("t")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[fastlane] universe load from sp500_heatmap failed: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Earnings copy builder (Scorekeeper persona)
# ─────────────────────────────────────────────────────────────────────────────

def _build_earnings_copy(event: dict[str, Any]) -> dict[str, Any]:
    """Build headline + body copy for an earnings event.

    Uses the Scorekeeper persona from config/marketing.yml ("blunt, numbers-first,
    zero spin; wins and losses with the same flat tone; everything resolves to a
    number; emoji budget: 1 (🧾)").

    All numbers included in copy are also placed in the numbers_whitelist so
    validate_copy() can clear them cleanly.

    Returns a dict compatible with build_context():
        {ticker, cashtag, type, account, numbers_whitelist, persona, ...}
    plus derived fields needed by validate_copy:
        {headline, body}
    """
    ticker = event.get("ticker", "").upper()
    cashtag = f"${ticker}"
    eps_actual: float = float(event.get("eps_actual", 0.0))
    eps_est: float = float(event.get("eps_est", eps_actual))
    rev_actual: float | None = event.get("rev_actual")
    rev_est: float | None = event.get("rev_est")
    quarter: str | None = event.get("quarter")
    session: str = event.get("_session", "rth")

    # ── Classify beat/miss/inline ────────────────────────────────────────────
    if eps_est == 0:
        surp_pct = 0.0
    else:
        surp_pct = (eps_actual - eps_est) / abs(eps_est) * 100.0

    if abs(surp_pct) < 0.5:
        verdict = "INLINE"
    elif eps_actual > eps_est:
        verdict = "BEAT"
    else:
        verdict = "MISS"

    sign = "+" if surp_pct >= 0 else ""
    surp_str = f"{sign}{surp_pct:.1f}%"

    # ── Format number strings ────────────────────────────────────────────────
    def _fmt_eps(v: float) -> str:
        return f"{v:.2f}"

    def _fmt_rev(v: float) -> str:
        # Always use unit suffixes — never comma-grouped integers.
        # validate_copy tokenises on whitespace/punctuation; "500,000" splits
        # into "500" and "000", neither of which is whitelisted, causing a
        # spurious quarantine.  "$0.50M" tokenises as "0.50M" — one clean token.
        if v >= 1e12:
            return f"{v / 1e12:.2f}T"
        if v >= 1e9:
            return f"{v / 1e9:.2f}B"
        if v >= 1e6:
            return f"{v / 1e6:.2f}M"
        return f"{v / 1e6:.2f}M"

    eps_a_str = _fmt_eps(eps_actual)
    eps_e_str = _fmt_eps(eps_est)
    q_label = f" ({quarter})" if quarter else ""

    # Build numbers whitelist — every numeric token that appears in copy.
    # Include the year from the quarter label (e.g. "2026" in "Q2 2026") since
    # the number-regex catches 4-digit bare integers.
    whitelist: list[str] = [eps_a_str, eps_e_str, surp_str]
    if quarter:
        import re as _re
        for _yr in _re.findall(r"\b\d{4}\b", quarter):
            if _yr not in whitelist:
                whitelist.append(_yr)

    # Revenue strings
    rev_a_str: str | None = None
    rev_e_str: str | None = None
    rev_surp_str: str | None = None
    if rev_actual is not None and rev_est is not None:
        rev_a_str = _fmt_rev(rev_actual)
        rev_e_str = _fmt_rev(rev_est)
        if rev_est != 0:
            rev_surp_pct = (rev_actual - rev_est) / abs(rev_est) * 100.0
            rev_sign = "+" if rev_surp_pct >= 0 else ""
            rev_surp_str = f"{rev_sign}{rev_surp_pct:.1f}%"
        # The revenue FIGURES are computed (the card still draws them) but no
        # longer appear in the post's words, so they must NOT be whitelisted.
        # The whitelist is what certifies a number as vouched-for; listing one
        # the copy never says widens the certificate for nothing, which is the
        # quiet direction for a guard to weaken in.

    # ── Scorekeeper-voice copy ───────────────────────────────────────────────
    # Persona: "everything resolves to a number; emoji budget: 1 (🧾)"
    # Rule: EPS $ actual vs $ est — beat/miss by Z%.
    session_note = {
        "premarket": "Pre-market earnings drop.",
        "postmarket": "After-hours earnings drop.",
        "rth": "Earnings out.",
    }.get(session, "Earnings out.")

    # SIX NUMBERS AND NO POINT OF VIEW (2026-07-31). This template emitted
    # "🧾 $AAPL (Q3 2026) earnings: BEAT. / EPS $2.11 vs $1.98 est (+6.6%).
    # Rev $98.40B vs $97.10B est (+1.3%). After-hours earnings drop." — six
    # distinct figures against a house budget of two, an emoji lead, a shouted
    # verdict, and not one word that costs us anything. It is the machine voice
    # the operator graded F, and the lane is only dark by accident: nothing runs
    # `--lane earnings`, so it has never been seen on a timeline.
    #
    # Rewritten to the two laws it was breaking:
    #   * NUMBERS ARE THE POINT, BUT ONLY THE ONES THAT ARE. The EPS pair and
    #     its surprise are the claim; the revenue pair is the same claim told
    #     twice, so it goes into WORDS. Three figures, inside the budget of four
    #     that `earnings` now carries for exactly this reason.
    #   * A FACT PLUS A REACTION THAT COSTS US. "We don't trade the print"
    #     concedes that we are not acting on the thing we just reported, which
    #     is the admission the house voice is built on, and it is true.
    # A VERB, NOT A LABEL. `verdict` is BEAT/MISS/INLINE — a machine token, and
    # lowercasing it straight into a sentence produced "$AAPL miss on the
    # Q3 2026", which is not English and reads exactly as generated as it is.
    _verb = {"BEAT": "beat", "MISS": "missed"}.get(verdict, "came in line")
    _period = q_label.strip("() ") or "the quarter"
    headline = f"{cashtag} {_verb} on {_period}."

    body_parts = [f"EPS ${eps_a_str} against ${eps_e_str} expected, {surp_str}."]
    if rev_a_str and rev_e_str:
        # The revenue LEG in words: same fact, no second pair of figures.
        _rev_dir = ("came in ahead too" if (rev_surp_str or "").startswith("+")
                    else "came in light")
        body_parts.append(f"Revenue {_rev_dir}.")
    body_parts.append(session_note)
    body_parts.append("We don't trade the print, we trade what the tape does with it.")
    body = " ".join(body_parts)

    # Dedupe whitelist
    seen_wl: set[str] = set()
    unique_whitelist: list[str] = []
    for item in whitelist:
        if item not in seen_wl:
            seen_wl.add(item)
            unique_whitelist.append(item)

    # build_context()-compatible dict so validate_copy() works directly
    ctx = {
        "ticker": ticker,
        "cashtag": cashtag,
        "type": "earnings",   # not a standard content_type; validate_copy won't
                               # apply signal/theme rules to it
        # Overwritten by run_tick with the ROUTED account before validate_copy
        # runs (XG-W2). Kept as a default here so the function stays a pure
        # single-argument builder — the tests monkeypatch it with that shape.
        "account": _FALLBACK_ACCOUNT,
        "numbers_whitelist": unique_whitelist,
        "emoji_budget": 1,    # Scorekeeper allows 1 emoji
        "voice": "dry, receipts-forward",
        "persona_name": "The Scorekeeper",
    }
    return {"ctx": ctx, "headline": headline, "body": body}


# ─────────────────────────────────────────────────────────────────────────────
# Outbox writer
# ─────────────────────────────────────────────────────────────────────────────

def _story_key_for(event: dict[str, Any]) -> str:
    """The one-owner lock identity for an earnings event."""
    try:
        from engine.marketing.story_lock import story_key  # noqa: PLC0415

        ticker = str(event.get("ticker") or "").upper()
        quarter = str(event.get("quarter") or "")
        cluster = f"earnings:{ticker}:{quarter}" if ticker else ""
        return story_key(cluster_key=cluster, event_id=event.get("id"))
    except Exception:  # noqa: BLE001
        return ""


def _story_locked(account: str, key: str, *, root: Path, now: datetime,
                  cfg: dict | None) -> bool:
    """True when ANOTHER account already owns this story inside the window.

    Fail-soft: a lock that cannot read its state returns False (proceed) rather
    than becoming a silent publication stopper.
    """
    if not key:
        return False
    try:
        from engine.marketing import outbox as _ob  # noqa: PLC0415
        from engine.marketing import story_lock as _sl  # noqa: PLC0415

        verdict = _sl.check(account, key, _ob.read_items_all(root), now=now, cfg=cfg)
        if not verdict.allowed:
            logger.info("[fastlane] story %s already owned by %s — standing down",
                        key, verdict.owner)
        return not verdict.allowed
    except Exception as exc:  # noqa: BLE001
        logger.warning("[fastlane] story lock unavailable (%s) — proceeding", exc)
        return False


def _route_account(cfg: dict | None, root: Path) -> str:
    """The account that owns an earnings emission (XG-W2 wire routing).

    Fail-soft to the historical flagship — a routing lookup must never stop an
    earnings post from emitting at all.
    """
    try:
        from engine.marketing.wire_routing import route  # noqa: PLC0415

        return route("earnings", cfg=cfg, root=root)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[fastlane] wire routing failed (%s) — using %s",
                       exc, _FALLBACK_ACCOUNT)
        return _FALLBACK_ACCOUNT


def _emit_outbox(
    root: Path,
    event: dict[str, Any],
    account: str,
    headline: str,
    body: str,
    svg: str,
    now: datetime,
    *,
    story_key: str = "",
    dry_run: bool = False,
    cfg: dict | None = None,
    spool: bool = False,
) -> dict[str, Any] | None:
    """Build a CANONICAL outbox item (kind='earnings') and enqueue it.

    XG-W2 replaced the hand-rolled ``data/marketing/outbox/<id>.json`` writer this
    used to be. That file shape had no reader — the publisher folds
    ``items.jsonl`` and nothing else — so every earnings emission bypassed
    ``make_item``/``validate_item`` and the id-dedup, text-dedup, same-account
    near-dup and cross-account near-dup guards that live in ``enqueue``.

    Returns the item, or None when validation or the queue refused it.
    ``dry_run`` builds and validates but writes nothing.
    """
    from engine.marketing import outbox as _ob  # noqa: PLC0415

    event_id: str = str(event["id"])
    media_rel = f"data/marketing/outbox/media/{event_id}.svg"
    as_of = now.astimezone(timezone.utc).strftime("%Y-%m-%d")

    try:
        item = _ob.make_item(
            account=account,
            kind="earnings",
            text=_ob.compose_text(headline, body),
            as_of=as_of,
            # Media keeps its historical filename (the EVENT id); only the item
            # id becomes canonical (ob-<as_of>-<hash>, derived from the copy).
            media=[{"kind": "chart_svg", "path": media_rel, "chart_id": event_id}],
            # Explicit sentinel, not an absent key: the publisher decides the
            # breaking path off scheduled_at (_is_immediate), and the admin
            # renders it.
            scheduled_at="immediate",
            priority=_EARNINGS_PRIORITY,
            provenance="fastlane",
            source={
                "lane": "earnings",
                "event_id": event_id,
                "story_key": story_key,
                **{k: v for k, v in event.items() if not str(k).startswith("_")},
                "source": event.get("source", "unknown"),
            },
            now=now,
        )
    except ValueError as exc:
        print(f"::warning title=fastlane-item-invalid::{event_id}: {exc}", flush=True)
        return None

    # Additive fields the canonical schema has no slot for; validate_item does
    # not reject extras and each is read downstream (see press_lane).
    item["immediate"] = True
    item["headline"] = headline
    item["body"] = body

    errors = _ob.validate_item(item)
    if errors:
        print(f"::warning title=fastlane-item-invalid::{event_id}: {errors[0]}",
              flush=True)
        return None

    if dry_run:
        return item

    media_path = root / _MEDIA_DIR / f"{event_id}.svg"
    media_path.parent.mkdir(parents=True, exist_ok=True)
    # Write via temp+replace to avoid torn writes (law from mm-data-guard lessons)
    import os  # noqa: PLC0415
    import tempfile  # noqa: PLC0415
    tmp_fd, tmp_path = tempfile.mkstemp(dir=media_path.parent, suffix=".svg.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(svg)
        os.replace(tmp_path, media_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    result = _ob.enqueue(item, root, cfg=cfg, spool=spool)
    if result != "queued":
        print(f"::warning title=fastlane-not-queued::{event_id} refused by the "
              f"outbox: {result}", flush=True)
        return None
    return item


# ─────────────────────────────────────────────────────────────────────────────
# Public: run_tick
# ─────────────────────────────────────────────────────────────────────────────

def run_tick(
    events: list[dict[str, Any]],
    *,
    root: Path | str,
    now: datetime,
    universe: set[str] | None = None,
    dry_run: bool = False,
    cta: bool = True,
    cfg: dict | None = None,
    spool: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """Process one tick of earnings events through the fast-lane pipeline.

    Args:
        events:   Raw event dicts from fetch_events() (see earnings_feed.py schema).
        root:     Repository root path.  Used to locate the seen-ledger, sp500
                  heatmap (when universe=None), and the outbox output dirs.
        now:      Current UTC datetime (injectable for tests).
        universe: Set of eligible uppercase tickers.  When None, derived from
                  site/marketdata/sp500_heatmap.json (cheapest read available).
        dry_run:  When True, computes everything but writes nothing to disk.
        cta:      publish.chart_cta_enabled — False renders the earnings card
                  footer without the trial button (URL lockup stays). The caller
                  resolves it from config; the default keeps the legacy card for
                  any caller that has no config in hand.
        spool:    True routes the emission to the GITIGNORED daemon-local
                  outbox spool instead of the git-TRACKED items.jsonl. The VPS
                  daemon sets it so a tick cannot dirty the checkout its
                  3-minute `git pull` depends on. Read-side guards read the
                  union of both files, so nothing is weakened.
        cfg:      The full config/marketing.yml dict (XG-W2). Read for wire
                  routing, the one-owner lock window, and the cross-account
                  near-dup threshold. None (the default) keeps every one of
                  those on its in-code fallback, which is the pre-XG-W2
                  behaviour — so a caller with no config in hand still works.

    Returns:
        {
            "emitted":     list of emitted outbox items (full dicts),
            "skipped":     list of {id, ticker, reason} skip records,
            "quarantined": list of {id, ticker, reason, violations} records,
        }
    """
    from engine.marketing.copywriter import validate_copy
    from engine.marketing.chart_render import render_earnings_card

    root = Path(root)

    # ── Load seen-ledger (dedupe survives restarts) ───────────────────────────
    seen_ids: set[str] = _load_seen(root)

    # ── Load quarantine ledger (version-keyed) ────────────────────────────────
    quarantined_keys: set[tuple[str, int]] = _load_quarantined(root)

    # ── Resolve universe (fail-closed) ───────────────────────────────────────
    # universe=None means "not injected by caller" — load from disk.
    # _load_universe returns None when the file is missing/broken; that is
    # distinct from an empty set (genuinely no tickers).  When None, we must
    # fail-closed: skip ALL events until the universe is available.
    _universe_unavailable: bool = False
    if universe is None:
        loaded = _load_universe(root)
        if loaded is None:
            _universe_unavailable = True
            universe = set()  # placeholder — eligibility check below will skip all
        else:
            universe = loaded

    emitted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    quarantined_out: list[dict[str, Any]] = []

    for event in events:
        event_id = str(event.get("id", ""))
        ticker = str(event.get("ticker", "")).upper()

        # ── Dedupe ────────────────────────────────────────────────────────────
        if event_id in seen_ids:
            skipped.append({"id": event_id, "ticker": ticker, "reason": "dedupe"})
            continue

        # ── Eligibility: universe fail-closed ────────────────────────────────
        # When the universe file failed to load, skip all events with a specific
        # reason and do NOT write them to the seen-ledger so they retry once the
        # universe becomes available.
        if _universe_unavailable:
            skipped.append({
                "id": event_id,
                "ticker": ticker,
                "reason": "universe unavailable",
            })
            continue

        # When the universe loaded successfully, check membership.
        if ticker not in universe:
            skipped.append({
                "id": event_id,
                "ticker": ticker,
                "reason": "ticker not in universe",
            })
            continue

        # ── Tag session window ────────────────────────────────────────────────
        event = {**event, "_session": _session_window(str(event.get("when", "")))}

        # ── Route (XG-W2): which account owns this earnings emission? ─────────
        account = _route_account(cfg, root)

        # ── One conversation, one owner (charter §2 amendment 6) ──────────────
        # An earnings print is a story like any other: if the wire lane already
        # emitted it under another account, this lane stands down. The key is the
        # event id (already the lane's dedupe identity), headline as fallback.
        story_key = _story_key_for(event)
        if _story_locked(account, story_key, root=root, now=now, cfg=cfg):
            skipped.append({"id": event_id, "ticker": ticker,
                            "reason": "story_locked"})
            continue

        # ── Build copy (Scorekeeper voice) ────────────────────────────────────
        copy_result = _build_earnings_copy(event)
        ctx = copy_result["ctx"]
        # The routed account is what validate_copy must judge against — a
        # per-account copy law is only real if the account it sees is the
        # account that posts.
        if isinstance(ctx, dict):
            ctx["account"] = account
        headline = copy_result["headline"]
        body = copy_result["body"]

        # ── Validate copy — violations → quarantine (version-keyed ledger) ────
        violations = validate_copy(headline, body, ctx)
        if violations:
            # Quarantine deduplication uses (event_id, TEMPLATE_VERSION) so
            # bumping TEMPLATE_VERSION re-opens previously quarantined events
            # once the copy template is fixed.  Quarantined events are NOT
            # written to the seen-ledger so they retry when the version bumps.
            quarantine_key = (event_id, TEMPLATE_VERSION)
            if quarantine_key not in quarantined_keys:
                quarantined_keys.add(quarantine_key)
                _append_quarantine(root, event_id, violations, dry_run=dry_run)
            quarantined_out.append({
                "id": event_id,
                "ticker": ticker,
                "reason": "copy_violations",
                "violations": violations,
            })
            continue

        # ── Render earnings card SVG ──────────────────────────────────────────
        company_name = event.get("company_name") or ticker
        eps_actual = float(event.get("eps_actual", 0.0))
        eps_est = float(event.get("eps_est", eps_actual))
        rev_actual = event.get("rev_actual")
        rev_est = event.get("rev_est")
        quarter = event.get("quarter")

        try:
            svg = render_earnings_card(
                ticker,
                company_name,
                eps_actual,
                eps_est,
                rev_actual,
                rev_est,
                quarter=quarter,
                logo_root=root,
                cta=cta,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("[fastlane] render_earnings_card(%s) failed: %s", ticker, exc)
            svg = f"<svg xmlns='http://www.w3.org/2000/svg' width='100' height='50'><text y='20'>{ticker} card render failed</text></svg>"

        # ── Emit through the canonical outbox path ────────────────────────────
        try:
            outbox_item = _emit_outbox(
                root, event, account, headline, body, svg, now,
                story_key=story_key, dry_run=dry_run, cfg=cfg, spool=spool,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("[fastlane] outbox write(%s) failed: %s", event_id, exc)
            skipped.append({"id": event_id, "ticker": ticker, "reason": f"outbox_write_error: {exc}"})
            continue
        if outbox_item is None:
            # The canonical path refused it (invalid, duplicate, cross-account
            # near-dup, or over cap). NOT recorded as seen — a refusal is not an
            # emission, and a later tick may legitimately retry it.
            skipped.append({"id": event_id, "ticker": ticker,
                            "reason": "outbox_refused"})
            continue

        # ── Record in seen-ledger ─────────────────────────────────────────────
        seen_ids.add(event_id)
        _append_seen(root, event_id, dry_run=dry_run)
        emitted.append(outbox_item)

        logger.info(
            "[fastlane] emitted %s | %s | %s", event_id, ticker, headline[:60]
        )

    return {
        "emitted": emitted,
        "skipped": skipped,
        "quarantined": quarantined_out,
    }
