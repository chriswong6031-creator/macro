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

# provisional (W5 calibrates) thresholds — spec §1.2
REL_THRESH = 0.5                                  # ±0.5σ velocity
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


def rel_field(value: float | None, *, reference_window: int = 126) -> dict[str, Any]:
    return {"value": value, "unit": "sigma", "direction": rel_direction(value),
            "reference_window": reference_window}


def enrich_group(abs_value: float | None, rel_value: float | None, *,
                  abs_unit: str = "pct_rate", abs_period: str = "20d",
                  reference_window: int = 126) -> dict[str, Any]:
    """The additive ``{abs, rel, quadrant, quadrant_en, quadrant_zh}`` block for one
    group/aggregate row — the anti-conflation device every W1 gate hinges on."""
    a = abs_field(abs_value, period=abs_period, unit=abs_unit)
    r = rel_field(rel_value, reference_window=reference_window)
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
                 abs_unit: str = "pct_rate") -> dict[str, dict[str, int]]:
    """absolute_breadth / relative_breadth / acceleration_breadth, each declaring its own
    denominator = scored + unscored (§4 law: every cross-sectional statistic declares
    denominator + coverage). ``unscored`` folds the previously-silent kin-None drops into
    ``missing`` rather than letting them vanish from the count entirely."""
    denom = len(rows) + unscored
    abs_c = {"positive": 0, "negative": 0, "neutral": 0, "missing": unscored, "denominator": denom}
    rel_c = {"positive": 0, "negative": 0, "neutral": 0, "missing": unscored, "denominator": denom}
    accel_c = {"strengthening": 0, "cooling": 0, "easing": 0, "worsening": 0,
               NEUTRAL_OR_UNKNOWN: unscored, "denominator": denom}
    for r in rows:
        ad = direction_from_value(r.get(abs_key), abs_unit)
        abs_c["missing" if ad == "unknown" else ad] += 1
        rd = rel_direction(r.get(rel_key))
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
    "historical": ("historical only — ended {date}", "仅历史 · 止于{date}"),
    "unavailable": ("unavailable", "不可用"),
}

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


def leg_ui_state(effective_date: str | None, newest_session: str | None, *,
                  status: str | None = None, expected_lag_days: int = 0) -> str:
    """current | expected_lag | behind | historical | unavailable — a leg's own
    effective_date vs the desk's newest session (spec §2.2). ``expected_lag_days`` is the
    leg's OWN normal cadence (hk_sb_holdings = 1, "expected T-1" is HEALTHY there, not
    degraded — §5). ``unavailable`` (S7) is a leg with no usable effective_date at all —
    its panel did not build this run — distinct from ``behind`` (built, but past budget)."""
    if status == "HISTORICAL_ONLY":
        return "historical"
    ed = _parse_date(effective_date)
    if ed is None:
        return "unavailable"
    ns = _parse_date(newest_session)
    if ns is None:
        return "unavailable"
    gap = (ns - ed).days
    if gap <= 0:
        return "current"
    if expected_lag_days and gap <= expected_lag_days:
        return "expected_lag"
    return "behind"


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
                 status: str | None = None, source_kind: str = "", first_known_at=None,
                 newest_session: str | None = None, expected_lag_days: int = 0) -> dict[str, Any]:
    meta = SOURCE_META.get(source_id, {})
    ui_state = leg_ui_state(effective_date, newest_session, status=status,
                            expected_lag_days=expected_lag_days)
    word_en, word_zh = _STATE_WORDS.get(ui_state, _STATE_WORDS["behind"])
    date_str = effective_date or "—"
    return {
        "source_id": source_id, "source_kind": source_kind, "provider": provider,
        "market": market, "effective_date": effective_date,
        "expected_availability": expected_availability, "coverage": coverage,
        "first_known_at": first_known_at, "status": status,
        "ui_state": ui_state,
        "name_en": meta.get("name_en", source_id), "name_zh": meta.get("name_zh", source_id),
        "tip_en": meta.get("tip_en", ""), "tip_zh": meta.get("tip_zh", ""),
        "coverage_line": _coverage_line(coverage),
        "state_word_en": word_en.format(date=date_str), "state_word_zh": word_zh.format(date=date_str),
    }


