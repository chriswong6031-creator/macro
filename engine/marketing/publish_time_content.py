"""engine.marketing.publish_time_content — publish-time mover/theme generation.

`mover` ("Mover of the Day") and `theme_list` ("Theme Tape") posts are the one
family the NIGHTLY content plan deliberately generates but never emits: a "+7%
today" claim written at 23:45 ET is stale by the next morning's opening bell.
This module builds the HONEST version — it runs INSIDE the publisher's slot runs
(10:00 / 13:30 / 16:15 ET on the ubuntu publish workflow), reads the freshest
tape available in that checkout, renders copy from the SAME v3 template banks the
nightly desk uses, enqueues text-only items via the outbox, and hands them to the
existing post-time tape gate (engine/marketing/live_verify.py) which re-verifies
the exact number the copy claims before it may post.

Import constraint (the ubuntu publish workflow installs ONLY pyyaml+pandas+
pyarrow): every top-level import here is stdlib or an engine.marketing module
that is itself stdlib-only (movers_source, copywriter, outbox, sentinel,
live_verify). pandas / chart_render / logo_cache are NEVER imported at module
top level. Items are text-only (no media → they never touch the media cap).

Public API (a single orchestrator the publisher calls):
    generate_slot_items(root, *, cfg, now, state, approved_due, posted_counts,
                        cap, live, account_filter=None) -> dict

Fail-soft law: the whole body is wrapped in try/except → a broken generation
NEVER raises into the legacy publisher flow; it logs a warning and returns a
report with the error noted. In dry-run (live=False) it writes NOTHING and
collects candidates into "would_generate".

Display-tier ops (no signal authority, no forward-ledger writes): this only
describes what already moved on the tape.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.marketing import (
    copywriter,
    live_verify,
    market_facts,
    movers_source,
    outbox,
    sentinel,
)

log = logging.getLogger(__name__)

_CASHTAG_RE = re.compile(r"\$[A-Z]{1,5}\b")

# In-code defaults for the publish.publish_time_movers config block. CONSERVATIVE
# by design: `enabled` is False when the block is absent, so old configs and the
# test-suite fixtures that carry no block are unaffected (generation disabled).
_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "max_per_run": 2,           # network-wide new items per slot run
    "min_abs_mover_pct": 3.0,   # floor for a single-name move claim
    "min_abs_theme_pct": 1.0,   # floor for a theme-average claim
    "max_quote_age_min": 45,    # generation freshness gate (mirrors live_gate)
    "min_active_tiles": 25,     # flat-tape belt: skip when the board isn't moving
}

# A tile counts as "active" for the flat-tape belt when its overlaid 1D move is
# at least this large. Heuristic, not a sentinel cap: a normal RTH session has
# hundreds of S&P names past ±0.5%; a closed market (holiday whose feeds still
# tick) or a stale/static splice has almost none — that is the failure the belt
# catches, because _tape_stale can be anchored fresh by a non-equity quote (BTC
# in the display feed) while every equity pct rides yesterday's board.
_ACTIVE_TILE_MIN_ABS = 0.5

_PROVENANCE = "publisher_live_movers"


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

def _pt_cfg(cfg: dict | None) -> dict[str, Any]:
    """Resolve publish.publish_time_movers over the in-code defaults (fail-soft)."""
    out = dict(_DEFAULTS)
    try:
        block = ((cfg or {}).get("publish") or {}).get("publish_time_movers") or {}
        for k, dv in _DEFAULTS.items():
            if k in block:
                if isinstance(dv, bool):
                    v = block[k]
                    out[k] = v if isinstance(v, bool) else (
                        str(v).strip().lower() in {"1", "true", "yes"})
                else:
                    out[k] = type(dv)(block[k])
    except Exception as exc:  # noqa: BLE001
        log.warning("publish_time_content: bad publish.publish_time_movers config "
                    "(%s) — using defaults", exc)
    return out


def _sentinel_knob(cfg: dict | None, key: str, default: Any) -> Any:
    """Read a sentinel: knob from cfg, matching sentinel's in-code fallback."""
    try:
        block = (cfg or {}).get("sentinel") or {}
        if key in block and block[key] is not None:
            return type(default)(block[key])
    except Exception:  # noqa: BLE001
        pass
    return default


# ─────────────────────────────────────────────────────────────────────────────
# Per-call lane eligibility — the ONE place both lanes ask "who may post?"
#
# Both lanes used to filter on ``acc.get("disabled")`` alone, which reads a
# LEGACY key. ``desk_network`` has carried an explicit ``enabled`` since the
# accounts model landed, and ``accounts._config_enabled`` gives ``enabled``
# precedence over ``disabled`` — so an account with ``enabled: false`` and no
# ``disabled`` key (mastermind_news, and every employee desk had one been left
# off) sailed through both filters. Adding a Buffer channel id was then enough to
# make it a live posting target under an unrestricted auto-approve and a -1 cap.
# Liveness now resolves through ``accounts.effective_accounts``, the same
# function the nightly plan builder uses, so the two lanes cannot disagree about
# which accounts exist — and the operator override file is honoured here too.
# ─────────────────────────────────────────────────────────────────────────────

#: Accounts the PER-CALL publish-time lanes may draw, when config names none.
#:
#: Default-restrictive, and it ENFORCES a decision the charter already recorded
#: rather than making a new one: the employee desks launch on non-news/tape kinds
#: (charter §7 sequencing), and their tilts zero ``mover`` and ``event`` to say
#: so. But these two lanes are per-CALL generators — they pick an account from
#: desk_network and build an item directly, never consulting tilt — so a zeroed
#: tilt does not reach them. Without an allowlist an employee desk would launch
#: on exactly the two kinds its own spec sets to 0.00.
#:
#: Employees therefore launch on the NIGHTLY content_studio lane only, which is
#: tilt-governed and rotates variants within a batch so two desks diverge.
#: Charter §6 XG-W2 (cadence resolver) and XG-W3 (desk feeds) are the unlock:
#: when per-account cadence profiles and desk feeds exist, this allowlist is the
#: knob that widens.
_PER_CALL_DEFAULT_ACCOUNTS: tuple[str, ...] = ("flagship", "founder")


