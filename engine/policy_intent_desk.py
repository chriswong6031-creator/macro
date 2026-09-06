"""Policy Intent Desk — the accountable, realpolitik LLM layer on the Fed/Admin intel.

LEAF · GATED · DEFAULT-OFF-WITHOUT-KEY · NEVER-SCORED. This is the generative cousin of
data/policy/intel.json (the hand-curated, source-grounded substrate behind Fed & Policy
Watch). Where that file holds FACTS + a static falsifiable-prediction ledger, this desk
runs an LLM over that substrate + the live market state and emits FRESH, dated,
FALSIFIABLE intent leans — each mapped to a tradable proxy ticker so the engine can
derive a machine-checkable predicate and score it later.

It reuses the exact accountability chassis as engine.ai_desk:
  realpolitik analyst (LLM) → engine-derived falsifier + check-by date →
  append-only ledger (data/policy_intent/theses.jsonl) → scorer → track record.

DISCIPLINE (mirrors ai_desk / master_brain):
  * CONTEXT-ONLY — a lean is NEVER a size, weight, or order; nothing in axes / regime /
    conditions imports this. It writes a SEPARATE artifact (site/policy_intent.json).
  * REALPOLITIK, NON-PARTISAN — reason from interests / revealed preference, not politics.
  * GROUNDED — reason ONLY over the provided intel + market state; never fabricate facts,
    levels, or events; carry the substrate's FACT/INFERENCE/PRIOR/THEORY labels.
  * ACCOUNTABLE — the MODEL authors the judgement; the ENGINE derives the falsifier from
    (subject-proxy, lean, horizon), so every kept lean is scorable (or marked 'soft').
  * FIREWALLED + graceful — needs DEEPSEEK_API_KEY; absent the key / disabled / no intel,
    returns a degraded record (or None) and NEVER raises into the pipeline.

Runs on DeepSeek V4 Pro via master_brain's Anthropic-compatible client by default.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled
from lib import config
from engine import desk_ledger as _ledger_law       # run-scoped ids + immutable appends
from engine import master_brain as _mb              # reuse the DeepSeek/Anthropic client
from engine import ai_desk as _desk                 # reuse _level_asof / _check_by
from engine import ai_desk_scorer as _scorer        # reuse the predicate evaluators
from engine.catalyst_tone import _extract_json      # shared tolerant JSON parser
from engine.regime_label import quad_label          # regime stamp → by_regime track record

log = logging.getLogger(__name__)

SCHEMA = "policy_intent_desk.v1"
DISCLAIMER = (
    "Policy intent desk — realpolitik, context only, never scored or sized. Each lean is "
    "a fallible, checkable judgement (proxy vs SPY, with a check-by date), not a trade "
    "or a position size. Intent is inferred from interests; treat it as a hypothesis with "
    "a track record, not an oracle.")
DISCLAIMER_ZH = (
    "意图台 —— 现实政治、仅供参考，从不评分或定仓。每条判断都是可检验、会出错的判断"
    "（代理标的 vs SPY，附核查日期），并非交易或仓位大小。意图由利益推断而来；请将其"
    "视为有战绩记录的假设，而非神谕。")

_LEANS = ("overweight", "underweight", "avoid")
_CONVICTIONS = ("low", "medium", "high")
_BENCH = "SPY"

# Proxy tickers the desk may use as a subject. SCORABLE = present in data/yahoo (the
# falsifier can be evaluated vs SPY). SOFT = thematically relevant but no local price
# series → logged but never scored (honest, never fudged).
_SCORABLE = {"SMH", "SOXX", "XLF", "KBE", "XLE", "XOP", "TLT", "SMR", "OKLO",
             "XLK", "XLU", "XLI", "XLV", "XLY", "XLP", "XLB", "XLRE", "XLC", "IWM", "GLD"}
_SOFT = {"ITA", "XAR", "PPA", "SHLD", "URA", "URNM", "CCJ", "REMX", "MP", "BIL", "SHV", "UUP", "IBIT"}
_ALLOWED = _SCORABLE | _SOFT
# subject name the LLM uses -> the actual cached price ticker (data/yahoo). GLD has no
# local series; gold futures GC_F does, so a gold lean stays gradeable, not phantom-expired.
_ALIAS = {"GLD": "GC_F"}
# CORRELATED SURROGATES — a soft proxy (no local price series) mapped to a scorable cousin,
# so the highest-conviction longest-horizon themes (defense, nuclear/uranium, rare-earths)
# get GRADED instead of silently expiring. The surrogate is broader (defense ⊂ industrials),
# so a hit/miss is WEAKER evidence than a direct one — flagged via='correlated', graded on a
# wider threshold, and the track record keeps direct vs surrogate hit-rates separate. The
# cash/dollar/bitcoin softs (BIL/SHV/UUP/IBIT) have no equity surrogate → stay soft.
_SOFT_PROXY = {
    "ITA": "XLI", "XAR": "XLI", "PPA": "XLI", "SHLD": "XLI",     # defense → industrials
    "URA": "XLU", "URNM": "XLU", "CCJ": "XLU",                   # uranium / nuclear → utilities
    "REMX": "XLB", "MP": "XLB",                                  # rare earths → materials
}


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def _cfg() -> dict:
    base = {
        "enabled": False,                   # chassis convention: off unless config enables it
        "api_key_env": "DEEPSEEK_API_KEY",
        "llm_base_url": "https://api.deepseek.com/anthropic",
        "llm_model": "deepseek-v4-pro",
        "max_tokens": 8000,
        "interval_days": 3,                 # policy-shock W1-D: 3-day cadence (was 7)
        "max_theses": 5,
        "default_horizon_d": 40,            # policy horizons are longer than flow
        "falsifier_defaults": {"rel_return": 0.05},
    }
    try:
        base.update(config.load().get("policy_intent_desk", {}) or {})
    except Exception:  # noqa: BLE001 — never let config IO break the pipeline
        pass
    return base


def enabled() -> bool:
    return bool(_cfg().get("enabled", False))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# falsifier derivation (mirrors ai_desk._derive_check, proxy-vs-SPY)
# --------------------------------------------------------------------------- #
def _resolve_subject(subject: str):
    """-> (ticker, vs, kind, via). kind in {'rel_return','soft'}; via in {'direct','correlated','soft'}."""
    t = (subject or "").strip().upper()
    if t in _SCORABLE:
        return _ALIAS.get(t, t), _BENCH, "rel_return", "direct"   # resolve to the cached price ticker
    if t in _SOFT_PROXY:
        return _SOFT_PROXY[t], _BENCH, "rel_return", "correlated"  # gradeable via a correlated cousin
    if t in _SOFT:
        return t, None, "soft", "soft"
    return None, None, "soft", "soft"


def _derive_check(subject: str, lean: str, horizon: int, cfg: dict) -> dict:
    thr = float((cfg.get("falsifier_defaults", {}) or {}).get("rel_return", 0.05))
    ticker, vs, kind, via = _resolve_subject(subject)
    if kind == "rel_return":
        # a correlated surrogate is noisier than a direct proxy → widen the threshold so we
        # don't false-fail a defense lean on industrials' idiosyncratic wobble.
        eff_thr = thr * (1.6 if via == "correlated" else 1.0)
        if lean == "overweight":
            op, threshold = "<", -eff_thr        # FALSE if it underperforms SPY by >= thr
        elif lean in ("underweight", "avoid"):
            op, threshold = ">", eff_thr         # FALSE if it outperforms SPY by >= thr
        else:
            return {"kind": "soft", "via": "soft", "reason": f"lean '{lean}' has no relative-return rule"}
        check = {"kind": "rel_return", "subject_ticker": ticker, "vs": vs, "via": via,
                 "op": op, "threshold": threshold, "horizon_d": horizon}
        if via == "correlated":
            check["surrogate_of"] = (subject or "").strip().upper()
            check["note"] = f"graded via correlated surrogate {ticker} (no local series for {check['surrogate_of']})"
        return check
    return {"kind": "soft", "via": "soft",
            "reason": f"'{subject}' not a scorable proxy (no local price series, no correlated surrogate)"}


def _build_thesis(t: dict, i: int, asof, cfg: dict, run_token: str = "") -> dict | None:
    if not isinstance(t, dict):
        return None
    subject = str(t.get("subject") or "").strip().upper()
    lean = str(t.get("lean") or "").strip().lower()
    actor = str(t.get("actor") or "").strip().lower()      # 'fed' | 'admin' (context)
    if subject not in _ALLOWED or lean not in _LEANS:
        return None
    try:
        horizon = int(t.get("horizon_d") or cfg.get("default_horizon_d", 40))
    except Exception:  # noqa: BLE001
        horizon = int(cfg.get("default_horizon_d", 40))
    horizon = max(10, min(126, horizon))
    conv = str(t.get("conviction") or "low").strip().lower()
    if conv not in _CONVICTIONS:
        conv = "low"
    return {
        "id": f"{asof}-{run_token}-{i + 1}" if run_token else f"{asof}-{i + 1}",
        "actor": actor if actor in ("fed", "admin") else "admin",
        "subject": subject,
        "lean": lean,
        "conviction": conv,
        "horizon_d": horizon,
        "thesis": t.get("thesis"),
        "thesis_zh": t.get("thesis_zh"),
        "evidence": [str(e) for e in (t.get("evidence") or []) if e],
        "dissent": t.get("dissent"),
        "dissent_zh": t.get("dissent_zh"),
        "falsifier": {"text": t.get("falsifier_text"),
                      "text_zh": t.get("falsifier_text_zh"),
                      "check": _derive_check(subject, lean, horizon, cfg)},
        "check_by": _desk._check_by(asof, horizon),
    }


# --------------------------------------------------------------------------- #
# state gathering
# --------------------------------------------------------------------------- #
def gather_state(root=None) -> dict | None:
    root = Path(root) if root else config.ROOT
    intel = _read_json(root / "data" / "policy" / "intel.json")
    if not intel:
        return None
    latest = _read_json(root / "data" / "regime" / "latest.json") or {}
    cond = latest.get("conditions") or {}
    market = {
        "quad": latest.get("quad_name") or latest.get("quad"),
        "growth_score": latest.get("growth_score"),
        "inflation_score": latest.get("inflation_score"),
        "fed_path_gap": (latest.get("fed_path") or {}).get("gap"),
        "market_driver": (latest.get("market_drivers") or {}).get("verdict"),
        "turning_point": bool((latest.get("turning_point") or {}).get("present")),
        "drawdown_risk": (cond.get("drawdown_risk") or {}).get("score") if isinstance(cond.get("drawdown_risk"), dict) else None,
    }
    return {
        # as_of = the RUN DATE (when the lean is made) so thesis ids + check-by dates are
        # unique per run and accrue forward. intel_asof carries the substrate's vintage.
        "as_of": str(date.today()),
        "intel_asof": intel.get("as_of"),
        "thesis": (intel.get("thesis") or {}).get("en"),
        "theaters": [{"title": (th.get("title_en") or ""), "basis": th.get("basis"),
                      "capital": th.get("capital_en")} for th in (intel.get("administration", {}).get("theaters") or [])],
        "rotation_targeted": [{"theme": r.get("theme_en"), "proxies": r.get("proxies"),
                               "basis": r.get("basis")} for r in (intel.get("rotation", {}).get("targeted") or [])],
        "open_predictions": [p.get("text_en") for p in (intel.get("predictions") or []) if p.get("status") == "open"][:12],
        "market": market,
        "allowed_subjects": sorted(_ALLOWED),
        "scorable_subjects": sorted(_SCORABLE),
        "track_record": _read_json(root / "data" / "policy_intent" / "track_record.json"),
    }


# --------------------------------------------------------------------------- #
# the analyst (single structured DeepSeek call)
# --------------------------------------------------------------------------- #
_SCHEMA_TAIL = (
    "Return ONLY a JSON object (no markdown fences) with keys:\n"
    "  regime_context: string — 1-2 sentences on the policy regime + where the consensus "
    "narrative diverges from revealed interest (grounded; no invented numbers).\n"
    "  regime_context_zh: string — a faithful Simplified-Chinese (简体中文) translation of "
    "regime_context. Preserve tickers, acronyms and proper nouns; translate the rest.\n"
    "  theses: array of 0..N objects (omit rather than pad), each:\n"
    "     actor: \"fed\" or \"admin\" — whose intent drives it.\n"
    "     subject: a TICKER from allowed_subjects (PREFER scorable_subjects so it can be "
    "graded). The lean is proxy-vs-SPY.\n"
    "     lean: \"overweight\" | \"underweight\" | \"avoid\" — a DIRECTION, never a size.\n"
    "     conviction: \"low\" | \"medium\" | \"high\" — modest; default low.\n"
    "     horizon_d: integer trading days, 10..126.\n"
    "     thesis: string — the realpolitik reasoning (which policy lever / interest).\n"
    "     thesis_zh: string — faithful 简体中文 translation of thesis (preserve tickers).\n"
    "     evidence: array of strings — cite the specific theater / lever / prediction.\n"
    "     dissent: string — the single strongest contrary case.\n"
    "     dissent_zh: string — faithful 简体中文 translation of dissent (preserve tickers).\n"
    "     falsifier_text: string — one concrete condition that would prove it wrong, "
    "phrased as the plain condition itself (e.g. 'XLE lags SPY by 5% before the check-by "
    "date'). This text is shown to users under a 'Changes this read' label: never write "
    "the words 'falsified', 'falsify' or 'refuted' in it.\n"
    "     falsifier_text_zh: string — faithful 简体中文 translation of falsifier_text. Same "
    "display rule: write it as a plain 改判条件-style condition, never with the word 证伪.\n"
    "  confidence: \"low\" | \"medium\" | \"high\".\n"
    "Every *_zh field is REQUIRED and must be natural Simplified Chinese, not English."
)

_SYSTEM = (
    "You are a cold, interest-driven REALPOLITIK macro-policy desk for a top-down trader. "
    "You are handed a source-grounded intelligence substrate on the Fed (Warsh) and the "
    "Administration (Trump/Bessent) — facts, geopolitical theaters, a capital-rotation "
    "map, and a falsifiable prediction ledger — plus the live market regime state. Your "
    "job: turn revealed POLICY INTENT into a SHORT set of accountable, FALSIFIABLE, "
    "tradable leans.\n\n"
    "STANCE: analyze by interests, incentives, leverage and revealed preference — NOT "
    "partisan or normative politics. Weed out spin; where the consensus narrative diverges "
    "from revealed interest, say so and trade the revealed interest.\n\n"
    "RULES:\n"
    "- Reason ONLY over the provided JSON (intel + market state) + well-known market "
    "structure. NEVER fabricate a fact, level, or event. Honor the substrate's "
    "FACT/INFERENCE/PRIOR/THEORY labels — do NOT trade a THEORY (e.g. the Mar-a-Lago "
    "Accord) as if it were policy.\n"
    "- Each lean maps a policy thesis to a SUBJECT ticker from allowed_subjects, expressed "
    "as a direction vs SPY. Prefer scorable_subjects so the call is machine-graded.\n"
    "- NEVER give a size, weight, dollar amount, or trade. Give a DIRECTION + what would "
    "invalidate it. Every thesis needs an honest DISSENT and a CONCRETE falsifier.\n"
    "- If track_record is present, CALIBRATE conviction to it (past misses -> lean lower).\n"
    "- Be honest about fragility: ceasefires, tariff truces and pending court rulings are "
    "two-sided. Small sample — stay modest. This note is graded against reality.\n\n"
    + _SCHEMA_TAIL
)


def _build_user(state: dict) -> str:
    return "POLICY + MARKET STATE (analyze; do not repeat back):\n" + json.dumps(state, default=str)[:14000]


def synthesize(state: dict, cfg: dict | None = None, call=None) -> dict:
    """Run the analyst over a gathered state. Always returns a record (degraded fields
    flagged); never raises. `call` is injectable (defaults to master_brain._call_model)
    so tests run without an API key."""
    cfg = cfg or _cfg()
    asof = state.get("as_of")
    brief = {
        "schema": SCHEMA, "is_context_only": True, "lens": "realpolitik",
        "generated_at": _now_iso(), "state_asof": asof,
        "model": cfg.get("llm_model", "deepseek-v4-pro"),
        "regime_context": None, "regime_context_zh": None, "theses": [],
        "track_record": state.get("track_record"),
        "confidence": "low", "raw_text": None, "degraded_reason": None,
        "disclaimer": DISCLAIMER, "disclaimer_zh": DISCLAIMER_ZH,
        # #41 badge honesty: the desk's conviction badge carries an honest provenance passport
        # (measured·n / accruing·n=0), derived from the outcome spine, so a cold lean can't read
        # as an earned edge. Set here so every return path (incl. degraded) carries it.
        "passport": _desk._desk_passport("policy_intent"),
    }
    reply, reason = (call or _mb._call_model)(
        _SYSTEM, _build_user(state), {**(cfg or {}), "usage_stage": "policy-desk"})
    brief["raw_text"] = reply
    if reply is None:
        brief["degraded_reason"] = reason
        return brief
    parsed = _extract_json(reply)
    if not isinstance(parsed, dict):
        brief["degraded_reason"] = reason or "unparseable_reply"
        return brief
    brief["regime_context"] = parsed.get("regime_context")
    brief["regime_context_zh"] = parsed.get("regime_context_zh")
    conf = str(parsed.get("confidence") or "low").strip().lower()
    brief["confidence"] = conf if conf in _CONVICTIONS else "low"
    raw = parsed.get("theses") if isinstance(parsed.get("theses"), list) else []
    # per-run token (full YYYYMMDDHHMMSS from generated_at) so re-runs can't collide ids.
    # The original HHMMSS slice still collided when two different run DAYS shared a stale
    # state_asof and fired at the same wall-clock second (engine.desk_ledger).
    run_token = _ledger_law.run_token(brief.get("generated_at"))
    theses = []
    for t in raw[: int(cfg.get("max_theses", 5))]:
        th = _build_thesis(t, len(theses), asof, cfg, run_token=run_token)
        if th is not None:
            theses.append(th)
    brief["theses"] = theses
    if reason:
        brief["degraded_reason"] = reason
    return brief


# --------------------------------------------------------------------------- #
# append-only ledger + persist
# --------------------------------------------------------------------------- #
def _append_ledger(brief: dict, root) -> None:
    # House law: nightly is the SOLE advancer of data/ forward ledgers. This module
    # also runs on render.yml's express lane (step `policy_intent`, DEEPSEEK live,
    # COLLECT_LANE unset) — engine-render.yml excludes it for exactly this reason.
    # Ungated, an off-lane run minted fresh thesis ids (per-run token) into a ledger
    # the lane never commits, so the baked page asserted accrual the committed
    # ledger did not contain (#2598 class). Gate-first, before any arg evaluation.
    if not _ledger_advance_enabled():
        return
    theses = brief.get("theses") or []
    if not theses:
        return
    try:
        d = Path(root) / "data" / "policy_intent"
        d.mkdir(parents=True, exist_ok=True)
        asof = brief.get("state_asof")
        regime = quad_label(root)
        rows = []
        for t in theses:
            check = (t.get("falsifier") or {}).get("check") or {}
            entry = {}
            for key in ("subject_ticker", "vs"):
                tk = check.get(key)
                if tk:
                    lv = _desk._level_asof(tk, root, asof)
                    if lv is not None:
                        entry[tk] = lv
            rows.append({
                "id": t["id"], "logged_at": brief["generated_at"], "state_asof": asof,
                "actor": t.get("actor"), "subject": t["subject"], "lean": t["lean"],
                "conviction": t["conviction"], "horizon_d": t["horizon_d"],
                "falsifier": t["falsifier"], "check_by": t["check_by"],
                "entry_levels": entry, "regime": regime,
                "status": "open", "scored_at": None, "outcome": None, "realized": None,
            })
        # Immutability gate: a logged thesis is pre-registered — an id already in the
        # ledger is refused loudly, never rewritten (engine.desk_ledger).
        rows = _ledger_law.reject_existing_ids(d / "theses.jsonl", rows, "policy_intent")
        with open(d / "theses.jsonl", "a") as fh:
            for row in rows:
                fh.write(json.dumps(row, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        log.warning("policy_intent ledger append failed: %s", e)


def _persist(brief: dict, root) -> None:
    try:
        out = Path(root) / "data" / "regime" / "policy_intent.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(brief, indent=2, default=str))
        site = Path(root) / "site"
        if site.is_dir():
            pub = {k: v for k, v in brief.items() if k != "raw_text"}
            (site / "policy_intent.json").write_text(json.dumps(pub, indent=2, default=str))
    except Exception as e:  # noqa: BLE001
        log.warning("policy_intent persist failed: %s", e)


def _brief_age_days(prev) -> float | None:
    try:
        g = (prev or {}).get("generated_at")
        return (datetime.now(timezone.utc) - datetime.fromisoformat(g)).total_seconds() / 86400.0
    except Exception:  # noqa: BLE001
        return None


def run(persist: bool = True, root=None, force: bool = False, call=None) -> dict | None:
    """Gather → synthesize → persist + append the ledger. None when disabled (unless
    force) or no intel substrate present. NEVER raises."""
    cfg = _cfg()
    if not force and not cfg.get("enabled", False):
        return None
    try:
        root = Path(root) if root else config.ROOT
        if not force:
            try:
                interval = max(1, min(7, int(cfg.get("interval_days", 7))))
            except Exception:  # noqa: BLE001
                interval = 7
            if interval > 1:
                prev = _read_json(Path(root) / "data" / "regime" / "policy_intent.json")
                age = _brief_age_days(prev)
                if age is not None and age < interval:
                    log.info("policy_intent: note %.1fd old (< %dd) — keeping prior", age, interval)
                    return prev
        state = gather_state(root)
        if state is None:
            log.info("policy_intent: no data/policy/intel.json — nothing to brief")
            return None
        brief = synthesize(state, cfg, call=call)
        if persist:
            _persist(brief, root)
            _append_ledger(brief, root)
        return brief
    except Exception as e:  # noqa: BLE001
        log.error("policy_intent run failed: %s", e)
        return None


# --------------------------------------------------------------------------- #
# scorer — reuse ai_desk_scorer's predicate evaluators against our own ledger
# --------------------------------------------------------------------------- #
def _read_ledger(p: Path) -> dict:
    out = {}
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    r = json.loads(line)
                    out[r.get("id")] = r          # last write per id wins
                except ValueError:
                    pass
    return out


def score(root=None, today=None) -> dict:
    """Resolve open leans whose check-by has passed (reusing ai_desk_scorer evaluators),
    append scored rows, and write the rolling track record. NEVER raises.

    Lane-gated whole: scored.jsonl is a forward ledger (nightly is the sole advancer)
    and track_record.json is derived from it in the same pass — an off-lane render
    scoring early would ship a track record the committed ledgers can't reproduce."""
    if not _ledger_advance_enabled():
        return {"schema": SCHEMA, "scored_total": 0, "open": 0,
                "overall": {"n": 0}, "calibration_note": "off-lane: scorer not run"}
    try:
        root = Path(root) if root else config.ROOT
        today = today or date.today()
        d = root / "data" / "policy_intent"
        d.mkdir(parents=True, exist_ok=True)
        led = _read_ledger(d / "theses.jsonl")
        scored = _read_ledger(d / "scored.jsonl")
        new = []
        for tid, row in led.items():
            if tid in scored:
                continue
            try:
                s = _scorer._score_one(row, root, today)
            except Exception as e:  # noqa: BLE001
                log.warning("policy_intent score_one failed for %s: %s", tid, e)
                s = None
            if s:
                new.append(s)
        if new:
            try:
                with open(d / "scored.jsonl", "a") as fh:
                    for r in new:
                        fh.write(json.dumps(r, default=str) + "\n")
            except Exception as e:  # noqa: BLE001
                log.warning("policy_intent scored append failed: %s", e)
        all_scored = list(scored.values()) + new
        tr = _scorer._aggregate(all_scored, led, today)
        try:
            (d / "track_record.json").write_text(json.dumps(tr, indent=2, default=str))
        except Exception as e:  # noqa: BLE001
            log.warning("policy_intent track_record write failed: %s", e)
        return tr
    except Exception as e:  # noqa: BLE001 — additive overlay, never fatal
        log.error("policy_intent score failed: %s", e)
        return {"schema": SCHEMA, "scored_total": 0, "open": 0,
                "overall": {"n": 0}, "calibration_note": "scorer error"}



