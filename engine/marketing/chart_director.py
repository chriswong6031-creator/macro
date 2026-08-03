"""engine.marketing.chart_director — THE chart-spec builder for post charts.

TrendSpider hardening PR-C (masterplan §3). Every chart-family lane calls this
module instead of assembling its own ``render_chart_v2`` kwargs. Before it,
nine call sites each carried their own literal block — daily, 90 bars,
``indicators=("volume","macd")``, no annotations — and the drift between them
was invisible because no two were ever read side by side. The renderer grew a
whole annotation grammar in PR-A that no call site could reach.

  INPUT   {ticker, angle, fact(s), timeframe hint}
  OUTPUT  a validated :class:`ChartSpec` whose ``kwargs`` splat straight into
          ``chart_render.render_chart_v2``

THE DOCTRINE TABLE (masterplan §3 PR-C.1). One claim kind, one chart:

  level touch / reclaim   that ONE moving average, a blue-grey disc per prior
                          touch, a gold disc on now, a level tag in the MA's
                          own colour. Daily.
  streak / superlative    the streak sub-pane (its y-unit IS the claim's unit)
                          or a weekly chart with the record bars boxed.
  analog                  weekly/monthly, log above four years, blue-grey discs
                          on each prior instance and gold on now.
  volume event            a real volume PANE plus the volume profile, with a
                          callout scoped to the window the fact measured.
  breakout / breakdown    trendline or zone band plus a measure box from the
                          break bar.
  stage read              WEEKLY, the 30-week average, a stage callout. The
                          CHART LABEL may say "Stage 2"; the COPY says "marking
                          up" (§0 gate 5 — show the indicator, don't say it).
  post-event drift        the average price paid since the event anchor plus a
                          measure box. We have this and the corpus does not.
  valuation observation   a zone band at the reference lows plus a callout.

WHAT THE DIRECTOR ENFORCES, in code, on every spec it returns:

  * **≤1 moving average.** The corpus draws one, labelled inline in its own
    colour, and never a legend box.
  * **≤2 sub-panes.** The renderer caps this too; the director caps it earlier
    so a spec that would have been silently truncated is instead never built.
  * **≤3 annotation FAMILIES.** Read the masterplan's "≤3 annotation objects"
    against its own doctrine table and the literal reading self-destructs: the
    level-touch row orders a disc per prior touch PLUS a gold disc PLUS a level
    tag, which is six objects for a five-touch name, and ref-27/ref-25 in the
    committed reference pack both draw five discs. What the corpus never does
    is mix more than a few KINDS of ink on one canvas. So the cap counts
    distinct families (spotlights / zones / trendlines / arcs / measure box) and
    the per-family object counts are bounded separately —
    :data:`MAX_SPOTLIGHTS` and friends. Level tags are excluded from the count
    on purpose: an axis tag is the in-frame RESTATEMENT device, not a mark on
    the canvas, and capping it would defeat §0 gate 5.
  * **The claim-window law (§0 gate 2).** A fact's full evidence window must lie
    inside the plotted axis. The director widens ``lookback_bars`` first, and
    if the widest permitted window still cannot cover the claim it REFUSES the
    fact and tries the next one. This is the inverse of the documented corpus
    failure — three of thirteen sampled charts assert "ever" on an axis that
    starts last year — and it is enforced here, not requested in a prompt.
  * **PIT discipline (§0 gate 3).** Facts come from the same split-adjusted
    daily parquet the chart plots; a short or null history yields no spec.
  * **Volume profile ON by default** for chart-family posts.
  * **The forming-bar law.** The chart PLOTS the live weekly/monthly bar
    (``resample_bars`` keeps it); every fact was computed on COMPLETED bars
    (``chart_facts.resample_completed`` drops it). The two series differ by one
    bar, so fact anchors are mapped to chart bars BY DATE — never by index —
    in :func:`_index_of_date`.

A7 / display tier: nothing here originates a signal, a score or a ranking. It
selects a pre-computed deterministic fact and decides how to DRAW it.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union

log = logging.getLogger(__name__)

PathLike = Union[str, Path]

# ─────────────────────────────────────────────────────────────────────────────
# Grammar budgets
# ─────────────────────────────────────────────────────────────────────────────

#: The corpus draws ONE moving average, ever (§1.1, "What they NEVER draw").
MAX_MAS = 1

#: Sub-pane cap. Mirrors ``chart_render._MAX_SUBPANES`` deliberately: the
#: renderer's cap is the last line, this one is the design rule.
MAX_SUBPANES = 2

#: Distinct annotation FAMILIES on one canvas — see the module docstring for
#: why this counts families rather than objects.
MAX_ANNOTATION_FAMILIES = 3

#: Per-family object budgets. Five discs is the corpus maximum (ref-25/ref-27).
MAX_SPOTLIGHTS = 6
MAX_ZONES = 2
MAX_TRENDLINES = 2
MAX_LEVEL_TAGS = 2

#: Widest axis the director will open to satisfy a claim window, per timeframe.
#: Past these the chart stops being legible: 3,000 daily candles in 1,000px is
#: a smear, and a claim that needs one has been mis-scoped by the fact layer.
MAX_LOOKBACK: dict[str, int] = {"DAILY": 504, "WEEKLY": 520, "MONTHLY": 360}

#: Below this the axis is not worth drawing at all.
MIN_LOOKBACK: dict[str, int] = {"DAILY": 60, "WEEKLY": 60, "MONTHLY": 48}

#: Span past which a multi-year chart goes log (masterplan §3: "log if >4y").
_LOG_SCALE_BARS: dict[str, int] = {"DAILY": 1008, "WEEKLY": 208, "MONTHLY": 48}

#: Future runway — the corpus puts the last bar at 60-85% of frame width and
#: keeps the dead space for the volume profile and the tags (§1.1).
RUNWAY_FRAC = 0.18

#: Card geometry, unchanged from the lanes this replaces.
_CARD_W, _CARD_H = 1000, 880
_SUBPANEL_H = 190

#: Timeframe defaults when no fact and no hint name one.
_DEFAULT_LOOKBACK: dict[str, int] = {"DAILY": 90, "WEEKLY": 156, "MONTHLY": 120}

#: Angle → claim kinds it prefers, most-preferred first. An angle that names no
#: preference takes the salience order as it comes.
_ANGLE_CLAIMS: dict[str, tuple[str, ...]] = {
    "level_watch": ("level_touch", "breakout", "analog", "superlative"),
    "precedent": ("analog", "superlative", "streak", "level_touch"),
    "long_term_structure": ("analog", "superlative", "level_touch", "stage_read"),
    "stage_read": ("stage_read", "analog", "level_touch"),
    "risk_frame": ("streak", "level_touch", "volume_event"),
    "group_read": ("volume_event", "level_touch", "streak"),
    "receipt_frame": ("post_event_drift", "level_touch"),
    "process": ("level_touch", "analog"),
}

#: Claim kinds the director knows how to DRAW. A fact of any other kind is
#: context for the writer, never the subject of a chart.
_BUILDABLE: frozenset[str] = frozenset({
    "level_touch", "streak", "superlative", "analog", "volume_event",
    "breakout", "stage_read", "post_event_drift", "valuation",
})

#: Claim kinds whose truth depends on a window WIDER than the bars they point
#: at, so an absent ``window_start`` is fatal rather than merely unhelpful.
_WINDOW_CRITICAL: frozenset[str] = frozenset({
    "superlative", "analog", "level_touch", "volume_event",
})

#: Bars a prior instance must sit BEHIND the last bar to count as a precedent
#: rather than as part of the current event.
_ANALOG_MIN_GAP_BARS = 8

#: The average a tape card draws when no fact selected one. ONE, inline
#: labelled — the legacy pair the lanes used to draw is two, which the grammar
#: forbids on a posted chart (§1.1, "Max ONE moving average").
_TAPE_MA = {"kind": "sma", "length": 50, "color": "#F59E0B"}

#: The moving-average ink. Matches ``chart_render._MA_COLORS[0]`` so the level
#: tag and the curve are the same colour without the renderer having to guess —
#: which is the whole point of the second axis tag (§3 PR-A.7).
MA_INK = "#F59E0B"

#: Numbers a caption may carry without the chart restating them. Mirrors the
#: existing copy validator's exemption for bare 1-2 digit integers ("3 weeks",
#: "T1"): those are counts the sentence itself explains, not levels a reader
#: would go and check. Everything with a decimal point, a percent sign, an "x"
#: or three-plus digits is a LEVEL, and a level in the caption must be on the
#: picture (§0 gate 5, in-frame restatement).
_CAPTION_NUMBER_RE = re.compile(
    r"""
    [+-]?\d+\.?\d*%            # percentage
    | \d+\.?\d*x               # multiplier
    | \b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b   # grouped price: 1,147.32
    | \b\d+\.\d+\b             # decimal price
    | \b\d{3,}\b               # bare integer of 3+ digits
    """,
    re.VERBOSE,
)


# ─────────────────────────────────────────────────────────────────────────────
# The spec
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ChartSpec:
    """A validated render request plus everything downstream needs to audit it.

    ``kwargs`` is complete: ``render_chart_v2(**spec.kwargs)`` renders the card.
    Everything else is the receipt — which fact the chart is about, what window
    it plots, which number it restates in frame, and what got refused on the way.
    """

    ticker: str
    claim_kind: str
    fact_id: str
    timeframe: str
    kwargs: dict[str, Any]
    axis_start: str = ""
    axis_end: str = ""
    fact_window_start: str = ""
    drawn_level: float | None = None
    level_kind: str = ""
    in_frame_numbers: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_meta(self) -> dict:
        """The audit slice for the plan artifact (no bar arrays, no SVG)."""
        return {
            "ticker": self.ticker,
            "claim_kind": self.claim_kind,
            "fact_id": self.fact_id,
            "timeframe": self.timeframe,
            "axis_start": self.axis_start,
            "axis_end": self.axis_end,
            "fact_window_start": self.fact_window_start,
            "drawn_level": self.drawn_level,
            "level_kind": self.level_kind,
            "in_frame_numbers": list(self.in_frame_numbers),
            "rejected": list(self.rejected),
            "notes": list(self.notes),
            "lookback_bars": self.kwargs.get("_lookback_bars"),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────────────

def _index_of_date(dates: list[str], iso: str) -> int | None:
    """Index of *iso* in *dates*, or the nearest EARLIER bar. None if before all.

    DATES, NOT INDICES, is the whole contract between the fact layer and this
    one. The fact series drops the forming bucket and the chart series keeps
    it, so the two are off by one at the right-hand end; on a weekly chart a
    fact index reused as a chart index puts every disc one bar early. Matching
    by date is immune to that, and to any future change in either window.
    """
    key = str(iso or "")[:10]
    if not key or not dates:
        return None
    best: int | None = None
    for i, d in enumerate(dates):
        if str(d)[:10] <= key:
            best = i
        else:
            break
    return best


def _fmt_price(v: float) -> str:
    """Two-decimal price, matching chart_facts and the renderer's axis tags."""
    return f"{float(v):.2f}"