def build_sources(snap: dict[str, Any], *, newest_session: str | None,
                  seats_as_of: str | None = None) -> list[dict[str, Any]]:
    """One block per masterplan §3 leg — ALWAYS all five W1 legs (S7 repair): a leg whose
    panel did not build this run still gets its identity row so the trust strip shows
    "unavailable — not zero flow" rather than a silent hole (masterplan §5 publication
    law). ``sw_l1_sectors`` stays out of scope entirely (W4 — the engine has no panel for
    it at all yet; see the SOURCE_META docstring above for why fabricating one would
    itself violate the honesty gate this module exists to enforce).

    W1 = identity/dates/coverage only; W2 adds the HEALTHY/DEGRADED/... status machine on
    top of ``status``, which W1 leaves ``null`` except the HISTORICAL_ONLY northbound leg
    (never faked).

    HK-market legs (S8): ``sb_aggregate``/``hk_sb_holdings`` anchor their freshness gap
    against the newest HK-family date (sb_aggregate's own effective_date) rather than the
    CN ``market_session`` — the two calendars are not the same trading calendar, so
    comparing an HK leg's date against a CN close date can manufacture a false gap/false
    currency on days the two markets' sessions diverge. CN legs keep the CN anchor.
    """
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

    legs: list[dict[str, Any]] = []

    n_obs = names.get("n")
    n_unscored = names.get("n_unscored") or 0
    total = (n_obs or 0) + n_unscored
    pct = round(100.0 * n_obs / total, 1) if (names_asof and n_obs is not None and total) else None
    legs.append(_source_leg(
        "cn_large_order_proxy", source_kind="large_order_size_proxy",
        provider="Tushare moneyflow_dc", market="CN", effective_date=names_asof,
        expected_availability="T+0 after CN close",
        coverage={"n_observed": n_obs if names_asof else None, "n_sized": None, "pct_names": pct},
        newest_session=newest_session))

    legs.append(_source_leg(
        "sb_aggregate", source_kind="official_connect_aggregate",
        provider="Eastmoney RPT_MUTUAL_DEAL_HISTORY", market="HK",
        effective_date=sb.get("as_of") if sb_live else None,
        expected_availability="T+0 after HK close",
        coverage={"n_observed": 1, "n_sized": None, "pct_names": None} if sb_live
                  else {"n_observed": None, "n_sized": None, "pct_names": None},
        newest_session=hk_anchor))

    legs.append(_source_leg(
        "hk_sb_holdings", source_kind="official_connect_holdings",
        provider="Eastmoney RPT_MUTUAL_STOCK_HOLDRANKS", market="HK",
        effective_date=hk.get("as_of"), expected_availability="expected T−1",
        coverage={"n_observed": hk.get("n"), "n_sized": hk.get("n_sized"), "pct_names": None}
                  if hk else {"n_observed": None, "n_sized": None, "pct_names": None},
        newest_session=hk_anchor, expected_lag_days=1))

    legs.append(_source_leg(
        "nb_aggregate", source_kind="official_connect_aggregate",
        provider="Eastmoney (discontinued disclosure)", market="CN",
        effective_date=nb.get("frozen_since") if nb else None,
        expected_availability=(f"discontinued {nb.get('frozen_since')}" if nb and nb.get("frozen_since")
                               else "discontinued"),
        coverage={"n_observed": None, "n_sized": None, "pct_names": None},
        status="HISTORICAL_ONLY" if nb else None, newest_session=newest_session))

    legs.append(_source_leg(
        "lhb_inst_seats", source_kind="event_selected_institution_seat",
        provider="Eastmoney 龙虎榜 机构专用", market="CN",
        effective_date=seats_as_of if seats else None, expected_availability="event-window",
        coverage={"n_observed": len(seats), "n_sized": None, "pct_names": None}
                  if seats else {"n_observed": None, "n_sized": None, "pct_names": None},
        newest_session=newest_session))

    return legs


