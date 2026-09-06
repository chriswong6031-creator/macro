"""engine.chronicle.impact — event-to-asset consequence projection (F05, MO-PAID-017).

Reads chronicle spine events (the ONE canonical event owner — see spine.py's
module docstring) and projects a deterministic, owner-native
consequence/impact view per event: which tickers are implicated, whether the
linkage is direct (the event names the ticker) or second-order (inferred only
via shared theme, never via a ticker the event itself did not name), when the
underlying development happened vs when it became knowable, and a causal
label that is capped by construction to never claim more than the evidence
supports.

Do-not-redo (agentos/handoffs/MARKET-ONTOLOGY-F05-EVENT-IMPACT-CATALYST-FABLE-COO-2026-08-26.md):
no second event ID/database, no headline-count event identity, no LLM fact
extraction authority, no opaque catalyst ranker. This module performs no
scoring, no ranking, and no statistical estimation — it is a pure,
deterministic re-projection of fields already present on the chronicle.event.v1
record produced by spine.py. Calibrated impact magnitude is explicitly gated
on K5 (Evaluation OS / registered model law) and always reports as
``not_yet_knowable`` here rather than being estimated by this module.

Materiality law: "direct" means the ticker appears in the event's own
``tickers`` field (the adapter that produced the event already asserted that
linkage from source data). "second_order" means a ticker is NOT on the event
but shares a *narrow* theme with the event and IS directly implicated by some
OTHER event carrying that theme, dated on-or-before this event (point-in-time
-- no future-event leakage) -- a strictly weaker, labelled-as-such claim,
never silently promoted to direct. Broad co-mention themes (e.g. corpus-wide
"earnings") fail closed rather than fabricating materiality. When more than
``SECOND_ORDER_MAX_PER_EVENT`` candidates remain after the specificity +
support filters, the projection refuses ALL second-order exposures for that
event (fail closed on ambiguity) and prints the candidate/dropped counts --
it never ranks by co-mention count or alphabetical tiebreak to pick winners.

Causal label law: every projection carries ``causal_label`` fixed to
``"uncalibrated_association"``. This module has no identification strategy and
therefore never emits "causal" -- that ceiling is structural, not a runtime
check the caller could accidentally skip.

Bitemporal honesty (no fabricated known-at clock): every adapter today sets
``ts`` to either a genuine source publication timestamp, or (when the source
gives only a calendar date) exactly ``f"{date}T00:00:00Z"`` -- the same
instant as ``event_time``, not a distinct ingestion/discovery clock. Printing
that synthetic midnight stamp as "known_at" would fabricate a bitemporal claim
the ledger explicitly disclaims (correction_behavior: "event spine (chronicle)
-- no bitemporal claim made"). So ``known_at`` is populated ONLY when ``ts``
is genuinely distinct from the synthetic midnight-of-date value; otherwise it
is printed as ``None`` with a typed reason, per the fail-closed / nulls-
printed-not-hidden law -- never silently collapsed into ``event_time`` and
never fabricated.

Correction law: an event's ``kind``/fields never carry a corrected/withdrawn
state today (authoritative retractions are excluded from events.jsonl
entirely by spine.apply_authoritative_retractions before this module ever
sees them). A caller that still holds a retracted or superseded event object
(e.g. re-projecting a stale snapshot) can mark it explicitly via
``retracted=True`` / ``retraction_reason`` on :func:`project_event_impact`;
this module never infers retraction on its own -- that stays spine's call.

Nightly write law: this module never writes a git-tracked data/ artifact.
Consumers call :func:`project_events_impact` / :func:`glance_consequence_surface`
at render or inspect time over a bounded event window.
"""
from __future__ import annotations

import re
from typing import Iterable

# Fixed by construction: this module performs no causal identification, so it
# can never emit a label stronger than an uncalibrated association regardless
# of event kind, weight_hint, or theme overlap.
CAUSAL_LABEL = "uncalibrated_association"

MATERIALITY_DIRECT = "direct"
MATERIALITY_SECOND_ORDER = "second_order"

# K5 (Evaluation OS / registered model law) is not consumed here -- any
# magnitude/probability estimate is out of scope for this projection and
# always reports this reason code rather than a fabricated number.
CALIBRATED_IMPACT_GATE_REASON = "not_yet_knowable_k5_gated"

