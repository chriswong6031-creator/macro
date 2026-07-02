"""Cross-sectional "setup" scoring — selection (sector-neutral residual alpha)
× timing (cycle entry + the alpha engine's reversal overlay).

Shared by the US stock library (``scripts/build_stock_library``), the China
A-share library (``scripts/build_china_library``) and the macro dashboard's
"Standout individual stocks" board (``scripts/build_site``).

This is NOT a new statistical edge. Every consumer RE-RANKS an already-validated
alpha cross-section (``engine/residual_alpha``) by *when* — the calibrated
cycle-timing engine (``engine/cycles``) plus the alpha engine's own reversal
overlay. The honest claim is *confluence* (a sector-neutral leader you'd also want
to BUY today), not a fresh signal.

The blend weight on residual momentum differs by market because the VALIDATED
microstructure differs:

* **US equities** — sector-neutral residual momentum is a positive-IC *context*
  leg: a robust cross-sectional leader (PIT de-biased IC ~.012) but NOT a
  standalone edge (de-contaminated L/S Sharpe <= 0, nothing clears FDR; see
  ``research/RESIDUAL_ALPHA_MOMENTUM.md`` §4). So on the US side momentum LEADS
  the selection and the cycle is the entry/timing overlay -> ``US_ALPHA_WEIGHT``.
* **A-shares** — ~35y deep history KILLS cross-sectional momentum; short-term
  REVERSAL is the validated effect (``research/CHINA_HK_STOCK_SIGNALS.md``). So
  the residual is demoted to a light quality tiebreaker (``CN_ALPHA_WEIGHT``) and
  the score leads with the cycle entry + mean-reversion (pullback) overlay.

The ``pullback`` / ``extended`` direction is the SAME in both markets (a leader on
a recent pullback is the constructive entry; a just-spiked one is reversal RISK);
only the residual's weight changes.
"""
from __future__ import annotations

import re

# per-market residual-momentum weight (see module docstring)
US_ALPHA_WEIGHT = 0.7    # alpha-led: US residual momentum is a validated context leg
CN_ALPHA_WEIGHT = 0.35   # demoted to a quality tiebreaker: A-share momentum is killed in deep history
CA_ALPHA_WEIGHT = 0.55   # Canada: developed/momentum-persistent like the US but commodity-cyclical -> alpha-led, between US and CN (PRIOR; to be validated)

# timing tilts (shared across markets)
_URG_TILT = {"now": 0.9, "imminent": 0.9, "soon": 0.45, "exit": -0.9, "avoid": -0.9}
_EQDIR_TILT = {"up": 0.35, "down": -0.35}
_ENTRY_TILT = {"pullback": 0.7, "extended": -0.7}

# default cross-sectional gates for the "Top setups" / "Laggards" boards
BUY_MIN, LAG_MAX, N_BUY, N_LAG = 0.5, -0.3, 12, 6

# SUE earnings-momentum confirmer (DISPLAY CONTEXT ONLY) — a setup card / Top-setups
# row may carry a SUE (standardized unexpected earnings) chip the SAME way it carries
# the insider buy-cluster chip: a CONFIRMER shown beside the card, NEVER folded into
# setup_score. The setup ranking is validated as rank-by-alpha — timing and confirmers
# are displayed risk context, not scored (research/US_STANDOUT_SETUP_SCORE.md). SUE is
# the post-earnings-announcement-drift leg; it was the lone FDR survivor on the shallow
# 2023-2025 window but its cross-sectional edge collapses on deep history (engine/sue.py;
# reports/sue-deep-history-phase0.md), so it is shown as a confluence confirmer only. A
# positive z means the latest quarter beat its seasonal expectation and tends to keep
# drifting — earnings momentum AGREES with the setup. Gated to a real positive tailwind
# so it stays a confirmer, not noise.
SUE_CONFIRM = 1.0


