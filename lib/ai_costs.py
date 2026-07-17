"""lib/ai_costs.py — Unified AI usage and cost ledger.

PURPOSE
-------
Append-only JSONL ledger at data/ai_costs/usage.jsonl.  Every lane that makes
an AI call records a row with token counts, provider, model, and estimated cost
so the operator can audit spend, quota burn, and routing decisions in one place.

REDLINE (shared with key_pool / capability_broker):
    A secret VALUE must NEVER appear in a ledger row, log line, or return value
    of this module.  Only capability_id strings and env-var NAMES are stored.

NEVER-RAISE CONTRACT:
    record_usage() must never abort the calling lane.  All public functions
    catch ALL exceptions, log a warning, and return a safe fallback value.

Provider vocabulary (cost_basis meaning):
    "claude_oauth"  — subscription OAuth key;  cost_basis = "subscription"
                      est_cost_usd is the API-EQUIVALENT value, not billed USD
    "claude_api"    — metered API key;          cost_basis = "metered"
    "deepseek"      — DeepSeek API (metered);   cost_basis = "metered"
    "claude_cli"    — Claude Code CLI channel;  cost_basis = "subscription"
                      when tokens are parsed; "estimated" when guessed

Schema: ai_costs.usage.v1
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "ai_costs.usage.v1"
_LEDGER_REL = "data/ai_costs/usage.jsonl"
_PRICING_REL = "config/ai_pricing.yml"


# ── Path helpers ──────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    """Auto-detect repo root from this file's location (lib/)."""
    return Path(__file__).resolve().parent.parent


def _ledger_path(root: Path | None = None) -> Path:
    base = root if root is not None else _repo_root()
    return base / _LEDGER_REL


def _pricing_path(root: Path | None = None) -> Path:
    base = root if root is not None else _repo_root()
    return base / _PRICING_REL


# ── Pricing helpers ───────────────────────────────────────────────────────────

def _load_pricing(root: Path | None = None) -> dict[str, Any]:
    """Load config/ai_pricing.yml.  Returns {} on any error (NEVER-RAISE)."""
    try:
        import yaml
        p = _pricing_path(root)
        with open(p, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("ai_costs._load_pricing: %s", exc)
        return {}


def _resolve_model_rates(
    model: str | None,
    pricing: dict[str, Any],
) -> tuple[float, float, float, float] | None:
    """Return (in_rate, out_rate, read_mult, write_mult) per MTok, or None.

    Prefix-match: "claude-haiku-4-5-20251001" matches prefix "claude-haiku-4-5".
    Longest prefix wins.
    """
    if not model:
        return None
    per_mtok: dict[str, Any] = pricing.get("per_mtok") or {}
    cache: dict[str, Any] = pricing.get("cache") or {}

    read_mult: float = float(cache.get("read_multiplier", 0.10))
    write_mult: float = float(cache.get("write_5m_multiplier", 1.25))

    best_prefix = ""
    best_rates: dict[str, float] | None = None
    for prefix, rates in per_mtok.items():
        if model.startswith(prefix) and len(prefix) > len(best_prefix):
            best_prefix = prefix
            best_rates = rates

    if best_rates is None:
        return None

    in_rate = float(best_rates.get("input", 0.0))
    out_rate = float(best_rates.get("output", 0.0))
    return in_rate, out_rate, read_mult, write_mult


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    root: Path | None = None,
) -> float | None:
    """Estimate cost in USD for a call using config/ai_pricing.yml rates.

    Formula (all per 1e6 tokens):
        input * in_rate
        + output * out_rate
        + cache_read * in_rate * read_multiplier
        + cache_creation * in_rate * write_5m_multiplier

    Returns None when the model is not found in the pricing table.
    Never raises.
    """
    try:
        pricing = _load_pricing(root)
        rates = _resolve_model_rates(model, pricing)
        if rates is None:
            return None
        in_rate, out_rate, read_mult, write_mult = rates
        cost = (
            input_tokens * in_rate / 1_000_000
            + output_tokens * out_rate / 1_000_000
            + cache_read_tokens * in_rate * read_mult / 1_000_000
            + cache_creation_tokens * in_rate * write_mult / 1_000_000
        )
        return round(cost, 8)
    except Exception as exc:  # noqa: BLE001
        log.warning("ai_costs.estimate_cost_usd: %s", exc)
        return None


# ── Ledger read/write ─────────────────────────────────────────────────────────

