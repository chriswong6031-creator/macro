"""US Prophet v1 — board priority score, stage buckets, featured flag, theme linkage.

Architecture mirrors :mod:`engine.china_board_rank` (``cn_prophet_v2``): frozen
constants, pure functions, an artifact-disclosed ``ranking`` block, and no pandas
dependency in the scoring path.  The score is a **transparent priority heuristic,
not a calibrated return forecast** — it orders names that the confluence admission
gate has already admitted; it never decides who is on the board.

Three US-specific departures from the CN module are deliberate and evidenced:

1. ``edge`` (25 pts) replaces CN's ``reversal_member`` leg and is the **residual-alpha
   percentile inside the current buy pool**.  ``research/US_BOARD_MEASUREMENT.md``
   measured residual alpha as the only positive-IC leg at every horizon (§3), while
   the *published* board order — which was conviction/``composite_z`` ordering — was
   anti-predictive at the top (P@1 0.20 as published vs 0.60 re-ordered by alpha;
   ``corr(board_position, excess_5d) = +0.07``; top-5 lift −13.7 points vs the board's
   own base rate, §1).  Its ruling is "order by edge, gate by timing, never the
   reverse".  Accordingly **conviction / composite_z carry ZERO score authority here**
   (see :data:`ZERO_SCORE_AUTHORITY`) and the percentile is transformed
   ``clip01((pctile − 0.25) / 0.75)`` so the bottom quartile of alpha earns nothing.
2. ``runway`` (10 pts) reads the own-history extension z (``ext_z``) rather than CN's
   fuel/extension blend, because that is the extension evidence the US builder
   attaches to a board row.
3. Timing decides **grouping** (the stage bucket), never the within-bucket order —
   the same measurement found the timing leg net-negative to sort by (§3, Study 2).

Nothing outside :data:`SCORE_WEIGHTS` may add points.  Theme membership, sector turn,
narrative, the legacy setup score, fundamental quality, low volatility, risk sizing,
smart money, insider prints, SUE, and options/GEX are **context chips only**.

Fail-closed rule, inherited from CN: unknown evidence never earns best-case points.
A row with no extension reading scores 0 on ``runway`` (it is not assumed "not
extended"); a row with an unknown entry status buckets to ``setting_up``, never to
``live``.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


BOARD_DEFINITION = "us_prophet_v1"

FEATURED_CAP = 12
SECTOR_CAP = 4
RAN_CAP = 12
RAN_TICKS_MIN = 3
RAN_TICKS_MAX = 15

# ext_z at or above this is fully extended (mirrors engine.extension.PARABOLIC_Z —
# do not tune here).  ext_z <= 0 is "not extended"; the leg is linear between.
EXT_Z_FULL = 2.0

# Featured freshness window (mirrors engine.confluence_tiers.FRESH_TICKS).
FEATURED_MAX_TICKS = 2

# Theme linkage (display-tier context; zero score authority).
THEME_TOP_N = 8
THEME_IN_FAVOUR_RECOS = frozenset(("accumulate", "enter"))
# A theme whose bull run is this young "only just confirmed" — the sector-clock /
# stock-clock desync case (a name's cross looks stale while its theme just turned).
THEME_CONFIRMED_MAX_BULL_DAYS = 7
# GICS pseudo-baskets: the card already prints the sector, so a sector chip is noise.
THEME_ID_EXCLUDE_PREFIX = "us_sector_"

SCORE_WEIGHTS = {
    "signal": 30.0,
    "entry": 25.0,
    "edge": 25.0,
    "runway": 10.0,
    "quality": 10.0,
}

# Frozen definition inputs, not fitted coefficients.  Shared verbatim with
# engine.china_board_rank — the tier cascade and entry-status vocabularies are
# market-independent, so the two boards speak one scoring language.
_SIGNAL_BASE = {"T2": 1.0, "T1": 0.9, "T3": 0.7}
_ENTRY_VALUE = {
    "buy_now": 1.0,
    "partial": 0.9,
    "buy_soon": 0.8,
    "hold": 0.65,
    "wait_pullback": 0.55,
    "later": 0.55,
    "await": 0.45,
    "await_confluence": 0.45,
    "watch": 0.4,
    "bounce_wait": 0.35,
    "extended": 0.0,
    "topping": 0.0,
    "blocked": 0.0,
    "exit": 0.0,
    "avoid": 0.0,
}

# Stage buckets — timing is the WHEN-gate and owns grouping, never order.
STAGE_LIVE = "live"
STAGE_SETTING_UP = "setting_up"
STAGE_RAN = "ran"
STAGE_BLOCKED = "blocked"
STAGE_ORDER = (STAGE_LIVE, STAGE_SETTING_UP, STAGE_RAN, STAGE_BLOCKED)
_STAGE_RANK = {name: index for index, name in enumerate(STAGE_ORDER)}

_LIVE_STATUSES = frozenset(("buy_now", "partial", "buy_soon"))
_SETTING_UP_STATUSES = frozenset(("await_confluence", "bounce_wait", "watch"))
_RAN_STATUSES = frozenset(("extended", "topping", "hold"))
_BLOCKED_STATUSES = frozenset(("blocked", "exit", "avoid"))

STAGE_LABELS = {
    STAGE_LIVE: {"en": "Live now", "zh": "现在可操作"},
    STAGE_SETTING_UP: {"en": "Setting up", "zh": "形成中"},
    STAGE_RAN: {"en": "Ran — don't chase", "zh": "已启动 — 勿追"},
    STAGE_BLOCKED: {"en": "Blocked", "zh": "受阻"},
}

_FEATURED_ENTRY_STATUSES = frozenset(("buy_now", "partial"))
_FEATURED_TIERS = frozenset(("T1", "T2", "T3"))

ZERO_SCORE_AUTHORITY = (
    "conviction_composite",
    "setup",
    "sector_turn",
    "narrative",
    "quality_factor",
    "low_vol",
    "risk_sizing",
    "smartmoney",
    "insider",
    "sue",
    "options_gex",
    "theme",
)

SCORE_KIND = "transparent priority heuristic; not a calibrated return forecast"


# --------------------------------------------------------------------------- #
# small pure helpers
# --------------------------------------------------------------------------- #
def _clip01(value: Any) -> float:
    """Return a finite float clipped to ``[0, 1]``; malformed values become zero."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, min(1.0, number))