def sue_confirmer(sue_z) -> float | None:
    """The SUE z to DISPLAY as an earnings-momentum confirmer chip on a setup card,
    or None when it is missing/NaN or below the positive-tailwind gate. Mirrors the
    insider buy-cluster chip: a confirmer leg only — the caller attaches the returned
    value to the card row, and it NEVER enters :func:`setup_score`."""
    try:
        z = float(sue_z)
    except (TypeError, ValueError):
        return None
    if z != z or z < SUE_CONFIRM:        # NaN, or below the tailwind gate
        return None
    return round(z, 2)


def timing_tilt(urgency: str | None, eq_dir: str | None,
                alpha_entry: str | None) -> float:
    """The timing component of the setup score (no residual term). Public so the
    macro board can score a name on the SAME scale even when it has no residual."""
    return (_URG_TILT.get(urgency, 0.0)
            + _EQDIR_TILT.get(eq_dir, 0.0)
            + _ENTRY_TILT.get(alpha_entry, 0.0))


def setup_score(rec: dict, *, alpha_weight: float) -> tuple[float, dict] | None:
    """Confluence rank for one name: ``alpha_weight * alpha_z + timing_tilt``.

    ``rec`` carries an ``alpha`` dict (``engine/residual_alpha`` per-ticker) and a
    ``ladder`` dict (``engine/cycles``). Returns ``(score, row)`` or ``None`` when
    the name has no residual (ETF / index / thin history) — i.e. nothing to rank.
    """
    a = rec.get("alpha") or {}
    az = a.get("alpha")
    if az is None:
        return None
    lad = rec.get("ladder") or {}
    entry = lad.get("entry") or {}
    urg, eqdir, ae = entry.get("urgency"), lad.get("eq_dir"), a.get("entry")
    score = alpha_weight * az + timing_tilt(urg, eqdir, ae)
    row = {"ticker": rec.get("ticker"), "name": rec.get("name"),
           "sector": rec.get("sector"),
           "alpha": az, "alpha_entry": ae, "state": lad.get("state"),
           "label": lad.get("label"), "label_zh": lad.get("label_zh"),
           "urgency": urg, "dir": lad.get("dir"), "eq_dir": eqdir,
           "sector_rank": a.get("sector_rank"), "sector_n": a.get("sector_n"),
           "setup": round(score, 2)}
    return score, row


_CLASS_TOK = re.compile(r"\b(?:cl|class)\s*[a-k]\b")


def norm_company(name: str | None) -> str:
    """Normalised company name for dual-class / multi-listing dedup: lowercased,
    punctuation and share-class tokens ('Cl A' / 'Class C') stripped, so GOOG
    'Alphabet Inc Cl C' and GOOGL 'Alphabet Inc Cl A' collapse to one key. Corporate
    suffixes (Inc/Corp/…) are KEPT to avoid collapsing genuinely distinct firms."""
    s = _CLASS_TOK.sub(" ", (name or "").lower())
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def dedupe_dual_class(rows: list[dict]) -> list[dict]:
    """Drop dual-class / multi-listing duplicates from an already-ranked list,
    keeping the FIRST (best-ranked) variant per normalised company name — so a board
    doesn't spend two slots on GOOG + GOOGL. Falls back to the ticker when a name is
    blank (never collapses two blank-named rows together)."""
    seen, out = set(), []
    for r in rows:
        key = norm_company(r.get("name")) or (r.get("ticker") or id(r))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def entry_open_first(rows: list[dict]) -> list[dict]:
    """STABLE re-rank of a standout 'buy' board so names whose ENTRY gauge reads
    'Buy zone — entry open now' (entry_signal.status == 'buy_now') lead the strip,
    then by the displayed conviction score (high → low).

    W6-US fix 5: 'buy_now' only floats a name to the top when composite_z > 0
    (i.e. the name has positive multi-factor conviction). This prevents a sparse binary
    flag on a negative-edge name (e.g. ETN: composite_z -0.047) from unilaterally
    seizing slot #1.  Names with composite_z <= 0 and status=='buy_now' are treated
    as not-open for sorting purposes and fall to their bottoming-alignment position.

    Soft invariant: after sorting, if slot #1 has negative alpha we log a warning.

    Stable: rows that tie on (entry-open?, score) keep the caller's prior order, so the
    validated bottoming-alignment / confluence rank still settles ties. Best-effort: a
    row missing either field sorts as not-open / lowest-score within its group."""
    import logging as _log
    _logger = _log.getLogger(__name__)

    def _key(r):
        es = r.get("entry_signal") or {}
        c = r.get("conviction") or {}
        sc = c.get("score")
        czr = c.get("composite_z")
        cz = float(czr) if czr is not None else 0.0
        # only honour buy_now if composite_z > 0 (positive conviction)
        is_open = (es.get("status") == "buy_now") and (cz > 0)
        return (0 if is_open else 1, -(sc if sc is not None else -1.0))

    result = sorted(rows, key=_key)
    # soft invariant: warn if slot #1 has negative alpha (not fatal, but tracked)
    if result:
        _top = result[0]
        _top_alpha = _top.get("alpha")
        if _top_alpha is not None and _top_alpha < 0:
            _logger.warning(
                "entry_open_first: slot #1 is %s with negative alpha %.2f — "
                "bottoming-alignment may be placing a weak name at the top",
                _top.get("ticker"), _top_alpha)
    return result


