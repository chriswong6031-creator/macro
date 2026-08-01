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
_SHARD_REL = "data/ai_costs/usage.d"          # per-writer shard dir (merge-on-read)
_PRICING_REL = "config/ai_pricing.yml"
_STATE_ROOT_ENV = "AI_COSTS_STATE_ROOT"


# ── Lobe taxonomy ─────────────────────────────────────────────────────────────
# Every usage `lane` belongs to exactly one lobe.  The AI Cost page rolls spend
# up to the lobe so the operator can see, at a glance, which subsystem is
# burning the most tokens (and decide whether to throttle it).  A lane with no
# rule falls through to "Other" — add it here when a new lane is instrumented.

LOBE_ORDER: list[str] = [
    "Metabolism", "Master Brain", "Mastermind", "Marketing", "Prophet",
    "News", "Risk", "Narrative", "Altdata", "Qual", "Research",
    "Whitehouse", "Translate", "Special Situations", "Codex", "Other",
]

_LANE_LOBE_EXACT: dict[str, str] = {
    "master-brain": "Master Brain",
    "brain-fast": "Mastermind", "brain-pro": "Mastermind",
    "ask-brain": "Mastermind", "cortex": "Mastermind",
    "orchestrator-chat": "Mastermind",
    "narrative-brain": "Narrative",
    "whitehouse": "Whitehouse",
    "altdata-brain": "Altdata", "influence-extract": "Altdata",
    "foresight-analyst": "Altdata",
    "earnings_qual": "Qual", "extraction-drift": "Qual",
    "qual-extraction": "Qual",
    "commodity-news": "News", "news-llm": "News", "catalyst-tone": "News",
    "china-news": "News", "macro-news": "News", "china-news-intel": "News",
    "news-translate": "News",
    "causal-brainstorm": "Research", "signal-foundry": "Research",
    "translate": "Translate", "translate-profiles": "Translate",
    "special-situations": "Special Situations",
    "prophet-autopsy": "Prophet",
}

# Ordered prefix rules — first match wins; keep more specific prefixes first.
_LANE_LOBE_PREFIX: list[tuple[str, str]] = [
    ("metabolism-", "Metabolism"),
    ("marketing-", "Marketing"),
    ("prophet-", "Prophet"),
    ("risk-", "Risk"),
    ("brain-", "Mastermind"),
    ("narrative-", "Narrative"),
    ("altdata-", "Altdata"),
    ("news-", "News"),
    ("codex", "Codex"),
]


def lobe_for_lane(lane: str | None) -> str:
    """Map a usage `lane` string to its owning lobe.  Never raises."""
    if not lane:
        return "Other"
    key = str(lane).strip().lower()
    if key in _LANE_LOBE_EXACT:
        return _LANE_LOBE_EXACT[key]
    for prefix, lobe in _LANE_LOBE_PREFIX:
        if key.startswith(prefix):
            return lobe
    return "Other"


# ── Path helpers ──────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    """Auto-detect repo root from this file's location (lib/)."""
    return Path(__file__).resolve().parent.parent


def _state_root() -> Path:
    """Resolve the mutable-ledger root without moving repository config.

    Long-lived appliances can set ``AI_COSTS_STATE_ROOT`` to keep append-only
    usage telemetry outside their immutable Git checkout. Pricing continues to
    come from the repository unless a caller supplies the existing explicit
    ``root=`` test/diagnostic override.
    """
    override = os.environ.get(_STATE_ROOT_ENV, "").strip()
    if not override:
        return _repo_root()

    candidate = Path(override).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"{_STATE_ROOT_ENV} must be an absolute path")
    resolved = candidate.resolve(strict=False)
    repo = _repo_root().resolve(strict=False)
    home = Path.home().resolve(strict=False)
    filesystem_root = Path(resolved.anchor)
    if resolved in {filesystem_root, home}:
        raise ValueError(f"{_STATE_ROOT_ENV} is too broad for mutable telemetry")
    if resolved == repo or repo in resolved.parents:
        raise ValueError(f"{_STATE_ROOT_ENV} must live outside the repository")
    return resolved


