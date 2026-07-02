"""Override-Registry apply layer for the Bitcoin Vector.

ARCHITECTURE (Override-Registry Program, W0):

  allocation() in btc_signals is now a PURE ENGINE — it computes the
  (momentum × risk × conviction × brake × overlay) allocation without any
  post-hoc masking. Human conviction overrides are DECLARED in config.yml
  under `vector.overrides:` and APPLIED here as the final word.

  apply(alloc_df, cfg) -> DataFrame
    Input  : the pure engine alloc_df (columns alloc_<name> for each variant)
    Output : the same frame PLUS, for every alloc_<name> column:
               alloc_<name>       final: masked to 0.0 where an override is
                                  active (IDENTICAL to the pre-W0 live values)
               alloc_<name>_raw   the pure engine input, untouched
             and two cross-variant index columns:
               override_active    bool Series — True on every bar where ANY
                                  override suppresses the engine output
               override_id        str  Series — the id of the active override,
                                  '' on non-gated bars

  Every override that sizes money must be graded.  The registry declaration in
  config.yml (vector.overrides) is the governance instrument; the ledger output
  (data/vector/override_ledger.jsonl) is the grading surface.  This module only
  applies; it does not grade.

  The midterm-election blackout is currently the sole registered override.
  It delegates blackout-window computation to btc_signals.midterm_blackout()
  so that tests/test_btc_signals.py::test_midterm_blackout_windows keeps
  passing unchanged.
"""
from __future__ import annotations

import pandas as pd


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def apply(alloc_df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Apply all registered overrides to a pure-engine allocation frame.

    Parameters
    ----------
    alloc_df : DataFrame
        Pure engine output from btc_signals.allocation().  Must contain at
        least one column named ``alloc_<name>`` for each strategy variant.
    cfg : dict
        The ``vector.allocation`` config block (the same block that carries
        ``midterm_gate`` and ``variants``).

    Returns
    -------
    DataFrame
        The input columns, unmodified, renamed to ``alloc_<name>_raw``.
        Plus ``alloc_<name>`` final (masked where override is active).
        Plus ``override_active`` (bool) and ``override_id`` (str).
    """
    out = alloc_df.copy()

    # Discover the variant allocation columns (prefix ``alloc_``).
    alloc_cols = [c for c in alloc_df.columns if c.startswith("alloc_")]

    # ---------------------------------------------------------------------- #
    # Build the combined override mask from all registered overrides.
    # Today there is exactly one: the midterm-election blackout.
    # New overrides should be added here; each must set its rows in `active`
    # and record its id string in `oid` for those rows.
    # ---------------------------------------------------------------------- #
    active = pd.Series(False, index=alloc_df.index)
    oid = pd.Series("", index=alloc_df.index)

    # Override 0 — midterm_blackout
    # Config params live at vector.allocation.midterm_gate (back-compat kept).
    # The blackout window function stays in btc_signals so the existing test
    # suite continues to exercise it there.
    gate_cfg = cfg.get("midterm_gate")
    if gate_cfg and gate_cfg.get("enabled", False):
        from engine.btc_signals import midterm_blackout
        gate = midterm_blackout(alloc_df.index, gate_cfg)
        active = active | gate
        oid = oid.mask(gate, "midterm_blackout")

    # ---------------------------------------------------------------------- #
    # Emit raw columns and apply the combined mask.
    # ---------------------------------------------------------------------- #
    for col in alloc_cols:
        out[f"{col}_raw"] = alloc_df[col]  # pure engine — untouched
        out[col] = alloc_df[col].mask(active, 0.0)  # override: force flat

    # Store override_active as int8 (0/1) rather than Python bool so the column
    # survives parquet round-trips with a stable numeric dtype and does not trip
    # bool-subtract errors in numeric pipeline checks (pandas is_numeric_dtype
    # returns True for bool, but numpy boolean subtraction is undefined).
    # Callers that need a bool mask should cast: override_active.astype(bool).
    out["override_active"] = active.astype("int8")
    out["override_id"] = oid

    return out
