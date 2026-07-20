"""Master brain — cross-asset macro SYNTHESIS (LLM Tier-B).

LEAF · GATED · DEFAULT-OFF · RESEARCH/CONTEXT-ONLY. Reads the DETERMINISTIC
outputs of the dashboards and asks a reasoning LLM to synthesize the picture a
single panel can't. Three LENSES share one engine:
  • macro — the cross-asset read across every dashboard (macro/China/HK/commodity/
    forex/BTC) + the catalyst digest  → data/regime/master_brief.json
  • china — a China & Hong-Kong focused read (US macro / dollar / global liquidity /
    commodities as backdrop)          → data/regime/china_brief.json
  • btc   — a Bitcoin focused read (cycle / valuation / leverage / on-chain / ETF
    flows / macro-liquidity backdrop)  → data/regime/btc_brief.json
Each writes a SEPARATE artifact and a site/ copy the dashboard panel fetches.

This is the analyst's morning note. It NEVER feeds a score, signal, or allocation;
nothing in the scoring path imports it. It READS the engine's outputs and writes a
SEPARATE artifact. Every public function returns plain data or None and never
raises into the pipeline.

Runs on DeepSeek V4 Pro via its Anthropic-compatible endpoint by default — one
config line (`llm_model` / `llm_base_url` / `api_key_env`) swaps it to Claude Opus.
NOTE: unlike the Tier-A digest (public docs only), the brain necessarily sends the
user's DERIVED market-state summary (regime labels, scores, conflicts — NOT
holdings or watchlist composition) to the provider. Swap to a first-party model in
config if that matters.
"""
from __future__ import annotations

import hashlib
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

CHINA_THESIS = (
    "China equity risk appetite is driven mainly by DOMESTIC policy & liquidity "
    "(PBoC stance, credit impulse, fiscal) rather than earnings, and A-shares "
    "MEAN-REVERT over short horizons — short-term reversal is the robust effect "
    "while momentum is unreliable, so treat 'relative-strength leaders' as EXTENDED "
    "rather than as continuation. Hong Kong additionally rides global risk appetite "
    "and the US dollar far more than mainland A-shares. Treat this as a HYPOTHESIS "
    "to test against the data, not a fact."
)

BTC_THESIS = (
    "Bitcoin is the long-duration, high-beta tail of the GLOBAL LIQUIDITY cycle — "
    "it leads risk assets higher when net liquidity / global M2 expand and unwinds "
    "hardest when they contract; within that, leverage & funding extremes and "
    "valuation / cycle position (MVRV, halving clock) gate the risk-reward. Treat "
    "this as a HYPOTHESIS to test against the data, not a fact."
)

DISCLAIMER_TEXT = (
    "Context only — not a signal. This is an AI-generated SYNTHESIS of the "
    "dashboards' own deterministic outputs. It does not feed any score, signal or "
    "allocation, and it can be wrong or overconfident. Use it as a research read; "
    "verify every claim against the underlying dashboard it cites. Effective sample "
    "sizes on macro regimes are small — treat cross-asset 'reads' as odds, not "
    "forecasts."
)

# ── ABX v2 shared prompt blocks ──────────────────────────────────────────────
# The brief is a Tier-1 surface (docs/DESIGN_DOCTRINE.md), so the prompt IS a
# copywriting contract: the model reads machine state but may only ever emit
# plain language. engine-side style lint (_style_violations) enforces the bans.

_VOICE_LAW = (
    "VOICE — HARD RULES (any violation makes the reply invalid):\n"
    "- Write for a smart reader with NO finance training. Short sentences, plain "
    "words. Every line must pass the test: would a taxi driver get it on first read?\n"
    "- The state JSON is for YOUR eyes only. NEVER let its vocabulary leak into the "
    "output: no snake_case tokens (growth_score, mom_20d, cross_asset_confirm, "
    "neural_web, cphase_days_left), no 'panel:'/'panels:' citations, no block or "
    "schema names, no quadrant codes — write 'Goldilocks', never 'Q1 Goldilocks'.\n"
    "- NEVER write σ, z-scores, percentiles, basis points, or 'n='. Translate "
    "magnitude into meaning: not 'semis RS -2.5σ' but 'chip stocks have lagged the "
    "market by the widest margin in about a year'; not 'MVRV-Z 20th percentile' but "
    "'cheap by the on-chain yardstick — near the bottom of its historical range'.\n"
    "- Numbers: at most one per sentence, and only ones a person would say out loud "
    "— a price, a percent change, a count of days or flags, a date. Every number "
    "carries its meaning in the same sentence, or gets dropped for the meaning alone.\n"
    "- Acronyms: only front-page ones (Fed, ETF, GDP, CPI). Everything else in plain "
    "words, optionally with the code in parentheses once: 'China's 7-day interbank "
    "rate (FR007)', 'the reserve-requirement cut that frees banks to lend (RRR)', "
    "'leveraged bets outstanding (open interest)'.\n"
    "- Point at evidence by its desk in plain words — 'the bond desk', 'the China "
    "liquidity read', 'the ETF-flow tracker' — never by an internal key.\n"
)

_REGIME_MAP_LAW = (
    "REGIME = POSITION, NOT A BOX: a regime label is a position on a map, and the "
    "state tells you where inside the regime we sit and which border we are drifting "
    "toward (regime_path, transition/pending fields, score drifts, cycle clocks). "
    "Never present the label as a settled fact. Say both things: 'still Goldilocks "
    "on the map, but growth has cooled to the edge — one more soft month tips it "
    "into Reflation.' When the state says the regime is transitioning or a flip is "
    "pending, that drift IS the story — lead with it.\n"
)

_STANCE_LAW = (
    "STANCE: the LAST tldr item starts exactly 'What to do:' and uses ONLY this "
    "vocabulary: Act · Get ready · Watch — don't chase · Protect gains · Stand aside "
    "· Ignore. It RESTATES the deterministic system's own posture from the state "
    "(the playbook posture, the allocation, the risk label) in plain words — you may "
    "soften it, you may never go further than the system does. 'Watch — don't "
    "chase' is a complete, honest answer.\n"
)

_THESIS_RULE = (
    "THE STANDING PLAYBOOK: a working hypothesis is on file below. The reader knows "
    "it by heart — NEVER restate its wording, and never mention it in tldr, "
    "regime_read, conflicts or transmission. Fill `rotation_check` ONLY when today's "
    "evidence meaningfully moved for or against it (a leg confirmed, a leg broken, "
    "the sequence running backwards); on an ordinary day OMIT the field entirely. "
    "When you do write it: ≤40 words, plain words, name what moved.\n"
)

# Shared output contract + tail every lens reuses, so the three system prompts and
# the renderers stay identical bar the domain framing.
_SCHEMA_TAIL = (
    "Return ONLY a JSON object (no markdown fences) with keys:\n"
    "  tldr: array of 3-5 strings — the glance read, most important first. Each "
    "item 'Head: rest' (Head ≤3 words, rest ≤14 words). The LAST item is the "
    "stance line ('What to do: ...' per the STANCE rule).\n"
    "  summary: string — ONE sentence, ≤22 words, plain words.\n"
    "  regime_read: string — ≤2 short paragraphs: where we are on the map, which "
    "way we're drifting, and what today's dominant driver is.\n"
    "  conflicts: array of 1-3 strings — each 'Head: A says X, B says Y — what "
    "that implies', ≤30 words.\n"
    "  transmission: array of 0-2 strings — each a chain reaction in the exact "
    "shape 'If <what is happening> keeps up → <what follows next>', ≤24 words.\n"
    "  rotation_check: OPTIONAL string — see the STANDING PLAYBOOK rule; omit on "
    "an ordinary day.\n"
    "  watch_items: array of 2-4 strings — each 'Trigger: what it means', ≤16 "
    "words.\n"
    "  confidence: one of \"low\",\"medium\",\"high\"."
)

# Forward-watch tail — ONLY appended to the macro lens when forward_calendar is in state.
# (ADB-W2) Generates forward_watch rows + optional forward_read narrative.
_FORWARD_TAIL = (
    "\n\nIf `forward_calendar` is present in the state, also emit these two OPTIONAL keys "
    "(omit both if forward_calendar is absent or all sub-blocks are absent):\n"
    "  forward_watch: array of objects, one per notable upcoming event or release, with keys:\n"
    "    date: the date string VERBATIM from forward_calendar (e.g. \"2026-07-14\").\n"
    "    label: the event label VERBATIM from forward_calendar (e.g. \"CPI\", \"FOMC\").\n"
    "    kind: the kind/type string VERBATIM from forward_calendar.\n"
    "    note: <=20 words of plain-word framing — context for the trader, NO new numbers.\n"
    "  forward_read: optional string, <=3 sentences of narrative context for the forward "
    "picture. HARD RULES that are ABSOLUTE — violating any makes the field INVALID:\n"
    "  (a) Every digit-sequence in forward_watch rows and in forward_read MUST exist "
    "VERBATIM in the forward_calendar state block — no arithmetic, no rounding, no derived "
    "composites.\n"
    "  (b) Each forward_watch row cites exactly ONE source artifact (one event, one release, "
    "or one hazard — never combine two source numbers in one row).\n"
    "  (c) Model-emitted confidence fields (confidence_v2 etc.) are QUOTED from the state — "
    "never originated by you.\n"
    "  (d) If a sub-block has absent:true, say it is not available or omit the row — never "
    "synthesise as if data were present.\n"
    "  (e) Claims has model_status='benchmark_only' — only quote its benchmark values, "
    "never a projection band.\n"
    "  (f) Hazard numbers include their horizon exactly as given (e.g. '1m').\n"
    "  (g) Never add policy-timing or policy-intent predictions (these are conditions-framed "
    "calendar entries, never 'will fire' claims)."
)

# Producer tail — ONLY appended to the macro lens. Lets the brain stake its OWN falsifiable
# cross-asset leans (graded by master_brain_scorer), turning it from a read-only loop into a
# full closed loop. Subjects are restricted to instruments that are actually in the price
# cache (UUP/EEM/GLD are NOT cached → US dollar / EM / Gold are intentionally omitted).
_MACRO_THESES_TAIL = (
    "\n\nOPTIONALLY add a `theses` array — but usually EMPTY. Stake a lean ONLY on a "
    "genuine multi-dashboard cross-asset divergence you have real conviction in; a lean is a "
    "DIRECTION, never a size, and it is graded against realized prices, so OMIT rather than "
    "pad. Each thesis object:\n"
    "    subject: one of \"US equities\",\"Long Treasuries\",\"Investment-grade credit\","
    "\"High-yield credit\",\"Small caps\",\"Growth over value\",\"Semiconductors\","
    "\"China equities\",\"Bitcoin\",\"VIX\".\n"
    "    lean: one of \"overweight\",\"underweight\",\"avoid\",\"fade-fear\" (fade-fear is VIX-only).\n"
    "    conviction: \"low\"|\"medium\"|\"high\" — default low; reserve high for genuine agreement.\n"
    "    horizon_d: integer trading days, 5..60.\n"
    "    thesis: one sentence naming the divergence.\n"
    "    falsifier_text: one concrete condition that would prove the lean wrong."
)

MASTER_SYSTEM_TMPL = (
    "You are a senior cross-asset strategist writing a SHORT plain-language brief for "
    "the owner of this dashboard system. You are given the system's OWN deterministic "
    "outputs (already computed, validated) across the US macro regime, China, Hong "
    "Kong, commodities, FX, bonds/credit, and Bitcoin, plus optional policy digests "
    "and a Neural-Web context packet. Your job is SYNTHESIS — the one picture the "
    "individual panels can't see alone — never recomputing or inventing numbers.\n\n"
    "EVIDENCE RULES:\n"
    "- Use ONLY the provided state. Never fabricate a level, score, or signal; if "
    "something is missing or marked stale/absent, say so in one plain line.\n"
    "- Same-tape rule: blocks sharing a `_tape_family` are ONE observation of the "
    "same underlying series, not independent confirmation. Independence only exists "
    "across families (prices vs rates/credit vs policy text). A conflict between "
    "same-family blocks is a decomposition, not a cross-asset disagreement.\n"
    "- Open with the dominant driver when the state names one; when it reads mixed "
    "or quiet, say that plainly rather than inventing a driver.\n"
    "- Weigh desk track records when present: a cold desk (tiny sample) or a "
    "sub-50% desk is weak evidence — don't build a conflict on it alone.\n"
    "- Do NOT give position sizes or fire trades — the deterministic system does "
    "that. Give the read and what would change it.\n"
    "- Macro regimes have few historical cases: frame reads as odds, not forecasts.\n\n"
    "BLOCK GUIDE (how to use, never how to cite):\n"
    "- Bonds + the cross-asset check: say plainly whether bonds and credit AGREE "
    "with the stock market's read or are worried. Credit and the curve lead only "
    "loosely and noisily; everything else moves with prices — never claim bonds "
    "'predict' stocks; a divergence is an attention flag, not a forecast.\n"
    "- Rate/inflation transmission + yield curve: backdrop and risk framing only "
    "(which assets feel pressure) — never a return forecast or a timing signal.\n"
    "- Fed stance / policy intel: the Fed's stated stance and the market-vs-Fed "
    "gap; honor FACT vs INFERENCE vs PRIOR labels — never present a PRIOR as fact.\n"
    "- Entry-quality breadth (present only when it disagrees with the regime): a "
    "temper-your-conviction check about how BROAD participation is — never a "
    "buy/sell read, never a regime flip on its own.\n"
    "- neural_web: calibration and cross-check; its synthesis blocks re-read the "
    "same US tape, not new evidence. A degraded overnight review means it is "
    "absent — one honest line at most.\n\n"
    + _VOICE_LAW + "\n" + _REGIME_MAP_LAW + "\n" + _STANCE_LAW + "\n" + _THESIS_RULE
    + "\nWorking playbook on file (do not restate):\n{thesis}\n\n"
    + _SCHEMA_TAIL + _MACRO_THESES_TAIL + _FORWARD_TAIL
)