# No genuine source clock at all (neither ``date`` nor ``ts`` present).
NO_SOURCE_CLOCK = "no_source_clock"
# ``ts`` exists but is not distinguishable from the synthetic
# midnight-of-``date`` stamp every non-timestamped adapter emits -- printing
# it as a separate "known_at" would fabricate a bitemporal claim.
NO_DISTINCT_SOURCE_CLOCK = "no_distinct_source_clock"

# Second-order eligibility (fail closed on weak materiality / ambiguity).
# MIN_SUPPORT is an eligibility floor, not a ranker. MAX_PER_EVENT is a
# refuse-all ceiling when ambiguity remains after the theme-specificity gate
# -- never a top-N selector. THEME_MAX_SHARE refuses corpus-dominant themes
# (measured: "earnings" alone is ~82% of events.jsonl) where co-theme carries
# no information.
SECOND_ORDER_MIN_SUPPORT = 2
SECOND_ORDER_MAX_PER_EVENT = 5
SECOND_ORDER_THEME_MAX_SHARE = 0.05
# Share gate only applies once a theme's absolute count clears this floor —
# otherwise a 3-event fixture would refuse every theme (3/3 = 100% share)
# while the real corpus still needs the share gate for "earnings" (~82%).
SECOND_ORDER_THEME_BROAD_MIN_COUNT = 40
SECOND_ORDER_AMBIGUOUS_REASON = "second_order_refused_ambiguous_cap"
SECOND_ORDER_THEME_TOO_BROAD_REASON = "second_order_refused_theme_too_broad"
# Kept as an alias so older call-sites/tests that still reference the prior
# truncation reason string keep resolving; new emits use AMBIGUOUS_REASON.
SECOND_ORDER_CAPPED_REASON = SECOND_ORDER_AMBIGUOUS_REASON

# Glance-tier surface bound (News Feed consequence panel). Bounded so render
# never runs the full-corpus projection.
GLANCE_EVENT_LIMIT = 24


def _midnight_of(date: str | None) -> str | None:
    return f"{date}T00:00:00Z" if date else None


def _time_fields(event: dict) -> tuple[str | None, str | None, str | None]:
    """Return (event_time, known_at, known_at_null_reason).

    Never fabricates a known_at that the source data does not actually
    support -- see the bitemporal-honesty note in the module docstring.
    event_time and known_at stay the same granularity family: event_time is
    always a calendar date (YYYY-MM-DD) when knowable; known_at is an ISO
    instant only when genuinely distinct from midnight-of-that-date.
    """
    date = event.get("date") or None
    ts = event.get("ts") or None

    if not date and not ts:
        return None, None, NO_SOURCE_CLOCK

    # When date is absent but ts is present, recover the calendar date from
    # the timestamp so we never print known_at beside a null event_time.
    if not date and isinstance(ts, str) and len(ts) >= 10 and ts[4] == "-" and ts[7] == "-":
        date = ts[:10]

    event_time = date
    if ts and ts != _midnight_of(date):
        return event_time, ts, None
    return event_time, None, NO_DISTINCT_SOURCE_CLOCK


