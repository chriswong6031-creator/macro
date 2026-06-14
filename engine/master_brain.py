"""Master brain — cross-asset macro SYNTHESIS (LLM Tier-B).

LEAF · GATED · DEFAULT-OFF · RESEARCH/CONTEXT-ONLY. Reads the DETERMINISTIC
outputs of every dashboard (macro / China / HK / commodity / forex / BTC-vector)
plus the catalyst_tone digest, and asks a reasoning LLM to synthesize the
cross-asset picture a single dashboard can't: the unified regime read, where the
signals CONFLICT and why, whether reality is tracking the liquidity-rotation
thesis, and the transmission chains to watch.

This is the analyst's morning note. It NEVER feeds a score, signal, or allocation;
nothing in the scoring path imports it. It READS the engine's outputs and writes a
SEPARATE artifact (data/regime/master_brief.json). Every public function returns
plain data or None and never raises into the pipeline.

Runs on DeepSeek V4 Pro via its Anthropic-compatible endpoint by default — one
config line (`llm_model` / `llm_base_url` / `api_key_env`) swaps it to Claude Opus.
NOTE: unlike the Tier-A digest (public docs only), the brain necessarily sends the
user's DERIVED market-state summary (regime labels, scores, conflicts — NOT
holdings or watchlist composition) to the provider. Swap to a first-party model in
config if that matters.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from lib import config
from engine.catalyst_tone import _extract_json   # shared tolerant JSON parser (leaf util)

log = logging.getLogger(__name__)

DEFAULT_THESIS = (
    "Liquidity rotates across risk assets in a rough sequence — US large-cap "
    "semis -> software/growth -> ex-US (China/HK) -> crypto — as net liquidity "
    "expands, and unwinds in reverse when it contracts. Treat this as a HYPOTHESIS "
    "to test against the data, not a fact."
)

DISCLAIMER_TEXT = (
    "Context only — not a signal. This is an AI-generated SYNTHESIS of the "
    "dashboards' own deterministic outputs. It does not feed any score, signal or "
    "allocation, and it can be wrong or overconfident. Use it as a research read; "
    "verify every claim against the underlying dashboard it cites. Effective sample "
    "sizes on macro regimes are small — treat cross-asset 'reads' as odds, not "
    "forecasts."
)

MASTER_SYSTEM_TMPL = (
    "You are a senior cross-asset macro strategist writing a SHORT morning brief for "
    "a solo top-down trader. You are given the trader's OWN deterministic dashboard "
    "outputs (already computed, validated signals) across macro regime, China, Hong "
    "Kong, commodities, FX, and Bitcoin, plus an optional FOMC catalyst digest. Your "
    "job is SYNTHESIS across them — not to recompute or invent numbers.\n\n"
    "Rules:\n"
    "- Use ONLY the provided state. Never fabricate a level, score, or signal. If "
    "something isn't in the state, say it's not available.\n"
    "- Your value is the CROSS-ASSET view: the unified regime read, where signals "
    "CONFLICT (e.g. risk-on FX vs a cautious macro-risk gauge) and what that implies, "
    "and second-order transmission chains worth watching.\n"
    "- Evaluate the trader's working rotation thesis against the actual state; say "
    "explicitly where reality tracks it and where it diverges.\n"
    "- Do NOT give position sizes or fire trades — the deterministic system does "
    "that. Give the read and what to watch.\n"
    "- Be honest about uncertainty and small samples. Flag conflicts rather than "
    "papering over them. Cite which dashboard supports each claim.\n\n"
    "Working rotation thesis to test:\n{thesis}\n\n"
    "Return ONLY a JSON object (no markdown fences) with keys:\n"
    "  summary: string — one-line TL;DR of the cross-asset read.\n"
    "  regime_read: string — 1-2 short paragraphs: where we are across assets.\n"
    "  conflicts: array of strings — each a specific cross-asset signal conflict + "
    "what it implies.\n"
    "  rotation_check: string — is reality tracking the rotation thesis? where it "
    "diverges.\n"
    "  transmission: array of strings — key second-order chains to watch (e.g. "
    "'oil up -> inflation print -> Fed path -> crypto liquidity').\n"
    "  watch_items: array of strings — what would change this read / what to watch next.\n"
    "  confidence: one of \"low\",\"medium\",\"high\"."
)

_BRIEF_FIELDS = ("summary", "regime_read", "conflicts", "rotation_check",
                 "transmission", "watch_items", "confidence")


def _cfg() -> dict:
    return config.load().get("master_brain", {}) or {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", False))


# --------------------------------------------------------------------------- #
# state gathering — compact summaries of each dashboard's deterministic output
# --------------------------------------------------------------------------- #
def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001
        return None


def _leg(x):
    """Compact a conditions leg dict down to its headline fields."""
    if isinstance(x, dict):
        slim = {k: x.get(k) for k in ("label", "state", "value", "score", "pctile") if k in x}
        return slim or x
    return x


def _macro_summary(m: dict) -> dict:
    cond = m.get("conditions") or {}
    dis = m.get("dislocation") or {}
    mr = m.get("macro_risk") or {}
    pb = m.get("playbook") or {}
    dial = pb.get("dial")
    return {
        "date": m.get("date"), "quad": m.get("quad"), "quad_name": m.get("quad_name"),
        "label": m.get("label"),
        "growth_score": m.get("growth_score"), "inflation_score": m.get("inflation_score"),
        "confidence": m.get("confidence"),
        "liquidity_overlay": m.get("liquidity_overlay"), "cycle_tag": m.get("cycle_tag"),
        "transition_state": m.get("transition_state"),
        "macro_risk": {"score": mr.get("score"), "label": mr.get("label")},
        "conditions": {k: _leg(v) for k, v in cond.items()} if isinstance(cond, dict) else None,
        "dislocation": {"verdict": dis.get("verdict"), "put_state": dis.get("put_state"),
                        "headline": dis.get("headline"),
                        "catalyst_narrative": dis.get("catalyst_narrative")},
        "playbook": {"posture": pb.get("posture"),
                     "dial_score": dial.get("score") if isinstance(dial, dict) else dial},
    }


def _btc_summary(root: Path) -> dict | None:
    out: dict = {}
    fs = _read_json(root / "data/vector/flash_state.json")
    if fs:
        out["alert_state"] = fs.get("state")
        out["price"] = fs.get("price")
    try:
        import math

        import pandas as pd
        df = pd.read_parquet(root / "data/vector/signals.parquet")
        if len(df):
            last = df.iloc[-1]
            for c in ("composite_state", "risk_regime", "momentum", "mvrv_z",
                      "funding_z", "net_liquidity_bn", "macro_regime"):
                if c in df.columns:
                    v = last[c]
                    try:
                        fv = float(v)
                        out[c] = None if math.isnan(fv) else round(fv, 3)
                    except (TypeError, ValueError):
                        out[c] = v if isinstance(v, str) else None
    except Exception:  # noqa: BLE001
        pass
    return out or None


def gather_state(root: Path | None = None) -> dict:
    """Compact cross-asset state assembled from each dashboard's latest.json.
    Excludes holdings / watchlist composition by design."""
    root = Path(root) if root else config.ROOT
    macro = _read_json(root / "data/regime/latest.json") or {}
    state: dict = {"macro": _macro_summary(macro)}
    ch = _read_json(root / "data/china_regime/latest.json")
    if ch:
        state["china"] = {k: ch.get(k) for k in (
            "date", "quad", "quad_name", "growth_score", "inflation_score",
            "liquidity_overlay", "cycle_tag", "pending_quad")}
    hk = _read_json(root / "data/hk_regime/latest.json")
    if hk:
        state["hk"] = {k: hk.get(k) for k in (
            "date", "quad", "quad_name", "global_score", "risk_state",
            "peg_state", "peg_distance", "liquidity_overlay")}
    co = _read_json(root / "data/commodity/latest.json")
    if co:
        state["commodity"] = {k: co.get(k) for k in ("date", "regime", "favored")}
    fx = _read_json(root / "data/forex/latest.json")
    if fx:
        state["forex"] = {k: fx.get(k) for k in ("date", "regime", "favored", "risk")}
    btc = _btc_summary(root)
    if btc:
        state["btc"] = btc
    if macro.get("catalyst_tone"):
        state["catalyst_tone"] = macro.get("catalyst_tone")
    return state


# --------------------------------------------------------------------------- #
# the model call (DeepSeek V4 Pro via the Anthropic-compatible endpoint)
# --------------------------------------------------------------------------- #
def _client(cfg: dict):
    try:
        import anthropic
    except ImportError:
        return None
    key = config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY"))
    if not key:
        return None
    try:
        return anthropic.Anthropic(
            base_url=cfg.get("llm_base_url", "https://api.deepseek.com/anthropic"),
            api_key=key)
    except Exception:  # noqa: BLE001
        return None


def _call_model(system: str, user: str, cfg: dict) -> tuple[str | None, str | None]:
    """Return (reply_text, degraded_reason). Never raises."""
    client = _client(cfg)
    if client is None:
        return None, "no_client_or_key"
    try:
        resp = client.messages.create(
            model=cfg.get("llm_model", "deepseek-v4-pro"),
            max_tokens=int(cfg.get("max_tokens", 4000)),
            system=system,
            messages=[{"role": "user", "content": user}])
        sr = getattr(resp, "stop_reason", None)
        if sr == "refusal":
            return None, "stop_refusal"
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        if not text:
            return None, "empty_reply"
        return text, ("truncated" if sr == "max_tokens" else None)
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("master_brain model call failed (%s)", e)
        return None, "llm_error"


# --------------------------------------------------------------------------- #
# public: synthesize one brief
# --------------------------------------------------------------------------- #
def synthesize(state: dict, cfg: dict | None = None) -> dict:
    """Run the LLM synthesis over a gathered state. Always returns a brief record
    (degraded fields flagged); never raises."""
    cfg = cfg or _cfg()
    macro = state.get("macro") or {}
    brief = {
        "schema": "master_brief.v1", "is_context_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": cfg.get("llm_model", "deepseek-v4-pro"),
        "state_asof": macro.get("date"),
        "summary": None, "regime_read": None, "conflicts": [], "rotation_check": None,
        "transmission": [], "watch_items": [], "confidence": "low",
        "raw_text": None, "degraded_reason": None, "disclaimer": DISCLAIMER_TEXT,
    }
    system = MASTER_SYSTEM_TMPL.format(thesis=cfg.get("rotation_thesis", DEFAULT_THESIS))
    user = ("Today's deterministic cross-asset state (JSON). Synthesize per your "
            "instructions.\n<state>\n"
            + json.dumps(state, indent=2, default=str) + "\n</state>")
    reply, reason = _call_model(system, user, cfg)
    brief["raw_text"] = reply
    if reply is None:
        brief["degraded_reason"] = reason
        return brief
    parsed = _extract_json(reply)
    if not isinstance(parsed, dict):
        brief["degraded_reason"] = reason or "unparseable_reply"   # surfaces "truncated"
        return brief
    for k in _BRIEF_FIELDS:
        if k in parsed:
            brief[k] = parsed[k]
    if reason:
        brief["degraded_reason"] = reason          # parsed, but flag e.g. truncation
    return brief


def render_markdown(brief: dict) -> str:
    """Human-readable rendering of a brief (for the CLI / a future panel)."""
    if not brief:
        return "_no brief_"
    if brief.get("degraded_reason") and not brief.get("regime_read"):
        return f"_master brief unavailable: {brief['degraded_reason']}_"
    L = [f"# Master brief — {brief.get('state_asof','?')} ({brief.get('model','?')})", ""]
    if brief.get("summary"):
        L += [f"**{brief['summary']}**", ""]
    if brief.get("regime_read"):
        L += ["## Regime read", brief["regime_read"], ""]
    if brief.get("conflicts"):
        L += ["## Conflicts", *[f"- {c}" for c in brief["conflicts"]], ""]
    if brief.get("rotation_check"):
        L += ["## Rotation thesis", brief["rotation_check"], ""]
    if brief.get("transmission"):
        L += ["## Transmission chains to watch", *[f"- {c}" for c in brief["transmission"]], ""]
    if brief.get("watch_items"):
        L += ["## Watch next", *[f"- {c}" for c in brief["watch_items"]], ""]
    L += [f"_confidence: {brief.get('confidence','?')} · context only, not a signal_"]
    return "\n".join(L)


_ZH_SCALARS = ("summary", "regime_read", "rotation_check")
_ZH_LISTS = ("conflicts", "transmission", "watch_items")


def _translate_brief(brief: dict, cfg: dict) -> None:
    """Attach a Chinese version (brief['zh']) via the shared DeepSeek translator
    (engine/translate.translate_to_zh) so the dashboard's 中文 toggle shows the brief
    in Chinese. The brief is unique daily, so it's translated fresh each run — a cheap
    V4-Flash pass. Degrade-never-raise: on any failure brief['zh'] is omitted and the
    panel falls back to English (per field)."""
    if not cfg.get("translate_zh", True):
        return
    if brief.get("degraded_reason") and not brief.get("regime_read"):
        return                                       # nothing usable to translate
    try:
        from engine import translate as _tr
        texts: list[str] = []
        layout: list[tuple[str, int | None]] = []
        for k in _ZH_SCALARS:
            v = brief.get(k)
            if isinstance(v, str) and v.strip():
                layout.append((k, None)); texts.append(v)
        for k in _ZH_LISTS:
            for i, v in enumerate(brief.get(k) or []):
                if isinstance(v, str) and v.strip():
                    layout.append((k, i)); texts.append(v)
        if not texts:
            return
        tcfg = {                                     # force-on Flash translate (independent of profile_translation)
            "enabled": True,
            "base_url": cfg.get("llm_base_url", "https://api.deepseek.com/anthropic"),
            "api_key_env": cfg.get("api_key_env", "DEEPSEEK_API_KEY"),
            "model": cfg.get("translate_model", "deepseek-v4-flash"),
            "max_chars": 2000, "max_tokens": 4000, "batch_size": 24,
        }
        zh_list = _tr.translate_to_zh(texts, tcfg)
        if not zh_list or all(x is None for x in zh_list):
            return
        zh: dict = {"summary": None, "regime_read": None, "rotation_check": None,
                    "conflicts": [None] * len(brief.get("conflicts") or []),
                    "transmission": [None] * len(brief.get("transmission") or []),
                    "watch_items": [None] * len(brief.get("watch_items") or [])}
        for (k, i), t in zip(layout, zh_list):
            if t is None:
                continue
            if i is None:
                zh[k] = t
            else:
                zh[k][i] = t
        brief["zh"] = zh
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("master_brief zh translation failed (%s)", e)


def run(persist: bool = True, root: Path | None = None, force: bool = False) -> dict | None:
    """Gather state -> synthesize -> persist data/regime/master_brief.json.
    Returns the brief, or None when disabled (unless `force`, for on-demand/CLI use).
    NEVER raises into the pipeline."""
    cfg = _cfg()
    if not force and not cfg.get("enabled", False):
        return None
    try:
        root = Path(root) if root else config.ROOT
        state = gather_state(root)
        brief = synthesize(state, cfg)
        _translate_brief(brief, cfg)          # attach brief['zh'] for the 中文 toggle
        if persist:
            try:
                payload = json.dumps(brief, indent=2, default=str)
                out = root / "data" / "regime" / "master_brief.json"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(payload)
                site = root / "site"          # client-fetched by the dashboard panel
                if site.is_dir():
                    (site / "master_brief.json").write_text(payload)
            except Exception as e:  # noqa: BLE001
                log.warning("master_brief persist failed (%s)", e)
        return brief
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("master_brain run failed (%s)", e)
        return None


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    logging.basicConfig(level=logging.INFO)
    force = "--force" in sys.argv            # ad-hoc run even when master_brain.enabled is false
    b = run(persist=True, force=force)
    if b is None:
        print("master_brain disabled — set master_brain.enabled: true, or pass --force")
    else:
        print(render_markdown(b))
        if b.get("degraded_reason"):
            print(f"\n[degraded: {b['degraded_reason']}]")
