"""Override-Registry apply layer for the Bitcoin Vector.

ARCHITECTURE (Override-Registry Program, W0 + W2 + W4):

  allocation() in btc_signals is now a PURE ENGINE — it computes the
  (momentum × risk × conviction × brake × overlay) allocation without any
  post-hoc masking. Human conviction overrides are DECLARED in config.yml
  under `vector.overrides:` and APPLIED here as the final word.

  apply(alloc_df, cfg, ctx=None) -> DataFrame
    Input  : the pure engine alloc_df (columns alloc_<name> for each variant)
    Output : the same frame PLUS, for every alloc_<name> column:
               alloc_<name>       final: scaled by the override release fraction
                                  (0.0 fully gated — IDENTICAL to the pre-W0
                                  live values; raw × frac while the W4 staged
                                  re-entry fills; raw after release)
               alloc_<name>_raw   the pure engine input, untouched
             and cross-variant index columns:
               override_active        int8 0/1 — 1 on every bar where an
                                      override suppresses (fully or partially)
                                      the engine output
               override_id            str — the id of the active override, ''
                                      on non-gated bars
               override_released      int8 0/1 — 1 from the bar a Class-1
                                      release confirms through the end of that
                                      override window (sticky; final == raw)
               override_release_frac  float — fraction of the raw allocation
                                      the final gets (1.0 outside engagements,
                                      0.0 fully gated, stepped while the W4
                                      tranches fill)
               reentry_trigger        str — event tokens on W4 re-entry event
                                      bars ('' elsewhere): "t1:schedule",
                                      "t2:accel_mvrv_z_lt0",
                                      "t3:accel_bottom_pressure",
                                      "class1_ath_invalidation"

  CLASS-1 AUTO-RELEASE (W2; owner decision D1, recorded 2026-07-02):
  the registry may declare a `structural_invalidation` release rule
  (signal: new_ath_close). The invalidation is ANCHOR-INDEPENDENT — a new
  all-time-high daily close (close > running historical max), NOT a comparison
  against a hand-set anchor date — held for `confirm_days` CONSECUTIVE closes
  above the broken prior ATH. On confirm the gate steps down to the engine's
  raw allocation (the brake/conviction stack then governs) for the REMAINDER
  of that override window. confirm_days is pre-committed in the masterplan and
  counted in the registry `dof_cost`; it must never be re-tuned.

  W4 — STAGED AUTO RE-ENTRY (owner decision D4; masterplan N5 as REDESIGNED
  2026-07-02 after the W1 trigger eval — research/BTC_REENTRY_TRIGGER_EVAL.md
  failed ALL SIX candidate evidence triggers against the pre-registered bar,
  so no evidence signal holds tranche AUTHORITY):
    • CALENDAR-SCHEDULED TRANCHE SPINE (the authority): the gate's release
      edge moves from election day to the thesis monitor's projected bottom
      window (cycle top + btc_cycle_thesis.WIN_LEAD_D days; 2026: Oct 1 —
      the old buy_lead_days calendar released AFTER the projected bottom).
      Tranches fill ON SCHEDULE — T1 40% at window open, T2 30% +30d,
      T3 30% +60d — deterministic, zero evidence DOF, each sized against
      the engine's RAW allocation.
    • EVIDENCE ACCELERATORS ONLY (never blockers/vetoes): one registered
      rule — a fresh MVRV-Z<0 print (≥90d non-negative prior) OR a fresh
      bottom_pressure≥0.45 cross (≥20d below prior) INSIDE the window pulls
      the NEXT scheduled tranche forward to that day. Bounded loss by
      construction: evidence can only move a fill EARLIER inside an
      already-committed window.
    • the owner halt switch (reentry.halt_from) freezes scheduled fills and
      accelerator pulls from that date; it does NOT halt the Class-1 release
      (D1 is its own governance instrument);
    • Class-1 composes: EARLIEST full release wins (a confirmed structural
      invalidation any time inside the engagement steps straight to raw and
      moots the remaining schedule).
  When no projected window is computable for an engagement (e.g. 2014 — no
  recorded prior cycle top), the legacy election-day release applies,
  bit-identical to W0/W2.

  Every override that sizes money must be graded.  The registry declaration in
  config.yml (vector.overrides) is the governance instrument; the sub-claim
  grading ledger lives in engine/btc_override_ledger.py (W5) and consumes the
  override columns this module emits.  W4 re-entry EVENTS (tranche fills /
  releases, with evidence) append to data/vector/reentry_ledger.jsonl
  (sync_ledger below) — a SEPARATE file from W5's override_ledger.jsonl, which
  is a per-date surface rewritten by its scorer (incompatible schema; two
  writers on one JSONL would clobber each other).  total_dof() feeds the
  declared dof_cost into the DSR trial budget (scripts/calibrate_vector.py) —
  the registry makes DOF more expensive, never cheaper.

  The midterm-election blackout is currently the sole registered override.
  It delegates blackout-window computation to btc_signals.midterm_blackout()
  so that tests/test_btc_signals.py::test_midterm_blackout_windows keeps
  passing unchanged.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# W4 re-entry event-token vocabulary (also the reentry ledger `trigger` values).
CAUSE_SCHEDULE = "schedule"
CAUSE_ACCEL_MVRV = "accel_mvrv_z_lt0"
CAUSE_ACCEL_BP = "accel_bottom_pressure"
TOKEN_CLASS1 = "class1_ath_invalidation"


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
# W4 staged re-entry — calendar spine + evidence accelerators
# --------------------------------------------------------------------------- #
def _projected_window(engage_start: pd.Timestamp, vector_cfg: dict):
    """The thesis monitor's projected bottom window for the cycle preceding this
    engagement: the latest recorded cycle top BEFORE the engagement whose window
    still reaches it.  Returns (window_start, window_end) or None (→ legacy
    election-day release).  ONE source of truth: btc_cycle_thesis constants."""
    from engine.btc_cycle_thesis import WIN_LEAD_D, WIN_TRAIL_D
    cpc = (vector_cfg or {}).get("cycle_phase_clock") or {}
    tops = sorted(pd.Timestamp(str(t)[:10]) for t in (cpc.get("tops") or []))
    cand = [t for t in tops
            if t < engage_start and t + pd.Timedelta(days=WIN_TRAIL_D) >= engage_start]
    if not cand:
        return None
    top = cand[-1]
    return (top + pd.Timedelta(days=WIN_LEAD_D), top + pd.Timedelta(days=WIN_TRAIL_D))


def fresh_cross_events(series: pd.Series, level: float, min_days_prior: int,
                       kind: str) -> pd.DatetimeIndex:
    """Debounced cross EVENTS per the W1 trigger-eval registered definitions
    (research/BTC_REENTRY_TRIGGER_EVAL.md): `kind='below'` — first day the
    series prints < level after >= min_days_prior consecutive days >= level;
    `kind='above'` — first day >= level after >= min_days_prior days below.
    NaN days never satisfy the prior-window requirement (conservative)."""
    s = pd.to_numeric(series, errors="coerce")
    if kind == "below":
        now = s < level
        prior_ok = (s >= level).astype(float).rolling(int(min_days_prior)).min().shift(1) == 1.0
    else:
        now = s >= level
        prior_ok = (s < level).astype(float).rolling(int(min_days_prior)).min().shift(1) == 1.0
    ev = (now & prior_ok.fillna(False)).fillna(False)
    return s.index[ev]


def _accelerator_events(rcfg: dict, ctx: dict, ws: pd.Timestamp, we: pd.Timestamp):
    """Sorted [(date, cause)] of in-window accelerator events. ONE registered
    rule (N5-redesigned): fresh MVRV-Z<0 print OR fresh bottom_pressure>=0.45
    cross. Events can only pull scheduled fills EARLIER — never block, never
    veto, never add size."""
    acfg = rcfg.get("accelerator") or {}
    if not acfg.get("enabled", False):
        return []
    events: list[tuple[pd.Timestamp, str]] = []
    mv_cfg = acfg.get("mvrv_z_fresh_cross") or {}
    if ctx.get("mvrv_z") is not None:
        for d in fresh_cross_events(ctx["mvrv_z"], float(mv_cfg.get("level", 0.0)),
                                    int(mv_cfg.get("min_days_above", 90)), "below"):
            if ws <= d <= we:
                events.append((d, CAUSE_ACCEL_MVRV))
    bp_cfg = acfg.get("bottom_pressure_fresh_cross") or {}
    if ctx.get("bottom_pressure") is not None:
        for d in fresh_cross_events(ctx["bottom_pressure"], float(bp_cfg.get("level", 0.45)),
                                    int(bp_cfg.get("min_days_below", 20)), "above"):
            if ws <= d <= we:
                events.append((d, CAUSE_ACCEL_BP))
    return sorted(events, key=lambda x: x[0])


def _reentry_engagement(idx: pd.DatetimeIndex, es: pd.Timestamp, ws: pd.Timestamp,
                        we: pd.Timestamp, rcfg: dict, ctx: dict, confirm_days: int):
    """Release plan for ONE midterm engagement with a computable window.

    Returns (frac, tokens, released_from): `frac` over the idx bars in [es, ∞)
    — 0.0 until the first fill, stepping up the tranche weights, 1.0 after full
    release; `tokens` — {date: [token, ...]} on event bars; `released_from` —
    the Class-1 release date or None."""
    span_idx = idx[idx >= es]
    tokens: dict[pd.Timestamp, list[str]] = {}
    frac = pd.Series(0.0, index=span_idx)

    tranches = [float(x) for x in (rcfg.get("tranches") or [0.40, 0.30, 0.30])]
    offsets = [int(x) for x in (rcfg.get("schedule_offsets_d") or [0, 30, 60])]
    sched = [ws + pd.Timedelta(days=o) for o in offsets[:len(tranches)]]
    halt = pd.Timestamp(rcfg["halt_from"]) if rcfg.get("halt_from") else None

    # ---- evidence accelerators pull the NEXT scheduled fill earlier ----------
    events = _accelerator_events(rcfg, ctx, ws, we)
    fills: list[tuple[pd.Timestamp, str]] = []
    ei = 0
    for k, due in enumerate(sched):
        fill, cause = due, CAUSE_SCHEDULE
        while ei < len(events):
            e, ecause = events[ei]
            if fills and e < fills[-1][0]:
                ei += 1          # chronologically consumed by an earlier fill
                continue
            if e < due:
                fill, cause = e, ecause
                ei += 1          # each event pulls at most one tranche
            break
        fills.append((fill, cause))

    # ---- walk the schedule into a fraction path (halt freezes future fills) --
    cum = 0.0
    for k, (d, cause) in enumerate(fills):
        if halt is not None and d >= halt:
            break                # owner halt: no further fills (spine + accel)
        if d > span_idx[-1]:
            break                # fill scheduled beyond the data horizon
        cum = min(cum + tranches[k], 1.0)
        frac.loc[frac.index >= d] = cum
        tokens.setdefault(d, []).append(f"t{k + 1}:{cause}")

    # ---- Class-1 composes: EARLIEST full release wins (NOT haltable — D1) ----
    released_from = None
    close = ctx.get("close")
    if close is not None and confirm_days:
        conf = ath_invalidation_confirmed(close.reindex(idx), confirm_days)
        span_end = min(max(sched[-1], we), span_idx[-1])
        hits = conf.loc[es:span_end]
        hit_days = hits.index[hits]
        if len(hit_days):
            c1 = hit_days[0]
            already_full = frac[frac >= 1.0]
            if len(already_full) == 0 or c1 < already_full.index[0]:
                released_from = c1
                frac.loc[frac.index >= c1] = 1.0
                tokens.setdefault(c1, []).append(TOKEN_CLASS1)
                for d in [d for d in tokens if d > c1]:
                    del tokens[d]  # the release moots later scheduled events

    return frac, tokens, released_from


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
    ctx : dict, optional (W2 + W4)
        Extra context the release rules need:
          close           — daily close Series for the Class-1 new-ATH
                            invalidation (W2);
          overrides       — the ``vector.overrides`` registry list (declares
                            the release rules + pre-committed parameters);
          vector_cfg      — the full ``vector`` config block (W4: the
                            projected-window calendar reads
                            cycle_phase_clock.tops);
          mvrv_z          — MVRV-Z Series (W4 accelerator, optional);
          bottom_pressure — bottom-pressure Series (W4 accelerator, optional).
        Omitting ctx (or the relevant keys) degrades gracefully: no close /
        registry → no Class-1 (W0 behavior); no vector_cfg → legacy
        election-day release (W2 behavior).

    Returns
    -------
    DataFrame
        The input columns, unmodified, renamed to ``alloc_<name>_raw``.
        Plus ``alloc_<name>`` final (scaled by the release fraction).
        Plus ``override_active`` (int8), ``override_id`` (str),
        ``override_released`` (int8), ``override_release_frac`` (float)
        and ``reentry_trigger`` (str).
    """
    ctx = ctx or {}
    out = alloc_df.copy()

    # Discover the variant allocation columns (prefix ``alloc_``).
    alloc_cols = [c for c in alloc_df.columns if c.startswith("alloc_")]

    # ---------------------------------------------------------------------- #
    # Build the combined override release fraction from all registered
    # overrides.  Today there is exactly one: the midterm-election blackout.
    # New overrides should be added here; each must fold its fraction into
    # `frac` and record its id string in `oid` for its gated rows.
    # ---------------------------------------------------------------------- #
    frac = pd.Series(1.0, index=alloc_df.index)
    oid = pd.Series("", index=alloc_df.index)
    released = pd.Series(False, index=alloc_df.index)
    tok = pd.Series("", index=alloc_df.index)

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
        c1_rule = _release_rule(ctx.get("overrides"), "midterm_blackout",
                                "structural_invalidation")
        close = ctx.get("close")
        confirm_days = int(c1_rule.get("confirm_days", 5)) if c1_rule is not None else 0
        if c1_rule is not None and close is not None and bool(gate.any()):
            confirmed = ath_invalidation_confirmed(
                close.reindex(alloc_df.index), confirm_days)
            released = _sticky_within_windows(gate, confirmed)

        # legacy path (W0/W2): binary gate until ~election day, Class-1 sticky
        frac = frac.mask(gate & ~released, 0.0)

        # W4 staged re-entry (owner D4; N5-REDESIGNED): for engagements with a
        # computable projected window, the release edge moves off the election
        # calendar onto the window spine — overwrite those engagement spans.
        rcfg = gate_cfg.get("reentry") or {}
        re_rule = _release_rule(ctx.get("overrides"), "midterm_blackout",
                                "staged_reentry")
        if (re_rule is not None and rcfg.get("enabled", False)
                and close is not None and ctx.get("vector_cfg")):
            idx = alloc_df.index
            for y in sorted({int(yr) for yr in idx.year.unique() if int(yr) % 4 == 2}):
                es = pd.Timestamp(year=y, month=1, day=1)
                window = _projected_window(es, ctx["vector_cfg"])
                if window is None:
                    continue     # 2014-style: no recorded prior top → legacy
                ws, we = max(window[0], es), window[1]
                efrac, tokens, released_from = _reentry_engagement(
                    idx, es, ws, we, rcfg, ctx, confirm_days)
                if len(efrac) == 0:
                    continue
                # the engagement owns its span until ITS full release;
                # engagements are years apart so the overwrite is exact
                span_end = efrac[efrac >= 1.0].index[0] \
                    if (efrac >= 1.0).any() else efrac.index[-1]
                span = (idx >= es) & (idx <= span_end)
                frac.loc[span] = efrac.loc[efrac.index[efrac.index <= span_end]]
                if released_from is not None:
                    released.loc[(idx >= released_from) & (idx <= we)] = True
                for d, names in tokens.items():
                    if d in tok.index:
                        tok.loc[d] = ",".join(
                            ([tok.loc[d]] if tok.loc[d] else []) + names)

        oid = oid.mask(frac < 1.0, "midterm_blackout")

    active = frac < 1.0

    # ---------------------------------------------------------------------- #
    # Emit raw columns and apply the release fraction.
    # ---------------------------------------------------------------------- #
    for col in alloc_cols:
        raw = alloc_df[col]
        out[f"{col}_raw"] = raw                      # pure engine — untouched
        final = raw.mask(frac <= 0.0, 0.0)           # fully gated: force flat
        partial = (frac > 0.0) & (frac < 1.0)
        if partial.any():
            final = final.mask(partial, raw * frac)  # tranche-scaled re-entry
        out[col] = final

    # Store override_active as int8 (0/1) rather than Python bool so the column
    # survives parquet round-trips with a stable numeric dtype and does not trip
    # bool-subtract errors in numeric pipeline checks (pandas is_numeric_dtype
    # returns True for bool, but numpy boolean subtraction is undefined).
    # Callers that need a bool mask should cast: override_active.astype(bool).
    out["override_active"] = active.astype("int8")
    out["override_id"] = oid
    out["override_released"] = released.astype("int8")
    out["override_release_frac"] = frac.astype(float)
    out["reentry_trigger"] = tok

    return out