# ── build_v2 assembly (spec §1.7) ──────────────────────────────────────────────────
def build_v2(snap: dict[str, Any], *, log_rows: list[dict[str, Any]] | None = None,
            market_session: str | None = None, generated_at: str | None = None,
            seats_as_of: str | None = None,
            state_history=None) -> dict[str, Any]:
    """Merge the W1 ``flow_observatory.v2`` additive fields into the existing desk payload.

    Pure assembly — no I/O. ``log_rows`` is the already-read ``state_log.jsonl`` content
    (pass ``[]``/``None`` when unavailable — history fields degrade to honest nulls, never
    a fabricated zero). ``state_history`` is an injectable ``changes.theme_state_history``
    callable (defaults to importing :mod:`engine.flow_observatory.changes` lazily, keeping
    this module import-cycle-free for tests that only need the pure math).
    """
    log_rows = log_rows or []
    market_session = market_session or snap.get("as_of")
    if state_history is None:
        from engine.flow_observatory.changes import theme_state_history as state_history

    out: dict[str, Any] = dict(snap)
    out["schema"] = SCHEMA
    out["authority"] = AUTHORITY
    out["generated_at"] = generated_at
    out["market_session"] = market_session

    # §1.3 — per-row abs/rel/quadrant/rank/rank_change/state_* on ashare_sectors.rows[]
    sectors = snap.get("ashare_sectors")
    enriched_rows: list[dict[str, Any]] = []
    if sectors and sectors.get("rows"):
        for row in sectors["rows"]:
            row = dict(row)
            row.update(enrich_group(row.get("rate_4wk"), row.get("vel"),
                                    abs_unit="pct_rate", abs_period="20d", reference_window=126))
            enriched_rows.append(row)
        assign_ranks(enriched_rows)
        prev_ranks = _previous_ranks(log_rows, market_session)
        for row in enriched_rows:
            hist = (state_history(row["id"], row["quadrant"], log_rows, market_session)
                    if market_session else
                    {"state_started": None, "state_age_sessions": None, "prior_state": None,
                     "note": "first tracked session"})
            row["state_started"] = hist["state_started"]
            row["state_age_sessions"] = hist["state_age_sessions"]
            row["prior_state"] = hist["prior_state"]
            row["state_note"] = hist["note"]
            prev_rank = prev_ranks.get(row["id"]) if prev_ranks is not None else None
            row["rank_change"] = (row["rank"] - prev_rank) \
                if (prev_ranks is not None and row["rank"] is not None and prev_rank is not None) \
                else None
        out["ashare_sectors"] = {**sectors, "rows": enriched_rows}

    # southbound aggregate — the SAME abs+rel+quadrant treatment (spec §1.3 last line)
    agg = snap.get("aggregate")
    if agg:
        new_agg = []
        for chan in agg:
            chan = dict(chan)
            if chan.get("key") == "southbound" and chan.get("live"):
                chan.update(enrich_group(chan.get("flow_1m_b"), chan.get("vel_primary"),
                                         abs_unit="cny_b", abs_period="1m", reference_window=126))
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
    themes_mr = market_read(enriched_rows, unscored=themes_unscored)
    names_mr = names.get("market_read") or market_read([], names.get("n_unscored") or 0)
    out["market_read"] = {"themes": themes_mr, "names": names_mr}

    # §1.5 — sources[]
    out["sources"] = build_sources(snap, newest_session=market_session, seats_as_of=seats_as_of)

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
    """
    mr = desk.get("market_read") or {}
    for lens_name, lens in mr.items():
        if not isinstance(lens, dict):
            raise ContractError(f"market_read.{lens_name} is not a breadth object")
        for breadth_name, breadth in lens.items():
            if "denominator" not in (breadth or {}):
                raise ContractError(f"market_read.{lens_name}.{breadth_name} missing denominator")

    for row in (desk.get("ashare_sectors") or {}).get("rows") or []:
        a, r, q = row.get("abs"), row.get("rel"), row.get("quadrant")
        if a is None or r is None or q is None:
            continue
        av, ad = a.get("value"), a.get("direction")
        expected_ad = direction_from_value(av, a.get("unit"))
        if expected_ad != ad:
            raise ContractError(
                f"row {row.get('id')}: abs.direction {ad!r} disagrees with abs.value {av!r} "
                f"(expected {expected_ad!r})")
        rv, rd = r.get("value"), r.get("direction")
        expected_rd = rel_direction(rv)
        if expected_rd != rd:
            raise ContractError(
                f"row {row.get('id')}: rel.direction {rd!r} disagrees with rel.value {rv!r} "
                f"(expected {expected_rd!r})")
        expected_q = quadrant(ad, rd)
        if expected_q != q:
            raise ContractError(
                f"row {row.get('id')}: quadrant {q!r} inconsistent with abs={ad!r} rel={rd!r} "
                f"(expected {expected_q!r})")

    generated_at = desk.get("generated_at")
    for s in desk.get("sources") or []:
        ed = s.get("effective_date")
        if not ed:
            continue
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
