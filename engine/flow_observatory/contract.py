"""engine.flow_observatory.contract — the ``flow_observatory.v2`` schema (W1).

Pure assembly and validation, no I/O (masterplan §4 module-layout freeze): every function
here takes plain dicts/lists in and returns plain dicts/lists out. ``scripts/build_flow_velocity``
is the only caller that touches disk; tests call these functions directly on fixtures.

The whole point of this module is the honesty gate the program exists to enforce: absolute
flow (did money actually move) and relative pressure (is that fast or slow FOR this series)
are separate fields, separate labels, and — via :func:`quadrant` — a separate four-way read
that can say "still selling, but the pressure is easing" instead of collapsing that into a
single inflow-colored number (the live-page defect this program was commissioned to kill).
"""
from __future__ import annotations

import re
from typing import Any

from engine.flow_observatory import history
from engine.flow_observatory import quality as fo_quality

SCHEMA = "flow_observatory.v2"
AUTHORITY = "context_only"

# ── quadrant enum — masterplan §6 table, EXACT strings (language law) ─────────────────
QUADRANT_LABELS: dict[str, tuple[str, str]] = {
    "true_accumulation": ("real inflow, above norm", "真实流入·高于常态"),
    "improving_but_still_selling": ("still selling, pressure easing", "仍净流出·压力改善"),
    "weakening_but_still_buying": ("still buying, pace fading", "仍净流入·动能转弱"),
    "true_distribution": ("real outflow, below norm", "真实流出·低于常态"),
    "neutral_or_unknown": ("quiet / insufficient data", "平静 / 数据不足"),
}
NEUTRAL_OR_UNKNOWN = "neutral_or_unknown"

# relative-axis vocabulary v2 — masterplan §6 table (replaces engine :147-156's absolute
# words on a relative measure). Keys are the OLD strings so a migration/mutation check can
# assert they are gone; values are the (EN, ZH) pair the engine must emit instead.
VOCAB_V2: dict[str, tuple[str, str]] = {
    "accelerating in": ("above norm, rising", "高于常态·升温"),
    "inflow cooling": ("above norm, cooling", "高于常态·降温"),
    "accelerating out": ("below norm, worsening", "低于常态·加剧"),
    "outflow easing": ("below norm, easing", "低于常态·趋缓"),
    "balanced": ("near its norm", "接近常态"),
    "n/a": ("no data", "无数据"),
}

# acceleration_breadth buckets, keyed by the NEW state string (masterplan §4 shape).
_ACCEL_BUCKET: dict[str, str] = {
    "above norm, rising": "strengthening",
    "above norm, cooling": "cooling",
    "below norm, worsening": "worsening",
    "below norm, easing": "easing",
    "near its norm": NEUTRAL_OR_UNKNOWN,
    "no data": NEUTRAL_OR_UNKNOWN,
}

# W5-calibrated thresholds — spec §1.2 (research/flow_observatory/W5_PREREG.md;
# DEC-FLOW-OBSERVATORY-V2-W5-METHOD-SELECTION). REL_THRESH stays the shared default AND
# southbound's own post-W5 cutoff (its threshold re-sweep excluded every improving tau via
# the <2% held-out-reach sanity bound — a current-regime degeneracy — so the incumbent 0.5
# stays numerically unchanged). THEMES/NAMES recalibrate per the frozen §4 procedure.
REL_THRESH = 0.5                                  # ±0.5σ velocity — southbound (unchanged)
THEMES_REL_THRESH = 0.75                          # themes: in the honest-neutral band, flip
                                                   # strictly improves (not a tie)
NAMES_REL_THRESH = 0.3                            # names: mechanical nearest-band + min-flip
SOUTHBOUND_REL_THRESH = REL_THRESH                # explicit alias — see comment above
ABS_DEMINIMIS: dict[str, float] = {"pct_rate": 0.1, "cny_b": 0.5}


class ContractError(ValueError):
    """Raised by :func:`validate` on a ``flow_observatory.v2`` contract violation."""


# ── direction enums ─────────────────────────────────────────────────────────────────
def direction_from_value(value: float | None, unit: str) -> str:
    """positive|negative|neutral|unknown for an ABSOLUTE-axis value.

    ``unknown`` when the value itself is missing (never "zero" — missing ≠ zero, §4 law).
    ``neutral`` inside the unit's de-minimis band (themes: |x|<0.1pp; southbound: |x|<0.5¥B).
    """
    if value is None:
        return "unknown"
    floor = ABS_DEMINIMIS.get(unit, 0.0)
    if abs(value) < floor:
        return "neutral"
    return "positive" if value > 0 else "negative"


def rel_direction(vel: float | None, thresh: float = REL_THRESH) -> str:
    """positive|negative|neutral|unknown for the RELATIVE (velocity/σ) axis."""
    if vel is None:
        return "unknown"
    if abs(vel) < thresh:
        return "neutral"
    return "positive" if vel > 0 else "negative"


def quadrant(abs_dir: str, rel_dir: str, sufficient: bool = True) -> str:
    """abs_dir/rel_dir in {positive,negative,neutral,unknown} -> the quadrant enum.

    ``sufficient=False``, either axis ``unknown``, or either axis ``neutral`` all fall to
    ``neutral_or_unknown`` — the honest neutral band (spec §1.2): a near-threshold or
    partially-missing read must never be forced into one of the four "loud" quadrants.
    """
    if not sufficient or abs_dir in ("unknown", "neutral") or rel_dir in ("unknown", "neutral"):
        return NEUTRAL_OR_UNKNOWN
    if abs_dir == "positive" and rel_dir == "positive":
        return "true_accumulation"
    if abs_dir == "negative" and rel_dir == "positive":
        return "improving_but_still_selling"
    if abs_dir == "positive" and rel_dir == "negative":
        return "weakening_but_still_buying"
    if abs_dir == "negative" and rel_dir == "negative":
        return "true_distribution"
    return NEUTRAL_OR_UNKNOWN                     # unreachable with the 4 known dirs; fail safe


def quadrant_labels(q: str) -> tuple[str, str]:
    return QUADRANT_LABELS.get(q, QUADRANT_LABELS[NEUTRAL_OR_UNKNOWN])


# ── per-row abs/rel/quadrant block (spec §1.3) ─────────────────────────────────────────
def abs_field(value: float | None, *, period: str, unit: str) -> dict[str, Any]:
    return {"period": period, "value": value, "unit": unit,
            "direction": direction_from_value(value, unit)}