# --------------------------------------------------------------------------- #
# W4 grading surfaces (re-entry event ledger + owner arming status)
# --------------------------------------------------------------------------- #
def _r(v, nd: int = 4):
    try:
        f = float(v)
        return None if pd.isna(f) else round(f, nd)
    except (TypeError, ValueError):
        return None


def ledger_events(sig: pd.DataFrame, vector_cfg: dict) -> list[dict]:
    """Derive W4 re-entry ledger rows from an applied signals frame (needs the
    apply() companion columns plus close / mvrv_z / bottom_pressure).  Only
    events on/after reentry.ledger_from are ledgered — engagements before the
    registry era are history, not registry rows."""
    rcfg = ((vector_cfg.get("allocation") or {}).get("midterm_gate") or {}) \
        .get("reentry") or {}
    if "reentry_trigger" not in sig.columns:
        return []
    since = pd.Timestamp(rcfg.get("ledger_from", "2026-01-01"))
    tranches = [float(x) for x in (rcfg.get("tranches") or [0.40, 0.30, 0.30])]
    events: list[dict] = []
    fired = sig.loc[(sig["reentry_trigger"] != "") & (sig.index >= since)]
    for d, row in fired.iterrows():
        for token in str(row["reentry_trigger"]).split(","):
            ev = {
                "ts": d.strftime("%Y-%m-%d"),
                "override_id": "midterm_blackout",
                "event": "full_release" if token == TOKEN_CLASS1 else "tranche_fill",
                "trigger": token.split(":", 1)[1] if ":" in token else token,
                "cum_release_frac": _r(row.get("override_release_frac", 1.0)),
                "evidence": {
                    "close": _r(row.get("close"), 2),
                    "mvrv_z": _r(row.get("mvrv_z")),
                    "bottom_pressure": _r(row.get("bottom_pressure")),
                },
            }
            if ev["event"] == "tranche_fill" and ":" in token:
                k = int(token.split(":", 1)[0].lstrip("t")) - 1
                ev["tranche_idx"] = k
                ev["tranche_weight"] = tranches[k] if k < len(tranches) else None
                ev["accelerated"] = ev["trigger"] != CAUSE_SCHEDULE
            events.append(ev)
    return events