# --------------------------------------------------------------------------- #
# deterministic policy lifecycle state machine (NO LLM) — MO-DELTA-032          #
# Per-item state projection ledger over the operator-signed substrate. Never    #
# imports synthesize/_SYSTEM/call/master_brain. Nightly-gated ingest; pure fold.#
# --------------------------------------------------------------------------- #
import hashlib
import logging
import json as _json
from pathlib import Path

log = logging.getLogger(__name__)

LIFECYCLE_SCHEMA = "policy_lifecycle.v1"
LIFECYCLE_STAGES = ("proposed", "passed", "in_force", "enforced")
LIFECYCLE_TERMINAL = ("withdrawn", "struck_down", "superseded")
LIFECYCLE_NULLS = ("unknown", "no_coverage", "rights_suppressed")
LIFECYCLE_EVENT_TYPES = LIFECYCLE_STAGES + LIFECYCLE_TERMINAL + ("correction", "reinstated")

_STAGE_RANK = {s: i for i, s in enumerate(LIFECYCLE_STAGES)}


def _lifecycle_source_label(url):
    from urllib.parse import urlparse
    host = urlparse(str(url or "")).netloc.lower().split(":", 1)[0]
    host = host.removeprefix("www.")
    known = {
        "federalreserve.gov": "Federal Reserve",
        "home.treasury.gov": "U.S. Treasury",
        "treasury.gov": "U.S. Treasury",
        "whitehouse.gov": "White House",
        "energy.gov": "Energy Department",
        "sec.gov": "SEC",
        "nato.int": "NATO",
        "congress.gov": "Congress",
        "supremecourt.gov": "Supreme Court",
        "cmegroup.com": "CME Group",
        "federalregister.gov": "Federal Register",
    }
    return known.get(host, host or "source")


