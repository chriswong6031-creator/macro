"""Accountable AI JUDGMENT layer on the US standout top-picks (T9).

The per-stock sibling of engine/ai_desk.py and engine/thematic_desk.py. Where
catalyst_stock.py writes a DESCRIPTIVE brief (summary/drivers/risks), this writes an
ACCOUNTABLE, FALSIFIABLE LEAN per top pick — a direction the model is graded on:

    {ticker, lean: constructive|neutral|cautious|avoid, conviction, horizon_d,
     thesis, evidence[], dissent, falsifier{text, check}, check_by, entry_levels}

and a TRACK RECORD: every lean's check-by date is scored against the realized
forward return of the name vs SPY, so the layer earns (or loses) credibility over
time instead of asserting it.

HONESTY (load-bearing — this is NOT an alpha oracle):
  * The board's cross-sectional rank has NO validated forward edge at this horizon —
    the deep+PIT event gate is NEUTRAL and even SUE at its native quarterly cadence
    is ~0 IC (reports/sue-insider-deep-phase0.md). The validated, shipped content is
    the residual-alpha SELECTION rank + the T1–T7 RISK CONTROLS (extension brake,
    macro/event tax, lottery/idiosyncratic-risk haircut, suggested size, earnings/
    FOMC proximity). The model is told this explicitly.
  * The lean is the model's FALLIBLE judgement expressed as a falsifiable conditional,
    never edge extracted from the detectors, never a position size (the deterministic
    system owns sizing). It must be CALIBRATED to the track record.
  * HARD GUARD — the model may NOT override the deterministic risk reshape: a name the
    engine flags Extended / Avoid / blocked / size-AVOID can never be 'constructive'.
    `_reconcile` clamps it down so the AI can't re-introduce the CASY chase the T1–T7
    reshape removed.

FIREWALL: only public/derived context is sent to the third-party model — the same
fixed whitelist catalyst_stock.assemble_context already enforces, plus the public
Conviction profile + risk block off the standout board. No holdings/positions/
watchlist are ever read. Every public function returns plain data or None and NEVER
raises into the build (degrade-never-raise, like its siblings).

Run:  python -m engine.stock_desk --force      # regenerate notes now
      python -m engine.stock_desk --score       # grade past-due leans only
Writes data/stock_desk/{notes.json,theses.jsonl,track_record.json} +
site/stockdata/{ai_desk_notes.json,ai_desk_track.json}.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from engine import catalyst_stock, master_brain
from engine.catalyst_tone import _extract_json
from lib import config, store

log = logging.getLogger(__name__)

_LEDGER_DIR = ("data", "stock_desk")
SCHEMA = "stock_desk.v1"
_LEANS = ("constructive", "neutral", "cautious", "avoid")
_CONVICTIONS = ("low", "medium", "high")
_BENCH = "SPY"
_REL_THRESHOLD = 0.05            # ±5% rel-to-SPY = the lean was wrong-way
_DEFAULT_HORIZON = 21


# --------------------------------------------------------------------------- #
# config / flags
# --------------------------------------------------------------------------- #
def _cfg() -> dict:
    return (config.load().get("stock_desk") or {})


def enabled() -> bool:
    return bool(_cfg().get("enabled", False))


# --------------------------------------------------------------------------- #
# close readers (single-stock from the breadth matrix; SPY from the yahoo store)
# --------------------------------------------------------------------------- #
_CLOSES = None


def _closes():
    global _CLOSES
    if _CLOSES is None:
        try:
            from engine.equity_factors import _closes as _bc
            _CLOSES = _bc()
        except Exception:  # noqa: BLE001
            _CLOSES = pd.DataFrame()
    return _CLOSES


def _stock_series(ticker: str):
    if ticker == _BENCH:
        try:
            df = store.read("yahoo", _BENCH)
            if df is None or "close" not in df.columns:
                return None
            s = df["close"].astype(float).dropna()
            s.index = pd.to_datetime(s.index)
            return s
        except Exception:  # noqa: BLE001
            return None
    c = _closes()
    if ticker not in getattr(c, "columns", []):
        return None
    s = c[ticker].astype(float).dropna()
    s.index = pd.to_datetime(s.index)
    return s


def _close_asof(ticker: str, on_or_before) -> float | None:
    s = _stock_series(ticker)
    if s is None:
        return None
    s = s[s.index <= pd.Timestamp(on_or_before)]
    return round(float(s.iloc[-1]), 6) if len(s) else None


def _close_on_or_after(ticker: str, on_or_after) -> float | None:
    s = _stock_series(ticker)
    if s is None:
        return None
    s = s[s.index >= pd.Timestamp(on_or_after)]
    return round(float(s.iloc[0]), 6) if len(s) else None


# --------------------------------------------------------------------------- #
# STATE — the per-pick judgment bundle (public whitelist only)
# --------------------------------------------------------------------------- #
def _pick_state(row: dict, root: Path) -> dict | None:
    """One standout row → the bundle the model judges. Reuses catalyst_stock's
    firewall-safe context and adds the public Conviction profile + risk block."""
    t = row.get("ticker")
    if not t:
        return None
    ctx = catalyst_stock.assemble_context(t, root) or {"ticker": t}
    conv = row.get("conviction") or {}
    # public, already-rendered fields off the board — the deterministic verdict the model
    # must honour. The REAL profile schema (engine/stock_score.profile) carries
    # `cycle_blocked` (the cycle gate that already forbids "Buy" on a downtrend/topping/
    # parabolic name) — NOT 'blocked'/'size'/'risk'. Forward cycle_blocked so BOTH the
    # _reconcile guard AND the LLM see it (the guard's whole point is the CASY anti-chase).
    ctx["conviction"] = {
        "verdict": conv.get("verdict"),
        "band": conv.get("band"),
        "trust_tier": conv.get("trust_tier"),
        "score": conv.get("score"),
        "axes": conv.get("axes"),
        "drivers": conv.get("drivers"),
        "cautions": conv.get("cautions"),
        "cycle_blocked": conv.get("cycle_blocked"),
        "regime": conv.get("regime"),
    }
    ctx["board"] = {"price": row.get("price"), "off_high_pct": row.get("off_high"),
                    "dir": row.get("dir"), "state": row.get("state"),
                    "urgency": row.get("urgency"),
                    "macro_sensitivity": (row.get("macro_sensitivity") or {}).get("tier")}
    return ctx


def gather_top_picks(root=None, cfg: dict | None = None) -> dict | None:
    root = Path(root) if root else config.ROOT
    cfg = cfg or _cfg()
    site = root / config.load()["storage"].get("site_dir", "site")
    board = catalyst_stock._read_json(site / "factordata" / "us_standouts.json")
    if not isinstance(board, dict) or not board.get("buy"):
        return None
    n = max(1, min(12, int(cfg.get("max_picks", 6))))
    picks = []
    # PRIORITY-ORDER DEPENDENCY (intentional): this slice takes the board's own top-n
    # in artifact order (us_prophet_v1 = stage bucket, priority score desc, ticker), so
    # re-ordering the buy lane changes WHICH names the desk writes notes about — pinned
    # by tests/test_us_board_rank.py::TestArtifactOrderConsumers.
    for row in board["buy"][:n]:
        st = _pick_state(row, root)
        if st:
            picks.append(st)
    if not picks:
        return None
    return {"as_of": board.get("as_of"), "rank_by": board.get("rank_by"),
            "gate_go": board.get("gate_go"), "picks": picks}


# --------------------------------------------------------------------------- #
# LLM synthesis
# --------------------------------------------------------------------------- #
_SCHEMA_TAIL = (
    "Return ONLY a JSON object (no markdown fences): {\"notes\": [ONE object per ticker "
    "you were given, in any order]} where each note is:\n"
    "  ticker: string — exactly as provided.\n"
    "  lean: one of \"constructive\",\"neutral\",\"cautious\",\"avoid\". A lean is a "
    "DIRECTION on the name RELATIVE TO THE S&P 500 over the horizon, never a size.\n"
    "  conviction: one of \"low\",\"medium\",\"high\" — be modest; default \"low\" when "
    "the edge is illegible or the detectors are display-only.\n"
    "  horizon_d: integer trading days, 5..60.\n"
    "  thesis: one or two sentences — the reasoning, naming WHICH validated leg or risk "
    "control supports it.\n"
    "  evidence: array of short strings (cite the specific axis / verdict / risk leg).\n"
    "  dissent: string — the single strongest contrary case.\n"
    "  falsifier_text: string — one concrete condition that would prove the lean wrong, "
    "phrased as the plain condition itself. This text is shown to users under a 'Changes "
    "this read' label: never write the words 'falsified', 'falsify' or 'refuted' in it.")

_SYSTEM = (
    "You are the analyst writing accountable JUDGMENT notes on a solo trader's OWN "
    "deterministic stock-screen 'top picks'. For each name you are handed its public "
    "Conviction profile (verdict, four axes, trust tier, risk block, suggested size), "
    "its cycle/ladder read, technicals, cross-sectional factor z-scores and EDGAR "
    "fundamentals. Turn that into a SHORT, FALSIFIABLE, accountable lean per name.\n\n"
    "CRITICAL — what is and isn't validated:\n"
    "- The board's cross-sectional RANK has NO validated forward edge at this horizon: "
    "the deep, point-in-time event-edge gate is NEUTRAL and even earnings-surprise (SUE) "
    "at its native quarterly cadence is ~0 information-coefficient. So you must NOT claim "
    "the rank 'predicts' returns or that a high score means it will outperform.\n"
    "- What IS validated and shipped is (a) the residual-alpha SELECTION that orders the "
    "board and (b) the RISK CONTROLS in each profile — the extension/'don't-chase' brake, "
    "the macro/event tax, the lottery and idiosyncratic-risk haircut, the suggested size, "
    "and earnings/FOMC proximity. Lean ON the risk reshape, not on imagined alpha.\n"
    "- Your lean is YOUR FALLIBLE judgement expressed as a falsifiable conditional graded "
    "against reality — not edge extracted from the detectors.\n\n"
    "Rules:\n"
    "- Reason ONLY over the provided JSON per name + well-known market structure. NEVER "
    "fabricate a level, score, catalyst or event. If a name's state doesn't support a "
    "view, say so and lean \"neutral\".\n"
    "- HONOUR THE DETERMINISTIC VERDICT, BUT DON'T SHORT A LEADER ON EXTENSION ALONE. A "
    "\"cautious\"/\"avoid\" lean is a GRADED DIRECTIONAL SHORT vs the S&P 500 — it scores a "
    "MISS when the name OUT-performs. On this desk, cautious leans placed on strong-leader "
    "names that were merely extended have been directionally correct only ~17% of the time "
    "(momentum persists over this horizon); cautious leans on genuinely weak/lagging names "
    "were ~86% correct. So: if the verdict is a strong leader / high-conviction / high-"
    "confluence / 'good entry' / 'building a base' and the caution is ONLY that it is "
    "extended / priced-in / 'don't chase' (momentum still intact), you may NOT be "
    "\"constructive\" (no chasing) but you must lean \"neutral\" — watch, don't chase, DON'T "
    "short it. Reserve \"cautious\"/\"avoid\" for a name with an ACTUAL bearish signal: "
    "cycle_blocked / downtrend / topping / rolling over / 'wait for a base' / 'timing "
    "against' / weak or lagging / deteriorating fundamentals. The engine owns the risk call; "
    "you explain and pressure-test it, you do not overrule it.\n"
    "- NEVER give a position size, weight, dollar amount or fire a trade. Direction + "
    "what would invalidate it only.\n"
    "- Each note needs an honest DISSENT (the best bear case) and a CONCRETE falsifier.\n"
    "- If a track_record is provided, CALIBRATE conviction to it (if past constructive "
    "leans underperformed, default lower). Be honest about small samples.\n\n"
    + _SCHEMA_TAIL)


def _build_user(state: dict) -> str:
    return ("The trader's top picks with their deterministic profiles (JSON). Write one "
            "accountable, falsifiable, never-sized judgment note PER ticker.\n<state>\n"
            + json.dumps(state, indent=2, default=str) + "\n</state>")


def synthesize(state: dict, cfg: dict | None = None, call=None) -> dict:
    cfg = {**(cfg or _cfg()), "usage_stage": "stock-desk"}  # cost drill-down tag
    call = call or (lambda system, user, c: master_brain._call_model(system, user, c))
    payload = {"as_of": state.get("as_of"), "picks": state.get("picks"),
               "track_record": state.get("track_record")}
    reply, degraded = call(_SYSTEM, _build_user(payload), cfg)
    if reply is None:
        return {"notes": [], "degraded": degraded or "no_reply"}
    parsed = _extract_json(reply)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("notes"), list):
        return {"notes": [], "degraded": "unparseable"}
    return {"notes": parsed["notes"], "degraded": None}


# --------------------------------------------------------------------------- #
# falsifiable check + reconcile with the deterministic risk reshape
# --------------------------------------------------------------------------- #
_BLOCK_WORDS = ("extended", "don't chase", "dont chase", "avoid", "exit", "reduce",
                "elevated-risk", "imminent")


_BLOCK_VERDICT_WORDS = ("extended", "don't chase", "dont chase", "avoid", "exit",
                        "wait for a base", "timing against", "hold off")


def _is_risk_blocked(pick: dict) -> bool:
    conv = pick.get("conviction") or {}
    # PRIMARY: the cycle gate (engine/stock_score) — a downtrend/topping/parabolic name is
    # cycle_blocked and its verdict ("Strong name · wrong tape — wait for a base",
    # "Hold off — timing against you") carries NO "extended/avoid" word, so the word-scan
    # alone misses all 21/120 live cycle-blocked names. cycle_blocked is the real flag.
    if conv.get("cycle_blocked") or conv.get("blocked"):   # 'blocked' kept as a legacy alias
        return True
    # belt-and-braces: a non-cycle-blocked but extended/avoid name (T1 stretch brake etc.)
    size = (conv.get("size") or {})                        # harmless future-proof; absent today
    if str(size.get("bucket", "")).lower() == "avoid" or size.get("pct") == 0:
        return True
    blob = (" ".join(str(conv.get(k) or "") for k in ("verdict", "band")) + " "
            + " ".join(str(c) for c in (conv.get("cautions") or []))).lower()
    return any(w in blob for w in _BLOCK_VERDICT_WORDS)


# A name can be risk-blocked for two very different reasons, and they INVERT the right lean:
#   (1) STRONG LEADER, merely EXTENDED — momentum intact, just priced-in / 'don't chase'. A
#       "cautious" lean here is a directional SHORT vs SPY that FIGHTS live momentum; on this
#       desk those have been ~17% directionally correct (n=52). The honest lean is NEUTRAL
#       (watch, don't chase, don't short) — never constructive (no chasing), never cautious.
#   (2) BEARISH TAPE — cycle_blocked / downtrend / topping / rolling over / weak / lagging /
#       deteriorating. Here caution is warranted (those cautious leans were ~86% correct) — keep it.
# Discriminator: a leader-class verdict with NO bearish-tape cause is case (1). (Measured on the
# desk's own theses.jsonl — see research/INTEL_HUB_V3_LOOP_CLOSING.md §Phase 3.)
_LEADER_VERDICT_WORDS = ("leader", "high-conviction", "high conviction", "high-confluence",
                         "high confluence", "constructive", "good entry", "building a base")
_BEARISH_CAUSE_WORDS = ("wait for a base", "timing against", "hold off", "downtrend", "down trend",
                        "topping", "rolling over", "rolling-over", "distribution", "breakdown",
                        "lagging", "weak", "relative weakness", "deteriorat", "exit", "reduce")


def _is_strong_leader_extension(pick: dict) -> bool:
    """True when a name is de-escalation-worthy ONLY because a strong leader is extended
    (momentum intact) — NOT because the tape is bearish. This is the case where a 'cautious'
    short fights momentum and loses ~5:1, so the honest lean is 'neutral'."""
    conv = pick.get("conviction") or {}
    board = pick.get("board") or {}
    blob = (" ".join(str(conv.get(k) or "") for k in ("verdict", "band")) + " "
            + " ".join(str(c) for c in (conv.get("cautions") or []))).lower()
    leader = any(w in blob for w in _LEADER_VERDICT_WORDS)
    bearish = (bool(conv.get("cycle_blocked"))                 # cycle gate = downtrend/topping/parabolic
               or any(w in blob for w in _BEARISH_CAUSE_WORDS)
               or "down" in str(board.get("dir") or "").lower())
    return leader and not bearish


def _reconcile(lean: str, pick: dict) -> tuple[str, str | None]:
    """Reconcile an LLM lean with the deterministic risk reshape — DE-ESCALATION ONLY (the AI
    can soften a name but never escalate a risk-blocked one to constructive), AND never let a
    lean SHORT a strong leader on extension alone (that lean fights momentum and is ~17% right)."""
    lean = lean if lean in _LEANS else "neutral"
    leader_ext = _is_strong_leader_extension(pick)
    # (1) anti-chase: never constructive on a risk-blocked name. A strong-but-extended leader
    #     de-escalates to NEUTRAL (don't chase, don't short); a bearish-tape name to CAUTIOUS.
    if lean == "constructive" and _is_risk_blocked(pick):
        if leader_ext:
            return "neutral", "clamped: strong leader but extended — don't chase, don't short (neutral)"
        return "cautious", "clamped: engine flags this name extended/avoid/blocked"
    # (2) don't SHORT a leader on extension alone: soften an LLM-native cautious/avoid on a
    #     momentum-intact leader down to neutral (cautious-on-leader ≈ 17% directionally correct).
    if lean in ("cautious", "avoid") and leader_ext:
        return "neutral", ("softened: strong leader, momentum intact — extension is not a short "
                           "(cautious-on-leader historically ~17% right); watch, don't chase")
    return lean, None


def _derive_check(ticker: str, lean: str, horizon: int, cfg: dict) -> dict:
    """Machine-checkable relative-return predicate vs SPY. constructive → FALSE if it
    UNDER-performs SPY by ≥ threshold; cautious/avoid → FALSE if it OUT-performs by ≥
    threshold (the caution was wrong); neutral → soft (logged, never scored)."""
    thr = float((cfg.get("falsifier_defaults") or {}).get("rel_return", _REL_THRESHOLD))
    if lean == "constructive":
        return {"kind": "rel_return", "subject_ticker": ticker, "vs": _BENCH,
                "op": "<", "threshold": -thr, "horizon_d": horizon}
    if lean in ("cautious", "avoid"):
        return {"kind": "rel_return", "subject_ticker": ticker, "vs": _BENCH,
                "op": ">", "threshold": thr, "horizon_d": horizon}
    return {"kind": "soft", "reason": "neutral lean — not scored"}


def _check_by(asof, horizon: int) -> str | None:
    try:
        d = pd.Timestamp(asof) + pd.tseries.offsets.BDay(int(horizon))
        return d.date().isoformat()
    except Exception:  # noqa: BLE001
        return None


def _entry_levels(check: dict, asof) -> dict:
    out = {}
    if check.get("kind") == "rel_return":
        for sym in (check.get("subject_ticker"), check.get("vs")):
            lv = _close_asof(sym, asof)
            if lv is not None:
                out[sym] = lv
    return out


def _build_note(note: dict, pick: dict, asof, cfg: dict, idx: int) -> dict | None:
    t = note.get("ticker") or pick.get("ticker")
    if not t:
        return None
    lean, clamp = _reconcile(str(note.get("lean", "neutral")).lower(), pick)
    conv = str(note.get("conviction", "low")).lower()
    conv = conv if conv in _CONVICTIONS else "low"
    try:
        horizon = int(note.get("horizon_d") or cfg.get("default_horizon_d", _DEFAULT_HORIZON))
    except Exception:  # noqa: BLE001
        horizon = _DEFAULT_HORIZON
    horizon = max(5, min(60, horizon))
    check = _derive_check(t, lean, horizon, cfg)
    dissent = note.get("dissent")
    if clamp:
        dissent = f"{dissent} ({clamp})" if dissent else clamp
    return {
        "id": f"{asof}-{t}-{idx + 1}",
        "ticker": t,
        "name": (pick.get("identity") or {}).get("name"),
        "lean": lean, "conviction": conv, "horizon_d": horizon,
        "thesis": note.get("thesis"),
        "evidence": [str(e) for e in (note.get("evidence") or [])][:5],
        "dissent": dissent,
        "falsifier": {"text": note.get("falsifier_text"), "check": check},
        "check_by": _check_by(asof, horizon),
        "engine_verdict": (pick.get("conviction") or {}).get("verdict"),
    }


# --------------------------------------------------------------------------- #
# ledger
# --------------------------------------------------------------------------- #
def _ledger_path(root) -> Path:
    d = Path(root).joinpath(*_LEDGER_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d / "theses.jsonl"


def _append_ledger(notes: list, asof, root) -> None:
    lp = _ledger_path(root)
    now = datetime.now(timezone.utc).isoformat()
    lines = []
    for nt in notes:
        check = (nt.get("falsifier") or {}).get("check") or {}
        lines.append(json.dumps({
            "id": nt["id"], "logged_at": now, "state_asof": str(asof),
            "ticker": nt["ticker"], "lean": nt["lean"], "conviction": nt["conviction"],
            "horizon_d": nt["horizon_d"], "falsifier": nt.get("falsifier"),
            "check_by": nt.get("check_by"),
            "entry_levels": _entry_levels(check, asof),
            "engine_verdict": nt.get("engine_verdict"),
            "status": "open", "scored_at": None, "outcome": None, "realized": None,
        }, default=str))
    with lp.open("a") as f:
        for ln in lines:
            f.write(ln + "\n")


# --------------------------------------------------------------------------- #
# scorer — grade past-due leans vs realized name-minus-SPY return
# --------------------------------------------------------------------------- #
# Outcomes that are FINAL once written to scored.jsonl. Mirrors engine.desk_scorer's
# append-only convention (theses.jsonl is the desk's; outcomes go to a separate file, one
# row per id) minus `expired` — see _prior_outcomes for why that one stays retryable.
_FINAL_OUTCOMES = ("hit", "miss", "unscored")


def _append_scored(d: Path, rows: list) -> None:
    """Append newly-final outcomes to the append-only scored.jsonl.

    NOT lane-gated, deliberately. The forward-ledger law ("nightly is the sole advancer")
    is enforced for THIS desk at the workflow level, not in the module: the only caller is
    scripts.build_stock_briefs → daily.yml's `stock_briefs` job, and that job is also the
    only thing that commits `data/stock_desk` (daily.yml `git add data/stock_desk`). Any
    other lane's write lands in a checkout that is thrown away. Do not "fix" this with
    engine.ledger_lane.nightly_advance_enabled(): the `stock_briefs` job sets no
    COLLECT_LANE, so that gate would never fire and the spine would be dead on arrival
    (the sibling theses.jsonl append and track_record.json write here are ungated for the
    same reason).

    Never raises: an unwritable audit trail must not cost us the track record."""
    if not rows:
        return
    try:
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "scored.jsonl", "a") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        log.warning("stock_desk scored append failed: %s", e)


def _prior_outcomes(d: Path) -> dict:
    """Already-graded outcomes from scored.jsonl, by thesis id (last write wins).

    Only FINAL outcomes are read back. `open` is retried every run by definition, and
    `expired` here means the price cache could not value the lean — which for this desk is
    emitted on the FIRST unpriceable read, with none of engine.desk_scorer.GRACE_BD's ten
    business days of slack (score_ledger turns any `_eval` → None straight into `expired`).
    Freezing that would turn a collector gap — a name absent from today's `_closes()` panel,
    a delisting that later backfills — into a permanent verdict, so it stays retryable."""
    out = {}
    try:
        for line in (d / "scored.jsonl").read_text().splitlines():
            try:
                r = json.loads(line)
                if r.get("id") and r.get("outcome") in _FINAL_OUTCOMES:
                    out[r["id"]] = r
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001 — absent file is the cold-start case, not an error
        pass
    return out


def _eval(check: dict, entry: dict, check_by: str, asof) -> dict | None:
    et, vs = check.get("subject_ticker"), check.get("vs")
    e0 = (entry or {}).get(et) or _close_asof(et, asof)
    b0 = (entry or {}).get(vs) or _close_asof(vs, asof)
    e1 = _close_on_or_after(et, check_by)
    b1 = _close_on_or_after(vs, check_by)
    if None in (e0, e1, b0, b1) or e0 == 0 or b0 == 0:
        return None
    realized = (e1 / e0 - 1.0) - (b1 / b0 - 1.0)
    op, thr = check.get("op"), float(check.get("threshold", 0.0))
    falsified = (realized <= thr) if op == "<" else (realized >= thr)
    dir_ok = (realized > 0) if op == "<" else (realized < 0)
    return {"outcome": "miss" if falsified else "hit", "realized": round(realized, 4),
            "directionally_correct": bool(dir_ok)}


def _bucket(rows: list) -> dict:
    dec = [r for r in rows if r.get("outcome") in ("hit", "miss")]
    n = len(dec)
    hits = sum(1 for r in dec if r["outcome"] == "hit")
    dok = sum(1 for r in dec if r.get("directionally_correct"))
    return {"n": n, "hits": hits, "misses": n - hits,
            "hit_rate": round(hits / n, 3) if n else None,
            "dir_accuracy": round(dok / n, 3) if n else None}


def _calibration_note(overall: dict) -> str:
    if overall["n"] == 0:
        return ("No stock leans scored yet — the track record begins once the first "
                "check-by dates pass. Until then every lean is a provisional hypothesis, "
                "and the honest prior is no exploitable cross-sectional edge.")
    parts = [f"{overall['n']} leans scored, hit-rate {overall['hit_rate']} "
             f"(directional accuracy {overall['dir_accuracy']})."]
    if overall["n"] < 20:
        parts.append("Small sample — treat conviction as provisional; the prior remains "
                     "no validated forward edge (this layer is accountability, not alpha).")
    return " ".join(parts)


def score_ledger(root=None, today=None) -> dict | None:
    """Grade every past-due, scorable lean; write data/stock_desk/track_record.json +
    site/stockdata/ai_desk_track.json and append new outcomes to
    data/stock_desk/scored.jsonl. Additive/idempotent; never raises."""
    root = Path(root) if root else config.ROOT
    today = pd.Timestamp(today) if today else pd.Timestamp(datetime.now(timezone.utc).date())
    lp = _ledger_path(root)
    if not lp.exists():
        return None
    try:
        rows = {}
        for line in lp.read_text().splitlines():
            try:
                r = json.loads(line)
                if r.get("id"):
                    rows[r["id"]] = r
            except Exception:  # noqa: BLE001
                pass
        d = Path(root).joinpath(*_LEDGER_DIR)
        prior = _prior_outcomes(d)
        scored, fresh = [], []
        for r in rows.values():
            check = (r.get("falsifier") or {}).get("check") or {}
            cb = r.get("check_by")
            # `subject` duplicates `ticker` for engine.spine.adapt_desk_scorer, which reads
            # `subject` for the row's symbol and derives its co-firing collapse key from it
            # (event_key defaults to "{symbol}:{as_of}"). Without it every row here would
            # fall back to the literal "stock_desk" and 45 distinct leans would collapse to
            # one effective event per check_by date in engine.pooling.arming. `ticker` stays
            # for the track record's own `recent` list and any existing reader.
            base = {"id": r.get("id"), "ticker": r.get("ticker"), "subject": r.get("ticker"),
                    "lean": r.get("lean"), "conviction": r.get("conviction"),
                    "kind": check.get("kind"), "check_by": cb}
            was = prior.get(r.get("id"))
            if was is not None:
                # A verdict is reached ONCE. The aggregation dimensions are re-read from the
                # ledger, but the OUTCOME is the one already published — yfinance re-bases a
                # name's whole stored history on every dividend, so re-grading from live
                # prices can silently rewrite a grade the track record already reported.
                scored.append({**base, **{k: was.get(k) for k in
                                          ("outcome", "realized", "directionally_correct")}})
                continue
            if check.get("kind") != "rel_return" or not cb:
                row = {**base, "outcome": "unscored"}
            elif pd.Timestamp(cb) > today:
                row = {**base, "outcome": "open"}
            else:
                res = _eval(check, r.get("entry_levels") or {}, cb, r.get("state_asof"))
                row = {**base, **(res or {"outcome": "expired"})}
            scored.append(row)
            if row.get("outcome") in _FINAL_OUTCOMES:
                fresh.append({**row, "scored_at": datetime.now(timezone.utc).isoformat()})
        _append_scored(d, fresh)
        dec = [s for s in scored if s.get("outcome") in ("hit", "miss")]
        overall = _bucket(dec)
        track = {
            "schema": SCHEMA, "as_of": today.date().isoformat(),
            "scored_total": len(dec),
            "open": sum(1 for s in scored if s.get("outcome") == "open"),
            "unscored_neutral": sum(1 for s in scored if s.get("outcome") == "unscored"),
            "overall": overall,
            "by_lean": {ln: _bucket([s for s in dec if s.get("lean") == ln]) for ln in _LEANS},
            "by_conviction": {c: _bucket([s for s in dec if s.get("conviction") == c])
                              for c in _CONVICTIONS},
            "calibration_note": _calibration_note(overall),
            "recent": [{k: s.get(k) for k in ("id", "ticker", "lean", "conviction",
                        "outcome", "realized", "check_by")}
                       for s in sorted(dec, key=lambda s: s.get("check_by") or "",
                                       reverse=True)[:12]],
        }
        (d / "track_record.json").write_text(json.dumps(track, indent=2, default=str))
        pub = Path(root) / "site" / "stockdata" / "ai_desk_track.json"
        pub.parent.mkdir(parents=True, exist_ok=True)
        pub.write_text(json.dumps(track, default=str))
        return track
    except Exception as e:  # noqa: BLE001
        log.error("stock_desk score_ledger failed: %s", e)
        return None


# --------------------------------------------------------------------------- #
# run — interval-gated; gather → synthesize → persist + append ledger
# --------------------------------------------------------------------------- #
def _brief_age_days(prev: dict | None) -> float | None:
    if not isinstance(prev, dict) or not prev.get("generated_at"):
        return None
    try:
        gen = pd.to_datetime(prev["generated_at"])
        return (datetime.now(timezone.utc) - gen.to_pydatetime().replace(tzinfo=timezone.utc)).total_seconds() / 86400.0
    except Exception:  # noqa: BLE001
        return None


def run(persist: bool = True, root=None, force: bool = False, call=None) -> dict | None:
    """Generate accountable leans on the top picks. Interval-gated to cap LLM cost;
    returns the prior note untouched when it is younger than `interval_days`. Always
    scores the ledger (cheap, no LLM). Never raises."""
    if not enabled() and not force:
        return None
    root = Path(root) if root else config.ROOT
    cfg = _cfg()
    notes_path = Path(root).joinpath(*_LEDGER_DIR) / "notes.json"
    pub_path = Path(root) / "site" / "stockdata" / "ai_desk_notes.json"

    score_ledger(root=root)                     # always refresh the track record

    if not force:
        interval = max(1, min(7, int(cfg.get("interval_days", 1))))
        if interval > 1 and notes_path.exists():
            prev = catalyst_stock._read_json(notes_path)
            age = _brief_age_days(prev)
            if age is not None and age < interval:
                log.info("stock_desk: notes %.1fd old (< %dd) — skipping regen", age, interval)
                return prev

    state = gather_top_picks(root, cfg)
    if not state:
        log.info("stock_desk: no top picks to judge")
        return None
    track = catalyst_stock._read_json(
        Path(root).joinpath(*_LEDGER_DIR) / "track_record.json")
    if isinstance(track, dict):
        state["track_record"] = {k: track.get(k) for k in ("overall", "by_lean", "calibration_note")}

    syn = synthesize(state, cfg, call=call)
    asof = state.get("as_of") or datetime.now(timezone.utc).date().isoformat()
    pick_by_t = {p.get("ticker"): p for p in state["picks"]}
    notes = []
    for i, nt in enumerate(syn.get("notes") or []):
        pick = pick_by_t.get(nt.get("ticker")) or {}
        built = _build_note(nt, pick, asof, cfg, i)
        if built:
            notes.append(built)

    out = {"schema": SCHEMA, "as_of": asof,
           "generated_at": datetime.now(timezone.utc).isoformat(),
           "degraded": syn.get("degraded"), "notes": notes,
           "disclaimer": ("Accountable AI judgment on the deterministic top picks. The "
                          "cross-sectional rank has no validated forward edge; these leans "
                          "are fallible, falsifiable conditionals graded against reality — "
                          "never position sizes. See the track record.")}
    if persist and notes:
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        notes_path.write_text(json.dumps(out, indent=2, default=str))
        by_t = {nt["ticker"]: nt for nt in notes}
        pub_path.parent.mkdir(parents=True, exist_ok=True)
        pub_path.write_text(json.dumps({"as_of": asof, "by_ticker": by_t,
                                        "disclaimer": out["disclaimer"]}, default=str))
        _append_ledger(notes, asof, root)
        score_ledger(root=root)                 # re-score so the new open leans show
    log.info("stock_desk: %d notes (%s)", len(notes), syn.get("degraded") or "ok")
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="regenerate ignoring the interval gate")
    ap.add_argument("--score", action="store_true", help="only grade the ledger (no LLM)")
    args = ap.parse_args()
    if args.score:
        tr = score_ledger()
        print(json.dumps(tr, indent=2) if tr else "no ledger")
        return 0
    out = run(persist=True, force=args.force)
    if not out:
        print("no output (no picks / disabled)")
        return 0
    print(f"as_of {out['as_of']} · {len(out['notes'])} notes · degraded={out.get('degraded')}")
    for nt in out["notes"]:
        print(f"  {nt['ticker']:6s} {nt['lean']:12s} conv={nt['conviction']:6s} "
              f"h={nt['horizon_d']}d  check_by={nt.get('check_by')}  | {nt.get('thesis')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