# minimum aligned names a standout strip shows before it backfills with NEAR-aligned
# (clearly tagged) candidates — so the strip is never bare in thin tape but never pads
# with falling knives (near-aligned still requires a not-falling weekly). Sourced from
# config.yml engine.entry_gate.align_min_keep (fallback 10) so it tunes with the gate;
# config is imported lazily so this pure module stays import-light for tests.
def _default_align_min_keep(fallback: int = 10) -> int:
    try:
        from lib import config
        v = ((config.load().get("engine") or {}).get("entry_gate") or {}).get("align_min_keep")
        return int(v) if v is not None else fallback
    except Exception:  # noqa: BLE001 — config unavailable -> use the fallback
        return fallback


ALIGN_MIN_KEEP = _default_align_min_keep()


def _align_tier(a: dict | None) -> str | None:
    """'aligned' / 'near' / None from an engine.cycles.mtf_alignment dict."""
    a = a or {}
    if a.get("aligned"):
        return "aligned"
    if a.get("near"):
        return "near"
    return None


def alignment_gate(rows: list[dict], align_of, *, min_keep: int = 0,
                   sort_key=None, tier_key: str = "align_tier") -> list[dict]:
    """Filter an (already-ranked) row list to bottoming-ALIGNED names, backfilling
    NEAR-aligned names only up to ``min_keep``. ``align_of(row)`` returns that row's
    alignment dict (engine.cycles.mtf_alignment). Knives / unaligned / thin-history
    rows are DROPPED. Every kept row is tagged ``row[tier_key]`` in {'aligned','near'}
    so the card can flag a near-aligned (unconfirmed) pick. When ``sort_key`` is given,
    aligned and near are each sorted by it descending (e.g. by alignment score)."""
    aligned, near = [], []
    for r in rows:
        tier = _align_tier(align_of(r))
        if tier is None:
            continue
        r[tier_key] = tier
        (aligned if tier == "aligned" else near).append(r)
    if sort_key is not None:
        aligned.sort(key=sort_key, reverse=True)
        near.sort(key=sort_key, reverse=True)
    if len(aligned) >= min_keep:
        return aligned
    return aligned + near[: max(0, min_keep - len(aligned))]