def project_event_impact(
    event: dict,
    *,
    second_order_tickers: Iterable[str] = (),
    second_order_sources: dict[str, list[str]] | None = None,
    retracted: bool = False,
    retraction_reason: str | None = None,
) -> dict:
    """Project one chronicle.event.v1 record into a consequence/impact view.

    ``second_order_tickers`` (optional) lets a caller pass tickers implicated
    only via co-theme propagation from OTHER events -- this function never
    invents them itself. A ticker present in both the event's own ``tickers``
    and ``second_order_tickers`` is reported once, as direct (direct always
    wins; second-order is never used to demote a directly-named ticker).

    ``second_order_sources`` (optional) maps each second-order ticker to the
    originating event id(s) that directly named it under the shared theme --
    K1 evidence for what would otherwise be an unsourced claim.

    ``retracted``/``retraction_reason`` let a caller mark an event whose
    authoritative status has been withdrawn (spine.py's correction plane);
    such an event still carries its evidence fields but its exposures are
    force-emptied and its state is reported explicitly rather than silently
    projecting a live claim for a withdrawn record.
    """
    direct = [t for t in (event.get("tickers") or []) if t]
    direct_set = set(direct)
    second_order = [t for t in dict.fromkeys(second_order_tickers or ()) if t and t not in direct_set]
    second_order_sources = second_order_sources or {}

    event_time, known_at, known_at_reason = _time_fields(event)

    if retracted:
        exposures: list[dict] = []
    else:
        exposures = [
            {"ticker": t, "materiality": MATERIALITY_DIRECT} for t in direct
        ] + [
            {
                "ticker": t,
                "materiality": MATERIALITY_SECOND_ORDER,
                "source_event_ids": sorted(second_order_sources.get(t, [])),
            }
            for t in second_order
        ]

    return {
        "event_id": event.get("id"),
        # Time law: event_time is when the underlying development occurred
        # (spine's ``date``); known_at is when the chronicle store could
        # first know about it, printed ONLY when the source data actually
        # supports a distinct clock -- otherwise None + a typed reason
        # (never fabricated, never silently collapsed into event_time).
        "event_time": event_time,
        "known_at": known_at,
        "known_at_reason": known_at_reason,
        "source": event.get("source"),
        "source_ref": event.get("source_ref"),
        "kind": event.get("kind"),
        "title": event.get("title"),
        "facts": list(event.get("facts") or []),
        "links": event.get("links"),
        "themes": list(event.get("themes") or []),
        "exposures": exposures,
        "causal_label": CAUSAL_LABEL,
        "calibrated_impact": None,
        "calibrated_impact_reason": CALIBRATED_IMPACT_GATE_REASON,
        "state": "retracted" if retracted else "active",
        "retraction_reason": retraction_reason if retracted else None,
    }


def _co_theme_index(events: list[dict]) -> dict[str, list[tuple[str, list[str], str | None]]]:
    """theme -> [(date, tickers, event_id), ...] for every event that
    directly names tickers under that theme -- one entry per event so
    callers can apply an as-of cutoff and a support-count eligibility test.
    """
    out: dict[str, list[tuple[str, list[str], str | None]]] = {}
    for ev in events:
        tickers = [t for t in (ev.get("tickers") or []) if t]
        date = ev.get("date") or ""
        if not tickers:
            continue
        for theme in (ev.get("themes") or []):
            out.setdefault(theme, []).append((date, tickers, ev.get("id")))
    return out


def _eligible_themes(events: list[dict]) -> set[str]:
    """Themes narrow enough that co-theme overlap can carry materiality.

    A theme is refused only when it is both numerous in absolute terms
    (``SECOND_ORDER_THEME_BROAD_MIN_COUNT``) AND appears on more than
    ``SECOND_ORDER_THEME_MAX_SHARE`` of the event set. Corpus-dominant themes
    like "earnings" (~82% of events.jsonl) fail closed; small fixtures and
    genuinely narrow themes stay eligible.
    """
    if not events:
        return set()
    counts: dict[str, int] = {}
    for ev in events:
        for theme in set(ev.get("themes") or []):
            counts[theme] = counts.get(theme, 0) + 1
    n = len(events)
    eligible: set[str] = set()
    for theme, count in counts.items():
        if count >= SECOND_ORDER_THEME_BROAD_MIN_COUNT and (count / n) > SECOND_ORDER_THEME_MAX_SHARE:
            continue
        eligible.add(theme)
    return eligible


