#!/usr/bin/env python3
"""Freeze the three outcome-blind PSS follow-on programs.

This is a one-time registration utility.  It reads only the already-frozen
PSS-RH1 registration, the pre-cutoff FINRA short-volume prefix, and source
availability.  It never constructs an event or reads a forward outcome.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.trial_ledger import TrialLedger  # noqa: E402


FROZEN_AT = "2026-07-27T23:02:00Z"
NOT_BEFORE_SESSION = "2026-07-24"
SOURCE_COMMIT = "e61042bf70fe2ca61db5bc55e163c9e208927b02"

BASE = ROOT / "data/personality_timing"
RH1_MANIFEST = BASE / "relief_hazard_manifest_v1.json"
RH1_MEMBERSHIP = BASE / "relief_hazard_membership_v1.json"
RH1_MANIFEST_SHA256 = (
    "0b07345178592032570aeb57c1c54c1cb24b6463a5836431bc7daf5d44b0cc6b"
)
RH1_MEMBERSHIP_SHA256 = (
    "f00c9d70e0c554213d6aa9a82fecc1492bcedc49c04ce36d4a14647f85713baf"
)
CR1_MANIFEST = BASE / "challenge_resilience_manifest_v1.json"
CR1_MANIFEST_SHA256 = (
    "0b520e60616d60f4c4182e9796bbf4e23cc58279ccf2b0b2d03eb3cec3c352e1"
)

FINRA_PANEL = ROOT / "data/finra_short_volume/panel.parquet"
FINRA_PREFIX_END = "2026-07-21"
FINRA_PREFIX_ROWS = 51_960
FINRA_PREFIX_SHA256 = (
    "4d7165ff3346c7bdaaf28e0b4064f1eda4311a1600f3df33509e8d03d183bbf6"
)

TRIAL_LEDGER = ROOT / "data/trial_ledger.jsonl"

AUTHORITY = {
    "research_only": True,
    "may_enter": False,
    "may_rank": False,
    "may_size": False,
    "may_gate": False,
    "may_alert": False,
    "may_display_to_users": False,
    "may_auto_promote": False,
}

GRADE = {
    "maturity_sessions_after_action": 63,
    "outcomes_begin": "session_after_action",
    "mae63": "minimum close return over action+1 through action+63",
    "tail10": "mae63<=-10%",
    "proximity_window": "minimum close action-31 through action+31",
    "w5": "action close within 5% above proximity-window minimum",
    "called": "proximity trough offset -2 through +5 sessions",
    "tdt": "signed action-minus-trough trading-session offset",
    "competing_risk": {
        "rebound": "close>=action_close*1.08",
        "breach": "low<reference_low-0.50*anchor_atr",
        "tie": "breach_wins",
        "unresolved": "retained_as_failure",
    },
}

CR1_CONSTRUCTION = {
    "construction_id": "pss_cr1_first_peer_pullback_resilience_v1",
    "source": {
        "program_id": "PSS-RH1",
        "ledger": "data/personality_timing/relief_hazard.jsonl",
        "group": "relief_hazard",
        "source_action": "B_close",
        "historical_source_rows_allowed": False,
    },
    "challenge": {
        "same_sector_ex_self_membership": "frozen_PSS_RH1_membership",
        "minimum_valid_peers": 15,
        "peer_statistic": "cross_sectional_median_simple_return_over_3_sessions",
        "return_definition": "close[C]/close[C-3]-1",
        "search_completion_sessions_after_B_inclusive": [5, 20],
        "first_completion_only": True,
        "threshold_at_B": {
            "window_sessions": 126,
            "minimum_valid_metric_sessions": 63,
            "quantile": 0.20,
            "information_cutoff": "B_minus_1_close",
        },
        "qualifies": "peer_return_3[C]<0 and peer_return_3[C]<=frozen_q20_at_B",
        "challenge_start": "C_minus_2",
        "action": "C_close",
    },
    "primary_eligibility": {
        "no_subject_breach_B_plus_1_through_C": (
            "minimum_low>=reference_low-0.50*anchor_atr"
        ),
        "held_recovery_during_challenge": (
            "each_close_C_minus_2_through_C>=reference_low+0.50*anchor_atr"
        ),
    },
    "leadership": {
        "return_window": "close[C]/close[C-3]-1",
        "cross_section": "subject_plus_valid_ex_self_peers",
        "minimum_percentile_inclusive": 0.75,
        "minimum_relative_return": "0.50*anchor_atr/source_action_close",
        "requires_both": True,
    },
    "labels": {
        "resilient_leader": "primary eligible and both leadership tests pass",
        "challenged_control": "primary eligible and either leadership test fails",
        "failed_hold_diagnostic": "challenge exists but primary eligibility fails",
    },
    "fixed_bands": {
        "challenge_return": ["(-inf,-0.04]", "(-0.04,-0.02]", "(-0.02,0)"],
    },
}

CD1_CONSTRUCTION = {
    "construction_id": "pss_cd1_peer_factor_crowding_v1",
    "source": {
        "program_id": "PSS-RH1",
        "ledger": "data/personality_timing/relief_hazard.jsonl",
        "group": "relief_hazard",
        "action": "same_B_close",
        "historical_source_rows_allowed": False,
    },
    "peers": {
        "same_sector_ex_self_membership": "frozen_PSS_RH1_membership",
        "minimum_valid_peers": 15,
    },
    "metrics": {
        "pc1_share": {
            "return_sessions": 10,
            "matrix": "peer daily simple returns, each peer population-standardized",
            "definition": "largest_singular_value_squared/sum_all_singular_values_squared",
        },
        "dispersion_5": {
            "definition": (
                "cross_sectional_median_absolute_deviation_of_peer_"
                "close[t]/close[t-5]-1"
            ),
        },
    },
    "pit_thresholds": {
        "metric_sessions_before_B": 126,
        "minimum_valid_metric_sessions": 63,
        "pc1_quantile": 0.80,
        "dispersion_quantile": 0.20,
        "information_cutoff": "B_minus_1_close",
    },
    "labels": {
        "crowding_hazard": "pc1_share>=prior_q80 and dispersion_5<=prior_q20",
        "uncrowded_control": "pc1_share<prior_q80 and dispersion_5>prior_q20",
        "mixed_diagnostic": "exactly one extreme condition is true",
    },
}

AF1_CONSTRUCTION = {
    "construction_id": "pss_af1_finra_short_marked_absorption_witness_v1",
    "source": {
        "program_id": "PSS-CR1",
        "ledger": "data/personality_timing/challenge_resilience.jsonl",
        "group": "resilient_leader",
        "action": "same_C_close",
        "historical_source_rows_allowed": False,
    },
    "flow_source": {
        "dataset": "FINRA consolidated daily short-sale volume",
        "path": "data/finra_short_volume/panel.parquet",
        "required_columns": [
            "date",
            "ticker",
            "short_vol",
            "short_exempt",
            "total_vol",
            "short_ratio",
        ],
        "interpretation": (
            "short-marked transaction activity, not short interest, net bearish "
            "inventory, or a standalone directional signal"
        ),
    },
    "baseline": {
        "sessions": 20,
        "dates": "the 20 subject trading sessions immediately before challenge_start",
        "coverage_required": "all_20_FINRA_rows",
        "rolling_comparable_windows": "all_18_overlapping_3_session_windows",
    },
    "challenge_window": {
        "dates": "challenge_start_through_C_exactly_3_subject_sessions",
        "coverage_required": "all_3_FINRA_rows",
        "short_ratio": "sum(short_vol)/sum(total_vol)",
        "activity": "mean(total_vol)",
    },
    "labels": {
        "flow_witness": (
            "challenge_short_ratio>=prior_18_window_q75 and "
            "challenge_mean_total_vol>=prior_20_session_median_total_vol"
        ),
        "leader_flow_control": (
            "challenge_short_ratio<prior_18_window_q75 and "
            "challenge_mean_total_vol>=prior_20_session_median_total_vol"
        ),
        "low_activity_diagnostic": (
            "challenge_mean_total_vol<prior_20_session_median_total_vol"
        ),
        "missing_flow_diagnostic": "required_20_plus_3_exact_date_coverage_missing",
    },
    "quantile": {
        "value": 0.75,
        "method": "linear",
        "information_cutoff": "challenge_start_minus_1_close",
    },
}


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _finra_prefix_bytes(frame: pd.DataFrame) -> bytes:
    columns = [
        "date",
        "ticker",
        "short_vol",
        "short_exempt",
        "total_vol",
        "short_ratio",
    ]
    prefix = frame.loc[
        pd.to_datetime(frame["date"]).dt.normalize() <= pd.Timestamp(FINRA_PREFIX_END),
        columns,
    ].copy()
    prefix["date"] = pd.to_datetime(prefix["date"]).dt.normalize()
    prefix = prefix.sort_values(["date", "ticker"]).reset_index(drop=True)
    lines = []
    for row in prefix.itertuples(index=False):
        lines.append(
            "|".join(
                [
                    str(row.date.date()),
                    str(row.ticker),
                    format(float(row.short_vol), ".12g"),
                    format(float(row.short_exempt), ".12g"),
                    format(float(row.total_vol), ".12g"),
                    format(float(row.short_ratio), ".12g"),
                ]
            )
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _validate_sources() -> dict[str, object]:
    if _sha256_file(RH1_MANIFEST) != RH1_MANIFEST_SHA256:
        raise RuntimeError("PSS-RH1 manifest changed before follow-on freeze")
    if _sha256_file(RH1_MEMBERSHIP) != RH1_MEMBERSHIP_SHA256:
        raise RuntimeError("PSS-RH1 membership changed before follow-on freeze")
    membership = json.loads(RH1_MEMBERSHIP.read_text(encoding="utf-8"))
    members = {str(row["sym"]) for row in membership["members"]}

    panel = pd.read_parquet(FINRA_PANEL)
    prefix = panel[
        pd.to_datetime(panel["date"]).dt.normalize() <= pd.Timestamp(FINRA_PREFIX_END)
    ]
    prefix_hash = _sha256_bytes(_finra_prefix_bytes(panel))
    if len(prefix) != FINRA_PREFIX_ROWS or prefix_hash != FINRA_PREFIX_SHA256:
        raise RuntimeError("FINRA stable historical prefix changed before freeze")
    covered = set(panel["ticker"].dropna().astype(str)) & members
    return {
        "rh1_member_count": len(members),
        "finra_first_session": str(pd.to_datetime(panel["date"]).min().date()),
        "finra_latest_session": str(pd.to_datetime(panel["date"]).max().date()),
        "finra_session_count": int(pd.to_datetime(panel["date"]).nunique()),
        "finra_rh1_member_count": len(covered),
        "finra_missing_members": sorted(members - covered),
        "finra_prefix_end": FINRA_PREFIX_END,
        "finra_prefix_rows": len(prefix),
        "finra_prefix_sha256": prefix_hash,
    }


def _decision_law(
    *,
    treatment: str,
    control: str,
    minimums: dict[str, int],
    harm: bool,
    seed: int,
) -> dict[str, object]:
    if harm:
        signs = {
            "mae": f"{control}_mae_minus_{treatment}_mae",
            "tail10": f"{treatment}_tail_rate_minus_{control}_tail_rate",
            "w5": f"{control}_w5_rate_minus_{treatment}_w5_rate",
            "rebound8_first": (
                f"{control}_rebound_first_rate_minus_{treatment}_rebound_first_rate"
            ),
        }
        sign_word = "harm"
    else:
        signs = {
            "mae": f"{treatment}_mae_minus_{control}_mae",
            "tail10": f"{control}_tail_rate_minus_{treatment}_tail_rate",
            "w5": f"{treatment}_w5_rate_minus_{control}_w5_rate",
            "rebound8_first": (
                f"{treatment}_rebound_first_rate_minus_{control}_rebound_first_rate"
            ),
        }
        sign_word = "benefit"
    return {
        "authority_now": "none",
        "interim_outcome_reads": "forbidden",
        "read_count": 1,
        "first_read_requires_all": minimums,
        "inference_tape": {
            "deduplication": "keep first primary action per name per calendar month",
            "stratum": (
                "sector x action_month x source_anchor_severity_band x "
                "source_delay_band"
            ),
            "minimum_per_label_in_stratum": 2,
            "aggregation": "equal weight across informative strata",
            "permutation": {
                "labels_move_only_within_stratum": True,
                "draws": 10_000,
                "seed": seed,
                "one_sided_alpha": 0.05,
            },
            "bootstrap": {
                "unit": "three-calendar-month moving block",
                "draws": 5_000,
                "seed": seed + 1,
                "confidence": 0.95,
            },
        },
        f"{sign_word}_signs": signs,
        "qualification_requires_all": [
            f"mae {sign_word}>0, one-sided permutation p<=0.05, and block-CI lower>0",
            f"tail10 {sign_word}>0, one-sided permutation p<=0.05, and block-CI lower>0",
            f"w5 and rebound8_first {sign_word}>0",
            f"mae and tail10 {sign_word}>0 in chronological early and late halves",
            f"leave-one-sector-out mae and tail10 {sign_word} stay>0",
            f"no sector supplies more than 25% of {treatment} rows",
        ],
        "ruling": (
            "Qualification authorizes only a separate preregistered intervention "
            "shadow. It never creates entry, rank, size, gate, alert, display, or "
            "automatic promotion authority. Failure kills this exact construction."
        ),
    }


PROGRAMS = (
    {
        "program_id": "PSS-CR1",
        "family": "pss_cr1_challenge_resilience_prospective",
        "schema": "personality_challenge_resilience.manifest/v1",
        "manifest": BASE / "challenge_resilience_manifest_v1.json",
        "construction": CR1_CONSTRUCTION,
        "hypothesis": (
            "Inside a prospectively observed RH1 synchronized-relief hazard, a "
            "subject that preserves its frozen recovery and remains top-quartile "
            "during the first independently defined peer pullback has lower "
            "subsequent drawdown and tail risk than an equally held but non-leading "
            "subject exposed to the same challenge."
        ),
        "treatment": "resilient_leader",
        "control": "challenged_control",
        "harm": False,
        "minimums": {
            "matured_primary_rows": 300,
            "unique_names": 150,
            "resilient_leader_rows": 75,
            "challenged_control_rows": 75,
            "distinct_action_months": 12,
            "action_date_span_days": 365,
            "informative_exact_strata": 20,
        },
        "seed": 20260810,
        "outputs": {
            "ledger": "data/personality_timing/challenge_resilience.jsonl",
            "state": "data/personality_timing/challenge_resilience_state.json",
        },
    },
    {
        "program_id": "PSS-CD1",
        "family": "pss_cd1_correlation_dispersion_prospective",
        "schema": "personality_crowding_hazard.manifest/v1",
        "manifest": BASE / "crowding_hazard_manifest_v1.json",
        "construction": CD1_CONSTRUCTION,
        "hypothesis": (
            "Inside a prospectively observed RH1 synchronized-relief hazard, "
            "unusually concentrated common-factor variance plus unusually low "
            "cross-sectional dispersion marks a crowded beta rally with greater "
            "subsequent drawdown and tail risk than a nested uncrowded hazard."
        ),
        "treatment": "crowding_hazard",
        "control": "uncrowded_control",
        "harm": True,
        "minimums": {
            "matured_primary_rows": 250,
            "unique_names": 125,
            "crowding_hazard_rows": 50,
            "uncrowded_control_rows": 50,
            "distinct_action_months": 12,
            "action_date_span_days": 365,
            "informative_exact_strata": 20,
        },
        "seed": 20260812,
        "outputs": {
            "ledger": "data/personality_timing/crowding_hazard.jsonl",
            "state": "data/personality_timing/crowding_hazard_state.json",
        },
    },
    {
        "program_id": "PSS-AF1",
        "family": "pss_af1_finra_absorption_witness_prospective",
        "schema": "personality_flow_absorption.manifest/v1",
        "manifest": BASE / "flow_absorption_manifest_v1.json",
        "construction": AF1_CONSTRUCTION,
        "hypothesis": (
            "Among prospectively observed CR1 resilient leaders with comparable "
            "FINRA activity, leadership that survives top-quartile own-history "
            "short-marked activity has lower subsequent drawdown and tail risk "
            "than resilient leadership without that transaction-flow witness."
        ),
        "treatment": "flow_witness",
        "control": "leader_flow_control",
        "harm": False,
        "minimums": {
            "matured_primary_rows": 150,
            "unique_names": 100,
            "flow_witness_rows": 40,
            "leader_flow_control_rows": 40,
            "distinct_action_months": 12,
            "action_date_span_days": 365,
            "informative_exact_strata": 12,
        },
        "seed": 20260814,
        "outputs": {
            "ledger": "data/personality_timing/flow_absorption.jsonl",
            "state": "data/personality_timing/flow_absorption_state.json",
        },
    },
)


def freeze(*, register_trials: bool) -> None:
    availability = _validate_sources()
    for spec in PROGRAMS:
        construction = spec["construction"]
        construction_sha = _sha256_bytes(_canonical(construction))
        decision = _decision_law(
            treatment=str(spec["treatment"]),
            control=str(spec["control"]),
            minimums=dict(spec["minimums"]),
            harm=bool(spec["harm"]),
            seed=int(spec["seed"]),
        )
        manifest = {
            "schema": spec["schema"],
            "program_id": spec["program_id"],
            "family": spec["family"],
            "status": "prospective_accrual_only",
            "frozen_at": FROZEN_AT,
            "source_commit": SOURCE_COMMIT,
            "not_before_session": NOT_BEFORE_SESSION,
            "enrollment_law": (
                "source action must be strictly greater than not_before_session; "
                "historical events are never imported or counted"
            ),
            "hypothesis": spec["hypothesis"],
            "prior_seen_not_confirmation": [
                "PSS-F1 through F4 and F4R/F4H outcomes",
                "PSS-SR1 through SR3 outcomes",
                "PSS-RH1 was selected from the historical PSS-SR3 sign inversion",
            ],
            "construction": construction,
            "construction_sha256": construction_sha,
            "source_bindings": {
                "rh1_manifest": {
                    "path": str(RH1_MANIFEST.relative_to(ROOT)),
                    "sha256": RH1_MANIFEST_SHA256,
                },
                "rh1_membership": {
                    "path": str(RH1_MEMBERSHIP.relative_to(ROOT)),
                    "sha256": RH1_MEMBERSHIP_SHA256,
                    "ticker_count": availability["rh1_member_count"],
                },
            },
            "availability_audit": availability,
            "grading": GRADE,
            "decision_law": decision,
            "trial_budget": {
                "prospective_configurations": 1,
                "historical_lineage_disclosed": True,
                "no_threshold_grid": True,
                "no_interim_retiming": True,
            },
            "outputs": spec["outputs"],
            "authority": AUTHORITY,
        }
        if spec["program_id"] == "PSS-AF1":
            if _sha256_file(CR1_MANIFEST) != CR1_MANIFEST_SHA256:
                raise RuntimeError("PSS-CR1 manifest changed before AF1 binding")
            manifest["source_bindings"]["cr1_manifest"] = {
                "path": str(CR1_MANIFEST.relative_to(ROOT)),
                "sha256": CR1_MANIFEST_SHA256,
            }
            manifest["source_bindings"]["finra_stable_prefix"] = {
                "path": str(FINRA_PANEL.relative_to(ROOT)),
                "through": FINRA_PREFIX_END,
                "row_count": FINRA_PREFIX_ROWS,
                "canonical_sha256": FINRA_PREFIX_SHA256,
            }
        _write_json(Path(spec["manifest"]), manifest)

        if register_trials:
            ledger = TrialLedger(path=TRIAL_LEDGER, family=str(spec["family"]))
            ledger.log_trial(
                {
                    "id": spec["program_id"],
                    "design": spec["hypothesis"],
                    "not_before_session": NOT_BEFORE_SESSION,
                    "construction_sha256": construction_sha,
                    "rh1_membership_sha256": RH1_MEMBERSHIP_SHA256,
                    "treatment": spec["treatment"],
                    "control": spec["control"],
                    "single_read": spec["minimums"],
                    "registered_at": FROZEN_AT,
                },
                info_cutoff=NOT_BEFORE_SESSION,
                source=str(spec["program_id"]),
                note=(
                    "Prospective-only follow-on. Historical rows and outcomes "
                    "cannot enter this ledger or decision."
                ),
            )
            ledger.log_declared_budget(
                1,
                reason=(
                    "one exact prospective construction; no threshold, lookback, "
                    "control, outcome, or read-clock grid"
                ),
            )

        print(
            f"{spec['program_id']} "
            f"construction_sha256={construction_sha} "
            f"manifest_sha256={_sha256_file(Path(spec['manifest']))}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--register-trials",
        action="store_true",
        help="Also append the three exact trials and budgets to the trial ledger.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    freeze(register_trials=parse_args().register_trials)
