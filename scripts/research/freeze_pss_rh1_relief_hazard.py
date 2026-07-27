#!/usr/bin/env python3
"""Freeze the outcome-blind PSS-RH1 prospective enrollment contract.

This is a one-time registration utility.  It reads only the already-selected
PSS universe, current sector membership, and the last available OHLC date.  It
does not construct events and never reads a post-action outcome.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.trial_ledger import TrialLedger  # noqa: E402


PANEL = ROOT / "data/research/ptt_w1_panel.parquet"
SECTOR_MAP = ROOT / "data/breadth/ticker_sectors.parquet"
OHLCV_DIR = ROOT / "data/baskets/ohlcv"
MEMBERSHIP = ROOT / "data/personality_timing/relief_hazard_membership_v1.json"
MANIFEST = ROOT / "data/personality_timing/relief_hazard_manifest_v1.json"
TRIAL_LEDGER = ROOT / "data/trial_ledger.jsonl"

FROZEN_AT = "2026-07-27T22:30:55Z"
NOT_BEFORE_SESSION = "2026-07-24"
SOURCE_COMMIT = "71ac1df412a9cf0b32b050ff05d40ed59c0ac27c"
PANEL_SHA256 = "0bf8ddbde7263c7f72f0e1aaeacef77695f81fc2ac1c05e387d200bebdd9687e"
SECTOR_MAP_SHA256 = "24c0d576f800c92333bb13689a250905a1172f5dc6ca982982d3ec152d1e35f3"

SECTORS = (
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
)

CONSTRUCTION = {
    "construction_id": "pss_sr3_exact_v1_as_adverse_hazard",
    "anchor": {
        "subject_prior_close_low_sessions": 60,
        "minimum_ex_self_peer_new_low_breadth": 0.15,
        "breadth_quantile": 0.80,
        "breadth_quantile_window_sessions": 126,
        "breadth_quantile_min_periods": 63,
        "breadth_quantile_shift_sessions": 1,
        "anchor_cooldown_sessions": 21,
        "minimum_ex_self_peers": 15,
    },
    "formation": {
        "sessions_including_anchor": 4,
        "atr_sessions": 14,
        "atr_information_cutoff": "anchor_minus_1_close",
        "reference_low": "minimum_intraday_low_anchor_through_anchor_plus_3",
    },
    "subject_action": {
        "search_sessions_after_formation": 30,
        "first_only": True,
        "persistence_sessions": 3,
        "minimum_close_above_reference_atr": 0.50,
        "minimum_low_above_reference_atr": -0.50,
        "action_close_depth_atr_inclusive": [1.00, 1.75],
    },
    "peer_state": {
        "peer_specific_reference_and_atr": True,
        "subject_excluded": True,
        "persistence_sessions": 3,
        "level_recovery_atr": 0.50,
        "active_trend_lookback_sessions": 5,
        "active_requires_strictly_higher_close": True,
        "minimum_ex_self_peers_each_observation": 15,
    },
    "labels": {
        "relief_hazard": "level_min>=0.50 and active_min>=0.50",
        "level_control": "level_min>=0.50 and active_min<0.50",
        "weak_level_diagnostic": "level_min<0.50",
    },
    "fixed_bands": {
        "anchor_severity": ["[0.15,0.30)", "[0.30,0.50)", "[0.50,1.01]"],
        "formation_to_action_delay": ["[1,10]", "[11,20]", "[21,30]"],
        "action_close_depth_atr": ["[1.00,1.25)", "[1.25,1.50)", "[1.50,1.75]"],
    },
}

GRADING = {
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

DECISION_LAW = {
    "authority_now": "none",
    "interim_outcome_reads": "forbidden",
    "read_count": 1,
    "first_read_requires_all": {
        "matured_primary_rows": 500,
        "unique_names": 250,
        "relief_hazard_rows": 100,
        "level_control_rows": 100,
        "distinct_action_months": 12,
        "action_date_span_days": 365,
        "informative_exact_strata": 30,
    },
    "inference_tape": {
        "deduplication": "keep first primary action per name per calendar month",
        "stratum": "sector x action_month x anchor_severity_band x delay_band",
        "minimum_per_label_in_stratum": 2,
        "aggregation": "equal weight across informative strata",
        "permutation": {
            "labels_move_only_within_stratum": True,
            "draws": 10000,
            "seed": 20260808,
            "one_sided_alpha": 0.05,
        },
        "bootstrap": {
            "unit": "three-calendar-month moving block",
            "draws": 5000,
            "seed": 20260809,
            "confidence": 0.95,
        },
    },
    "harm_signs": {
        "mae": "level_control_mae_minus_relief_hazard_mae",
        "tail10": "relief_hazard_tail_rate_minus_level_control_tail_rate",
        "w5": "level_control_w5_rate_minus_relief_hazard_w5_rate",
        "rebound8_first": (
            "level_control_rebound_first_rate_minus_"
            "relief_hazard_rebound_first_rate"
        ),
    },
    "qualification_requires_all": [
        "mae harm > 0, one-sided permutation p<=0.05, and block-CI lower>0",
        "tail10 harm > 0, one-sided permutation p<=0.05, and block-CI lower>0",
        "w5 harm > 0 and rebound8_first harm > 0",
        "mae and tail10 harm > 0 independently in chronological early and late halves",
        "leave-one-sector-out mae and tail10 harm stay > 0",
        "no sector supplies more than 25% of relief_hazard rows",
        "absolute stratified action-close-distance difference <=0.25 ATR",
    ],
    "ruling": (
        "Qualification authorizes only a separate preregistered de-escalation-"
        "shadow review. It never automatically creates entry, rank, size, gate, "
        "alert, or user-display authority. Failure of any required check kills "
        "PSS-RH1 at its sole read; thresholds and the read clock may not be retimed."
    ),
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


def _load_members() -> tuple[list[dict[str, str]], dict[str, object]]:
    if _sha256_file(PANEL) != PANEL_SHA256:
        raise RuntimeError("W1 panel changed after PSS-RH1 source freeze")
    if _sha256_file(SECTOR_MAP) != SECTOR_MAP_SHA256:
        raise RuntimeError("sector map changed after PSS-RH1 source freeze")

    panel = pd.read_parquet(PANEL, columns=["sym", "eligible"])
    eligible = set(
        panel.loc[panel["eligible"].astype(bool), "sym"].dropna().astype(str)
    )
    mapping = pd.read_parquet(
        SECTOR_MAP,
        columns=["ticker", "sector"],
    ).drop_duplicates("ticker", keep="last")
    mapping = mapping[
        mapping["ticker"].astype(str).isin(eligible)
        & mapping["sector"].astype(str).isin(SECTORS)
    ]
    members = sorted(
        (
            {"sym": str(row.ticker), "sector": str(row.sector)}
            for row in mapping.itertuples(index=False)
        ),
        key=lambda row: (row["sector"], row["sym"]),
    )

    latest_dates: Counter[str] = Counter()
    missing: list[str] = []
    for row in members:
        path = OHLCV_DIR / f"{row['sym']}.parquet"
        if not path.exists():
            missing.append(row["sym"])
            continue
        close = pd.read_parquet(path, columns=["close"])["close"].dropna()
        index = pd.DatetimeIndex(close.index).tz_localize(None)
        latest_dates[str(index.max().date())] += 1
    if missing:
        raise RuntimeError(f"missing OHLC for frozen members: {missing}")
    if not latest_dates or max(latest_dates) != NOT_BEFORE_SESSION:
        raise RuntimeError(
            f"unexpected latest session {max(latest_dates, default=None)}; "
            f"expected {NOT_BEFORE_SESSION}"
        )
    return members, {
        "latest_session_distribution": dict(sorted(latest_dates.items())),
        "maximum_latest_session": max(latest_dates),
    }


def freeze(*, register_trial: bool) -> None:
    members, availability = _load_members()
    member_counts = Counter(row["sector"] for row in members)
    membership_payload = {
        "schema": "personality_relief_hazard.membership/v1",
        "membership_id": "pss_rh1_live_membership_20260724",
        "frozen_at": FROZEN_AT,
        "not_before_session": NOT_BEFORE_SESSION,
        "source_commit": SOURCE_COMMIT,
        "selection_rule": (
            "eligible=true in frozen PTT-W1 panel; latest frozen ticker-sector "
            "mapping; one of eleven standard GICS sectors; OHLC file present"
        ),
        "source_files": {
            str(PANEL.relative_to(ROOT)): PANEL_SHA256,
            str(SECTOR_MAP.relative_to(ROOT)): SECTOR_MAP_SHA256,
        },
        "ticker_count": len(members),
        "sector_counts": dict(sorted(member_counts.items())),
        "availability_audit": availability,
        "members": members,
    }
    _write_json(MEMBERSHIP, membership_payload)
    membership_sha = _sha256_file(MEMBERSHIP)
    construction_sha = _sha256_bytes(_canonical(CONSTRUCTION))

    manifest_payload = {
        "schema": "personality_relief_hazard.manifest/v1",
        "program_id": "PSS-RH1",
        "family": "pss_rh1_relief_hazard_prospective",
        "status": "prospective_accrual_only",
        "frozen_at": FROZEN_AT,
        "source_commit": SOURCE_COMMIT,
        "not_before_session": NOT_BEFORE_SESSION,
        "enrollment_law": (
            "action_date must be strictly greater than not_before_session; "
            "historical events are never imported or counted"
        ),
        "hypothesis": (
            "After identical systemic stress, held subject recovery, and passive "
            "majority peer recovery, persistent majority five-session peer "
            "advancement marks a synchronized relief-rally hazard with worse "
            "subsequent drawdown/tail risk than the nested level control."
        ),
        "prior_seen_not_confirmation": [
            "PSS-SR3 historical DEV, VAL, and FWD outcomes",
            "PSS-SR3 construction-only feasibility shapes",
            "PSS-F1 through F4, F4R/F4H, SR1, and SR2 results",
        ],
        "construction": CONSTRUCTION,
        "construction_sha256": construction_sha,
        "membership": {
            "path": str(MEMBERSHIP.relative_to(ROOT)),
            "sha256": membership_sha,
            "ticker_count": len(members),
        },
        "grading": GRADING,
        "decision_law": DECISION_LAW,
        "trial_budget": {
            "prospective_configurations": 1,
            "historical_lineage_disclosed": True,
            "no_threshold_grid": True,
            "no_interim_retiming": True,
        },
        "outputs": {
            "ledger": "data/personality_timing/relief_hazard.jsonl",
            "state": "data/personality_timing/relief_hazard_state.json",
        },
        "authority": {
            "research_only": True,
            "may_enter": False,
            "may_rank": False,
            "may_size": False,
            "may_gate": False,
            "may_alert": False,
            "may_display_to_users": False,
            "may_auto_promote": False,
        },
    }
    _write_json(MANIFEST, manifest_payload)

    if register_trial:
        ledger = TrialLedger(
            path=TRIAL_LEDGER,
            family="pss_rh1_relief_hazard_prospective",
        )
        registration = {
            "id": "PSS-RH1",
            "design": "exact PSS-SR3 label prospectively tested as adverse hazard",
            "not_before_session": NOT_BEFORE_SESSION,
            "construction_sha256": construction_sha,
            "membership_sha256": membership_sha,
            "ruler": "MAE63/tail10 primary; W5 and rebound8-first support",
            "control": "passive level_min>=0.50 and active_min<0.50",
            "single_read": DECISION_LAW["first_read_requires_all"],
            "prior_seen": "PSS-SR3 historical adverse result is hypothesis generation only",
            "registered_at": FROZEN_AT,
        }
        ledger.log_trial(
            registration,
            info_cutoff=NOT_BEFORE_SESSION,
            source="PSS-RH1",
            note=(
                "Prospective-only exact-label replication. Historical rows and "
                "outcomes cannot enter the RH1 ledger or decision."
            ),
        )
        ledger.log_declared_budget(
            1,
            reason=(
                "one exact prospective construction; no threshold, lookback, "
                "control, outcome, or read-clock grid"
            ),
        )

    print(f"members={len(members)}")
    print(f"membership_sha256={membership_sha}")
    print(f"construction_sha256={construction_sha}")
    print(f"manifest_sha256={_sha256_file(MANIFEST)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--register-trial",
        action="store_true",
        help="Also append the exact prospective trial and budget to the ledger.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    freeze(register_trial=parse_args().register_trial)