def project_events_impact(
    events: list[dict], *, eligible_themes: set[str] | None = None,
) -> list[dict]:
    """Project a full event list, resolving second-order (co-theme) exposures.

    Point-in-time: a ticker only propagates to an event via themes from OTHER
    events dated on-or-before that event's own date -- a later event can never
    leak its ticker backward onto an earlier one.

    Fail-closed specificity: only themes at-or-below
    ``SECOND_ORDER_THEME_MAX_SHARE`` of the corpus participate. Broad themes
    are refused with a typed reason, not ranked through.

    Fail-closed ambiguity: a ticker must be directly named by at least
    ``SECOND_ORDER_MIN_SUPPORT`` prior co-theme events; if more than
    ``SECOND_ORDER_MAX_PER_EVENT`` candidates remain, ALL second-order
    exposures for that event are refused and the candidate/dropped counts are
    printed. There is no support-count or alphabetical top-N selector -- that
    would be an opaque catalyst ranker (do_not_redo).

    Deterministic and order-preserving: iterating the same event list twice
    yields byte-identical output, matching spine.py's byte-stable regeneration
    contract. No field outside the event's own schema-allowed data is
    consulted -- no external ranking, no LLM call.

    ``eligible_themes``, when given, overrides the eligibility computed from
    ``events`` alone (MAJOR 1). A windowed caller (e.g.
    :func:`glance_consequence_surface`) must compute eligibility over the
    FULL corpus and pass it here -- a small window can never contain the
    ``SECOND_ORDER_THEME_BROAD_MIN_COUNT`` occurrences needed to refuse a
    corpus-dominant theme like "earnings" on its own.
    """
    eligible = _eligible_themes(events) if eligible_themes is None else eligible_themes
    by_theme = {
        theme: rows for theme, rows in _co_theme_index(events).items()
        if theme in eligible
    }
    projections = []
    for ev in events:
        own = set(ev.get("tickers") or [])
        own_date = ev.get("date") or ""
        own_themes = list(ev.get("themes") or [])
        refused_themes = sorted({t for t in own_themes if t not in eligible})

        # ticker -> set of supporting (prior, on-or-before-date) event ids
        support: dict[str, set[str]] = {}
        for theme in own_themes:
            if theme not in eligible:
                continue
            for date, tickers, src_id in by_theme.get(theme, ()):
                if date > own_date:
                    continue
                if src_id == ev.get("id"):
                    continue
                for t in tickers:
                    if t in own:
                        continue
                    support.setdefault(t, set()).add(src_id)

        candidates = [
            (t, sorted(ids)) for t, ids in support.items()
            if len(ids) >= SECOND_ORDER_MIN_SUPPORT
        ]
        # Deterministic order by ticker name only -- NEVER by support count.
        # Sorting here is for stable output, not selection: when over the
        # ceiling we refuse the whole set rather than taking a prefix.
        candidates.sort(key=lambda pair: pair[0])
        candidate_count = len(candidates)

        if candidate_count > SECOND_ORDER_MAX_PER_EVENT:
            second_order: list[str] = []
            second_order_sources: dict[str, list[str]] = {}
            truncated = True
            truncated_reason = SECOND_ORDER_AMBIGUOUS_REASON
            dropped_count = candidate_count
        else:
            second_order = [t for t, _ in candidates]
            second_order_sources = {t: ids for t, ids in candidates}
            truncated = False
            truncated_reason = None
            dropped_count = 0

        proj = project_event_impact(
            ev, second_order_tickers=second_order,
            second_order_sources=second_order_sources,
        )
        proj["second_order_truncated"] = truncated
        proj["second_order_truncated_reason"] = truncated_reason
        proj["second_order_candidate_count"] = candidate_count
        proj["second_order_dropped_count"] = dropped_count
        if refused_themes:
            proj["second_order_theme_refused"] = refused_themes
            proj["second_order_theme_refused_reason"] = SECOND_ORDER_THEME_TOO_BROAD_REASON
        else:
            proj["second_order_theme_refused"] = []
            proj["second_order_theme_refused_reason"] = None
        projections.append(proj)
    return projections


def project_family_impact(events: list[dict]) -> dict[str, list[dict]]:
    """Group projected impact by event family (``source``) -- the "consequence
    surface per event family" the ledger row's acceptance test names. Grouping
    only; the underlying event identity, dedup and correction lineage remain
    entirely spine.py's -- this never mutates or re-derives an event id.
    """
    families: dict[str, list[dict]] = {}
    for proj in project_events_impact(events):
        families.setdefault(proj["source"] or "unknown", []).append(proj)
    return families


# Glance-tier outcome labels (ledger enums never reach the News panel).
# Shared wording with the Prophet closed-outcome map (T1_HIT / EXPIRED / …).
_PROPHET_OUTCOME_PLAIN: dict[str, tuple[str, str]] = {
    "T1_HIT": ("hit first target", "达到首个目标"),
    "T2_HIT": ("hit second target", "达到第二个目标"),
    "T3_HIT": ("hit final target", "达到最终目标"),
    "EXPIRED": ("timed out", "到期未达标"),
    "INVALIDATED": ("stopped out", "止损离场"),
}

_SIDE_PLAIN: dict[str, tuple[str, str]] = {
    "BULL": ("bullish plan", "偏多计划"),
    "BEAR": ("bearish plan", "偏空计划"),
}