def _finite_float(value: Any) -> float | None:
    """Return ``value`` as a finite float, or ``None`` (NaN/inf/garbage all fail)."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _finite_int(value: Any) -> int | None:
    """Integer coercion that keeps ``0`` — a same-day cross is the FRESHEST signal.

    ``ticks``, ``bars_to_cross`` and ``days_since_signal`` are all legitimately ``0``.
    Every caller must therefore test ``is not None`` rather than truthiness; writing
    ``(v.get("ticks") or 99) <= 2`` silently un-features exactly the freshest rows.
    """
    number = _finite_float(value)
    return int(number) if number is not None else None


def _as_date(value: Any) -> str | None:
    """Normalise common date values without making the ranking depend on pandas."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text[:10] if len(text) >= 10 else (text or None)


def _status_of(entry: Mapping[str, Any] | None) -> str:
    return str((entry or {}).get("status") or "").strip().lower()


def _notice(title: str, message: str) -> None:
    """Emit a GitHub Actions notice.

    A bare ``print`` with ``flush=True`` is load-bearing (house law): every builder
    here logs through a prefixing formatter, so ``log.info("::notice ...")`` emits
    ``INFO ::notice ...`` and GitHub silently drops the annotation.  stdout is
    block-buffered when piped in CI, hence the flush.
    """
    print(f"::notice title={title}::{message}", flush=True)


# --------------------------------------------------------------------------- #
# score legs
# --------------------------------------------------------------------------- #
def signal_value(verdict: Mapping[str, Any] | None) -> float:
    """Confluence-tier freshness value in ``[0, 1]`` (CN's frozen map).

    Base ``{T2: 1.0, T1: 0.9, T3: 0.7}`` (the operator re-ranked T2 above T1 on
    2026-07-06); a provisional verdict loses 0.1; a cross that is 2 ticks old is
    decayed 15%.  Any other tier — including ``T4`` and a cleared ``None`` — is 0.
    """
    verdict = verdict or {}
    value = _SIGNAL_BASE.get(str(verdict.get("tier_cascade")), 0.0)
    if verdict.get("provisional"):
        value = max(0.0, value - 0.1)
    ticks = _finite_int(verdict.get("ticks"))
    if ticks is not None and ticks == 2:
        value *= 0.85
    return _clip01(value)


def entry_value(entry: Mapping[str, Any] | None) -> float:
    """Entry-window value in ``[0, 1]`` — CN's ``_ENTRY_VALUE`` map verbatim."""
    return _ENTRY_VALUE.get(_status_of(entry), 0.0)


def alpha_percentiles(rows: Sequence[Mapping[str, Any]]) -> dict[int, float | None]:
    """Row-index → residual-alpha percentile inside the supplied pool.

    Rank 1 is the highest alpha; percentile 1.0 is the top of the pool and 0.0 the
    bottom.  Ties break on ticker so the percentile is reproducible for identical
    inputs.  Rows with no finite ``alpha`` are excluded from the pool (they neither
    occupy a rank nor distort the spread) and map to ``None`` — the fail-closed
    outcome is zero points, not a mid-pool default.
    """
    ranked: list[tuple[int, str, float]] = []
    for index, row in enumerate(rows):
        alpha = _finite_float(row.get("alpha"))
        if alpha is None:
            continue
        ranked.append((index, str(row.get("ticker") or ""), alpha))

    out: dict[int, float | None] = {index: None for index in range(len(rows))}
    if not ranked:
        return out
    ranked.sort(key=lambda item: (-item[2], item[1]))
    count = len(ranked)
    for rank, (index, _ticker, _alpha) in enumerate(ranked, start=1):
        percentile = 1.0 if count == 1 else 1.0 - (rank - 1) / (count - 1)
        out[index] = round(_clip01(percentile), 6)
    return out