def _ledger_path(root: Path | None = None) -> Path:
    base = root if root is not None else _state_root()
    return base / _LEDGER_REL


def _shard_dir(root: Path | None = None) -> Path:
    base = root if root is not None else _state_root()
    return base / _SHARD_REL


def _sanitize_shard(name: str) -> str:
    """Keep only filename-safe chars so a shard token can't escape the dir.

    Dots are disallowed too (collapsed to '-') so a token can never form a
    '..' traversal component; the '.jsonl' suffix is appended separately.
    """
    return "".join(c if (c.isalnum() or c in "-_") else "-" for c in name)[:120]


def _write_ledger_path(root: Path | None = None) -> Path:
    """Where record_usage should append.

    When AI_COSTS_SHARD is set (CI / multi-writer environments) each writer
    appends to its OWN shard file under data/ai_costs/usage.d/<shard>.jsonl so
    parallel GitHub-Actions lanes never merge-conflict on the shared ledger.
    read_usage() merges the main ledger + every shard, so the split is
    invisible to consumers.  Unset (local/dev) → the canonical usage.jsonl.
    """
    shard = os.environ.get("AI_COSTS_SHARD", "").strip()
    if shard:
        return _shard_dir(root) / f"{_sanitize_shard(shard)}.jsonl"
    return _ledger_path(root)


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

        ledger = _write_ledger_path(root)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("ai_costs.record_usage: %s", exc)
        return False


def infer_provider(base_url: str | None, *, oauth: bool = False) -> tuple[str, str]:
    """Infer (provider, cost_basis) for a direct-SDK call site.

    Direct-client engines default to DeepSeek (base_url set) but are operator-
    switchable to a Claude credential.  Centralised so every call site tags
    spend the same way.  Never raises.
        oauth=True                 → ("claude_oauth", "subscription")
        base_url contains deepseek → ("deepseek", "metered")
        other non-anthropic base   → ("openai_compat", "metered")   # local/qwen
        else                       → ("claude_api", "metered")
    """
    try:
        b = (base_url or "").lower()
        if oauth:
            return "claude_oauth", "subscription"
        if "deepseek" in b:
            return "deepseek", "metered"
        if b and "anthropic" not in b:
            return "openai_compat", "metered"
        return "claude_api", "metered"
    except Exception:  # noqa: BLE001
        return "claude_api", "metered"


