"""engine.marketing.departments — 10 chartered departments.

Department charters are seeded here from the docket (§7) and strategy doc (§8).
Config overrides in config/marketing.yml are applied at runtime via registry().

Spec law: office_cmo director_model="fable"; all others "opus".
          growth_os lifecycle_state="building"; rest="chartered".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Scorecard:
    primary_metric: str
    leading: list[str] = field(default_factory=list)
    trust_health: str = "clean"
    experiment_velocity: int = 0
    learning_quality: str = "seeding"
    authority_level: str = "G1"


@dataclass
class Department:
    id: str
    name: str
    director_model: str  # "fable" | "opus"
    primary_outcome: str
    non_goals: list[str]
    engines: list[str]
    authority_level: str  # "G1" | "G2"
    lifecycle_state: str  # "chartered" | "building"
    budget: dict  # {envelope_usd: 0, spent_usd: 0}
    model_mix: dict
    clock: dict  # {cadence, last_review, next_review}
    retirement_test: str
    scorecard: Scorecard
    wave: int

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "director_model": self.director_model,
            "primary_outcome": self.primary_outcome,
            "non_goals": self.non_goals,
            "engines": self.engines,
            "authority_level": self.authority_level,
            "lifecycle_state": self.lifecycle_state,
            "budget": dict(self.budget),
            "model_mix": dict(self.model_mix),
            "clock": dict(self.clock),
            "retirement_test": self.retirement_test,
            "scorecard": {
                "primary_metric": self.scorecard.primary_metric,
                "leading": list(self.scorecard.leading),
                "trust_health": self.scorecard.trust_health,
                "experiment_velocity": self.scorecard.experiment_velocity,
                "learning_quality": self.scorecard.learning_quality,
                "authority_level": self.scorecard.authority_level,
            },
            "wave": self.wave,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Seed charters (10 departments)
# ─────────────────────────────────────────────────────────────────────────────

_REVIEW_CADENCE = "weekly"
_DEFAULT_BUDGET = {"envelope_usd": 0, "spent_usd": 0}

DEPARTMENT_CHARTERS: list[Department] = [

    Department(
        id="office_cmo",
        name="Office of the Autonomous CMO",
        director_model="fable",
        primary_outcome=(
            "Maximize durable contribution profit and strategic distribution power "
            "through capital allocation, org design, and growth thesis ownership."
        ),
        non_goals=[
            "Review routine newsletter assembly or approved lifecycle emails.",
            "Approve standard chart cards or low-budget in-envelope experiments.",
            "Be the chief copywriter or day-to-day content producer.",
        ],
        engines=[
            "portfolio_allocator",
            "department_registry",
            "objective_tree",
            "conflict_resolver",
            "strategy_memory",
            "opportunity_queue",
            "org_simulator",
        ],
        authority_level="G2",
        lifecycle_state="chartered",
        budget=dict(_DEFAULT_BUDGET),
        model_mix={"director": "fable", "workers": "opus"},
        clock={"cadence": "weekly", "last_review": None, "next_review": "2026-07-25"},
        retirement_test=(
            "Retire if a simpler governance mechanism achieves equivalent "
            "attribution accuracy with lower inference cost over 90 days."
        ),
        scorecard=Scorecard(
            primary_metric="day-90 retained contribution profit (marketing-attributable)",
            leading=[
                "opportunity_queue_depth",
                "department_scorecard_coverage",
                "experiment_velocity_lobe",
            ],
            trust_health="clean",
            experiment_velocity=0,
            learning_quality="seeding",
            authority_level="G2",
        ),
        wave=0,
    ),

    Department(
        id="growth_os",
        name="Growth Operating System and Finance",
        director_model="opus",
        primary_outcome="Reliable autonomous execution at known cost.",
        non_goals=[
            "Create editorial content or marketing campaigns.",
            "Make audience or channel strategy decisions.",
            "Own product feature roadmap.",
        ],
        engines=[
            "campaign_task_scheduler",
            "run_ledger_event_bus",
            "budget_inference_cost_allocator",
            "credential_connector_registry",
            "job_locks_idempotency",
            "vendor_cost_monitor",
            "department_health",
            "incident_rollback_manager",
            "service_level_objectives",
            "human_exception_queue",
        ],
        authority_level="G2",
        lifecycle_state="building",
        budget=dict(_DEFAULT_BUDGET),
        model_mix={"director": "opus", "workers": "haiku"},
        clock={"cadence": "daily", "last_review": None, "next_review": "2026-07-25"},
        retirement_test=(
            "Retire if a managed external execution platform provides equivalent "
            "reliability, auditability, and cost transparency."
        ),
        scorecard=Scorecard(
            primary_metric="successful campaign executions per day",
            leading=[
                "run_ledger_health",
                "inference_cost_per_campaign",
                "incident_mean_time_to_resolve",
            ],
            trust_health="clean",
            experiment_velocity=0,
            learning_quality="seeding",
            authority_level="G2",
        ),
        wave=1,
    ),

    Department(
        id="intelligence",
        name="Market, Audience, and Opportunity Intelligence",
        director_model="opus",
        primary_outcome=(
            "Identify the best audience/problem/event/channel opportunities "
            "before competitors."
        ),
        non_goals=[
            "Produce editorial content or campaign assets.",
            "Make budget allocation decisions.",
            "Own the publication ledger.",
        ],
        engines=[
            "product_page_crawler",
            "competitor_category_monitor",
            "search_demand_miner",
            "community_question_miner",
            "event_attention_detector",
            "audience_segment_graph",
            "review_objection_miner",
            "channel_white_space_detector",
            "creator_community_prospecting",
            "opportunity_scoring_decay",
        ],
        authority_level="G1",
        lifecycle_state="chartered",
        budget=dict(_DEFAULT_BUDGET),
        model_mix={"director": "opus", "workers": "sonnet", "extraction": "haiku"},
        clock={"cadence": "weekly", "last_review": None, "next_review": "2026-07-25"},
        retirement_test=(
            "Retire if opportunity detection recall falls below 60% on "
            "major events for two consecutive quarters."
        ),
        scorecard=Scorecard(
            primary_metric="qualified opportunities surfaced per week",
            leading=[
                "opportunity_score_median",
                "event_detection_latency_minutes",
                "competitor_coverage_pct",
            ],
            trust_health="clean",
            experiment_velocity=0,
            learning_quality="seeding",
            authority_level="G1",
        ),
        wave=1,
    ),

    Department(
        id="products",
        name="Intelligence Products and Public Tools",
        director_model="opus",
        primary_outcome=(
            "Turn user uncertainty into useful, shareable product experiences."
        ),
        non_goals=[
            "Build advertising creatives or promotional landing pages.",
            "Own lifecycle or conversion optimization.",
            "Operate distribution channels.",
        ],
        engines=[
            "what_changed",
            "why_is_it_moving",
            "stock_dossier",
            "event_impact_maps",
            "receipt_forecast_pages",
            "chart_as_url",
            "portfolio_watchlist_xray",
            "market_regime_explainers",
            "comparison_alternative_pages",
            "widgets_embeds",
            "public_report_generator",
            "content_freshness_expiration",
        ],
        authority_level="G1",
        lifecycle_state="chartered",
        budget=dict(_DEFAULT_BUDGET),
        model_mix={"director": "opus", "workers": "sonnet", "formatting": "haiku"},
        clock={"cadence": "weekly", "last_review": None, "next_review": "2026-07-25"},
        retirement_test=(
            "Retire a specific product when it generates fewer than 10 "
            "qualified acquisition events per month for 60 days."
        ),
        scorecard=Scorecard(
            primary_metric="public value use events per week",
            leading=[
                "share_generated_rate",
                "embed_view_count",
                "dossier_generated_count",
            ],
            trust_health="clean",
            experiment_velocity=0,
            learning_quality="seeding",
            authority_level="G1",
        ),
        wave=3,
    ),

    Department(
        id="studio",
        name="Editorial, Creative Studio, and Data Newsroom",
        director_model="opus",
        primary_outcome=(
            "Create distinctive, timely, multi-format work from every "
            "worthy opportunity."
        ),
        non_goals=[
            "Own opportunity detection or scoring.",
            "Operate distribution channels directly.",
            "Make budget allocation decisions.",
        ],
        engines=[
            "campaign_brief_compiler",
            "narrative_hook_generator",
            "chart_annotation",
            "visual_identity_renderer",
            "short_long_form_video",
            "voice_caption_transcript",
            "newsletter_article_assembly",
            "platform_specific_adaptation",
            "multilingual_localization",
            "event_newsroom",
            "asset_quality_tests",
            "asset_variation_fatigue_detection",
        ],
        authority_level="G1",
        lifecycle_state="chartered",
        budget=dict(_DEFAULT_BUDGET),
        model_mix={"director": "opus", "writers": "sonnet", "formatters": "haiku"},
        clock={"cadence": "weekly", "last_review": None, "next_review": "2026-07-25"},
        retirement_test=(
            "Retire if creative output fails distinctness checks or "
            "produces zero qualified-reach events for 30 consecutive days."
        ),
        scorecard=Scorecard(
            primary_metric="qualified-reach events driven by studio assets",
            leading=[
                "asset_distinctness_score",
                "creative_fatigue_index",
                "assets_shipped_per_week",
            ],
            trust_health="clean",
            experiment_velocity=0,
            learning_quality="seeding",
            authority_level="G1",
        ),
        wave=4,
    ),

    Department(
        id="distribution",
        name="Distribution Network",
        director_model="opus",
        primary_outcome=(
            "Place useful intelligence where the right audience already gathers."
        ),
        non_goals=[
            "Create original editorial content.",
            "Own audience or opportunity research.",
            "Make product decisions.",
        ],
        engines=[
            "owned_site_publisher",
            "email_publisher",
            "x_publisher",
            "youtube_publisher",
            "tiktok_instagram_adapters",
            "stocktwits_editorial_queue",
            "reddit_participation_queue",
            "discord_telegram_apps",
            "syndication",
            "embed_widget_delivery",
            "partner_feeds",
            "channel_policy_adapters",
            "reply_community_queues",
            "publication_receipts_takedown",
        ],
        authority_level="G2",
        lifecycle_state="chartered",
        budget=dict(_DEFAULT_BUDGET),
        model_mix={
            "director": "opus",
            "policy_classifiers": "haiku",
            "scheduling": "deterministic",
        },
        clock={"cadence": _REVIEW_CADENCE, "last_review": None, "next_review": "2026-07-25"},
        retirement_test=(
            "Retire a channel adapter if it produces warnings, policy flags, "
            "or zero qualified-reach events for 60 days."
        ),
        scorecard=Scorecard(
            primary_metric="qualified-reach events per channel per week",
            leading=[
                "publication_receipt_rate",
                "correction_rate",
                "channel_policy_warning_count",
            ],
            trust_health="clean",
            experiment_velocity=0,
            learning_quality="seeding",
            authority_level="G2",
        ),
        wave=4,
    ),

    Department(
        id="lifecycle",
        name="Lifecycle, Conversion, and Monetization",
        director_model="opus",
        primary_outcome=(
            "Move the right visitor from first value to repeated value "
            "to retained paid use."
        ),
        non_goals=[
            "Optimize sign-up volume rather than retained contribution.",
            "Own distribution or creative production.",
            "Make positioning or category decisions.",
        ],
        engines=[
            "landing_onboarding_optimizer",
            "account_watchlist_activation",
            "preview_trial_allocator",
            "next_best_value_engine",
            "email_in_product_lifecycle",
            "checkout_offer_experiments",
            "pricing_packaging_research",
            "cancellation_refund_intelligence",
            "win_back",
            "subscriber_reason_to_return_graph",
            "lead_quality_backpressure",
        ],
        authority_level="G2",
        lifecycle_state="chartered",
        budget=dict(_DEFAULT_BUDGET),
        model_mix={"director": "opus", "workers": "sonnet", "tagging": "haiku"},
        clock={"cadence": _REVIEW_CADENCE, "last_review": None, "next_review": "2026-07-25"},
        retirement_test=(
            "Redesign if day-30 retained-contribution forecast is negative "
            "for two consecutive cohort reviews."
        ),
        scorecard=Scorecard(
            primary_metric="day-30 retained-contribution forecast (cohort)",
            leading=[
                "activation_rate",
                "preview_to_paid_conversion",
                "refund_rate",
            ],
            trust_health="clean",
            experiment_velocity=0,
            learning_quality="seeding",
            authority_level="G2",
        ),
        wave=2,
    ),

    Department(
        id="ecosystem",
        name="Creator, Partner, and Community Infrastructure",
        director_model="opus",
        primary_outcome=(
            "Make external people and communities more effective "
            "because Mastermind exists."
        ),
        non_goals=[
            "Pay creators to post advertisements.",
            "Operate promotional reply bots.",
            "Own lifecycle or billing infrastructure.",
        ],
        engines=[
            "creator_graph_quality_score",
            "personalized_creator_demos",
            "creator_copilot",
            "cobranded_reports",
            "recurring_referral_ledger",
            "standard_commercial_terms",
            "partner_workspace_provisioning",
            "discord_telegram_community_config",
            "partner_dashboards",
            "reporter_newsletter_data_desk",
            "partnership_outcome_analysis",
        ],
        authority_level="G1",
        lifecycle_state="chartered",
        budget=dict(_DEFAULT_BUDGET),
        model_mix={"director": "opus", "workers": "sonnet"},
        clock={"cadence": _REVIEW_CADENCE, "last_review": None, "next_review": "2026-07-25"},
        retirement_test=(
            "Retire a partner if they produce zero incremental retained "
            "contributions after two payout cycles."
        ),
        scorecard=Scorecard(
            primary_metric="incremental retained contributions from partner channel",
            leading=[
                "active_creator_partnerships",
                "referral_conversion_rate",
                "creator_asset_quality_median",
            ],
            trust_health="clean",
            experiment_velocity=0,
            learning_quality="seeding",
            authority_level="G1",
        ),
        wave=5,
    ),

    Department(
        id="growth_science",
        name="Growth Science and Self-Improvement",
        director_model="opus",
        primary_outcome=(
            "Determine incremental causal impact and improve the institution."
        ),
        non_goals=[
            "Produce editorial content or run distribution channels.",
            "Make final budget allocation decisions (recommend only).",
            "Operate the human-exception queue.",
        ],
        engines=[
            "event_taxonomy",
            "identity_resolution",
            "attribution",
            "randomized_holdouts",
            "incrementality_tests",
            "cohort_retention",
            "contribution_margin_model",
            "creative_audience_embeddings",
            "experiment_registry",
            "playbook_promotion_demotion",
            "department_scorecards",
            "model_prompt_evaluation",
            "simulation_digital_twin",
            "automated_postmortems",
        ],
        authority_level="G1",
        lifecycle_state="chartered",
        budget=dict(_DEFAULT_BUDGET),
        model_mix={"director": "opus", "analysts": "sonnet", "scoring": "deterministic"},
        clock={"cadence": _REVIEW_CADENCE, "last_review": None, "next_review": "2026-07-25"},
        retirement_test=(
            "Redesign if attribution methodology fails holdout validation "
            "on two consecutive quarter reviews."
        ),
        scorecard=Scorecard(
            primary_metric="experiments with holdout-validated incrementality results",
            leading=[
                "holdout_experiment_velocity",
                "attribution_model_accuracy",
                "playbook_improvement_rate",
            ],
            trust_health="clean",
            experiment_velocity=0,
            learning_quality="seeding",
            authority_level="G1",
        ),
        wave=2,
    ),

    Department(
        id="trust_office",
        name="Autonomous Trust, Policy, and Red-Team Office",
        director_model="opus",
        primary_outcome=(
            "Keep autonomy truthful, recoverable, and commercially durable."
        ),
        non_goals=[
            "Be a routine human approval gate for low-consequence publishing.",
            "Own marketing strategy or budget decisions.",
            "Report to any department it audits.",
        ],
        engines=[
            "provenance_verification",
            "claim_disclosure_linting",
            "platform_policy_compiler",
            "jurisdiction_consequence_classifier",
            "privacy_consent_checks",
            "duplicate_spam_detection",
            "correction_recall",
            "adversarial_brand_review",
            "security_secret_checks",
            "contract_rights_checks",
            "audit_sampling",
            "autonomous_quarantine_rollback",
        ],
        authority_level="G2",
        lifecycle_state="chartered",
        budget=dict(_DEFAULT_BUDGET),
        model_mix={"auditor": "opus", "linting": "haiku", "red_team": "opus"},
        clock={"cadence": _REVIEW_CADENCE, "last_review": None, "next_review": "2026-07-25"},
        retirement_test=(
            "The auditor is never retired; it may be redesigned "
            "if it generates more than 5% false-positive quarantines per month."
        ),
        scorecard=Scorecard(
            primary_metric="unresolved compliance incidents (target: 0)",
            leading=[
                "false_positive_quarantine_rate",
                "correction_resolution_time_hours",
                "platform_policy_coverage_pct",
            ],
            trust_health="clean",
            experiment_velocity=0,
            learning_quality="seeding",
            authority_level="G2",
        ),
        wave=0,
    ),
]

# Index by id for fast lookup
_DEPT_BY_ID: dict[str, Department] = {d.id: d for d in DEPARTMENT_CHARTERS}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def registry(cfg: dict | None = None) -> list[Department]:
    """Return the department list, applying config overrides where present.

    cfg should be the parsed marketing.yml dict.  Overrides are applied
    per-department under the ``departments:`` key.  Unknown department ids
    in overrides are silently ignored.
    """
    overrides: dict[str, Any] = (cfg or {}).get("departments", {}) or {}
    result: list[Department] = []
    for dept in DEPARTMENT_CHARTERS:
        ov = overrides.get(dept.id, {}) or {}
        if not ov:
            result.append(dept)
            continue
        # Shallow-clone and apply field overrides
        import copy
        d = copy.deepcopy(dept)
        if "lifecycle_state" in ov:
            d.lifecycle_state = ov["lifecycle_state"]
        if "authority_level" in ov:
            d.authority_level = ov["authority_level"]
            d.scorecard.authority_level = ov["authority_level"]
        if "budget_envelope_usd" in ov:
            d.budget["envelope_usd"] = ov["budget_envelope_usd"]
        result.append(d)
    return result