def lifecycle_events(root=None) -> list[dict]:
    """Read the append-only lifecycle event store. Missing file -> []. Never raises."""
    try:
        p = Path(root) / "data" / "policy_lifecycle" / "events.jsonl" if root else Path("data/policy_lifecycle/events.jsonl")
        if not p.exists():
            return []
        rows = []
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(_json.loads(line))
            except Exception as e:  # noqa: BLE001
                log.warning("policy_lifecycle: skipping malformed event line: %s", e)
        return rows
    except Exception as e:  # noqa: BLE001
        log.warning("policy_lifecycle: read failed: %s", e)
        return []


def ingest_lifecycle(root=None) -> int:
    """Deterministic, idempotent ingest from the operator-signed substrate into the
    append-only event store. Nightly-gated. NEVER raises. Never LLM-derived."""
    if not _ledger_advance_enabled():
        return 0
    try:
        root_path = Path(root) if root else Path(".")
        intel_path = root_path / "data" / "policy" / "intel.json"
        if not intel_path.exists():
            return 0
        intel = _json.loads(intel_path.read_text())
        raw_events = intel.get("policy_lifecycle")
        if not raw_events:
            return 0
        rejects = 0
        candidates = []
        for ev in raw_events:
            if not isinstance(ev, dict):
                rejects += 1
                continue
            typ = ev.get("type")
            item_id = ev.get("item_id")
            event_date = ev.get("event_date")
            source = ev.get("source") or {}
            if typ not in LIFECYCLE_EVENT_TYPES or not item_id or not event_date or not source.get("url"):
                rejects += 1
                continue
            candidates.append(ev)
        if rejects:
            log.warning("policy_lifecycle: rejected %d malformed substrate rows", rejects)
        if not candidates:
            return 0
        store_dir = root_path / "data" / "policy_lifecycle"
        store_dir.mkdir(parents=True, exist_ok=True)
        store_path = store_dir / "events.jsonl"
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for ev in candidates:
            key = "|".join([
                str(ev.get("item_id")), str(ev.get("type")),
                str(ev.get("event_date")), str((ev.get("source") or {}).get("url")),
            ])
            event_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
            row = dict(ev)
            row["event_id"] = event_id
            row["id"] = event_id  # desk_ledger.reject_existing_ids keys on "id"
            row["logged_at"] = now
            row["schema"] = LIFECYCLE_SCHEMA
            row.setdefault("corrects", None)
            row.setdefault("reason", None)
            rows.append(row)
        rows = _ledger_law.reject_existing_ids(store_path, rows, "policy_lifecycle")
        with open(store_path, "a") as fh:
            for row in rows:
                fh.write(_json.dumps(row, default=str) + "\n")
        return len(rows)
    except Exception as e:  # noqa: BLE001
        log.warning("policy_lifecycle: ingest failed: %s", e)
        return 0


