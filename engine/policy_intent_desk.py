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

from lib import config
from engine import master_brain as _mb              # reuse the DeepSeek/Anthropic client
from engine import ai_desk as _desk                 # reuse _level_asof / _check_by
from engine import ai_desk_scorer as _scorer        # reuse the predicate evaluators
from engine.catalyst_tone import _extract_json      # shared tolerant JSON parser
from engine.regime_label import quad_label          # regime stamp → by_regime track record

log = logging.getLogger(__name__)

SCHEMA = "policy_intent_desk.v1"
DISCLAIMER = (
    "Policy intent desk — realpolitik, context only, never scored or sized. Each lean is "
    "a fallible, FALSIFIABLE judgement (proxy vs SPY, with a check-by date), not a trade "
    "or a position size. Intent is inferred from interests; treat it as a hypothesis with "
    "a track record, not an oracle.")
DISCLAIMER_ZH = (
    "意图台 —— 现实政治、仅供参考，从不评分或定仓。每条判断都是可证伪、会出错的判断"
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
    "     falsifier_text: string — one concrete condition that would prove it wrong.\n"
    "     falsifier_text_zh: string — faithful 简体中文 translation of falsifier_text.\n"
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
    reply, reason = (call or _mb._call_model)(_SYSTEM, _build_user(state), cfg)
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
    # per-run token (HHMMSS from generated_at) so same-day re-runs can't collide ids
    run_token = "".join(c for c in (brief.get("generated_at") or "") if c.isdigit())[8:14]
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
    theses = brief.get("theses") or []
    if not theses:
        return
    try:
        d = Path(root) / "data" / "policy_intent"
        d.mkdir(parents=True, exist_ok=True)
        asof = brief.get("state_asof")
        regime = quad_label(root)
        with open(d / "theses.jsonl", "a") as fh:
            for t in theses:
                check = (t.get("falsifier") or {}).get("check") or {}
                entry = {}
                for key in ("subject_ticker", "vs"):
                    tk = check.get(key)
                    if tk:
                        lv = _desk._level_asof(tk, root, asof)
                        if lv is not None:
                            entry[tk] = lv
                fh.write(json.dumps({
                    "id": t["id"], "logged_at": brief["generated_at"], "state_asof": asof,
                    "actor": t.get("actor"), "subject": t["subject"], "lean": t["lean"],
                    "conviction": t["conviction"], "horizon_d": t["horizon_d"],
                    "falsifier": t["falsifier"], "check_by": t["check_by"],
                    "entry_levels": entry, "regime": regime,
                    "status": "open", "scored_at": None, "outcome": None, "realized": None,
                }, default=str) + "\n")
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
    append scored rows, and write the rolling track record. NEVER raises."""
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


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(force="--force" in __import__("sys").argv)
    score()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