def _numeric_tokens(text: str) -> list[str]:
    """Level-shaped numbers inside a string (see :data:`_CAPTION_NUMBER_RE`)."""
    return [m.group(0) for m in _CAPTION_NUMBER_RE.finditer(str(text or ""))]


def claims_for_angle(angle: str) -> tuple[str, ...]:
    """Claim kinds this angle prefers, most-preferred first ( () when none)."""
    return _ANGLE_CLAIMS.get(str(angle or "").strip().lower(), ())


def select_fact(facts: list[dict] | None, *, angle: str = "") -> list[dict]:
    """Buildable facts, ordered by the angle's preference then by salience.

    Returns a LIST, not a winner: the claim-window law can refuse the top fact,
    and the caller has to be able to fall through to the next one rather than
    give up on the chart entirely.
    """
    rows = [f for f in (facts or [])
            if isinstance(f, dict) and str(f.get("claim_kind") or "") in _BUILDABLE]
    prefs = claims_for_angle(angle)

    def _key(f: dict) -> tuple[int, int, str]:
        kind = str(f.get("claim_kind") or "")
        rank = prefs.index(kind) if kind in prefs else len(prefs) + 1
        return (rank, -int(f.get("salience", 0)), str(f.get("id") or ""))

    return sorted(rows, key=_key)