def edge_value(percentile: float | None) -> float:
    """Transform an alpha percentile so the bottom quartile of the pool earns zero.

    ``clip01((pctile − 0.25) / 0.75)``.  The measurement found the alpha edge real but
    tail-concentrated — a floor that deletes the bottom quartile, not a fine ranker.
    """
    if percentile is None:
        return 0.0
    return _clip01((_clip01(percentile) - 0.25) / 0.75)


def runway_value(row: Mapping[str, Any]) -> float:
    """Room-to-run value in ``[0, 1]`` = ``1 − extension``.

    ``ext_z >= EXT_Z_FULL`` is fully extended (0 runway), ``ext_z <= 0`` is not
    extended (full runway), linear in between; an ``antichase_shadow_blocked`` row is
    treated as fully extended.  **Unknown extension evidence earns 0**, never the
    best case — CN's fail-closed rule.  On the current US builder ``ext_z`` reaches
    very few board rows, so this leg is usually a constant 0 across the pool: it
    costs every row the same 10 points and therefore does not distort the order.
    """
    if row.get("antichase_shadow_blocked") is True:
        return 0.0
    ext_z = _finite_float(row.get("ext_z"))
    if ext_z is None:
        return 0.0
    return _clip01(1.0 - _clip01(ext_z / EXT_Z_FULL))


def quality_value(row: Mapping[str, Any]) -> float:
    """Bottom-quality value in ``[0, 1]`` — CN's ``_bottom_quality_value`` logic."""
    coiled = row.get("coiled") or {}
    if coiled.get("star"):
        return 1.0
    if coiled.get("coiled"):
        return 0.8
    if coiled.get("washout_ctx") or row.get("washout_ctx"):
        return 0.4
    return 0.0


# --------------------------------------------------------------------------- #
# stage bucketing
# --------------------------------------------------------------------------- #
def stage_for(row: Mapping[str, Any], entry: Mapping[str, Any] | None = None) -> str:
    """Bucket a row into ``live`` / ``setting_up`` / ``ran`` / ``blocked``.

    Blocked wins over everything: an ``avoid``/``exit``/``blocked`` entry status, or a
    downtrending name (``dir == "down"``) that carries no entry status at all, must
    never render above an actionable row.  A missing or unrecognised status buckets to
    ``setting_up`` — an unknown timing state is never advertised as live.
    """
    status = _status_of(entry if entry is not None else row.get("entry_signal"))
    if status in _BLOCKED_STATUSES:
        return STAGE_BLOCKED
    if not status and str(row.get("dir") or "").strip().lower() == "down":
        return STAGE_BLOCKED
    if status in _LIVE_STATUSES:
        return STAGE_LIVE
    if status in _RAN_STATUSES:
        return STAGE_RAN
    if status in _SETTING_UP_STATUSES:
        return STAGE_SETTING_UP
    return STAGE_SETTING_UP


def stage_rank(stage: str) -> int:
    """Sort position of a stage bucket (unknown stages sort last, deterministically)."""
    return _STAGE_RANK.get(stage, len(STAGE_ORDER))


# --------------------------------------------------------------------------- #
# freshness
# --------------------------------------------------------------------------- #
def signal_asof(row: Mapping[str, Any], verdict: Mapping[str, Any] | None = None) -> str | None:
    """The signal's own session date (verdict first, then the row's compact signal)."""
    if verdict:
        stamped = _as_date(verdict.get("asof"))
        if stamped:
            return stamped
    return _as_date((row.get("signal") or {}).get("asof"))