CHINA_SYSTEM_TMPL = (
    "You are a senior China & Hong-Kong strategist writing a SHORT plain-language "
    "brief for the owner of this dashboard system. You are given the system's OWN "
    "deterministic outputs: the China A-share regime (growth/inflation position, "
    "central-bank liquidity overlay, cycle tag, sector strength, key ratios incl. "
    "USD/CNY), the Hong-Kong regime (global-risk score, currency-peg state, sector "
    "strength), China policy/news intelligence, and a compact US / dollar / "
    "commodity backdrop. Your job is SYNTHESIS — never recomputing or inventing "
    "numbers.\n\n"
    "EVIDENCE RULES:\n"
    "- Use ONLY the provided state; anything missing or stale gets one honest "
    "plain line, never a paper-over.\n"
    "- Centre the read on China and Hong Kong; the US / dollar / commodity "
    "backdrop exists only to explain what is pushing on them.\n"
    "- Mainland A-shares tend to snap BACK over short horizons: frame this week's "
    "leaders as stretched rather than as proof of continuation, and deep pullbacks "
    "in good groups as the higher-odds setups. Say where Hong Kong is split from "
    "the mainland — global risk appetite and the dollar push HK around far more.\n"
    "- Policy easing and system liquidity can point in opposite directions — when "
    "they do, that tension is usually the story: has the easing actually reached "
    "the system, or is it still stuck in the pipes?\n"
    "- Do NOT give position sizes or fire trades — the deterministic system does "
    "that. Be honest about uncertainty and small samples.\n"
    "- neural_web blocks: calibration and cross-check only; a degraded overnight "
    "review means it is absent — one honest line at most.\n\n"
    + _VOICE_LAW + "\n" + _REGIME_MAP_LAW + "\n" + _STANCE_LAW + "\n" + _THESIS_RULE
    + "\nWorking playbook on file (do not restate):\n{thesis}\n\n"
    + _SCHEMA_TAIL
)

BTC_SYSTEM_TMPL = (
    "You are a senior crypto & macro strategist writing a SHORT plain-language "
    "brief on BITCOIN for the owner of this dashboard system. You are given the "
    "system's OWN deterministic Bitcoin outputs — the composite risk regime and "
    "its allocation, momentum and structure, the halving-cycle clock, on-chain "
    "valuation, leverage and positioning, options, spot-ETF flows, miner/on-chain "
    "demand — plus the global-liquidity and US-macro backdrop and a Neural-Web "
    "context packet. Your job is SYNTHESIS across these layers — never recomputing "
    "or inventing numbers.\n\n"
    "EVIDENCE RULES:\n"
    "- Use ONLY the provided state; anything missing or stale gets one honest "
    "plain line, never a paper-over.\n"
    "- Tie the cycle position and valuation to the liquidity backdrop and to "
    "leverage/flows. When they disagree — cheap valuation inside a still-falling "
    "structure, strong ETF inflows against crowded leverage — that disagreement IS "
    "the story.\n"
    "- The system's allocation is the system's call: narrate it (including any "
    "override, honestly) — never argue the reader into overriding it, and never "
    "set sizes yourself.\n"
    "- This brief refreshes every few days, so write it to KEEP: the standing "
    "picture plus the concrete triggers that would change it, rather than "
    "day-count minutiae that ages overnight.\n"
    "- Few crypto cycles exist — frame history-based claims as odds, not laws.\n"
    "- neural_web blocks: calibration and cross-check only; a degraded overnight "
    "review means it is absent — one honest line at most.\n\n"
    + _VOICE_LAW + "\n" + _REGIME_MAP_LAW + "\n" + _STANCE_LAW + "\n" + _THESIS_RULE
    + "\nWorking playbook on file (do not restate):\n{thesis}\n\n"
    + _SCHEMA_TAIL
)

_BRIEF_FIELDS = ("tldr", "summary", "regime_read", "conflicts", "rotation_check",
                 "transmission", "watch_items", "confidence")


def _cfg() -> dict:
    return config.load().get("master_brain", {}) or {}


# --------------------------------------------------------------------------- #
# the macro PRODUCER — the brain's own falsifiable cross-asset leans. Mirrors the proven
# engine.ai_desk producer (resolve subject → engine-derived machine-checkable falsifier →
# validated thesis → append-only ledger), graded by engine.master_brain_scorer. ADDITIVE,
# macro-lens only, degrade-never-raise. ai_desk imports master_brain at module top, so every
# ai_desk reference here MUST be lazy (inside a function) to avoid an import cycle.
# --------------------------------------------------------------------------- #
_THESIS_LEANS = ("overweight", "underweight", "avoid", "fade-fear")
_CONVICTIONS = ("low", "medium", "high")
_BENCH = "SPY"
_VIX = "_VIX"
# subject (lowercased) -> (ticker, benchmark). ONLY tickers verified present in data/yahoo/.
# UUP/EEM/GLD are NOT cached, so US dollar / Emerging markets / Gold are omitted until a
# collector backfill; the cache-gate in _mb_derive_check is the safety net for map drift.
_XASSET_ETF = {
    "us equities": ("SPY", None),
    "long treasuries": ("TLT", "SPY"),
    "investment-grade credit": ("LQD", "SPY"),
    "high-yield credit": ("HYG", "SPY"),
    "small caps": ("IWM", "SPY"),
    "growth over value": ("IWF", "IWD"),
    "semiconductors": ("SMH", "SPY"),
    "china equities": ("FXI", "SPY"),
    "bitcoin": ("BTC-USD", "SPY"),   # NB: BTC trades 7d but check_by uses BusinessDay (context-only)
}


def _mb_cached(ticker, root) -> bool:
    try:
        from engine.ai_desk import _close_series        # lazy — avoid the ai_desk import cycle
        s = _close_series(ticker, root)
        return s is not None and not s.empty
    except Exception:  # noqa: BLE001
        return False


def _mb_resolve(subject: str):
    s = (subject or "").strip().lower()
    if s in _XASSET_ETF:
        t, vs = _XASSET_ETF[s]
        return t, vs, "rel_return"
    if s in ("vix", "fear", "fade-fear"):
        return _VIX, None, "level"
    return None, None, "soft"


def _mb_derive_check(subject: str, lean: str, horizon: int, root) -> dict:
    ticker, vs, kind = _mb_resolve(subject)
    if kind == "rel_return":
        # cache-presence gate: an uncached ticker would silently EXPIRE after the grace
        # window (never 'soft'), so downgrade to soft → logged-unscored, honest.
        if root is not None and not _mb_cached(ticker, root):
            return {"kind": "soft", "reason": f"{ticker} not in price cache"}
        thr = 0.05
        if lean == "overweight":
            op, threshold = "<", -thr
        elif lean in ("underweight", "avoid"):
            op, threshold = ">", thr
        else:
            return {"kind": "soft", "reason": f"lean '{lean}' has no relative-return rule"}
        return {"kind": "rel_return", "subject_ticker": ticker, "vs": vs,
                "op": op, "threshold": threshold, "horizon_d": horizon}
    if kind == "level":
        if lean == "fade-fear":
            return {"kind": "level", "subject_ticker": ticker, "vs": None, "op": ">",
                    "ref": "entry", "horizon_d": horizon,
                    "note": "FALSE if VIX makes a new high above the entry level within horizon"}
        return {"kind": "soft", "reason": f"lean '{lean}' has no level rule"}
    return {"kind": "soft", "reason": "subject not resolvable to a closeable instrument"}


def _mb_check_by(asof, horizon: int):
    try:
        import pandas as pd                               # lazy — master_brain stays pandas-free at import
        return (pd.Timestamp(asof) + pd.offsets.BusinessDay(int(horizon))).date().isoformat()
    except Exception:  # noqa: BLE001
        return None


def _mb_build_thesis(t: dict, i: int, asof, root, cfg: dict) -> dict | None:
    """Validate one model-authored cross-asset lean + attach the engine-derived falsifier.
    Returns None for malformed / non-directional entries (every kept lean is scorable)."""
    if not isinstance(t, dict):
        return None
    subject = str(t.get("subject") or "").strip()
    lean = str(t.get("lean") or "").strip().lower()
    if not subject or lean not in _THESIS_LEANS:
        return None
    try:
        horizon = int(t.get("horizon_d") or 20)
    except Exception:  # noqa: BLE001
        horizon = 20
    horizon = max(5, min(60, horizon))
    conv = str(t.get("conviction") or "low").strip().lower()
    if conv not in _CONVICTIONS:
        conv = "low"
    return {
        "id": f"mb-{asof}-{i + 1}",
        "subject": subject, "lean": lean, "conviction": conv, "horizon_d": horizon,
        "thesis": t.get("thesis"),
        "falsifier": {"text": t.get("falsifier_text"),
                      "check": _mb_derive_check(subject, lean, horizon, root)},
        "check_by": _mb_check_by(asof, horizon),
    }


def _mb_entry_levels(check: dict, asof, root) -> dict:
    out = {}
    try:
        from engine.ai_desk import _level_asof           # lazy — avoid the import cycle
        for key in ("subject_ticker", "vs"):
            tk = check.get(key)
            if tk:
                lv = _level_asof(tk, root, asof)
                if lv is not None:
                    out[tk] = lv
    except Exception:  # noqa: BLE001
        pass
    return out


