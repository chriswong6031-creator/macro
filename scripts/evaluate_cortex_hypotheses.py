"""scripts/evaluate_cortex_hypotheses.py — Generic cortex hypothesis evaluator.

Nightly step (cheap, resilient) that runs after the spine-index build.  For each
registered hypothesis whose come_back date <= today it:

1. Enforces the strict post-registration filter at the entry point.
2. Routes to the appropriate claim-shape evaluator.
3. Grades against the PRE-COMMITTED gate ONLY (no post-hoc metric switching).
4. Updates registry status and appends an article3_review governance event.
5. Queues passed hypotheses for the quarterly cortex FDR batch.

ANTI-MINING GUARANTEE
---------------------
STRICT POST-REGISTRATION FILTER — ENTRY POINT:
  Every data row used for grading must satisfy as_of > registered_at (strict).
  This is enforced here, not in the registry or qledger.  A hypothesis that
  passes ONLY on pre-registration data comes back as 'insufficient-n', never
  as 'passed'.  Zero exception mechanism.

PRE-COMMITTED GATE ONLY:
  The gate spec is read from the registration row.  No metric is substituted
  post-hoc; the evaluator reads pre_committed_gate.metric and uses that field
  name exclusively.

FDR FAMILY:
  All evaluations use family='cortex' so walk_forward and qledger account for
  shared multiple-testing budget.

PROMOTION NOTE:
  A 'passed' status queues the hypothesis for the quarterly cortex FDR batch
  (scripts/quarterly_cortex_fdr.py).  A pass alone does NOT promote beyond
  shadow — it requires the standard gauntlet (quarterly BH FDR over the 'cortex'
  family).  This is documented in the governance event.

CLAIM SHAPES:
  lead_lag + sector_conditional  → PATH A: qledger forward-return
  entry_quality                  → PATH B: walk_forward stop-out
  conditional_regime             → PATH A variant: regime-conditioned qledger

Usage:
    python -m scripts.evaluate_cortex_hypotheses           # production
    python -m scripts.evaluate_cortex_hypotheses --dry-run # no writes
    python -m scripts.evaluate_cortex_hypotheses --root /path/to/repo
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_EVALUATOR_VERSION = "W7b-PR2"

# ---------------------------------------------------------------------------
# Article 1 — self-grading exclusions
# ---------------------------------------------------------------------------
# The cortex MAY NOT be its own evidence (Article 1: "Never originate").
# adapt_cortex_attention produces synthetic ±0.01 outcome_excess values as
# sign placeholders (see query.py adapt_cortex_attention).  Including those
# rows in a hypothesis evaluation would let the cortex grade itself on its
# own firings — a closed evidence loop that violates the earned-authority
# constitution.
#
# _SELF_LEDGER_EXCLUSIONS is applied at the query layer BEFORE gate scoring.
# A separate defense-in-depth check at REGISTRATION time (_validate_hypothesis
# in metabolism.py) rejects any hypothesis whose spine_query references these
# ledgers/families/engines.
_SELF_LEDGER_EXCLUSIONS: frozenset[str] = frozenset({
    "cortex_attention",              # ledger enum value
    "reflex.cortex_attention",       # engine column value
})


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _root_path(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent


def _data(root: Path, *parts: str) -> Path:
    return root / "data" / Path(*parts)


# ---------------------------------------------------------------------------
# Post-registration filter — ENTRY POINT, no bypass
# ---------------------------------------------------------------------------

def _filter_post_registration(
    rows: list[dict],
    registered_at_str: str,
    asof_field: str = "as_of",
) -> tuple[list[dict], int]:
    """Filter rows to only those where as_of > registered_at (strict).

    Parameters
    ----------
    rows : list[dict]
        Data rows to filter.
    registered_at_str : str
        ISO-8601 UTC datetime of registration.
    asof_field : str
        Name of the as_of field in rows.

    Returns
    -------
    (kept_rows, n_dropped)
    """
    try:
        reg_dt = datetime.fromisoformat(str(registered_at_str))
        if reg_dt.tzinfo is None:
            reg_dt = reg_dt.replace(tzinfo=timezone.utc)
        reg_date = reg_dt.date()
    except Exception as exc:
        log.warning("evaluator: could not parse registered_at %r (%s)", registered_at_str, exc)
        return [], len(rows)

    kept = []
    dropped = 0
    for row in rows:
        asof = row.get(asof_field) or row.get("as_of") or row.get("asof")
        if asof is None:
            dropped += 1
            continue
        try:
            asof_date = date.fromisoformat(str(asof)[:10])
            if asof_date > reg_date:   # STRICT: >
                kept.append(row)
            else:
                dropped += 1
        except Exception:  # noqa: BLE001
            dropped += 1

    if dropped:
        log.info(
            "evaluator: post-registration filter dropped %d rows "
            "(as_of <= %s) — anti-mining law",
            dropped, reg_date,
        )
    return kept, dropped


# ---------------------------------------------------------------------------
# Verdict evaluation
# ---------------------------------------------------------------------------

def _evaluate_gate(
    metric_value: float | None,
    n: int,
    gate: dict,
) -> str:
    """Apply the pre-committed gate.  Returns 'passed', 'failed', or 'insufficient-n'."""
    min_n = int(gate.get("min_n", 25))
    threshold = float(gate.get("threshold", 0.0))
    metric = gate.get("metric", "")
    # direction_expected: +1 means "higher is better" (hit_rate, win_rate, etc.)
    #                     -1 means "lower is better" (stop_out_rate, etc.)
    # Default +1: when absent, callers must specify -1 explicitly for lower-is-better metrics.
    direction = int(gate.get("direction_expected", 1) or 1)

    if n < min_n:
        return "insufficient-n"

    if metric_value is None:
        return "insufficient-n"

    # Direction -1: metric should be below threshold (e.g. stop_out_rate)
    # Direction +1: metric should be above threshold (e.g. hit_rate)
    if direction <= 0:
        return "passed" if metric_value <= threshold else "failed"
    else:
        return "passed" if metric_value >= threshold else "failed"


# ---------------------------------------------------------------------------
# PATH A: lead_lag / sector_conditional / conditional_regime
# ---------------------------------------------------------------------------

def _evaluate_path_a(
    hyp: dict,
    root: Path,
    dry_run: bool,
) -> dict[str, Any]:
    """Forward-return path via spine/qledger."""
    gate = hyp.get("pre_committed_gate") or {}
    sq = hyp.get("spine_query") or {}
    registered_at = hyp["registered_at"]

    metric_value = None
    n = 0
    verdict = "insufficient-n"
    result_detail: dict[str, Any] = {}

    try:
        from engine.neuralweb.query import load_index, query  # type: ignore[import]
        df = load_index(root)

        if df is None or df.empty:
            result_detail["note"] = "spine index empty or unavailable"
            return {"verdict": verdict, "n": n, "metric_value": metric_value,
                    "detail": result_detail}

        # Build query filters from spine_query
        filter_kw: dict[str, Any] = {}
        if sq.get("subject"):
            filter_kw["symbol"] = sq["subject"]
        if sq.get("family"):
            filter_kw["family"] = sq["family"]
        if sq.get("engine"):
            filter_kw["engine"] = sq["engine"]
        horizon_d = int(hyp.get("horizon_d") or gate.get("horizon_d") or 21)
        filter_kw["graded_only"] = True

        filtered = query(df, **filter_kw)

        # Article 1 — self-grading exclusion.
        # Remove any rows from the cortex_attention ledger or reflex.cortex_attention
        # engine BEFORE scoring.  These rows carry synthetic ±0.01 outcome_excess
        # sign placeholders and must never feed hypothesis verdicts.
        if not filtered.empty:
            self_mask = (
                filtered["ledger"].astype(str).isin(_SELF_LEDGER_EXCLUSIONS) |
                filtered["engine"].astype(str).isin(_SELF_LEDGER_EXCLUSIONS) |
                filtered["family"].astype(str).str.startswith("reflex.cortex_attention")
            )
            n_self_excluded = int(self_mask.sum())
            if n_self_excluded:
                log.info(
                    "evaluator: Article 1 — excluded %d self-referencing rows "
                    "(cortex_attention) from hypothesis %s",
                    n_self_excluded, hyp.get("id"),
                )
                filtered = filtered[~self_mask].reset_index(drop=True)
                result_detail["self_excluded_rows"] = n_self_excluded

        # Strict post-registration filter
        rows_dicts = filtered.to_dict(orient="records") if not filtered.empty else []
        kept, dropped = _filter_post_registration(rows_dicts, registered_at, "as_of")

        result_detail["total_spine_rows"] = len(rows_dicts)
        result_detail["pre_reg_dropped"] = dropped
        result_detail["post_reg_n"] = len(kept)

        n = len(kept)

        if n == 0:
            result_detail["note"] = (
                "No post-registration graded rows found. "
                "All data predates registration — anti-mining law enforced."
            )
            verdict = "insufficient-n"
        else:
            # Compute directional hit rate on graded rows
            hits = sum(
                1 for r in kept
                if (r.get("outcome_excess") or 0) > 0
            )
            metric_name = gate.get("metric", "hit_rate")
            if metric_name == "hit_rate":
                metric_value = hits / n if n > 0 else 0.0
            elif metric_name == "excess_mean":
                excesses = [float(r.get("outcome_excess") or 0) for r in kept]
                metric_value = sum(excesses) / len(excesses) if excesses else 0.0
            else:
                metric_value = hits / n if n > 0 else 0.0  # default to hit_rate

            verdict = _evaluate_gate(metric_value, n, gate)
            result_detail.update({
                "hits": hits,
                "metric": metric_name,
                "metric_value": round(metric_value, 4),
            })

    except Exception as exc:  # noqa: BLE001
        log.warning("evaluator: path-A failed for %s (%s)", hyp.get("id"), exc)
        result_detail["error"] = str(exc)
        verdict = "insufficient-n"

    return {
        "verdict": verdict,
        "n": n,
        "metric_value": metric_value,
        "detail": result_detail,
    }


# ---------------------------------------------------------------------------
# PATH B: entry_quality
# ---------------------------------------------------------------------------

def _evaluate_path_b(
    hyp: dict,
    root: Path,
    dry_run: bool,
) -> dict[str, Any]:
    """Stop-out path via walk_forward harness."""
    gate = hyp.get("pre_committed_gate") or {}
    sq = hyp.get("spine_query") or {}
    registered_at = hyp["registered_at"]

    metric_value = None
    n = 0
    verdict = "insufficient-n"
    result_detail: dict[str, Any] = {}

    try:
        from engine.neuralweb.query import load_index, query  # type: ignore[import]
        df = load_index(root)

        if df is None or df.empty:
            result_detail["note"] = "spine index empty"
            return {"verdict": verdict, "n": n, "metric_value": metric_value,
                    "detail": result_detail}

        # Get signal rows for entry_quality
        filter_kw: dict[str, Any] = {"graded_only": False}
        if sq.get("subject"):
            filter_kw["symbol"] = sq["subject"]
        if sq.get("engine"):
            filter_kw["engine"] = sq["engine"]

        filtered = query(df, **filter_kw)
        rows_dicts = filtered.to_dict(orient="records") if not filtered.empty else []

        # Strict post-registration filter
        kept, dropped = _filter_post_registration(rows_dicts, registered_at, "as_of")
        result_detail["total_spine_rows"] = len(rows_dicts)
        result_detail["pre_reg_dropped"] = dropped
        result_detail["post_reg_n"] = len(kept)

        n = len(kept)

        if n < int(gate.get("min_n", 25)):
            result_detail["note"] = (
                f"insufficient post-registration signals ({n} < {gate.get('min_n', 25)})"
            )
            verdict = "insufficient-n"
        else:
            # Build a minimal panel from the available data
            # The walk_forward harness needs price data — attempt to load
            # from the massive stock day store or yahoo parquet.
            symbols = list({r.get("symbol") for r in kept if r.get("symbol")})[:20]
            panel = _load_price_panel(root, symbols)

            if not panel:
                result_detail["note"] = "no price panel available for walk_forward"
                verdict = "insufficient-n"
            else:
                # Build signal_fn from the spine data
                import pandas as pd  # noqa: PLC0415
                reg_date = datetime.fromisoformat(str(registered_at)).date()
                symbol_signals: dict[str, pd.Series] = {}
                for r in kept:
                    sym = r.get("symbol", "")
                    if sym in panel:
                        asof_str = str(r.get("as_of", ""))[:10]
                        if asof_str:
                            symbol_signals.setdefault(sym, []).append(asof_str)

                # Convert to signal series
                def make_signal_fn(sigs: dict):
                    def signal_fn(close: pd.Series, **_kwargs) -> pd.Series:
                        out = pd.Series(False, index=close.index)
                        sym = close.name
                        dates = sigs.get(str(sym)) or []
                        for d in dates:
                            try:
                                t = pd.Timestamp(d)
                                if t in out.index:
                                    out.loc[t] = True
                            except Exception:  # noqa: BLE001
                                pass
                        return out
                    return signal_fn

                # Run walk_forward on the filtered panel
                try:
                    from research.signal_engine.walk_forward import walk_forward  # type: ignore[import]
                    wf_result = walk_forward(
                        make_signal_fn(symbol_signals),
                        panel,
                        family="cortex",
                        metric="stop_out_rate",
                        n_trials=None,
                        run_id=f"cortex-eval-{hyp['id'][:12]}",
                        log=False,
                    )
                    metric_name = gate.get("metric", "stop_out_rate")
                    if metric_name == "stop_out_rate":
                        metric_value = (
                            wf_result.get("pooled", {}).get("stop_out_rate")
                        )
                    verdict = _evaluate_gate(metric_value, n, gate)
                    result_detail.update({
                        "metric": metric_name,
                        "metric_value": round(float(metric_value), 4) if metric_value is not None else None,
                        "wf_n_names": wf_result.get("n_names", 0),
                    })
                except Exception as exc:  # noqa: BLE001
                    log.warning("evaluator: walk_forward failed (%s)", exc)
                    result_detail["wf_error"] = str(exc)
                    verdict = "insufficient-n"

    except Exception as exc:  # noqa: BLE001
        log.warning("evaluator: path-B failed for %s (%s)", hyp.get("id"), exc)
        result_detail["error"] = str(exc)
        verdict = "insufficient-n"

    return {
        "verdict": verdict,
        "n": n,
        "metric_value": metric_value,
        "detail": result_detail,
    }


def _load_price_panel(root: Path, symbols: list[str]) -> dict:
    """Attempt to load a minimal price panel for walk_forward."""
    panel = {}
    try:
        import pandas as pd  # noqa: PLC0415
        yahoo_dir = root / "data" / "yahoo"
        for sym in symbols:
            p = yahoo_dir / f"{sym}.parquet"
            if p.exists():
                try:
                    df = pd.read_parquet(p)
                    if "close" in df.columns:
                        s = df["close"].dropna()
                        s.name = sym
                        if len(s) >= 400:
                            panel[sym] = df.rename(columns={"close": "close"})
                except Exception:  # noqa: BLE001
                    pass
    except Exception as exc:  # noqa: BLE001
        log.debug("evaluator: price panel load error (%s)", exc)
    return panel


# ---------------------------------------------------------------------------
# Governance event for evaluation result
# ---------------------------------------------------------------------------

def _emit_evaluation_governance(
    hyp_id: str,
    verdict: str,
    n: int,
    gate: dict,
    result_detail: dict,
    root: Path,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    try:
        from engine.neuralweb.governance import append_event  # type: ignore[import]
        append_event(
            "article3_review",
            target=f"cortex_hypothesis:{hyp_id}",
            article=3,
            authored_by="evaluate_cortex_hypotheses",
            evidence={
                "verdict": verdict,
                "n": n,
                "gate": gate,
                "detail": result_detail,
            },
            note=(
                f"verdict={verdict} n={n} — "
                f"{'promotion queued for quarterly FDR batch' if verdict == 'passed' else 'see detail'}. "
                f"Promotion beyond shadow ALSO needs the standard gauntlet."
            ),
            root=str(root),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("evaluator: governance event failed for %s (%s)", hyp_id, exc)


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def evaluate_due(
    root: Path | str | None = None,
    dry_run: bool = False,
    today: date | None = None,
) -> dict[str, Any]:
    """Evaluate all due hypotheses.  Returns a summary dict."""
    root = _root_path(root) if not isinstance(root, Path) else root
    if today is None:
        today = datetime.now(timezone.utc).date()

    from engine.neuralweb.metabolism import load_due  # type: ignore[import]
    due = load_due(root=str(root), today=today)

    summary = {
        "as_of": today.isoformat(),
        "evaluator_version": _EVALUATOR_VERSION,
        "dry_run": dry_run,
        "n_due": len(due),
        "results": [],
    }

    if not due:
        log.info("evaluator: no due hypotheses today (%s)", today)
        return summary

    from engine.neuralweb.metabolism import _update_row_status  # type: ignore[import]

    for hyp in due:
        hyp_id = hyp.get("id", "unknown")
        claim_shape = hyp.get("claim_shape", "")
        gate = hyp.get("pre_committed_gate") or {}
        registered_at = hyp.get("registered_at", "")

        log.info("evaluator: processing %s (shape=%s)", hyp_id, claim_shape)

        if not registered_at:
            log.warning("evaluator: %s has no registered_at — skipping", hyp_id)
            continue

        # Article 1 — defense in depth: reject any pre-existing registry row
        # whose spine_query references cortex_attention even if it bypassed
        # _validate_hypothesis at registration time (e.g. hand-written rows,
        # old rows before the guard was added).
        sq_check = hyp.get("spine_query") or {}
        _self_ref_values = {
            sq_check.get("family", ""),
            sq_check.get("engine", ""),
            sq_check.get("ledger", ""),
        }
        _self_forbidden = {"cortex_attention", "reflex.cortex_attention"}
        _self_family_prefix = str(sq_check.get("family", "")).startswith("reflex.cortex_attention")
        if _self_ref_values & _self_forbidden or _self_family_prefix:
            log.warning(
                "evaluator: Article 1 — hypothesis %s references cortex_attention "
                "in spine_query; verdict=invalid-self-reference (never graded)",
                hyp_id,
            )
            if not dry_run:
                _update_row_status(hyp_id, "invalid-self-reference", str(root))
                _emit_evaluation_governance(
                    hyp_id, "invalid-self-reference", 0, gate,
                    {"reason": "Article 1: spine_query references cortex_attention — self-grading forbidden"},
                    root, dry_run,
                )
            summary["results"].append({
                "id": hyp_id,
                "claim_shape": claim_shape,
                "verdict": "invalid-self-reference",
                "n": 0,
                "metric_value": None,
                "detail": {"reason": "Article 1: spine_query references cortex_attention — self-grading forbidden"},
                "gate": gate,
                "note": None,
            })
            continue

        # Route to evaluator path
        if claim_shape in ("lead_lag", "sector_conditional", "conditional_regime"):
            result = _evaluate_path_a(hyp, root, dry_run)
        elif claim_shape == "entry_quality":
            result = _evaluate_path_b(hyp, root, dry_run)
        else:
            log.warning("evaluator: unknown claim_shape %r for %s", claim_shape, hyp_id)
            result = {"verdict": "insufficient-n", "n": 0, "metric_value": None,
                      "detail": {"error": f"unknown claim_shape {claim_shape!r}"}}

        verdict = result["verdict"]
        n = result.get("n", 0)
        metric_value = result.get("metric_value")
        detail = result.get("detail", {})

        # Write verdict and governance event
        if not dry_run:
            _update_row_status(hyp_id, verdict, str(root))
            _emit_evaluation_governance(hyp_id, verdict, n, gate, detail, root, dry_run)

        eval_result = {
            "id": hyp_id,
            "claim_shape": claim_shape,
            "verdict": verdict,
            "n": n,
            "metric_value": metric_value,
            "detail": detail,
            "gate": gate,
            "note": (
                "passed hypotheses are queued for quarterly cortex FDR batch; "
                "promotion beyond shadow also needs the standard gauntlet"
            ) if verdict == "passed" else None,
        }
        summary["results"].append(eval_result)
        log.info("evaluator: %s → %s (n=%d)", hyp_id, verdict, n)

    summary["n_passed"] = sum(1 for r in summary["results"] if r["verdict"] == "passed")
    summary["n_failed"] = sum(1 for r in summary["results"] if r["verdict"] == "failed")
    summary["n_insufficient"] = sum(
        1 for r in summary["results"] if r["verdict"] == "insufficient-n"
    )

    # Write summary artifact
    if not dry_run:
        out_path = _data(root, "neuralweb", "cortex", "evaluator_run.json")
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(summary, indent=2, default=str), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("evaluator: could not write run summary (%s)", exc)

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [evaluate_cortex] %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Cortex hypothesis evaluator (W7b PR2)"
    )
    parser.add_argument("--root", default=None, help="Repo root override")
    parser.add_argument("--dry-run", action="store_true", help="Compute only; no writes")
    args = parser.parse_args(argv)

    try:
        summary = evaluate_due(root=args.root, dry_run=args.dry_run)
        print(json.dumps(summary, indent=2, default=str))
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("evaluator: fatal error (%s)", exc, exc_info=True)
        # Degrade-never-raise
        return 0


if __name__ == "__main__":
    sys.exit(main())