def days_since_signal(sig_asof: Any, board_asof: Any) -> int | None:
    """Calendar days between the signal session and the board session.

    ``0`` means the signal fired on the board's own session — the freshest possible
    value, and the reason every consumer must test ``is not None`` before comparing.
    Returns ``None`` when either date is unknown or unparseable.  A negative value is
    returned as-is rather than clamped: a signal stamped after the board session is a
    data fault that should stay visible.
    """
    left = _as_date(sig_asof)
    right = _as_date(board_asof)
    if not left or not right:
        return None
    try:
        return (date.fromisoformat(right) - date.fromisoformat(left)).days
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# featured
# --------------------------------------------------------------------------- #
def featured_shortfalls(
    row: Mapping[str, Any],
    *,
    verdict: Mapping[str, Any] | None = None,
    entry: Mapping[str, Any] | None = None,
    in_blackout: bool | None = None,
) -> list[str]:
    """Every reason this row may not be featured (empty list = it qualifies).

    Featured is a **flag plus an order**, never a population change: a row that fails
    here stays on the buy lane exactly where its stage and score put it.
    """
    reasons: list[str] = []
    verdict = verdict if verdict is not None else (row.get("signal") or {})
    entry = entry if entry is not None else (row.get("entry_signal") or {})

    if stage_for(row, entry) != STAGE_LIVE:
        reasons.append("stage_not_live")
    status = _status_of(entry)
    if status not in _FEATURED_ENTRY_STATUSES:
        reasons.append(f"entry_status_{status or 'unknown'}")

    tier = str(verdict.get("tier_cascade") or "")
    if tier not in _FEATURED_TIERS:
        reasons.append(f"tier_{tier or 'unknown'}")

    # ticks == 0 is a same-day cross — the best case.  Explicit None check, never
    # `or`: truthiness would reject 0 and un-feature the freshest rows on the board.
    ticks = _finite_int(verdict.get("ticks"))
    if ticks is None:
        reasons.append("ticks_unknown")
    elif ticks > FEATURED_MAX_TICKS:
        reasons.append("ticks_stale")

    if verdict.get("provisional"):
        reasons.append("provisional")

    if row.get("antichase_shadow_blocked") is True:
        reasons.append("antichase_blocked")

    ext_z = _finite_float(row.get("ext_z"))
    if ext_z is not None and ext_z > EXT_Z_FULL:
        reasons.append("extended")

    alpha = _finite_float(row.get("alpha"))
    if alpha is None:
        reasons.append("alpha_unknown")
    elif alpha < 0:
        reasons.append("alpha_below_floor")

    blackout = in_blackout
    if blackout is None:
        blackout = (row.get("earnings_soon") or {}).get("in_blackout")
    if blackout is True:
        reasons.append("earnings_blackout")

    return reasons


# --------------------------------------------------------------------------- #
# the scoring pass
# --------------------------------------------------------------------------- #
def score_rows(
    rows: Iterable[dict],
    *,
    verdict_by: Mapping[str, Mapping[str, Any]] | None = None,
    entry_by: Mapping[str, Mapping[str, Any]] | None = None,
    blackout_by: Mapping[str, bool] | None = None,
    board_asof: Any = None,
    featured_cap: int = FEATURED_CAP,
    sector_cap: int = SECTOR_CAP,
) -> list[dict]:
    """Score, stage, feature and order a buy pool.

    Rows are stamped **in place** and returned in board order — the US builder shares
    one row object across lanes and enrichment passes, so copying here would strand
    every later mutation.  Membership is untouched: this function adds fields and
    decides ORDER, never who is on the board.

    Sort key: ``(stage_rank, −score, ticker)``.  ``score_rank`` is the pool rank by
    that key and ``display_rank`` the rendered position; today they are equal, and
    they are kept separate so a future lane split cannot silently conflate them.
    """
    pool = list(rows)
    board_date = _as_date(board_asof)
    percentiles = alpha_percentiles(pool)

    for index, row in enumerate(pool):
        ticker = str(row.get("ticker") or "")
        verdict = (verdict_by or {}).get(ticker) or row.get("signal") or {}
        entry = (entry_by or {}).get(ticker) or row.get("entry_signal") or {}

        values = {
            "signal": signal_value(verdict),
            "entry": entry_value(entry),
            "edge": edge_value(percentiles.get(index)),
            "runway": runway_value(row),
            "quality": quality_value(row),
        }
        points = {
            name: round(SCORE_WEIGHTS[name] * value, 4)
            for name, value in values.items()
        }
        score = max(0.0, min(100.0, sum(points.values())))

        row["stage"] = stage_for(row, entry)
        row["prophet"] = {
            "version": BOARD_DEFINITION,
            "score": round(score, 1),
            "components": {name: round(value, 6) for name, value in values.items()},
            "points": points,
            "alpha_percentile": percentiles.get(index),
            "zero_score_authority": list(ZERO_SCORE_AUTHORITY),
        }
        # No top-level ``score`` key: rows already carry ``alpha``, ``setup`` and the
        # conviction score legs, and a fourth bare "score" would be unreadable.
        # ``prophet.score`` is the display/sort authority; the legacy fields stay.
        sig_date = signal_asof(row, verdict)
        row["signal_asof"] = sig_date
        row["days_since_signal"] = days_since_signal(sig_date, board_date)
        row["new"] = bool(sig_date and board_date and sig_date == board_date)

        shortfalls = featured_shortfalls(
            row,
            verdict=verdict,
            entry=entry,
            in_blackout=(blackout_by or {}).get(ticker),
        )
        row["_featured_shortfalls"] = shortfalls
        row["featured"] = False

    pool.sort(
        key=lambda row: (
            stage_rank(str(row.get("stage") or "")),
            -float((row.get("prophet") or {}).get("score") or 0.0),
            str(row.get("ticker") or ""),
        )
    )

    featured_n = 0
    sector_counts: dict[str, int] = defaultdict(int)
    for rank, row in enumerate(pool, start=1):
        row["score_rank"] = rank
        row["display_rank"] = rank
        shortfalls = row.pop("_featured_shortfalls", ["not_evaluated"])
        if shortfalls:
            row["featured_blocked_by"] = shortfalls
            continue
        sector = str(row.get("sector") or "—")
        if featured_n >= max(0, int(featured_cap)):
            row["featured_blocked_by"] = ["featured_cap"]
        elif sector_counts[sector] >= max(0, int(sector_cap)):
            row["featured_blocked_by"] = ["sector_cap"]
        else:
            featured_n += 1
            sector_counts[sector] += 1
            row["featured"] = True
            row.pop("featured_blocked_by", None)
    return pool


