"""Private Prophet Trade Memory: evidence packets, autopsies, and pattern accrual.

This module is the reasoning half of the Trade Memory department.  It deliberately
does not own a second market-data knowledge base:

* operator episodes live in the owner-scoped Supabase ``trade_episodes`` table;
* Prophet episodes continue to live in the existing forward ledgers;
* historical analogues continue to live in Winner Autopsy / Codex Research;
* point-in-time context is read from :mod:`engine.neuralweb.context_api`.

The write/manage/read boundary is strict.  Deterministic evidence is built first.
An LLM may then explain that evidence and propose measurable hypotheses, but every
hypothesis is stamped ``research_only`` and ``direct_authority=False``.  Nothing in
this module ranks, sizes, gates, suppresses, or escalates a live signal.
"""
from __future__ import annotations

import json
import logging
import math
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("neuralweb.trade_memory")

SCHEMA_EPISODE = "prophet.trade_episode/v1"
SCHEMA_EVIDENCE = "prophet.trade_evidence/v1"
SCHEMA_AUTOPSY = "prophet.trade_autopsy/v1"
SCHEMA_PATTERN = "prophet.trade_pattern/v1"

SOURCES = frozenset({"operator", "prophet", "historical_replay"})
SIDES = frozenset({"long", "short"})
OUTCOMES = frozenset({"open", "win", "loss", "flat"})
EVIDENCE_STATES = frozenset({"corroborated", "contradicted", "claimed", "unknown"})
TIMING_STATES = frozenset({"known_at_entry", "emerged_after", "hindsight_only", "unknown"})
LAYERS = frozenset({
    "macro_regime",
    "market_rotation",
    "sector",
    "company_alpha",
    "catalyst",
    "entry_timing",
    "path_risk",
    "counterfactual",
})
MITIGATION_VERDICTS = frozenset({
    "mitigable_process",
    "mitigable_conditioning",
    "external_unforeseeable",
    "external_foreseeable_unpriced",
    "not_a_failure",
})

# Same canonical sector proxy mapping used by Pick Lab.
GICS_ETF: dict[str, str] = {
    "Energy": "XLE",
    "Information Technology": "XLK",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Utilities": "XLU",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,19}$")
_FEATURE_RE = re.compile(r"[^a-z0-9]+")
_OPUS_FALLBACK = "claude-opus-4-8"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_text(value: Any, field: str, required: bool = False) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        if required:
            raise ValueError(f"{field} is required")
        return None
    try:
        return date.fromisoformat(raw[:10]).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def _price(value: Any, field: str) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a positive number")
    try:
        n = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive number") from exc
    if not math.isfinite(n) or n <= 0 or n > 10_000_000:
        raise ValueError(f"{field} must be a positive number")
    return round(n, 8)


def _text(value: Any, field: str, limit: int) -> str:
    raw = str(value or "").strip()
    if len(raw) > limit:
        raise ValueError(f"{field} must be at most {limit} characters")
    return raw