def rel_field(value: float | None, *, reference_window: int = 126,
             thresh: float = REL_THRESH) -> dict[str, Any]:
    return {"value": value, "unit": "sigma", "direction": rel_direction(value, thresh=thresh),
            "reference_window": reference_window}


def enrich_group(abs_value: float | None, rel_value: float | None, *,
                  abs_unit: str = "pct_rate", abs_period: str = "20d",
                  reference_window: int = 126, rel_thresh: float = REL_THRESH) -> dict[str, Any]:
    """The additive ``{abs, rel, quadrant, quadrant_en, quadrant_zh}`` block for one
    group/aggregate row — the anti-conflation device every W1 gate hinges on.

    ``rel_thresh`` defaults to the legacy/southbound ±0.5σ cutoff; W5-adjudicated callers
    pass ``THEMES_REL_THRESH``/``NAMES_REL_THRESH`` (DEC-FLOW-OBSERVATORY-V2-W5-METHOD-
    SELECTION)."""
    a = abs_field(abs_value, period=abs_period, unit=abs_unit)
    r = rel_field(rel_value, reference_window=reference_window, thresh=rel_thresh)
    q = quadrant(a["direction"], r["direction"])
    en, zh = quadrant_labels(q)
    return {"abs": a, "rel": r, "quadrant": q, "quadrant_en": en, "quadrant_zh": zh}


def assign_ranks(rows: list[dict[str, Any]]) -> None:
    """1-based rank by |vel| within the lens, in place. ``vel=None`` rows get ``rank=None``
    rather than being silently sorted to one end (spec §1.3)."""
    ranked = sorted((r for r in rows if r.get("vel") is not None), key=lambda r: -abs(r["vel"]))
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
    for r in rows:
        r.setdefault("rank", None)


# ── market_read (spec §1.4) — reusable for the theme lens AND the names lens ──────────
def market_read(rows: list[dict[str, Any]], unscored: int = 0, *,
                 abs_key: str = "rate_4wk", rel_key: str = "vel", state_key: str = "state",
                 abs_unit: str = "pct_rate", rel_thresh: float = REL_THRESH) -> dict[str, dict[str, int]]:
    """absolute_breadth / relative_breadth / acceleration_breadth, each declaring its own
    denominator = scored + unscored (§4 law: every cross-sectional statistic declares
    denominator + coverage). ``unscored`` folds the previously-silent kin-None drops into
    ``missing`` rather than letting them vanish from the count entirely.

    ``rel_thresh`` defaults to the legacy/southbound ±0.5σ cutoff; the themes/names callers
    in :func:`build_v2` and ``engine.flow_velocity.ashare_name_velocity`` pass their own
    W5-adjudicated value (DEC-FLOW-OBSERVATORY-V2-W5-METHOD-SELECTION)."""
    denom = len(rows) + unscored
    abs_c = {"positive": 0, "negative": 0, "neutral": 0, "missing": unscored, "denominator": denom}
    rel_c = {"positive": 0, "negative": 0, "neutral": 0, "missing": unscored, "denominator": denom}
    accel_c = {"strengthening": 0, "cooling": 0, "easing": 0, "worsening": 0,
               NEUTRAL_OR_UNKNOWN: unscored, "denominator": denom}
    for r in rows:
        ad = direction_from_value(r.get(abs_key), abs_unit)
        abs_c["missing" if ad == "unknown" else ad] += 1
        rd = rel_direction(r.get(rel_key), thresh=rel_thresh)
        rel_c["missing" if rd == "unknown" else rd] += 1
        accel_c[_ACCEL_BUCKET.get(r.get(state_key) or "no data", NEUTRAL_OR_UNKNOWN)] += 1
    return {"absolute_breadth": abs_c, "relative_breadth": rel_c, "acceleration_breadth": accel_c}


# ── sources[] (spec §1.5) ───────────────────────────────────────────────────────────
# Presentation metadata per masterplan §3 leg — kept here (not the template) so a
# "thin render tier" template stays thin: state words and method lines are business
# logic, not Jinja. Only the legs the W1 engine actually produces panels for are
# emitted (cn_large_order_proxy, sb_aggregate, nb_aggregate, hk_sb_holdings,
# lhb_inst_seats); sw_l1_sectors (the official-sector lens) is W4 scope — the engine
# has no sw_l1_sectors panel at all yet, and fabricating a source block with no real
# coverage for a leg nothing reads would itself violate the honesty gate this module
# exists to enforce.
SOURCE_META: dict[str, dict[str, str]] = {
    "cn_large_order_proxy": {
        "name_en": "A-share large-order flow", "name_zh": "A股主力大单",
        "tip_en": "Large & super-large order-size proxy — Tushare moneyflow_dc main-force "
                  "order-size classification, not identified investors.",
        "tip_zh": "大单+超大单口径——Tushare moneyflow_dc 主力口径分类，非机构身份识别。",
    },
    "sb_aggregate": {
        "name_en": "Southbound aggregate", "name_zh": "南向整体",
        "tip_en": "Official Stock-Connect southbound aggregate net flow — Eastmoney "
                  "RPT_MUTUAL_DEAL_HISTORY, whole-channel tape.",
        "tip_zh": "沪深港通南向整体净流入——东方财富 RPT_MUTUAL_DEAL_HISTORY，整条通道口径。",
    },
    "nb_aggregate": {
        "name_en": "Northbound aggregate", "name_zh": "北向整体",
        "tip_en": "Official Stock-Connect northbound aggregate net flow — disclosure "
                  "discontinued under the home-market rule; historical only.",
        "tip_zh": "沪深港通北向整体净流入——本地市场规则下已停止披露，仅历史数据。",
    },
    "hk_sb_holdings": {
        "name_en": "HK southbound holdings", "name_zh": "南向持仓",
        "tip_en": "Mainland southbound per-name holdings — Eastmoney "
                  "RPT_MUTUAL_STOCK_HOLDRANKS, expected one HK session behind.",
        "tip_zh": "内地南向个股持仓——东方财富 RPT_MUTUAL_STOCK_HOLDRANKS，预期滞后一个港股交易日。",
    },
    "lhb_inst_seats": {
        "name_en": "Dragon-Tiger institutional seats", "name_zh": "龙虎榜机构专用",
        "tip_en": "Dragon-Tiger institutional-seat net flow on recent event-selected names — "
                  "an anonymous, event-selected sample, never a market-wide census.",
        "tip_zh": "近期事件筛选个股的龙虎榜机构专用席位净额——匿名、事件样本，非市场普查。",
    },
}

