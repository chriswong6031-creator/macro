"""engine.marketing.allies — Allies W1 target ledger + materials kit engine.

MKT-D11 LAW: nothing outbound ships from this module.  All contact is operator-only.
No network calls, no LLM, no randomness.  Deterministic on each run.

Public API
----------
seed_targets(root=None)    -> list[dict]
score_target(t)            -> float
draft_referral(target_id, tier, billing) -> dict   (PAPER ONLY — persists nothing)
track_record_stats(root=None) -> dict
render_kit(target, stats)  -> str (markdown)
build_allies(root=None)    -> dict
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pricing constants — SOLE authorised source:
#   research/MONETIZATION_ACCESS_MASTERPLAN_BY_FABLE.md Amendment 1
#   (operator-ratified 2026-07-18, PRs #2923/#2943)
# ---------------------------------------------------------------------------
_PRICING: dict[str, dict[str, float]] = {
    "insider": {
        "monthly": 59.0,          # $59/mo billed monthly
        "annual_monthly": 49.0,   # $49/mo billed annually
        "annual_total": 588.0,    # $49 × 12 = $588/yr  (save 17%)
    },
    "pro": {
        "monthly": 89.0,          # $89/mo billed monthly
        "annual_monthly": 69.0,   # $69/mo billed annually
        "annual_total": 828.0,    # $69 × 12 = $828/yr  (save 22%)
    },
}

REFERRAL_SCHEMA = "marketing.allies_referral/v1"

# ---------------------------------------------------------------------------
# Style → topical_overlap map (documented weights)
# Overlap is 0..1 — how well a fund's angle matches our universe
# (US stocks / technicals / options / macro).
# superinvestor_value  0.80 — quality US equity focus aligns well
# activist             0.70 — US equity but angle is corporate action
# tiger_crossover      0.85 — growth tech + macro mix matches our universe
# event_distressed     0.60 — special situations, partial overlap
# macro_satellite      0.85 — macro framing maps directly
# quality_growth       0.80 — long-only growth equity, solid overlap
# sector_healthcare    0.55 — narrow sector, limited universe match
# sector_other         0.60 — other narrow sectors, partial match
# ---------------------------------------------------------------------------
_STYLE_OVERLAP: dict[str, float] = {
    "superinvestor_value": 0.80,
    "activist":            0.70,
    "tiger_crossover":     0.85,
    "event_distressed":    0.60,
    "macro_satellite":     0.85,
    "quality_growth":      0.80,
    "sector_healthcare":   0.55,
    "sector_other":        0.60,
}

# ---------------------------------------------------------------------------
# Newsletter → topical_overlap map (documented)
# semianalysis       0.75 — semis/AI infra; high US-stock relevance
# doomberg           0.65 — energy/commodities; partial overlap
# geopolitical_futures 0.55 — macro geopolitics, tangential
# clouded_judgment   0.70 — SaaS / software equities, good fit
# banking_on_ai      0.50 — fintech AI framing, indirect overlap
# ---------------------------------------------------------------------------
_FEED_OVERLAP: dict[str, float] = {
    "semianalysis":         0.75,
    "doomberg":             0.65,
    "geopolitical_futures": 0.55,
    "clouded_judgment":     0.70,
    "banking_on_ai":        0.50,
}

# Schema key set for ledger rows
_TARGET_SCHEMA_KEYS = {
    "schema", "target_id", "kind", "name", "platform", "source",
    "link", "style", "audience_tier", "topical_overlap",
    "receipt_friendly", "outreach_verdict", "rule_citation",
    "score", "status", "kit_path", "seeded_utc", "tier",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _repo_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _slugify(s: str) -> str:
    """Simple slug: lowercase, non-alnum → hyphen, collapse runs."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_config(root: Path) -> dict:
    """Load config.yml — fail-soft to {}."""
    try:
        import yaml  # type: ignore[import]
        cfg_path = root / "config.yml"
        with cfg_path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("allies: failed to load config.yml: %s", exc)
        return {}