# ─────────────────────────────────────────────────────────────────────────────
# The claim-window law (§0 gate 2)
# ─────────────────────────────────────────────────────────────────────────────

def required_bars(fact: dict, timeframe: str) -> int:
    """How many bars of *timeframe* the fact's evidence window spans.

    ``window_bars`` is authoritative when the fact and the chart share a
    timeframe. When they do not (a weekly fact drawn on a daily axis, which the
    director avoids but a caller may force), the count is converted at the
    renderer's own daily-per-bar ratio so the comparison stays in one unit.
    """
    from engine.marketing.chart_render import _TIMEFRAME_DAILY_PER_BAR

    bars = int(fact.get("window_bars") or 0)
    if bars <= 0:
        return 0
    ftf = str(fact.get("timeframe") or timeframe).upper()
    if ftf == timeframe:
        return bars
    per_f = _TIMEFRAME_DAILY_PER_BAR.get(ftf, 1)
    per_c = _TIMEFRAME_DAILY_PER_BAR.get(timeframe, 1)
    return max(1, int(round(bars * per_f / per_c)))


def claim_window_violation(
    fact: dict,
    plotted_dates: list[str],
    *,
    timeframe: str,
) -> str:
    """"" when the fact's evidence window fits the plotted axis, else the reason.

    THE LAW, stated once. A superlative, an analog count or a touch count is a
    claim ABOUT A STRETCH OF TAPE. If the picture does not show that stretch,
    the reader is being asked to take the window on faith — and three of the
    thirteen charts sampled in the corpus study do exactly that ("since 2015"
    over an axis that starts in 2025). Two ways a fact can fail:

    1. Its ``window_start`` is older than the first DRAWN bar.
    2. It has no ``window_start`` at all AND its claim kind is one whose truth
       depends on a window (a stage read has no dated evidence bar, so it is
       judged on ``window_bars`` instead). Absent metadata is refused, never
       waved through — "we don't know the window" is not "the window is fine".
    """
    if not plotted_dates:
        return "no plotted bars"
    kind = str(fact.get("claim_kind") or "")
    axis_start = str(plotted_dates[0])[:10]
    ws = str(fact.get("window_start") or "")[:10]

    if ws:
        if ws < axis_start:
            return (f"claim window starts {ws}, plotted axis starts {axis_start} "
                    f"({kind})")
        return ""

    need = required_bars(fact, timeframe)
    if need and len(plotted_dates) < need:
        return (f"claim needs {need} {timeframe.lower()} bars, axis draws "
                f"{len(plotted_dates)} ({kind})")
    if not need and kind in _WINDOW_CRITICAL:
        return f"fact carries no window_start and no window_bars ({kind})"
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Grammar enforcement
# ─────────────────────────────────────────────────────────────────────────────