def stage_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Per-stage row counts, every bucket present (a zero is a fact, not an absence)."""
    counts = {stage: 0 for stage in STAGE_ORDER}
    for row in rows:
        stage = str(row.get("stage") or "")
        if stage in counts:
            counts[stage] += 1
    return counts


def ranking_block(
    rows: Iterable[Mapping[str, Any]],
    *,
    featured_cap: int = FEATURED_CAP,
    sector_cap: int = SECTOR_CAP,
    theme_asof: Any = None,
) -> dict[str, Any]:
    """The artifact-disclosed ``ranking`` block — the score's own receipt.

    Everything a reader needs to reproduce the order is printed here: the weights,
    what each leg reads, the featured requirements, and the explicit list of inputs
    that carry no score authority at all.
    """
    scored = list(rows)
    counts = stage_counts(scored)
    return {
        "definition": BOARD_DEFINITION,
        "score_kind": SCORE_KIND,
        "weights": dict(SCORE_WEIGHTS),
        "formula_points": [
            {"component": "signal", "points": SCORE_WEIGHTS["signal"],
             "reads": "confluence tier + freshness",
             "basis": "tier base T2 1.0 / T1 0.9 / T3 0.7; provisional −0.1; "
                      "cross 2 ticks old ×0.85"},
            {"component": "entry", "points": SCORE_WEIGHTS["entry"],
             "reads": "entry_signal.status",
             "basis": "frozen status map, shared with the China board"},
            {"component": "edge", "points": SCORE_WEIGHTS["edge"],
             "reads": "residual alpha percentile inside this buy pool",
             "basis": "clip01((pctile − 0.25) / 0.75) — bottom quartile earns 0"},
            {"component": "runway", "points": SCORE_WEIGHTS["runway"],
             "reads": "own-history extension z (ext_z) / anti-chase flag",
             "basis": "1 − clip01(ext_z / 2.0); unknown extension earns 0"},
            {"component": "quality", "points": SCORE_WEIGHTS["quality"],
             "reads": "coiled / washout context",
             "basis": "coiled star 1.0 · coiled 0.8 · washout context 0.4"},
        ],
        "sort_key": "stage bucket, then priority score desc, then ticker",
        "stage_order": list(STAGE_ORDER),
        "stage_labels": {stage: dict(STAGE_LABELS[stage]) for stage in STAGE_ORDER},
        "stage_counts": counts,
        "featured_cap": max(0, int(featured_cap)),
        "sector_cap": max(0, int(sector_cap)),
        "featured_count": sum(1 for row in scored if row.get("featured")),
        "featured_requirements": [
            "stage is live",
            "entry status is buy_now or partial",
            "confluence tier T1, T2 or T3",
            f"cross no older than {FEATURED_MAX_TICKS} ticks (a same-day cross, "
            "ticks 0, qualifies)",
            "verdict not provisional",
            "no anti-chase flag and no extension block",
            "residual alpha at or above zero",
            "outside the earnings blackout window",
            f"at most {int(sector_cap)} per sector, {int(featured_cap)} on the board",
        ],
        "zero_score_authority": list(ZERO_SCORE_AUTHORITY),
        "membership_note": "featured is a flag and an order — the buy lane's "
                           "membership is decided by the confluence admission gate "
                           "alone and is unchanged by this ranking",
        "theme_asof": _as_date(theme_asof),
    }


# --------------------------------------------------------------------------- #
# total-return momentum (the leaders lane's rank key)
# --------------------------------------------------------------------------- #
LEADERS_MOMENTUM_SESSIONS = 63    # ~3 months — the lane's own chartered window


def total_return_z(
    closes_by: Mapping[str, Sequence[Any]],
    *,
    sessions: int = LEADERS_MOMENTUM_SESSIONS,
) -> dict[str, float]:
    """Cross-sectional z-score of trailing TOTAL return over ``sessions`` sessions.

    This is the leaders lane's rank key, and it is deliberately NOT residual alpha
    and NOT the composite's ``momentum`` leg. Measured 2026-08-02 on the live board:
    ``corr(alpha, composite.legs.momentum) = 0.984`` — that leg is fed by
    ``alpha_pt[t]["alpha"]`` (scripts/build_stock_library.py, composite assembly), so
    ranking by it would be the residual-alpha rule under a new name, and the software
    cohort would stay invisible exactly as before. Trailing total return over the same
    universe correlates ``+0.37`` with residual alpha — a different quantity, which is
    the whole point: residual strips beta, and a theme rally is mostly beta.

    Window: 63 sessions, no skip-month. The classic 12-1 academic convention is the
    wrong instrument here (measured: it puts MSFT at the 13th percentile and PLTR at
    the 15th while the software theme was leading, because it deletes precisely the
    recent leg that names current leadership). 63 sessions is also this lane's own
    chartered universe — it was created on the 2026-07-28 finding that "of the top-100
    3-month runners, 2 passed the confluence gate".

    ``closes_by`` maps ticker to an oldest-first close sequence; only the last
    ``sessions + 1`` values are read, so callers should pass a tail, not a history.
    Names with too little history, a non-positive base price, or a degenerate
    cross-section are omitted — an absent reading is a skipped row, never a zero.
    """
    window = max(1, int(sessions))
    returns: dict[str, float] = {}
    for ticker, closes in (closes_by or {}).items():
        values = [v for v in (_finite_float(c) for c in (closes or [])) if v is not None]
        if len(values) < window + 1:
            continue
        base = values[-(window + 1)]
        if base <= 0:
            continue
        returns[str(ticker)] = values[-1] / base - 1.0

    if len(returns) < 2:
        return {}
    mean = sum(returns.values()) / len(returns)
    variance = sum((v - mean) ** 2 for v in returns.values()) / len(returns)
    sd = math.sqrt(variance)
    if not math.isfinite(sd) or sd <= 0:
        return {}
    return {ticker: round((value - mean) / sd, 4) for ticker, value in returns.items()}


# --------------------------------------------------------------------------- #
# theme linkage (display-tier context chips; zero score authority)
# --------------------------------------------------------------------------- #
def _default_data_dir() -> Path:
    try:  # pragma: no cover — trivial import shim
        from lib import config as _config

        return _config.data_dir()
    except Exception:  # noqa: BLE001 — engine modules must import standalone
        return Path(__file__).resolve().parents[1] / "data"


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001 — absent/unreadable/malformed all degrade the same
        return None


def load_theme_context(
    data_dir: Path | str | None = None,
    *,
    latest_path: Path | str | None = None,
    membership_path: Path | str | None = None,
    top_n: int = THEME_TOP_N,
) -> dict[str, Any]:
    """Load the in-favour theme map from the nightly baskets engine.

    Selection: drop the ``us_sector_*`` GICS pseudo-baskets (the card already prints
    the sector), keep themes whose ``reco`` is ``accumulate`` or ``enter``, order by
    the baskets engine's own ``rank`` and take the first ``top_n``.  A ticker that
    belongs to several in-favour themes is chipped with the highest-ranked one.
    Members carrying a ``removed`` date are dropped.

    Returns ``{"as_of", "themes", "by_ticker"}``.  Fail-soft by contract: a missing or
    malformed file yields empty structures plus one ``::notice`` line — a theme chip
    is context, and its absence must never fail a build.
    """
    root = Path(data_dir) if data_dir is not None else _default_data_dir()
    latest = Path(latest_path) if latest_path is not None else root / "baskets" / "latest.json"
    membership = (
        Path(membership_path) if membership_path is not None
        else root / "baskets" / "membership.json"
    )
    empty: dict[str, Any] = {"as_of": None, "themes": [], "by_ticker": {}}

    latest_doc = _read_json(latest)
    membership_doc = _read_json(membership)
    if not isinstance(latest_doc, Mapping) or not isinstance(membership_doc, Mapping):
        _notice("us_board_theme", "baskets snapshot unreadable — board ships without "
                                  "theme chips")
        return empty

    themes_raw = latest_doc.get("themes")
    baskets = membership_doc.get("baskets")
    if not isinstance(themes_raw, list) or not isinstance(baskets, Mapping):
        _notice("us_board_theme", "baskets snapshot malformed — board ships without "
                                  "theme chips")
        return empty

    in_favour: list[dict[str, Any]] = []
    for entry in themes_raw:
        if not isinstance(entry, Mapping):
            continue
        theme_id = str(entry.get("id") or "")
        if not theme_id or theme_id.startswith(THEME_ID_EXCLUDE_PREFIX):
            continue
        reco = str(entry.get("reco") or "").strip().lower()
        if reco not in THEME_IN_FAVOUR_RECOS:
            continue
        rank = _finite_int(entry.get("rank"))
        if rank is None:
            continue
        basket = baskets.get(theme_id)
        basket = basket if isinstance(basket, Mapping) else {}
        in_favour.append({
            "id": theme_id,
            "name": basket.get("name") or entry.get("name") or theme_id,
            "name_zh": basket.get("name_zh"),
            "rank": rank,
            "reco": reco,
            "bull_days": _finite_int(entry.get("bull_days")),
            "clean_entry": bool(entry.get("clean_entry")),
        })

    in_favour.sort(key=lambda theme: (theme["rank"], theme["id"]))
    in_favour = in_favour[: max(0, int(top_n))]
    if not in_favour:
        _notice("us_board_theme", "no in-favour themes in the baskets snapshot — "
                                  "board ships without theme chips")
        return {"as_of": _as_date(latest_doc.get("as_of")), "themes": [], "by_ticker": {}}

    by_ticker: dict[str, dict[str, Any]] = {}
    tickers_by_theme: dict[str, list[str]] = {}
    for theme in in_favour:
        basket = baskets.get(theme["id"])
        members = (basket or {}).get("members") if isinstance(basket, Mapping) else None
        owned: list[str] = []
        for member in members or []:
            if not isinstance(member, Mapping):
                continue
            if member.get("removed") is not None:
                continue
            ticker = str(member.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            owned.append(ticker)
            # Highest-ranked theme wins; in_favour is already rank-ordered.
            by_ticker.setdefault(ticker, dict(theme))
        tickers_by_theme[theme["id"]] = sorted(set(owned))

    for theme in in_favour:
        theme["tickers"] = tickers_by_theme.get(theme["id"], [])

    return {
        "as_of": _as_date(latest_doc.get("as_of")),
        "themes": in_favour,
        "by_ticker": by_ticker,
    }


def load_theme_map(
    data_dir: Path | str | None = None,
    **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    """Ticker → in-favour theme chip (see :func:`load_theme_context`)."""
    return load_theme_context(data_dir, **kwargs)["by_ticker"]


def theme_confirmed(theme: Mapping[str, Any] | None) -> bool:
    """True when the chipped theme's bull run is younger than the confirm window.

    The sector-clock / stock-clock desync read: a name whose own cross fired days ago
    looks stale, while the theme it belongs to only just turned.  Display-tier context
    only — it never enters the priority score and never changes admission.
    """
    bull_days = _finite_int((theme or {}).get("bull_days"))
    return bull_days is not None and bull_days <= THEME_CONFIRMED_MAX_BULL_DAYS


def stamp_themes(
    rows: Iterable[dict],
    theme_by: Mapping[str, Mapping[str, Any]] | None,
    *,
    confirmed_flag: bool = False,
) -> int:
    """Stamp ``row["theme"]`` from the ticker map; return how many rows were chipped."""
    if not theme_by:
        return 0
    stamped = 0
    for row in rows:
        theme = theme_by.get(str(row.get("ticker") or "").strip().upper())
        if not theme:
            continue
        row["theme"] = dict(theme)
        if confirmed_flag and theme_confirmed(theme):
            row["theme_confirmed"] = True
        stamped += 1
    return stamped


# --------------------------------------------------------------------------- #
# ran lane — names whose cross already fired, trend still intact
# --------------------------------------------------------------------------- #
RAN_LABEL = "RAN"
RAN_LABEL_ZH = "已启动"
RAN_THEME_LINE = "Theme just confirmed — watch for the next entry"
RAN_THEME_LINE_ZH = "主题刚确认 — 关注下一个买点"


def ran_admits(verdict: Mapping[str, Any] | None, row: Mapping[str, Any] | None = None,
               *, ticks_min: int = RAN_TICKS_MIN, ticks_max: int = RAN_TICKS_MAX) -> bool:
    """Ran-lane admission: the cross has lapsed but the trend is provably intact.

    ``eligible is False`` (the gate no longer admits it) ∧ ``ticks`` inside the window
    ∧ ``above200`` ∧ ``weekly_bull`` ∧ the row is not marked down.  The ``is True``
    tests are deliberate: a ``None`` (unanalysed) trend must never read as intact.
    """
    verdict = verdict or {}
    if verdict.get("eligible") is not False:
        return False
    ticks = _finite_int(verdict.get("ticks"))
    if ticks is None or not (int(ticks_min) <= ticks <= int(ticks_max)):
        return False
    if verdict.get("above200") is not True or verdict.get("weekly_bull") is not True:
        return False
    if str((row or {}).get("dir") or "").strip().lower() == "down":
        return False
    return True


def cross_read(
    dates: Sequence[Any],
    closes: Sequence[Any],
    *,
    cross_date: Any = None,
    sessions_back: int | None = None,
) -> dict[str, Any] | None:
    """Move-since-the-cross read: ``{cross_date, sessions_since, pct_since}``.

    The anchor is the last session at or before ``cross_date`` when the signal's own
    marker date is known (the China ran-lane idiom, and the only exact answer); it
    falls back to ``sessions_back`` sessions before the last close otherwise.  The
    fallback is approximate on purpose: ``ticks`` are counted on the signal's native
    higher-timeframe grid (one 3D tick ≈ 3 sessions), so ``sessions_since`` is the
    field to render as "fired N sessions ago", never the raw tick count.
    """
    values: list[float] = []
    stamps: list[str | None] = []
    for stamp, close in zip(dates, closes):
        number = _finite_float(close)
        if number is None:
            continue
        values.append(number)
        stamps.append(_as_date(stamp))
    if len(values) < 2:
        return None

    anchor: int | None = None
    anchor_date = _as_date(cross_date)
    if anchor_date:
        for index in range(len(stamps) - 1, -1, -1):
            stamp = stamps[index]
            if stamp is not None and stamp <= anchor_date:
                anchor = index
                break
    if anchor is None:
        back = _finite_int(sessions_back)
        if back is None or back < 0:
            return None
        anchor = len(values) - 1 - back
        if anchor < 0:
            return None

    price_at_cross = values[anchor]
    spot = values[-1]
    if price_at_cross <= 0:
        return None
    return {
        "cross_date": stamps[anchor],
        "sessions_since": len(values) - 1 - anchor,
        "pct_since": round((spot / price_at_cross - 1.0) * 100.0, 1),
    }


def build_ran_rows(
    verdict_by: Mapping[str, Mapping[str, Any]],
    *,
    meta_by: Mapping[str, Mapping[str, Any]] | None = None,
    close_of: Callable[[str], tuple[Sequence[Any], Sequence[Any]] | None] | None = None,
    exclude: Iterable[str] = (),
    theme_by: Mapping[str, Mapping[str, Any]] | None = None,
    board_asof: Any = None,
    cap: int = RAN_CAP,
    ticks_min: int = RAN_TICKS_MIN,
    ticks_max: int = RAN_TICKS_MAX,
) -> list[dict]:
    """Build the ran lane: crossed days ago, trend intact, no entry claim attached.

    These are DISPLAY-TIER context rows.  They carry no ``entry_signal``, no
    conviction claim and no priority score — the honest read is "the move already
    started; wait for the next entry", which is why they cannot outrank a live row.

    Order: theme-confirmed rows first (their theme only just turned, so the desync is
    the point), then the freshest cross, then the largest move since it fired.
    """
    skip = {str(t or "").strip().upper() for t in exclude}
    meta_by = meta_by or {}
    rows: list[dict] = []

    for ticker, verdict in (verdict_by or {}).items():
        key = str(ticker or "").strip().upper()
        if not key or key in skip:
            continue
        meta = meta_by.get(ticker) or meta_by.get(key) or {}
        if not ran_admits(verdict, meta, ticks_min=ticks_min, ticks_max=ticks_max):
            continue

        ticks = _finite_int((verdict or {}).get("ticks"))
        series = close_of(ticker) if close_of is not None else None
        read: dict[str, Any] | None = None
        if series is not None:
            dates, closes = series
            marker = (verdict or {}).get("last") or {}
            marker_date = marker.get("date") if marker.get("type") in ("buy", "rebuy") else None
            read = cross_read(dates, closes, cross_date=marker_date, sessions_back=ticks)

        theme = (theme_by or {}).get(key)
        sig_date = signal_asof(meta, verdict)
        row: dict[str, Any] = {
            "ticker": key,
            "name": meta.get("name") or key,
            "sector": meta.get("sector"),
            "price": meta.get("price"),
            "ticks": ticks,
            "cross_date": (read or {}).get("cross_date"),
            "sessions_since": (read or {}).get("sessions_since"),
            "pct_since": (read or {}).get("pct_since"),
            "stage": STAGE_RAN,
            "lane": "ran",
            "label": RAN_LABEL,
            "label_zh": RAN_LABEL_ZH,
            "signal_asof": sig_date,
            "days_since_signal": days_since_signal(sig_date, board_asof),
        }
        if meta.get("spark_svg"):
            row["spark_svg"] = meta["spark_svg"]
        if theme:
            row["theme"] = dict(theme)
            if theme_confirmed(theme):
                row["theme_confirmed"] = True
                row["theme_note"] = RAN_THEME_LINE
                row["theme_note_zh"] = RAN_THEME_LINE_ZH
        rows.append(row)

    rows.sort(
        key=lambda row: (
            0 if row.get("theme_confirmed") else 1,
            row.get("ticks") if row.get("ticks") is not None else 10**6,
            -(row.get("pct_since") if row.get("pct_since") is not None else -10.0**6),
            row["ticker"],
        )
    )
    return rows[: max(0, int(cap))]
