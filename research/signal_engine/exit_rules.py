"""Exit rules — deliberately MINIMAL (CHARTER §6.2).

Exit work is a SEPARATE, ACTIVE session. This file exists only to (1) name the
canonical seam so exit research has one obvious home, and (2) ship the simplest
honest baseline. **Do not over-build it here.**

WHY IT STAYS SIMPLE
-------------------
The CHARTER's hardest-won lesson (§5): a regime/exit-routing classifier was built,
tested on 105 held-out names, and **KILLED** — it was no better than a single fixed
exit and captured less. *"Drawdown control comes from filtering bad ENTRIES, not
from clever EXIT-routing."* So the bar for any exit beyond `fixed_exit` is the same
generalization gate the buy-filter cleared: held-out names, drawdown metric, tiny
spec, walk-forward embargo (see `README.md` -> "the verdict gate"). Until a candidate
beats `fixed_exit` on drawdown out-of-sample, ship `fixed_exit`.

The expected `sig` frame is `confluence.compute_signals` /
`engine.signal_quality.signal_frame` output (columns include `CS`, `revSell`).
"""
from __future__ import annotations


def fixed_exit(i, sig) -> tuple[bool, str]:
    """The baseline exit: leave on a confluence SELL* or the fast-reversal cut-loss.

    This is the "single fixed exit ≈ as good as the killed router" baseline of
    CHARTER §6.2 — the thing every fancier exit must beat out-of-sample to ship.

    >>> import pandas as pd
    >>> sig = pd.DataFrame({"CS": [True, False, False], "revSell": [False, True, False]})
    >>> fixed_exit(0, sig)
    (True, 'confluence SELL*')
    >>> fixed_exit(1, sig)
    (True, 'fast-reversal cut-loss')
    >>> fixed_exit(2, sig)
    (False, 'hold')
    """
    if bool(sig["CS"].iloc[i]):
        return True, "confluence SELL*"
    if bool(sig["revSell"].iloc[i]):
        return True, "fast-reversal cut-loss"
    return False, "hold"


# ---------------------------------------------------------------------------
# EXPANSION POINT  (the separate exit session plugs in here)
# ---------------------------------------------------------------------------
# Add new exit candidates as `def <name>_exit(i, sig, **params) -> (bool, reason)`
# and register them below so a harness can A/B them against `fixed_exit` on the
# SAME held-out panel and the SAME drawdown metric. Keep each candidate's spec
# tiny (multiple-testing inflates in-sample winners) and validate with the
# walk-forward embargo before promoting anything. DO NOT route by regime here —
# that path is killed (CHARTER §5); improve exits only via a cross-sectionally
# validated, single-rule change.
#
# Example skeleton (left intentionally unimplemented — owned by the exit session):
#   def structural_trailing_exit(i, sig, fast_span=8):
#       """Exit on close < a rising fast EMA (the diagnose_v2 structural stop)."""
#       raise NotImplementedError("owned by the exit-rules session; cf. the diagnose_v2 structural stop")

EXIT_RULES = {
    "fixed": fixed_exit,
    # "structural_trailing": structural_trailing_exit,   # <- add when validated
}


if __name__ == "__main__":   # pragma: no cover
    import doctest
    fails, _ = doctest.testmod(verbose=False)
    print("exit_rules doctests:", "OK" if not fails else f"{fails} FAILED")
