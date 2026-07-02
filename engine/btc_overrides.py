"""Override-Registry apply layer for the Bitcoin Vector.

ARCHITECTURE (Override-Registry Program, W0 + W2):

  allocation() in btc_signals is now a PURE ENGINE — it computes the
  (momentum × risk × conviction × brake × overlay) allocation without any
  post-hoc masking. Human conviction overrides are DECLARED in config.yml
  under `vector.overrides:` and APPLIED here as the final word.

  apply(alloc_df, cfg, ctx=None) -> DataFrame
    Input  : the pure engine alloc_df (columns alloc_<name> for each variant)
    Output : the same frame PLUS, for every alloc_<name> column:
               alloc_<name>       final: masked to 0.0 where an override is
                                  active (IDENTICAL to the pre-W0 live values
                                  unless a Class-1 release has fired)
               alloc_<name>_raw   the pure engine input, untouched
             and three cross-variant index columns:
               override_active    int8 0/1 — 1 on every bar where ANY override
                                  suppresses the engine output
               override_id        str — the id of the active override, '' on
                                  non-gated bars
               override_released  int8 0/1 — 1 from the bar a Class-1 release
                                  confirms through the end of that override
                                  window (sticky; final == raw on those bars)

  CLASS-1 AUTO-RELEASE (W2; owner decision D1, recorded 2026-07-02):
  the registry may declare a `structural_invalidation` release rule
  (signal: new_ath_close). The invalidation is ANCHOR-INDEPENDENT — a new
  all-time-high daily close (close > running historical max), NOT a comparison
  against a hand-set anchor date — held for `confirm_days` CONSECUTIVE closes
  above the broken prior ATH. On confirm the gate steps down to the engine's
  raw allocation (the brake/conviction stack then governs) for the REMAINDER
  of that override window. confirm_days is pre-committed in the masterplan and
  counted in the registry `dof_cost`; it must never be re-tuned.

  Every override that sizes money must be graded.  The registry declaration in
  config.yml (vector.overrides) is the governance instrument; the grading
  ledger lives in engine/btc_override_ledger.py (W5) and consumes the override
  columns this module emits.  total_dof() feeds the declared dof_cost into the
  DSR trial budget (scripts/calibrate_vector.py) — the registry makes DOF more
  expensive, never cheaper.

  The midterm-election blackout is currently the sole registered override.
  It delegates blackout-window computation to btc_signals.midterm_blackout()
  so that tests/test_btc_signals.py::test_midterm_blackout_windows keeps
  passing unchanged.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# Class-1 structural invalidation — anchor-independent, zero-fit
# --------------------------------------------------------------------------- #
def ath_invalidation_confirmed(close: pd.Series, confirm_days: int = 5) -> pd.Series:
    """Boolean EVENT Series: True exactly on the bar where a NEW ALL-TIME-HIGH
    daily close has been held for `confirm_days` CONSECUTIVE closes above the
    broken prior ATH — the bar the structural invalidation CONFIRMS.

    Definition (masterplan §4 N2, overfit-hawk approved):
      - a confirm sequence STARTS on a close strictly above the running
        historical max of all prior closes (a new-ATH close);
      - the broken prior ATH is FROZEN as the confirm reference for the
        sequence (subsequent closes need not each set fresh records — they
        must stay above the level that was broken);
      - any close at/below the reference (or a missing close) RESETS the
        sequence — "consecutive" means consecutive;
      - on the `confirm_days`-th consecutive qualifying close the event FIRES
        and the machine resets — the event is CONSUMED. It is a one-bar EVENT,
        not a standing state: sitting for years above some long-ago broken ATH
        must not read as "currently confirming" (live tape lesson: the spliced
        history starts 2014-09, so a 2016 series-ATH break otherwise kept
        streak>=N alive for a decade and spuriously released the 2026 gate).
        The caller latches window stickiness via _sticky_within_windows.

    Anchor-independent (no hand-set pivot dates anywhere) and zero-fit:
    the only parameter is the pre-committed confirm window, registered as
    dof_cost in config.yml vector.overrides. Causal: bar i reads only closes
    up to i.
    """
    n = int(confirm_days)
    c = pd.to_numeric(close, errors="coerce")
    vals = c.to_numpy(dtype=float)
    out = np.zeros(len(vals), dtype=bool)
    ath = np.nan          # running max of all closes seen so far
    ref = np.nan          # the prior ATH broken by the current confirm sequence
    streak = 0
    for i, v in enumerate(vals):
        if not np.isfinite(v):
            streak, ref = 0, np.nan          # missing close breaks the sequence (conservative)
        elif streak == 0:
            if np.isfinite(ath) and v > ath:  # a new-ATH close starts a sequence
                ref, streak = ath, 1
        elif v > ref:
            streak += 1
        else:
            streak, ref = 0, np.nan
        if streak >= n:                       # the invalidation event fires…
            out[i] = True
            streak, ref = 0, np.nan           # …and is consumed (machine resets)
        if np.isfinite(v):
            ath = v if not np.isfinite(ath) else max(ath, v)
    return pd.Series(out, index=close.index)


def _sticky_within_windows(gate: pd.Series, confirmed: pd.Series) -> pd.Series:
    """Release mask: once `confirmed` fires inside a contiguous gate window, the
    release holds (sticky) through the END of that window. Never leaks across
    windows — the next gate window starts armed again."""
    gate = gate.astype(bool)
    win_id = (gate != gate.shift()).cumsum()
    hit = (confirmed.reindex(gate.index).fillna(False).astype(bool)) & gate
    return hit.groupby(win_id).cummax() & gate


def _release_rule(overrides: list | None, override_id: str, kind: str) -> dict | None:
    """The declared release rule of `kind` for `override_id`, or None. Tolerates
    the W0 string-form release_rules (treated as undeclared)."""
    for ov in overrides or []:
        if isinstance(ov, dict) and ov.get("id") == override_id:
            for rule in ov.get("release_rules") or []:
                if isinstance(rule, dict) and rule.get("kind") == kind:
                    return rule
    return None


def total_dof(vcfg: dict) -> int:
    """Sum of declared dof_cost across the Override Registry (vector.overrides).
    Charged to the DSR trial budget (calibrate_vector n_trials) the moment an
    override is WRITTEN — the registry makes DOF more expensive, never cheaper."""
    return int(sum(int(ov.get("dof_cost", 1) or 0)
                   for ov in (vcfg.get("overrides") or []) if isinstance(ov, dict)))


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def apply(alloc_df: pd.DataFrame, cfg: dict, ctx: dict | None = None) -> pd.DataFrame:
    """Apply all registered overrides to a pure-engine allocation frame.

    Parameters
    ----------
    alloc_df : DataFrame
        Pure engine output from btc_signals.allocation().  Must contain at
        least one column named ``alloc_<name>`` for each strategy variant.
    cfg : dict
        The ``vector.allocation`` config block (the same block that carries
        ``midterm_gate`` and ``variants``).
    ctx : dict, optional (W2)
        Extra context the release rules need:
          close     — daily close Series (same calendar as alloc_df) for the
                      Class-1 new-ATH invalidation;
          overrides — the ``vector.overrides`` registry list (declares the
                      release rules + the pre-committed confirm window).
        Omitting ctx (or either key) disables Class-1 release — W0 behavior.

    Returns
    -------
    DataFrame
        The input columns, unmodified, renamed to ``alloc_<name>_raw``.
        Plus ``alloc_<name>`` final (masked where override is active).
        Plus ``override_active`` (int8), ``override_id`` (str) and
        ``override_released`` (int8).
    """
    ctx = ctx or {}
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
    released = pd.Series(False, index=alloc_df.index)

    # Override 0 — midterm_blackout
    # Config params live at vector.allocation.midterm_gate (back-compat kept).
    # The blackout window function stays in btc_signals so the existing test
    # suite continues to exercise it there.
    gate_cfg = cfg.get("midterm_gate")
    if gate_cfg and gate_cfg.get("enabled", False):
        from engine.btc_signals import midterm_blackout
        gate = midterm_blackout(alloc_df.index, gate_cfg)

        # Class-1 AUTO-RELEASE (owner D1): a confirmed anchor-independent
        # structural invalidation (new-ATH close × confirm_days consecutive
        # closes) releases the gate for the remainder of the window — final
        # steps down to the engine's raw allocation. Only runs when the
        # registry declares the rule AND the caller supplies the close series.
        rule = _release_rule(ctx.get("overrides"), "midterm_blackout",
                             "structural_invalidation")
        close = ctx.get("close")
        if rule is not None and close is not None and bool(gate.any()):
            confirmed = ath_invalidation_confirmed(
                close.reindex(alloc_df.index),
                int(rule.get("confirm_days", 5)))
            released = _sticky_within_windows(gate, confirmed)

        final_gate = gate & ~released
        active = active | final_gate
        oid = oid.mask(final_gate, "midterm_blackout")

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
    out["override_released"] = released.astype("int8")

    return out