def record_usage(
    *,
    lane: str,
    provider: str,
    model: str | None = None,
    key_id: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cost_basis: str = "metered",
    cycle_id: str = "",
    stage: str = "",
    note: str = "",
    est_cost_usd: float | None = None,
    root: Path | None = None,
) -> bool:
    """Append one usage row to data/ai_costs/usage.jsonl.

    When est_cost_usd is None it is computed from config/ai_pricing.yml.
    Returns True on success, False on any failure.  Never raises.

    Concurrency: single-line JSONL appends are well under PIPE_BUF (4096 B on
    Linux, 512 B POSIX minimum) so POSIX O_APPEND writes are atomic — parallel
    nightly lanes may interleave rows but cannot corrupt each other's writes.
    read_usage() skips corrupt lines defensively (the rare truncation case from
    non-POSIX filesystems or large rows).
    """
    try:
        if est_cost_usd is None and model is not None:
            est_cost_usd = estimate_cost_usd(
                model, input_tokens, output_tokens,
                cache_read_tokens, cache_creation_tokens, root=root,
            )

        row: dict[str, Any] = {
            "schema": SCHEMA,
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lane": lane,
            "provider": provider,
            "model": model,
            "key_id": key_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "est_cost_usd": est_cost_usd,
            "cost_basis": cost_basis,
            "cycle_id": cycle_id,
            "stage": stage,
            "note": note,
        }

        ledger = _ledger_path(root)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("ai_costs.record_usage: %s", exc)
        return False


def read_usage(root: Path | None = None, days: int | None = None) -> list[dict]:
    """Read all rows from the usage ledger.

    Skips corrupt lines silently (NEVER-RAISE).  When days is set returns only
    rows whose ts falls within the last `days` calendar days (UTC).
    """
    try:
        p = _ledger_path(root)
        if not p.exists():
            return []
        rows: list[dict] = []
        cutoff: datetime | None = None
        if days is not None:
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001 — corrupt line, skip
                log.warning("ai_costs.read_usage: skipping corrupt line")
                continue
            if cutoff is not None:
                try:
                    ts = datetime.fromisoformat(row.get("ts", "").replace("Z", "+00:00"))
                    if ts < cutoff:
                        continue
                except Exception:  # noqa: BLE001
                    pass
            rows.append(row)
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("ai_costs.read_usage: %s", exc)
        return []


# ── Summarize ─────────────────────────────────────────────────────────────────

def _empty_bucket() -> dict[str, Any]:
    return {"usd": 0.0, "input_tokens": 0, "output_tokens": 0, "calls": 0}


def _add_row_to_bucket(bucket: dict[str, Any], row: dict) -> None:
    bucket["usd"] += float(row.get("est_cost_usd") or 0.0)
    bucket["input_tokens"] += int(row.get("input_tokens") or 0)
    bucket["output_tokens"] += int(row.get("output_tokens") or 0)
    bucket["calls"] += 1


def summarize(root: Path | None = None) -> dict[str, Any]:
    """Aggregate usage statistics.

    Returns a dict with keys:
        today, d7, d30 — each {usd, input_tokens, output_tokens, calls}
        by_lane, by_provider, by_key, by_model — each a dict of 30-day aggregates
            keyed by the dimension value; each value is {usd, input_tokens,
            output_tokens, calls}
        recent — last 50 rows, newest first

    Never raises; returns an empty-bucket structure on any error.
    """
    try:
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        d7_start = now - timedelta(days=7)
        d30_start = now - timedelta(days=30)

        all_rows = read_usage(root=root)

        today_b = _empty_bucket()
        d7_b = _empty_bucket()
        d30_b = _empty_bucket()
        by_lane: dict[str, Any] = {}
        by_provider: dict[str, Any] = {}
        by_key: dict[str, Any] = {}
        by_model: dict[str, Any] = {}

        for row in all_rows:
            ts_str = row.get("ts", "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                ts = now  # treat unparseable ts as current so it counts in all windows

            if ts >= today_start:
                _add_row_to_bucket(today_b, row)
            if ts >= d7_start:
                _add_row_to_bucket(d7_b, row)
            if ts >= d30_start:
                _add_row_to_bucket(d30_b, row)

                # 30d dimension breakdowns
                lane = row.get("lane") or "unknown"
                by_lane.setdefault(lane, _empty_bucket())
                _add_row_to_bucket(by_lane[lane], row)

                provider = row.get("provider") or "unknown"
                by_provider.setdefault(provider, _empty_bucket())
                _add_row_to_bucket(by_provider[provider], row)

                key = row.get("key_id") or "none"
                by_key.setdefault(key, _empty_bucket())
                _add_row_to_bucket(by_key[key], row)

                model = row.get("model") or "unknown"
                by_model.setdefault(model, _empty_bucket())
                _add_row_to_bucket(by_model[model], row)

        # Round USD buckets to 6 dp to avoid FP noise in comparisons
        for b in [today_b, d7_b, d30_b]:
            b["usd"] = round(b["usd"], 6)
        for mapping in (by_lane, by_provider, by_key, by_model):
            for b in mapping.values():
                b["usd"] = round(b["usd"], 6)

        recent = list(reversed(all_rows))[:50]

        return {
            "today": today_b,
            "d7": d7_b,
            "d30": d30_b,
            "by_lane": by_lane,
            "by_provider": by_provider,
            "by_key": by_key,
            "by_model": by_model,
            "recent": recent,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("ai_costs.summarize: %s", exc)
        empty = _empty_bucket()
        return {
            "today": empty,
            "d7": _empty_bucket(),
            "d30": _empty_bucket(),
            "by_lane": {},
            "by_provider": {},
            "by_key": {},
            "by_model": {},
            "recent": [],
        }