_STATE_WORDS = {
    "current": ("current", "最新"),
    "expected_lag": ("expected T−1", "预期T−1"),
    # {date} is substituted by the caller (build_sources) with the leg's own effective_date.
    "behind": ("behind — showing {date} data", "滞后 · 显示{date}数据"),
    # S9: a coverage-collapse DEGRADED (gap_sessions == 0 — the leg IS today's date, just
    # thin) reads differently from a plain calendar-gap DEGRADED: "behind — showing {date}"
    # would be misleading (the date shown is TODAY's, not a stale one), and the real numbers
    # already live in the chip's LENS tooltip (REASON_TEXT["coverage_collapse"] below).
    "thin_coverage": ("thin coverage", "覆盖不足"),
    "stale": ("stale — showing {date}", "已过期 · 显示{date}数据"),
    "historical": ("historical only — ended {date}", "仅历史 · 止于{date}"),
    "unavailable": ("unavailable", "不可用"),
    "revised": ("revised", "已修正"),
}

# ``sources[].status`` (quality.STATUS_ENUM) -> ``sources[].ui_state`` (W2_SPEC.md §2 exact
# mapping table). HEALTHY splits into "current"/"expected_lag" by reason, handled in
# :func:`ui_state_from_status` rather than this table.
_STATUS_TO_UI_STATE: dict[str, str] = {
    fo_quality.HEALTHY: "current",
    fo_quality.DEGRADED: "behind",
    fo_quality.STALE: "stale",
    fo_quality.UNAVAILABLE: "unavailable",
    fo_quality.HISTORICAL_ONLY: "historical",
    fo_quality.REVISED: "revised",
}

# plain-word phrasing for a leg's own quality.classify_leg() reasons — surfaced in the
# trust-chip LENS tooltip (spec §3: "DEGRADED renders ... plus the coverage reason in the
# chip LENS") so a reader can hover a "behind" or "stale" chip and learn WHY, not just THAT.
REASON_TEXT: dict[str, tuple[str, str]] = {
    "one_session_behind": ("one session behind its own calendar", "落后自身日历一个交易日"),
    "sessions_behind": ("multiple sessions behind its own calendar", "落后自身日历多个交易日"),
    "behind_expected_lag": ("behind its own T−1 cadence", "落后于其自身T−1节奏"),
    "coverage_collapse": ("scored coverage dropped sharply vs its recent norm",
                         "已评分覆盖率较近期常态大幅下降"),
    "unreadable_as_of": ("no usable date could be read", "无法读取有效日期"),
    "expected_t_minus_1": ("expected — this leg normally lags one session by design",
                          "预期滞后——该数据源按设计正常滞后一个交易日"),
    "desk_backstop": ("the whole desk has not advanced in over 10 days",
                     "整个看板已超过10天未更新"),
    "date_regression": ("a previously published date moved backward — treat as revised",
                       "此前发布的日期发生倒退——请视为已修正"),
    "discontinued": ("disclosure permanently discontinued", "披露已永久停止"),
    "event_window": ("event-window sample — a quiet stretch is normal",
                    "事件窗口样本——平静期属正常现象"),
}

# status word for CHANGE ROWS ("A-share large-order proxy: current → stale", spec §3) —
# deliberately a separate table from _STATE_WORDS (which carries {date}-templated chip
# copy): a transition row names the FROM/TO status word bare, with no date substitution.
STATUS_WORD: dict[str, tuple[str, str]] = {
    fo_quality.HEALTHY: ("current", "最新"),
    fo_quality.DEGRADED: ("behind", "滞后"),
    fo_quality.STALE: ("stale", "已过期"),
    fo_quality.UNAVAILABLE: ("unavailable", "不可用"),
    fo_quality.HISTORICAL_ONLY: ("historical", "仅历史"),
    fo_quality.REVISED: ("revised", "已修正"),
}


def ui_state_from_status(status: str | None, reasons: list[str] | None = None) -> str:
    """``sources[].ui_state`` FROM ``sources[].status`` — W2_SPEC.md §2's exact mapping.

    HEALTHY splits by reason: ``hk_sb_holdings`` at its normal one-session lag carries
    ``reasons=["expected_t_minus_1"]`` and reads "expected_lag", not a bare "current" (that
    would erase the useful "this leg is ALWAYS one session behind by design" signal); every
    other HEALTHY leg reads "current".

    S1: the literal "revised" ui_state word is possible ONLY when ``status`` is itself the
    literal string "REVISED" — which (per ``quality.classify_leg``'s S1 repair) only ever
    happens when the gap verdict ALONE would have been HEALTHY. A leg that is ALSO
    STALE/UNAVAILABLE never reaches this branch: its ``status`` stays "STALE"/"UNAVAILABLE"
    (the regression only ever WORSENS a gap-based status, never replaces it with "REVISED"),
    so ``_STATUS_TO_UI_STATE`` maps it to "stale"/"unavailable" as normal — the "revised"
    chip word can never mask a materially worse read.
    """
    if status == fo_quality.HEALTHY and reasons and "expected_t_minus_1" in reasons:
        return "expected_lag"
    return _STATUS_TO_UI_STATE.get(status, "unavailable")


def _state_word_key(status: str | None, ui_state: str, reasons: list[str] | None,
                    gap_sessions: int | None) -> str:
    """The ``_STATE_WORDS`` key for one leg's chip (S9 repair): DEGRADED's own wording
    depends on WHY it is degraded. A plain calendar-gap DEGRADED keeps the existing
    "behind — showing {date} data" word (``ui_state`` "behind"). A pure coverage-collapse
    DEGRADED — ``gap_sessions == 0``, i.e. the leg's date IS current, it is just thin — reads
    "thin coverage" instead: the {date}-behind wording would misleadingly show TODAY's date
    under a word implying staleness, and the real coverage numbers already live in the
    chip's LENS tooltip (``REASON_TEXT["coverage_collapse"]``).
    """
    if (status == fo_quality.DEGRADED and reasons and "coverage_collapse" in reasons
            and (gap_sessions or 0) == 0):
        return "thin_coverage"
    return ui_state