def _lane_accounts(cfg: dict | None, lane_key: str) -> frozenset[str]:
    """``publish.<lane_key>.accounts`` allowlist for a per-call lane.

    Absent key → :data:`_PER_CALL_DEFAULT_ACCOUNTS`. Present → EXACTLY that list,
    including an explicit empty list, which means "no account" — default-
    restrictive both ways, so widening the lane is always a visible config edit.
    """
    try:
        block = ((cfg or {}).get("publish") or {}).get(lane_key) or {}
        if "accounts" in block:
            raw = block.get("accounts") or []
            if isinstance(raw, (list, tuple)):
                return frozenset(str(a).strip() for a in raw if str(a).strip())
            log.warning("publish_time_content: publish.%s.accounts is not a list "
                        "— falling back to the default allowlist", lane_key)
    except Exception as exc:  # noqa: BLE001
        log.warning("publish_time_content: bad publish.%s.accounts (%s) — "
                    "using the default allowlist", lane_key, exc)
    return frozenset(_PER_CALL_DEFAULT_ACCOUNTS)


def _per_call_eligible(
    cfg: dict | None,
    *,
    lane_key: str,
    root: Path | str | None = None,
    account_filter: str | None = None,
) -> list[dict]:
    """Account dicts a per-call publish-time lane may draw, in config order.

    Four gates, all of which must pass: the account is LIVE (config ``enabled``
    resolved through the accounts model, operator overrides included), it is on
    this lane's allowlist, it has a publish channel id (an item that could never
    post is not worth generating), and it matches any explicit account_filter.
    """
    from engine.marketing.accounts import effective_accounts  # noqa: PLC0415

    pub_channels = ((cfg or {}).get("publish") or {}).get("channels") or {}
    allow = _lane_accounts(cfg, lane_key)

    out: list[dict] = []
    for acc in effective_accounts(cfg, root):
        aid = str(acc.get("id", "") or "")
        if not aid:
            continue
        if not acc.get("enabled"):
            continue
        if aid not in allow:
            continue
        if not str(pub_channels.get(aid, "") or "").strip():
            continue  # no channel id → the item could never post
        if account_filter is not None and aid != account_filter:
            continue
        out.append(acc)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Slot / gating helpers
# ─────────────────────────────────────────────────────────────────────────────

def _slot_label(now: datetime) -> str | None:
    """Map now (UTC) to a slot label, or None outside the posting window.

    Window: 13:30 <= now UTC < 22:00 (the AM/PM/EOD posting slots run in RTH).
      [13:30, 16:30) -> "AM"   (10:00 ET slot)
      [16:30, 19:30) -> "PM"   (13:30 ET slot)
      [19:30, 22:00) -> "EOD"  (16:15 ET slot)
    """
    minutes = now.hour * 60 + now.minute
    if minutes < (13 * 60 + 30) or minutes >= (22 * 60):
        return None
    if minutes < (16 * 60 + 30):
        return "AM"
    if minutes < (19 * 60 + 30):
        return "PM"
    return "EOD"


def _slot_index(slot: str) -> int:
    return {"AM": 0, "PM": 1, "EOD": 2}.get(slot, 0)


