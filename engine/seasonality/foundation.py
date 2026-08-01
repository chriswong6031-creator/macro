"""Public, claim-bounded methodology manifest for the seasonality program."""
from __future__ import annotations

from datetime import date

METHODOLOGY_SCHEMA = "biopharma_seasonality.methodology.v1"


def build_methodology_manifest(as_of: date | None = None) -> dict:
    """Describe the live foundation without implying a live forecast exists."""
    as_of = as_of or date.today()
    return {
        "schema": METHODOLOGY_SCHEMA,
        "as_of": as_of.isoformat(),
        "status": "foundation_contracts_live",
        "availability": {
            "live_forecasts": False,
            "live_screener": False,
            "live_event_graph": False,
            "note": "Contracts and multiplicity controls are live; data ingestion and forecasts are not yet commissioned.",
        },
        "clean_room": {
            "policy": "independent_implementation",
            "inputs": ["public_product_behavior", "licensed_or_public_data", "published_methods"],
            "forbidden": ["copied_source_code", "copied_assets", "proprietary_backend_access"],
        },
        "clocks": {
            "calendar": ["day_of_year", "weekday", "month", "turn_of_month", "quarter_end"],
            "event": ["fda", "clinical_trial", "conference", "financing", "commercial"],
            "regime": ["broad_market", "biotech_tape", "rates_liquidity", "issuer_financing_pressure"],
        },
        "validation": {
            "independence_unit": "year_or_event_cluster",
            "selection_controls": ["trial_ledger", "benjamini_yekutieli", "joint_max_t", "spa_reality_check"],
            "out_of_sample": ["chronological_walk_forward", "purge_embargo", "issuer_holdout", "untouched_epoch_holdout"],
            "calibration": ["brier", "log_score", "crps", "reliability", "forward_ledger"],
        },
        "authority": {
            "tier": "shadow",
            "is_context_only": True,
            "may_explain": True,
            "may_flag_attention": True,
            "may_deescalate": False,
            "may_rank": False,
            "may_gate": False,
            "may_size": False,
            "may_originate": False,
            "may_rewrite_geometry": False,
            "may_boost_confidence": False,
        },
        "contracts": {
            "event": "biopharma.event.v1",
            "neural_web": "neuralweb.biopharma_seasonality_state.v1",
            "prophet": "prophet.seasonality_overlay/v1",
        },
    }