def _reason_suffix(reasons: list[str] | None, lang_idx: int) -> str:
    return " · ".join(REASON_TEXT[r][lang_idx] for r in (reasons or []) if r in REASON_TEXT)


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_date(value):
    """Parse an ISO ``YYYY-MM-DD`` stamp, or None when it is not one.

    A pure, module-level copy of ``lib.desk_guard._as_date`` (S8 repair): contract.py
    is pure assembly/validation with no I/O and no cross-module private imports (masterplan
    §4 module-layout freeze) — reaching into another module's underscore-prefixed helper
    coupled this module to desk_guard's internals for a two-line date parse.
    """
    from datetime import date, datetime

    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _coverage_line(coverage: dict[str, Any]) -> str:
    n_obs, n_sized, pct = coverage.get("n_observed"), coverage.get("n_sized"), coverage.get("pct_names")
    if n_obs is None:
        return "—"
    if n_sized is not None:
        return f"{n_obs:,} ({n_sized:,} sized)"
    if pct is not None:
        return f"{n_obs:,} · {pct:g}%"
    return f"{n_obs:,}"


def _source_leg(source_id: str, *, provider: str, market: str, effective_date: str | None,
                 expected_availability: str, coverage: dict[str, Any],
                 quality_result: dict[str, Any] | None = None,
                 source_kind: str = "", first_known_at=None) -> dict[str, Any]:
    meta = SOURCE_META.get(source_id, {})
    q = quality_result or {}
    status = q.get("status")
    reasons = q.get("reasons") or []
    confidence = q.get("confidence")
    gap_sessions = q.get("gap_sessions")
    revised = bool(q.get("revised"))
    ui_state = ui_state_from_status(status, reasons)
    word_key = _state_word_key(status, ui_state, reasons, gap_sessions)
    word_en, word_zh = _STATE_WORDS.get(word_key, _STATE_WORDS["unavailable"])
    date_str = effective_date or "—"
    tip_en, tip_zh = meta.get("tip_en", ""), meta.get("tip_zh", "")
    suf_en, suf_zh = _reason_suffix(reasons, 0), _reason_suffix(reasons, 1)
    if suf_en:
        tip_en = f"{tip_en} {suf_en}".strip()
    if suf_zh:
        tip_zh = f"{tip_zh} {suf_zh}".strip()
    return {
        "source_id": source_id, "source_kind": source_kind, "provider": provider,
        "market": market, "effective_date": effective_date,
        "expected_availability": expected_availability, "coverage": coverage,
        "first_known_at": first_known_at, "status": status,
        "reasons": reasons, "confidence": confidence, "gap_sessions": gap_sessions,
        "revised": revised, "ui_state": ui_state,
        "name_en": meta.get("name_en", source_id), "name_zh": meta.get("name_zh", source_id),
        "tip_en": tip_en, "tip_zh": tip_zh,
        "coverage_line": _coverage_line(coverage),
        "state_word_en": word_en.format(date=date_str), "state_word_zh": word_zh.format(date=date_str),
    }