def enforce_grammar(kwargs: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Apply the house caps to a kwargs dict. Returns (kwargs, notes).

    Mutating rather than raising is deliberate: a chart that draws one average
    instead of two is still a good chart, and a nightly that dies because a
    fact offered a second one is not. Every trim is NAMED in the notes so the
    plan artifact records what the director took away.
    """
    notes: list[str] = []

    mas = list(kwargs.get("mas") or [])
    if len(mas) > MAX_MAS:
        notes.append(f"trimmed {len(mas)} MAs to {MAX_MAS}")
        kwargs["mas"] = mas[:MAX_MAS]

    from engine.marketing.chart_render import _SUBPANE_KINDS

    inds = tuple(kwargs.get("indicators") or ())
    panes = [i for i in inds if i in _SUBPANE_KINDS]
    # volume drawn INSIDE the price pane claims no sub-pane of its own.
    if kwargs.get("volume_overlay") and "volume" in panes:
        panes = [p for p in panes if p != "volume"]
    if len(panes) > MAX_SUBPANES:
        keep = set(panes[:MAX_SUBPANES])
        notes.append(f"trimmed sub-panes to {MAX_SUBPANES}")
        kwargs["indicators"] = tuple(
            i for i in inds if i not in _SUBPANE_KINDS or i in keep
            or (i == "volume" and kwargs.get("volume_overlay")))

    for key, cap in (("spotlights", MAX_SPOTLIGHTS), ("zones", MAX_ZONES),
                     ("trendlines", MAX_TRENDLINES), ("level_tags", MAX_LEVEL_TAGS)):
        items = list(kwargs.get(key) or [])
        if len(items) > cap:
            notes.append(f"trimmed {key} {len(items)}→{cap}")
            # Keep the OLDEST instances and the newest one: the story is "this
            # happened before, and it is happening now". Dropping the gold
            # "now" disc to fit a budget would delete the point of the chart.
            kwargs[key] = (items[: cap - 1] + items[-1:]) if cap > 1 else items[-1:]

    families = [k for k in ("spotlights", "zones", "trendlines", "arcs")
                if kwargs.get(k)]
    if kwargs.get("measure_box"):
        families.append("measure_box")
    if len(families) > MAX_ANNOTATION_FAMILIES:
        # Drop from the BACK of the doctrine order — the earlier a family
        # appears here, the more load it carries in the corpus grammar.
        order = ["spotlights", "zones", "measure_box", "trendlines", "arcs"]
        ranked = sorted(families, key=lambda f: order.index(f) if f in order else 99)
        for extra in ranked[MAX_ANNOTATION_FAMILIES:]:
            notes.append(f"dropped annotation family {extra} (cap "
                         f"{MAX_ANNOTATION_FAMILIES})")
            kwargs[extra] = None
    return kwargs, notes


# ─────────────────────────────────────────────────────────────────────────────
# In-frame restatement (§0 gate 5)
# ─────────────────────────────────────────────────────────────────────────────

def caption_number_violations(text: str, in_frame: list[str] | None) -> list[str]:
    """Numbers the caption claims that the CHART does not restate. [] = clean.

    §0 gate 5: "a number may appear in the caption only if the chart restates it
    in-frame (axis tag, measurement box, or callout)". A screenshot outlives its
    thread; a caption whose number exists nowhere on the picture becomes an
    unsourced claim the moment it is re-shared, which is precisely the corpus
    failure the reference pack documents.

    This is a VALIDATION-SIDE check, not prompt hope. The director already puts
    every level it draws into ``in_frame_numbers``, so a compliant post passes
    by construction; a post that reaches for a number the chart never drew is
    refused. Bare 1-2 digit integers are exempt, matching the copy validator's
    existing exemption — "four red weeks" is a count the sentence explains, not
    a level a reader would go and check.
    """
    allowed = {str(x).strip() for x in (in_frame or []) if str(x).strip()}
    # A level may be written with or without thousands separators, and a
    # percent may be signed in the caption and unsigned on the chart. Normalise
    # both sides rather than demanding a byte match the writer cannot see.
    def _norm(tok: str) -> str:
        return str(tok).replace(",", "").lstrip("+").rstrip("%").rstrip("x")

    allowed_norm = {_norm(a) for a in allowed}
    out: list[str] = []
    for tok in _numeric_tokens(text):
        if _norm(tok) in allowed_norm:
            continue
        out.append(f"caption number {tok} is not restated on the chart")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# The builder
# ─────────────────────────────────────────────────────────────────────────────

def _annotations_for(
    fact: dict,
    dates: list[str],
    o: list[float],
    h: list[float],
    l: list[float],
    c: list[float],
    warmup: int,
    timeframe: str,
) -> dict[str, Any]:
    """The doctrine table, as data. Returns a partial kwargs dict.

    Every branch obeys the same three rules: point at bars BY DATE, restate the
    level the fact cites via ``level_tags``, and keep the label to the corpus's
    2-6 words.
    """
    kind = str(fact.get("claim_kind") or "")
    n = len(c)
    last = n - 1
    anchors = [str(d)[:10] for d in (fact.get("anchor_dates") or [])]
    idxs = [i for i in (_index_of_date(dates, a) for a in anchors)
            if i is not None and i >= warmup]
    # Dedupe while keeping order — two fact anchors inside one chart bucket are
    # one disc on a weekly chart.
    seen: set[int] = set()
    idxs = [i for i in idxs if not (i in seen or seen.add(i))]
    level = fact.get("level")
    callout = str(fact.get("callout") or "")
    out: dict[str, Any] = {}

    def _tag(price: object, colour: str = MA_INK) -> None:
        try:
            p = float(price)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return
        if p > 0:
            out.setdefault("level_tags", []).append({"price": p, "color": colour})

    if kind in ("level_touch", "stage_read"):
        ma = dict(fact.get("ma") or {})
        if ma.get("length"):
            out["mas"] = [{"kind": str(ma.get("kind") or "sma"),
                           "length": int(ma["length"]), "color": MA_INK}]
        spots = [{"index": i, "tense": "past"} for i in idxs[:-1]]
        now_idx = idxs[-1] if idxs else last
        spots.append({"index": now_idx, "tense": "now",
                      "label": callout or None})
        out["spotlights"] = [{k: v for k, v in s.items() if v is not None}
                             for s in spots]
        _tag(level)

    elif kind in ("streak", "superlative") and fact.get("streak_len"):
        run = int(fact["streak_len"])
        start = max(warmup, last - run + 1)
        # The record bars, BOXED (ref-10): a zone spanning the streak's own
        # price range over exactly its own bars, so the count is countable.
        lo = min(l[start:last + 1]) if last >= start else l[last]
        hi = max(h[start:last + 1]) if last >= start else h[last]
        out["zones"] = [{"lo": lo, "hi": hi, "start_index": start,
                         "end_index": last, "label": callout or None}]
        out["zones"] = [{k: v for k, v in z.items() if v is not None}
                        for z in out["zones"]]
        # The indicator whose y-axis unit IS the claim's unit (§1.1). A streak
        # claim gets a consecutive-candles pane and nothing else — an
        # oscillator here would be decoration, which the doctrine forbids.
        out["_want_pane"] = "streak"
        # ref-10 keeps ONE average behind the boxed streak for context.
        out["mas"] = [{"kind": "sma", "length": 50, "color": MA_INK}]
        # NO level tag: the streak's number lives in the boxed zone's label and
        # in the pane's own y-axis, and the last-price pill already prints the
        # close. A second tag at the same price is the duplicate the first
        # proof render showed (two "90.20" chips stacked).

    elif kind == "superlative":
        spots = [{"index": i, "tense": "past"} for i in idxs[:-1]]
        spots.append({"index": idxs[-1] if idxs else last,
                      "tense": "now", "label": callout or None})
        out["spotlights"] = [{k: v for k, v in s.items() if v is not None}
                             for s in spots]
        out["_want_pane"] = "volume_pane"
        out["mas"] = []
        _tag(level if level else c[last])

    elif kind == "analog":
        # PRIOR instances only. A "we have been here before" chart whose
        # blue-grey disc sits on the bar next to the gold one is not showing a
        # precedent, it is showing the same event twice — and on a multi-year
        # axis the two discs literally overlap (measured on the 2026-08 AMZN
        # monthly proof). An instance has to be far enough back to READ as
        # history at the chart's own scale.
        recent_cut = last - _ANALOG_MIN_GAP_BARS
        past = [i for i in idxs[:-1] if i <= recent_cut]
        spots = [{"index": i, "tense": "past"} for i in past]
        spots.append({"index": last, "tense": "now",
                      "label": callout or "You are here"})
        out["spotlights"] = spots
        # The editorial multi-year chart (ref-13) draws NO average: the claim
        # is about a level, and a 50-period curve on a 12-year axis is noise.
        out["mas"] = []
        out["_want_pane"] = "volume_pane"
        _tag(level)

    elif kind == "volume_event":
        idx = idxs[-1] if idxs else last
        out["spotlights"] = [{"index": idx, "tense": "now",
                              "label": callout or "Heaviest volume"}]
        out["_want_pane"] = "volume_pane"
        out["mas"] = []
        _tag(c[last])

    elif kind == "breakout":
        frm = idxs[0] if idxs else max(warmup, last - 20)
        out["measure_box"] = {"from_index": frm, "to_index": last}
        if level:
            _tag(level)

    elif kind == "post_event_drift":
        frm = idxs[0] if idxs else max(warmup, last - 20)
        out["measure_box"] = {"from_index": frm, "to_index": last}
        out["_want_avwap"] = True

    elif kind == "valuation":
        if level:
            try:
                lv = float(level)
                band = max(lv * 0.02, 0.01)
                out["zones"] = [{"lo": lv - band, "hi": lv + band,
                                 "label": callout or None}]
                out["zones"] = [{k: v for k, v in z.items() if v is not None}
                                for z in out["zones"]]
                _tag(lv)
            except (TypeError, ValueError):
                pass

    return out


def build_spec(
    ticker: str,
    *,
    root: PathLike,
    facts: list[dict] | None = None,
    angle: str = "",
    timeframe_hint: str | None = None,
    variant: str = "tape",
    marker_date: str | None = None,
    lookback_bars: int | None = None,
    cta: bool = True,
    volume_profile: bool = True,
    logo_root: PathLike | None = None,
) -> ChartSpec | None:
    """Build the chart spec for one post. ``None`` when no chart is possible.

    *variant* keeps each lane's existing marker semantics untouched: only
    ``"signal"`` — an un-demoted, live-verified entry claim — draws the entry
    marker, the highlight disc and the SETUP pill. Everything else is TAPE: an
    honest chart with no claim attached. Filing/house-pick lanes pass
    ``variant="tape"`` and get exactly the card they got before, now with the
    annotation grammar available to them.

    *marker_date* is a DATE, not an index, for the same reason fact anchors are:
    the director chooses its own window and timeframe, so an index computed
    against some other caller's 90-bar daily load would point at an unrelated
    bar here. An out-of-window marker date resolves to no marker rather than to
    a clamped one — a SETUP pill on the wrong candle is worse than none.

    The fact walk is a LADDER, not a lookup: the highest-salience fact the angle
    prefers is tried first, and a fact refused by the claim-window law falls
    through to the next one. Only when every fact is refused does the director
    fall back to an un-annotated tape card — which is still a chart, and still
    better than the post shipping bare (the ticker-post-carries-a-chart law).
    """
    from engine.marketing.chart_render import (
        build_m2_overlays,
        load_ohlcv_timeframe,
        normalize_timeframe,
    )

    tkr = str(ticker or "").upper()
    if not tkr:
        return None
    root_s = str(root)
    logo_s = str(logo_root if logo_root is not None else root)

    ordered = select_fact(facts, angle=angle)
    rejected: list[str] = []

    # Candidate list: every buildable fact, then a bare tape card as the floor.
    for fact in ordered + [None]:
        tf = normalize_timeframe(
            (fact or {}).get("timeframe") if fact else (timeframe_hint or "DAILY"))
        if fact is None:
            tf = normalize_timeframe(timeframe_hint or "DAILY")
        vis = int(lookback_bars) if lookback_bars else _DEFAULT_LOOKBACK[tf]
        vis = max(MIN_LOOKBACK[tf], min(MAX_LOOKBACK[tf], vis))

        # ── the claim-window law: widen, then refuse ─────────────────────────
        if fact is not None:
            need = required_bars(fact, tf)
            if need > vis:
                if need > MAX_LOOKBACK[tf]:
                    rejected.append(
                        f"{fact.get('id')}: needs {need} {tf.lower()} bars, "
                        f"cap is {MAX_LOOKBACK[tf]}")
                    continue
                # +10% headroom so the oldest evidence bar is not welded to the
                # left edge where a disc would be half off-canvas.
                vis = min(MAX_LOOKBACK[tf], int(need * 1.1) + 2)

        loaded = load_ohlcv_timeframe(tkr, root_s, timeframe=tf, lookback_bars=vis)
        if not loaded:
            # PIT law: no bars, no chart, no snapshot fallback.
            if fact is not None:
                rejected.append(f"{fact.get('id')}: no {tf.lower()} bars for {tkr}")
                continue
            return None
        (dates, o, h, l, c, v), warmup = loaded
        if len(c) - warmup < MIN_LOOKBACK[tf] // 2:
            if fact is not None:
                rejected.append(f"{fact.get('id')}: only {len(c) - warmup} drawn bars")
                continue
            return None
        plotted = [str(d)[:10] for d in dates[warmup:]]

        if fact is not None:
            why = claim_window_violation(fact, plotted, timeframe=tf)
            if why:
                # ONE retry at the widest permitted axis before refusing: a
                # window_start a few bars off the edge is a scoping problem, not
                # a false claim, and widening is the masterplan's first remedy.
                wide = MAX_LOOKBACK[tf]
                if vis < wide:
                    loaded2 = load_ohlcv_timeframe(tkr, root_s, timeframe=tf,
                                                   lookback_bars=wide)
                    if loaded2:
                        (dates, o, h, l, c, v), warmup = loaded2
                        plotted = [str(d)[:10] for d in dates[warmup:]]
                        vis = wide
                        why = claim_window_violation(fact, plotted, timeframe=tf)
                if why:
                    rejected.append(f"{fact.get('id')}: {why}")
                    continue

        # ── the doctrine table ───────────────────────────────────────────────
        ann = _annotations_for(fact, dates, o, h, l, c, warmup, tf) if fact else {}
        want_pane = ann.pop("_want_pane", None)
        want_avwap = ann.pop("_want_avwap", False)

        # Sub-panes. Volume rides INSIDE the price pane by default (paneless,
        # the way every lane this replaces already draws it) so the one sub-pane
        # budget goes to the indicator whose y-unit is the claim's unit.
        volume_overlay = True
        indicators: tuple[str, ...] = ("volume", "macd")
        if want_pane == "streak":
            indicators = ("volume", "streak")
        elif want_pane == "volume_pane":
            # A volume EVENT gets a real volume pane — the claim is about the
            # bars in it, and a wash behind the candles cannot carry a record.
            # The multi-year editorial charts (analog/superlative) take the same
            # layout: candles, volume, annotations, nothing else (ref-13).
            volume_overlay = False
            indicators = ("volume",)

        # ONE average, or none, decided by the doctrine row — never the
        # renderer's legacy 50/200 PAIR, which is two averages on a chart the
        # grammar allows one on. ``mas=[]`` is how the renderer is told "no
        # average"; ``mas=None`` is how it is told "use the legacy pair", and
        # the director never says that.
        mas_spec = ann.pop("mas", None)
        if mas_spec is None:
            mas_spec = [dict(_TAPE_MA)] if fact is None else []

        span = len(c) - warmup
        log_scale = span >= _LOG_SCALE_BARS[tf]

        # The entry marker, resolved in THIS window's bars. A tape card never
        # carries one; a signal card with an unresolvable date falls back to the
        # last bar, which is the same "latest" fallback the lanes already use.
        marker_idx: int | None = None
        if variant == "signal":
            marker_idx = _index_of_date(dates, marker_date) if marker_date else None
            if marker_idx is None or marker_idx < warmup:
                marker_idx = len(c) - 1

        m2: dict = {}
        if volume_profile or want_avwap:
            try:
                m2 = build_m2_overlays(tkr, dates, o, h, l, c, v, root_s) or {}
            except Exception:  # noqa: BLE001
                m2 = {}

        kwargs: dict[str, Any] = {
            "ticker": tkr,
            "dates": list(dates),
            "o": list(o), "h": list(h), "l": list(l), "c": list(c),
            "volume": list(v),
            "timeframe": tf,
            "marker_index": marker_idx,
            "highlight_index": marker_idx,
            "pct_from_index": (
                marker_idx
                if (marker_idx is not None and (len(c) - 1 - marker_idx) >= 5)
                else None
            ),
            "show_indicators": True,
            "indicators": indicators,
            "mas": mas_spec,
            "warmup": warmup,
            "volume_overlay": volume_overlay,
            "subpanel_h": _SUBPANEL_H,
            "height": _CARD_H,
            "width": _CARD_W,
            "company_name": tkr,
            "logo_root": logo_s,
            "log_scale": log_scale,
            "runway_frac": RUNWAY_FRAC,
            "cta": cta,
            # VOLUME PROFILE ON BY DEFAULT for chart-family posts (§3 PR-C.1).
            "poc_overlay": m2.get("poc_overlay") if volume_profile else None,
            "avwap_overlay": m2.get("avwap_overlay") if want_avwap else None,
        }
        kwargs.update({k: val for k, val in ann.items() if val})
        kwargs, notes = enforce_grammar(kwargs)

        # ── in-frame restatement inventory ───────────────────────────────────
        in_frame: list[str] = [_fmt_price(c[-1])]  # the last-price pill, always
        for tag in (kwargs.get("level_tags") or []):
            in_frame.append(_fmt_price(tag["price"]))
        for group in ("spotlights", "zones"):
            for item in (kwargs.get(group) or []):
                in_frame.extend(_numeric_tokens(item.get("label") or ""))
        if kwargs.get("measure_box"):
            mb = kwargs["measure_box"]
            try:
                p0, p1 = float(c[mb["from_index"]]), float(c[mb["to_index"]])
                in_frame.append(_fmt_price(p1 - p0))
                in_frame.append(f"{(p1 - p0) / p0 * 100:.2f}" if p0 else "")
            except Exception:  # noqa: BLE001
                pass
        # The fact's own numbers are on the picture whenever the fact IS the
        # chart: the level is tagged, the callout carries the count, the span
        # is the axis. Whitelisting them here is what makes a compliant caption
        # pass the gate by construction rather than by luck.
        if fact is not None:
            in_frame.extend(str(x) for x in (fact.get("numbers") or []))
        in_frame = [x for x in dict.fromkeys(in_frame) if x]

        kwargs["_lookback_bars"] = vis
        return ChartSpec(
            ticker=tkr,
            claim_kind=str((fact or {}).get("claim_kind") or "tape"),
            fact_id=str((fact or {}).get("id") or ""),
            timeframe=tf,
            kwargs=kwargs,
            axis_start=plotted[0] if plotted else "",
            axis_end=plotted[-1] if plotted else "",
            fact_window_start=str((fact or {}).get("window_start") or "")[:10],
            drawn_level=(float(kwargs["level_tags"][0]["price"])
                         if kwargs.get("level_tags") else None),
            level_kind=str((fact or {}).get("claim_kind") or ""),
            in_frame_numbers=in_frame,
            rejected=rejected,
            notes=notes,
        )
    return None


def render(spec: ChartSpec) -> str | None:
    """Render a spec. Returns the SVG, or None on any failure (fail-soft)."""
    from engine.marketing.chart_render import render_chart_v2

    try:
        kwargs = {k: v for k, v in spec.kwargs.items() if not k.startswith("_")}
        return render_chart_v2(**kwargs)
    except Exception as exc:  # noqa: BLE001
        log.debug("chart_director.render(%s) failed: %s", spec.ticker, exc)
        return None


#: Daily bars ``build_facts`` loads, per requested horizon.
#:
#: THE LOAD DEPTH IS THE CLAIM CEILING, which is the point. A weekly fact
#: measured over 1,300 daily bars says "its 5-year high" and the director opens
#: a 5-year axis to carry it; the same fact measured over the full store says
#: "12-year high" and needs a 12-year axis, which past ~520 weekly bars the
#: director refuses as illegible. Loading exactly as deep as the chart can
#: honestly show is therefore not a shortcut — it is the claim-window law
#: applied one layer earlier, where it costs a parquet read instead of a
#: rejected fact. MONTHLY is the editorial horizon (ref-13 is a 29-year chart)
#: and gets the whole store.
_FACT_DAILY_BARS: dict[str, int] = {"DAILY": 400, "WEEKLY": 1300, "MONTHLY": 7000}


def build_facts(
    ticker: str,
    *,
    root: PathLike,
    timeframe_hint: str | None = None,
    as_of: object = None,
    daily_bars: int | None = None,
) -> dict:
    """The fact packet the director expects, assembled from ONE daily load.

    ONE LOAD, THREE VIEWS. The daily series feeds the daily level facts and the
    weekly/monthly resamples, so every fact in a post is measured against the
    same split-adjusted bars the chart plots (§0 gate 3). Stage and attention
    facts come from the PR-B pools and are simply ABSENT when those pools are
    empty — the stage backfill is a weekly artifact and legitimately fails its
    own freshness gate most days, which must degrade to no stage fact, never to
    a fabricated one.
    """
    from engine.marketing import chart_facts as CF
    from engine.marketing.chart_render import load_ohlcv, normalize_timeframe

    tkr = str(ticker or "").upper()
    if not tkr:
        return {"facts": [], "numbers_whitelist": []}
    tf = normalize_timeframe(timeframe_hint or "WEEKLY")
    tf = "MONTHLY" if tf == "MONTHLY" else "WEEKLY"
    depth = int(daily_bars) if daily_bars else _FACT_DAILY_BARS[tf]

    packets: list[dict] = []
    bars = load_ohlcv(tkr, str(root), n=depth)
    if bars and bars[0]:
        d, o, h, l, c, v = bars
        packets.append(CF.compute_daily_level_facts(tkr, d, o, h, l, c, v))
        packets.append(CF.compute_timeframe_facts(tkr, d, o, h, l, c, v, timeframe=tf))
    packets.append(CF.compute_stage_facts(tkr, root, as_of=as_of))
    packets.append(CF.compute_attention_facts(tkr, root, as_of=as_of))
    return CF.merge_packets(*packets)