def record_response_usage(
    *,
    lane: str,
    response: Any,
    model: str | None = None,
    provider: str = "claude_api",
    cost_basis: str = "metered",
    key_id: str | None = None,
    cycle_id: str = "",
    stage: str = "",
    note: str = "",
    root: Path | None = None,
) -> bool:
    """Extract token usage from an anthropic-style response and record one row.

    Convenience for direct-SDK call sites that do NOT route through
    engine.llm_auth.make_call (which captures usage automatically).  Reads the
    standard anthropic Usage attributes off `response.usage`.  Returns False
    (no row) when the response carries no usage object.  Never raises.
    """
    try:
        u = getattr(response, "usage", None)
        if u is None:
            return False
        return record_usage(
            lane=lane,
            provider=provider,
            model=model,
            key_id=key_id,
            input_tokens=int(getattr(u, "input_tokens", 0) or 0),
            output_tokens=int(getattr(u, "output_tokens", 0) or 0),
            cache_read_tokens=int(getattr(u, "cache_read_input_tokens", 0) or 0),
            cache_creation_tokens=int(getattr(u, "cache_creation_input_tokens", 0) or 0),
            cost_basis=cost_basis,
            cycle_id=cycle_id,
            stage=stage,
            note=note,
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("ai_costs.record_response_usage: %s", exc)
        return False


def read_usage(root: Path | None = None, days: int | None = None) -> list[dict]:
    """Read all rows from the usage ledger.

    Skips corrupt lines silently (NEVER-RAISE).  When days is set returns only
    rows whose ts falls within the last `days` calendar days (UTC).
    """
    try:
        # Merge the canonical ledger + every per-writer shard (see
        # _write_ledger_path).  Sorted for deterministic ordering across runs.
        sources: list[Path] = []
        main = _ledger_path(root)
        if main.exists():
            sources.append(main)
        shard_dir = _shard_dir(root)
        if shard_dir.is_dir():
            sources.extend(sorted(shard_dir.glob("*.jsonl")))
        if not sources:
            return []

        rows: list[dict] = []
        cutoff: datetime | None = None
        if days is not None:
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        for p in sources:
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001 — unreadable shard, skip
                log.warning("ai_costs.read_usage: skipping unreadable %s", p.name)
                continue
            for line in text.splitlines():
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

        # Global chronological order (shards interleave with the main ledger).
        rows.sort(key=lambda r: r.get("ts", ""))
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


def _pct(part: float, whole: float) -> float:
    """Percentage of `whole`, rounded to 1 dp.  0.0 when whole is 0."""
    return round(100.0 * part / whole, 1) if whole else 0.0


def _add_pcts(bucket: dict[str, Any], tot_usd: float, tot_tok: int, tot_calls: int) -> None:
    """Annotate one aggregate bucket with pct_usd / pct_tokens / pct_calls."""
    tok = int(bucket.get("input_tokens", 0)) + int(bucket.get("output_tokens", 0))
    bucket["tokens"] = tok
    bucket["pct_usd"] = _pct(float(bucket.get("usd", 0.0)), tot_usd)
    bucket["pct_tokens"] = _pct(tok, tot_tok)
    bucket["pct_calls"] = _pct(int(bucket.get("calls", 0)), tot_calls)


def _rank(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    """Return buckets as a USD-descending list, each carrying its `name`."""
    out = [{"name": k, **v} for k, v in mapping.items()]
    out.sort(key=lambda b: (float(b.get("usd", 0.0)), b.get("tokens", 0)), reverse=True)
    return out


def _cost_basis_bucketname(row: dict) -> str:
    """Group a row into 'subscription' (OAuth/CLI flat-fee) or 'metered' (API/DeepSeek)."""
    cb = str(row.get("cost_basis") or "").lower()
    if cb in ("subscription", "estimated"):
        return "subscription"
    if cb == "metered":
        return "metered"
    # Fall back on provider when cost_basis is missing/unknown.
    prov = str(row.get("provider") or "").lower()
    return "subscription" if prov in ("claude_oauth", "claude_cli") else "metered"


def summarize(root: Path | None = None) -> dict[str, Any]:
    """Aggregate usage statistics across the ledger + all shards.

    Returns a dict with keys:
        today, d7, d30 — each {usd, input_tokens, output_tokens, calls}
        by_lane, by_provider, by_key, by_model, by_cost_basis — 30-day
            aggregates keyed by the dimension value; each value is
            {usd, input_tokens, output_tokens, calls, tokens, pct_usd,
             pct_tokens, pct_calls}
        by_lobe — {lobe: {...aggregate..., lanes: {lane: {...aggregate...,
            stages: {stage: {...aggregate...}}}}}}, rolled up via lobe_for_lane
        lobe_order — the canonical lobe display order
        totals_30d — {usd, input_tokens, output_tokens, tokens, calls}
        recent — last 50 rows, newest first

    All aggregate buckets are also exposed pre-ranked (USD desc) under the
    *_ranked keys for direct rendering.  Never raises.
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
        by_cost_basis: dict[str, Any] = {}
        # lane -> stage -> bucket (for lobe drill-down)
        lane_stages: dict[str, dict[str, Any]] = {}

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

                cbn = _cost_basis_bucketname(row)
                by_cost_basis.setdefault(cbn, _empty_bucket())
                _add_row_to_bucket(by_cost_basis[cbn], row)

                stage = (row.get("stage") or "").strip()
                if stage:
                    lane_stages.setdefault(lane, {})
                    lane_stages[lane].setdefault(stage, _empty_bucket())
                    _add_row_to_bucket(lane_stages[lane][stage], row)

        # 30d totals form the percentage base for every breakdown.
        tot_usd = float(d30_b["usd"])
        tot_tok = int(d30_b["input_tokens"]) + int(d30_b["output_tokens"])
        tot_calls = int(d30_b["calls"])

        # Round the window totals + annotate pct on every breakdown bucket.
        for b in [today_b, d7_b, d30_b]:
            b["usd"] = round(b["usd"], 6)
            b["tokens"] = int(b["input_tokens"]) + int(b["output_tokens"])
        for mapping in (by_lane, by_provider, by_key, by_model, by_cost_basis):
            for b in mapping.values():
                b["usd"] = round(b["usd"], 6)
                _add_pcts(b, tot_usd, tot_tok, tot_calls)

        # Roll lanes up into lobes (lobe -> lanes -> stages).
        by_lobe: dict[str, Any] = {}
        for lane, lb in by_lane.items():
            lobe = lobe_for_lane(lane)
            lobe_b = by_lobe.setdefault(lobe, {**_empty_bucket(), "lanes": {}})
            for fld in ("usd", "input_tokens", "output_tokens", "calls"):
                lobe_b[fld] += lb[fld]
            lane_entry = {k: lb[k] for k in ("usd", "input_tokens", "output_tokens",
                                             "calls", "tokens", "pct_usd",
                                             "pct_tokens", "pct_calls")}
            # attach stage drill-down (ranked) when the lane carries stages
            stages = lane_stages.get(lane) or {}
            if stages:
                for sb in stages.values():
                    sb["usd"] = round(sb["usd"], 6)
                    _add_pcts(sb, float(lb["usd"]) or 0.0,
                              int(lb["tokens"]) or 0, int(lb["calls"]) or 0)
                lane_entry["stages"] = _rank(stages)
            lobe_b["lanes"][lane] = lane_entry
        for lobe_b in by_lobe.values():
            lobe_b["usd"] = round(lobe_b["usd"], 6)
            _add_pcts(lobe_b, tot_usd, tot_tok, tot_calls)
            lobe_b["lanes_ranked"] = _rank(lobe_b["lanes"])

        recent = list(reversed(all_rows))[:50]

        return {
            "today": today_b,
            "d7": d7_b,
            "d30": d30_b,
            "totals_30d": {
                "usd": round(tot_usd, 6), "tokens": tot_tok,
                "input_tokens": int(d30_b["input_tokens"]),
                "output_tokens": int(d30_b["output_tokens"]),
                "calls": tot_calls,
            },
            "by_lane": by_lane,
            "by_provider": by_provider,
            "by_key": by_key,
            "by_model": by_model,
            "by_cost_basis": by_cost_basis,
            "by_lobe": by_lobe,
            "lobe_order": LOBE_ORDER,
            "lobe_ranked": _rank({k: {kk: vv for kk, vv in v.items()
                                      if kk not in ("lanes",)}
                                  for k, v in by_lobe.items()}),
            "by_lane_ranked": _rank(by_lane),
            "by_provider_ranked": _rank(by_provider),
            "by_model_ranked": _rank(by_model),
            "by_key_ranked": _rank(by_key),
            "recent": recent,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("ai_costs.summarize: %s", exc)
        empty = _empty_bucket()
        return {
            "today": empty,
            "d7": _empty_bucket(),
            "d30": _empty_bucket(),
            "totals_30d": {"usd": 0.0, "tokens": 0, "input_tokens": 0,
                           "output_tokens": 0, "calls": 0},
            "by_lane": {},
            "by_provider": {},
            "by_key": {},
            "by_model": {},
            "by_cost_basis": {},
            "by_lobe": {},
            "lobe_order": LOBE_ORDER,
            "lobe_ranked": [],
            "by_lane_ranked": [],
            "by_provider_ranked": [],
            "by_model_ranked": [],
            "by_key_ranked": [],
            "recent": [],
        }