def fold_lifecycle(events: list[dict], registry: list[dict]) -> list[dict]:
    """Pure, no IO, no clock. Folds a per-item event list against a registry of
    tracked items into the frozen per-item state projection."""
    by_item: dict[str, list[dict]] = {}
    for ev in events or []:
        by_item.setdefault(ev.get("item_id"), []).append(ev)

    out = []
    for reg in registry or []:
        item_id = reg.get("id")
        item_events = sorted(
            by_item.get(item_id, []),
            key=lambda e: (
                e.get("known_at") or "",
                _STAGE_RANK.get(e.get("type"), -1),
                e.get("event_id") or "",
            ),
        )
        if not item_events:
            out.append({
                "id": item_id,
                "title_en": reg.get("title_en"), "title_zh": reg.get("title_zh"),
                "jurisdiction": reg.get("jurisdiction"),
                "jurisdiction_en": reg.get("jurisdiction_en"), "jurisdiction_zh": reg.get("jurisdiction_zh"),
                "state": "unknown", "stage_rank": None, "reached": [], "gaps": [],
                "state_asof": None, "known_at": None, "source": None,
                "next_step": None, "stalled": False, "corrected": False,
                "conflict": False, "why": "no_document",
            })
            continue

        state = "unknown"
        stage_rank = None
        reached: list[str] = []
        gaps: list[str] = []
        state_asof = None
        known_at = None
        source = None
        corrected = False
        conflict = False
        terminal_frozen = False
        pre_terminal = None  # snapshot to restore on reinstated

        for ev in item_events:
            typ = ev.get("type")
            if typ == "correction":
                corrected = True
                # re-derive nothing special here beyond marking corrected; the
                # corrected event's own effect (if any ladder/terminal payload
                # is embedded) is handled by its own type below when present.
                continue
            if typ == "reinstated":
                if terminal_frozen and pre_terminal is not None:
                    state = pre_terminal["state"]
                    stage_rank = pre_terminal["stage_rank"]
                    reached = list(pre_terminal["reached"])
                    state_asof = pre_terminal["state_asof"]
                    known_at = pre_terminal["known_at"]
                    source = pre_terminal["source"]
                terminal_frozen = False
                continue
            if terminal_frozen:
                # later ordinary events do not resurrect a terminal state
                continue
            if typ in LIFECYCLE_TERMINAL:
                pre_terminal = {
                    "state": state, "stage_rank": stage_rank, "reached": list(reached),
                    "state_asof": state_asof, "known_at": known_at, "source": source,
                }
                state = typ
                terminal_frozen = True
                state_asof = ev.get("event_date")
                known_at = ev.get("known_at")
                src = ev.get("source") or {}
                source = {
                    "url": src.get("url"), "label": _lifecycle_source_label(src.get("url")),
                    "title": src.get("title"), "doc_id": src.get("doc_id"),
                }
                continue
            # ladder event
            rank = _STAGE_RANK.get(typ)
            if rank is None:
                continue
            if stage_rank is None or rank > stage_rank:
                stage_rank = rank
                state = typ
                reached = list(LIFECYCLE_STAGES[: rank + 1])
                gaps = [s for s in LIFECYCLE_STAGES[: rank + 1] if s not in reached] or gaps
                # compute gaps from actually-observed ladder events, not just rank
                observed_types = {e.get("type") for e in item_events if e.get("type") in LIFECYCLE_STAGES}
                gaps = [s for s in LIFECYCLE_STAGES[: rank + 1] if s not in observed_types]
                state_asof = ev.get("event_date")
                known_at = ev.get("known_at")
                src = ev.get("source") or {}
                source = {
                    "url": src.get("url"), "label": _lifecycle_source_label(src.get("url")),
                    "title": src.get("title"), "doc_id": src.get("doc_id"),
                }
            else:
                conflict = True

        next_step = None
        if stage_rank is not None and not terminal_frozen and stage_rank + 1 < len(LIFECYCLE_STAGES):
            next_step = {"stage": LIFECYCLE_STAGES[stage_rank + 1], "date": None}

        why = None
        if state == "unknown":
            why = "no_document"

        out.append({
            "id": item_id,
            "title_en": reg.get("title_en"), "title_zh": reg.get("title_zh"),
            "jurisdiction": reg.get("jurisdiction"),
            "jurisdiction_en": reg.get("jurisdiction_en"), "jurisdiction_zh": reg.get("jurisdiction_zh"),
            "state": state, "stage_rank": stage_rank, "reached": reached, "gaps": gaps,
            "state_asof": state_asof, "known_at": known_at, "source": source,
            "next_step": next_step, "stalled": False, "corrected": corrected,
            "conflict": conflict, "why": why,
        })
    return out