def sync_ledger(sig: pd.DataFrame, vector_cfg: dict, path: str | Path | None = None) -> int:
    """Append NEW re-entry events to data/vector/reentry_ledger.jsonl
    (idempotent — keyed on ts/override_id/event/trigger).  Returns rows added.
    Never raises.  NOT data/vector/override_ledger.jsonl — that file is W5's
    per-date sub-claim grading surface and gets rewritten by its scorer."""
    try:
        if path is None:
            from lib import config
            path = Path(config.data_dir()) / "vector" / "reentry_ledger.jsonl"
        path = Path(path)
        events = ledger_events(sig, vector_cfg)
        if not events:
            return 0
        seen = set()
        if path.exists():
            for line in path.read_text().splitlines():
                try:
                    r = json.loads(line)
                    seen.add((r.get("ts"), r.get("override_id"),
                              r.get("event"), r.get("trigger")))
                except Exception:  # noqa: BLE001 — a corrupt line never blocks grading
                    continue
        fresh = [e for e in events
                 if (e["ts"], e["override_id"], e["event"], e["trigger"]) not in seen]
        if fresh:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a") as fh:
                for e in fresh:
                    fh.write(json.dumps(e, separators=(",", ":")) + "\n")
        return len(fresh)
    except Exception as e:  # noqa: BLE001
        log.warning("reentry ledger sync failed: %s", e)
        return 0