def rank_setups(cands: list[tuple[float, dict]], *, buy_min: float = BUY_MIN,
                lag_max: float = LAG_MAX, n_buy: int = N_BUY, n_lag: int = N_LAG,
                as_of=None, rank_by: str = "setup",
                align_map: dict | None = None,
                align_min_keep: int = ALIGN_MIN_KEEP,
                buy_gate=None) -> dict:
    """Split scored candidates into the constructive ``buy`` shortlist and the
    ``laggards`` watch. ``cands`` is a list of ``(score, row)`` from :func:`setup_score`.

    ``buy_gate`` (``ticker -> bool``), when given, is a HARD admission filter on the BUY
    shortlist ONLY (laggards are untouched): a name reaches the buy list only when
    ``buy_gate(ticker)`` is truthy. It REPLACES the ``alpha >= buy_min`` momentum floor (the
    gate is now the buyability criterion; the score is just the rank). This is how the US
    "Top setups" board surfaces only names that have a FRESH MACD-2D x StochRSI-3D confluence
    buy (engine.signal_gate.is_buyable) instead of every high-alpha leader regardless of tape.
    It composes with ``align_map`` (both must pass).

    ``rank_by`` chooses the SORT key, per the market's validated evidence:
      * ``"alpha"`` (US) — order by the sector-neutral residual-momentum z. The
        cycle-timing/reversal blend was Phase-0 tested (reports/setup-score-phase0.md)
        and does NOT improve forward-return ranking — it slightly DILUTES alpha — so
        the board rides the only positive-IC leg and the timing is displayed *context*.
      * ``"setup"`` (China, default) — order by the full reversal-led setup score, which
        IS the A-share validated construction (deep-history reversal edge,
        research/CHINA_HK_STOCK_SIGNALS.md).

    The factor composite (``row['factor_z']``) breaks near-ties as a LIGHT quality leg.
    Dual-class duplicates collapse to the best-ranked variant.

    ``align_map`` (ticker -> engine.cycles.mtf_alignment dict), when given, REPLACES the
    ``alpha >= buy_min`` admission with the multi-timeframe BOTTOMING-ALIGNMENT gate: the
    buy list becomes the aligned names (weekly not-falling + 3-day nearing a bullish cross
    + daily just-crossed/about-to), ranked by alignment score then the market's leg, with
    NEAR-aligned names backfilling only up to ``align_min_keep`` (each tagged align_tier).
    This is how a falling knife is kept off the strip — the laggards board is unchanged."""
    def _key(x):
        s, r = x
        primary = (r.get("alpha") if rank_by == "alpha" else s) or 0.0
        return primary, (r.get("factor_z") or 0.0)

    ranked_desc = sorted(cands, key=_key, reverse=True)   # best (buys) first
    ranked_asc = sorted(cands, key=_key)                  # worst (laggards) first
    _gate_ok = (lambda r: bool(buy_gate(r.get("ticker")))) if buy_gate is not None \
        else (lambda r: True)
    if align_map is not None:
        def _asort(r):
            a = align_map.get(r.get("ticker")) or {}
            sec = (r.get("alpha") if rank_by == "alpha" else r.get("setup")) or 0.0
            return (a.get("score") or 0.0, sec)
        buys = dedupe_dual_class(
            alignment_gate([r for _s, r in ranked_desc if _gate_ok(r)],
                           lambda r: align_map.get(r.get("ticker")),
                           min_keep=align_min_keep, sort_key=_asort))[:n_buy]
    else:
        # buy_gate REPLACES the alpha floor (it is now the buyability gate); without a gate the
        # board keeps the classic alpha >= buy_min momentum admission.
        buys = dedupe_dual_class(
            [r for s, r in ranked_desc
             if r.get("alpha") is not None
             and (_gate_ok(r) if buy_gate is not None else r["alpha"] >= buy_min)])[:n_buy]
    laggards = dedupe_dual_class(
        [r for s, r in ranked_asc
         if r.get("alpha") is not None and r["alpha"] <= lag_max])[:n_lag]
    return {"as_of": as_of, "buy": buys, "laggards": laggards}