# Common regime / risk-band tokens that otherwise leak English into ZH glance copy.
_STATE_TOKEN_ZH: dict[str, str] = {
    "stagflation": "滞胀",
    "reflation": "再通胀",
    "goldilocks": "金发女孩",
    "growth-scare": "增长担忧",
    "growth scare": "增长担忧",
    "calm": "平静",
    "watch": "关注",
    "caution": "警惕",
    "alarm": "警报",
}

_REGION_ZH: dict[str, str] = {
    "canada": "加拿大",
    "hk": "香港",
    "us": "美国",
    "china": "中国",
}


def _zh_state(token: str) -> str:
    key = (token or "").strip().lower()
    return _STATE_TOKEN_ZH.get(key, (token or "").strip())


def _zh_region(token: str) -> str:
    key = (token or "").strip().lower()
    return _REGION_ZH.get(key, (token or "").strip())


def _zh_detail(detail: str | None) -> str:
    """Translate common '+X% in Nd' ledger detail fragments for ZH glance."""
    if not detail:
        return ""
    m = re.match(r"^([+\-]?\d+(?:\.\d+)?%)\s+in\s+(\d+)d$", detail.strip(), re.IGNORECASE)
    if m:
        return f"（{m.group(2)}日内 {m.group(1)}）"
    return f"（{detail}）"

# Strip ledger quarter prefixes from regime state tokens for glance copy.
_QUARTER_PREFIX_RE = re.compile(r"^Q[1-4]\s+", re.IGNORECASE)
_ARROW = r"(?:→|->)"
_PROPHET_CLOSE_RE = re.compile(
    rf"^Prophet close:\s*([A-Z0-9.\-]+)\s+(BULL|BEAR)\s*{_ARROW}\s*([A-Z0-9_]+)"
    r"(?:\s*\(([^)]+)\))?\s*$",
    re.IGNORECASE,
)
_REGIME_FLIP_RE = re.compile(
    rf"^([A-Za-z][A-Za-z /-]*)\s+regime:\s*(.+?)\s*{_ARROW}\s*(.+?)\s*$",
    re.IGNORECASE,
)
_RISK_BAND_RE = re.compile(
    rf"^Risk radar:\s*(.+?)\s*{_ARROW}\s*(.+?)\s*$",
    re.IGNORECASE,
)

_EARNINGS_RE = re.compile(r"^Earnings:\s*(\S+)\s+actual vs est\s*$", re.IGNORECASE)
_EARNINGS_CALL_RE = re.compile(
    r"^Earnings call:\s*(\S+)\s+(Q\d\s+FY\d+)\s*\u2014\s*(.+?)\s*$", re.IGNORECASE
)
_MACRO_PRINT_RE = re.compile(
    r"^Macro print:\s*([A-Za-z0-9_.]+)\s*=\s*([+-]?[\d.]+)\s*\(([\d-]+)\)\s*$",
    re.IGNORECASE,
)
_EARNINGS_TONE_ZH = {
    "cautious": "谨慎", "mixed": "中性", "positive": "积极",
    "negative": "偏弱", "upbeat": "乐观", "bearish": "看空",
    "bullish": "看多", "weak": "疲软", "strong": "强劲",
    "neutral": "中性",
}
_ENUM_LEAK_RE = re.compile(r"\b(T[123]_HIT|INVALIDATED|EXPIRED|BULL|BEAR)\b")


def _sanitize(en: str, zh: str, *, fallback_en: str, fallback_zh: str) -> tuple[str, str]:
    """Single exit-point guard: no raw ledger enum reaches the glance surface,
    regardless of which family branch produced the strings (MAJOR 2)."""
    if _ENUM_LEAK_RE.search(en or "") or _ENUM_LEAK_RE.search(zh or ""):
        return fallback_en, fallback_zh
    return en, zh


def _strip_quarter_prefix(token: str) -> str:
    return _QUARTER_PREFIX_RE.sub("", (token or "").strip()) or (token or "").strip()