def _append_ledger(brief: dict, root) -> None:
    """Append the macro brief's theses to data/master_brain/theses.jsonl. Never fatal."""
    theses = brief.get("theses") or []
    if not theses:
        return
    try:
        from engine.regime_label import quad_label
        d = Path(root) / "data" / "master_brain"
        d.mkdir(parents=True, exist_ok=True)
        asof = brief.get("state_asof")
        regime = quad_label(root)
        with open(d / "theses.jsonl", "a") as fh:
            for t in theses:
                check = (t.get("falsifier") or {}).get("check") or {}
                row = {
                    "id": t["id"], "logged_at": brief["generated_at"], "state_asof": asof,
                    "subject": t["subject"], "lean": t["lean"], "conviction": t["conviction"],
                    "horizon_d": t["horizon_d"], "falsifier": t["falsifier"],
                    "check_by": t["check_by"], "entry_levels": _mb_entry_levels(check, asof, root),
                    "regime": regime, "status": "open", "scored_at": None,
                    "outcome": None, "realized": None,
                }
                fh.write(json.dumps(row, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        log.warning("master_brain: ledger append failed: %s", e)


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


def _brief_age_days(prev: dict | None) -> float | None:
    """Age in days of a previously-generated brief, from its `generated_at`. Returns
    None when missing/unparseable so the caller treats the brief as DUE (regenerate).
    Used by the regenerate-every-N-days interval gate in run()."""
    if not isinstance(prev, dict):
        return None
    ts = prev.get("generated_at")
    if not isinstance(ts, str) or not ts.strip():
        return None
    try:
        gen = datetime.fromisoformat(ts)
        if gen.tzinfo is None:
            gen = gen.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - gen).total_seconds() / 86400.0
    except Exception:  # noqa: BLE001
        return None


def _interval_for(lens: str, cfg: dict) -> int:
    """Resolve the regeneration interval for a lens (spec §7).

    Resolution order: per-lens override (interval_days_by_lens.<lens>)
    → global interval_days → 1.  Result clamped 1..7.  Exception-safe.
    """
    try:
        by_lens = cfg.get("interval_days_by_lens") or {}
        if isinstance(by_lens, dict) and lens in by_lens:
            return max(1, min(7, int(by_lens[lens])))
        global_val = cfg.get("interval_days", 1)
        return max(1, min(7, int(global_val)))
    except Exception:  # noqa: BLE001
        return 1


def _leg(x):
    """Compact a conditions leg dict down to its headline fields."""
    if isinstance(x, dict):
        slim = {k: x.get(k) for k in ("label", "state", "value", "score", "pctile") if k in x}
        return slim or x
    return x


def _regime_drift_strings(now_val, val_5, val_20, dimension: str) -> dict:
    """Compose plain drift strings from score deltas (spec §5a).

    Direction word from sign of delta only:
      growth axis:    rising→strengthening, falling→cooling, |delta|<0.02→flat
      inflation axis: rising→warming, falling→cooling, |delta|<0.02→flat
    Never raises — returns {} on any exception.
    """
    try:
        if now_val is None:
            return {}
        out: dict = {"now": round(float(now_val), 4)}

        def _dir_word(delta: float) -> str:
            if abs(delta) < 0.02:
                return "flat"
            if dimension == "growth":
                return "strengthening" if delta > 0 else "cooling"
            else:  # inflation
                return "warming" if delta > 0 else "cooling"

        if val_5 is not None:
            d5 = float(now_val) - float(val_5)
            out["vs_5d"] = round(float(val_5), 4)
            out["delta_5d"] = round(d5, 4)
            out["drift_5d"] = (
                f"{dimension} {now_val:+.2f} now vs {val_5:+.2f} 5d ago "
                f"({_dir_word(d5)})"
            )
        if val_20 is not None:
            d20 = float(now_val) - float(val_20)
            out["vs_20d"] = round(float(val_20), 4)
            out["delta_20d"] = round(d20, 4)
            out["drift_20d"] = (
                f"{dimension} {now_val:+.2f} now vs {val_20:+.2f} 20d ago "
                f"({_dir_word(d20)})"
            )
        return out
    except Exception:  # noqa: BLE001
        return {}


def _regime_path_drift(history_path) -> dict:
    """Read growth/inflation drift from regime_history.parquet (spec §5a).

    Reads last row + rows 5 and 20 positions back.
    Fail-open: returns {} on ANY exception (file absent, corrupt, column mismatch).
    """
    try:
        import pandas as pd  # lazy — master_brain avoids pandas at import
        df = pd.read_parquet(history_path)
        if df is None or len(df) < 1:
            return {}
        last = df.iloc[-1]
        g_now = last.get("growth_score") if hasattr(last, "get") else last["growth_score"] if "growth_score" in df.columns else None
        i_now = last.get("inflation_score") if hasattr(last, "get") else last["inflation_score"] if "inflation_score" in df.columns else None

        # Safely pull a value from row at offset from the end
        def _back(col, n):
            if col not in df.columns or len(df) <= n:
                return None
            v = df.iloc[-(n + 1)][col]
            try:
                import math
                return None if math.isnan(float(v)) else float(v)
            except (TypeError, ValueError):
                return None

        g5 = _back("growth_score", 5)
        g20 = _back("growth_score", 20)
        i5 = _back("inflation_score", 5)
        i20 = _back("inflation_score", 20)

        growth_drift = _regime_drift_strings(
            float(g_now) if g_now is not None else None, g5, g20, "growth"
        )
        inflation_drift = _regime_drift_strings(
            float(i_now) if i_now is not None else None, i5, i20, "inflation"
        )
        out: dict = {}
        if growth_drift:
            out["growth"] = growth_drift
        if inflation_drift:
            out["inflation"] = inflation_drift
        return out
    except Exception:  # noqa: BLE001
        return {}


def _build_regime_path(m: dict, root=None) -> dict:
    """Compose the regime_path sub-dict from raw regime latest dict + history parquet (spec §5a).

    Never raises — entirely fail-open; missing keys or missing file → fields omitted.
    """
    out: dict = {}
    try:
        # From the raw latest dict: transition fields + flip info
        ts = m.get("transition_state")
        if ts is not None:
            out["transition_state"] = ts
        tsr = m.get("transition_state_raw")
        if tsr is not None:
            out["transition_state_raw"] = tsr
        tdr = m.get("transition_dwell_remaining")
        if tdr is not None:
            out["transition_dwell_remaining"] = tdr
        fc = m.get("flip_condition")
        if fc is not None:
            out["flip_condition"] = fc
        fm = m.get("flip_margin")
        if fm is not None:
            out["flip_margin"] = fm
        # transition_flags: names only of True flags, cap 4 (spec §5a)
        tf = m.get("transition_flags")
        if isinstance(tf, dict):
            active = [k for k, v in tf.items() if v][:4]
            if active:
                out["transition_flags"] = active

        # Drift block from history parquet — fail-open on any exception
        if root is not None:
            import pathlib
            hp = pathlib.Path(root) / "data" / "regime" / "regime_history.parquet"
            drift = _regime_path_drift(hp)
            if drift:
                out["drift"] = drift
    except Exception:  # noqa: BLE001
        pass
    return out


def _macro_summary(m: dict, root=None) -> dict:
    cond = m.get("conditions") or {}
    dis = m.get("dislocation") or {}
    mr = m.get("macro_risk") or {}
    pb = m.get("playbook") or {}
    dial = pb.get("dial")
    mdr = m.get("market_drivers") or {}
    drivers = None
    if mdr.get("verdict") not in (None, "unknown"):
        drivers = {"primary": mdr.get("primary_label"), "direction": mdr.get("direction"),
                   "verdict": mdr.get("verdict"), "confidence": mdr.get("confidence"),
                   "evidence": mdr.get("evidence"), "invalidation": mdr.get("invalidation")}
    summary = {
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
        "market_drivers": drivers,
    }
    # regime_path: always additive — never raises, never blocks (spec §5a)
    rp = _build_regime_path(m, root)
    if rp:
        summary["regime_path"] = rp
    return summary


def _macro_backdrop(m: dict | None) -> dict | None:
    """A SLIM macro summary for the focused (china/btc) lenses — regime + risk +
    posture only, no full conditions block (that's noise for a non-US read)."""
    if not m:
        return None
    mr = m.get("macro_risk") or {}
    pb = m.get("playbook") or {}
    return {
        "date": m.get("date"), "quad": m.get("quad"), "quad_name": m.get("quad_name"),
        "growth_score": m.get("growth_score"), "inflation_score": m.get("inflation_score"),
        "liquidity_overlay": m.get("liquidity_overlay"),
        "macro_risk": {"score": mr.get("score"), "label": mr.get("label")},
        "playbook_posture": pb.get("posture"),
    }


def _bonds_backdrop(root: Path | None = None) -> dict | None:
    """Bond-health backdrop for the cross-asset brain — the INDEPENDENT bond reads
    (cycle clock, credit / curve / rates-vol / sovereign states, the `drivers_for`
    hand-off built for exactly this). Deliberately EXCLUDES the bond contract's
    recession_risk / drawdown_risk / stock_bond_corr numbers, which are byte-identical
    to the macro `conditions` the brain already has (the bonds engine reuses
    engine.conditions) — passing them would double-count."""
    root = Path(root) if root else config.ROOT
    b = _read_json(root / "data/bonds/bond_health.json")
    if not b:
        return None
    p = b.get("pillars") or {}

    def gp(*ks):
        cur = p
        for k in ks:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(k)
        return cur

    return {
        "as_of": b.get("as_of"),
        "health_score": b.get("health_score"), "health_label": b.get("health_label"),
        "cycle_phase": b.get("cycle_phase"), "verdict": b.get("verdict_en"),
        "curve": {"taxonomy": gp("curve", "move_taxonomy"), "inverted": gp("curve", "inverted"),
                  "ntfs": gp("curve", "ntfs"), "uninversion_alarm": gp("curve", "uninversion_alarm")},
        "credit": {"distress_band": gp("credit", "distress_band"),
                   "direction": gp("credit", "direction"), "hy_oas": gp("credit", "hy_oas"),
                   "ebp": gp("credit", "ebp")},
        "real_inflation": {"real_10y": gp("real_inflation", "real_10y"),
                           "breakeven_5y5y": gp("real_inflation", "breakeven_5y5y"),
                           "term_premium": gp("real_inflation", "term_premium")},
        "stress": {"move_band": gp("stress", "move_band"),
                   "move_leads_vix": gp("stress", "move_leads_vix"),
                   "repo_stress": gp("stress", "repo_stress")},
        "stock_bond_corr_regime": gp("cross_asset", "regime"),
        "hedge_working": gp("cross_asset", "hedge_working"),
        "sovereign": {"frag_state": gp("sovereign", "frag_state"),
                      "jgb_state": gp("sovereign", "jgb_state")},
        "alarms": b.get("alarms") or [],
        "drivers_for": b.get("drivers_for"),
    }


def _confirm_summary(macro: dict | None) -> dict | None:
    """Compact cross-asset CONFIRMATION read (bonds + FX vs the equity regime) for the
    brain — the verdict + headline + the engine's own `to_brain` payload."""
    c = (macro or {}).get("cross_asset_confirm")
    if not isinstance(c, dict) or c.get("verdict") in (None, "unknown"):
        return None
    out = {"verdict": c.get("verdict"), "headline": c.get("headline_en"),
           "agree_pct": c.get("agree_pct")}
    tb = c.get("to_brain")
    if isinstance(tb, dict):
        out.update(tb)
    return out


_BTC_SMALL_COLS = ("composite_state", "risk_regime", "momentum", "mvrv_z",
                   "funding_z", "net_liquidity_bn", "macro_regime")

# Richer set for the BTC-focused lens — every layer of the vector, all scalar.
_BTC_RICH_COLS = (
    "composite_state", "composite_context", "market_mode", "alloc_optimal",
    # Override-Registry (W0): feed the AI brief both the final (possibly gated)
    # allocation and the pure engine series + override flag so the LLM can narrate
    # the override honestly (e.g. "engine wants 22% but override holds to 0%").
    # W2: override_released marks a Class-1 structural-invalidation auto-release.
    "alloc_optimal_raw", "override_active", "override_released",
    "risk_index", "risk_regime", "momentum", "momentum_state", "structure_state",
    "impulse_state", "efficiency_ratio",
    "cycle_phase", "cycle_pct", "days_since_halving", "vdd_multiple", "cycle_position",
    # bottom-anchored 1064/364 cycle clock (the chart's theory) — parity with the halving
    # phase above; CONTEXT only, lets the synthesis cite the projected pivot + maturity
    "cphase_phase", "cphase_pct", "cphase_days_left", "cphase_next_pivot", "cphase_status",
    "mvrv_z", "mvrv_z_pctile", "valuation_state", "nupl", "mayer", "reserve_risk_pctile",
    "market_extreme", "extreme_score",
    "vol_state", "dvol", "dvol_pctile", "rv_cone_pctile", "vrp", "rr_25d", "skew_term",
    "put_call_oi_ratio", "term_slope_30_90",
    "oi_mcap_pctile", "oi_price_divergence", "funding_annual_pct", "funding_z",
    "leverage_stress", "basis_ann", "cme_basis_regime",
    "flow_state", "etf_flow_state", "etf_flow_z",
    "coinbase_premium", "ssr_oscillator", "mpi",
    "net_liquidity_bn", "net_liq_roc", "global_m2_yoy", "global_liq_regime",
    "real_yield", "hy_oas", "vix", "dxy", "macro_score", "macro_regime",
    "stbl_regime", "stbl_growth_z", "peg_state",
    "cot_z", "corr_spx", "corr_gold", "corr_dxy", "risk_asset_regime",
    "hash_ribbon", "puell",
)


def _btc_signals_row(root: Path, cols) -> dict | None:
    """Pull the last row of the vector signals parquet (+ flash state) down to the
    requested columns. Floats rounded; non-numeric strings kept; NaN -> None."""
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
            try:
                out["date"] = str(getattr(last, "name", ""))[:10] or None
            except Exception:  # noqa: BLE001
                pass
            for c in cols:
                if c in df.columns:
                    v = last[c]
                    try:
                        fv = float(v)
                        out[c] = None if math.isnan(fv) else round(fv, 4)
                    except (TypeError, ValueError):
                        out[c] = v if isinstance(v, str) else None
    except Exception:  # noqa: BLE001
        pass
    return out or None


def _btc_summary(root: Path) -> dict | None:
    return _btc_signals_row(root, _BTC_SMALL_COLS)


def _transmission_summary(macro: dict | None) -> dict | None:
    """Slim rate/inflation transmission read for the LLM brief: the current state, the
    top headwind/tailwind assets, and which causal chains are active. DISPLAY-ONLY
    context (the scored-leg gate found none robust) — narrate, never call it a signal."""
    t = (macro or {}).get("rate_inflation_transmission")
    if not t:
        return None
    st = t.get("state") or {}
    def lab(d):  # the EN side of a bilingual label dict
        return (d or {}).get("label", {}).get("en") if isinstance(d, dict) else None
    out = {
        "rates": lab(st.get("rates")), "inflation": lab(st.get("inflation")),
        "expectations": lab(st.get("expectations")),
        "headwinds": [h.get("asset") for h in (t.get("headwinds") or [])[:4]],
        "tailwinds": [h.get("asset") for h in (t.get("tailwinds") or [])[:4]],
        "active_chains": [c.get("id") for c in (t.get("chains") or []) if c.get("active")],
        "scored": False,
    }
    # slim yield-curve read (engine/yield_curve.py) — regime + recession dashboard +
    # the curve's sector/style tilt. Display-only context; the curve narrates, never sizes.
    yc = (macro or {}).get("yield_curve")
    if yc:
        reg = yc.get("regime") or {}
        rec = yc.get("recession") or {}
        fac = (yc.get("signals") or {}).get("stock_factor") or {}
        out["yield_curve"] = {
            "regime": (reg.get("label") or {}).get("en"),
            "fed_phase": (reg.get("fed_phase") or {}).get("en"),
            "favored": reg.get("favored"), "pressured": reg.get("pressured"),
            "recession_risk": rec.get("risk"), "recession_flags": rec.get("flags"),
            "policy_stance": (rec.get("policy_stance") or {}).get("stance"),
            "style": {k: fac.get(k) for k in ("value_vs_growth", "size", "duration_factor")},
            "market_tendency": ((yc.get("signals") or {}).get("market_tendency") or {}).get("drawdown_risk"),
        }
    return out


def _policy_intel_summary(root: Path) -> dict | None:
    """Compact realpolitik policy-layer read for the macro brief (Fed/Admin intent +
    capital rotation). Context only — carries its own FACT/INFERENCE/PRIOR labels."""
    intel = _read_json(root / "data/policy/intel.json")
    if not intel:
        return None
    rot = intel.get("rotation") or {}
    return {
        "thesis": (intel.get("thesis") or {}).get("en"),
        "regime_read": (intel.get("regime_read") or {}).get("en"),
        "targeted": [r.get("theme_en") for r in (rot.get("targeted") or [])][:7],
        "starved": [r.get("theme_en") for r in (rot.get("starved") or [])][:4],
        "open_predictions_n": sum(1 for p in (intel.get("predictions") or []) if p.get("status") == "open"),
    }


_DESK_TRACKS = (
    ("ai_desk", "data/ai_desk/track_record.json"),
    ("policy_intent", "data/policy_intent/track_record.json"),
    ("altdata", "data/altdata/track_record.json"),
    ("radar", "data/radar/track_record.json"),
    ("stock_desk", "data/stock_desk/track_record.json"),
    ("demand_chain", "data/demand_chain/track_record.json"),
)


def _desk_track_records(root) -> dict:
    """Compact hit-rate summary of the Phase-C falsifiable-thesis desks, injected into the
    macro state so the Brain calibrates its synthesis to which desks have actually been
    right — down-weighting a desk that is cold (tiny sample) or has been wrong. This is the
    read-back that turns the flagship brain from an open loop into a consumer of measured
    desk accuracy. CONTEXT-ONLY; reads the scorers' track_record.json (never a score/size)."""
    out = {}
    for name, rel in _DESK_TRACKS:
        d = _read_json(Path(root) / rel)
        if not isinstance(d, dict):
            continue
        ov = d.get("overall") or {}
        rec = {"scored": d.get("scored_total"), "open": d.get("open"),
               "hit_rate": ov.get("hit_rate"), "dir_accuracy": ov.get("dir_accuracy")}
        if d.get("calibration_note"):
            rec["note"] = d["calibration_note"]
        out[name] = rec
    return out



# --------------------------------------------------------------------------- #
# entry-quality breadth — the MTF confluence buy-filter leaf, aggregated into a
# RISK / ENTRY-QUALITY breadth CALIBRATION check for the brain. This is the seam
# where the brain CONSUMES data/signal_archive/mtf_signals_latest.json (the leaf
# run.py loads into latest["mtf_signals"]; see research/signal_engine/CHARTER.md §7).
# Hard rules (CHARTER §2–4): it is a RISK / drawdown / entry-quality read, NOT a
# return / alpha signal; ONE input among many; never scored, never an auto-trade
# trigger; a DIFFERENT axis from engine.cycles entry_quality (cycle proximity) —
# do not conflate. Surfaced ONLY when the breadth DISAGREES with the macro regime.
# --------------------------------------------------------------------------- #
def _macro_risk_posture(macro: dict | None) -> tuple[str, int]:
    """Coarse risk-on / risk-off / neutral read off the macro summary, as an integer
    tilt: low macro-risk + expanding growth & liquidity -> risk-on; the inverse ->
    risk-off. Used ONLY to decide whether the entry-quality breadth DISAGREES with the
    regime (a calibration check) — it is NOT itself a signal. Reads keys that exist on
    BOTH the raw data/regime/latest.json dict and the _macro_summary shape (growth_score,
    liquidity_overlay, macro_risk.label), so either may be passed."""
    if not isinstance(macro, dict):
        return "unknown", 0
    tilt = 0
    mr = ((macro.get("macro_risk") or {}).get("label") or "").lower()
    tilt += {"low": 2, "moderate": 1, "elevated": -1, "severe": -2}.get(mr, 0)
    g = macro.get("growth_score")
    if isinstance(g, (int, float)):
        tilt += 1 if g > 0.25 else -1 if g < -0.25 else 0
    liq = (macro.get("liquidity_overlay") or "").lower()
    tilt += 1 if "expand" in liq else -1 if "contract" in liq else 0
    posture = "risk-on" if tilt >= 2 else "risk-off" if tilt <= -2 else "neutral"
    return posture, tilt


def entry_quality_breadth(macro: dict | None, root: Path | None = None) -> dict | None:
    """Aggregate the MTF buy-filter leaf across the US deep universe into a one-line
    entry-quality BREADTH read, and flag a calibration CONFLICT when that breadth
    disagrees with the macro regime posture. DISPLAY-ONLY risk/entry-quality context
    (CHARTER §2) — one input among many, never a return signal, never auto-traded."""
    root = Path(root) if root else config.ROOT
    leaf = _read_json(root / "data" / "signal_archive" / "mtf_signals_latest.json")
    return breadth_from_leaf(leaf, macro)


def breadth_from_leaf(leaf: dict | None, macro: dict | None) -> dict | None:
    """Pure aggregation of an mtf_signals leaf (the §7B shape) into the entry-quality
    breadth read + calibration check. Split out so the disk path and the historical
    regression harness share ONE code path."""
    if not isinstance(leaf, dict):
        return None
    sigs = [s for s in (leaf.get("signals") or []) if isinstance(s, dict)]
    n = len(sigs)
    if n < 20:                      # too thin to read breadth honestly
        return None

    def pct(c: int) -> int:
        return round(100.0 * c / n)

    def _last(s: dict) -> dict:          # malformed/absent `last` -> {} (degrade-never-raise)
        last = s.get("last")
        return last if isinstance(last, dict) else {}

    long_pct = pct(sum(1 for s in sigs if s.get("state") == "long-bias"))
    short_pct = pct(sum(1 for s in sigs if s.get("state") == "short-bias"))
    mixed_pct = pct(sum(1 for s in sigs if s.get("state") == "mixed"))
    above_pct = pct(sum(1 for s in sigs if s.get("above200") is True))
    # entry-posture = names whose LAST signal is a fresh entry (buy/rebuy); quality
    # (take/block/pending) only exists on those.
    entries = [s for s in sigs if _last(s).get("type") in ("buy", "rebuy")]
    ne = len(entries)
    entry_pct = pct(ne)
    take_n = sum(1 for s in entries if _last(s).get("quality") == "take")
    block_n = sum(1 for s in entries if _last(s).get("quality") == "block")
    pend_n = sum(1 for s in entries if _last(s).get("quality") == "pending")

    def qpct(c: int) -> int | None:
        return round(100.0 * c / ne) if ne else None

    take_pct, block_pct, pending_pct = qpct(take_n), qpct(block_n), qpct(pend_n)
    # take_share = take over RESOLVED entries (exclude pending) — the conviction read used
    # for the conflict test, so a wave of not-yet-confirmable entries can't masquerade as
    # low conviction (a pending entry isn't a blocked one).
    resolved = take_n + block_n
    take_share = round(100.0 * take_n / resolved) if resolved else None

    # Two ORTHOGONAL dimensions — CHARTER §5 is explicit that the 3D confluence is a
    # MEAN-REVERSION oscillator, so its long/short state mix is SHORT-HORIZON entry-timing
    # colour, NOT a regime read (at a local low inside an uptrend the whole universe reads
    # short-bias). Only the 200-day TREND breadth tracks the slow regime — so the regime
    # conflict is anchored on trend breadth, and entry quality is reported separately.
    #   thresholds: 40/60 trend bands; 45/55 take-share bands (around a 50% midpoint) —
    #   coarse, symmetric, display-only cut points, never tuned to past P&L (CHARTER §3).
    trend_breadth = ("broad-up" if above_pct >= 60
                     else "broad-down" if above_pct <= 40 else "split")
    entry_breadth = ("n/a" if take_share is None
                     else "endorsed" if take_share >= 55
                     else "narrow" if (ne >= 8 and take_share <= 45) else "mixed")

    take_txt = f"{take_pct}% take-quality entries" if take_pct is not None else "no fresh entries"
    summary = (f"entry-quality breadth (risk / display-only): {above_pct}% above 200-day, "
               f"{take_txt}, {long_pct}% long-bias ({n} US names, {ne} at entry)")

    # Surface a calibration CONFLICT only when the breadth DISAGREES with the regime: a
    # rolled-over / narrow tape under a risk-on read, or a still-broad tape under risk-off.
    macro_posture, _tilt = _macro_risk_posture(macro)
    conflict = None
    if macro_posture == "risk-on":
        if trend_breadth == "broad-down":
            conflict = (f"macro read is risk-on, but equity breadth has broadly rolled over "
                        f"(only {above_pct}% above the 200-day, {short_pct}% short-bias) — "
                        f"not broad risk appetite.")
        elif entry_breadth == "narrow":
            conflict = (f"macro read is risk-on, but only {take_share}% of fresh entries clear "
                        f"the buy-filter ({ne} at entry) — suggests narrow leadership / rotation, "
                        f"not broad conviction (trend breadth is {trend_breadth}).")
    elif macro_posture == "risk-off":
        if trend_breadth == "broad-up" and (take_share is None or take_share >= 50):
            extra = f", {take_share}% of fresh entries clear the filter" if take_share is not None else ""
            conflict = (f"macro read is risk-off, but equity breadth is still broadly up "
                        f"({above_pct}% above the 200-day{extra}) — the de-risk may be lagging or "
                        f"the all-clear premature; watch breadth to confirm the turn.")

    return {
        "kind": "entry-quality / risk breadth (NOT a return signal)",
        "asof": leaf.get("asof"), "tf": leaf.get("tf"), "universe": leaf.get("universe"),
        "n": n, "n_at_entry": ne,
        "long_bias_pct": long_pct, "short_bias_pct": short_pct, "mixed_pct": mixed_pct,
        "above200_pct": above_pct, "entry_posture_pct": entry_pct,
        "take_pct": take_pct, "block_pct": block_pct, "pending_pct": pending_pct,
        "take_share_resolved_pct": take_share,
        "trend_breadth": trend_breadth,        # regime-tracking (above-200)
        "entry_breadth": entry_breadth,        # short-horizon entry conviction
        "macro_posture": macro_posture,
        "summary": summary,
        "calibration_check": conflict,        # populated ONLY on a regime conflict
        "is_risk_breadth_only": True,
        "axis_note": ("3D MTF confluence buy-filter breadth; a DIFFERENT axis from cycle "
                      "entry_quality (cycle proximity) — do not conflate."),
    }


def gather_state(root: Path | None = None) -> dict:
    """Compact cross-asset state assembled from each dashboard's latest.json.
    Excludes holdings / watchlist composition by design. (macro lens)

    #35 same-tape labeling (W7): each block carries two metadata fields so the
    synthesis LLM knows which inputs share a root cause:
      tape_family — the underlying series family the block derives from.
        price_regime     : US price/momentum tape (quad legs, equity breadth, FX risk-off,
                           commodity, BTC are all different reads of the SAME price series)
        price_regime_cn  : China price tape
        price_regime_hk  : HK price tape
        rates_credit     : rates, credit spreads (EBP, HY-OAS) — partially leading
        policy_text      : forward-looking policy documents (FOMC text, Fed guidance, WH intel)
      lead_lag — this block's documented temporal relationship to equity returns:
        coincident : moves with prices (no forward-predictive edge documented for this block)
        leading    : has a defensible (though noisy) leading horizon on this price tape
    These tags are NOT an IC claim — they are honest provenance so the Brain cannot
    count five price-regime reads as five independent observations of the same signal.
    """
    root = Path(root) if root else config.ROOT
    macro = _read_json(root / "data/regime/latest.json") or {}
    macro_sum = _macro_summary(macro, root)
    # Attach tape provenance to the macro block (W7 #35)
    macro_sum["_tape_family"] = "price_regime"
    macro_sum["_lead_lag"] = "coincident"
    macro_sum["_tape_note"] = (
        "US equity/macro quad — 73% market-proxy legs (copper-gold, XLY/XLP, breadth). "
        "Coincident: moves with and re-encodes the price tape it is derived from."
    )
    state: dict = {"macro": macro_sum}
    ch = _read_json(root / "data/china_regime/latest.json")
    if ch:
        ch_block = {k: ch.get(k) for k in (
            "date", "quad", "quad_name", "growth_score", "inflation_score",
            "liquidity_overlay", "cycle_tag", "pending_quad")}
        ch_block["_tape_family"] = "price_regime_cn"
        ch_block["_lead_lag"] = "coincident"
        state["china"] = ch_block
    hk = _read_json(root / "data/hk_regime/latest.json")
    if hk:
        hk_block = {k: hk.get(k) for k in (
            "date", "quad", "quad_name", "global_score", "risk_state",
            "peg_state", "peg_distance", "liquidity_overlay")}
        hk_block["_tape_family"] = "price_regime_hk"
        hk_block["_lead_lag"] = "coincident"
        state["hk"] = hk_block
    co = _read_json(root / "data/commodity/latest.json")
    if co:
        co_block = {k: co.get(k) for k in ("date", "regime", "favored")}
        co_block["_tape_family"] = "price_regime"
        co_block["_lead_lag"] = "coincident"
        state["commodity"] = co_block
    fx = _read_json(root / "data/forex/latest.json")
    if fx:
        fx_block = {k: fx.get(k) for k in
                    ("date", "regime", "favored", "risk", "dollar_desk", "transmission",
                     "regime_radar", "stance")}
        fx_block["_tape_family"] = "price_regime"
        fx_block["_lead_lag"] = "coincident"
        fx_block["_tape_note"] = (
            "FX risk-off/dollar read is a COINCIDENT fragility gauge — moves with prices, "
            "not ahead of them. Do not treat it as independent of the equity regime."
        )
        # MSX-1 §2.2 additions — null-tolerant; absent keys degrade to None
        # state_changes: flips and regime ages are DESCRIPTIVE context, not predictors
        _sc = fx.get("state_changes") or {}
        fx_block["state_changes"] = {
            "_tape_family": "price_regime",
            "_lead_lag": "coincident",
            "_tape_note": (
                "State-change durations (days_in_state) describe how long the current "
                "regime has been in place — DESCRIPTIVE context only, not a predictor "
                "of flips. Do not infer reversion risk from age alone."
            ),
            "data": _sc if _sc else None,
        }
        # dominant stress scenario: context for narration, not a trading signal
        _rr_raw = fx.get("regime_radar") or {}
        _scenarios = _rr_raw.get("scenarios") or [] if isinstance(_rr_raw, dict) else []
        _dominant_key = _rr_raw.get("dominant") if isinstance(_rr_raw, dict) else None
        _dom_sc: dict | None = None
        for _sc_item in _scenarios:
            if isinstance(_sc_item, dict) and (
                _sc_item.get("key") == _dominant_key or _sc_item.get("active")
            ):
                _prob = _sc_item.get("prob") or {}
                _dom_sc = {
                    "key": _sc_item.get("key"),
                    "intensity": _sc_item.get("intensity"),
                    "p_cond": _prob.get("p_cond"),
                    "base_rate": _prob.get("base_rate"),
                    "_tape_family": "price_regime",
                    "_lead_lag": "coincident",
                    "_tape_note": (
                        "Stress-scenario intensity is a DESCRIPTIVE severity label — "
                        "not a probability of adverse outcome. Narrate; do not escalate."
                    ),
                }
                break
        fx_block["dominant_stress_scenario"] = _dom_sc
        # strength extremes: directional context, coincident with price moves
        _st_raw = fx.get("strength") or {}
        _st_default = _st_raw.get("default") or "1m"
        _st_horizons = _st_raw.get("horizons") or {}
        _st_list = _st_horizons.get(_st_default) or []
        _st_sorted = sorted(
            [h for h in _st_list if isinstance(h, dict) and h.get("strength") is not None],
            key=lambda h: h.get("strength", 0),
        ) if _st_list else []
        fx_block["strength_extremes"] = {
            "strongest": _st_sorted[-1] if _st_sorted else None,
            "weakest": _st_sorted[0] if _st_sorted else None,
            "horizon": _st_default,
            "_tape_family": "price_regime",
            "_lead_lag": "coincident",
            "_tape_note": (
                "Currency strength extremes are COINCIDENT with price moves — "
                "not predictive. Use for narrative context only."
            ),
        } if _st_sorted else None
        state["forex"] = fx_block
    # Bonds: the leading-family credit/curve/rates-vol backdrop — built (drivers_for)
    # for exactly this synthesis, but never wired in until now.
    bonds = _bonds_backdrop(root)
    if bonds:
        bonds["_tape_family"] = "rates_credit"
        bonds["_lead_lag"] = "leading"
        bonds["_tape_note"] = (
            "Credit/EBP and the curve (NTFS) have a defensible but noisy LEADING horizon. "
            "Rates-vol-vs-VIX and FX carry are COINCIDENT. The stock-bond correlation is a "
            "slow regime descriptor. Treat partial leading — do not claim bonds predict equities."
        )
        state["bonds"] = bonds
    # Cross-asset confirmation: do bonds + FX confirm or diverge from the equity regime?
    conf = _confirm_summary(macro)
    if conf:
        conf["_tape_family"] = "price_regime"
        conf["_lead_lag"] = "coincident"
        conf["_tape_note"] = (
            "SAME tape as `macro` and `forex` — bonds+FX vs equity regime divergence. "
            "This is ONE observation of the price_regime tape, not independent confirmation."
        )
        state["cross_asset_confirm"] = conf
    # Rate & inflation transmission: the current rate/inflation state + which assets it
    # is a headwind/tailwind for + which causal chains are active (display-only context).
    tr = _transmission_summary(macro)
    if tr:
        tr["_tape_family"] = "rates_credit"
        tr["_lead_lag"] = "coincident"
        tr["_tape_note"] = (
            "Rate/inflation read — rates are coincident to growth/inflation realizations. "
            "Scored=False: gate found no leg robust enough to time returns."
        )
        state["rate_inflation_transmission"] = tr
    btc = _btc_summary(root)
    if btc:
        btc["_tape_family"] = "price_regime"
        btc["_lead_lag"] = "coincident"
        state["btc"] = btc
    if macro.get("catalyst_tone"):
        ct_block = dict(macro["catalyst_tone"])
        ct_block["_tape_family"] = "policy_text"
        ct_block["_lead_lag"] = "leading"
        ct_block["_tape_note"] = (
            "FOMC text digest — forward-looking policy signal, independent of price tape. "
            "Context only; shock_reversible read is the binding use case."
        )
        state["catalyst_tone"] = ct_block
    # explicit Fed reaction-function stance (display-only leaf) + the realpolitik policy layer
    if macro.get("fed_stance"):
        fsd = macro["fed_stance"]
        fed_block = {k: fsd.get(k) for k in
                     ("stance", "label_en", "guidance", "implied_cuts_12m", "market_vs_fed_en")}
        fed_block["_tape_family"] = "policy_text"
        fed_block["_lead_lag"] = "leading"
        state["fed_stance"] = fed_block
    pol = _policy_intel_summary(root)
    if pol:
        pol["_tape_family"] = "policy_text"
        pol["_lead_lag"] = "leading"
        state["policy_intel"] = pol
    # event-driven special situations (display-only leaf): macro-level landscape only.
    # Per-ticker situation context is consumed directly from site/allocationdata/
    # special_situations.json (schema special_situations.v1, is_context_only).
    ss = _read_json(root / "data/regime/special_situations_latest.json")
    if ss:
        state["special_situations"] = {k: ss.get(k) for k in
                                       ("total", "n_categories", "cross_border", "top_categories")}
    # Read-back: the measured hit-rates of the falsifiable-thesis desks, so the Brain
    # calibrates its synthesis to which desks have actually been right (close the loop).
    tracks = _desk_track_records(root)
    if tracks:
        state["desk_track_records"] = tracks
    # W4 (#13): the SHADOW deterministic desk-weight vector from the outcome spine's
    # partial-pooling. Computed alongside the context read; the live flip is gated behind the
    # arm-by-evidence predicate (engine.pooling.arming). Surfaced so the divergence from
    # equal-weight is visible and the loop is measurable — the brain sees which desks the
    # spine down-weights, not just their hit-rates.
    try:
        from engine import desk_scorer as _ds
        dw = _ds.desk_weights(root=root)
        if dw and dw.get("per_desk"):
            state["desk_weights_shadow"] = {
                "armed": dw.get("armed"), "arming": dw.get("arming"),
                "divergence_l1": dw.get("divergence_l1"),
                "live_weights": dw.get("live_weights"),
                "shadow_weights": dw.get("shadow_weights"),
            }
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
    # MTF buy-filter entry-quality BREADTH (the brain CONSUMING the mtf_signals leaf) —
    # a RISK / entry-quality calibration check (CHARTER §2). Surfaced ONLY when it
    # CONFLICTS with the macro regime read; one input among many, never scored.
    eqb = entry_quality_breadth(macro, root)
    if eqb and eqb.get("calibration_check"):
        eqb["_tape_family"] = "price_regime"
        eqb["_lead_lag"] = "coincident"
        eqb["_tape_note"] = (
            "MTF buy-filter breadth — derived from the SAME US price tape as `macro`. "
            "SAME tape_family = one observation, not independent confirmation."
        )
        state["entry_quality_breadth"] = eqb
    # Oracle rotation directive — optional additive block (data/oracle/rotation_directive.json).
    # Surfaces rolling-over leaders and rotation context so the Brain can temper conviction
    # and raise cash; never a directional buy signal. Degrades silently when absent.
    try:
        _od = _read_json(root / "data" / "oracle" / "rotation_directive.json")
        if isinstance(_od, dict) and _od.get("rolling_over_leaders") is not None:
            oracle_block = {
                "rolling_over_leaders": _od.get("rolling_over_leaders"),
                "strengthening_complexes": _od.get("strengthening_complexes"),
                "regime_aggregate": _od.get("regime_aggregate"),
                "instruction": _od.get("instruction"),
                "asof": _od.get("asof"),
                "_tape_family": "price_regime",
                "_lead_lag": "coincident",
                "_tape_note": (
                    "Oracle rotation context: rolling-over leaders for conviction tempering "
                    "and cash-raising guidance. Display-only. NOT a directional buy signal. "
                    "Primaries NULL per P3 gauntlet; onset secondaries DISPLAY-WITH-EDGE only."
                ),
            }
            state["oracle_rotation"] = oracle_block
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
    # ADB-W1: inject NW context packet (lazy import so a broken NW package never breaks the brief)
    try:
        from engine.neuralweb import brief_context  # noqa: PLC0415
        state["neural_web"] = brief_context.macro_slice(root)
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
    # ADB-W2: forward-calendar state block (events, releases, rebalance, cycle hazards,
    # odds fingerprint, hypothesis clocks).  Fail-open: any failure → absent markers.
    try:
        from engine import forward_calendar_context as _fcc  # noqa: PLC0415
        state["forward_calendar"] = _fcc.gather_forward_calendar(root)
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
    return state


def gather_china_state(root: Path | None = None) -> dict:
    """China & Hong-Kong focused state: the full China/HK regime detail, with a slim
    US-macro / commodity / FX backdrop. (china lens)"""
    root = Path(root) if root else config.ROOT
    state: dict = {}
    ch = _read_json(root / "data/china_regime/latest.json")
    if ch:
        state["china"] = {k: ch.get(k) for k in (
            "date", "quad", "quad_name", "growth_score", "inflation_score",
            "growth_confidence", "inflation_confidence", "confidence",
            "liquidity_overlay", "cycle_tag", "pending_quad", "pending_days",
            "confirming", "contradicting", "sector_rs", "pair_ratios") if k in ch}
        # regime_path for china: same-shape drift from china regime history (spec §5a)
        try:
            _ch_hp = root / "data" / "china_regime" / "regime_history.parquet"
            _ch_drift = _regime_path_drift(_ch_hp)
            if _ch_drift:
                state["china"]["regime_path"] = {"drift": _ch_drift}
        except Exception:  # noqa: BLE001 — silently omit, never block
            pass
    hk = _read_json(root / "data/hk_regime/latest.json")
    if hk:
        state["hk"] = {k: hk.get(k) for k in (
            "date", "quad", "quad_name", "growth_score", "inflation_score", "confidence",
            "liquidity_overlay", "cycle_tag", "global_score", "risk_state",
            "peg_state", "peg_distance", "confirming", "contradicting",
            "sector_rs", "pair_ratios") if k in hk}
        # compact display-only leaves (RORO / slowdown / drawdown / fear-euphoria /
        # tape drivers / property) — context for the narrator; never scored.
        cond = hk.get("conditions") or {}
        if cond:
            state["hk"]["conditions"] = {
                "roro_state": (cond.get("roro") or {}).get("roro_state"),
                "slowdown_score": (cond.get("recession") or {}).get("score"),
                "slowdown_label": (cond.get("recession") or {}).get("label"),
                "drawdown_band": (cond.get("drawdown_risk") or {}).get("band"),
            }
        fe = hk.get("fear_euphoria") or {}
        if fe:
            state["hk"]["fear_euphoria"] = {k: fe.get(k) for k in ("fe_score", "band") if k in fe}
        md = hk.get("market_drivers") or {}
        if md.get("verdict") not in (None, "unknown"):
            state["hk"]["market_drivers"] = {k: md.get(k) for k in
                                             ("verdict", "primary_label", "direction") if k in md}
        prop = hk.get("property") or {}
        if prop:
            state["hk"]["property"] = {k: prop.get(k) for k in
                                       ("regime", "ccl_chg_52w") if k in prop}
    backdrop = _macro_backdrop(_read_json(root / "data/regime/latest.json"))
    if backdrop:
        state["us_macro_backdrop"] = backdrop
    co = _read_json(root / "data/commodity/latest.json")
    if co:
        state["commodity"] = {k: co.get(k) for k in ("date", "regime", "favored")}
    fx = _read_json(root / "data/forex/latest.json")
    if fx:
        state["forex"] = {k: fx.get(k) for k in
                          ("date", "regime", "favored", "risk", "dollar_desk", "transmission",
                           "regime_radar", "stance")}
    # bonds backdrop — global rate-differential / risk-off context that pushes on HK & A-shares
    bonds = _bonds_backdrop(root)
    if bonds:
        state["bonds"] = bonds
    # China intelligence surfaces (news media-sentiment · PBoC stance · alt-data convergence ·
    # divergence radar) — the transmission bus already fans these four into one compact,
    # context-only block. Display/context for the narrator; never scored.
    try:
        from engine import china_intel_bus
        b = china_intel_bus.briefing()
        # widened whitelist (v3): the central-analysis synthesis (now opportunity/edge/lifecycle-
        # ranked) + flagged tickers + what-changed + the risk-appetite regime + off-desk discovery
        # must propagate, not just the raw surface blocks (the whitelist gates them).
        keys = ("news", "policy", "altdata", "radar",
                "analysis", "conviction", "cross_surface", "flagged_tickers",
                "what_changed", "salience", "regime", "discovery")
        intel = {k: b.get(k) for k in keys if b.get(k)}
        if intel:
            intel["digest"] = b.get("digest")     # the synthesis-led plain-text rollup
            # the context-only contract MUST travel with the hoisted conviction/flagged tickers
            intel["is_context_only"] = True
            intel["disclaimer"] = b.get("disclaimer")
            intel["disclaimer_zh"] = b.get("disclaimer_zh")
            state["china_intel"] = intel
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.debug("china_intel state unavailable (%s)", e)
    # ADB-W1: inject NW China context packet (lazy import so a broken NW package never breaks the brief)
    try:
        from engine.neuralweb import brief_context  # noqa: PLC0415
        state["neural_web"] = brief_context.china_slice(root)
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
    return state


def gather_btc_state(root: Path | None = None) -> dict:
    """Bitcoin focused state: the rich vector signal row + a slim US-macro backdrop.
    (btc lens)"""
    root = Path(root) if root else config.ROOT
    state: dict = {}
    btc = _btc_signals_row(root, _BTC_RICH_COLS)
    if btc:
        state["btc"] = btc
    backdrop = _macro_backdrop(_read_json(root / "data/regime/latest.json"))
    if backdrop:
        state["us_macro_backdrop"] = backdrop
    # bonds backdrop — BTC is a long-duration, real-rate-sensitive liquidity asset, so the
    # real-10y / credit / rates-vol read (and the bond layer's `drivers_for.bitcoin` gate) is
    # directly relevant.
    bonds = _bonds_backdrop(root)
    if bonds:
        state["bonds"] = bonds
    # ADB-W1 / spec §5b: inject NW BTC context packet (lazy import, never fatal)
    try:
        from engine.neuralweb import brief_context  # noqa: PLC0415
        state["neural_web"] = brief_context.btc_slice(root)
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
    return state


# --------------------------------------------------------------------------- #
# lens registry — domain framing + state builder + output file, one engine each
# --------------------------------------------------------------------------- #
LENSES: dict[str, dict] = {
    "macro": {"out": "master_brief.json", "state_fn": gather_state,
              "system": MASTER_SYSTEM_TMPL, "thesis": DEFAULT_THESIS},
    "china": {"out": "china_brief.json", "state_fn": gather_china_state,
              "system": CHINA_SYSTEM_TMPL, "thesis": CHINA_THESIS},
    "btc":   {"out": "btc_brief.json", "state_fn": gather_btc_state,
              "system": BTC_SYSTEM_TMPL, "thesis": BTC_THESIS},
}


def _state_asof(state: dict) -> str | None:
    for k in ("macro", "china", "btc", "hk"):
        d = state.get(k)
        if isinstance(d, dict) and d.get("date"):
            return d.get("date")
    return None


def _thesis_for(lens: str, cfg: dict) -> str:
    spec = LENSES.get(lens, LENSES["macro"])
    # per-lens override (<lens>_thesis), then legacy rotation_thesis (macro only), then default
    return (cfg.get(f"{lens}_thesis")
            or (cfg.get("rotation_thesis") if lens == "macro" else None)
            or spec["thesis"])


# --------------------------------------------------------------------------- #
# content-hash reply cache — determinism kit (W7 #33)
#
# master_brain synthesis is CONVERSATIONAL/NARRATIVE (not graded → not in a
# ledger), BUT its output shapes the daily brief users act on and the producer
# theses land in theses.jsonl (a graded ledger). Temperature=0 + seed=0 makes
# the call as deterministic as the provider allows. The content-hash cache gives
# a HARD guarantee: the same state JSON on the same day → identical brief, even
# if the provider's temperature=0 isn't perfectly deterministic.
# --------------------------------------------------------------------------- #
def _mb_prompt_hash(model: str, system: str, user: str) -> str:
    h = hashlib.sha256()
    for part in (model, system, user):
        h.update(part.encode("utf-8"))
    return h.hexdigest()


def _mb_reply_cache_path(prompt_hash: str, cfg: dict, root=None, create: bool = False):
    """Cache file path, ROOT-AWARE: fixture runs (root=tmp) must never touch the
    real data/ tree (MM_DATA_GUARD; the root-param≠data_dir bug class). The dir is
    only created on writes — a read probe leaves the tree untouched."""
    from pathlib import Path as _P
    base = _P(root) if root else config.ROOT
    cdir = base / cfg.get("reply_cache_dir", "data/master_brain/reply_cache")
    if create:
        cdir.mkdir(parents=True, exist_ok=True)
    return cdir / f"{prompt_hash}.txt"


def _mb_reply_cache_get(prompt_hash: str, cfg: dict, root=None) -> str | None:
    p = _mb_reply_cache_path(prompt_hash, cfg, root)
    try:
        return p.read_text() if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def _mb_reply_cache_put(prompt_hash: str, text: str, cfg: dict, root=None) -> None:
    try:
        _mb_reply_cache_path(prompt_hash, cfg, root, create=True).write_text(text)
    except Exception:  # noqa: BLE001
        pass


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
    """Return (reply_text, degraded_reason). Never raises.

    Determinism kit (W7 #33): temperature=0 + seed=0 for greedy/deterministic
    sampling. Content-hash cache: SHA-256(model‖system‖user) → cached reply text.
    Cache stores the FINAL post-lint text (updated by synthesize() after lint);
    on a cache HIT the stored text is already post-lint — synthesize() skips lint.

    W5 ITEM 1 — 401-fallback: master_brain defaults to DeepSeek as its primary
    provider (llm_base_url / api_key_env configurable). The waterfall is built via
    engine.llm_auth.build_providers() so a 401 from any provider falls back cleanly.
    The degraded_reason distinguishes "auth_invalid:<provider>" from "llm_error".
    """
    from engine import llm_auth

    # master_brain uses a non-standard provider config: the default provider is
    # DeepSeek, but it is fully config-overridable via llm_base_url/api_key_env.
    # We build a minimal provider descriptor directly rather than using build_providers()
    # (which assumes the oauth→anthropic→deepseek order), because master_brain
    # intentionally sends derived market state to an endpoint the operator chose.
    client = _client(cfg)
    if client is None:
        return None, "no_client_or_key"
    model = cfg.get("llm_model", "deepseek-v4-pro")
    env_var = cfg.get("api_key_env", "DEEPSEEK_API_KEY")
    providers = [{"name": "deepseek", "env_var": env_var, "cred": "present",
                  "client": client, "model": model,
                  "usage_lane": "master-brain"}]

    # NB: no caching here — synthesize() is the SOLE cache reader/writer, so only
    # FINAL post-lint text ever lands under the prompt hash (a raw pre-lint reply
    # cached here would dodge the style lint on the next same-day run).
    max_tokens = int(cfg.get("max_tokens", 4000))

    def _make_do_call(_seed: int | None):
        def _do_call(_client, _model: str):
            kw: dict = {
                "model": _model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
                # temperature removed — rejected (400) on opus-4.7+ per Anthropic API
            }
            try:
                if _seed is not None:
                    kw["seed"] = _seed
                resp = _client.messages.create(**kw)
            except TypeError:
                kw.pop("seed", None)
                resp = _client.messages.create(**kw)
            sr = getattr(resp, "stop_reason", None)
            if sr == "refusal":
                return None, "stop_refusal", resp
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            if not text:
                return None, "empty_reply", resp
            return text, ("truncated" if sr == "max_tokens" else None), resp
        return _do_call

    # Transient-failure retry (empty / refusal reply). A degraded or rate-limited
    # endpoint can return a 200 with no text content — the China lens hit exactly
    # this on 2026-07-20 while the macro lens (called seconds earlier) succeeded,
    # leaving china_brief.json blank until the next nightly run. A bounded re-call
    # recovers the SAME-run brief. Attempt 0 keeps seed=0 so the determinism
    # contract holds for the normal (successful) path; retries nudge the seed so a
    # deterministically-empty completion can differ. NOT retried: "truncated" (real
    # content, merely capped) and every make_call waterfall reason (auth / rate-limit
    # already walked the provider list, and the provider is now marked dead). This
    # function never touches the reply cache — synthesize() owns it, keyed on
    # (model, system, user) — so the seed nudge cannot poison or dodge the cache.
    _RETRYABLE = {"empty_reply", "stop_refusal"}
    max_attempts = max(1, int(cfg.get("empty_reply_retries", 2)) + 1)

    text: str | None = None
    reason: str | None = None
    for attempt in range(max_attempts):
        seed = 0 if attempt == 0 else attempt   # primary deterministic; retries vary
        try:
            text, reason, _ = llm_auth.make_call(
                providers, _make_do_call(seed), context="master_brain")
        except Exception as e:  # noqa: BLE001 — degrade, never raise
            log.warning("master_brain model call failed (%s)", e)
            return None, "llm_error"
        if text is not None or reason not in _RETRYABLE:
            break
        if attempt + 1 < max_attempts:
            log.warning(
                "master_brain: '%s' on attempt %d/%d — retrying (seed=%d)",
                reason, attempt + 1, max_attempts, attempt + 1)
    return text, reason


# --------------------------------------------------------------------------- #
# style lint — deterministic banned-token checker (spec §4)
# --------------------------------------------------------------------------- #
import re as _re

# Paren-gated tokens: these are violations ONLY when NOT inside parentheses.
# Pattern: the token appears in text NOT preceded by "(" context.
_PAREN_GATED_TOKENS = (
    "FR007", "MVRV", "NUPL", "SSR", "DVOL", "EBP", "SOFR", "IORB", "LPR", "RRR",
)

# Hard-banned tokens (case-insensitive, always a violation)
_HARD_BANNED_TOKENS = (
    "cross_asset_confirm", "neural_web", "nw_synthesis", "tape_family",
    "cphase", "mvrv_z", "funding_z", "etf_flow_z", "oi_mcap", "hy_oas",
    "ntfs", "display-tier", "display_only",
)

# Compiled patterns (module-level; re-use across calls)
_RE_SNAKE = _re.compile(r"\b[A-Za-z]+_[A-Za-z0-9_]+\b")
_RE_SIGMA = _re.compile(r"σ|\bz[- ]?scores?\b|[+-]?\d+(?:\.\d+)?\s*σ|%ile\b|\bpctile\b|\bpercentile\b", _re.IGNORECASE)
_RE_PANEL = _re.compile(r"\bpanels?\s*:", _re.IGNORECASE)
_RE_DASHBOARD = _re.compile(r"\bdashboards?\s*:", _re.IGNORECASE)
_RE_QUAD = _re.compile(r"\bQ[1-4]\b")
_RE_HARD_BANNED = _re.compile(
    r"\b(" + "|".join(_re.escape(t) for t in _HARD_BANNED_TOKENS) + r")\b",
    _re.IGNORECASE,
)

# For paren-gated: find occurrences of the token NOT inside parens.
# We match "(... TOKEN ...)" as allowed; bare TOKEN is a violation.
def _paren_gated_violations(text: str) -> list[str]:
    """Return violations for paren-gated tokens found OUTSIDE parentheses."""
    violations: list[str] = []
    for token in _PAREN_GATED_TOKENS:
        # Find all occurrences of token (case-sensitive, they are uppercase codes)
        for m in _re.finditer(_re.escape(token), text):
            start = m.start()
            # Check if this occurrence is inside parentheses: scan left for '(' before ')'
            prefix = text[:start]
            open_count = prefix.count("(") - prefix.count(")")
            if open_count <= 0:
                violations.append(f"paren-gated token outside parens: {token}")
                break  # one violation per token
    return violations


def _style_violations(text: str) -> list[str]:
    """Return list of style violation descriptions for a single string (spec §4).

    Checks: snake_case, sigma/z/percentile forms, panel citations, quad codes,
    hard-banned tokens, paren-gated tokens (violation ONLY outside parens).
    Returns [] on any exception (degrade-never-raise).
    """
    if not isinstance(text, str) or not text:
        return []
    try:
        violations: list[str] = []

        # 1. snake_case tokens
        for m in _RE_SNAKE.finditer(text):
            violations.append(f"snake_case: {m.group()}")

        # 2. sigma/z/percentile forms
        for m in _RE_SIGMA.finditer(text):
            violations.append(f"sigma/z/pctile: {m.group()}")

        # 3. panel citations (colon form only)
        for m in _RE_PANEL.finditer(text):
            violations.append(f"panel citation: {m.group()}")
        for m in _RE_DASHBOARD.finditer(text):
            violations.append(f"dashboard citation: {m.group()}")

        # 4. quad codes
        for m in _RE_QUAD.finditer(text):
            violations.append(f"quad code: {m.group()}")

        # 5. hard-banned tokens
        for m in _RE_HARD_BANNED.finditer(text):
            violations.append(f"banned token: {m.group()}")

        # 6. paren-gated tokens (only when outside parens)
        violations.extend(_paren_gated_violations(text))

        return violations
    except Exception:  # noqa: BLE001
        return []


def _collect_style_violations(parsed: dict) -> list[str]:
    """Collect style violations across all LLM string fields of a parsed brief reply."""
    fields_to_check: list[str] = []
    # Scalar string fields
    for k in ("summary", "regime_read", "rotation_check", "forward_read"):
        v = parsed.get(k)
        if isinstance(v, str):
            fields_to_check.append(v)
    # List fields (each item individually)
    for k in ("tldr", "conflicts", "transmission", "watch_items"):
        for item in (parsed.get(k) or []):
            if isinstance(item, str):
                fields_to_check.append(item)

    all_violations: list[str] = []
    for text in fields_to_check:
        all_violations.extend(_style_violations(text))
    return all_violations


# --------------------------------------------------------------------------- #
# public: synthesize one brief
# --------------------------------------------------------------------------- #
def synthesize(state: dict, cfg: dict | None = None, lens: str = "macro", root=None) -> dict:
    """Run the LLM synthesis over a gathered state for one LENS. Always returns a
    brief record (degraded fields flagged); never raises."""
    cfg = cfg or _cfg()
    spec = LENSES.get(lens, LENSES["macro"])
    brief = {
        "schema": "master_brief.v2", "lens": lens, "is_context_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": cfg.get("llm_model", "deepseek-v4-pro"),
        "state_asof": _state_asof(state),
        "tldr": [],
        "summary": None, "regime_read": None, "conflicts": [], "rotation_check": None,
        "transmission": [], "watch_items": [], "confidence": "low",
        "theses": [],    # macro-lens producer leans (always present → additive when absent)
        "raw_text": None, "degraded_reason": None, "disclaimer": DISCLAIMER_TEXT,
    }
    system = spec["system"].format(thesis=_thesis_for(lens, cfg))
    user = ("Today's deterministic state (JSON). Synthesize per your "
            "instructions.\n<state>\n"
            + json.dumps(state, indent=2, default=str) + "\n</state>")

    # _call_model handles cache GET (returns cached if hit) and the raw provider call.
    # Content-hash cache, ROOT-AWARE (spec §4): synthesize is the SOLE cache
    # reader/writer, so only FINAL post-lint text ever lands under the prompt
    # hash — a cache hit therefore skips both the (paid) call AND the lint.
    # Root-awareness keeps fixture runs inside tmp roots (MM_DATA_GUARD).
    model = cfg.get("llm_model", "deepseek-v4-pro")
    phash = _mb_prompt_hash(model, system, user)
    cached = _mb_reply_cache_get(phash, cfg, root)
    _cache_was_hit = cached is not None
    if _cache_was_hit:
        log.debug("master_brain: reply cache HIT (%s)", phash[:12])
        reply, reason = cached, None
    else:
        reply, reason = _call_model(system, user, cfg)

    brief["raw_text"] = reply
    if reply is None:
        brief["degraded_reason"] = reason
        return brief
    parsed = _extract_json(reply)
    if not isinstance(parsed, dict):
        brief["degraded_reason"] = reason or "unparseable_reply"   # surfaces "truncated"
        return brief

    # Style lint + ONE rewrite retry (spec §4).
    # Skip lint on cache hits — stored text was already linted on the run that wrote it.
    style_flags: list[str] = []
    if not _cache_was_hit:
        try:
            violations = _collect_style_violations(parsed)
            if violations:
                # Build a deduplicated list of banned token names for the rewrite prompt
                banned_list = list(dict.fromkeys(v.split(": ", 1)[-1] for v in violations))[:15]
                rewrite_system = (
                    "Your brief contains banned machine tokens: "
                    + ", ".join(banned_list)
                    + ". Rewrite the SAME JSON — identical structure and claims — "
                    "replacing every banned token with plain language a non-finance "
                    "reader understands. Return only the JSON."
                )
                rw_reply, _rw_reason = _call_model(rewrite_system, reply, cfg)
                if rw_reply:
                    rw_parsed = _extract_json(rw_reply)
                    if isinstance(rw_parsed, dict):
                        rw_violations = _collect_style_violations(rw_parsed)
                        if len(rw_violations) <= len(violations):
                            # Rewrite is better (or no worse) — accept it
                            reply = rw_reply
                            parsed = rw_parsed
                            violations = rw_violations
                style_flags = violations
            # Cache the FINAL post-lint text under the ORIGINAL prompt hash. On a
            # lint failure above we cache NOTHING (next run re-calls and re-lints)
            # — never a raw pre-lint reply that would dodge the lint on a hit.
            _mb_reply_cache_put(phash, reply, cfg, root)
        except Exception:  # noqa: BLE001 — degrade, never raise
            pass

    brief["style_flags"] = style_flags

    for k in _BRIEF_FIELDS:
        if k in parsed:
            brief[k] = parsed[k]
    # ADB-W2: forward_watch and forward_read (macro lens only).  Parsed defensively:
    # - forward_watch: must be a list of dicts; any malformed row is dropped.
    # - forward_read: must be a string; missing → omitted.
    if lens == "macro":
        try:
            raw_fw = parsed.get("forward_watch")
            if isinstance(raw_fw, list):
                valid_rows = []
                for row in raw_fw:
                    if isinstance(row, dict) and row.get("date") and row.get("label"):
                        valid_rows.append({
                            "date": str(row["date"]),
                            "label": str(row["label"]),
                            "kind": str(row.get("kind", "")),
                            "note": str(row.get("note", ""))[:120],  # guard runaway notes
                        })
                if valid_rows:
                    brief["forward_watch"] = valid_rows
            raw_fr = parsed.get("forward_read")
            if isinstance(raw_fr, str) and raw_fr.strip():
                brief["forward_read"] = raw_fr.strip()
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.debug("master_brain: forward_watch/read parse failed: %s", e)
    # macro-lens producer: stake the brain's OWN falsifiable leans. Wrapped in its own try so
    # a theses bug can NEVER discard the free-text already copied above (the schema tail is
    # placed last, so a truncated reply drops the trailing theses array first, not the narrative).
    if lens == "macro" and cfg.get("emit_theses", True):
        try:
            raw = parsed.get("theses") if isinstance(parsed.get("theses"), list) else []
            built = []
            for t in raw[: int(cfg.get("max_theses", 2))]:
                th = _mb_build_thesis(t, len(built), brief["state_asof"], root, cfg)
                if th is not None:
                    built.append(th)
            brief["theses"] = built
        except Exception as e:  # noqa: BLE001 — a theses bug must never lose the free-text
            log.warning("master_brain: theses parse failed: %s", e)
            brief["theses"] = []
    if reason:
        brief["degraded_reason"] = reason          # parsed, but flag e.g. truncation
    return brief


# --------------------------------------------------------------------------- #
# key_facts builders (spec §6) — deterministic chip rail, bilingual at build
# --------------------------------------------------------------------------- #

def _prettify(s) -> str:
    """Prettify an enum string: replace underscores with spaces, title-case."""
    return str(s).replace("_", " ").title() if s is not None else ""


# quad_name → (EN display, ZH display)
_QUAD_NAME_MAP: dict[str, tuple[str, str]] = {
    "goldilocks":  ("Goldilocks",      "金发姑娘(不冷不热)"),
    "reflation":   ("Reflation",       "再通胀"),
    "stagflation": ("Stagflation",     "滞胀"),
    "deflation":   ("Deflation",       "通缩/放缓"),
}
_QUAD_TONE: dict[str, str] = {
    "goldilocks": "good", "reflation": "info",
    "stagflation": "warn", "deflation": "bad",
}


def _quad_display(quad_name, shifting: bool) -> tuple[str, str, str]:
    """Return (value_en, value_zh, tone) for a quad_name, with optional shifting suffix."""
    key = (quad_name or "").lower()
    en_base, zh_base = _QUAD_NAME_MAP.get(key, (_prettify(quad_name), _prettify(quad_name)))
    tone = _QUAD_TONE.get(key, "neutral")
    if shifting:
        tone = "warn"
        return en_base + " · shifting", zh_base + " · 转换中", tone
    return en_base, zh_base, tone


def _kf_macro(state: dict) -> list[dict]:
    """Build macro key_facts chips (spec §6, macro table)."""
    chips: list[dict] = []
    try:
        macro = state.get("macro") or {}
        bonds = state.get("bonds") or {}
        ca = state.get("cross_asset_confirm") or {}
        mdr = (macro.get("market_drivers") or {}) if isinstance(macro.get("market_drivers"), dict) else {}

        # 1. regime
        quad_name = macro.get("quad_name")
        if quad_name is not None:
            ts = (macro.get("transition_state") or macro.get("regime_path", {}).get("transition_state") or "")
            shifting = (str(ts).upper() == "TRANSITIONING")
            v_en, v_zh, tone = _quad_display(quad_name, shifting)
            chips.append({
                "key": "regime", "label_en": "Regime", "label_zh": "市场格局",
                "value_en": v_en, "value_zh": v_zh, "tone": tone,
            })

        # 2. risk
        risk_label = ((macro.get("macro_risk") or {}).get("label") or "")
        _risk_map: dict[str, tuple[str, str, str]] = {
            "low":      ("Low",      "低",   "good"),
            "moderate": ("Moderate", "中等", "neutral"),
            "elevated": ("Elevated", "偏高", "warn"),
            "severe":   ("Severe",   "严重", "bad"),
        }
        if risk_label:
            rv_en, rv_zh, rt = _risk_map.get(risk_label.lower(), (_prettify(risk_label), _prettify(risk_label), "neutral"))
            chips.append({
                "key": "risk", "label_en": "Market risk", "label_zh": "市场风险",
                "value_en": rv_en, "value_zh": rv_zh, "tone": rt,
            })

        # 3. money (liquidity_overlay)
        liq = (macro.get("liquidity_overlay") or "").lower()
        if liq:
            _liq_map: dict[str, tuple[str, str, str]] = {
                "expand":    ("Expanding", "扩张", "good"),
                "contract":  ("Tightening", "收紧", "warn"),
            }
            # match by prefix so "expanding", "contracting" both work
            lv_en, lv_zh, lt = "Neutral", "中性", "neutral"
            for k, v in _liq_map.items():
                if liq.startswith(k):
                    lv_en, lv_zh, lt = v
                    break
            chips.append({
                "key": "money", "label_en": "Money", "label_zh": "资金面",
                "value_en": lv_en, "value_zh": lv_zh, "tone": lt,
            })

        # 4. bonds (cross_asset_confirm.verdict)
        ca_verdict = (ca.get("verdict") or "").lower()
        if ca_verdict:
            _ca_map: dict[str, tuple[str, str, str]] = {
                "confirm":  ("Agree",                        "一致",         "good"),
                "diverge":  ("Disagree — bonds worried",     "分歧 — 债市担忧", "warn"),
                "mixed":    ("Mixed",                        "好坏参半",     "neutral"),
            }
            bv_en, bv_zh, bt = _ca_map.get(ca_verdict, (_prettify(ca_verdict), _prettify(ca_verdict), "neutral"))
            chips.append({
                "key": "bonds", "label_en": "Bonds vs stocks", "label_zh": "债股关系",
                "value_en": bv_en, "value_zh": bv_zh, "tone": bt,
            })

        # 5. credit (bonds.credit.distress_band + direction)
        credit = (bonds.get("credit") or {})
        band = (credit.get("distress_band") or "").lower()
        direction = (credit.get("direction") or "").lower()
        if band:
            # "tight" is the live distress_band vocabulary today (spec table only
            # named calm/stressed) — map it bilingually so ZH never shows raw EN.
            if band in ("calm", "tight") and "widen" in direction:
                _b_en, _b_zh = ("Calm", "平静") if band == "calm" else ("Tight", "偏紧")
                cv_en, cv_zh, ct = f"{_b_en}, but widening", f"{_b_zh}但在走宽", "warn"
            elif band == "calm":
                cv_en, cv_zh, ct = "Calm", "平静", "good"
            elif band == "tight":
                cv_en, cv_zh, ct = "Tight", "偏紧", "good"
            elif band == "stressed":
                cv_en, cv_zh, ct = "Stressed", "紧张", "bad"
            else:
                cv_en, cv_zh, ct = _prettify(band), _prettify(band), "neutral"
            chips.append({
                "key": "credit", "label_en": "Credit", "label_zh": "信用",
                "value_en": cv_en, "value_zh": cv_zh, "tone": ct,
            })

        # 6. driver (market_drivers.primary_label + direction)
        primary = mdr.get("primary_label") or (macro.get("market_drivers") or {}).get("primary_label") if isinstance(macro.get("market_drivers"), dict) else None
        if not primary and isinstance(state.get("macro"), dict):
            _mdr2 = state["macro"].get("market_drivers") or {}
            if isinstance(_mdr2, dict):
                primary = _mdr2.get("primary_label") or _mdr2.get("primary")
        direction_raw = (mdr.get("direction") or (state.get("macro", {}).get("market_drivers") or {}).get("direction") or "").lower() if isinstance(state.get("macro", {}).get("market_drivers"), dict) else ""
        _dir_suffix_en = {"down": " — down", "up": " — up"}.get(direction_raw, "")
        _dir_suffix_zh = {"down": " — 走弱", "up": " — 走强"}.get(direction_raw, "")
        if primary:
            chips.append({
                "key": "driver", "label_en": "What's moving markets", "label_zh": "当前主导",
                "value_en": str(primary) + _dir_suffix_en,
                "value_zh": str(primary) + _dir_suffix_zh,
                "tone": "info",
            })

    except Exception:  # noqa: BLE001 — never raises, never blocks
        pass
    return chips[:6]


def _lc(x) -> str:
    """Type-safe lowercase for enum reads: non-strings (floats, dicts, None)
    lower() to "" instead of raising inside the chip builders' fail-open try —
    a raised AttributeError silently costs every chip after it."""
    return x.lower() if isinstance(x, str) else ""


def _is_pending(x) -> bool:
    """True only for a real pending-quad value — None, NaN and '' are no-pending."""
    if x is None:
        return False
    if isinstance(x, float) and x != x:          # NaN
        return False
    return str(x).strip().lower() not in ("", "nan", "none")


def _kf_china(state: dict) -> list[dict]:
    """Build china key_facts chips (spec §6, china table)."""
    chips: list[dict] = []
    try:
        china = state.get("china") or {}
        hk = state.get("hk") or {}
        intel = state.get("china_intel") or {}
        policy_block = (intel.get("policy") or {}) if isinstance(intel.get("policy"), dict) else {}

        # 1. cn_regime
        quad_name = china.get("quad_name")
        if quad_name is not None:
            shifting = _is_pending(china.get("pending_quad"))
            v_en, v_zh, tone = _quad_display(quad_name, shifting)
            chips.append({
                "key": "cn_regime", "label_en": "China regime", "label_zh": "A股格局",
                "value_en": v_en, "value_zh": v_zh, "tone": tone,
            })

        # 2. policy — the corridor classifier's stance string. Live key is
        # `pboc_stance` ("easing"/"neutral"/"tightening"); `stance` exists but is
        # a nested DICT in the intel payload (the .lower() on it was the crash
        # that silently cost chips 2-6), so only string values are considered.
        impulse = (_lc(policy_block.get("pboc_stance"))
                   or _lc(policy_block.get("impulse"))
                   or _lc(policy_block.get("stance_label_en")))
        if impulse:
            _policy_map: dict[str, tuple[str, str, str]] = {
                "easing":     ("Cutting rates", "在降息", "info"),
                "tightening": ("Tightening",    "在收紧", "warn"),
            }
            pv_en, pv_zh, pt = "On hold", "按兵不动", "neutral"
            for k, v in _policy_map.items():
                if k in impulse:
                    pv_en, pv_zh, pt = v
                    break
            chips.append({
                "key": "policy", "label_en": "Policy", "label_zh": "政策",
                "value_en": pv_en, "value_zh": pv_zh, "tone": pt,
            })

        # 3. cn_money (liquidity_overlay from china block)
        liq = _lc(china.get("liquidity_overlay"))
        if liq:
            _liq_map2: dict[str, tuple[str, str, str]] = {
                "expand":   ("Expanding",  "扩张",   "good"),
                "contract": ("Tightening", "收紧",   "warn"),
            }
            lv2_en, lv2_zh, lt2 = "Neutral", "中性", "neutral"
            for k, v in _liq_map2.items():
                if liq.startswith(k):
                    lv2_en, lv2_zh, lt2 = v
                    break
            chips.append({
                "key": "cn_money", "label_en": "System money", "label_zh": "系统流动性",
                "value_en": lv2_en, "value_zh": lv2_zh, "tone": lt2,
            })

        # 4. hk_risk
        risk_state = _lc(hk.get("risk_state"))
        if risk_state:
            _hk_risk_map: dict[str, tuple[str, str, str]] = {
                "risk_on":  ("Risk-on",   "偏积极", "good"),
                "risk-on":  ("Risk-on",   "偏积极", "good"),
                "risk_off": ("Risk-off",  "避险",   "warn"),
                "risk-off": ("Risk-off",  "避险",   "warn"),
                "neutral":  ("Neutral",   "中性",   "neutral"),
            }
            hv_en, hv_zh, ht = _prettify(risk_state), _prettify(risk_state), "neutral"
            if risk_state in _hk_risk_map:
                hv_en, hv_zh, ht = _hk_risk_map[risk_state]
            chips.append({
                "key": "hk_risk", "label_en": "Hong Kong", "label_zh": "香港",
                "value_en": hv_en, "value_zh": hv_zh, "tone": ht,
            })

        # 5. peg — live values carry suffixes ("weak-side (outflow)"), so match
        # by substring, weak before strong so "weak-side" can never miss.
        peg_state = _lc(hk.get("peg_state"))
        if peg_state:
            pv_en, pv_zh, pt2 = _prettify(peg_state), _prettify(peg_state), "neutral"
            if "weak" in peg_state:
                pv_en, pv_zh, pt2 = "At weak edge — watching", "贴近弱方 — 需留意", "warn"
            elif "strong" in peg_state:
                pv_en, pv_zh, pt2 = "At strong edge", "贴近强方", "info"
            elif peg_state in ("normal", "mid") or "normal" in peg_state:
                pv_en, pv_zh, pt2 = "Steady", "稳定", "good"
            chips.append({
                "key": "peg", "label_en": "HK dollar", "label_zh": "港元",
                "value_en": pv_en, "value_zh": pv_zh, "tone": pt2,
            })

        # 6. cn_leader (top sector_rs by rank from china block)
        sector_rs = china.get("sector_rs")
        if isinstance(sector_rs, list) and sector_rs:
            top = sorted(sector_rs, key=lambda x: x.get("rank", 999))[0]
            leader_name = top.get("name") or top.get("display_name") or ""
            if leader_name:
                chips.append({
                    "key": "cn_leader", "label_en": "Leading sector", "label_zh": "领涨板块",
                    "value_en": leader_name, "value_zh": leader_name, "tone": "info",
                })

    except Exception:  # noqa: BLE001 — never raises, never blocks
        pass
    return chips[:6]


def _kf_btc(state: dict) -> list[dict]:
    """Build BTC key_facts chips (spec §6, btc table)."""
    chips: list[dict] = []
    try:
        btc = state.get("btc") or {}

        # 1. system (composite_state + alloc_optimal + override_active)
        comp_state = _lc(btc.get("composite_state")).upper()
        if comp_state:
            _sys_map: dict[str, tuple[str, str, str]] = {
                "ACCUMULATE": ("Accumulate",    "系统偏多",  "good"),
                "HOLD":       ("Hold",          "持有",      "neutral"),
                "NEUTRAL":    ("Hold",          "持有",      "neutral"),
                "DISTRIBUTE": ("Distribute",    "系统减持",  "warn"),
            }
            sv_en, sv_zh, st = _sys_map.get(comp_state, (_prettify(comp_state), _prettify(comp_state), "neutral"))
            alloc = btc.get("alloc_optimal")
            if alloc == 0:
                sv_en += " · allocation 0%"
                sv_zh += " · 仓位 0%"
                st = "bad"
            if btc.get("override_active"):
                sv_en += " (override)"
                sv_zh += "（人工覆盖）"
            chips.append({
                "key": "system", "label_en": "System stance", "label_zh": "系统姿态",
                "value_en": sv_en, "value_zh": sv_zh, "tone": st,
            })

        # 2. cycle (cycle_phase + cphase_pct)
        cycle_phase = _lc(btc.get("cycle_phase")) or _lc(btc.get("cphase_phase"))
        if cycle_phase:
            _cyc_map: dict[str, tuple[str, str, str]] = {
                "markup":       ("Early rise",    "上行早段",  "good"),
                "accumulation": ("Bottoming",     "筑底",      "info"),
                "distribution": ("Topping",       "筑顶",      "warn"),
                "markdown":     ("Late decline",  "下行后段",  "warn"),
            }
            cv_en, cv_zh, ct = _cyc_map.get(cycle_phase, (_prettify(cycle_phase), _prettify(cycle_phase), "neutral"))
            pct = btc.get("cphase_pct") or btc.get("cycle_pct")
            if pct is not None:
                try:
                    # cphase_pct is a 0..1 FRACTION in the signals parquet
                    # (0.783 = 78% through) — the raw int() read showed "~1%".
                    pf = float(pct)
                    if pf <= 1.5:
                        pf *= 100.0
                    pct_int = int(round(pf))
                    if 0 <= pct_int <= 100:
                        cv_en += f" · ~{pct_int}% through"
                        cv_zh += f" · 约{pct_int}%进度"
                except (TypeError, ValueError):
                    pass
            chips.append({
                "key": "cycle", "label_en": "Cycle clock", "label_zh": "周期时钟",
                "value_en": cv_en, "value_zh": cv_zh, "tone": ct,
            })

        # 3. value (valuation_state)
        val_state = _lc(btc.get("valuation_state"))
        if val_state:
            _val_map: dict[str, tuple[str, str, str]] = {
                "cheap": ("Cheap",     "偏便宜", "good"),
                "fair":  ("Fair",      "中性",   "neutral"),
                "rich":  ("Expensive", "偏贵",   "warn"),
            }
            vv_en, vv_zh, vt = _val_map.get(val_state, (_prettify(val_state), _prettify(val_state), "neutral"))
            chips.append({
                "key": "value", "label_en": "On-chain value", "label_zh": "链上估值",
                "value_en": vv_en, "value_zh": vv_zh, "tone": vt,
            })

        # 4. leverage — leverage_stress is a NUMERIC 0-100 score in the live
        # signals row (47.55 today), not an enum; the .lower() on it raised and
        # silently cost chips 4-6. Accept both forms: numeric score bands
        # (>=70 crowded / <=30 light) or a string enum, plus the funding_z gate.
        lev_raw = btc.get("leverage_stress")
        lev_str = _lc(lev_raw)
        lev_num = None
        if isinstance(lev_raw, (int, float)):
            try:
                lev_num = float(lev_raw)
            except (TypeError, ValueError):
                lev_num = None
        funding_z = btc.get("funding_z")
        if lev_str or lev_num is not None or funding_z is not None:
            crowded = (lev_str == "high" or (lev_num is not None and lev_num >= 70)
                       or (isinstance(funding_z, (int, float)) and funding_z > 2))
            light = (lev_str == "low" or (lev_num is not None and lev_num <= 30))
            if crowded:
                lv_en, lv_zh, lt = "Crowded longs", "多头拥挤", "warn"
            elif light:
                lv_en, lv_zh, lt = "Light", "清淡", "good"
            else:
                lv_en, lv_zh, lt = "Normal", "正常", "neutral"
            chips.append({
                "key": "leverage", "label_en": "Leverage", "label_zh": "杠杆",
                "value_en": lv_en, "value_zh": lv_zh, "tone": lt,
            })

        # 5. etf — live vocabulary is "accumulation"/"distribution", so match by
        # substring rather than the literal inflow/outflow spec words.
        etf_state = _lc(btc.get("etf_flow_state"))
        if etf_state:
            ev_en, ev_zh, et = _prettify(etf_state), _prettify(etf_state), "neutral"
            if "inflow" in etf_state or "accum" in etf_state:
                ev_en, ev_zh, et = "Money coming in", "资金流入", "good"
            elif "outflow" in etf_state or "distribut" in etf_state:
                ev_en, ev_zh, et = "Money leaving", "资金流出", "warn"
            elif "flat" in etf_state or "neutral" in etf_state:
                ev_en, ev_zh, et = "Flat", "持平", "neutral"
            chips.append({
                "key": "etf", "label_en": "ETF flows", "label_zh": "ETF资金",
                "value_en": ev_en, "value_zh": ev_zh, "tone": et,
            })

        # 6. liquidity (global_liq_regime)
        gliq = _lc(btc.get("global_liq_regime"))
        if gliq:
            _gliq_map: dict[str, tuple[str, str, str]] = {
                "expanding":   ("Expanding",   "扩张", "good"),
                "contracting": ("Contracting", "收缩", "warn"),
            }
            gv_en, gv_zh, gt = _gliq_map.get(gliq, ("Neutral", "中性", "neutral"))
            chips.append({
                "key": "liquidity", "label_en": "Global money", "label_zh": "全球流动性",
                "value_en": gv_en, "value_zh": gv_zh, "tone": gt,
            })

    except Exception:  # noqa: BLE001 — never raises, never blocks
        pass
    return chips[:6]


_LENS_KEY_FACTS: dict[str, object] = {
    "macro": _kf_macro,
    "china": _kf_china,
    "btc":   _kf_btc,
}


def _key_facts_for(lens: str, state: dict) -> list[dict]:
    """Dispatch to the per-lens key_facts builder. Returns [] on any exception."""
    try:
        fn = _LENS_KEY_FACTS.get(lens)
        if fn is None:
            return []
        return fn(state)  # type: ignore[operator]
    except Exception:  # noqa: BLE001
        return []


def render_markdown(brief: dict) -> str:
    """Human-readable rendering of a brief (for the CLI / a future panel)."""
    if not brief:
        return "_no brief_"
    if brief.get("degraded_reason") and not brief.get("regime_read"):
        return f"_master brief unavailable: {brief['degraded_reason']}_"
    L = [f"# Master brief — {brief.get('state_asof','?')} ({brief.get('model','?')})", ""]
    if brief.get("summary"):
        L += [f"**{brief['summary']}**", ""]
    if brief.get("tldr"):
        L += ["## The gist", *[f"- {x}" for x in brief["tldr"]], ""]
    if brief.get("regime_read"):
        L += ["## Regime read", brief["regime_read"], ""]
    if brief.get("conflicts"):
        L += ["## Conflicts", *[f"- {c}" for c in brief["conflicts"]], ""]
    if brief.get("rotation_check"):
        L += ["## Thesis check", brief["rotation_check"], ""]
    if brief.get("transmission"):
        L += ["## Transmission chains to watch", *[f"- {c}" for c in brief["transmission"]], ""]
    if brief.get("watch_items"):
        L += ["## Watch next", *[f"- {c}" for c in brief["watch_items"]], ""]
    L += [f"_confidence: {brief.get('confidence','?')} · context only, not a signal_"]
    return "\n".join(L)


_ZH_SCALARS = ("summary", "regime_read", "rotation_check")
_ZH_LISTS = ("conflicts", "transmission", "watch_items", "tldr")


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
            # small batches + generous cap: a Flash batch that hits max_tokens fails the
            # WHOLE batch closed (translate._translate_one_batch), and a long brief in one
            # 24-item batch blows the cap -> zero zh. Split it so any truncation is local.
            "max_chars": 2000, "max_tokens": 8000, "batch_size": 6,
        }
        zh_list = _tr.translate_to_zh(texts, tcfg)
        if not zh_list or all(x is None for x in zh_list):
            return
        zh: dict = {"summary": None, "regime_read": None, "rotation_check": None,
                    "tldr": [None] * len(brief.get("tldr") or []),
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


def run(persist: bool = True, root: Path | None = None, force: bool = False,
        lens: str = "macro") -> dict | None:
    """Gather state -> synthesize -> persist data/regime/<out> + site/<out> for one
    LENS. Returns the brief, or None when disabled (unless `force`, for on-demand/CLI
    use) or the lens is unknown. NEVER raises into the pipeline."""
    cfg = _cfg()
    if not force and not cfg.get("enabled", False):
        return None
    spec = LENSES.get(lens)
    if spec is None:
        log.warning("master_brain: unknown lens %r", lens)
        return None
    try:
        root = Path(root) if root else config.ROOT
        # Interval gate — only regenerate every N days (1..7). When the existing brief
        # is younger than the interval, skip the (paid) LLM call and KEEP the prior
        # brief live: the committed data/regime/<out> + site/<out> are left untouched
        # so the dashboard deploys the previous note verbatim. `force` (CLI/on-demand)
        # always bypasses the gate. Anchored off data/regime (the canonical write
        # target); a missing/unparseable generated_at falls through to regeneration.
        if not force:
            interval = _interval_for(lens, cfg)
            if interval > 1:
                prev = _read_json(root / "data" / "regime" / spec["out"])
                age = _brief_age_days(prev)
                if age is not None and age < interval:
                    log.info("master_brain: lens=%s brief is %.1fd old (< %dd interval) "
                             "— skipping regen, keeping prior brief", lens, age, interval)
                    return prev
        state = spec["state_fn"](root)
        brief = synthesize(state, cfg, lens=lens, root=root)
        # ADB-R9: additive optional keys (schema: master_brief.v2)
        brief["nw_context_used"] = bool(state.get("neural_web"))
        _nw = state.get("neural_web") or {}
        _cortex = _nw.get("cortex") or {}
        brief["cortex_status"] = (
            _cortex.get("status", "absent") if not _cortex.get("absent") else "absent"
        )
        # spec §7: expose the lens interval so the UI can show "Updated every N days"
        brief["refresh_days"] = _interval_for(lens, cfg)
        # spec §6: deterministic chip rail — bilingual at build, never sent to translator
        try:
            brief["key_facts"] = _key_facts_for(lens, state)
        except Exception:  # noqa: BLE001 — additive, never fatal
            brief["key_facts"] = []
        _translate_brief(brief, cfg)          # attach brief['zh'] for the 中文 toggle
        if persist:
            try:
                payload = json.dumps(brief, indent=2, default=str)
                out = root / "data" / "regime" / spec["out"]
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(payload)
                site = root / "site"          # client-fetched by the dashboard panel
                if site.is_dir():
                    (site / spec["out"]).write_text(payload)
            except Exception as e:  # noqa: BLE001
                log.warning("master_brief persist failed (lens=%s: %s)", lens, e)
        if lens == "macro":                   # producer: append the brain's own leans (macro only)
            _append_ledger(brief, root)
        return brief
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("master_brain run failed (lens=%s: %s)", lens, e)
        return None


def run_all(persist: bool = True, root: Path | None = None,
            force: bool = False) -> dict[str, dict | None]:
    """Run every configured lens (master_brain.lenses, default macro+china+btc).
    Returns {lens: brief}. Disabled (and not forced) -> {} . NEVER raises."""
    cfg = _cfg()
    if not force and not cfg.get("enabled", False):
        return {}
    lenses = cfg.get("lenses") or list(LENSES.keys())
    out: dict[str, dict | None] = {}
    for lens in lenses:
        if lens in LENSES:
            out[lens] = run(persist=persist, root=root, force=force, lens=lens)
        else:
            log.warning("master_brain: skipping unknown lens %r in config", lens)
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    logging.basicConfig(level=logging.INFO)
    argv = sys.argv[1:]
    force = "--force" in argv                 # ad-hoc run even when enabled is false
    want = [a for a in argv if a in LENSES]   # optional explicit lens(es): macro/china/btc
    results = ({ln: run(persist=True, force=force, lens=ln) for ln in want}
               if want else run_all(persist=True, force=force))
    if not results:
        print("master_brain disabled — set master_brain.enabled: true, or pass --force")
    for ln, b in results.items():
        print(f"\n===== lens: {ln} =====")
        print(render_markdown(b) if b else "(none)")
        if b and b.get("degraded_reason"):
            print(f"[degraded: {b['degraded_reason']}]")