def _iso_now(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _empty_report(slot: str | None, *, enabled: bool, quote_source: str = "none",
                  drop: list[dict] | None = None) -> dict:
    return {
        "enabled": enabled,
        "generated": [],
        "would_generate": [],
        "dropped": drop or [],
        "quote_source": quote_source,
        "slot": slot or "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tape freshness + live overlay
# ─────────────────────────────────────────────────────────────────────────────

def _tape_stale(tape: dict, movers_data: dict | None, now: datetime,
                max_age_min: float) -> bool:
    """True when the freshest tape is older than the generation freshness gate.

    Precedence: if the tape carries per-ticker ts/asof (snapshot/display), use
    live_verify._quote_age_min semantics over the freshest ticker. When the tape
    is heatmap-only (no ts, no asof), fall back to the movers heatmap's own asof.
    """
    quotes = (tape or {}).get("quotes") or {}
    asof = (tape or {}).get("asof")
    ages: list[float] = []
    for q in quotes.values():
        age = live_verify._quote_age_min(q, asof, now)
        if age is not None:
            ages.append(age)
    if ages:
        return min(ages) > max_age_min
    # Heatmap-only source: no per-ticker ts and no snapshot asof — age the tiles
    # by the sp500 heatmap asof field (movers_source.load_movers surfaces it).
    heat_asof = (movers_data or {}).get("asof")
    if heat_asof:
        age = live_verify._quote_age_min({}, str(heat_asof), now)
        if age is not None:
            return age > max_age_min
    # Nothing datable → treat as stale (fail closed: never claim a move we cannot
    # anchor to a fresh timestamp).
    return True


def _live_pct(tape_quotes: dict, ticker: str) -> float | None:
    """The live change_pct for a ticker if the tape has a numeric one, else None."""
    q = tape_quotes.get(str(ticker).upper())
    if not q:
        return None
    return live_verify._f(q.get("change_pct"))


def _overlay_movers(movers_data: dict, tape: dict) -> dict:
    """Return a COPY of the movers data with live tape pcts overlaid.

    For every sp500 tile and every theme member, if the tape has that ticker with
    a numeric change_pct, replace perf["1D"] with the live change_pct. When the
    tape source includes "snapshot" or "display" (a real quote feed), DROP tiles
    and members that lack a live quote — the heatmap's own 1D is stale next to a
    live feed. When the tape is heatmap-only, the tiles ARE the freshest source,
    so keep them all. Never mutates the loaded dicts in place.
    """
    tape_quotes = (tape or {}).get("quotes") or {}
    src = str((tape or {}).get("source") or "")
    has_feed = ("snapshot" in src) or ("display" in src)

    out: dict[str, Any] = {"asof": (movers_data or {}).get("asof")}

    new_sp500: list[dict] = []
    for tile in (movers_data or {}).get("sp500_tiles") or []:
        if not isinstance(tile, dict):
            continue
        tkr = tile.get("t", "")
        lp = _live_pct(tape_quotes, tkr) if tkr else None
        if lp is None:
            if has_feed:
                continue  # a live feed exists but not for this name → stale, drop
            new_sp500.append(dict(tile))  # heatmap-only: keep the tile as-is
            continue
        new_tile = dict(tile)
        new_perf = dict(new_tile.get("perf") or {})
        new_perf["1D"] = lp
        new_tile["perf"] = new_perf
        new_sp500.append(new_tile)
    out["sp500_tiles"] = new_sp500

    new_theme: list[dict] = []
    for tile in (movers_data or {}).get("theme_tiles") or []:
        if not isinstance(tile, dict):
            continue
        new_tile = dict(tile)
        new_members: list[dict] = []
        for m in tile.get("members") or []:
            if not isinstance(m, dict):
                continue
            tkr = m.get("t", "")
            lp = _live_pct(tape_quotes, tkr) if tkr else None
            if lp is None:
                if has_feed:
                    continue
                new_members.append(dict(m))
                continue
            nm = dict(m)
            nm_perf = dict(nm.get("perf") or {})
            nm_perf["1D"] = lp
            nm["perf"] = nm_perf
            new_members.append(nm)
        new_tile["members"] = new_members
        new_theme.append(new_tile)
    out["theme_tiles"] = new_theme

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Candidate generation (mirrors content_studio nightly wiring)
# ─────────────────────────────────────────────────────────────────────────────

def _radar_tier_map(root: Path, cfg: dict | None) -> dict | None:
    """The radar tier map, only when settings.radar_tiers_enabled is true.

    radar_internal is loaded lazily (kept off the module top-level import set so a
    missing optional dep never breaks the publisher). Fail-soft: absent → None.
    """
    try:
        if not (cfg or {}).get("settings", {}).get("radar_tiers_enabled"):
            return None
        from engine.marketing.radar_internal import load_cashtag_tiers as _lct  # noqa: PLC0415
        tiers = _lct(root)
        if tiers:
            return {t: v["tier"] for t, v in (tiers.get("tickers") or {}).items()}
    except Exception:  # noqa: BLE001
        return None
    return None


def _build_candidates(overlaid: dict, root: Path, cfg: dict, pt: dict) -> list[dict]:
    """Build interleaved [theme1, mover1, theme2, mover2, ...] candidates.

    Replicates the nightly wiring (content_studio.py ~1126-1239): cashtag_tiers
    via movers_source._load_cashtag_tiers; the radar tier_map only under
    settings.radar_tiers_enabled; min_abs from the publish config. Movers are
    ranked by abs(pct) desc over losers+gainers (nightly convention — losers
    listed first so they win ties). Themes and movers interleave THEME-first.
    Each candidate is a movers-desk-shaped item dict (no copy yet).
    """
    tier_map = _radar_tier_map(root, cfg)
    cashtag_tiers: dict | None = None
    try:
        ct = movers_source._load_cashtag_tiers(root)
        if ct:
            cashtag_tiers = ct
    except Exception:  # noqa: BLE001
        cashtag_tiers = None

    mv_result = movers_source.top_movers(
        overlaid, min_abs=float(pt["min_abs_mover_pct"]), tier_map=tier_map)
    tl_result = movers_source.theme_lists(
        overlaid, min_abs_theme=float(pt["min_abs_theme_pct"]),
        cashtag_tiers=cashtag_tiers)

    # Rank movers by |pct| desc; losers first so they win ties (nightly convention).
    all_movers = list(mv_result.get("losers") or []) + list(mv_result.get("gainers") or [])
    all_movers.sort(key=lambda x: abs(x.get("pct", 0)), reverse=True)

    mover_items: list[dict] = []
    used_mover_tickers: set[str] = set()
    for mv in all_movers:
        tkr = mv.get("ticker", "")
        if not tkr or tkr in used_mover_tickers:
            continue
        used_mover_tickers.add(tkr)
        mover_items.append({
            "type": "mover",
            "ticker": tkr,
            "cashtag": f"${tkr}",
            "_mover_data": mv,
            "_mover_facts": movers_source.mover_facts(mv),
        })

    theme_items: list[dict] = []
    for tl in tl_result:
        members = tl.get("members") or []
        if not members:
            continue
        lead = members[0]
        theme_items.append({
            "type": "theme_list",
            "ticker": "",
            "cashtags": [f"${m['ticker']}" for m in members[:10]],
            "_theme_data": tl,
            "_theme_facts": movers_source.theme_facts(tl),
            "_lead_ticker": lead.get("ticker", ""),
            "_lead_pct": lead.get("pct"),
            "_theme_name": tl.get("theme", ""),
            "_agg_pct": tl.get("agg_pct"),
        })

    # Interleave THEME-first: [theme1, mover1, theme2, mover2, ...].
    interleaved: list[dict] = []
    for i in range(max(len(theme_items), len(mover_items))):
        if i < len(theme_items):
            interleaved.append(theme_items[i])
        if i < len(mover_items):
            interleaved.append(mover_items[i])
    return interleaved


# ─────────────────────────────────────────────────────────────────────────────
# Copy (reuse-only — v3 banks via copywriter)
# ─────────────────────────────────────────────────────────────────────────────

def _persona_for(cfg: dict, account: str, voice: str) -> dict:
    """Resolve the persona card the same way content_studio does: by account id,
    then by voice, from cfg copywriter.personas."""
    personas = (cfg or {}).get("copywriter", {}).get("personas", {}) or {}
    return personas.get(account) or personas.get(voice) or {}


def _render_copy(candidate: dict, *, account: str, voice: str, persona: dict,
                 slot: str) -> tuple[str, str, list[str]]:
    """Render (text, headline, violations) for a candidate via the v3 banks.

    Builds a movers-desk item dict exactly like content_studio's nightly ones,
    builds the writer context via copywriter.build_context (facts drive the
    number whitelist), stamps type/voice/slot on the context (LIVE-<slot> so the
    hash key — and thus the chosen template variant — varies across slots for the
    same ticker), and renders with write_posts_deterministic. NEVER calls
    write_posts_llm (no network / model at post time). Post text is the
    emit_from_content_plan convention: headline + "\n\n" + body.
    """
    if candidate["type"] == "mover":
        item = {
            "type": "mover",
            "account": account,
            "ticker": candidate["ticker"],
            "cashtag": candidate["cashtag"],
            "_mover_data": candidate["_mover_data"],
            "_mover_facts": candidate["_mover_facts"],
        }
        facts = candidate["_mover_facts"]
    else:
        item = {
            "type": "theme_list",
            "account": account,
            "ticker": "",
            "cashtags": candidate["cashtags"],
            "_theme_data": candidate["_theme_data"],
            "_theme_facts": candidate["_theme_facts"],
        }
        facts = candidate["_theme_facts"]

    ctx = copywriter.build_context(item, persona=persona or None, facts=facts)
    ctx["type"] = item["type"]
    ctx["voice"] = voice
    ctx["slot"] = f"LIVE-{slot}"
    # Text-only lane: exclude template variants that claim an attached chart
    # ("Chart below", "levels are on the chart") — see copywriter._variant_allowed.
    ctx["has_chart"] = False
    if item["type"] == "theme_list":
        # Selection identity only (theme_list skips the ticker-cashtag copy law):
        # a theme item carries ticker "" and a single-context render would always
        # rotate to variant 0. Hashing on the lead member + account + LIVE-slot
        # restores cross-slot/day variety exactly like ticker posts get.
        ctx["ticker"] = candidate.get("_lead_ticker", "")

    posts = copywriter.write_posts_deterministic([ctx])
    post = posts[0] if posts else {"headline": "", "body": "", "violations": ["empty render"]}
    headline = post.get("headline", "") or ""
    body = post.get("body", "") or ""
    text = f"{headline}\n\n{body}" if headline and body else (headline or body)
    return text, headline, list(post.get("violations") or [])


# ─────────────────────────────────────────────────────────────────────────────
# Ledger-derived today-state (posts-today + existing-today dedupe corpus)
# ─────────────────────────────────────────────────────────────────────────────

def _existing_today_items(state: dict, today: str) -> list[dict]:
    """Every item that belongs to 'today' — as_of==today OR created_at date==today.

    This is the corpus for per-day dedupe (mover ticker / theme name) and the
    near-dup gate (jaccard vs any existing today text), across all accounts and
    all statuses.
    """
    items = state.get("items") or {}
    out: list[dict] = []
    for it in items.values():
        as_of = str(it.get("as_of") or "")
        created = str(it.get("created_at") or "")
        if as_of == today or created[:10] == today:
            out.append(it)
    return out


def _live_queued_pt_today(state: dict, today: str) -> list[dict]:
    """This-lane items already queued today (kind mover/theme_list, provenance
    publisher_live_movers, created today). They may still auto-approve this run,
    so they count toward posts-today and the per-account one-per-run law."""
    out: list[dict] = []
    for it in (state.get("items") or {}).values():
        if it.get("provenance") != _PROVENANCE:
            continue
        if it.get("kind") not in {"mover", "theme_list"}:
            continue
        if str(it.get("created_at") or "")[:10] == today:
            out.append(it)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def generate_slot_items(
    root: Path | str,
    *,
    cfg: dict,
    now: datetime,
    state: dict,
    approved_due: list[dict],
    posted_counts: dict[str, int] | None = None,
    cap: int,
    live: bool,
    account_filter: str | None = None,
) -> dict:
    """Generate publish-time mover/theme items for the current slot run.

    Returns a report dict {enabled, generated:[ids], would_generate:[...],
    dropped:[{reason, detail}], quote_source, slot}. NEVER raises — the whole
    body is fail-soft; on error it logs a warning and returns a report with the
    error noted. In dry-run (live=False) it writes NOTHING and fills
    would_generate; enqueues only when live is True.

    `posted_counts` is accepted for API completeness (the publisher passes its
    as_of-based tally) but the cap decision uses the LEDGER-based posts-today this
    module computes from `state` — as_of counting undercounts nightly items that
    carry yesterday's as_of.
    """
    slot: str | None = None
    try:
        r = Path(root)
        pt = _pt_cfg(cfg)

        if not pt["enabled"]:
            return _empty_report(None, enabled=False,
                                 drop=[{"reason": "disabled",
                                        "detail": "publish.publish_time_movers.enabled is false"}])

        # ── Gate 1: weekday + posting window ────────────────────────────────
        if now.weekday() >= 5:  # Sat/Sun
            return _empty_report(None, enabled=True,
                                 drop=[{"reason": "not_weekday", "detail": now.strftime("%A")}])
        slot = _slot_label(now)
        if slot is None:
            return _empty_report(None, enabled=True,
                                 drop=[{"reason": "outside_window",
                                        "detail": f"{now.strftime('%H:%M')}Z not in [13:30,22:00)"}])

        dropped: list[dict] = []

        # ── Load tape + heatmap ─────────────────────────────────────────────
        tape = live_verify.load_live_quotes(r)
        quote_source = str(tape.get("source") or "none")
        movers_data = movers_source.load_movers(r)
        if not movers_data:
            return _empty_report(slot, enabled=True, quote_source=quote_source,
                                 drop=[{"reason": "no_heatmap",
                                        "detail": "movers_source.load_movers returned None"}])

        # ── Gate 2: generation freshness ────────────────────────────────────
        if _tape_stale(tape, movers_data, now, float(pt["max_quote_age_min"])):
            return _empty_report(slot, enabled=True, quote_source=quote_source,
                                 drop=[{"reason": "tape stale",
                                        "detail": f"freshest tape older than "
                                                  f"{pt['max_quote_age_min']}m ({quote_source})"}])

        # ── Live overlay + candidates ───────────────────────────────────────
        overlaid = _overlay_movers(movers_data, tape)

        # ── Gate 3: flat-tape belt ──────────────────────────────────────────
        # The market must actually be MOVING before we claim anything did: a
        # holiday (weekday, crypto still ticking → _tape_stale passes) or a
        # static delayed splice leaves ~every name near 0%. Counted over the
        # union of everything generation draws from — S&P tiles AND theme
        # members (deduped by ticker) — so a theme-only universe is measured
        # by its members, not an absent index board. Fail closed.
        _active_seen: dict[str, float] = {}
        for t in overlaid.get("sp500_tiles") or []:
            tkr = str(t.get("t") or "")
            if tkr:
                _active_seen[tkr] = live_verify._f((t.get("perf") or {}).get("1D")) or 0.0
        for tt in overlaid.get("theme_tiles") or []:
            for m in tt.get("members") or []:
                tkr = str(m.get("t") or "")
                if tkr and tkr not in _active_seen:
                    _active_seen[tkr] = live_verify._f((m.get("perf") or {}).get("1D")) or 0.0
        active_tiles = sum(1 for v in _active_seen.values()
                           if abs(v) >= _ACTIVE_TILE_MIN_ABS)
        if active_tiles < int(pt["min_active_tiles"]):
            return _empty_report(slot, enabled=True, quote_source=quote_source,
                                 drop=[{"reason": "tape_flat",
                                        "detail": f"only {active_tiles} tiles moved "
                                                  f"≥{_ACTIVE_TILE_MIN_ABS}% (min "
                                                  f"{pt['min_active_tiles']}; closed market?)"}])

        candidates = _build_candidates(overlaid, r, cfg or {}, pt)
        if not candidates:
            return _empty_report(slot, enabled=True, quote_source=quote_source,
                                 drop=[{"reason": "no_candidates",
                                        "detail": "no mover/theme cleared the min_abs floors"}])

        # ── Today-state (ledger-based) ──────────────────────────────────────
        today = now.strftime("%Y-%m-%d")
        posted_today = outbox.posted_today_by_account(state, today)
        for it in _live_queued_pt_today(state, today):
            acct = it.get("account", "")
            posted_today[acct] = posted_today.get(acct, 0) + 1
        # This run's already-selected approved_due items also consume a slot.
        for it in (approved_due or []):
            acct = it.get("account", "")
            posted_today[acct] = posted_today.get(acct, 0) + 1

        existing_today = _existing_today_items(state, today)
        # Accounts that already have an approved_due item this run (spacing law:
        # one post per account per slot run).
        due_accounts = {it.get("account", "") for it in (approved_due or [])}
        # Accounts with a live-lane item already queued today (one per run).
        for it in _live_queued_pt_today(state, today):
            due_accounts.add(it.get("account", ""))

        # ── Eligible accounts (deterministic, config order) ─────────────────
        # LIVE + on this lane's allowlist + has a channel — see _per_call_eligible.
        accounts = (cfg or {}).get("desk_network", {}).get("accounts", []) or []
        eligible = [str(a.get("id", "")) for a in _per_call_eligible(
            cfg, lane_key="publish_time_movers", root=r,
            account_filter=account_filter)]
        if not eligible:
            return _empty_report(slot, enabled=True, quote_source=quote_source,
                                 drop=[{"reason": "no_eligible_accounts",
                                        "detail": "no live, lane-allowed account has a publish channel id (or filter mismatch)"}])

        voice_by_id = {str(a.get("id", "")): a.get("voice", "authoritative desk")
                       for a in accounts}

        # Rotate the starting account so the same desk doesn't always lead.
        start = (now.timetuple().tm_yday + _slot_index(slot)) % len(eligible)
        rotated = eligible[start:] + eligible[:start]

        # Sentinel knobs (read from cfg with sentinel in-code fallbacks — never
        # hardcode a cap constant here).
        near_dup_thresh = float(_sentinel_knob(cfg, "near_dup_jaccard",
                                               sentinel._DEFAULT_NEAR_DUP_JACCARD))

        # Per-account caps come from the SAME tier resolver the plan-time gate
        # uses (sentinel.resolve_ramp): this lane auto-approves its own output, so
        # if it read the base block directly a cold account would auto-post the
        # very shapes the D08 ramp exists to withhold. `today` is derived from the
        # injected `now`, so the resolution is as deterministic as the caller's
        # clock — the tier itself never reads a clock of its own.
        _ramp = sentinel.resolve_ramp(cfg or {}, today, root=r)

        def _acct_caps(aid: str) -> dict[str, Any]:
            entry = _ramp["accounts"].get(aid)
            return entry["caps"] if entry else _ramp["fallback"]

        max_per_run = int(pt["max_per_run"])

        # Pre-compute today token sets for the near-dup gate.
        existing_token_sets = [sentinel._token_set(_item_full_text(it)) for it in existing_today]

        generated: list[str] = []
        would_generate: list[dict] = []
        accepted_texts: list[frozenset[str]] = []
        assigned_accounts: set[str] = set()
        acct_cursor = 0

        for cand in candidates:
            if (len(generated) + len(would_generate)) >= max_per_run:
                break
            if assigned_accounts >= set(rotated):
                # Every postable account already took an item this run — no
                # later candidate can land. One summary row, not one per drop.
                dropped.append({"reason": "accounts_exhausted",
                                "detail": f"all {len(assigned_accounts)} eligible "
                                          f"account(s) assigned this run"})
                break

            lead_ticker = (cand["ticker"] if cand["type"] == "mover"
                           else cand.get("_lead_ticker", ""))
            lead_cashtag = f"${lead_ticker}" if lead_ticker else ""

            # ── Per-day dedupe (any account/status) ─────────────────────────
            if cand["type"] == "mover":
                if any(it.get("kind") == "mover"
                       and str((it.get("source") or {}).get("ticker") or "").upper() == cand["ticker"].upper()
                       for it in existing_today):
                    dropped.append({"reason": "dup_today_mover", "detail": cand["ticker"]})
                    continue
            else:
                theme_name = cand.get("_theme_name", "")
                if any(it.get("kind") == "theme_list"
                       and str((it.get("source") or {}).get("theme") or "") == theme_name
                       for it in existing_today):
                    dropped.append({"reason": "dup_today_theme", "detail": theme_name})
                    continue

            # ── Ramp gate: theme_list does not ship from a cold account ─────
            # A theme_list carries ≥4 member cashtags by format — the cashtag-
            # piggybacking fingerprint (D08 R3) — so the tier row withholds the
            # whole format until week 5. Mirrors the plan-tier ramp_theme_list
            # quarantine; without it this lane would auto-approve around the gate.
            if cand["type"] == "theme_list":
                if not any(_acct_caps(a)["theme_list_allowed"] for a in rotated):
                    dropped.append({
                        "reason": "ramp_theme_list",
                        "detail": f"{cand.get('_theme_name', '') or lead_cashtag}: "
                                  f"no eligible account is past the theme_list ramp gate",
                    })
                    continue

            # ── Pick an eligible account for this candidate ─────────────────
            chosen: str | None = None
            for _ in range(len(rotated)):
                aid = rotated[acct_cursor % len(rotated)]
                acct_cursor += 1
                if aid in assigned_accounts:
                    continue
                if aid in due_accounts:
                    continue  # spacing: one post per account per slot run
                # Ledger-based daily cap, tier-narrowed. TWO bugs lived on this
                # line. (1) The bare `>= cap` treated the UNLIMITED sentinel as a
                # cap of -1, so `0 >= -1` was true for every account and this
                # lane generated NOTHING from 2026-07-24 onward — the negative
                # cap must be routed through the same guarded shape outbox.enqueue
                # uses (`cap >= 0 and …`). (2) It read only the base cap, so once
                # unbounded a week-1 desk had no post-time ceiling at all;
                # stricter_daily_cap folds in the account's ramp tier.
                _aid_cap = outbox.stricter_daily_cap(
                    cap, _acct_caps(aid)["max_posts_per_account_per_day"])
                if _aid_cap >= 0 and posted_today.get(aid, 0) >= _aid_cap:
                    continue
                if cand["type"] == "theme_list" and not _acct_caps(aid)["theme_list_allowed"]:
                    continue  # this desk is still ramping — see the gate above
                # Per-account same-cashtag day cap: skip an account already
                # carrying an item today with this candidate's ticker or lead
                # cashtag in its text (sentinel max_same_cashtag_per_account_per_day,
                # tier-narrowed for a ramping desk).
                if _account_same_cashtag_today(existing_today, aid, lead_ticker,
                                               lead_cashtag) \
                        >= _acct_caps(aid)["max_same_cashtag_per_account_per_day"]:
                    continue
                chosen = aid
                break
            if chosen is None:
                dropped.append({"reason": "no_account",
                                "detail": f"no eligible account for {lead_cashtag or cand['type']}"})
                continue

            voice = voice_by_id.get(chosen, "authoritative desk")
            persona = _persona_for(cfg or {}, chosen, voice)

            # ── Copy (reuse-only) ───────────────────────────────────────────
            try:
                text, headline, violations = _render_copy(
                    cand, account=chosen, voice=voice, persona=persona, slot=slot)
            except Exception as exc:  # noqa: BLE001
                dropped.append({"reason": "copy_error", "detail": f"{lead_cashtag}: {exc}"})
                continue
            if not text:
                dropped.append({"reason": "empty_copy", "detail": lead_cashtag})
                continue
            # Fail-closed: any validate_copy violation drops the candidate — there
            # is no operator at post time to catch bad copy.
            if violations:
                dropped.append({"reason": "copy_violation",
                                "detail": f"{lead_cashtag}: {violations[:3]}"})
                continue

            # ── Cashtag breadth (movers only; theme_list exempt, per sentinel) ─
            # Cap is the chosen account's effective one: a ramping desk gets its
            # tier's tighter value, a graduated desk keeps the base block's.
            if cand["type"] == "mover":
                max_cashtags = _acct_caps(chosen)["max_cashtags_per_post"]
                distinct = set(_CASHTAG_RE.findall(text))
                if len(distinct) > max_cashtags:
                    dropped.append({"reason": "cashtag_breadth",
                                    "detail": f"{lead_cashtag}: {len(distinct)} > {max_cashtags}"})
                    continue

            # ── Near-dup gate (vs other accepted this run + existing today) ──
            tokset = sentinel._token_set(text)
            if any(sentinel._jaccard_sets(tokset, prev) >= near_dup_thresh
                   for prev in accepted_texts):
                dropped.append({"reason": "near_dup_run", "detail": lead_cashtag})
                continue
            if any(sentinel._jaccard_sets(tokset, prev) >= near_dup_thresh
                   for prev in existing_token_sets):
                dropped.append({"reason": "near_dup_today", "detail": lead_cashtag})
                continue

            # ── Build the outbox item + source stamp ────────────────────────
            source = _build_source(cand, slot, now, quote_source)
            try:
                item = outbox.make_item(
                    account=chosen,
                    kind=cand["type"],
                    text=text,
                    as_of=today,
                    scheduled_at="immediate",
                    slot=f"LIVE-{slot}",
                    priority=6,   # operator-approved D1 items are priority 5 → sort first
                    provenance=_PROVENANCE,
                    source=source,
                    now=now,
                )
            except ValueError as exc:
                dropped.append({"reason": "make_item_invalid", "detail": f"{lead_cashtag}: {exc}"})
                continue

            # Commit account assignment BEFORE enqueue so a per-run second
            # candidate never targets the same desk even if enqueue duplicates.
            assigned_accounts.add(chosen)
            accepted_texts.append(tokset)

            if not live:
                would_generate.append({
                    "id": item["id"], "account": chosen, "kind": cand["type"],
                    "ticker": lead_ticker, "slot": f"LIVE-{slot}",
                    "text": text.replace("\n", " ")[:200],
                })
                # Charge the account so the next candidate rotates onward in dry-run too.
                posted_today[chosen] = posted_today.get(chosen, 0) + 1
                existing_token_sets.append(tokset)
                existing_today.append(item)
                continue

            # Enqueue re-checks the cap against the day ledger; hand it the
            # CHOSEN account's tier-narrowed value so the two gates agree.
            result = outbox.enqueue(
                item, r,
                max_per_account_day=outbox.stricter_daily_cap(
                    cap, _acct_caps(chosen)["max_posts_per_account_per_day"]))
            if result == "queued":
                generated.append(item["id"])
                posted_today[chosen] = posted_today.get(chosen, 0) + 1
                existing_token_sets.append(tokset)
                existing_today.append(item)
            elif result == "duplicate":
                # EXPECTED when the tape hasn't moved since the prior slot: the
                # identical text hashes to the same id. That idempotency is a
                # feature — report it quietly, don't treat it as an error.
                dropped.append({"reason": "duplicate", "detail": f"{lead_cashtag} ({item['id']})"})
            elif result == "cap_exceeded":
                dropped.append({"reason": "cap_exceeded", "detail": lead_cashtag})
                # Roll back the account reservation — nothing was written.
                assigned_accounts.discard(chosen)
                accepted_texts.pop()
            else:
                dropped.append({"reason": "enqueue_failed", "detail": f"{lead_cashtag}: {result}"})
                assigned_accounts.discard(chosen)
                accepted_texts.pop()

        return {
            "enabled": True,
            "generated": generated,
            "would_generate": would_generate,
            "dropped": dropped,
            "quote_source": quote_source,
            "slot": slot,
        }

    except Exception as exc:  # noqa: BLE001
        log.warning("publish_time_content.generate_slot_items: %s", exc)
        return {
            "enabled": True,
            "generated": [],
            "would_generate": [],
            "dropped": [{"reason": "error", "detail": str(exc)}],
            "quote_source": "none",
            "slot": slot or "",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Small pure helpers used above
# ─────────────────────────────────────────────────────────────────────────────

def _item_full_text(item: dict) -> str:
    """The text used for near-dup — outbox items carry a single flat `text`."""
    return str(item.get("text") or "")


def _account_same_cashtag_today(existing_today: list[dict], account: str,
                                ticker: str, cashtag: str) -> int:
    """Count today's items on `account` whose source.ticker matches the candidate
    ticker OR whose text contains the candidate's lead cashtag (sentinel's
    per-account same-cashtag/day heuristic)."""
    tkr_u = str(ticker or "").upper()
    n = 0
    for it in existing_today:
        if it.get("account", "") != account:
            continue
        src_tkr = str((it.get("source") or {}).get("ticker") or "").upper()
        if tkr_u and src_tkr == tkr_u:
            n += 1
            continue
        if cashtag and cashtag in str(it.get("text") or ""):
            n += 1
    return n


def _build_source(cand: dict, slot: str, now: datetime, quote_source: str) -> dict[str, Any]:
    """The source stamp the live tape gate re-checks at post time.

    baseline_pct / ticker are what live_verify.verify_item re-verifies. For a
    mover that is the mover's ticker + its live pct. For a theme it is the LEAD
    MEMBER's ticker + pct (not the aggregate) — stamping the loudest number in
    the text makes the gate verify the exact figure a reader sees.
    """
    if cand["type"] == "mover":
        return {
            "lane": "publish_time",
            "slot_run": slot,
            "generated_at": _iso_now(now),
            "quote_source": quote_source,
            "ticker": cand["ticker"],
            "baseline_pct": (cand.get("_mover_data") or {}).get("pct"),
        }
    return {
        "lane": "publish_time",
        "slot_run": slot,
        "generated_at": _iso_now(now),
        "quote_source": quote_source,
        "ticker": cand.get("_lead_ticker", ""),
        "baseline_pct": cand.get("_lead_pct"),
        "theme": cand.get("_theme_name", ""),
        "agg_pct": cand.get("_agg_pct"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Publish-time DAILY READ ("My read on today's move", kind=event)
# ─────────────────────────────────────────────────────────────────────────────
#
# Sibling to generate_slot_items, one family over. The NIGHTLY plan bakes the
# `event` post at ~04:00 UTC but schedules it after the close, so it ships a
# driver read written ~18h stale. This generates the read AT publish time from
# the FRESH daily brief (market_facts.event_facts reads why_the_tape_moved,
# which refreshes intraday), on the after-close ladder slot, ONCE per day.
#
# DARK BY DEFAULT: publish.publish_time_read.enabled is False when the block is
# absent, so old configs / test fixtures without the block never fire. When
# disabled the function returns a disabled report and writes NOTHING — nothing
# can auto-post under the default config.

# In-code defaults for the publish.publish_time_read block (mirror _DEFAULTS).
_READ_DEFAULTS: dict[str, Any] = {
    "enabled": False,       # DARK by default (operator arms after dry-runs)
    # After-close ladder slot. Under the 45-min ladder (#3855,
    # outbox._LADDER_PT_TIMES) the last slot S19 (17:30 PT) owns the open-ended
    # evening tail, so it is the after-close block the daily read fires in.
    # (Was "S8" = 18:00 PT under the retired 2-hour 8-slot ladder — #3849
    # shipped against that ladder minutes before #3855 replaced it.)
    "slot": "S19",
}

_READ_KIND = "event"


def _read_cfg(cfg: dict | None) -> dict[str, Any]:
    """Resolve publish.publish_time_read over the in-code defaults (fail-soft).

    Mirrors _pt_cfg: a missing block leaves `enabled` False (the dark default),
    and a junk value coerces to the default type rather than raising.
    """
    out = dict(_READ_DEFAULTS)
    try:
        block = ((cfg or {}).get("publish") or {}).get("publish_time_read") or {}
        for k, dv in _READ_DEFAULTS.items():
            if k in block:
                if isinstance(dv, bool):
                    v = block[k]
                    out[k] = v if isinstance(v, bool) else (
                        str(v).strip().lower() in {"1", "true", "yes"})
                else:
                    out[k] = type(dv)(block[k])
    except Exception as exc:  # noqa: BLE001
        log.warning("publish_time_content: bad publish.publish_time_read config "
                    "(%s) — using defaults", exc)
    return out


def _ladder_local(now: datetime) -> datetime | None:
    """`now` in the ladder's Pacific clock, or None if the tz database is absent.

    The after-close ladder is a PACIFIC-clock concept, so both the weekday gate
    and the slot gate must read the Pacific frame — an S19 (17:30 PT) evening instant is
    the NEXT UTC calendar day (Fri 18:00 PT == Sat 01:00 UTC), so a UTC-based
    weekday check would wrongly reject a legitimate Friday after-close read and
    wrongly admit a Sunday-evening one. zoneinfo keeps the Pacific→UTC offset
    DST-safe (never hardcode -7/-8).
    """
    try:
        from zoneinfo import ZoneInfo  # noqa: PLC0415
        return now.astimezone(ZoneInfo(outbox._LADDER_TZ))
    except Exception:  # noqa: BLE001
        return None


def _ladder_slot_label(local: datetime) -> str | None:
    """Map a Pacific-LOCAL datetime to its 45-min ladder slot label (S1..S19).

    The daily read fires on an after-close ladder slot (config default S19 =
    17:30 PT), NOT on the AM/PM/EOD publish window `_slot_label` returns. Each
    slot owns [t, t+45min) per outbox._LADDER_PT_TIMES; the LAST slot owns the
    open-ended evening tail (17:30 PT to midnight) so every after-close sweep
    lands in it. Ported from outbox._LADDER_PT_HOURS (2-hour, S1..S8) after
    #3855 replaced that ladder and left this consumer referencing a name that
    no longer existed — the lane failed soft to a no-op on every sweep.
    """
    minutes = local.hour * 60 + local.minute
    ordered = sorted(outbox._LADDER_PT_TIMES.items(),
                     key=lambda kv: kv[1][0] * 60 + kv[1][1])
    last_slot = ordered[-1][0]
    best: str | None = None
    for slot, (h, m) in ordered:
        start = h * 60 + m
        end = start + 45 if slot != last_slot else 24 * 60
        if start <= minutes < end:
            best = slot
    return best


def _empty_read_report(slot: str | None, *, enabled: bool,
                       drop: list[dict] | None = None) -> dict:
    """Disabled/empty report for the read lane (mirror _empty_report shape,
    quote_source fixed to 'brief' since this lane reads the daily brief)."""
    return {
        "enabled": enabled,
        "generated": [],
        "would_generate": [],
        "dropped": drop or [],
        "quote_source": "brief",
        "slot": slot or "",
    }


def _read_top_fact(facts_data: dict | None) -> str:
    """The freshest 'What's driving today: …' line, or '' if the brief has none.

    event_facts falls back to macro_facts, which returns an EMPTY facts list when
    neither regime nor brief exists — so an empty/absent text means no usable
    driver read (→ dropped no_brief)."""
    for f in (facts_data or {}).get("facts") or []:
        txt = str(f.get("text") or "").strip()
        if txt:
            return txt
    return ""


def _queued_read_today(state: dict, today: str) -> set[str]:
    """Accounts that already have a publish-time-lane `event` item queued today
    (provenance publisher_live_movers, created today). Enforces once/day per
    account across sweeps — a second sweep in the same after-close block must not re-post.
    """
    out: set[str] = set()
    for it in (state.get("items") or {}).values():
        if it.get("provenance") != _PROVENANCE:
            continue
        if it.get("kind") != _READ_KIND:
            continue
        if str(it.get("created_at") or "")[:10] == today:
            out.add(str(it.get("account") or ""))
    return out


def generate_read_item(
    root: Path | str,
    *,
    cfg: dict,
    now: datetime,
    state: dict,
    live: bool,
    account_filter: str | None = None,
) -> dict:
    """Generate the publish-time DAILY READ (kind=event) for the after-close slot.

    Returns a report dict with the SAME shape generate_slot_items returns:
    {enabled, generated:[ids], would_generate:[{account,kind,text}],
    dropped:[{reason,detail}], quote_source:"brief", slot}. NEVER raises — the
    whole body is fail-soft; on error it logs a warning and returns a report with
    the error noted. In dry-run (live=False) it writes NOTHING and fills
    would_generate; enqueues only when live is True.

    DARK GATE: when publish.publish_time_read.enabled is false (the default) it
    returns a disabled report immediately and writes nothing.
    """
    slot: str | None = None
    try:
        r = Path(root)
        rc = _read_cfg(cfg)

        # ── DARK GATE ───────────────────────────────────────────────────────
        if not rc["enabled"]:
            return _empty_read_report(None, enabled=False,
                                      drop=[{"reason": "disabled",
                                             "detail": "publish.publish_time_read.enabled is false"}])

        # ── Gate 1: weekday + configured after-close ladder slot ────────────
        # Both read the PACIFIC clock (see _ladder_local): the after-close slot
        # is a Pacific-clock concept and its UTC instant is the next calendar day.
        local = _ladder_local(now)
        if local is None:
            return _empty_read_report(None, enabled=True,
                                      drop=[{"reason": "no_tzdata",
                                             "detail": "zoneinfo tz database unavailable"}])
        if local.weekday() >= 5:  # Sat/Sun (Pacific)
            return _empty_read_report(None, enabled=True,
                                      drop=[{"reason": "not_weekday", "detail": local.strftime("%A")}])
        want_slot = str(rc["slot"] or "").strip().upper()
        slot = _ladder_slot_label(local)
        if slot != want_slot:
            # Not the after-close slot (or outside the ladder) → empty report so
            # the read fires ONCE/day, not on every sweep.
            return _empty_read_report(slot, enabled=True,
                                      drop=[{"reason": "wrong_slot",
                                             "detail": f"{slot or 'none'} != {want_slot}"}])

        # ── Fresh driver fact from the daily brief ──────────────────────────
        facts_data = market_facts.event_facts(r)
        top_fact = _read_top_fact(facts_data)
        if not top_fact:
            return _empty_read_report(slot, enabled=True,
                                      drop=[{"reason": "no_brief",
                                             "detail": "event_facts returned no usable driver read"}])

        today = now.strftime("%Y-%m-%d")

        # ── Eligible accounts (deterministic, config order) ─────────────────
        # Mirror generate_slot_items EXACTLY by sharing its helper: live accounts
        # (config `enabled` via the accounts model, overrides honoured), on this
        # lane's allowlist, holding a publish channel, matching account_filter.
        already_today = _queued_read_today(state, today)
        eligible = [
            acc for acc in _per_call_eligible(
                cfg, lane_key="publish_time_read", root=r,
                account_filter=account_filter)
            # once/day per account (spacing across sweeps)
            if str(acc.get("id", "")) not in already_today
        ]
        if not eligible:
            return _empty_read_report(slot, enabled=True,
                                      drop=[{"reason": "no_eligible_accounts",
                                             "detail": "no live, lane-allowed account has a publish channel (filter/already-posted)"}])

        dropped: list[dict] = []
        generated: list[str] = []
        would_generate: list[dict] = []

        for acc in eligible:
            aid = str(acc.get("id", ""))
            voice = acc.get("voice", "authoritative desk")
            persona = _persona_for(cfg or {}, aid, voice)

            # ── Copy: mirror content_studio's nightly event context exactly ──
            # (content_studio.py ~1713-1728). Non-ticker item → the deterministic
            # picker seeds variant rotation by CALENDAR DAY off ctx["as_of"] (the
            # #3824 fix), so a single daily read differs day to day. Feed the fresh
            # event_facts so {top_fact} is the "What's driving today: …" line.
            try:
                item_dict = {"type": _READ_KIND, "account": aid, "ticker": ""}
                ctx = copywriter.build_context(
                    item_dict, persona=persona or None, facts=facts_data or None)
                ctx["type"] = _READ_KIND
                ctx["voice"] = voice
                ctx["slot"] = f"LIVE-{slot}"
                ctx["as_of"] = today
                ctx["has_chart"] = False
                posts = copywriter.write_posts_deterministic([ctx])
                post = posts[0] if posts else {}
                headline = str(post.get("headline") or "")
                body = str(post.get("body") or "")
                text = (f"{headline}\n\n{body}" if headline and body
                        else (headline or body))
                violations = list(post.get("violations") or [])
            except Exception as exc:  # noqa: BLE001
                dropped.append({"reason": "copy_error", "detail": f"{aid}: {exc}"})
                continue
            if not text:
                dropped.append({"reason": "empty_copy", "detail": aid})
                continue
            # Fail-closed: any validate_copy violation drops the candidate — there
            # is no operator at post time to catch bad copy.
            if violations:
                dropped.append({"reason": "copy_violation",
                                "detail": f"{aid}: {violations[:3]}"})
                continue

            # ── Source stamp (the read carries the brief driver, no tape pct) ─
            source = {
                "lane": "publish_time",
                "slot_run": slot,
                "generated_at": _iso_now(now),
                "quote_source": "brief",
                "driver": top_fact,
            }
            try:
                item = outbox.make_item(
                    account=aid,
                    kind=_READ_KIND,
                    text=text,
                    as_of=today,
                    scheduled_at="immediate",
                    slot=f"LIVE-{slot}",
                    priority=6,
                    provenance=_PROVENANCE,
                    source=source,
                    now=now,
                )
            except ValueError as exc:
                dropped.append({"reason": "make_item_invalid", "detail": f"{aid}: {exc}"})
                continue

            if not live:
                would_generate.append({
                    "id": item["id"], "account": aid, "kind": _READ_KIND,
                    "ticker": "", "slot": f"LIVE-{slot}",
                    "text": text.replace("\n", " ")[:200],
                })
                continue

            result = outbox.enqueue(item, r)
            if result == "queued":
                generated.append(item["id"])
            elif result == "duplicate":
                # EXPECTED if the brief hasn't changed since a prior sweep: the
                # identical text hashes to the same id (idempotent). The cross-
                # night dedup in enqueue (#3824) likewise catches a same-week
                # identical repeat. Report quietly, not as an error.
                dropped.append({"reason": "duplicate", "detail": f"{aid} ({item['id']})"})
            else:
                dropped.append({"reason": "enqueue_failed", "detail": f"{aid}: {result}"})

        return {
            "enabled": True,
            "generated": generated,
            "would_generate": would_generate,
            "dropped": dropped,
            "quote_source": "brief",
            "slot": slot,
        }

    except Exception as exc:  # noqa: BLE001
        log.warning("publish_time_content.generate_read_item: %s", exc)
        return {
            "enabled": True,
            "generated": [],
            "would_generate": [],
            "dropped": [{"reason": "error", "detail": str(exc)}],
            "quote_source": "brief",
            "slot": slot or "",
        }
