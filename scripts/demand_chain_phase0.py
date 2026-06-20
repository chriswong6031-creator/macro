"""Phase-0 validation harness for the demand-chain divergence signal (Demand Desk;
see memory demand-desk-divergence). Answers, honestly and falsifiably: does a
"customer-capex / RPO ahead of consensus" call actually precede relative strength?

TWO HONEST TRUTHS this encodes:

1. The signal CANNOT be robustly back-tested with the data we have. Capex/RPO are
   ANNUAL (≈3-6 observations per name; the AI-capex pool is a single market-wide
   series → effectively n≈5 time periods), and there is NO point-in-time consensus
   history (the revisions feed is a forward-accruing snapshot). Any in-sample
   "backtest" would be a tiny-n, look-ahead-contaminated placebo — exactly the trap
   the SUE work fell into (see memory event-edge-gate-neutral). So we do NOT fake one.

2. The ONLY legitimate validation is the forward-scored ledger (engine/demand_ledger):
   PIT entries, machine-checkable rel_return vs SPY, graded as horizons elapse. This
   harness reads that ledger and, once enough theses are DECIDED, tests the hit-rate
   against a 50% coin-flip with an exact binomial — emitting a verdict only when the
   sample is large enough to mean anything.

Verdict ladder: PENDING (too few decided) → NEUTRAL (indistinguishable from a
placebo) → EDGE_CANDIDATE (hit-rate > 50% at p<0.05; still display-only until
replicated). Base-rate expectation, given this codebase's track record: NEUTRAL.
Writes data/demand_chain/phase0.json. Deterministic; no network.
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

log = logging.getLogger("demand_chain_phase0")
MIN_N = 20                      # decided theses required before any verdict is offered


def _load(p: Path) -> list:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def _binom_two_sided(k: int, n: int, p: float = 0.5) -> float | None:
    """Exact two-sided binomial p-value for k hits in n trials under H0: p=0.5."""
    if n == 0:
        return None

    def cdf(j: int) -> float:
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, j + 1))

    lower = cdf(k)
    upper = 1.0 - cdf(k - 1) if k > 0 else 1.0
    return min(1.0, 2.0 * min(lower, upper))


def validate(root=None, today=None) -> dict:
    root = Path(root or config.ROOT)
    today = today or date.today()
    d = root / "data" / "demand_chain"
    scored = _load(d / "scored.jsonl")
    theses = _load(d / "theses.jsonl")
    decided = [s for s in scored if s.get("outcome") in ("hit", "miss")]
    n = len(decided)
    hits = sum(1 for s in decided if s.get("outcome") == "hit")
    dir_ok = [s for s in decided if s.get("directionally_correct") is not None]
    dir_acc = (sum(1 for s in dir_ok if s.get("directionally_correct")) / len(dir_ok)) if dir_ok else None
    hit_rate = (hits / n) if n else None
    pval = _binom_two_sided(hits, n) if n else None
    open_n = sum(1 for t in theses if t.get("status") == "open" and t.get("id") not in {s["id"] for s in scored})

    if n < MIN_N:
        verdict = "PENDING"
        note = (f"{n} decided / {open_n} open. Need ≥{MIN_N} decided before a verdict means "
                "anything; the forward record is still accruing (theses grade as their ~6-month "
                "horizons elapse). The signal is NOT back-testable historically (annual cadence, "
                "no point-in-time consensus history), so this forward ledger is the only honest path.")
        note_zh = (f"已判定 {n} 个／未结 {open_n} 个。需至少 {MIN_N} 个已判定才有意义；前向记录仍在累积"
                   "（随约6个月持有期到期逐步判定）。该信号无法用历史数据回测（年度频率、无时点共识历史），"
                   "故此前向记录是唯一诚实的验证路径。")
    elif pval is not None and pval < 0.05 and (hit_rate or 0) > 0.5:
        verdict = "EDGE_CANDIDATE"
        note = (f"{hits}/{n} hits ({hit_rate:.0%}), binomial p={pval:.3f} vs a coin flip. A CANDIDATE "
                "edge — still display-only until replicated out-of-sample on a fresh cohort.")
        note_zh = (f"{n} 个中命中 {hits} 个（{hit_rate:.0%}），相对掷硬币二项检验 p={pval:.3f}。属候选优势"
                   "——在新样本外复现前仍仅作展示。")
    else:
        verdict = "NEUTRAL"
        note = (f"{hits}/{n} hits ({hit_rate:.0%}), binomial p={pval:.3f} — indistinguishable from a "
                "placebo. Stays display-only (the expected, honest outcome).")
        note_zh = (f"{n} 个中命中 {hits} 个（{hit_rate:.0%}），二项检验 p={pval:.3f}——与安慰剂无异。"
                   "维持仅展示（符合预期的诚实结论）。")

    out = {
        "schema": "demand_chain_phase0.v1",
        "as_of": today.isoformat(),
        "verdict": verdict,
        "n_decided": n, "hits": hits, "hit_rate": hit_rate,
        "binom_p_two_sided": pval, "dir_accuracy": dir_acc,
        "open": open_n, "min_n_for_verdict": MIN_N,
        "historically_backtestable": False,
        "why_not": ("Annual capex/RPO cadence (~3-6 obs; AI pool is one market-wide series → n≈5 periods) "
                    "plus NO point-in-time consensus history → any in-sample backtest is a tiny-n, "
                    "look-ahead-contaminated placebo. Forward-scored ledger only."),
        "note": note, "note_zh": note_zh,
    }
    d.mkdir(parents=True, exist_ok=True)
    (d / "phase0.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    log.info("demand_chain_phase0: verdict=%s n=%d hits=%d open=%d", verdict, n, hits, open_n)
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    v = validate()
    print(json.dumps(v, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