def build_status(sig: pd.DataFrame, vector_cfg: dict, dat: dict | None = None) -> dict:
    """Owner-view arming status for the staged re-entry (written to data/vector/
    reentry_status.json by build_vector; feeds the W3 admin BTC Override tab).
    DISPLAY-ONLY — nothing in apply() reads this.  Carries the D5 pre-window
    MVRV owner-alert field and the DAT forced-sell chip, which is ADVISORY by
    construction (a hand-maintained JSON feed must never hard-veto sizing) and
    ships with the feed's staleness flag."""
    acfg = vector_cfg.get("allocation") or {}
    gate_cfg = acfg.get("midterm_gate") or {}
    rcfg = gate_cfg.get("reentry") or {}
    last = sig.iloc[-1] if len(sig) else pd.Series(dtype=object)
    now = sig.index[-1] if len(sig) else pd.Timestamp("1970-01-01")
    # the CURRENT (or next) midterm engagement year
    y = int(now.year) + (2 - int(now.year) % 4) % 4
    es = pd.Timestamp(year=y, month=1, day=1)
    window = _projected_window(es, vector_cfg)
    tranches = [float(x) for x in (rcfg.get("tranches") or [0.40, 0.30, 0.30])]
    offsets = [int(x) for x in (rcfg.get("schedule_offsets_d") or [0, 30, 60])]
    frac = _r(last.get("override_release_frac", 1.0)) if len(sig) else None
    fired = []
    if "reentry_trigger" in sig.columns and len(sig):
        f = sig.loc[(sig["reentry_trigger"] != "") & (sig.index >= es)]
        fired = [{"ts": d.strftime("%Y-%m-%d"), "token": str(r["reentry_trigger"])}
                 for d, r in f.iterrows()]
    filled = {int(t.split(":", 1)[0].lstrip("t")): (e["ts"], t.split(":", 1)[1])
              for e in fired for t in e["token"].split(",") if ":" in t}
    schedule = []
    if window is not None:
        ws = max(window[0], es)
        for k, w in enumerate(tranches):
            d, cause = filled.get(k + 1, (None, None))
            schedule.append({
                "tranche": k + 1, "weight": w,
                "scheduled": (ws + pd.Timedelta(days=offsets[k])).strftime("%Y-%m-%d")
                             if k < len(offsets) else None,
                "filled": d is not None, "fill_date": d, "cause": cause,
            })
    if not rcfg.get("enabled", False):
        state = "disabled"
    elif window is None:
        state = "no_window"
    elif now < window[0]:
        state = "armed_pending_window"
    elif frac is not None and frac >= 1.0:
        state = "fully_released"
    else:
        state = "window_open_filling"
    # D5 (owner decision, 2026-07-02): a PRE-WINDOW fresh MVRV-Z<0 print gets
    # an owner ALERT only — never a sleeve, never sizing authority.
    pre_window_mvrv_fire = None
    if window is not None and "mvrv_z" in sig.columns and len(sig):
        acc = (rcfg.get("accelerator") or {}).get("mvrv_z_fresh_cross") or {}
        ev = fresh_cross_events(sig["mvrv_z"], float(acc.get("level", 0.0)),
                                int(acc.get("min_days_above", 90)), "below")
        hits = [d for d in ev if es <= d < window[0]]
        pre_window_mvrv_fire = hits[-1].strftime("%Y-%m-%d") if hits else None
    status = {
        "schema": "btc_reentry_status.v2",
        "asof": now.strftime("%Y-%m-%d"),
        "state": state,
        "enabled": bool(rcfg.get("enabled", False)),
        "halt_from": rcfg.get("halt_from"),
        "engagement_year": y,
        "window_start": window[0].strftime("%Y-%m-%d") if window else None,
        "window_end": window[1].strftime("%Y-%m-%d") if window else None,
        "release_frac": frac,
        "schedule": schedule,
        "events": fired,
        "accelerator": {
            "enabled": bool((rcfg.get("accelerator") or {}).get("enabled", False)),
            "rule": "fresh MVRV-Z<0 (>=90d above prior) OR fresh bottom_pressure>=0.45 "
                    "(>=20d below prior), inside the window — pulls the NEXT scheduled "
                    "tranche forward; never blocks, never vetoes, never adds size",
            "mvrv_z_last": _r(last.get("mvrv_z")),
            "bottom_pressure_last": _r(last.get("bottom_pressure")),
        },
        "pre_window_mvrv_fire": pre_window_mvrv_fire,
        "owner_note": "Calendar spine is the authority (W1 trigger eval failed all "
                      "evidence triggers). Tranches size against the engine's RAW "
                      "allocation. Halt with vector.allocation.midterm_gate.reentry."
                      "halt_from (Class-1 D1 release is not haltable).",
    }
    if dat is not None and dat.get("ok"):
        status["dat_advisory"] = {
            "advisory_only": True,
            "forced_sell_distance_pct": dat.get("forced_sell_distance_pct"),
            "asof": dat.get("asof"),
            "stale": dat.get("stale"),
            "age_days": dat.get("age_days"),
            "note": "Hand-maintained 8-K feed — NEVER a veto on re-entry sizing.",
        }
    return status