def plain_glance_titles(proj: dict) -> tuple[str, str]:
    """EN/ZH plain-word glance titles for the News consequence panel.

    Spine event titles are ledger-facing (``T1_HIT``, ``Prophet close:``,
    ``Q3 Stagflation``). Glance surfaces may not print those raw forms —
    front-end clarity law. Falls back to a family-level plain label when the
    title cannot be parsed; never invents a market signal.
    """
    raw = (proj.get("title") or "").strip()
    source = (proj.get("source") or "").strip()
    direct = [
        e["ticker"] for e in (proj.get("exposures") or [])
        if e.get("materiality") == MATERIALITY_DIRECT and e.get("ticker")
    ]

    fallback = ("Chronicle event", "大事记事件")

    m = _PROPHET_CLOSE_RE.match(raw)
    if m or source == "prophet_ledger":
        if m:
            ticker, side, outcome, detail = m.group(1), m.group(2).upper(), m.group(3).upper(), m.group(4)
        else:
            ticker = direct[0] if direct else ""
            side, outcome, detail = "", "", None
        side_en, side_zh = _SIDE_PLAIN.get(side, ("plan", "计划"))
        out_en, out_zh = _PROPHET_OUTCOME_PLAIN.get(
            outcome, ("closed", "已结")
        )
        who = ticker or "Named name"
        detail_en = f" ({detail})" if detail else ""
        detail_zh = _zh_detail(detail)
        en = f"{who} {side_en} closed · {out_en}{detail_en}"
        zh = f"{who} {side_zh}已结 · {out_zh}{detail_zh}"
        return _sanitize(en, zh, fallback_en=fallback[0], fallback_zh=fallback[1])

    m = _REGIME_FLIP_RE.match(raw)
    if m or source == "regime_flip":
        if m:
            region, frm, to = m.group(1).strip(), m.group(2), m.group(3)
        else:
            region, frm, to = "Market", "prior state", "new state"
        frm_p, to_p = _strip_quarter_prefix(frm), _strip_quarter_prefix(to)
        en = f"{region} regime shifted: {frm_p} → {to_p}"
        zh = f"{_zh_region(region)}体制切换：{_zh_state(frm_p)} → {_zh_state(to_p)}"
        return _sanitize(en, zh, fallback_en=fallback[0], fallback_zh=fallback[1])

    m = _RISK_BAND_RE.match(raw)
    if m or source == "risk_band":
        if m:
            frm, to = m.group(1).strip(), m.group(2).strip()
        else:
            frm, to = "prior", "new"
        en = f"Risk radar moved: {frm} → {to}"
        zh = f"风险雷达切换：{_zh_state(frm)} → {_zh_state(to)}"
        return _sanitize(en, zh, fallback_en=fallback[0], fallback_zh=fallback[1])

    if source == "macro_release":
        # BLOCKER 1(b): parse "Macro print: <series> = <value> (<date>)" into
        # a plain-word dual-locale sentence instead of gluing a ZH prefix
        # onto the untranslated stat slug (or doubling it in EN).
        mp = _MACRO_PRINT_RE.match(raw)
        if mp:
            series, value = mp.group(1), mp.group(2)
            series_label = series.replace("_", " ")
            en = f"{series_label} came in at {value}"
            zh = f"{series_label} 公布为 {value}"
        else:
            en, zh = "Macro data release", "宏观数据发布"
        return _sanitize(
            en, zh,
            fallback_en="Macro data release", fallback_zh="宏观数据发布",
        )

    if source == "earnings":
        # BLOCKER 1(a): never echo `raw` as title_zh — real corpus rows
        # always carry `raw`, so this branch used to render untranslated
        # English on the ZH glance panel for 5,548 of 11,025 events (98.8%
        # combined with earnings_call/research_vault).
        who = direct[0] if direct else "Named name"
        en = f"{who} reported earnings"
        zh = f"{who} 公布业绩"
        return _sanitize(
            en, zh,
            fallback_en="Earnings event", fallback_zh="业绩事件",
        )

    if source == "earnings_call":
        # BLOCKER 1(c): previously fell to the unknown-family fallback and
        # returned the raw "Earnings call: FINV Q2 FY2026 — mixed" string as
        # BOTH locales.
        mc = _EARNINGS_CALL_RE.match(raw)
        ticker = mc.group(1) if mc else (direct[0] if direct else "Named name")
        tone_raw = (mc.group(3) if mc else "").strip().lower()
        tone_en = tone_raw or "neutral"
        tone_zh = _EARNINGS_TONE_ZH.get(tone_raw, "中性")
        en = f"{ticker} earnings call — {tone_en} tone"
        zh = f"{ticker} 业绩电话会——基调{tone_zh}"
        return _sanitize(
            en, zh,
            fallback_en="Earnings call", fallback_zh="业绩电话会",
        )

    if source == "research_vault":
        # BLOCKER 1(c): previously fell to the unknown-family fallback and
        # returned the raw analyst-note headline (e.g. "S&T: GS Duttenhoefer
        # ...") as BOTH locales.
        who = direct[0] if direct else None
        if who:
            en, zh = f"Research note on {who}", f"关于 {who} 的研究纪要"
        else:
            en, zh = "Market research note", "市场研究纪要"
        return _sanitize(
            en, zh,
            fallback_en="Research note", fallback_zh="研究纪要",
        )

    # Unknown family: prefer a short non-slug fallback over leaking raw ledger text.
    if raw:
        return _sanitize(raw, raw, fallback_en=fallback[0], fallback_zh=fallback[1])
    return fallback


