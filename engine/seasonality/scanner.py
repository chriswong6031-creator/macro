"""Lane 2/4 — the fixed window family and the price of having searched it.

The scanner exists to answer one question honestly: *what is this window worth
after paying for the search that found it?*  The incumbent products answer it by
not asking; a dense start-date x horizon scan produces hundreds of windows at
|t| >= 1.96 on pure noise, and any of them can be presented as the headline.

The correction is a joint (Westfall-Young style) maximum-statistic null:

* each resample rolls **each year's** daily return series by its **own** random
  offset, which destroys calendar alignment within and across years while
  preserving that year's return distribution and short-horizon autocorrelation;
* every resample then recomputes the ENTIRE window grid and only the maximum
  |t| is recorded, so dependence between overlapping windows is preserved
  exactly the way the maxT construction requires.

A *synchronized* shift (one offset shared by all years) is the wrong null here.
It moves a real seasonal effect to a new date instead of removing it, so the
null maximum inherits the very structure the test is supposed to price, and the
threshold comes out too high.  It is not implemented in this module.

Windows never wrap the year: a window is admissible only when
``start_doy + horizon <= 365``, which is what fixes the family at 2645.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np

from .multiplicity import benjamini_yekutieli, max_t_adjusted_p_values
from .panel import N_SLOTS, YearPanel, month_slot_bounds

HORIZONS_DAYS = (5, 10, 15, 20, 30, 45, 60, 90)
N_CANDIDATES = sum(N_SLOTS - horizon for horizon in HORIZONS_DAYS)  # 2645
DEFAULT_RESAMPLES = 2000
TOP_K_DISCOVERED = 8
MAX_OVERLAP_SHARE = 0.5
NULL_METHOD = "independent_circular_year_shift"
STATISTIC = "abs_t_of_mean_window_log_return_across_years"
START_DAYS_RULE = "1..365, restricted so start + horizon <= 365 (windows never wrap the year)"
QUANTILE_KEYS = ("0.90", "0.95", "0.99")
LADDER_STEPS = 101  # q = 0.00, 0.01, ... 1.00
# The lookback pills the page offers (research/STOCK_SEASONALITY_LANE2_DESIGN_SPEC
# §5: `10y | 15y | 25y | Max`). Each one changes the panel, so each one needs its
# OWN null: a 10-year |t| judged against a 25-year null is compared to a threshold
# built from a different sample size AND a different autocorrelation structure,
# and it is wrong in the flattering direction for short lookbacks.
LOOKBACKS_YEARS = (10, 15, 25)
STABILITY_SHIFTS_DAYS = (-5, -2, 2, 5)
STABILITY_MEDIAN_FLOOR = 0.6

_MIN_YEARS_FOR_T = 2


def family_size() -> int:
    """The exact number of admissible windows (2645)."""
    return N_CANDIDATES


def window_family() -> tuple[tuple[int, int], ...]:
    """Every ``(start_doy, horizon_days)`` in the family, 1-based start days."""
    return tuple(
        (start, horizon)
        for horizon in HORIZONS_DAYS
        for start in range(1, N_SLOTS - horizon + 1)
    )


def seed_for_symbol(symbol: str) -> int:
    """A stable 32-bit seed so a symbol's null is reproducible forever."""
    digest = hashlib.sha256(f"seasonality:{symbol}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def family_fingerprint() -> str:
    """Hash the search definition itself.

    ``panel_fingerprint`` answers "is this the same data"; this answers "is this
    the same search". Both have to key the selection cache, because the null
    quantiles are only meaningful for the family they were maximised over. Widen
    ``HORIZONS_DAYS`` without this and the panel hash is unchanged, so every
    symbol keeps its stored null and the artifact publishes a 3075-window search
    priced by a 2645-window null — with no visible symptom anywhere.
    """
    definition = (
        N_SLOTS,
        HORIZONS_DAYS,
        N_CANDIDATES,
        STATISTIC,
        NULL_METHOD,
        TOP_K_DISCOVERED,
        MAX_OVERLAP_SHARE,
        LOOKBACKS_YEARS,
        STABILITY_SHIFTS_DAYS,
        STABILITY_MEDIAN_FLOOR,
        QUANTILE_KEYS,
        LADDER_STEPS,
    )
    return "sha256:" + hashlib.sha256(repr(definition).encode("utf-8")).hexdigest()


def panel_fingerprint(panel: YearPanel) -> str:
    """Hash the complete-year panel so a vendor re-adjustment busts the cache.

    Keyed on the folded daily returns rather than the years alone: the vendor's
    adjustment is a current vintage re-applied to all history, so an old year's
    numbers can change without any year boundary moving.
    """
    hasher = hashlib.sha256()
    hasher.update(",".join(str(year) for year in panel.years).encode("utf-8"))
    hasher.update(np.ascontiguousarray(np.round(panel.daily, 8), dtype=np.float64).tobytes())
    return "sha256:" + hasher.hexdigest()


# --- observed statistics ----------------------------------------------------


def _abs_t(window_returns: np.ndarray) -> np.ndarray:
    """|t| of the mean window return across years; NaN where it is undefined.

    ``sd == 0`` (every year identical, e.g. a window with no sessions in it) and
    ``n < 2`` are both undefined rather than infinite.  They surface as NaN here
    and as ``null`` in the artifact; they are never silently coerced to a large
    number, which would put a degenerate window at the top of the family.
    """
    n_years = window_returns.shape[-2]
    if n_years < _MIN_YEARS_FOR_T:
        return np.full(window_returns.shape[:-2] + window_returns.shape[-1:], np.nan)
    mean = window_returns.mean(axis=-2)
    sd = window_returns.std(axis=-2, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        statistic = np.abs(mean) / (sd / np.sqrt(n_years))
    return np.where(sd > 0.0, statistic, np.nan)


def window_returns(cum: np.ndarray, start_doy: int, end_doy: int) -> np.ndarray:
    """Per-year log return of ``[start_doy, end_doy]`` (1-based, inclusive end)."""
    return cum[..., end_doy - 1] - cum[..., start_doy - 1]


def window_statistics(cum: np.ndarray, start_doy: int, end_doy: int) -> dict:
    """Published statistics for one window, with the undefined cases as None."""
    values = np.asarray(window_returns(cum, start_doy, end_doy), dtype=np.float64)
    n_years = int(values.size)
    if n_years == 0:
        return {"n_years": 0, "mean": None, "median": None, "up_share": None, "sd": None, "abs_t": None}
    sd = float(values.std(ddof=1)) if n_years >= _MIN_YEARS_FOR_T else None
    statistic: float | None = None
    if sd is not None and sd > 0.0:
        statistic = float(abs(values.mean()) / (sd / np.sqrt(n_years)))
    return {
        "n_years": n_years,
        "mean": float(values.mean()),
        "median": float(np.median(values)),
        "up_share": float((values > 0.0).sum() / n_years),
        "sd": sd,
        "abs_t": statistic,
    }


def window_stability(cum: np.ndarray, start_doy: int, end_doy: int) -> dict:
    """Does the window survive being nudged a few days either way?

    A recurring FIVE-day calendar window is usually pinned to a recurring
    corporate event — an earnings date, an expiry, an index rebalance — not to a
    season.  Real seasonal structure is smeared across the neighbourhood, so
    shifting both endpoints by a couple of days should degrade it gently; an
    event artefact collapses the moment the window stops covering its date.

    ``survives`` requires BOTH that the mean keeps its sign at every shift and
    that the median shifted |t| holds at least 60% of the unshifted |t|.  A shift
    that would push the window past day 365 is not computable — windows never
    wrap the year — so it is published as ``null`` and makes ``survives`` false
    rather than being quietly dropped from the median.  A window butting against
    either year edge therefore cannot pass, which is the honest answer: it cannot
    be tested in both directions.
    """
    base = window_statistics(cum, start_doy, end_doy)
    base_t = base["abs_t"]
    base_sign = None if base["mean"] is None else float(np.sign(base["mean"]))

    shifted: list[float | None] = []
    signs: list[float | None] = []
    for shift in STABILITY_SHIFTS_DAYS:
        start, end = start_doy + shift, end_doy + shift
        if start < 1 or end > N_SLOTS:
            shifted.append(None)
            signs.append(None)
            continue
        stats = window_statistics(cum, start, end)
        shifted.append(None if stats["abs_t"] is None else round(float(stats["abs_t"]), 4))
        signs.append(None if stats["mean"] is None else float(np.sign(stats["mean"])))

    complete = all(value is not None for value in shifted)
    sign_stable = bool(
        complete
        and base_sign not in (None, 0.0)
        and all(sign == base_sign for sign in signs)
    )
    survives = bool(
        sign_stable
        and base_t
        and float(np.median([value for value in shifted if value is not None]))
        >= STABILITY_MEDIAN_FLOOR * float(base_t)
    )
    return {
        "shifts_days": list(STABILITY_SHIFTS_DAYS),
        "abs_t": shifted,
        "sign_stable": sign_stable,
        "survives": survives,
    }


def grid_abs_t(cum: np.ndarray) -> dict[int, np.ndarray]:
    """|t| for every window in the family, keyed by horizon.

    ``cum`` is ``(..., n_years, 365)``.  Entry ``[h][i]`` is the window starting
    at ``start_doy = i + 1`` with that horizon.
    """
    out: dict[int, np.ndarray] = {}
    for horizon in HORIZONS_DAYS:
        starts = np.arange(N_SLOTS - horizon)
        values = cum[..., starts + horizon] - cum[..., starts]
        out[horizon] = _abs_t(values)
    return out


def best_window(cum: np.ndarray) -> tuple[int, int, float] | None:
    """The family's largest |t| as ``(start_doy, end_doy, abs_t)``."""
    best: tuple[int, int, float] | None = None
    for horizon, values in grid_abs_t(cum).items():
        if not np.isfinite(values).any():
            continue
        index = int(np.nanargmax(values))
        statistic = float(values[index])
        if best is None or statistic > best[2]:
            best = (index + 1, index + 1 + horizon, statistic)
    return best


# --- the null ---------------------------------------------------------------


def _grid_max_abs_t(cum: np.ndarray) -> np.ndarray:
    """Per-resample maximum |t| over the whole family."""
    leading = cum.shape[:-2]
    best = np.full(leading, -np.inf)
    for horizon in HORIZONS_DAYS:
        starts = np.arange(N_SLOTS - horizon)
        statistic = _abs_t(cum[..., starts + horizon] - cum[..., starts])
        best = np.maximum(best, np.nanmax(np.where(np.isfinite(statistic), statistic, -np.inf), axis=-1))
    return np.where(np.isfinite(best), best, 0.0)


def draw_year_offsets(rng: np.random.Generator, n_resamples: int, n_years: int) -> np.ndarray:
    """Draw ONE circular shift PER YEAR per resample — the whole point of the null.

    Shape is ``(n_resamples, n_years)``, not ``(n_resamples, 1)``. A synchronized
    draw (one offset shared by every year) would relocate a real seasonal effect
    instead of removing it, leaving the null maximum carrying the very structure
    the test exists to price.
    """
    return rng.integers(0, N_SLOTS, size=(n_resamples, n_years))


def circular_year_shift(daily: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    """Roll each year's slot series by its own offset. ``np.roll`` semantics."""
    slots = np.arange(N_SLOTS)
    index = (slots[None, None, :] - offsets[:, :, None]) % N_SLOTS
    return daily[np.arange(daily.shape[0])[None, :, None], index]


def null_max_abs_t(
    daily: np.ndarray,
    *,
    n_resamples: int = DEFAULT_RESAMPLES,
    seed: int,
    extra_windows: tuple[tuple[int, int], ...] = (),
    chunk: int = 200,
) -> tuple[np.ndarray, np.ndarray]:
    """Independent circular year-shift null.

    Returns ``(family_max, extra)`` where ``family_max`` is ``(B,)`` and
    ``extra`` is ``(B, len(extra_windows))`` — the marginal |t| of a small
    registered panel under the same resamples, which is what turns a familywise
    maxT p-value into a BY sensitivity check without a second bootstrap.
    """
    n_years = daily.shape[0]
    rng = np.random.default_rng(seed)
    family_max = np.empty(n_resamples, dtype=np.float64)
    extra = np.empty((n_resamples, len(extra_windows)), dtype=np.float64)

    done = 0
    while done < n_resamples:
        width = min(chunk, n_resamples - done)
        rolled = circular_year_shift(daily, draw_year_offsets(rng, width, n_years))
        cum = np.cumsum(rolled, axis=-1)
        cum = cum - cum[..., :1]
        family_max[done : done + width] = _grid_max_abs_t(cum)
        for column, (start_doy, end_doy) in enumerate(extra_windows):
            statistic = _abs_t((cum[..., end_doy - 1] - cum[..., start_doy - 1])[..., None])[..., 0]
            extra[done : done + width, column] = np.where(np.isfinite(statistic), statistic, 0.0)
        done += width
    return family_max, extra


def exceedance_pct(null_max: np.ndarray, observed: float) -> float:
    """Share of resamples in which chance produced a window at least this strong.

    Carries the same ``(1 + count) / (B + 1)`` floor as every other p-value in this
    module, for the same reason: with B resamples the finest thing the Monte Carlo
    can resolve is 1/(B+1), so a bare ``count/B`` would publish "0.000%" for a
    window that simply beat every draw. It also makes this number and
    ``p_adj_maxt_family`` two renderings of ONE quantity rather than two numbers a
    reader has to reconcile.
    """
    values = np.asarray(null_max)
    return 100.0 * float(1 + int((values >= observed).sum())) / float(values.size + 1)


def quantile_ladder(null_max: np.ndarray, steps: int = LADDER_STEPS) -> list[float]:
    """Evenly spaced quantiles of the null maximum, for the chance track."""
    probabilities = np.linspace(0.0, 1.0, steps)
    return [round(float(value), 4) for value in np.quantile(np.asarray(null_max), probabilities)]


# --- registered panel + selection correction --------------------------------


def _overlap_share(a: tuple[int, int], b: tuple[int, int]) -> float:
    """Shared days as a share of the SHORTER window (the conservative reading).

    A window ``(s, e)`` covers the days ``s+1 .. e`` — ``e - s`` of them, not
    ``e - s + 1``. Treating the endpoints as an inclusive day range made two
    genuinely disjoint windows like ``(100, 105)`` and ``(105, 110)`` report 17%
    shared, because they touch at a single boundary that belongs to neither's
    return.
    """
    shared = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    shortest = min(a[1] - a[0], b[1] - b[0])
    return shared / shortest if shortest else 0.0


def top_non_overlapping(cum: np.ndarray, k: int = TOP_K_DISCOVERED) -> list[tuple[int, int]]:
    """The k strongest windows that do not restate each other.

    "Non-overlapping" is <50% shared days with anything already selected; a
    dense scan otherwise returns the same discovery eight times with the edges
    nudged, which would make the registered panel look like eight independent
    findings.
    """
    candidates: list[tuple[float, int, int]] = []
    for horizon, values in grid_abs_t(cum).items():
        for index, statistic in enumerate(values):
            if np.isfinite(statistic):
                candidates.append((float(statistic), index + 1, index + 1 + horizon))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))

    chosen: list[tuple[int, int]] = []
    for _statistic, start_doy, end_doy in candidates:
        window = (start_doy, end_doy)
        if all(_overlap_share(window, other) < MAX_OVERLAP_SHARE for other in chosen):
            chosen.append(window)
        if len(chosen) >= k:
            break
    return chosen


def month_window(month: int) -> tuple[int, int]:
    """The ``(start_doy, end_doy)`` whose return IS that calendar month's.

    A window's return is ``cum[end_doy - 1] - cum[start_doy - 1]``, i.e. the days
    ``start_doy + 1 .. end_doy`` — you enter at the ``start_doy`` close and exit
    at the ``end_doy`` close.  So February (days 32..59) is the window
    ``(31, 59)``, NOT ``(32, 59)``: entering on Feb 1 would forfeit Feb 1's own
    session and quietly understate every February in the panel.

    January is the one month whose entry day would be day 0.  The cumulative path
    is rebased so slot 0 IS the anchor (``cum[0] == 0``), so ``(1, 31)`` is both
    in range and complete for a US equity, whose Jan-1 slot is always a holiday.
    """
    first, last = month_slot_bounds(month)
    return max(1, first), last + 1


def registered_panel_windows(cum: np.ndarray, k: int = TOP_K_DISCOVERED) -> list[dict]:
    """The 12 calendar-month windows plus the top-k discovered windows."""
    panel: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for month in range(1, 13):
        window = month_window(month)
        seen.add(window)
        panel.append({"kind": "calendar_month", "month": month, "start_doy": window[0], "end_doy": window[1]})
    for window in top_non_overlapping(cum, k=k):
        if window in seen:
            continue
        seen.add(window)
        panel.append({"kind": "discovered", "month": None, "start_doy": window[0], "end_doy": window[1]})
    return panel


def null_summary(
    daily: np.ndarray,
    *,
    n_resamples: int,
    seed: int,
) -> dict:
    """The null a client needs to judge ANY window on this panel, and nothing more.

    Deliberately no registered panel and no best window: a lookback view only has
    to answer "is this |t| large for a panel of this shape", which is the quantiles
    plus the ladder the chance track reads. Roughly 1 KB per lookback.
    """
    null_max, _ = null_max_abs_t(daily, n_resamples=n_resamples, seed=seed)
    return {
        "method": NULL_METHOD,
        "B": n_resamples,
        "seed": seed,
        "n_years": int(daily.shape[0]),
        "max_abs_t_quantiles": {
            key: round(float(np.quantile(null_max, float(key))), 4) for key in QUANTILE_KEYS
        },
        "max_abs_t_quantile_ladder": quantile_ladder(null_max),
    }


def lookback_nulls(
    panel: YearPanel,
    *,
    n_resamples: int,
    seed: int,
) -> dict[str, dict]:
    """One null per offered lookback SHORTER than the panel.

    A lookback at least as long as the panel is the panel, so it is omitted and
    the client falls back to ``family.null`` — which is exactly the "Max" pill.
    """
    out: dict[str, dict] = {}
    for lookback in LOOKBACKS_YEARS:
        if lookback >= panel.n_years or lookback < _MIN_YEARS_FOR_T:
            continue
        out[str(lookback)] = null_summary(
            panel.daily[-lookback:],
            n_resamples=n_resamples,
            seed=(seed + lookback) % (2**32),
        )
    return out


@dataclass(frozen=True)
class ScanResult:
    """Everything the artifact needs from the family, plus the null it was priced against."""

    n_candidates: int
    n_resamples: int
    seed: int
    n_years: int
    max_abs_t_quantiles: dict[str, float]
    max_abs_t_ladder: list[float]
    null_by_lookback: dict[str, dict]
    registered_panel: list[dict]
    best: dict | None
    panel_hash: str
    family_hash: str
    null_max: np.ndarray = field(repr=False, default_factory=lambda: np.zeros(0))


def scan(
    panel: YearPanel,
    *,
    n_resamples: int = DEFAULT_RESAMPLES,
    seed: int | None = None,
    k_discovered: int = TOP_K_DISCOVERED,
) -> ScanResult | None:
    """Run the family scan, its null, and the selection correction.

    Returns ``None`` when the panel cannot support a t statistic at all — a
    missing correction is printed as missing, never approximated.
    """
    if panel.n_years < _MIN_YEARS_FOR_T:
        return None
    resolved_seed = seed_for_symbol(panel.symbol) if seed is None else seed
    windows = registered_panel_windows(panel.cum, k=k_discovered)
    extra = tuple((entry["start_doy"], entry["end_doy"]) for entry in windows)

    null_max, null_panel = null_max_abs_t(
        panel.daily, n_resamples=n_resamples, seed=resolved_seed, extra_windows=extra
    )

    observed = [window_statistics(panel.cum, entry["start_doy"], entry["end_doy"]) for entry in windows]
    statistics = [0.0 if stats["abs_t"] is None else stats["abs_t"] for stats in observed]

    # Family-wide Westfall-Young via the shipped primitive. The full [B][2645]
    # matrix is impractical here (5.3M pure-Python element validations per panel,
    # per symbol), so each row is collapsed to the value the primitive would take
    # from it anyway — its maximum. Identical output, and
    # tests/test_stock_seasonality_engine.py pins that identity against a real
    # full-width matrix rather than leaving it as a claim in a comment.
    width = len(windows)
    adjusted = max_t_adjusted_p_values(statistics, [[value] * width for value in null_max])

    # Marginal p-values, and then a decision about which of them mean anything.
    #
    # The 12 calendar months are PRE-REGISTERED: nobody chose them after seeing
    # the data, so their marginal p is honest and a BY step-up over them is the
    # sensitivity result the docket asks for. The top-k windows are the opposite:
    # they are the family's largest |t| values, selected on this very panel. Their
    # marginal p is contaminated by construction — on pure-noise panels 96% of
    # them come out below 0.05 — so publishing one, or letting it into a BY panel,
    # would hand the page a "significant discovery" for every symbol on earth.
    # They already carry the number that IS valid for them: p_adj_maxt_family,
    # which prices exactly the search that found them.
    denominator = float(n_resamples + 1)
    raw: list[float | None] = []
    for column, entry in enumerate(windows):
        if entry["kind"] != "calendar_month":
            raw.append(None)
            continue
        raw.append(float((1 + int((null_panel[:, column] >= statistics[column]).sum())) / denominator))

    registered_p = [value for value in raw if value is not None]
    registered_q = benjamini_yekutieli(registered_p) if registered_p else []
    q_values: list[float | None] = []
    q_iter = iter(registered_q)
    for value in raw:
        q_values.append(next(q_iter) if value is not None else None)

    registered: list[dict] = []
    for column, (entry, stats) in enumerate(zip(windows, observed)):
        registered.append(
            {
                **entry,
                "horizon_days": entry["end_doy"] - entry["start_doy"],
                **{
                    key: (round(value, 6) if isinstance(value, float) else value)
                    for key, value in stats.items()
                },
                "null_max_exceedance_pct": (
                    None if stats["abs_t"] is None else round(exceedance_pct(null_max, stats["abs_t"]), 3)
                ),
                "p_raw": None if raw[column] is None else round(raw[column], 6),
                "p_adj_maxt_family": round(adjusted[column], 6),
                "q_by": None if q_values[column] is None else round(q_values[column], 6),
                "stability": window_stability(panel.cum, entry["start_doy"], entry["end_doy"]),
            }
        )

    quantiles = {
        key: round(float(np.quantile(null_max, float(key))), 4) for key in QUANTILE_KEYS
    }
    top = best_window(panel.cum)
    best: dict | None = None
    if top is not None:
        start_doy, end_doy, statistic = top
        best = {
            "start_doy": start_doy,
            "end_doy": end_doy,
            "abs_t": round(statistic, 4),
            "exceedance_pct": round(exceedance_pct(null_max, statistic), 3),
            "clears_95": bool(statistic >= quantiles["0.95"]),
            "stability": window_stability(panel.cum, start_doy, end_doy),
        }

    return ScanResult(
        n_candidates=N_CANDIDATES,
        n_resamples=n_resamples,
        seed=resolved_seed,
        n_years=panel.n_years,
        max_abs_t_quantiles=quantiles,
        max_abs_t_ladder=quantile_ladder(null_max),
        null_by_lookback=lookback_nulls(panel, n_resamples=n_resamples, seed=resolved_seed),
        registered_panel=registered,
        best=best,
        panel_hash=panel_fingerprint(panel),
        family_hash=family_fingerprint(),
        null_max=null_max,
    )
