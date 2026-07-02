"""Trial Ledger + the honest-N contract on deflated_sharpe.

These cover the keystone of the self-improving-AI suite's anti-p-hacking spine:
the multiple-testing N must be COUNTED (at generation, deduplicated, persisted),
not asserted by a caller who can lowball it. See research/SELF_IMPROVING_AI_SUITE.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.trial_ledger import TrialLedger
from engine.validation import deflated_sharpe, ret_moments


# --------------------------------------------------------------------------- #
# ledger mechanics
# --------------------------------------------------------------------------- #
def test_dedup_counts_distinct_configs(tmp_path):
    led = TrialLedger(tmp_path / "t.jsonl", family="fam")
    assert led.log_trial({"w": 20}) is True          # new
    assert led.log_trial({"w": 20}) is False         # exact re-run -> idempotent
    assert led.log_trial({"w": 40}) is True          # genuinely new config
    assert led.literal_n() == 2


def test_log_grid_returns_newly_distinct_and_is_idempotent(tmp_path):
    led = TrialLedger(tmp_path / "t.jsonl", family="fam")
    grid = [{"w": w, "cap": c} for w in (20, 60, 120) for c in (1.0, 1.5)]  # 6 configs
    assert led.log_grid(grid) == 6
    assert led.log_grid(grid) == 0                   # re-logging the grid adds nothing
    assert led.literal_n() == 6


def test_persists_and_reloads_from_disk(tmp_path):
    p = tmp_path / "t.jsonl"
    TrialLedger(p, family="fam").log_grid([{"w": w} for w in range(10)])
    # a fresh handle (new process, same file) must see the accumulated count
    assert TrialLedger(p, family="fam").literal_n() == 10


def test_family_is_required(tmp_path):
    led = TrialLedger(tmp_path / "t.jsonl")          # no default family
    try:
        led.log_trial({"w": 20})
    except ValueError as e:
        assert "family" in str(e)
    else:
        raise AssertionError("expected ValueError when no family is given")


def test_families_are_namespaced(tmp_path):
    led = TrialLedger(tmp_path / "t.jsonl")
    led.log_grid([{"w": w} for w in range(5)], family="a")
    led.log_grid([{"w": w} for w in range(3)], family="b")
    assert led.literal_n("a") == 5
    assert led.literal_n("b") == 3
    assert led.families() == ["a", "b"]


# --------------------------------------------------------------------------- #
# effective_n: conservative by default, floored when credit is allowed
# --------------------------------------------------------------------------- #
def test_effective_n_default_equals_literal(tmp_path):
    led = TrialLedger(tmp_path / "t.jsonl", family="fam")
    led.log_grid([{"w": w} for w in range(50)])
    assert led.effective_n() == 50                   # no credit -> count every trial


def test_correlation_credit_is_floored_at_sqrt(tmp_path):
    led = TrialLedger(tmp_path / "t.jsonl", family="fam")
    led.log_grid([{"w": w} for w in range(400)])
    # an adversary asking for 99% correlation credit cannot launder 400 -> ~4
    assert led.effective_n(correlation_credit=0.01) == 20   # ceil(sqrt(400)) floor
    # a mild, legitimate credit still reduces but stays well above the floor
    assert led.effective_n(correlation_credit=0.5) == 200


def test_effective_n_floor_one_when_empty(tmp_path):
    led = TrialLedger(tmp_path / "t.jsonl", family="fam")
    assert led.effective_n() == 1                    # never 0 -> never a div/scale blow-up


# --------------------------------------------------------------------------- #
# declared research budget: a floor that can only RAISE the haircut
# --------------------------------------------------------------------------- #
def test_declared_budget_floors_effective_n_above_itemized(tmp_path):
    led = TrialLedger(tmp_path / "t.jsonl", family="fam")
    led.log_grid([{"v": v} for v in ("a", "b", "c", "d")])   # 4 itemized variants
    led.log_declared_budget(40, reason="manual research upper-bound")
    assert led.literal_n() == 4
    assert led.declared_budget() == 40
    assert led.effective_n() == 40                   # floor wins over the 4 itemized


def test_declared_budget_never_lowers_effective_n(tmp_path):
    led = TrialLedger(tmp_path / "t.jsonl", family="fam")
    led.log_grid([{"v": v} for v in range(100)])     # 100 itemized
    led.log_declared_budget(10)                       # smaller declaration must NOT reduce N
    assert led.effective_n() == 100


def test_declared_budget_is_idempotent_and_takes_the_max(tmp_path):
    p = tmp_path / "t.jsonl"
    led = TrialLedger(p, family="fam")
    assert led.log_declared_budget(40, reason="r") is True
    assert led.log_declared_budget(40, reason="r") is False   # same (n, reason) -> no dup row
    led.log_declared_budget(64, reason="bigger")              # a higher declaration raises the floor
    assert led.effective_n() == 64
    # survives a process restart (rebuilt from disk)
    assert TrialLedger(p, family="fam").effective_n() == 64


def test_declared_budget_rejects_below_one(tmp_path):
    led = TrialLedger(tmp_path / "t.jsonl", family="fam")
    try:
        led.log_declared_budget(0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for a declared budget < 1")


def test_deflated_sharpe_uses_declared_floor(tmp_path):
    sr, sk, ku, n = _strong_series()
    led = TrialLedger(tmp_path / "t.jsonl", family="fam")
    led.log_grid([{"v": v} for v in ("a", "b", "c", "d")])
    led.log_declared_budget(40)
    by_ledger = deflated_sharpe(sr, sk, ku, n, ledger=led, family="fam")
    by_literal = deflated_sharpe(sr, sk, ku, n, n_trials=40)   # the old hand-declared path
    assert by_ledger["dsr"] == by_literal["dsr"]   # migration is behavior-preserving
    assert by_ledger["n_trials"] == 40


# --------------------------------------------------------------------------- #
# integration: deflated_sharpe honours the ledger and forbids ambiguity
# --------------------------------------------------------------------------- #
def _strong_series():
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.0010, 0.03, 4000))
    return ret_moments(r)


def test_ledger_path_matches_literal_for_equal_N(tmp_path):
    sr, sk, ku, n = _strong_series()
    led = TrialLedger(tmp_path / "t.jsonl", family="fam")
    led.log_grid([{"i": i} for i in range(37)])
    by_ledger = deflated_sharpe(sr, sk, ku, n, ledger=led, family="fam")
    by_literal = deflated_sharpe(sr, sk, ku, n, n_trials=37)
    assert by_ledger["dsr"] == by_literal["dsr"]
    assert by_ledger["n_trials"] == 37


def test_honest_N_lowers_dsr_vs_lowballed(tmp_path):
    """The whole point: a lowballed literal yields a rosier DSR than the honest count."""
    sr, sk, ku, n = _strong_series()
    led = TrialLedger(tmp_path / "t.jsonl", family="fam")
    led.log_grid([{"i": i} for i in range(60)])      # the search really tried 60 configs
    honest = deflated_sharpe(sr, sk, ku, n, ledger=led, family="fam")["dsr"]
    lowballed = deflated_sharpe(sr, sk, ku, n, n_trials=4)["dsr"]
    assert honest <= lowballed                       # honest accounting never flatters


def test_rejects_both_ledger_and_n_trials(tmp_path):
    sr, sk, ku, n = _strong_series()
    led = TrialLedger(tmp_path / "t.jsonl", family="fam")
    led.log_grid([{"i": 1}])
    try:
        deflated_sharpe(sr, sk, ku, n, n_trials=5, ledger=led, family="fam")
    except ValueError as e:
        assert "not both" in str(e)
    else:
        raise AssertionError("expected ValueError when both N sources are passed")


def test_requires_one_N_source(tmp_path):
    sr, sk, ku, n = _strong_series()
    try:
        deflated_sharpe(sr, sk, ku, n)               # neither n_trials nor ledger
    except ValueError as e:
        assert "multiple-testing N" in str(e)
    else:
        raise AssertionError("expected ValueError when no N source is given")


def test_legacy_positional_callers_unaffected():
    """The 45 existing callers pass n_trials positionally — must behave identically."""
    assert deflated_sharpe(None, 0.0, 3.0, 100, 50) is None     # thin input
    assert deflated_sharpe(0.05, 0.0, 3.0, 2, 50) is None       # T < 3
    sr, sk, ku, n = _strong_series()
    assert deflated_sharpe(sr, sk, ku, n, 10)["n_trials"] == 10


# --------------------------------------------------------------------------- #
# register_trials — the W1d budget-declaration decorator / context manager
# --------------------------------------------------------------------------- #
def test_register_trials_context_writes_declared_budget(tmp_path):
    from engine.trial_ledger import register_trials
    led = TrialLedger(tmp_path / "t.jsonl")
    with register_trials("fam_ctx", budget=40, reason="8x5 grid", ledger=led):
        pass
    # a fresh ledger on the same file must see the declared budget as a floor on N
    led2 = TrialLedger(tmp_path / "t.jsonl")
    assert led2.declared_budget("fam_ctx") == 40
    assert led2.effective_n("fam_ctx") == 40


def test_register_trials_decorator_writes_and_runs(tmp_path):
    from engine.trial_ledger import register_trials
    led = TrialLedger(tmp_path / "t.jsonl")

    @register_trials("fam_dec", budget=12, ledger=led)
    def harness():
        return "ran"

    assert harness.__trial_family__ == "fam_dec"
    assert harness.__trial_budget__ == 12
    assert harness() == "ran"                    # the wrapped fn still runs
    led2 = TrialLedger(tmp_path / "t.jsonl")
    assert led2.declared_budget("fam_dec") == 12


def test_register_trials_basis_and_expiry_stamped_in_reason(tmp_path):
    from engine.trial_ledger import register_trials
    led = TrialLedger(tmp_path / "t.jsonl")
    with register_trials("fam_fz", budget=30, reason="spvector quote",
                         basis="frozen-quote", expiry="2026-09-30", ledger=led):
        pass
    # the reason note carries the basis + expiry passport
    import json
    rows = [json.loads(l) for l in (tmp_path / "t.jsonl").read_text().splitlines() if l.strip()]
    decl = [r for r in rows if r.get("kind") == "declared_budget" and r["family"] == "fam_fz"]
    assert decl and "frozen-quote" in decl[0]["reason"] and "2026-09-30" in decl[0]["reason"]


def test_register_trials_is_idempotent(tmp_path):
    from engine.trial_ledger import register_trials
    led = TrialLedger(tmp_path / "t.jsonl")
    for _ in range(3):
        with register_trials("fam_idem", budget=20, reason="same", ledger=led):
            pass
    import json
    rows = [json.loads(l) for l in (tmp_path / "t.jsonl").read_text().splitlines() if l.strip()]
    decl = [r for r in rows if r.get("kind") == "declared_budget" and r["family"] == "fam_idem"]
    assert len(decl) == 1                         # re-running does NOT inflate N


def test_register_trials_rejects_empty_family():
    from engine.trial_ledger import register_trials
    try:
        register_trials("", budget=10)
    except ValueError:
        pass
    else:
        raise AssertionError("empty family must raise")