def _load_allies_communities(root: Path) -> list[dict]:
    """Load config/allies_communities.yml — fail-soft to []."""
    try:
        import yaml  # type: ignore[import]
        p = root / "config" / "allies_communities.yml"
        with p.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("communities", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("allies: failed to load allies_communities.yml: %s", exc)
        return []


def _load_narrative_sources(root: Path) -> list[dict]:
    """Load config/narrative_sources.yml substack_rss — fail-soft to []."""
    try:
        import yaml  # type: ignore[import]
        p = root / "config" / "narrative_sources.yml"
        with p.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("substack_rss", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("allies: failed to load narrative_sources.yml: %s", exc)
        return []


def _write_atomic(path: Path, text: str) -> None:
    """Write text atomically (temp → os.replace).  open('w') truncation law."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=path.suffix)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise


# ---------------------------------------------------------------------------
# score_target
# ---------------------------------------------------------------------------

def score_target(t: dict) -> float:
    """Score a target deterministically.

    Formula (weights sum to 1.0):
        score = 0.45 * topical_overlap
              + 0.25 * (1.0 if receipt_friendly else 0.0)
              + 0.20 * access
              + 0.10 * audience

    access:
        open        → 1.0
        conditional → 0.7
        prohibited  → 0.1

    audience = audience_tier / 3  if audience_tier is not None else 0.5
    """
    overlap = float(t.get("topical_overlap") or 0.0)
    receipt_w = 1.0 if t.get("receipt_friendly") else 0.0

    verdict = str(t.get("outreach_verdict") or "open").lower()
    access_map = {"open": 1.0, "conditional": 0.7, "prohibited": 0.1}
    access = access_map.get(verdict, 0.5)

    tier = t.get("audience_tier")
    audience = (float(tier) / 3.0) if tier is not None else 0.5

    raw = 0.45 * overlap + 0.25 * receipt_w + 0.20 * access + 0.10 * audience
    return round(raw, 3)


# ---------------------------------------------------------------------------
# seed_targets
# ---------------------------------------------------------------------------

def seed_targets(root: Path | str | None = None) -> list[dict]:
    """Build the full deterministic target list from four in-repo sources.

    Sources:
        (a) 51 funds from config.yml smart_money.funds  → kind "fund_manager"
        (b) 5 newsletters from config/narrative_sources.yml substack_rss → kind "newsletter"
        (c) DannyTrades creator (engine/dannytrades_chip.py)  → kind "creator"
        (d) 11 communities from config/allies_communities.yml → kind "community"

    Returns rows sorted by target_id for determinism.
    Fails soft — returns [] on any uncaught exception.
    """
    try:
        r = _repo_root(root)
        today = _today_utc()
        rows: list[dict] = []

        # ── (a) Fund managers ────────────────────────────────────────────────
        try:
            cfg = _load_config(r)
            funds: dict[str, Any] = cfg.get("smart_money", {}).get("funds", {})
            for slug, meta in funds.items():
                if not isinstance(meta, dict):
                    continue
                name = str(meta.get("name") or slug)
                style = str(meta.get("style") or "")
                overlap = _STYLE_OVERLAP.get(style, 0.65)
                target_id = f"fund-{_slugify(slug)}"
                kit_path = f"data/marketing/allies_kits/{target_id}.md"
                t: dict[str, Any] = {
                    "schema": "marketing.allies_target/v1",
                    "target_id": target_id,
                    "kind": "fund_manager",
                    "name": name,
                    "platform": "press",
                    "source": "config.yml:smart_money.funds",
                    "link": f"site/fund_{_slugify(slug)}.html",
                    "style": style,
                    "audience_tier": None,
                    "topical_overlap": overlap,
                    "receipt_friendly": True,
                    "outreach_verdict": "open",
                    "rule_citation": None,
                    "score": 0.0,  # filled below
                    "status": "candidate",
                    "kit_path": kit_path,
                    "seeded_utc": today,
                    "tier": "display",
                }
                t["score"] = score_target(t)
                rows.append(t)
        except Exception as exc:  # noqa: BLE001
            log.warning("allies.seed_targets: funds block failed: %s", exc)

        # ── (b) Newsletters ──────────────────────────────────────────────────
        try:
            feeds = _load_narrative_sources(r)
            for feed in feeds:
                feed_id = str(feed.get("feed_id") or "")
                if not feed_id:
                    continue
                rss_url = str(feed.get("rss_url") or "")
                desc = str(feed.get("description") or feed_id)
                overlap = _FEED_OVERLAP.get(feed_id, 0.55)
                target_id = f"news-{_slugify(feed_id)}"
                kit_path = f"data/marketing/allies_kits/{target_id}.md"
                t = {
                    "schema": "marketing.allies_target/v1",
                    "target_id": target_id,
                    "kind": "newsletter",
                    "name": desc,
                    "platform": "substack",
                    "source": "config/narrative_sources.yml",
                    "link": rss_url,
                    "style": None,
                    "audience_tier": None,
                    "topical_overlap": overlap,
                    "receipt_friendly": True,
                    "outreach_verdict": "open",
                    "rule_citation": None,
                    "score": 0.0,
                    "status": "candidate",
                    "kit_path": kit_path,
                    "seeded_utc": today,
                    "tier": "display",
                }
                t["score"] = score_target(t)
                rows.append(t)
        except Exception as exc:  # noqa: BLE001
            log.warning("allies.seed_targets: newsletters block failed: %s", exc)

        # ── (c) DannyTrades creator ──────────────────────────────────────────
        # Source: engine/dannytrades_chip.py (studied in-repo).
        # Per DT-R15/DT-R16 (engine/dannytrades_chip.py module docstring):
        # all directional chip reads are DESCRIPTIVE-ONLY; the kit must note this.
        try:
            target_id = "creator-dannytrades"
            kit_path = f"data/marketing/allies_kits/{target_id}.md"
            t = {
                "schema": "marketing.allies_target/v1",
                "target_id": target_id,
                "kind": "creator",
                "name": "DannyTrades",
                "platform": "youtube",
                "source": "engine/dannytrades_chip.py",
                "link": None,
                "style": None,
                "audience_tier": None,
                "topical_overlap": 0.85,
                "receipt_friendly": True,
                "outreach_verdict": "open",
                "rule_citation": None,
                "score": 0.0,
                "status": "candidate",
                "kit_path": kit_path,
                "seeded_utc": today,
                "tier": "display",
            }
            t["score"] = score_target(t)
            rows.append(t)
        except Exception as exc:  # noqa: BLE001
            log.warning("allies.seed_targets: creator block failed: %s", exc)

        # ── (d) Communities ──────────────────────────────────────────────────
        # All 11 from config/allies_communities.yml.
        # Rule citation is MANDATORY per MKT-D11 law.
        # receipt_friendly = True for all 11: every community has effort/context rules.
        try:
            communities = _load_allies_communities(r)
            for com in communities:
                com_id = str(com.get("id") or "")
                if not com_id:
                    continue
                verdict_raw = str(com.get("verdict") or "conditional").lower()
                # Map yml verdict → outreach_verdict
                outreach_verdict = verdict_raw  # "prohibited" | "conditional"
                target_id = f"com-{_slugify(com_id)}"
                kit_path = f"data/marketing/allies_kits/{target_id}.md"

                # rule_citation is mandatory — copy verbatim from yml
                rule_citation = {
                    "rules_url":      str(com.get("rules_url") or ""),
                    "rule_ref":       str(com.get("rule_ref") or ""),
                    "retrieved_utc":  str(com.get("retrieved_utc") or ""),
                    "verdict":        verdict_raw,
                    "note":           str(com.get("note") or ""),
                }

                t = {
                    "schema": "marketing.allies_target/v1",
                    "target_id": target_id,
                    "kind": "community",
                    "name": str(com.get("name") or com_id),
                    "platform": str(com.get("platform") or ""),
                    "source": "config/allies_communities.yml",
                    "link": str(com.get("rules_url") or ""),
                    "style": None,
                    "audience_tier": com.get("audience_tier"),
                    "topical_overlap": float(com.get("topical_overlap") or 0.5),
                    "receipt_friendly": True,  # all 11 have effort/context rules
                    "outreach_verdict": outreach_verdict,
                    "rule_citation": rule_citation,
                    "score": 0.0,
                    "status": "candidate",
                    "kit_path": kit_path,
                    "seeded_utc": today,
                    "tier": "display",
                }
                t["score"] = score_target(t)
                rows.append(t)
        except Exception as exc:  # noqa: BLE001
            log.warning("allies.seed_targets: communities block failed: %s", exc)

        # Sort by target_id for determinism
        rows.sort(key=lambda x: x.get("target_id", ""))
        return rows

    except Exception as exc:  # noqa: BLE001
        log.warning("allies.seed_targets: top-level failure: %s", exc)
        return []


# ---------------------------------------------------------------------------
# draft_referral
# ---------------------------------------------------------------------------

def draft_referral(target_id: str, tier: str, billing: str) -> dict:
    """Return a PAPER-ONLY referral scaffold.  Persists NOTHING.

    Parameters
    ----------
    target_id : str    e.g. "fund-berkshire"
    tier      : str    "insider" | "pro"
    billing   : str    "monthly" | "annual"

    Returns a dict with schema marketing.allies_referral/v1.
    cut_pct and code stay None — the operator sets them when (if) the program
    is approved.  The D07 attribution join consumes utm_source and utm_campaign.

    Pricing source: research/MONETIZATION_ACCESS_MASTERPLAN_BY_FABLE.md
    Amendment 1 (operator-ratified 2026-07-18, PRs #2923/#2943).
    """
    tier_key = tier.lower()
    billing_key = billing.lower()
    prices = _PRICING.get(tier_key, _PRICING["insider"])
    list_price = prices["monthly"] if billing_key == "monthly" else prices["annual_monthly"]

    return {
        "schema": REFERRAL_SCHEMA,
        "code": None,
        "target_id": target_id,
        "tier": tier_key,
        "billing": billing_key,
        "list_price_usd": list_price,
        "cut_pct": None,  # operator decision — not set in W1
        "utm_source": "ally",
        "utm_campaign": target_id,
        "status": "draft",
        "operator_approved": False,
        "issued_utc": None,
    }


# ---------------------------------------------------------------------------
# track_record_stats
# ---------------------------------------------------------------------------

def track_record_stats(root: Path | str | None = None) -> dict:
    """Honest track-record stats from graded Prophet receipts.

    Loads site/prophet/index.json "plans", runs receipt_source.graded_receipts(),
    counts wins/losses/mixed.  Returns zeros/None on any missing data.
    Kits must print the null honestly — never hide it.
    """
    try:
        r = _repo_root(root)
        from engine.marketing import receipt_source
        from engine.marketing.chart_render import load_closes

        plans: list[dict] = []
        prophet_path = r / "site" / "prophet" / "index.json"
        if prophet_path.exists():
            try:
                idx = json.loads(prophet_path.read_text(encoding="utf-8"))
                plans = idx.get("plans", []) or []
            except Exception as exc:  # noqa: BLE001
                log.warning("allies.track_record_stats: could not read prophet index: %s", exc)

        def closes_loader(ticker: str):  # type: ignore[return]
            return load_closes(ticker, r, n=90)

        receipts = receipt_source.graded_receipts(plans, closes_loader=closes_loader)

        wins = sum(1 for rx in receipts if rx.get("kind") == "win")
        losses = sum(1 for rx in receipts if rx.get("kind") == "loss")
        mixed = sum(1 for rx in receipts if rx.get("kind") == "mixed")
        graded_n = len(receipts)
        # Win rate over DECISIVE outcomes only — a "mixed" receipt (target and
        # stop both touched in-window) is neither a win nor a loss, and folding
        # it into the denominator would misstate it as a miss.
        decisive = wins + losses
        win_rate = round(wins / decisive, 3) if decisive > 0 else None

        # publications.jsonl line count (if present)
        pubs_path = r / "data" / "marketing" / "publications.jsonl"
        publications_n = 0
        if pubs_path.exists():
            try:
                publications_n = sum(
                    1 for ln in pubs_path.read_text(encoding="utf-8").splitlines()
                    if ln.strip()
                )
            except Exception:  # noqa: BLE001
                publications_n = 0

        return {
            "graded_n": graded_n,
            "wins": wins,
            "losses": losses,
            "mixed": mixed,
            "win_rate": win_rate,
            "window_days": 14,
            "publications_n": publications_n,
        }

    except Exception as exc:  # noqa: BLE001
        log.warning("allies.track_record_stats: failed: %s", exc)
        return {
            "graded_n": 0,
            "wins": 0,
            "losses": 0,
            "mixed": 0,
            "win_rate": None,
            "window_days": 14,
            "publications_n": 0,
        }


# ---------------------------------------------------------------------------
# render_kit
# ---------------------------------------------------------------------------

def render_kit(target: dict, stats: dict) -> str:
    """Render a one-page markdown kit for a single target.

    Sections:
    1. Who + why aligned
    2. What we'd offer
    3. Honest track record
    4. Community-only rules banner (at top for community kind)
    5. Footer (on every kit)

    Never uses the word "validated".
    """
    kind = str(target.get("kind") or "")
    name = str(target.get("name") or target.get("target_id", ""))
    target_id = str(target.get("target_id") or "")
    overlap_pct = int(round(float(target.get("topical_overlap") or 0) * 100))
    style_or_desc = target.get("style") or kind
    score = target.get("score", 0.0)

    lines: list[str] = []

    # ── Community rules banner (at TOP) ────────────────────────────────────
    if kind == "community":
        rc = target.get("rule_citation") or {}
        verdict = str(rc.get("verdict") or "unknown").lower()
        rule_ref = str(rc.get("rule_ref") or "")
        rules_url = str(rc.get("rules_url") or "")
        retrieved = str(rc.get("retrieved_utc") or "")
        note = str(rc.get("note") or "")

        if verdict == "prohibited":
            banner_verdict = (
                "**PROHIBITED** — Self-promotion / tool posts are banned.  "
                "Operator route is paid ads or nothing."
            )
        else:
            banner_verdict = (
                f"**CONDITIONAL** — A sanctioned path exists.  "
                f"{note.strip()}"
            )

        lines += [
            "---",
            "## COMMUNITY RULES — READ BEFORE ANY ACTION",
            "",
            f"**Rule reference:** {rule_ref}",
            f"**Verdict:** {banner_verdict}",
            f"**Rules page:** {rules_url}",
            f"**Retrieved:** {retrieved}",
            "",
            "---",
            "",
        ]

    # ── Section 1: Who + why aligned ────────────────────────────────────────
    lines += [
        f"# Allies Kit — {name}",
        "",
        "## 1. Who + Why Aligned",
        "",
        f"- **Target:** {name}",
        f"- **Kind:** {kind}",
        f"- **Style / description:** {style_or_desc}",
        f"- **Topical overlap:** {overlap_pct}% — universe match (US stocks / technicals / options / macro)",
        f"- **Score:** {score:.3f} (display-tier ranking input only)",
        "",
    ]

    # Creator-specific note (DT-R15/DT-R16)
    if kind == "creator" and "danny" in name.lower():
        lines += [
            "> **Note (DT-R15/DT-R16):** Per research adjudication, DannyTrades directional chip reads are",
            "> DESCRIPTIVE-ONLY — accumulation level/motion; never scored, never a price target, no tilt claims.",
            "",
        ]

    # ── Section 2: What we'd offer ──────────────────────────────────────────
    lines += [
        "## 2. What We'd Offer",
        "",
        "- **Free Pro access** (duration: operator-set — not defined in W1).",
        "- **Custom chart pack** from our chart engine (built from real close data, no external dependencies).",
        "- **Paper-only affiliate option** (W1 — codes not yet issued):",
        "",
        "  | Tier | Monthly | Annual (per month) | Annual total |",
        "  |------|---------|-------------------|--------------|",
        f"  | Insider | ${_PRICING['insider']['monthly']:.0f}/mo | "
        f"${_PRICING['insider']['annual_monthly']:.0f}/mo | "
        f"${_PRICING['insider']['annual_total']:.0f}/yr (save 17%) |",
        f"  | Pro | ${_PRICING['pro']['monthly']:.0f}/mo | "
        f"${_PRICING['pro']['annual_monthly']:.0f}/mo | "
        f"${_PRICING['pro']['annual_total']:.0f}/yr (save 22%) |",
        "",
        "  *Pricing per MONETIZATION_ACCESS_MASTERPLAN Amendment 1 (#2923/#2943)*",
        "",
        "  **Affiliate cut: unset — operator decision; no referral codes exist yet.**",
        "",
    ]

    # ── Section 3: Honest track record ─────────────────────────────────────
    lines += ["## 3. Honest Track Record", ""]

    graded_n = stats.get("graded_n", 0)
    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    mixed = stats.get("mixed", 0)
    win_rate = stats.get("win_rate")
    window = stats.get("window_days", 14)
    pubs_n = stats.get("publications_n", 0)

    if graded_n == 0:
        lines += [
            f"No graded track record yet — 0 graded receipts in the last {window}d.",
            "",
        ]
    else:
        if win_rate is not None:
            wr_str = f"{win_rate * 100:.0f}%"
        else:
            wr_str = "n/a — no decisive outcomes yet"
        lines += [
            f"Graded receipts (last {window}d): {graded_n} — "
            f"{wins} wins / {losses} losses / {mixed} mixed (win rate {wr_str})",
            "",
        ]

    lines += [
        f"- Publications in ledger: {pubs_n}",
        "- Signal source: Prophet graded plans (real outcome, not backtest).",
        "",
    ]

    # ── Section 5: Footer ───────────────────────────────────────────────────
    lines += [
        "---",
        "",
        "*Internal materials — outreach is operator-only.  "
        "Nothing in this lane sends, posts, or contacts anyone (MKT-D11).*",
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# build_allies
# ---------------------------------------------------------------------------

def build_allies(root: Path | str | None = None) -> dict:
    """Build the allies target ledger and per-target kits.

    Writes:
        data/marketing/allies_targets.jsonl  (atomic)
        data/marketing/allies_kits/<target_id>.md  (atomic, one per target)

    Returns:
        {"targets": n, "kits": n, "ledger_path": str, "as_of": str}

    Never raises — mirrors the marketing_governor fail-soft contract.
    """
    result: dict[str, Any] = {"targets": 0, "kits": 0, "ledger_path": None, "as_of": None}
    try:
        r = _repo_root(root)
        today = _today_utc()

        targets = seed_targets(r)
        stats = track_record_stats(r)

        # Write ledger (atomic)
        ledger_path = r / "data" / "marketing" / "allies_targets.jsonl"
        ledger_lines = "\n".join(
            json.dumps(t, ensure_ascii=False, separators=(",", ":"))
            for t in targets
        ) + ("\n" if targets else "")
        _write_atomic(ledger_path, ledger_lines)

        # Write kits (atomic, one per target)
        kits_written = 0
        for t in targets:
            kit_rel = t.get("kit_path", "")
            if not kit_rel:
                continue
            kit_path = r / kit_rel
            try:
                md = render_kit(t, stats)
                _write_atomic(kit_path, md)
                kits_written += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("allies.build_allies: kit write failed for %s: %s", t.get("target_id"), exc)

        result["targets"] = len(targets)
        result["kits"] = kits_written
        result["ledger_path"] = str(ledger_path)
        result["as_of"] = today
        log.info(
            "allies.build_allies: %d targets, %d kits, ledger=%s",
            len(targets), kits_written, ledger_path,
        )

    except Exception as exc:  # noqa: BLE001
        log.warning("allies.build_allies: top-level failure: %s", exc, exc_info=True)
        result["error"] = str(exc)

    return result
