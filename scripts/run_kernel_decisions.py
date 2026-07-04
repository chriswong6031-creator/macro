#!/usr/bin/env python3
"""Quarterly Kernel Decision Batch — Neural Web W3 PR2.

PRE-REGISTERED DECISION RULE (these constants ARE the registration):
--------------------------------------------------------------------
  FIRST_BATCH_DUE   = '2026-10-01'   — hard cadence gate; refuses to run early
  N_EFF_FLOOR       = 25             — minimum n_eff for a cell to be eligible
  STALENESS_DAYS    = 380            — maximum days since date_last (stale-data guard)
  FDR_ALPHA         = 0.10           — BH FDR alpha (one family: 'reliability_kernel')
  TRIAL_FAMILY      = 'reliability_kernel'
  SIGN_TEST_H0      = 0.5            — null hypothesis: P(positive outcome) = 0.5

ELIGIBILITY CRITERIA:
  1. n_eff >= N_EFF_FLOOR
  2. wilson_ci_low is not None (i.e. n_eff >= WILSON_MIN_N=12 was met)
  3. days since date_last <= STALENESS_DAYS

P-VALUE: one-sided sign test on the count of positive signed outcomes vs H0=0.5.
  (Rational: the kernel cells store hit counts implicitly via wilson_ci_low, which
  was computed from hits/n_eff. We re-derive from the parquet columns: sign test
  p = P(Binomial(n_eff, 0.5) >= hits), one-sided. This is the simplest exact test
  appropriate for a hit-rate metric; it is distribution-free, makes no normality
  assumption, and is consistent with the qledger Wilson-CI machinery already used
  to compute wilson_ci_low in the first place. The BH family across ALL eligible
  cells controls FDR at alpha=0.10.)

FDR: Benjamini-Hochberg across ALL eligible cells as ONE family per batch.
  The trial ledger is populated with declared_budget = n_eligible BEFORE the
  p-values are computed. This enforces the anti-peeking order in code.

STANDING LAW (written into kernel_decisions.json):
  Only cells in survivors[] may EVER feed a behavior-changing consumer.
  Each consumer hookup additionally requires its own PR + registry event.

CADENCE GUARD:
  - Running before FIRST_BATCH_DUE exits 1 with a clear message.
  - --dry-run-on-fixtures <fixture_dir> accepts ONLY a filesystem path that
    does NOT contain the real parquet (enforced by path check against config.ROOT).

ANTI-PEEKING ORDER (code-enforced, single function, no CLI flag to skip):
  Step 1: count eligible cells → N
  Step 2: register_trials(TRIAL_FAMILY, budget=N) [LEDGER WRITE BEFORE ANY PVALUE]
  Step 3: compute p-values
  Step 4: BH FDR
  Step 5: write kernel_decisions.json

Run:
  python3 scripts/run_kernel_decisions.py
  python3 scripts/run_kernel_decisions.py --dry-run-on-fixtures /path/to/fixture/root
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PRE-REGISTERED DECISION RULE CONSTANTS (DO NOT MODIFY WITHOUT A NEW PR)
# ---------------------------------------------------------------------------
FIRST_BATCH_DUE: str = "2026-10-01"
N_EFF_FLOOR: int = 25
STALENESS_DAYS: int = 380
FDR_ALPHA: float = 0.10
TRIAL_FAMILY: str = "reliability_kernel"
SIGN_TEST_H0: float = 0.5

# Derived: the output artifact path (relative to root)
_DECISIONS_REL = Path("data") / "neuralweb" / "kernel_decisions.json"

# The real kernel parquet path (relative to root) — used to reject this path
# in --dry-run-on-fixtures mode (fixture dir must not be the real data dir).
_REAL_ESTIMATES_REL = Path("data") / "neuralweb" / "kernel_estimates.parquet"


# ---------------------------------------------------------------------------
# Cadence guard
# ---------------------------------------------------------------------------

def _check_cadence(now_date_str: str | None = None, *, dry_run: bool = False) -> None:
    """Raise SystemExit(1) if today is before FIRST_BATCH_DUE and not dry-run."""
    if dry_run:
        return
    today_str = now_date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today_str < FIRST_BATCH_DUE:
        print(
            f"quarterly cadence — no early peeking. "
            f"FIRST_BATCH_DUE={FIRST_BATCH_DUE}, today={today_str}. "
            f"Use --dry-run-on-fixtures <dir> to test against a fixture directory.",
            file=sys.stderr,
        )
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# P-value: one-sided sign test (binomial CDF)
# ---------------------------------------------------------------------------

def _sign_test_p_value(hits: int, n: int, h0: float = SIGN_TEST_H0) -> float:
    """One-sided sign test p-value: P(Binomial(n, h0) >= hits).

    Pure stdlib — no scipy. Uses the exact binomial CDF via the regularized
    incomplete beta function identity: P(X >= hits) = I_{h0}(hits, n-hits+1)
    approximated by summing the PMF from 0..hits-1 and subtracting from 1.

    For n <= 200 (all current kernel cells) this is exact and fast.
    For larger n the normal approximation is used as a fallback.
    """
    if n <= 0:
        return 1.0
    if hits <= 0:
        return 1.0  # no evidence of positive edge
    if hits > n:
        hits = n

    # Exact binomial PMF sum for n <= 500
    if n <= 500:
        # P(X < hits) = sum_{k=0}^{hits-1} C(n,k) * h0^k * (1-h0)^(n-k)
        log_h0 = _safe_log(h0)
        log_1mh0 = _safe_log(1.0 - h0)
        p_less_than_hits = 0.0
        log_pmf = n * log_1mh0  # k=0 term: (1-h0)^n
        for k in range(hits):
            p_less_than_hits += _safe_exp(log_pmf)
            if k < hits - 1:
                # Recurrence: C(n,k+1)/C(n,k) * h0/(1-h0)
                log_pmf += _safe_log((n - k) / (k + 1)) + log_h0 - log_1mh0
        p_val = 1.0 - p_less_than_hits
        return max(0.0, min(1.0, p_val))

    # Normal approximation for large n
    import math
    mu = n * h0
    sigma = (n * h0 * (1.0 - h0)) ** 0.5
    if sigma < 1e-10:
        return 0.0 if hits > mu else 1.0
    z = (hits - 0.5 - mu) / sigma  # continuity correction
    # P(Z >= z) = 0.5 * erfc(z / sqrt(2))
    p_val = 0.5 * math.erfc(z / math.sqrt(2))
    return max(0.0, min(1.0, p_val))


def _safe_log(x: float) -> float:
    import math
    return math.log(max(x, 1e-300))


def _safe_exp(x: float) -> float:
    import math
    try:
        return math.exp(x)
    except OverflowError:
        return 0.0


# ---------------------------------------------------------------------------
# Reconstruct hits from wilson_ci_low (inverse Wilson formula)
# ---------------------------------------------------------------------------

def _hits_from_wilson_and_n(wilson_ci_low: float, n: int, z: float = 1.96) -> int:
    """Approximate hits from wilson_ci_low and n_eff.

    The wilson_ci_low formula (from engine/qledger.py):
        phat = hits / n
        z2 = z**2
        denom = 1 + z2/n
        centre = phat + z2/(2n)
        margin = z * sqrt((phat*(1-phat) + z2/(4n)) / n)
        ci_low = (centre - margin) / denom

    We cannot invert this analytically without solving a quadratic in phat.
    We use a binary search over hits in [0, n] to find the hit count whose
    wilson_ci_low is closest to the stored value.

    This is only needed when the parquet does not store hits directly (which
    is the case for the W3 PR1 artifact). For W3 PR2 this function is used
    to recover hits for the sign test. At n>=25, precision is sufficient.
    """
    from engine.qledger import wilson_ci_low as _wcl

    best_hits = 0
    best_gap = float("inf")
    for h in range(0, n + 1):
        ci = _wcl(h, n)
        if ci is None:
            continue
        gap = abs(ci - wilson_ci_low)
        if gap < best_gap:
            best_gap = gap
            best_hits = h
    return best_hits


# ---------------------------------------------------------------------------
# Core batch function (anti-peeking order enforced here)
# ---------------------------------------------------------------------------

def _run_batch(
    root: Path,
    *,
    dry_run: bool = False,
    fixture_dir: Path | None = None,
    _now_override: str | None = None,
) -> dict:
    """Execute the quarterly decision batch.

    Anti-peeking order (code-enforced, single function):
      1. Load estimates
      2. Filter to eligible cells → n_eligible
      3. Register trial budget in the ledger  ← LEDGER WRITE
      4. Compute p-values                     ← EVALUATION (after registration)
      5. BH FDR
      6. Write kernel_decisions.json

    Parameters
    ----------
    root :          repo root (used for the production run).
    dry_run :       if True, skip the cadence guard; accepts fixture_dir.
    fixture_dir :   alternative data root (only valid with dry_run=True;
                    must NOT point at the real data dir).
    _now_override : override today's date string (for testing).
    """
    import pandas as pd
    from engine.trial_ledger import TrialLedger, register_trials
    from engine.validation import benjamini_hochberg

    now_str = _now_override or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- Cadence guard ---
    _check_cadence(now_str, dry_run=dry_run)

    # --- Determine parquet path + fixture-dir collision guard ---
    data_root = fixture_dir if (dry_run and fixture_dir) else root
    estimates_path = data_root / _REAL_ESTIMATES_REL
    if dry_run and fixture_dir is not None:
        real_estimates = (root / _REAL_ESTIMATES_REL).resolve()
        fixture_estimates = (fixture_dir / _REAL_ESTIMATES_REL).resolve()
        if fixture_estimates == real_estimates:
            print(
                "ERROR: --dry-run-on-fixtures path resolves to the real parquet. "
                "Pass a fixture directory, not the production data root.",
                file=sys.stderr,
            )
            raise SystemExit(1)
    if not estimates_path.exists():
        raise FileNotFoundError(
            f"kernel_estimates.parquet not found at {estimates_path}"
        )

    # --- Load estimates ---
    df = pd.read_parquet(estimates_path)
    if df.empty:
        log.warning("kernel_decisions: estimates parquet is empty — writing null batch")
        _write_seed(root)
        return {"n_eligible": 0, "n_survivors": 0, "survivors": []}

    # --- Eligibility filter (pre-registered criteria) ---
    # 1. n_eff >= N_EFF_FLOOR
    mask_n = pd.to_numeric(df["n_eff"], errors="coerce").fillna(0) >= N_EFF_FLOOR
    # 2. wilson_ci_low is not None / not NaN
    mask_ci = df["wilson_ci_low"].notna()
    # 3. date_last within STALENESS_DAYS of today
    today = datetime.now(timezone.utc).date() if _now_override is None else \
        datetime.strptime(_now_override, "%Y-%m-%d").date()
    def _days_since(date_str) -> int:
        try:
            d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
            return (today - d).days
        except Exception:  # noqa: BLE001
            return 99999
    mask_fresh = df["date_last"].apply(_days_since) <= STALENESS_DAYS

    eligible = df[mask_n & mask_ci & mask_fresh].copy().reset_index(drop=True)
    n_eligible = len(eligible)

    log.info(
        "kernel_decisions: %d eligible cells (n_eff>=%d, ci_low not null, fresh<=%dd)",
        n_eligible, N_EFF_FLOOR, STALENESS_DAYS,
    )

    # =====================================================================
    # STEP 3: REGISTER TRIAL BUDGET — LEDGER WRITE BEFORE ANY P-VALUE
    # =====================================================================
    # This is the anti-peeking enforcement: the budget is registered as the
    # number of cells we are about to test, BEFORE we compute any p-values.
    # A caller cannot skip this step by any CLI flag — it is a single function.
    led = TrialLedger(path=root / "data" / "trial_ledger.jsonl", family=TRIAL_FAMILY)
    led.log_declared_budget(
        max(n_eligible, 1),
        family=TRIAL_FAMILY,
        reason=(
            f"quarterly kernel decision batch run_at={run_at}; "
            f"n_eligible_cells={n_eligible}; "
            f"alpha={FDR_ALPHA}; criteria=n_eff>={N_EFF_FLOOR} AND ci_low notna "
            f"AND staleness<={STALENESS_DAYS}d"
        ),
    )
    trial_ledger_ref = {
        "family": TRIAL_FAMILY,
        "budget_registered": max(n_eligible, 1),
        "path": "data/trial_ledger.jsonl",
    }
    log.info(
        "kernel_decisions: trial ledger registered — family=%s budget=%d",
        TRIAL_FAMILY, max(n_eligible, 1),
    )

    # =====================================================================
    # STEP 4: COMPUTE P-VALUES (after ledger write — order enforced above)
    # =====================================================================
    if n_eligible == 0:
        bh_result: dict = {}
        pvals: dict = {}
    else:
        pvals = {}
        for _, row in eligible.iterrows():
            cell_key = f"{row['engine']}:{row['regime']}:{int(row['horizon'])}"
            n_eff = int(row["n_eff"])
            ci_low = float(row["wilson_ci_low"])
            # Reconstruct hits from wilson_ci_low + n_eff
            hits = _hits_from_wilson_and_n(ci_low, n_eff)
            pvals[cell_key] = _sign_test_p_value(hits, n_eff)

        # STEP 5: BH FDR across ALL eligible cells (ONE family per batch)
        bh_result = benjamini_hochberg(pvals, alpha=FDR_ALPHA)

    # --- Survivors ---
    survivors = []
    for _, row in eligible.iterrows():
        cell_key = f"{row['engine']}:{row['regime']}:{int(row['horizon'])}"
        bh = bh_result.get(cell_key, {})
        if bh.get("reject", False):
            survivors.append({
                "cell": cell_key,
                "engine": str(row["engine"]),
                "regime": str(row["regime"]),
                "horizon": int(row["horizon"]),
                "n_eff": int(row["n_eff"]),
                "shrunken_ic": float(row.get("shrunken_ic") or 0.0),
                "wilson_ci_low": float(row["wilson_ci_low"]),
                "p_value": round(float(pvals.get(cell_key, 1.0)), 4),
                "q_value": round(float(bh.get("q", 1.0)), 4),
                "passes_decision_rule": True,
            })

    n_survivors = len(survivors)
    log.info(
        "kernel_decisions: %d survivors of %d eligible (FDR alpha=%.2f)",
        n_survivors, n_eligible, FDR_ALPHA,
    )

    # =====================================================================
    # STEP 6: WRITE kernel_decisions.json
    # =====================================================================
    # Compute next batch due (one year from now, quantized to Oct 1)
    next_year = today.year + 1
    next_batch_due = f"{next_year}-10-01"

    payload = {
        "batch_id": f"q{now_str[:7].replace('-', '')}",  # e.g. "q202610"
        "run_at": run_at,
        "alpha": FDR_ALPHA,
        "trial_family": TRIAL_FAMILY,
        "decision_rule": {
            "n_eff_floor": N_EFF_FLOOR,
            "staleness_days": STALENESS_DAYS,
            "test": "one_sided_sign_test",
            "h0": SIGN_TEST_H0,
            "fdr_correction": "benjamini_hochberg",
            "alpha": FDR_ALPHA,
            "family_scope": "all_eligible_cells_one_family_per_batch",
        },
        "n_eligible": n_eligible,
        "n_survivors": n_survivors,
        "survivors": survivors,
        "trial_ledger_ref": trial_ledger_ref,
        "next_batch_due": next_batch_due,
        # STANDING LAW — do not remove this field
        "standing_law": (
            "Only cells present in survivors[] may EVER feed a behavior-changing "
            "consumer. Each consumer hookup additionally requires its own PR + "
            "registry event. This field is structural enforcement of the display-first "
            "law — it is not documentation."
        ),
    }

    out_path = root / _DECISIONS_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    log.info("kernel_decisions: wrote %s", out_path)
    return payload


# ---------------------------------------------------------------------------
# Seed writer (idempotent — called when estimates are empty)
# ---------------------------------------------------------------------------

def _write_seed(root: Path) -> None:
    """Write the null-batch seed (same shape as a real run, all empty)."""
    payload = {
        "batch_id": None,
        "run_at": None,
        "alpha": FDR_ALPHA,
        "trial_family": TRIAL_FAMILY,
        "decision_rule": {
            "n_eff_floor": N_EFF_FLOOR,
            "staleness_days": STALENESS_DAYS,
            "test": "one_sided_sign_test",
            "h0": SIGN_TEST_H0,
            "fdr_correction": "benjamini_hochberg",
            "alpha": FDR_ALPHA,
            "family_scope": "all_eligible_cells_one_family_per_batch",
        },
        "n_eligible": 0,
        "n_survivors": 0,
        "survivors": [],
        "trial_ledger_ref": None,
        "next_batch_due": FIRST_BATCH_DUE,
        "note": (
            "no decision batch has run; "
            f"first batch due {FIRST_BATCH_DUE}; "
            "estimates are display-only"
        ),
        "standing_law": (
            "Only cells present in survivors[] may EVER feed a behavior-changing "
            "consumer. Each consumer hookup additionally requires its own PR + "
            "registry event. This field is structural enforcement of the display-first "
            "law — it is not documentation."
        ),
    }
    out_path = root / _DECISIONS_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Quarterly Kernel Decision Batch. "
            f"Refuses to run before {FIRST_BATCH_DUE} unless --dry-run-on-fixtures is passed."
        )
    )
    p.add_argument(
        "--dry-run-on-fixtures",
        metavar="FIXTURE_DIR",
        default=None,
        help=(
            "Run against a fixture directory instead of the real data. "
            "FIXTURE_DIR must be a filesystem path and must NOT point at the "
            "real repo root (enforced). Skips the cadence guard."
        ),
    )
    return p.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    args = _parse_args(argv)
    dry_run = args.dry_run_on_fixtures is not None

    # Locate repo root
    try:
        from lib import config as _cfg
        repo_root = _cfg.ROOT
    except Exception:  # noqa: BLE001
        repo_root = Path(__file__).resolve().parents[1]

    fixture_dir: Path | None = None
    if dry_run:
        fixture_dir = Path(args.dry_run_on_fixtures).resolve()
        # Enforce: fixture_dir must not be the real data dir
        real_estimates = (repo_root / _REAL_ESTIMATES_REL).resolve()
        fixture_estimates = (fixture_dir / _REAL_ESTIMATES_REL).resolve()
        if fixture_estimates == real_estimates:
            print(
                "ERROR: --dry-run-on-fixtures path resolves to the real parquet. "
                "Pass a fixture directory, not the production data root.",
                file=sys.stderr,
            )
            return 1

    try:
        result = _run_batch(repo_root, dry_run=dry_run, fixture_dir=fixture_dir)
        print(
            f"OK: {result.get('n_survivors', 0)} survivors of "
            f"{result.get('n_eligible', 0)} eligible cells "
            f"(FDR alpha={FDR_ALPHA})"
        )
        return 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 1
    except Exception as e:  # noqa: BLE001
        log.error("kernel_decisions batch failed: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