def lifecycle_view(root=None) -> dict:
    """Reads the substrate + store, folds, returns the frozen view model. Never raises."""
    try:
        root_path = Path(root) if root else Path(".")
        intel_path = root_path / "data" / "policy" / "intel.json"
        intel = {}
        if intel_path.exists():
            try:
                intel = _json.loads(intel_path.read_text())
            except Exception as e:  # noqa: BLE001
                log.warning("policy_lifecycle: intel parse failed: %s", e)
        registry = []
        for lever in ((intel.get("administration") or {}).get("verified_levers") or []):
            registry.append({
                "id": lever.get("id"), "title_en": lever.get("title_en"), "title_zh": lever.get("title_zh"),
                "jurisdiction": lever.get("jurisdiction"),
                "jurisdiction_en": lever.get("jurisdiction_en"), "jurisdiction_zh": lever.get("jurisdiction_zh"),
            })
        events = lifecycle_events(root_path)
        items = fold_lifecycle(events, registry)

        counts = {"proposed": 0, "passed": 0, "in_force": 0, "enforced": 0, "other": 0, "unknown": 0}
        for it in items:
            st = it.get("state")
            if st in counts:
                counts[st] += 1
            elif st == "unknown":
                counts["unknown"] += 1
            else:
                counts["other"] += 1

        known_ats = [it["known_at"] for it in items if it.get("known_at")]
        as_of = max(known_ats).split("T")[0] if known_ats else intel.get("as_of")

        null_reason = None
        if registry and not events:
            null_reason = "no_coverage"
        elif intel.get("policy_lifecycle_suppressed"):
            null_reason = "rights_suppressed"

        return {
            "schema": LIFECYCLE_SCHEMA, "as_of": as_of, "null_reason": null_reason,
            "counts": counts, "items": items,
        }
    except Exception as e:  # noqa: BLE001
        log.error("policy_lifecycle: view failed: %s", e)
        return {"schema": LIFECYCLE_SCHEMA, "as_of": None, "null_reason": "no_coverage",
                "counts": {"proposed": 0, "passed": 0, "in_force": 0, "enforced": 0, "other": 0, "unknown": 0},
                "items": []}

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(force="--force" in __import__("sys").argv)
    score()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
