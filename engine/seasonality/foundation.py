"""Public, claim-bounded methodology manifest for the seasonality program.

The manifest exists to stop the program from quietly outgrowing its own claims.
Every field here is either a description of something that RUNS tonight or an
explicit ``False`` saying it does not.  Nothing is aspirational: the planned
clocks below sit under ``clocks``, which is a design vocabulary, while
``availability`` is the boolean record of what is actually commissioned.
"""
from __future__ import annotations

from datetime import date

METHODOLOGY_SCHEMA = "biopharma_seasonality.methodology.v1"


def build_methodology_manifest(as_of: date | None = None) -> dict:
    """Describe the live foundation without implying a live forecast exists."""
    as_of = as_of or date.today()
    return {
        "schema": METHODOLOGY_SCHEMA,
        "as_of": as_of.isoformat(),
        "status": "calendar_clock_live",
        "availability": {
            # Still false, and each one is a real absence rather than a hedge.
            "live_forecasts": False,
            "live_screener": False,
            "live_event_graph": False,
            # Live as of the Lane 1/2/4 tranche: a point-in-time year panel, the
            # canonical curve, the fixed window family, and the selection
            # correction that prices having searched it.
            "live_calendar_clock": True,
            "live_selection_correction": True,
            "note": (
                "The calendar clock and its selection accounting are live and rebuild nightly. "
                "There is still no forecast, no probability, no screener, no cross-symbol "
                "ranking, and no event graph: the artifact describes what a window DID across "
                "complete years and what that is worth after counting every window searched."
            ),
        },
        "calendar_clock": {
            "artifacts": [
                "site/seasonalitydata/index.json",
                "site/seasonalitydata/entities/<SYMBOL>.json",
            ],
            "unit_of_evidence": "one_complete_year",
            "complete_year_rule": "first session <= Jan 10 and last session >= Dec 20",
            "clock_slots": 365,
            "leap_policy": "02-29_log_return_added_into_02-28_slot",
            "missing_session_policy": "non_trading_days_carry_zero_log_return",
            "years_capped_at": 25,
            "min_complete_years_for_coverage": 15,
            "window_family": {
                "n_candidates": 2645,
                "horizons_days": [5, 10, 15, 20, 30, 45, 60, 90],
                "wraps_year": False,
                "statistic": "abs_t_of_mean_window_log_return_across_years",
            },
            "selection_correction": {
                "null": "independent_circular_year_shift",
                "resamples": 2000,
                "familywise": "joint_max_t_westfall_young",
                "sensitivity": "benjamini_yekutieli_over_registered_panel",
                "across_symbol_multiplicity": "disclosed_as_program_level_rates_not_corrected_away",
            },
            "market_neutral": {
                "benchmark": "SPY",
                "beta_source": "pit_trailing_252d_shifted_one_session",
            },
            "disclosed_limits": {
                "price_adjustment_is_point_in_time": False,
                "price_adjustment_note": (
                    "Split- and dividend-adjusted closes are the vendor's CURRENT vintage "
                    "re-applied to all history, not a frozen point-in-time adjustment."
                ),
                "universe_is_survivorship_biased": True,
                "universe_note": (
                    "Coverage is measured from today's price store, so delisted, acquired, and "
                    "renamed names are absent. Nothing here ranks symbols against each other, "
                    "so the bias enters no per-symbol number."
                ),
                "exploratory_windows_are_uncounted": True,
                "exploratory_note": (
                    "A window a reader draws after seeing the chart spends testing budget the "
                    "family accounting does not know about, and is marked exploratory."
                ),
            },
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
            "calendar_index": "biopharma_seasonality.index.v1",
            "calendar_entity": "biopharma_seasonality.entity.v1",
        },
    }
