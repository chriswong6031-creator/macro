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

Outbox contract (D02):
    D02's engine/marketing/outbox.py will own the outbox publishing contract when
    it lands.  This emitter is intentionally minimal so it can be refactored onto
    that module without changes to callers.  The emitted JSON shape is:
    {
        "id":        str,
        "account":   "flagship",
        "kind":      "earnings",
        "text":      {"headline": str, "body": str},
        "media":     [str],            # relative paths under data/marketing/outbox/
        "immediate": true,
        "priority":  "high",
        "provenance": {<event fields> + "source": str},
        "status":    "queued",
        "created_at": str,             # ISO-8601 UTC
    }

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
_ACCOUNT = "flagship"

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
            whitelist.append(rev_surp_str)
        whitelist.extend([rev_a_str, rev_e_str])

    # ── Scorekeeper-voice copy ───────────────────────────────────────────────
    # Persona: "everything resolves to a number; emoji budget: 1 (🧾)"
    # Rule: EPS $ actual vs $ est — beat/miss by Z%.
    session_note = {
        "premarket": "Pre-market earnings drop.",
        "postmarket": "After-hours earnings drop.",
        "rth": "Earnings out.",
    }.get(session, "Earnings out.")

    headline = f"🧾 {cashtag}{q_label} earnings: {verdict}."

    body_parts = [
        f"EPS ${eps_a_str} vs ${eps_e_str} est — {surp_str}.",
    ]
    if rev_a_str and rev_e_str:
        rev_line = f"Rev ${rev_a_str} vs ${rev_e_str} est"
        if rev_surp_str:
            rev_line += f" ({rev_surp_str})"
        rev_line += "."
        body_parts.append(rev_line)
    body_parts.append(session_note)
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
        "account": _ACCOUNT,
        "numbers_whitelist": unique_whitelist,
        "emoji_budget": 1,    # Scorekeeper allows 1 emoji
        "voice": "dry, receipts-forward",
        "persona_name": "The Scorekeeper",
    }
    return {"ctx": ctx, "headline": headline, "body": body}


# ─────────────────────────────────────────────────────────────────────────────
# Outbox writer
# ─────────────────────────────────────────────────────────────────────────────

def _write_outbox(
    root: Path,
    event: dict[str, Any],
    headline: str,
    body: str,
    svg: str,
    now: datetime,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Write media SVG + outbox JSON and return the outbox item dict.

    When dry_run=True, writes nothing to disk and returns the item dict
    (the caller may log it).
    """
    event_id: str = str(event["id"])
    media_rel = f"data/marketing/outbox/media/{event_id}.svg"

    if not dry_run:
        media_path = root / _MEDIA_DIR / f"{event_id}.svg"
        media_path.parent.mkdir(parents=True, exist_ok=True)
        # Write via temp+replace to avoid torn writes (law from mm-data-guard lessons)
        import tempfile, os  # noqa: E401
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=media_path.parent, suffix=".svg.tmp"
        )
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

    item: dict[str, Any] = {
        "id": event_id,
        "account": _ACCOUNT,
        "kind": "earnings",
        "text": {"headline": headline, "body": body},
        "media": [media_rel],
        "immediate": True,
        "priority": "high",
        "provenance": {
            **{k: v for k, v in event.items() if not k.startswith("_")},
            "source": event.get("source", "unknown"),
        },
        "status": "queued",
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if not dry_run:
        outbox_path = root / _OUTBOX_DIR / f"{event_id}.json"
        outbox_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd2, tmp_path2 = tempfile.mkstemp(
            dir=outbox_path.parent, suffix=".json.tmp"
        )
        try:
            with os.fdopen(tmp_fd2, "w", encoding="utf-8") as fh:
                json.dump(item, fh, indent=2)
            os.replace(tmp_path2, outbox_path)
        except Exception:
            try:
                os.unlink(tmp_path2)
            except OSError:
                pass
            raise

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

        # ── Build copy (Scorekeeper voice) ────────────────────────────────────
        copy_result = _build_earnings_copy(event)
        ctx = copy_result["ctx"]
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
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("[fastlane] render_earnings_card(%s) failed: %s", ticker, exc)
            svg = f"<svg xmlns='http://www.w3.org/2000/svg' width='100' height='50'><text y='20'>{ticker} card render failed</text></svg>"

        # ── Write outbox item ─────────────────────────────────────────────────
        try:
            outbox_item = _write_outbox(
                root, event, headline, body, svg, now, dry_run=dry_run
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("[fastlane] outbox write(%s) failed: %s", event_id, exc)
            skipped.append({"id": event_id, "ticker": ticker, "reason": f"outbox_write_error: {exc}"})
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