def glance_consequence_surface(
    events: list[dict],
    *,
    limit: int = GLANCE_EVENT_LIMIT,
) -> dict:
    """Bounded, plain-word consequence surface for the News Feed panel.

    Reads spine events (most-recent first), projects impact over that window
    only, and returns glance rows plus an explicit Market-Feed disposition:
    this surface is served on the existing News Feed page and is NOT a
    Market-Feed-branded product surface (MO-DELTA-001).

    Calibrated impact stays null + reason. Empty / missing input prints an
    honest null state rather than fabricating rows. Row titles are dual-locale
    plain-word (``title_en`` / ``title_zh``); the raw spine ``title`` is kept
    for diagnostics only and must not be rendered on the glance surface.
    """
    if not events:
        return {
            "served_as_market_feed": False,
            "market_feed_disposition": "explicitly_does_not_serve_market_feed",
            "stance_en": "Not available yet",
            "stance_zh": "暂不可用",
            "reason_en": "No chronicle events in this window yet.",
            "reason_zh": "此窗口尚无大事记事件。",
            "families": {},
            "rows": [],
            "event_count": 0,
        }

    # Most-recent window, then restore chronological order for projection
    # (point-in-time second-order needs on-or-before semantics inside the window).
    newest = sorted(
        events,
        key=lambda e: (e.get("date") or "", e.get("id") or ""),
        reverse=True,
    )[: max(1, int(limit))]
    window = sorted(
        newest,
        key=lambda e: (e.get("date") or "", e.get("id") or ""),
    )
    families = project_family_impact(window)
    # MAJOR 1: eligibility must be computed over the FULL corpus, not the
    # bounded glance window -- a 24-event window can never reach the
    # SECOND_ORDER_THEME_BROAD_MIN_COUNT (40) needed to refuse a
    # corpus-dominant theme like "earnings".
    eligible_themes = _eligible_themes(events)
    rows = []
    for proj in project_events_impact(window, eligible_themes=eligible_themes):
        direct = [e["ticker"] for e in proj["exposures"] if e.get("materiality") == MATERIALITY_DIRECT]
        second = [e["ticker"] for e in proj["exposures"] if e.get("materiality") == MATERIALITY_SECOND_ORDER]
        title_en, title_zh = plain_glance_titles(proj)
        rows.append({
            "event_id": proj["event_id"],
            "event_time": proj["event_time"],
            "known_at": proj["known_at"],
            "family": proj["source"] or "unknown",
            "title": proj.get("title") or "",  # raw spine title — diagnostics only
            "title_en": title_en,
            "title_zh": title_zh,
            "direct_tickers": direct,
            "second_order_tickers": second,
            "second_order_truncated": bool(proj.get("second_order_truncated")),
            "second_order_candidate_count": proj.get("second_order_candidate_count", 0),
            "second_order_dropped_count": proj.get("second_order_dropped_count", 0),
            "calibrated_impact": None,
            "calibrated_impact_reason": CALIBRATED_IMPACT_GATE_REASON,
            "causal_label": CAUSAL_LABEL,
        })
    # Glance order: newest first.
    rows.sort(key=lambda r: (r.get("event_time") or "", r.get("event_id") or ""), reverse=True)
    return {
        "served_as_market_feed": False,
        "market_feed_disposition": "explicitly_does_not_serve_market_feed",
        "stance_en": "Recent market events and the names they touch — watch, don\u2019t chase.",
        "stance_zh": "近期市场事件及其涉及的标的——观察为主，不必追高。",
        "reason_en": None,
        "reason_zh": None,
        "families": {k: len(v) for k, v in families.items()},
        "rows": rows,
        "event_count": len(window),
    }
