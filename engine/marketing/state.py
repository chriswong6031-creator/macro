"""engine.marketing.state — Assemble the full marketing_state snapshot.

build_state(root=None, cfg=None) -> dict

Reads:
  - config/marketing.yml (positioning, settings, desk_network, department overrides)
  - data/marketing/*.jsonl  (seed ledgers)

Writes nothing — caller (marketing_governor) stamps and writes.

Never-raise: any error returns best-effort dict with "state":"error" note.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from engine.marketing.authority import LADDER
from engine.marketing.charter import mandate
from engine.marketing.claims import summarize as claims_summarize
from engine.marketing.cmo import (
    improvement_loop_state,
    portfolio,
    self_deception_checks,
)
from engine.marketing.departments import registry as dept_registry
from engine.marketing.economics import FORMULA, BudgetAllocator
from engine.marketing.events import GROWTH_EVENTS
from engine.marketing.ledgers import read_jsonl, tail
from engine.marketing.opportunity_bus import score_dict
from engine.marketing.publication import desk_network

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

def _root_path(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _cfg_path(root: Path) -> Path:
    return root / "config" / "marketing.yml"


def _ledger(root: Path, name: str) -> Path:
    return root / "data" / "marketing" / name


# ─────────────────────────────────────────────────────────────────────────────
# Config loader
# ─────────────────────────────────────────────────────────────────────────────

def _load_cfg(root: Path) -> dict:
    p = _cfg_path(root)
    try:
        if not p.exists():
            return {}
        text = p.read_text(encoding="utf-8")
        return yaml.safe_load(text) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing state: failed to load config: %s", exc)
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Waves (docket §19)
# ─────────────────────────────────────────────────────────────────────────────

_WAVES: list[dict] = [
    {
        "id": "wave0",
        "title": "Root charter and inventory",
        "status": "active",
        "goal": (
            "Establish the sovereign lobe, exact current-state truth, "
            "department registry, growth authority ladder, and auditor charter. "
            "Lobe visible in Neural Web organization; Fable can create a "
            "department in shadow mode."
        ),
    },
    {
        "id": "wave1",
        "title": "Autonomous Growth OS",
        "status": "planned",
        "goal": (
            "Make every action attributable, bounded, replayable, and recoverable. "
            "Build: Opportunity Bus, campaign compiler, provenance modes, "
            "Claim Passport, publication ledger, correction bus, "
            "experiment registry, budget allocator, policy compiler, "
            "human-exception queue, growth events."
        ),
    },
    {
        "id": "wave2",
        "title": "Commercial truth spine",
        "status": "planned",
        "goal": (
            "Ensure traffic can become measurable retained revenue. "
            "Build: production billing, canonical offers, preview logic, "
            "refunds, identity/audience graph, consent, lifecycle events, "
            "attribution, cohort economics."
        ),
    },
    {
        "id": "wave3",
        "title": "Proof products",
        "status": "planned",
        "goal": (
            "Create the highest-leverage public value objects: "
            "What Changed, Claim Passport / receipt page, Why Is It Moving?, "
            "share card and chart-as-URL, Stock Dossier, event impact map, "
            "watchlist monitoring bridge."
        ),
    },
    {
        "id": "wave4",
        "title": "Owned media machine",
        "status": "planned",
        "goal": (
            "Make one worthy opportunity become a coherent owned distribution bundle: "
            "newsletter, flagship X desk, chart/receipt X desk, YouTube shorts, "
            "public SEO templates, structured data, newsroom."
        ),
    },
    {
        "id": "wave5",
        "title": "Ecosystem distribution",
        "status": "planned",
        "goal": (
            "Make other people stronger because they distribute Mastermind intelligence: "
            "creator copilot, co-branded reports, partner ledger, Discord/Telegram, "
            "embed SDK, community configuration."
        ),
    },
    {
        "id": "wave6",
        "title": "Paid growth and autonomous scaling",
        "status": "planned",
        "goal": (
            "Buy only what the organic system has proved: "
            "paid account adapters, retargeting, organic-winner promotion, "
            "incrementality holdouts, day-90 value forecasts, "
            "automatic scale and stop rules."
        ),
    },
    {
        "id": "wave7",
        "title": "Self-expanding institution",
        "status": "planned",
        "goal": (
            "Allow Fable to create new growth organs autonomously: "
            "regional desks, product-led affiliate network, API distribution, "
            "adviser/professional offering, contributor marketplace."
        ),
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Channels priority (docket §18)
# ─────────────────────────────────────────────────────────────────────────────

_CHANNELS_PRIORITY: dict[str, list[str]] = {
    "tier1": [
        "public_what_changed",
        "public_why_moving",
        "public_receipts",
        "email_newsletter",
        "x_flagship_desk",
        "x_chart_receipts_desk",
        "youtube_chart_explainers",
        "seo_intelligence_templates",
        "on_site_activation_lifecycle",
        "shareable_charts_dossiers",
    ],
    "tier2": [
        "creator_copilot",
        "reporter_newsletter_data_desk",
        "discord_telegram_apps",
        "embeds_widgets",
        "cobranded_reports",
        "partner_referral_dashboards",
        "tiktok_instagram",
    ],
    "tier3": [
        "stocktwits_authorized_lane",
        "reddit_community_participation",
        "expanded_account_network",
        "nonstandard_performance_partnerships",
        "international_multilingual_desks",
    ],
    "tier4": [
        "retargeting",
        "high_intent_search",
        "paid_amplification_organic_creative",
        "creator_paid_media",
        "larger_automated_spend",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Main assembler
# ─────────────────────────────────────────────────────────────────────────────

def build_state(root: Path | str | None = None, cfg: dict | None = None) -> dict:
    """Assemble the full marketing_state snapshot.

    Never-raise: returns {"state": "error", ...} on catastrophic failure.
    """
    try:
        r = _root_path(root)
        if cfg is None:
            cfg = _load_cfg(r)

        settings = (cfg or {}).get("settings", {}) or {}
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # --- Departments ---
        depts = dept_registry(cfg)
        depts_list = [d.as_dict() for d in depts]

        # --- CMO portfolio ---
        port = portfolio(depts_list)

        # --- Ledger data ---
        opps = read_jsonl(_ledger(r, "opportunities.jsonl"))
        campaigns = read_jsonl(_ledger(r, "campaigns.jsonl"))
        publications = read_jsonl(_ledger(r, "publications.jsonl"))
        experiments_raw = read_jsonl(_ledger(r, "experiments.jsonl"))
        growth_events_raw = read_jsonl(_ledger(r, "growth_events.jsonl"))
        claims_raw = read_jsonl(_ledger(r, "claims.jsonl"))

        # Score opportunities
        for opp in opps:
            opp["score"] = score_dict(opp)
            from engine.marketing.opportunity_bus import half_life_class
            opp["half_life_class"] = half_life_class(opp.get("source_type", ""))

        open_opps = [o for o in opps if o.get("status") == "open"]
        scored_opps = [o for o in opps if "score" in o and o["score"] > 0]
        newest_opps = sorted(opps, key=lambda o: o.get("detected_at", ""), reverse=True)[:3]

        active_campaigns = [c for c in campaigns if c.get("status") == "active"]
        shadow_campaigns = [c for c in campaigns if c.get("mode") == "shadow"]
        newest_campaigns = sorted(campaigns, key=lambda c: c.get("campaign_id", ""), reverse=False)[:3]

        total_pubs = len(publications)
        corrections = [p for p in publications if p.get("correction_state") != "clean"]
        newest_pubs = sorted(publications, key=lambda p: p.get("published_at", ""), reverse=True)[:3]

        running_exps = [e for e in experiments_raw if e.get("status") == "running"]
        newest_exps = experiments_raw[:3]

        claims_summary = claims_summarize(claims_raw)

        # --- Economics ---
        budget_alloc = BudgetAllocator(total_envelope_usd=0.0)
        budget_alloc.allocate(depts_list)

        # --- Desk network (with per-account tilt + mix_observed) ---
        dn = desk_network(cfg)

        # --- Content plan summary (reads data/marketing/content_plan.json if present) ---
        content_summary: dict = {
            "total_posts": None,
            "signal_posts": None,
            "charts": None,
            "accounts": None,
            "state": "accruing",
            "note": "Content plan not yet generated.",
        }
        content_plan_path = r / "data" / "marketing" / "content_plan.json"
        try:
            if content_plan_path.exists():
                import json as _json
                _cp = _json.loads(content_plan_path.read_text(encoding="utf-8"))
                _s = _cp.get("summary", {})
                content_summary = {
                    "total_posts": _s.get("total_posts"),
                    "signal_posts": _s.get("signal_posts"),
                    "charts": _s.get("charts"),
                    "accounts": _s.get("accounts"),
                    "state": "present",
                    "as_of": _cp.get("as_of"),
                }
        except Exception:  # noqa: BLE001
            pass

        # --- Self-improvement loop ---
        improvement = improvement_loop_state(
            loop_state="observing",
            next_review="2026-07-25",
        )

        # --- Opportunity queue depth ---
        opp_queue_depth = len(open_opps)

        state: dict[str, Any] = {
            "schema": "marketing.state/v1",
            "schema_version": 1,
            "as_of": today,
            "lobe": {
                "id": "marketing",
                "name": "Marketing",
                "lifecycle_state": "chartered",
                "authority_level": "G2",
                "mandate": mandate(cfg),
            },
            "north_star": {
                "metric": (
                    "Day-90 retained contribution profit generated by activated users "
                    "attributable incrementally to Marketing"
                ),
                "value": None,
                "state": "accruing",
                "note": (
                    "Accruing — requires two mature cohorts and holdout-validated "
                    "incrementality. No data yet (wave0)."
                ),
            },
            "cmo": {
                "director": "Fable",
                "portfolio": port,
                "opportunity_queue_depth": opp_queue_depth,
                "self_improvement": improvement,
                "guardrails": {
                    "self_deception_checks": self_deception_checks(),
                },
            },
            "departments": depts_list,
            "authority_ladder": LADDER,
            "desk_network": dn,
            "pipeline": {
                "opportunities": {
                    "open": len(open_opps),
                    "scored": len(scored_opps),
                    "newest": [
                        {
                            "id": o.get("opportunity_id", ""),
                            "problem_or_desire": o.get("problem_or_desire", ""),
                            "expected_value": o.get("expected_value", 0),
                            "score": o.get("score", 0),
                            "half_life_class": o.get("half_life_class", ""),
                            "status": o.get("status", ""),
                        }
                        for o in newest_opps
                    ],
                },
                "campaigns": {
                    "active": len(active_campaigns),
                    "shadow": len(shadow_campaigns),
                    "newest": [
                        {
                            "id": c.get("campaign_id", ""),
                            "objective": c.get("objective", ""),
                            "audience": c.get("audience", ""),
                            "promise": c.get("promise", ""),
                            "channels": c.get("channels", []),
                            "authority_level": c.get("authority_level", ""),
                            "status": c.get("status", "shadow"),
                        }
                        for c in newest_campaigns
                    ],
                },
                "publications": {
                    "total": total_pubs,
                    "receipts": total_pubs,
                    "corrections": len(corrections),
                    "newest": [
                        {
                            "id": p.get("publication_id", ""),
                            "channel": p.get("channel", ""),
                            "account": p.get("account", ""),
                            "status": p.get("correction_state", "clean"),
                            "published_at": p.get("published_at", ""),
                        }
                        for p in newest_pubs
                    ],
                },
                "experiments": {
                    "running": len(running_exps),
                    "newest": [
                        {
                            "id": e.get("experiment_id", ""),
                            "hypothesis": e.get("hypothesis", ""),
                            "primary_metric": e.get("primary_metric", ""),
                            "status": e.get("status", "planned"),
                        }
                        for e in newest_exps
                    ],
                },
                "growth_events": {
                    "instrumented": list(GROWTH_EVENTS),
                    "observed": len(growth_events_raw),
                },
            },
            "provenance": {
                "modes": ["neural_web", "marketing_original", "hybrid"],
                "claims": claims_summary,
            },
            "economics": {
                "formula": FORMULA,
                "cohorts": [],
                "budget_allocator": budget_alloc.as_dict(),
            },
            "channels_priority": _CHANNELS_PRIORITY,
            "waves": _WAVES,
            "content": content_summary,
            "notes": [
                "deterministic v1 substrate; agent actuation staged",
                "display-tier; originates no market signal or score",
                "self-deception guardrails enforced via append-only ledgers",
                "desk network stage A: human-in-loop actuation, content drafted for review",
            ],
        }

        return state

    except Exception as exc:  # noqa: BLE001
        log.warning("marketing state: build_state failed: %s", exc, exc_info=True)
        return {
            "schema": "marketing.state/v1",
            "schema_version": 1,
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "state": "error",
            "error": str(exc),
            "lobe": {"id": "marketing", "name": "Marketing", "lifecycle_state": "error"},
        }