def state_log_legs_snapshot(sources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The compact per-leg record ``scripts/build_flow_velocity`` writes into the state_log
    entry's ``health.legs`` (spec §2: "state_log entry gains a compact health field") — just
    enough (status / effective_date / coverage_n) for the NEXT session's
    :func:`engine.flow_observatory.changes.leg_quality_history` to derive REVISED detection
    and the coverage-collapse trailing median. Deliberately not the desk-facing 3-key
    ``health`` block (:func:`engine.flow_observatory.quality.compute_health`) — that block
    is the machine/UI-facing rollup; this one is the historical accelerator, same split as
    ``state_log.jsonl`` vs ``market_read`` for themes.
    """
    return {s["source_id"]: {"status": s.get("status"), "effective_date": s.get("effective_date"),
                             "coverage_n": (s.get("coverage") or {}).get("n_observed")}
           for s in sources}


def build_sources(snap: dict[str, Any], *, newest_session: str | None,
                  seats_as_of: str | None = None,
                  log_rows: list[dict[str, Any]] | None = None,
                  ledger_rows: list[dict[str, Any]] | None = None,
                  now=None) -> list[dict[str, Any]]:
    """One block per masterplan §3 leg — ALWAYS all five W1 legs (S7 repair): a leg whose
    panel did not build this run still gets its identity row so the trust strip shows
    "unavailable — not zero flow" rather than a silent hole (masterplan §5 publication
    law). ``sw_l1_sectors`` stays out of scope entirely (W4 — the engine has no panel for
    it at all yet; see the SOURCE_META docstring above for why fabricating one would
    itself violate the honesty gate this module exists to enforce).

    W2: every leg's ``status``/``reasons``/``confidence``/``gap_sessions``/``revised`` now
    come from ``engine.flow_observatory.quality.classify_leg`` (never left ``null`` as W1
    did), with the desk-level wall-clock backstop applied across all five before
    ``ui_state`` is derived (spec §1-§2).

    ``now`` (B1 repair — renamed from ``today``) is the wall-clock anchor for calendar-gap
    legs, and MUST be a real ``datetime`` for production callers (never a bare UTC date fed
    straight to an Asia calendar — the exact forbidden shape B1 closes; see
    ``quality.classify_leg`` / ``quality._newest_completed_session``). ``None`` (the
    default, and every pre-W2 caller) skips staleness measurement entirely, so existing
    callers keep reporting HEALTHY/"current" exactly as before unless they opt in by
    passing a real ``now``. The desk-level wall-clock backstop (``apply_desk_backstop``, the
    ONE calendar-day rule) derives its own coarse ``today`` date FROM ``now`` here rather
    than taking a second explicit parameter — one wall-clock anchor in, and both the
    session-aware per-leg gap and the calendar-day backstop derive their own reading from
    it.
    ``log_rows`` (state_log history) feeds the coverage-collapse/REVISED inputs; omitted or
    empty degrades those two checks to their honest "insufficient/no history" no-ops.

    ``ledger_rows`` (W3 — the observations ledger, ``engine.flow_observatory.history``)
    feeds each leg's ``first_known_at`` (spec §2: "closes the W1 limitation" — previously
    always ``None``): the ``entity_kind='market'`` row's own ``revision_id==0`` first-known
    time for that leg's effective date. Omitted/empty ledger degrades to the honest
    ``None`` every pre-W3 caller already saw (bootstrap: the ledger starts empty).

    HK-market legs (S8): ``sb_aggregate``/``hk_sb_holdings`` anchor their freshness gap
    against the newest HK-family date (sb_aggregate's own effective_date) rather than the
    CN ``market_session`` — the two calendars are not the same trading calendar, so
    comparing an HK leg's date against a CN close date can manufacture a false gap/false
    currency on days the two markets' sessions diverge. CN legs keep the CN anchor.
    """
    from datetime import datetime as _dt

    from engine.flow_observatory.changes import leg_quality_history

    today = now.date() if isinstance(now, _dt) else now
    log_rows = log_rows or []
    agg = {c.get("key"): c for c in (snap.get("aggregate") or []) if isinstance(c, dict)}
    names = snap.get("ashare_names") or {}
    sectors = snap.get("ashare_sectors") or {}
    hk = snap.get("hk_names") or {}
    seats = snap.get("seats_by_ticker") or {}
    sb = agg.get("southbound")
    sb_live = bool(sb and sb.get("live"))
    nb = agg.get("northbound")

    names_asof = names.get("as_of") or sectors.get("as_of")
    # the HK anchor is sb_aggregate's own date when live, falling back to the holdings
    # leg's own date, falling back to the CN session — never fabricated, just the least
    # stale REAL HK-family date this build actually has.
    hk_anchor = (sb.get("as_of") if sb_live else None) or hk.get("as_of") or newest_session

    n_obs = names.get("n")
    n_unscored = names.get("n_unscored") or 0
    total = (n_obs or 0) + n_unscored
    pct = round(100.0 * n_obs / total, 1) if (names_asof and n_obs is not None and total) else None
    cn_coverage = {"n_observed": n_obs if names_asof else None, "n_sized": None, "pct_names": pct}

    sb_effective = sb.get("as_of") if sb_live else None
    sb_coverage = ({"n_observed": 1, "n_sized": None, "pct_names": None} if sb_live
                  else {"n_observed": None, "n_sized": None, "pct_names": None})

    hk_effective = hk.get("as_of")
    hk_coverage = ({"n_observed": hk.get("n"), "n_sized": hk.get("n_sized"), "pct_names": None}
                  if hk else {"n_observed": None, "n_sized": None, "pct_names": None})

    nb_effective = nb.get("frozen_since") if nb else None

    seats_effective = seats_as_of if seats else None
    seats_coverage = ({"n_observed": len(seats), "n_sized": None, "pct_names": None} if seats
                      else {"n_observed": None, "n_sized": None, "pct_names": None})

    # ── classify every leg (quality engine, W2) ── B1: `now` (a real datetime for
    # production callers), never the coarse `today` date — see classify_leg's own docstring.
    cn_q = fo_quality.classify_leg(
        "cn_large_order_proxy", names_asof, cn_coverage,
        leg_quality_history(log_rows, "cn_large_order_proxy", newest_session), now)
    sb_q = fo_quality.classify_leg(
        "sb_aggregate", sb_effective, sb_coverage,
        leg_quality_history(log_rows, "sb_aggregate", newest_session), now)
    hk_q = fo_quality.classify_leg(
        "hk_sb_holdings", hk_effective, hk_coverage,
        leg_quality_history(log_rows, "hk_sb_holdings", newest_session), now)
    nb_q = fo_quality.classify_leg("nb_aggregate", nb_effective, {}, {}, now)
    seats_q = fo_quality.classify_leg("lhb_inst_seats", seats_effective, seats_coverage,
                                      {"present": bool(seats)}, now)

    leg_results = {"cn_large_order_proxy": cn_q, "sb_aggregate": sb_q,
                  "hk_sb_holdings": hk_q, "nb_aggregate": nb_q, "lhb_inst_seats": seats_q}
    leg_effective_dates = {"cn_large_order_proxy": names_asof, "sb_aggregate": sb_effective,
                           "hk_sb_holdings": hk_effective, "nb_aggregate": nb_effective,
                           "lhb_inst_seats": seats_effective}
    # desk-level wall-clock backstop — applied ACROSS all five before ui_state is derived,
    # so a total freeze floors every live leg's chip together (spec §1 last bullet).
    leg_results = fo_quality.apply_desk_backstop(leg_results, leg_effective_dates, today)

    # W3: each leg's first-known time from the observations ledger (None until the ledger
    # actually holds this leg's key — honest bootstrap, spec §2/§5).
    def _fk(source_id: str, effective_date: str | None) -> str | None:
        if not ledger_rows or not effective_date:
            return None
        return history.first_known_at(ledger_rows, "market", source_id, effective_date)

    legs: list[dict[str, Any]] = []

    legs.append(_source_leg(
        "cn_large_order_proxy", source_kind="large_order_size_proxy",
        provider="Tushare moneyflow_dc", market="CN", effective_date=names_asof,
        expected_availability="T+0 after CN close", coverage=cn_coverage,
        quality_result=leg_results["cn_large_order_proxy"],
        first_known_at=_fk("cn_large_order_proxy", names_asof)))

    legs.append(_source_leg(
        "sb_aggregate", source_kind="official_connect_aggregate",
        provider="Eastmoney RPT_MUTUAL_DEAL_HISTORY", market="HK",
        effective_date=sb_effective, expected_availability="T+0 after HK close",
        coverage=sb_coverage, quality_result=leg_results["sb_aggregate"],
        first_known_at=_fk("sb_aggregate", sb_effective)))

    legs.append(_source_leg(
        "hk_sb_holdings", source_kind="official_connect_holdings",
        provider="Eastmoney RPT_MUTUAL_STOCK_HOLDRANKS", market="HK",
        effective_date=hk_effective, expected_availability="expected T−1",
        coverage=hk_coverage, quality_result=leg_results["hk_sb_holdings"],
        first_known_at=_fk("hk_sb_holdings", hk_effective)))

    legs.append(_source_leg(
        "nb_aggregate", source_kind="official_connect_aggregate",
        provider="Eastmoney (discontinued disclosure)", market="CN",
        effective_date=nb_effective,
        expected_availability=(f"discontinued {nb.get('frozen_since')}" if nb and nb.get("frozen_since")
                               else "discontinued"),
        coverage={"n_observed": None, "n_sized": None, "pct_names": None},
        quality_result=leg_results["nb_aggregate"],
        first_known_at=_fk("nb_aggregate", nb_effective)))

    legs.append(_source_leg(
        "lhb_inst_seats", source_kind="event_selected_institution_seat",
        provider="Eastmoney 龙虎榜 机构专用", market="CN",
        effective_date=seats_effective, expected_availability="event-window",
        coverage=seats_coverage, quality_result=leg_results["lhb_inst_seats"],
        first_known_at=_fk("lhb_inst_seats", seats_effective)))

    return legs


# ── build_v2 assembly (spec §1.7) ──────────────────────────────────────────────────
def build_v2(snap: dict[str, Any], *, log_rows: list[dict[str, Any]] | None = None,
            ledger_rows: list[dict[str, Any]] | None = None,
            market_session: str | None = None, generated_at: str | None = None,
            seats_as_of: str | None = None, now=None,
            state_history=None) -> dict[str, Any]:
    """Merge the W1+W2+W3 ``flow_observatory.v2`` additive fields into the existing desk
    payload.

    Pure assembly — no I/O. ``log_rows`` is the already-read ``state_log.jsonl`` content
    (pass ``[]``/``None`` when unavailable — history fields degrade to honest nulls, never
    a fabricated zero). ``now`` (B1 repair — renamed from ``today``) is the wall-clock
    anchor threaded into :func:`build_sources` / ``quality.classify_leg`` for calendar-gap
    staleness, and MUST be a real ``datetime`` for production callers (never a bare UTC date
    fed straight to an Asia calendar). ``None`` (the default) skips staleness measurement
    entirely, so every pre-W2 caller keeps reporting HEALTHY/"current" unless it opts in
    with a real ``now``. ``state_history`` is an injectable ``changes.theme_state_history``
    callable (defaults to importing :mod:`engine.flow_observatory.changes` lazily, keeping
    this module import-cycle-free for tests that only need the pure math).

    ``ledger_rows`` (W3 — the already-read ``observations.parquet`` content,
    ``engine.flow_observatory.history``) becomes the per-row state_started/
    state_age_sessions/prior_state/rank_change source, AND feeds ``sources[]``'
    ``first_known_at``, once it holds ≥2 distinct theme sessions (spec §2: "state_log
    summaries stay as fallback until the ledger has ≥2 sessions" — both paths tested).
    ``None``/empty (the bootstrap state and every pre-W3 caller) keeps the exact W1/W2
    state_log-derived behavior.
    """
    log_rows = log_rows or []
    ledger_rows = ledger_rows or []
    market_session = market_session or snap.get("as_of")
    # B2: the escalation streak's "current run" is identified by BUILD date (generated_at's
    # own date), never the market session — a frozen market_session must not also freeze
    # `quality.consecutive_degraded_sessions`'s walk (see that function's docstring).
    run_date = str(generated_at)[:10] if generated_at else None
    if state_history is None:
        from engine.flow_observatory.changes import theme_state_history as state_history

    out: dict[str, Any] = dict(snap)
    out["schema"] = SCHEMA
    out["authority"] = AUTHORITY
    out["generated_at"] = generated_at
    out["market_session"] = market_session

    # §1.5 — sources[] (hoisted ahead of the per-row loop below, W3): the per-row age walk
    # needs cn_large_order_proxy's OWN current-session status to know whether TODAY's read
    # must freeze (spec §3 test 6) — build_sources has no dependency on the enriched rows,
    # so calling it first changes nothing about its own output, only its ORDER.
    out["sources"] = build_sources(snap, newest_session=market_session, seats_as_of=seats_as_of,
                                   log_rows=log_rows, ledger_rows=ledger_rows, now=now)
    leg_statuses = {s["source_id"]: s.get("status") for s in out["sources"]}
    cn_status = leg_statuses.get("cn_large_order_proxy")
    ledger_ready = bool(ledger_rows) and history.ledger_session_count(ledger_rows, "theme") >= 2

    # §1.3 — per-row abs/rel/quadrant/rank/rank_change/state_* on ashare_sectors.rows[]
    sectors = snap.get("ashare_sectors")
    enriched_rows: list[dict[str, Any]] = []
    if sectors and sectors.get("rows"):
        for row in sectors["rows"]:
            row = dict(row)
            row.update(enrich_group(row.get("rate_4wk"), row.get("vel"),
                                    abs_unit="pct_rate", abs_period="20d", reference_window=126,
                                    rel_thresh=THEMES_REL_THRESH))
            enriched_rows.append(row)
        assign_ranks(enriched_rows)
        prev_ranks = _previous_ranks(log_rows, market_session)
        for row in enriched_rows:
            if ledger_ready and market_session:
                hist = history.state_for_session(
                    ledger_rows, "theme", row["id"], market_session, row["quadrant"],
                    current_rank=row.get("rank"), current_status=cn_status)
                row["rank_change"] = hist["rank_change"]
            else:
                hist = (state_history(row["id"], row["quadrant"], log_rows, market_session)
                        if market_session else
                        {"state_started": None, "state_age_sessions": None, "prior_state": None,
                         "note": "first tracked session"})
                prev_rank = prev_ranks.get(row["id"]) if prev_ranks is not None else None
                row["rank_change"] = (row["rank"] - prev_rank) \
                    if (prev_ranks is not None and row["rank"] is not None and prev_rank is not None) \
                    else None
            row["state_started"] = hist["state_started"]
            row["state_age_sessions"] = hist["state_age_sessions"]
            row["prior_state"] = hist["prior_state"]
            row["state_note"] = hist["note"]
        out["ashare_sectors"] = {**sectors, "rows": enriched_rows}

    # southbound aggregate — the SAME abs+rel+quadrant treatment (spec §1.3 last line)
    agg = snap.get("aggregate")
    if agg:
        new_agg = []
        for chan in agg:
            chan = dict(chan)
            if chan.get("key") == "southbound" and chan.get("live"):
                chan.update(enrich_group(chan.get("flow_1m_b"), chan.get("vel_primary"),
                                         abs_unit="cny_b", abs_period="1m", reference_window=126,
                                         rel_thresh=SOUTHBOUND_REL_THRESH))
            new_agg.append(chan)
        out["aggregate"] = new_agg

    # §1.4 — market_read for the theme lens (n=22) AND the names lens (n=1518+unscored).
    # The frozen JSON block in the spec is the shape ONE lens takes; the prose ("computed
    # for the theme lens AND names") is what makes this two objects rather than one — the
    # least-invention reading of a shape shown once but demanded twice (flagged in the PR
    # body as a judgment call, not a silent one).
    names = snap.get("ashare_names") or {}
    # B3 repair: this used to hardcode unscored=0 for the theme lens while
    # ashare_sectors.n_unscored (flow_velocity.ashare_sector_velocity) already carried the
    # real drop count (themes with <3 members or an unscoreable kinetics read) — silently
    # dropping them from market_read.themes' denominator, the exact "missing != zero" gap
    # this program's contract law exists to close.
    themes_unscored = (sectors or {}).get("n_unscored") or 0
    themes_mr = market_read(enriched_rows, unscored=themes_unscored, rel_thresh=THEMES_REL_THRESH)
    names_mr = names.get("market_read") or market_read([], names.get("n_unscored") or 0)
    out["market_read"] = {"themes": themes_mr, "names": names_mr}

    # §2 — publication_state (worst-of live legs) + the desk-wide health block. sources[]
    # (and leg_statuses) were already built above, ahead of the per-row loop (W3) — machine
    # contract and UI still read the SAME per-leg statuses the trust strip renders
    # (W2_SPEC.md §0.1); only the ORDER of assembly moved, not the values.
    pub_state = fo_quality.publication_state(leg_statuses)
    out["publication_state"] = pub_state
    leg_results_by_id = {s["source_id"]: s for s in out["sources"]}
    # B2: keyed on the BUILD run_date (generated_at), never market_session — see this
    # function's own docstring and quality.consecutive_degraded_sessions.
    out["health"] = fo_quality.compute_health(pub_state, leg_results_by_id, log_rows, run_date)

    # a STALE/UNAVAILABLE cn_large_order_proxy must never let market_read read as current —
    # both the theme lens AND the names lens are fed by the SAME Tushare panel (spec §2).
    proxy_status = leg_statuses.get("cn_large_order_proxy")
    quality_word = {
        fo_quality.HEALTHY: "healthy", fo_quality.DEGRADED: "degraded",
        fo_quality.STALE: "stale", fo_quality.UNAVAILABLE: "unavailable",
        fo_quality.REVISED: "revised",
    }.get(proxy_status)
    if quality_word and isinstance(out.get("market_read"), dict):
        for lens_name in ("themes", "names"):
            lens = out["market_read"].get(lens_name)
            if isinstance(lens, dict):
                out["market_read"][lens_name] = {**lens, "quality": quality_word}

    return out


def _previous_ranks(log_rows: list[dict[str, Any]], before_session: str | None) -> dict[str, int] | None:
    """The previous valid session's {theme_id: rank} map, or None when there is no prior
    session at all (spec §4 test 8: missing log -> null, never a manufactured zero)."""
    if not before_session:
        return None
    rows = sorted((r for r in log_rows if r.get("session") and r["session"] < before_session),
                  key=lambda r: r["session"], reverse=True)
    if not rows:
        return None
    themes = rows[0].get("themes") or {}
    return {tid: rec.get("rank") for tid, rec in themes.items() if isinstance(rec, dict)}


# M1/W4 repair: the coverage_state enum both group lenses (curated ashare_sectors AND
# official_sectors) may carry — engine.flow_observatory.groups.INSUFFICIENT_COVERAGE_EN
# is display prose, not this machine value; kept here (not imported from groups.py) so
# contract.py stays the sole owner of every enum validate() checks, matching the
# STATUS_ENUM/QUADRANT pattern already established in this module.
COVERAGE_STATE_ENUM = {"ok", "insufficient_coverage"}


def _validate_group_rows(lens: dict[str, Any], label: str, *,
                          rel_thresh: float = REL_THRESH) -> None:
    """Shared per-row check for a group lens (``{"rows": [...]}}``-shaped, curated
    OR official): abs/rel/quadrant axis-consistency (spec §1.7, previously
    ashare_sectors-only) plus the coverage_state enum (W4 M1 repair — previously
    unchecked for BOTH lenses).

    ``rel_thresh`` must match whatever threshold :func:`enrich_group` used to compute the
    row's own ``rel.direction`` (themes rows are W5-recalibrated to ``THEMES_REL_THRESH``;
    the official-sector lens is untouched by W5 and keeps the legacy default) — otherwise
    this independent recomputation would flag a row that was built correctly."""
    for row in (lens or {}).get("rows") or []:
        cs = row.get("coverage_state")
        if cs is not None and cs not in COVERAGE_STATE_ENUM:
            raise ContractError(
                f"{label} row {row.get('id')}: coverage_state {cs!r} is not in the known "
                f"enum {sorted(COVERAGE_STATE_ENUM)}")
        a, r, q = row.get("abs"), row.get("rel"), row.get("quadrant")
        if a is None or r is None or q is None:
            continue
        av, ad = a.get("value"), a.get("direction")
        expected_ad = direction_from_value(av, a.get("unit"))
        if expected_ad != ad:
            raise ContractError(
                f"{label} row {row.get('id')}: abs.direction {ad!r} disagrees with abs.value "
                f"{av!r} (expected {expected_ad!r})")
        rv, rd = r.get("value"), r.get("direction")
        expected_rd = rel_direction(rv, thresh=rel_thresh)
        if expected_rd != rd:
            raise ContractError(
                f"{label} row {row.get('id')}: rel.direction {rd!r} disagrees with rel.value "
                f"{rv!r} (expected {expected_rd!r})")
        expected_q = quadrant(ad, rd)
        if expected_q != q:
            raise ContractError(
                f"{label} row {row.get('id')}: quadrant {q!r} inconsistent with abs={ad!r} "
                f"rel={rd!r} (expected {expected_q!r})")


# ── validate() (spec §1.7) ──────────────────────────────────────────────────────────
def validate(desk: dict[str, Any]) -> None:
    """Raise :class:`ContractError` on a ``flow_observatory.v2`` contract violation.

    Builder calls this on the FINAL payload before writing (a violation blocks the v2
    write, never the plain page — see ``scripts/build_flow_velocity``); tests call it
    directly on fixtures. Checks (spec §1.7): missing denominators, quadrant inconsistent
    with its own abs/rel directions, absolute/relative fields disagreeing with their
    direction enums, and the top-level build instant imitating a leg's market date.

    S6 repair: the leg-date check used to compare a leg's ``effective_date`` (always a
    plain ``YYYY-MM-DD`` panel date) against ``generated_at`` verbatim (always a full ISO
    build instant with a time component, e.g. ``"2026-09-01T12:00:00+00:00"``) — two
    values that can never be string-equal regardless of any bug, so the check was dead
    code, unreachable by construction and never exercised by any test. The real invariant
    ("leg effective dates must come from panel-provided dates" — masterplan §5 "build time
    != source time") is now enforced two ways: (1) every non-null effective_date must
    actually BE a plain calendar date — a build instant substituted in for it is
    recognizably NOT that shape (has a "T", wrong length) and is rejected on sight, with
    zero false-positive risk against a real T+0 leg whose date legitimately coincides with
    today's build date; (2) the original byte-identical comparison is kept as a
    defense-in-depth belt-and-suspenders check.

    S3 repair (five checks, each with its own failing-first test in
    tests/test_flow_observatory_quality.py): (a) every ``sources[]`` block's ``status`` is
    non-null AND drawn from the enum — previously a null status only failed silently
    elsewhere, never here; (b) ``publication_state`` is now a REQUIRED top-level key, not a
    soft "only check it if present" — a payload that omits it entirely used to sail through
    unchecked; (c) ``market_read.{themes,names}.quality`` must reflect the cn proxy's status
    for BOTH STALE ("stale") and UNAVAILABLE ("unavailable") — the old check only ever
    covered STALE; (d) ``health.publication_state`` must equal the top-level
    ``publication_state`` — the two are supposed to be the SAME number by construction, but
    nothing enforced that machine/UI agreement; (e) every leg's ``ui_state`` must equal
    ``ui_state_from_status(status, reasons)`` — the machine (status) and the UI (ui_state)
    reading are validated to agree, never merely assumed to.
    """
    mr = desk.get("market_read") or {}
    for lens_name, lens in mr.items():
        if not isinstance(lens, dict):
            raise ContractError(f"market_read.{lens_name} is not a breadth object")
        for breadth_name, breadth in lens.items():
            if breadth_name == "quality":
                continue  # W2: a plain quality-word string, not a breadth-count object
            if "denominator" not in (breadth or {}):
                raise ContractError(f"market_read.{lens_name}.{breadth_name} missing denominator")

    _validate_group_rows(desk.get("ashare_sectors") or {}, "ashare_sectors",
                        rel_thresh=THEMES_REL_THRESH)
    # M1/W4 repair: official_sectors (the Shenwan L1 lens) never got its own
    # validate() coverage — contract.py was untouched in the W4 landing (its rows
    # reuse contract.enrich_group/assign_ranks, but nothing checked the RESULT).
    # Minimal extension: the SAME abs/rel/quadrant axis-consistency check every
    # ashare_sectors row already gets, plus the coverage_state enum (both lenses —
    # a group's coverage_state must be a known value, never an unchecked free string).
    os_lens = desk.get("official_sectors")
    if isinstance(os_lens, dict) and os_lens.get("available"):
        _validate_group_rows(os_lens, "official_sectors")

    generated_at = desk.get("generated_at")
    sources = desk.get("sources") or []
    for s in sources:
        ed = s.get("effective_date")
        if ed:
            if not _ISO_DATE_RE.match(str(ed)):
                raise ContractError(
                    f"source {s.get('source_id')}: effective_date {ed!r} is not a plain "
                    "calendar date — a build instant (or some other non-panel value) was "
                    "substituted for the panel's own as_of date (§5 law: build time must "
                    "never imitate source time)")
            if generated_at and str(ed) == str(generated_at):
                raise ContractError(
                    f"generated_at (build instant) is byte-identical to source "
                    f"{s.get('source_id')}'s effective_date {generated_at!r} — build time must "
                    "never imitate source time (§5 law)")
        # W2/S3(a) — status must be present (non-null) AND drawn from the enum (spec §2:
        # "status (now always set — replaces W1's null)").
        st = s.get("status")
        if st is None:
            raise ContractError(
                f"source {s.get('source_id')}: status is null — W2 always sets a status "
                "(classify_leg never returns None)")
        if st not in fo_quality.STATUS_ENUM:
            raise ContractError(
                f"source {s.get('source_id')}: status {st!r} is not in the W2 quality enum "
                f"{sorted(fo_quality.STATUS_ENUM)}")
        # S3(e) — the UI's own ui_state must equal what the status/reasons MAP to; a payload
        # cannot claim a status while showing a DIFFERENT ui_state chip for it.
        expected_ui = ui_state_from_status(st, s.get("reasons"))
        if s.get("ui_state") != expected_ui:
            raise ContractError(
                f"source {s.get('source_id')}: ui_state {s.get('ui_state')!r} disagrees with "
                f"status {st!r}/reasons {s.get('reasons')!r} (expected {expected_ui!r}) — "
                "machine and UI must read the same verdict (W2_SPEC.md §0.1)")

    # W2/S3(b) — publication_state is now a REQUIRED top-level key (previously only checked
    # "if present" — a payload omitting it entirely used to sail through untouched), and it
    # must be the worst-of rollup of the SAME leg statuses sources[] just carried (spec §2:
    # "publication_state consistent with worst-of rule"). A STALE cn_large_order_proxy proxy
    # leg can never coexist with a HEALTHY desk-wide rollup — the exact "stale reads as
    # confidently current" defect this wave exists to close.
    if "publication_state" not in desk:
        raise ContractError(
            "publication_state is a required top-level key (W2_SPEC.md §2) — missing entirely")
    by_id = {s.get("source_id"): s for s in sources}
    pub_state = desk.get("publication_state")
    expected_pub = fo_quality.publication_state({sid: s.get("status") for sid, s in by_id.items()})
    if pub_state != expected_pub:
        raise ContractError(
            f"publication_state {pub_state!r} inconsistent with the worst-of rollup of "
            f"sources[] statuses (expected {expected_pub!r})")
    proxy = by_id.get("cn_large_order_proxy")
    if proxy and proxy.get("status") == fo_quality.STALE and pub_state == fo_quality.HEALTHY:
        raise ContractError(
            "publication_state HEALTHY cannot coexist with a STALE cn_large_order_proxy "
            "leg — a stale source must never publish as confidently current (spec §2)")
    # S3(c): the market_read quality flag must reflect the cn proxy's status for BOTH STALE
    # ("stale") AND UNAVAILABLE ("unavailable") — the pre-repair check only ever covered the
    # STALE case, so an UNAVAILABLE proxy silently leaving market_read.quality unset (or
    # wrong) went unnoticed by validate() even though contract.build_v2 already sets it
    # correctly in production.
    proxy_status = proxy.get("status") if proxy else None
    expected_quality = {fo_quality.STALE: "stale", fo_quality.UNAVAILABLE: "unavailable"}.get(proxy_status)
    if expected_quality:
        for lens_name in ("themes", "names"):
            lens_quality = ((desk.get("market_read") or {}).get(lens_name) or {}).get("quality")
            if lens_quality != expected_quality:
                raise ContractError(
                    f"market_read.{lens_name}.quality must be {expected_quality!r} when "
                    f"cn_large_order_proxy is {proxy_status} (got {lens_quality!r}) — "
                    "quadrants computed from a non-current proxy must carry that quality "
                    "flag (spec §2)")

    # S3(d): health.publication_state must equal the top-level publication_state — the two
    # are supposed to be the identical number by construction (build_v2 computes health
    # AFTER publication_state, from the same pub_state value), but nothing enforced that
    # machine/UI agreement until now.
    health = desk.get("health")
    if isinstance(health, dict) and health.get("publication_state") != pub_state:
        raise ContractError(
            f"health.publication_state {health.get('publication_state')!r} != top-level "
            f"publication_state {pub_state!r} — the two must always agree (W2_SPEC.md §2)")