def normalize_episode(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize an operator episode.

    Position size, account value, and dollar P&L are intentionally absent from
    the contract.  They are unnecessary for causal attribution and would widen
    the blast radius of a private-store error.
    """
    if not isinstance(payload, dict):
        raise ValueError("episode must be an object")

    forbidden = {"quantity", "shares", "position_size", "account_value", "realized_pnl", "pnl"}
    leaked = sorted(k for k in forbidden if payload.get(k) not in (None, ""))
    if leaked:
        raise ValueError("Trade Memory does not store position size or dollar P&L")

    ticker = str(payload.get("ticker") or "").strip().upper()
    if not _TICKER_RE.fullmatch(ticker):
        raise ValueError("ticker must contain only letters, numbers, dot, dash, or underscore")

    source = str(payload.get("source") or "operator").strip().lower()
    if source not in SOURCES:
        raise ValueError(f"source must be one of {sorted(SOURCES)}")
    side = str(payload.get("side") or "long").strip().lower()
    if side not in SIDES:
        raise ValueError(f"side must be one of {sorted(SIDES)}")
    outcome = str(payload.get("outcome") or "open").strip().lower()
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {sorted(OUTCOMES)}")

    entry_date = _date_text(payload.get("entry_date"), "entry_date", required=True)
    exit_date = _date_text(payload.get("exit_date"), "exit_date")
    if exit_date and exit_date < entry_date:
        raise ValueError("exit_date cannot be before entry_date")
    if outcome != "open" and not exit_date:
        raise ValueError("closed outcomes require exit_date")

    entry_price = _price(payload.get("entry_price"), "entry_price")
    exit_price = _price(payload.get("exit_price"), "exit_price")
    if outcome == "open" and (exit_date or exit_price is not None):
        raise ValueError("open outcomes cannot have an exit_date or exit_price")
    if outcome != "open" and (entry_price is None) != (exit_price is None):
        raise ValueError("provide both entry_price and exit_price, or leave both blank")

    market = _text(payload.get("market") or "us", "market", 20).lower()
    if not re.fullmatch(r"[a-z0-9_-]{1,20}", market):
        raise ValueError("market must contain only letters, numbers, dash, or underscore")

    return {
        "schema": SCHEMA_EPISODE,
        "source": source,
        "ticker": ticker,
        "market": market,
        "side": side,
        "entry_date": entry_date,
        "exit_date": exit_date,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "outcome": outcome,
        "thesis_at_entry": _text(payload.get("thesis_at_entry"), "thesis_at_entry", 8_000),
        "observed_result": _text(payload.get("observed_result"), "observed_result", 8_000),
        "prophet_pick_ref": _text(payload.get("prophet_pick_ref"), "prophet_pick_ref", 240),
    }


def _jsonable(value: Any) -> Any:
    """Convert pandas/numpy/date values to bounded JSON-safe primitives."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "item"):
        try:
            return _jsonable(value.item())
        except Exception:  # noqa: BLE001
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            pass
    return str(value)


def _load_close(root: Path, ticker: str):
    """Load a daily close series from canonical local stores, fail-soft."""
    try:
        import pandas as pd  # noqa: PLC0415
    except Exception:  # pragma: no cover - production requirements carry pandas
        return None
    candidates = (
        root / "data" / "baskets" / "ohlcv" / f"{ticker}.parquet",
        root / "data" / "stocks" / f"{ticker}.parquet",
        root / "data" / "yahoo" / f"{ticker}.parquet",
    )
    for path in candidates:
        if not path.exists():
            continue
        try:
            frame = pd.read_parquet(path)
            if isinstance(frame, pd.Series):
                series = frame
            else:
                col = next((c for c in ("close", "Close", "adj_close", "Adj Close") if c in frame.columns), None)
                if col is None:
                    continue
                series = frame[col]
            if not isinstance(series.index, pd.DatetimeIndex):
                for dcol in ("date", "Date", "datetime", "timestamp"):
                    if dcol in frame.columns:
                        series.index = pd.to_datetime(frame[dcol], errors="coerce")
                        break
            series.index = pd.to_datetime(series.index, errors="coerce").tz_localize(None)
            series = pd.to_numeric(series, errors="coerce").dropna().sort_index()
            if not series.empty:
                return series[~series.index.duplicated(keep="last")]
        except Exception as exc:  # noqa: BLE001
            log.debug("trade_memory: close load failed for %s (%s)", path.name, type(exc).__name__)
    return None


def _sector_for(root: Path, ticker: str) -> str | None:
    path = root / "data" / "breadth" / "ticker_sectors.parquet"
    if not path.exists():
        return None
    try:
        import pandas as pd  # noqa: PLC0415
        frame = pd.read_parquet(path)
        if "ticker" in frame.columns:
            rows = frame[frame["ticker"].astype(str).str.upper() == ticker]
            if not rows.empty:
                value = rows.iloc[-1].get("sector")
                return str(value) if value is not None and not pd.isna(value) else None
        if ticker in frame.index:
            value = frame.loc[ticker].get("sector")
            return str(value) if value is not None and not pd.isna(value) else None
    except Exception as exc:  # noqa: BLE001
        log.debug("trade_memory: sector map unavailable (%s)", type(exc).__name__)
    return None


def _window(series, start: str, end: str):
    if series is None:
        return None
    try:
        import pandas as pd  # noqa: PLC0415
        s = series[(series.index >= pd.Timestamp(start)) & (series.index <= pd.Timestamp(end))]
        return s if len(s) >= 1 else None
    except Exception:  # noqa: BLE001
        return None


def _return_leg(series, start: str, end: str, start_override: float | None = None,
                end_override: float | None = None) -> dict[str, Any]:
    window = _window(series, start, end)
    if window is None or window.empty:
        return {"available": False, "reason": "price window unavailable"}
    p0 = float(start_override) if start_override is not None else float(window.iloc[0])
    p1 = float(end_override) if end_override is not None else float(window.iloc[-1])
    if p0 <= 0:
        return {"available": False, "reason": "non-positive entry price"}
    rets = window.astype(float) / p0 - 1.0
    return {
        "available": True,
        "observed_start": str(window.index[0].date()),
        "observed_end": str(window.index[-1].date()),
        "start_price": round(p0, 6),
        "end_price": round(p1, 6),
        "return": round(p1 / p0 - 1.0, 8),
        "mfe": round(float(rets.max()), 8),
        "mae": round(float(rets.min()), 8),
    }


def build_evidence_packet(episode: dict[str, Any], root: str | Path | None = None) -> dict[str, Any]:
    """Build the deterministic, point-in-time packet an autopsy is allowed to read."""
    normalized = normalize_episode(episode)
    repo = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    ticker = normalized["ticker"]
    exit_date = normalized.get("exit_date")
    if not exit_date:
        raise ValueError("an autopsy requires a closed episode with exit_date")

    stock = _return_leg(
        _load_close(repo, ticker),
        normalized["entry_date"],
        exit_date,
        normalized.get("entry_price"),
        normalized.get("exit_price"),
    )
    market_ticker = "SPY" if normalized["market"] == "us" else None
    market = (
        _return_leg(_load_close(repo, market_ticker), normalized["entry_date"], exit_date)
        if market_ticker else {"available": False, "reason": "market proxy not mapped"}
    )
    sector = _sector_for(repo, ticker)
    sector_ticker = GICS_ETF.get(sector or "")
    sector_leg = (
        _return_leg(_load_close(repo, sector_ticker), normalized["entry_date"], exit_date)
        if sector_ticker else {"available": False, "reason": "sector proxy not mapped"}
    )

    decomposition: dict[str, Any] = {
        "method": "arithmetic return attribution; descriptive, not causal",
        "market_proxy": market_ticker,
        "sector": sector,
        "sector_proxy": sector_ticker,
        "stock": stock,
        "market": market,
        "sector_leg": sector_leg,
        "sector_minus_market": None,
        "stock_minus_sector": None,
        "stock_minus_market": None,
    }
    sr = stock.get("return") if stock.get("available") else None
    mr = market.get("return") if market.get("available") else None
    xr = sector_leg.get("return") if sector_leg.get("available") else None
    if xr is not None and mr is not None:
        decomposition["sector_minus_market"] = round(xr - mr, 8)
    if sr is not None and xr is not None:
        decomposition["stock_minus_sector"] = round(sr - xr, 8)
    if sr is not None and mr is not None:
        decomposition["stock_minus_market"] = round(sr - mr, 8)

    try:
        from engine.neuralweb.context_api import context_snapshot  # noqa: PLC0415
        entry_context = context_snapshot(ticker, date=normalized["entry_date"], root=repo)
    except Exception as exc:  # noqa: BLE001
        entry_context = {
            "ticker": ticker,
            "date": normalized["entry_date"],
            "absent": True,
            "reason": f"context snapshot unavailable: {type(exc).__name__}",
        }

    return _jsonable({
        "schema": SCHEMA_EVIDENCE,
        "generated_at": _utc_now(),
        "episode": normalized,
        "return_attribution": decomposition,
        "entry_context": entry_context,
        "epistemic_rules": {
            "operator_text_is": "claim_until_corroborated",
            "entry_context_is": "point_in_time_only",
            "return_attribution_is": "descriptive_not_causal",
            "missing_is": "unknown_not_neutral",
            "direct_authority": False,
        },
    })


def autopsy_messages(packet: dict[str, Any]) -> tuple[str, str]:
    """Return the fixed system/user prompt for a private episode autopsy."""
    system = f"""You are Prophet Trade Memory, a forensic market analyst.
You receive a deterministic evidence packet for one completed trade. Separate facts,
operator claims, and inference. Reconstruct first-, second-, and third-order mechanisms,
but never invent evidence. A factor that appeared after entry is hindsight, not an
ex-ante reason. Test market, sector, company, catalyst, entry timing, path risk, and
counterfactual explanations. Name plausible alternatives and missing evidence.

You are a research-only memory writer. You may not emit a live signal, score, rank,
position size, gate, suppression, or attention escalation. Any measurable idea is only
a hypothesis for the existing Research Factory / Causal Lab.

Return one JSON object with exactly these top-level keys:
  schema: "{SCHEMA_AUTOPSY}"
  summary: concise plain-language explanation
  mitigation_verdict: one of {sorted(MITIGATION_VERDICTS)}
  causal_chain: list of objects with keys
    order (1, 2, or 3), layer, factor, mechanism, evidence_status, timing_status,
    counterfactual, evidence_refs
  alternate_explanations: list of strings
  missing_evidence: list of strings
  lesson: one concise process lesson
  signal_hypotheses: list of objects with keys feature_key, feature, measurement,
    expected_direction, falsifier, authority

Closed enums:
  layer: {sorted(LAYERS)}
  evidence_status: {sorted(EVIDENCE_STATES)}
  timing_status: {sorted(TIMING_STATES)}
For every signal_hypothesis authority MUST be "research_only".
Do not use the word validated."""
    user = "AUTOPSY EVIDENCE PACKET:\n" + json.dumps(packet, ensure_ascii=False, default=str)
    return system, user


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except Exception:  # noqa: BLE001
            return None


def _short(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _feature_key(value: Any) -> str:
    key = _FEATURE_RE.sub("_", str(value or "").strip().lower()).strip("_")
    return key[:96]


def parse_autopsy(text: str, packet: dict[str, Any]) -> dict[str, Any] | None:
    """Validate an LLM autopsy and stamp its non-authority boundary."""
    data = _extract_json_object(text)
    if data is None:
        return None

    verdict = str(data.get("mitigation_verdict") or "").strip()
    if verdict not in MITIGATION_VERDICTS:
        verdict = "invalid"

    chain: list[dict[str, Any]] = []
    for raw in data.get("causal_chain") or []:
        if not isinstance(raw, dict):
            continue
        try:
            order = int(raw.get("order"))
        except (TypeError, ValueError):
            continue
        layer = str(raw.get("layer") or "")
        evidence = str(raw.get("evidence_status") or "")
        timing = str(raw.get("timing_status") or "")
        if order not in (1, 2, 3) or layer not in LAYERS:
            continue
        if evidence not in EVIDENCE_STATES:
            evidence = "unknown"
        if timing not in TIMING_STATES:
            timing = "unknown"
        refs = [_short(x, 240) for x in (raw.get("evidence_refs") or []) if _short(x, 240)][:8]
        chain.append({
            "order": order,
            "layer": layer,
            "factor": _short(raw.get("factor"), 300),
            "mechanism": _short(raw.get("mechanism"), 900),
            "evidence_status": evidence,
            "timing_status": timing,
            "counterfactual": _short(raw.get("counterfactual"), 600),
            "evidence_refs": refs,
        })

    hypotheses: list[dict[str, Any]] = []
    for raw in data.get("signal_hypotheses") or []:
        if not isinstance(raw, dict):
            continue
        key = _feature_key(raw.get("feature_key") or raw.get("feature"))
        if not key:
            continue
        hypotheses.append({
            "feature_key": key,
            "feature": _short(raw.get("feature"), 300),
            "measurement": _short(raw.get("measurement"), 700),
            "expected_direction": _short(raw.get("expected_direction"), 180),
            "falsifier": _short(raw.get("falsifier"), 500),
            "authority": "research_only",
            "direct_authority": False,
        })

    episode = packet.get("episode") or {}
    return {
        "schema": SCHEMA_AUTOPSY,
        "generated_at": _utc_now(),
        "episode_ref": episode.get("id"),
        "ticker": episode.get("ticker"),
        "entry_date": episode.get("entry_date"),
        "outcome": episode.get("outcome"),
        "summary": _short(data.get("summary"), 1_600),
        "mitigation_verdict": verdict,
        "causal_chain": chain[:18],
        "alternate_explanations": [
            _short(x, 500) for x in (data.get("alternate_explanations") or []) if _short(x, 500)
        ][:10],
        "missing_evidence": [
            _short(x, 500) for x in (data.get("missing_evidence") or []) if _short(x, 500)
        ][:12],
        "lesson": _short(data.get("lesson"), 800),
        "signal_hypotheses": hypotheses[:12],
        "authority": "research_only",
        "direct_authority": False,
    }


def invoke_autopsy(
    packet: dict[str, Any],
    model_caller: Callable[[str, str], Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Call the deliberation model (or an injected test caller), never raise."""
    system, user = autopsy_messages(packet)
    if model_caller is not None:
        try:
            result = model_caller(system, user)
            text = result[0] if isinstance(result, tuple) else result
            return parse_autopsy(str(text or ""), packet), "injected"
        except Exception as exc:  # noqa: BLE001
            log.warning("trade_memory: injected autopsy caller failed (%s)", type(exc).__name__)
            return None, "injected_error"

    try:
        from engine import llm_auth  # noqa: PLC0415
        active_model = llm_auth.deliberation_model(default=_OPUS_FALLBACK)
        conf = {
            "opus_model": active_model,
            "deepseek_model": "deepseek-reasoner",
            "max_tokens": 7000,
        }
        providers = llm_auth.build_providers(
            conf,
            opus_model=active_model,
            deepseek_model=conf["deepseek_model"],
        )
        if not providers:
            return None, "no_provider"

        def _call(client: Any, model: str) -> tuple:
            response = client.messages.create(
                model=model,
                max_tokens=conf["max_tokens"],
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            if getattr(response, "stop_reason", None) == "refusal":
                return None, "stop_refusal", response
            text = "".join(
                block.text for block in response.content
                if getattr(block, "type", "") == "text"
            )
            return text or None, None, response

        text, reason, provider = llm_auth.make_call(
            providers, _call, context="prophet_trade_memory"
        )
        if text is None and active_model != _OPUS_FALLBACK and reason not in {
            "no_provider", "rate_limited_all", "auth_invalid_all",
        }:
            fallback = llm_auth.build_providers(
                {**conf, "opus_model": _OPUS_FALLBACK},
                opus_model=_OPUS_FALLBACK,
                deepseek_model=conf["deepseek_model"],
            )
            if fallback:
                text, reason, provider = llm_auth.make_call(
                    fallback, _call, context="prophet_trade_memory_fallback"
                )
        return parse_autopsy(str(text or ""), packet), provider or reason
    except Exception as exc:  # noqa: BLE001
        log.warning("trade_memory: LLM autopsy failed (%s)", type(exc).__name__)
        return None, "llm_error"


def build_pattern_candidates(autopsies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Accrue repeated feature hypotheses without granting signal authority.

    A candidate only becomes ``ready_for_prereg`` with support from at least three
    winning episodes, at least one contradicting/losing episode, five total cases,
    and three distinct entry months.  This is a routing threshold, not an edge claim.
    """
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for autopsy in autopsies:
        if not isinstance(autopsy, dict):
            continue
        for hypothesis in autopsy.get("signal_hypotheses") or []:
            if not isinstance(hypothesis, dict):
                continue
            key = _feature_key(hypothesis.get("feature_key") or hypothesis.get("feature"))
            if key:
                groups[key].append({"autopsy": autopsy, "hypothesis": hypothesis})

    out: list[dict[str, Any]] = []
    for key, rows in sorted(groups.items()):
        episode_ids = {
            str(r["autopsy"].get("episode_ref") or "")
            for r in rows if r["autopsy"].get("episode_ref")
        }
        outcomes = [str(r["autopsy"].get("outcome") or "") for r in rows]
        support_n = sum(1 for x in outcomes if x == "win")
        contradict_n = sum(1 for x in outcomes if x in {"loss", "flat"})
        months = {
            str(r["autopsy"].get("entry_date") or "")[:7]
            for r in rows if str(r["autopsy"].get("entry_date") or "")[:7]
        }
        total_n = len(episode_ids) if episode_ids else len(rows)
        status = (
            "ready_for_prereg"
            if support_n >= 3 and contradict_n >= 1 and total_n >= 5 and len(months) >= 3
            else "accruing"
        )
        exemplar = rows[0]["hypothesis"]
        out.append({
            "schema": SCHEMA_PATTERN,
            "feature_key": key,
            "feature": _short(exemplar.get("feature"), 300),
            "measurement": _short(exemplar.get("measurement"), 700),
            "expected_direction": _short(exemplar.get("expected_direction"), 180),
            "falsifier": _short(exemplar.get("falsifier"), 500),
            "support_n": support_n,
            "contradict_n": contradict_n,
            "episode_n": total_n,
            "time_cluster_n": len(months),
            "episode_ids": sorted(episode_ids),
            "status": status,
            "next_lane": "research_factory_prereg" if status == "ready_for_prereg" else "accrue",
            "authority": "research_only",
            "direct_authority": False,
        })
    return out
