"""engine.marketing.press_lane — pure, testable tick body for the press wire lane.

Processes a batch of press FeedItems (from press_providers.poll_all + the wire RSS
lane) through the full pipeline:

    satire blocklist -> relevance score -> corroboration gate -> flagship top-K/floor
    -> summarize-with-citation -> emit kind="breaking" outbox item (scheduled_at="immediate")

Reuses the existing display-tier machinery:
    breaking_relevance.score_item      deterministic salience / event_class / tickers
    breaking_summary.build_breaking_payload   LLM summarize-with-citation + card
    press_corroboration.corroboration_decision   the §3 gate

The emitted outbox item mirrors the earnings fast-lane shape (fastlane._write_outbox)
so it rides the SAME #3478 breaking dispatch rail (scheduled_at="immediate" ->
publisher._is_immediate -> Buffer customScheduled). The earnings path is untouched.

Public API:
    run_press_tick(items, *, root, now, cfg, press_cfg, state, dry_run=False,
                   llm_override=None) -> dict
        {emitted:[...], skipped:[...], digest:[...], blocked:[...]}

State (daemon-local, gitignored — data/marketing/press/):
    state["flagship_counter"] = {"day": "YYYY-MM-DD", "count": N}
    (the seen-ledger + provider cursors live in the same state file, owned by the
     daemon; this module only reads/advances the flagship counter and the
     corroboration window.)
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_OUTBOX_DIR = Path("data/marketing/outbox")
_MEDIA_DIR = _OUTBOX_DIR / "media"
_ACCOUNT = "flagship"

_DEFAULT_FLAGSHIP_TOP_K = 3
_DEFAULT_FLAGSHIP_FLOOR = 70.0
_DEFAULT_CORROBORATION_WINDOW_S = 1800

# B4a rail: the news.html live-wire rail floor is LOWER than the X post floor —
# the rail shows everything above this (incl. digest-class items), X gets top-K.
_DEFAULT_RAIL_FLOOR = 40.0
_DEFAULT_RAIL_MAX_ITEMS = 50

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _day_key(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _is_satire(item: dict, blocklist_lower: set[str]) -> bool:
    """True when the item comes from a satire/parody-blocklisted handle."""
    handle = str(item.get("x_handle", "")).lower()
    source = str(item.get("source", "")).lower()
    if handle and handle in blocklist_lower:
        return True
    # x_<handle> source key form.
    if source.startswith("x_") and source[2:] in blocklist_lower:
        return True
    return False


def _emission_key(item: dict) -> str:
    """Mirror-collapsed identity for EMISSION dedupe (M1).

    The same Truth post seen via two mirrors (trumpstruth + cnn_truth_backfill)
    carries two distinct FeedItem `id`s (each embeds its mirror source key) but a
    single `truth_status_id`. Deduping emission on `id` alone therefore double-
    emits the same post. When a truth_status_id is present the emission identity
    collapses to `truth:{id}`; otherwise it is the plain item id. This key (not the
    raw id) is what the seen-ledger records for mirror items, so a later tick from
    EITHER mirror is recognised as already-emitted.
    """
    tsid = str(item.get("truth_status_id", "")).strip()
    if tsid:
        return f"truth:{tsid}"
    return str(item.get("id", ""))


def _strip_trailing_source_clause(summary: str, source_name: str) -> str:
    """Remove a trailing '— {source_name}' clause from a summary (m3).

    The deterministic fallback builds '{headline} — {source_name}'; when the body
    attribution is supplied by the corroboration decision we must not leave the
    mirror name in the body. Only strips the EXACT trailing '— {source_name}'
    clause (any dash variant) so a legitimate em-dash inside the headline is kept.
    """
    text = str(summary).rstrip()
    src = str(source_name).strip()
    if not src:
        return text
    for dash in (" — ", " – ", " - ", "—", "–", "-"):
        suffix = f"{dash}{src}"
        if text.endswith(suffix):
            return text[: -len(suffix)].rstrip()
    return text


def _corroboration_key(item: dict) -> str:
    """A coarse claim key for counting independent corroborating sources.

    For mirror items it is the Truth status id (the same post seen via two
    mirrors is the SAME claim, not two).

    For hearsay/x_relay items corroboration keys on ENTITY + event_class, NOT raw
    headline text (M3): two handles wording the same claim differently
    ("Trump told reporters new China tariffs" vs "Trump: China tariffs to rise")
    share matched entity `tariffs` and event_class `policy`, so they land on the
    same claim key and corroborate. A verbatim-headline key never matched such a
    pair — the ≥2-source instant path was dead. `item` must be a SCORED item
    (carrying `matched` + `event_class` from score_item); an unscored item falls
    back to a headline stub so the function never raises.
    """
    tsid = str(item.get("truth_status_id", "")).strip()
    if tsid:
        return f"truth:{tsid}"

    event_class = str(item.get("event_class", "none"))
    entity = _primary_entity(item)
    if entity:
        return f"claim:{event_class}:{entity}"

    # No named entity/ticker to anchor on → fall back to a normalized headline
    # stub (unscored item, or a claim with no matched entity). This path never
    # corroborates a differently-worded pair, which is the conservative default.
    head = re.sub(r"[^a-z0-9 ]", "", str(item.get("headline", "")).lower())
    head = re.sub(r"\s+", " ", head).strip()
    return f"head:{head[:80]}"


def _primary_entity(item: dict) -> str:
    """The single strongest matched entity anchoring a claim, or "".

    Deterministic precedence ticker > macro_key > sector so two items about the
    same claim resolve to the SAME anchor even when one also matched a weaker
    signal. Reads score_item's `matched` dict; returns "" when nothing matched.
    """
    matched = item.get("matched")
    if not isinstance(matched, dict):
        return ""
    for field in ("tickers", "macro_keys", "sectors"):
        vals = matched.get(field) or []
        if vals:
            return f"{field[:3]}:{sorted(str(v) for v in vals)[0]}"
    return ""


def _independent_source(item: dict) -> str:
    """Identity used to count INDEPENDENT sources for corroboration."""
    return str(item.get("x_handle") or item.get("source") or "")


def _write_outbox_item(
    root: Path,
    item_id: str,
    headline: str,
    body: str,
    svg: str,
    provenance: dict,
    now: datetime,
    *,
    cta_suppress: bool,
    dry_run: bool,
) -> dict[str, Any]:
    """Write media SVG + outbox JSON (kind='breaking') and return the item dict.

    Mirrors fastlane._write_outbox exactly (atomic temp+replace) so the item rides
    the identical breaking dispatch rail. dry_run writes nothing.
    """
    media_rel = f"data/marketing/outbox/media/{item_id}.svg"
    if not dry_run and svg:
        media_path = root / _MEDIA_DIR / f"{item_id}.svg"
        media_path.parent.mkdir(parents=True, exist_ok=True)
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

    out_item: dict[str, Any] = {
        "id": item_id,
        "account": _ACCOUNT,
        "kind": "breaking",
        "text": {"headline": headline, "body": body},
        "media": [media_rel] if svg else [],
        "immediate": True,
        "scheduled_at": "immediate",
        "priority": "high",
        "cta_suppress": bool(cta_suppress),
        "provenance": provenance,
        "status": "queued",
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if not dry_run:
        outbox_path = root / _OUTBOX_DIR / f"{item_id}.json"
        outbox_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd2, tmp_path2 = tempfile.mkstemp(dir=outbox_path.parent, suffix=".json.tmp")
        try:
            with os.fdopen(tmp_fd2, "w", encoding="utf-8") as fh:
                json.dump(out_item, fh, indent=2)
            os.replace(tmp_path2, outbox_path)
        except Exception:
            try:
                os.unlink(tmp_path2)
            except OSError:
                pass
            raise

    return out_item


_RECENT_OPENERS_KEEP = 3   # per-account no-repeat window depth (only [-1] gates)


def _corroboration_chip(n_sources: int, corr_class: str) -> str:
    """Honest corroboration chip for the rail (§6: never present hearsay as fact).

    A user-facing surface must not present a single-source relay as confirmed:
        direct-quote (mirror-verified own post) -> "verified"
        >=2 independent sources                 -> "N sources"
        single-source hearsay                   -> "reports"
    """
    if corr_class == "direct-quote":
        return "verified"
    if n_sources >= 2:
        return f"{n_sources} sources"
    return "reports"


def _build_rail_item(
    scored: dict,
    now: datetime,
    emitted_bodies: dict[str, dict],
    *,
    corr: dict,
    now_iso: str,
    window_s: int,
    quotes_store: dict | None,
    tape_cfg: dict,
    wire_voice_enabled: bool,
) -> dict:
    """Build one wires.v1 rail item for a scored press item.

    An item that emitted to X reuses its fully-composed body (opener + summary +
    attribution + tape). A rail-only item (digest-class or below the X post floor)
    gets a DETERMINISTIC display text — headline + attribution + tape — with NO
    extra LLM call, so the rail stays cost-free display-tier.
    """
    iid = str(scored.get("id", ""))
    corr_class = str(scored.get("corroboration_class", "hearsay"))
    register = "markets"
    if wire_voice_enabled:
        try:
            from engine.marketing.wire_voice import derive_register  # noqa: PLC0415
            register = derive_register(scored)
        except Exception:  # noqa: BLE001
            register = str(scored.get("event_class", "none"))

    # Independent-source count for the chip.
    ck = _corroboration_key(scored)
    n_sources = len(corr.get(ck, {}).get("sources", []))

    hit = emitted_bodies.get(iid)
    if hit is not None:
        text_en = hit["text"]
        tape_stamp = hit.get("tape_stamp", "")
        attribution = hit.get("attribution", "")
        register = hit.get("register", register)
    else:
        # Deterministic rail-only text. Attribution comes from the corroboration
        # decision so the rail never presents hearsay as fact.
        from engine.marketing.press_corroboration import (  # noqa: PLC0415
            corroboration_decision,
        )
        window_ok = _within_window(
            corr.get(ck, {}).get("first_ts", now_iso), now, window_s
        )
        decision = corroboration_decision(
            scored, corroborated_sources=n_sources, window_ok=window_ok
        )
        attribution = decision.get("attribution", "")
        headline = str(scored.get("headline", "")).strip()
        tape_stamp = ""
        if wire_voice_enabled and quotes_store is not None:
            try:
                from engine.marketing.tape_stamp import stamp_clause  # noqa: PLC0415
                tape_stamp = stamp_clause(scored, quotes_store, now=now, cfg=tape_cfg)
            except Exception:  # noqa: BLE001
                tape_stamp = ""
        text_en = headline
        if attribution:
            text_en = f"{text_en} — {attribution}"
        if tape_stamp:
            text_en = f"{text_en} · {tape_stamp}"

    item: dict = {
        "id": iid,
        "ts": str(scored.get("published_at", "")) or now_iso,
        "class": str(scored.get("event_class", "none")),
        "register": register,
        "text_en": text_en,
        "attribution": attribution,
        "corroboration": _corroboration_chip(n_sources, corr_class),
    }
    if tape_stamp:
        item["tape_stamp"] = tape_stamp
    return item


def _apply_wire_voice(
    scored: dict,
    base_summary: str,
    attribution: str,
    *,
    account: str,
    recent_openers: dict,
    quotes_store: dict | None,
    fmt: str,
    voice_cfg: dict,
    format_cfg: dict,
    tape_cfg: dict,
    now: datetime,
) -> tuple[str, str, str, str, str, bool]:
    """Run the B2-COPY voice pass over one item's summary.

    `fmt` is the already-picked format ("flash"|"wire_deep") from the caller — the
    picker runs BEFORE the summarizer so the wire_deep two-paragraph instruction
    can steer the LLM prompt (the picker is deterministic code either way).

    Returns (body, register, opener, wire_format, tape_stamp, applied). `applied`
    is False when the composed post fails the length budget after the voice pass —
    the caller then keeps the plain B1 body. The AI-tell check is applied to the
    LLM summary text; a hit strips the offending prose to the deterministic
    headline, never posting the AI-tell'd summary.

    Mutates recent_openers[account] in place (records the chosen opener), so the
    daemon persists the no-repeat window across ticks.
    """
    from engine.marketing import wire_format as wf  # noqa: PLC0415
    from engine.marketing import wire_voice as wv  # noqa: PLC0415

    # 1. AI-tell guard on the summary prose. A hit means the LLM summary reads as
    #    generated — drop it to the deterministic headline so we never ship a tell.
    summary_text = str(base_summary or "")
    if summary_text and wv.ai_tell_hits(summary_text):
        summary_text = str(scored.get("headline", "")).strip()

    # 3. Opener rotation with a per-account no-repeat window.
    acct_recent = recent_openers.setdefault(account, [])
    opener, register = wv.select_opener(
        scored, account=account, recent_openers=acct_recent, cfg=voice_cfg
    )

    # 4. Tape stamp — threshold-gated; missing/stale/quiet => "".
    tape = ""
    if quotes_store is not None:
        from engine.marketing.tape_stamp import stamp_clause  # noqa: PLC0415
        tape = stamp_clause(scored, quotes_store, now=now, cfg=tape_cfg)

    # 5. Compose + length-budget validate.
    post = wv.compose_post(
        opener=opener, summary=summary_text, attribution=attribution,
        tape_stamp=tape,
    )
    violations = wf.validate_length(post, fmt, cfg=format_cfg)
    if violations:
        # A wire_deep post UNDER the 400-char minimum is just a long flash — the
        # source did not fill two paragraphs. Downgrade to flash rather than
        # decline, so the voice (opener + tape) still ships. (An OVER-budget deep
        # is a real overshoot and is not downgraded — it falls through below.)
        if fmt == "wire_deep" and all("< min" in v for v in violations):
            fmt = "flash"
            violations = wf.validate_length(post, fmt, cfg=format_cfg)
        if violations:
            # Retry once WITHOUT the opener (the cheapest length to shed); if still
            # over budget, the voice pass declines and the caller keeps the plain
            # body — we never ship an over-budget post.
            post_no_opener = wv.compose_post(
                opener="", summary=summary_text, attribution=attribution,
                tape_stamp=tape,
            )
            if not wf.validate_length(post_no_opener, fmt, cfg=format_cfg):
                opener = ""
                post = post_no_opener
            else:
                return base_summary, register, "", fmt, "", False

    # Record the chosen opener into the account's no-repeat window (newest last).
    acct_recent.append(opener)
    del acct_recent[:-_RECENT_OPENERS_KEEP]

    return post, register, opener, fmt, tape, True


# ─────────────────────────────────────────────────────────────────────────────
# Public: run_press_tick
# ─────────────────────────────────────────────────────────────────────────────

def run_press_tick(
    items: list[dict],
    *,
    root: Path | str,
    now: datetime,
    cfg: dict,
    press_cfg: dict,
    state: dict[str, Any],
    seen_ids: set[str] | None = None,
    dry_run: bool = False,
    prime: bool = False,
    llm_override: Any = None,
) -> dict[str, list[dict]]:
    """Run one press-lane tick over a batch of FeedItems.

    Args:
        items:      FeedItems from press_providers.poll_all + wire RSS poll_all.
        root:       repo root (outbox output dirs).
        now:        current UTC datetime (injectable for tests).
        cfg:        full marketing.yml dict (for breaking.llm gating + relevance cfg).
        press_cfg:  parsed press_sources.yml dict (satire list, wire caps).
        state:      daemon-local mutable state (flagship counter, corroboration seen).
        seen_ids:   ids already emitted (dedupe). When None, no cross-tick dedupe
                    (the daemon passes its persisted seen-set).
        dry_run:    compute everything, write nothing.
        prime:      COLD-START (m2). On the very first run — no cursor/seen state —
                    the batch is a full history snapshot, not real-time news;
                    emitting it would flood. When True the tick runs the full
                    pipeline (so the seen-ledger primes and provider cursors, which
                    the provider fetch already advanced to newest, stay advanced)
                    but emits NOTHING and logs a start-of-line "[press] primed".
                    The daemon sets this on true cold-start only.
        llm_override: test seam forwarded to build_breaking_payload.

    Returns {emitted, skipped, digest, blocked}.
    """
    from engine.marketing.breaking_relevance import score_item
    from engine.marketing.breaking_summary import build_breaking_payload
    from engine.marketing.press_corroboration import corroboration_decision

    root = Path(root)
    breaking_cfg = cfg.get("breaking", {}) if isinstance(cfg, dict) else {}
    wire_cfg = (press_cfg or {}).get("wire", {}) if isinstance(press_cfg, dict) else {}
    top_k = int(wire_cfg.get("flagship_top_k_per_day", _DEFAULT_FLAGSHIP_TOP_K))
    floor = float(wire_cfg.get("flagship_salience_floor", _DEFAULT_FLAGSHIP_FLOOR))
    window_s = int(wire_cfg.get("corroboration_window_s", _DEFAULT_CORROBORATION_WINDOW_S))
    rail_floor = float(wire_cfg.get("rail_salience_floor", _DEFAULT_RAIL_FLOOR))
    rail_max = int(wire_cfg.get("rail_max_items", _DEFAULT_RAIL_MAX_ITEMS))

    # B2-COPY wire-voice config lives under press_sources.yml `wire.voice`,
    # `wire.format`, `wire.tape` (all optional — absent => deterministic defaults,
    # so a B1-shaped config is a clean no-op enhancement). Loaded once per tick.
    voice_cfg = wire_cfg.get("voice", {}) if isinstance(wire_cfg, dict) else {}
    format_cfg = wire_cfg.get("format", {}) if isinstance(wire_cfg, dict) else {}
    tape_cfg = wire_cfg.get("tape", {}) if isinstance(wire_cfg, dict) else {}
    wire_voice_enabled = bool(voice_cfg.get("enabled", True))

    # Live-quote store for tape stamps — read ONCE (fail-soft: None => no stamps).
    quotes_store = None
    if bool(tape_cfg.get("enabled", True)):
        try:
            from engine.marketing.tape_stamp import load_quotes  # noqa: PLC0415
            quotes_store = load_quotes(tape_cfg.get("quote_store_paths"), root=root)
        except Exception:  # noqa: BLE001
            quotes_store = None

    # Per-account opener no-repeat window (persisted in daemon-local state so it
    # survives across ticks). recent[account] = [last openers], newest last.
    recent_openers_state = state.setdefault("recent_openers", {})

    blocklist_lower = {s.lower() for s in ((press_cfg or {}).get("satire_blocklist") or [])}
    seen = set(seen_ids or set())

    # Flagship daily counter (reset on day boundary).
    counter = state.setdefault("flagship_counter", {"day": _day_key(now), "count": 0})
    if counter.get("day") != _day_key(now):
        counter["day"] = _day_key(now)
        counter["count"] = 0

    # Corroboration window ledger: claim_key -> {sources:list, first_ts:iso}.
    # Prune entries older than the window so the state file cannot grow unbounded
    # (a claim past its corroboration window can never gain a within-window peer).
    corr = state.setdefault("corroboration", {})
    for ck in [k for k, e in corr.items()
               if not _within_window(e.get("first_ts"), now, window_s)]:
        del corr[ck]

    emitted: list[dict] = []
    skipped: list[dict] = []
    digest: list[dict] = []
    blocked: list[dict] = []
    rail: list[dict] = []   # B4a: rail-eligible items (lower floor, incl. digest)
    emitted_bodies: dict[str, dict] = {}   # id -> composed text for rail reuse

    # 1. Satire hard-blocklist at ingestion + dedupe.
    # Dedupe on the MIRROR-COLLAPSED emission key (M1): the same Truth post seen
    # via two mirrors shares one truth_status_id, so the second mirror is a
    # dedupe skip, not a second emission. Also collapse within a single tick so a
    # trumpstruth + cnn_truth_backfill pair arriving together emits once.
    ingest: list[dict] = []
    seen_this_tick: set[str] = set()
    for it in items:
        iid = str(it.get("id", ""))
        if _is_satire(it, blocklist_lower):
            blocked.append({"id": iid, "reason": "satire_blocklist"})
            continue
        ekey = _emission_key(it)
        if ekey and (ekey in seen or ekey in seen_this_tick):
            skipped.append({"id": iid, "reason": "dedupe"})
            continue
        if ekey:
            seen_this_tick.add(ekey)
        ingest.append(it)

    # 2. Score everything (deterministic relevance) and register corroboration.
    scored: list[dict] = []
    now_iso = now.astimezone(timezone.utc).isoformat()
    for it in ingest:
        s = score_item(it, now=now, cfg=breaking_cfg, root=root)
        # Register this source against its claim key for corroboration counting.
        ck = _corroboration_key(s)
        entry = corr.setdefault(ck, {"sources": [], "first_ts": now_iso})
        src = _independent_source(s)
        if src and src not in entry["sources"]:
            entry["sources"].append(src)
        scored.append(s)

    # 3. Rank by salience so the flagship top-K takes the strongest items.
    scored.sort(key=lambda x: x.get("salience", 0.0), reverse=True)

    # COLD-START (m2): on the very first run the batch is a full history snapshot
    # (mirror archives, twitterapi.io last_tweets with no prior cursor), NOT
    # real-time news — emitting it would flood. "Prime, don't post": record every
    # item's emission key so the NEXT tick dedupes the history away, keep the
    # advanced provider cursors + registered corroboration window, emit nothing.
    if prime:
        for s in scored:
            seen.add(_emission_key(s))
        print(f"[press] primed | {len(scored)} items seen, 0 emitted (cold start)",
              flush=True)
        return {
            "emitted": [],
            "skipped": [{"id": str(s.get("id", "")), "reason": "primed"} for s in scored],
            "digest": [],
            "blocked": blocked,
            "rail": [],
            "_seen": sorted(seen),
        }

    for s in scored:
        iid = str(s.get("id", ""))
        ck = _corroboration_key(s)
        entry = corr.get(ck, {"sources": [], "first_ts": now_iso})
        n_sources = len(entry.get("sources", []))
        window_ok = _within_window(entry.get("first_ts"), now, window_s)

        # 4. Corroboration gate.
        decision = corroboration_decision(
            s, corroborated_sources=n_sources, window_ok=window_ok
        )
        if decision["gate"] == "digest":
            digest.append({"id": iid, "reason": decision["reason"],
                           "salience": s.get("salience"), "headline": s.get("headline")})
            continue

        # 5. Flagship interim lane: top-K/day + salience floor.
        if s.get("salience", 0.0) < floor:
            skipped.append({"id": iid, "reason": "below_flagship_floor",
                            "salience": s.get("salience")})
            continue
        if counter["count"] >= top_k:
            skipped.append({"id": iid, "reason": "flagship_top_k_reached",
                            "salience": s.get("salience")})
            continue

        # 6. Pick the wire FORMAT first (deterministic — code, never the LLM), so
        #    the wire_deep two-paragraph instruction can steer the summarizer. The
        #    picked format is passed into the voice pass so it is not re-derived.
        chosen_format = "flash"
        wire_llm: dict | None = None
        if wire_voice_enabled:
            try:
                from engine.marketing import wire_format as _wf  # noqa: PLC0415
                chosen_format = _wf.pick_format(s, cfg=format_cfg)["format"]
                # wire config forwarded to the LLM summarizer: tier keys (from
                # voice_cfg) + the picked format so the prompt matches the budget.
                wire_llm = dict(voice_cfg)
                wire_llm["_format"] = chosen_format
            except Exception:  # noqa: BLE001
                chosen_format = "flash"
                wire_llm = None

        # Summarize-with-citation + build the outbox-shaped payload.
        payload = build_breaking_payload(
            s, cfg, root=root, _llm_override=llm_override, wire=wire_llm
        )

        headline = payload.get("headline", "")
        summary = payload.get("summary", "")
        # Body attribution comes from the corroboration DECISION, never from the
        # mirror name (m3). For a direct-quote the decision says "on Truth Social";
        # the mirror ("via trumpstruth.org") belongs to provenance/ledger, not the
        # post body. The deterministic fallback summary ends "— {source_name}",
        # which for a mirror item names the mirror — strip that clause and replace
        # it with the decision attribution. The LLM summary (mode="llm") carries no
        # trailing source line (its prompt forbids one), so the attribution is
        # appended. Either way the body attributes the ORIGINAL surface, and the
        # mirror is named only in provenance.
        attribution = decision.get("attribution", "")
        mode = payload.get("mode", "deterministic")
        source_name = str(s.get("source_name", s.get("source", "")))
        # The summary WITHOUT the trailing "— {source_name}" fallback clause — the
        # attribution is (re)applied by the corroboration decision, and the wire
        # voice pass composes opener + attribution + tape from these parts.
        base_summary = _strip_trailing_source_clause(summary, source_name)

        # ── B2-COPY wire voice pass ────────────────────────────────────────────
        # Opener rotation (deterministic + per-account no-repeat), deterministic
        # format pick, tape stamp (threshold-gated), AI-tell rejection, length
        # budget. Any failure in this layer falls back to the plain B1 body — the
        # voice pass NEVER blocks an item that would otherwise post.
        register = s.get("event_class", "none")
        wire_format = "flash"
        opener = ""
        tape_stamp = ""
        voice_applied = False
        if wire_voice_enabled:
            try:
                body, register, opener, wire_format, tape_stamp, voice_applied = (
                    _apply_wire_voice(
                        s, base_summary, attribution,
                        account=_ACCOUNT,
                        recent_openers=recent_openers_state,
                        quotes_store=quotes_store,
                        fmt=chosen_format,
                        voice_cfg=voice_cfg, format_cfg=format_cfg, tape_cfg=tape_cfg,
                        now=now,
                    )
                )
            except Exception:  # noqa: BLE001
                voice_applied = False

        if not voice_applied:
            # Plain B1 body (attribution appended, no opener/tape).
            if attribution:
                body = f"{base_summary} — {attribution}"
            else:
                body = base_summary

        provenance = {
            **payload.get("provenance", {}),
            "corroboration_class": s.get("corroboration_class", "hearsay"),
            "corroboration_gate": decision["gate"],
            "corroborated_sources": n_sources,
            "salience": s.get("salience"),
            "event_class": s.get("event_class"),
            # The mirror/relay surface is recorded HERE (provenance/ledger), never
            # in the post body (m3): e.g. "via trumpstruth.org".
            "via_source": source_name,
            # B2-COPY voice metadata (feedback-loop + rail payload inputs).
            "register": register,
            "wire_format": wire_format,
            "opener": opener,
            "tape_stamp": tape_stamp,
        }

        out_item = _write_outbox_item(
            root, iid, headline, body, payload.get("card_svg", ""),
            provenance, now,
            cta_suppress=bool(s.get("cta_suppress", False)),
            dry_run=dry_run,
        )
        counter["count"] = int(counter["count"]) + 1
        # Record the MIRROR-COLLAPSED key so a later tick from EITHER mirror is a
        # dedupe skip. out_item still carries the raw id for the outbox filename.
        seen.add(_emission_key(s))
        emitted.append(out_item)
        # An emitted item is rail-eligible with its FULLY-composed body (opener +
        # summary + attribution + tape). Record the composed text keyed by id so
        # the rail builder reuses it rather than re-running the LLM.
        emitted_bodies[iid] = {"text": body, "register": register,
                               "tape_stamp": tape_stamp, "attribution": attribution}

    # ── B4a rail ───────────────────────────────────────────────────────────────
    # The rail shows EVERYTHING above a LOWER floor (incl. digest-class items X
    # never posts) — the news.html retention surface. Items that emitted to X reuse
    # their composed body; rail-only items (digest/below-post-floor) get a
    # deterministic display text (headline + attribution + tape) — NO extra LLM
    # call, so the rail is cost-free display-tier. Ranked by salience, capped.
    rail_seen: set[str] = set()
    for s in scored:
        try:
            if float(s.get("salience", 0.0)) < rail_floor:
                continue
        except (TypeError, ValueError):
            continue
        rail_item = _build_rail_item(
            s, now, emitted_bodies, corr=corr, now_iso=now_iso,
            window_s=window_s, quotes_store=quotes_store, tape_cfg=tape_cfg,
            wire_voice_enabled=wire_voice_enabled,
        )
        rkey = rail_item["id"]
        if rkey in rail_seen:
            continue
        rail_seen.add(rkey)
        rail.append(rail_item)
        if len(rail) >= rail_max:
            break

    return {
        "emitted": emitted,
        "skipped": skipped,
        "digest": digest,
        "blocked": blocked,
        "rail": rail,   # B4a: rail-eligible items for the wires.json sink
        # The full seen-set AFTER this tick, including MIRROR-COLLAPSED emission
        # keys (M1). The daemon persists this verbatim so cross-tick dedupe works
        # for mirror pairs — recording out_item["id"] alone would miss the collapse.
        "_seen": sorted(seen),
    }


def _within_window(first_ts: str | None, now: datetime, window_s: int) -> bool:
    """True when `now` is within window_s of first_ts (both UTC)."""
    if not first_ts:
        return True
    try:
        first = datetime.fromisoformat(str(first_ts).replace("Z", "+00:00"))
    except ValueError:
        return True
    delta = (now.astimezone(timezone.utc) - first.astimezone(timezone.utc)).total_seconds()
    return 0 <= delta <= window_s
