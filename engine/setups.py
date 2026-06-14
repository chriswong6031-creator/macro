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

# per-market residual-momentum weight (see module docstring)
US_ALPHA_WEIGHT = 0.7    # alpha-led: US residual momentum is a validated context leg
CN_ALPHA_WEIGHT = 0.35   # demoted to a quality tiebreaker: A-share momentum is killed in deep history

# timing tilts (shared across markets)
_URG_TILT = {"now": 0.9, "imminent": 0.9, "soon": 0.45, "exit": -0.9, "avoid": -0.9}
_EQDIR_TILT = {"up": 0.35, "down": -0.35}
_ENTRY_TILT = {"pullback": 0.7, "extended": -0.7}

# default cross-sectional gates for the "Top setups" / "Laggards" boards
BUY_MIN, LAG_MAX, N_BUY, N_LAG = 0.5, -0.3, 12, 6


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


def rank_setups(cands: list[tuple[float, dict]], *, buy_min: float = BUY_MIN,
                lag_max: float = LAG_MAX, n_buy: int = N_BUY, n_lag: int = N_LAG,
                as_of=None) -> dict:
    """Split scored candidates into the constructive ``buy`` shortlist (strong
    alpha + constructive timing, ranked by setup desc) and the ``laggards`` watch
    (weak alpha, ranked by setup asc). ``cands`` is a list of ``(score, row)`` as
    returned by :func:`setup_score`."""
    buys = [r for s, r in sorted(cands, key=lambda x: -x[0])
            if r.get("alpha") is not None and r["alpha"] >= buy_min][:n_buy]
    laggards = [r for s, r in sorted(cands, key=lambda x: x[0])
                if r.get("alpha") is not None and r["alpha"] <= lag_max][:n_lag]
    return {"as_of": as_of, "buy": buys, "laggards": laggards}
