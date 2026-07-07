"""engine/stock_dossier.py — Buy Decision Packet v0: compact per-row dossier.

Assembles a ``dossier`` object attached additively to each us_standouts.json
row.  STRICT composition rule: every field surfaces ALREADY-COMPUTED keys from
the existing pipeline.  No new scoring, ranking, sizing, or gating arithmetic.

Dossier schema (all keys are optional / present-gated):
    {
      "action":        {verb, verb_zh, tone}  — from stock_view._action
      "why_now":       str                    — timing text (entry.text)
      "why_not":       [str, ...]             — top 1-2 falsifier EN texts
      "stale_flags":   [str, ...]             — short codes
      "authority_level": {tier, en, css}      — from trust_tier dict
      "no_buy_reasons": [str, ...]            — deterministic reason codes
    }

Caller (scripts/build_stock_library.py) builds the dossier after all chips
are attached to the row (conviction, signal, hold, earnings_soon) and writes
it as ``r["dossier"]``.  Fail-open: any per-row error → dossier absent.

no_buy_reasons code vocabulary (deterministic, sourced from existing keys):
    "freshness_expired"   — signal_gate near_miss_reason
    "not_topped"          — signal_gate near_miss_reason (not_topped_veto)
    "earnings_blackout"   — earnings_soon.in_blackout
    "risk_veto"           — conviction.cautions contains "stressed tape"
    "extended"            — ext grade parabolic/stretched OR ext_z > 2
    "capped_by_entry"     — conviction.size.capped_by_entry
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# no_buy reason codes — deterministic, sourced from already-computed keys
# ---------------------------------------------------------------------------
_REASON_EN: dict[str, str] = {
    "freshness_expired":  "Cross too old — wait for a fresh trigger",
    "not_topped":         "Topped / overbought — wait for it to reset",
    "earnings_blackout":  "Earnings within blackout window",
    "risk_veto":          "Stressed tape — size down or wait",
    "extended":           "Extended / parabolic — do not chase",
    "capped_by_entry":    "Entry capped — entry timing blocks a full buy",
}

_REASON_ZH: dict[str, str] = {
    "freshness_expired":  "交叉信号过期——等待新触发",
    "not_topped":         "超买/见顶——等待重置",
    "earnings_blackout":  "处于财报窗口期",
    "risk_veto":          "盘面承压——减仓或等待",
    "extended":           "过度拉伸/抛物线——勿追高",
    "capped_by_entry":    "入场封顶——入场时机阻碍满仓",
}

# stale_flag short codes emitted when specific conditions are present
_STALE_CHASE    = "chase"
_STALE_CAPPED   = "capped_by_entry"
_STALE_BARS     = "bars-since-cross"


def _g(d: Any, *keys: str, default: Any = None) -> Any:
    """Safe nested getter."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def build_dossier(row: dict, *, ext_grade: str | None = None) -> dict | None:
    """Build the compact dossier for one standout board row.

    Parameters
    ----------
    row : dict
        A fully-assembled us_standouts.json row (after conviction, signal, hold,
        earnings_soon chips are attached).
    ext_grade : str | None
        The extension grade string ("parabolic" | "stretched" | None) sourced
        from ext_map[ticker]["grade"] at the join point in build_stock_library.
        Cannot be read from the row directly (ext is not propagated to board rows).

    Returns
    -------
    dict | None
        The dossier dict, or None on any error (fail-open contract).
    """
    try:
        conv   = row.get("conviction") or {}
        signal = row.get("signal") or {}
        hold   = row.get("hold") or {}
        es     = row.get("earnings_soon") or {}

        # ── action chip ────────────────────────────────────────────────────
        # The action verb is already computed in stock_view._action() and stored
        # in rec["view"]["decision"]["action"].  For the board row we re-derive it
        # from conviction (which IS on the row) via the same logic keys rather
        # than re-importing stock_view (which would require a full rec).
        # Simpler: just expose the action from conviction's size + band fields,
        # passing hold_state + ext_grade so TRIM ONLY can fire on the board dossier.
        _view_action = _g(row, "view", "decision", "action")
        if _view_action:
            action = _view_action
        else:
            # Fallback: derive from existing verdict / cycle_blocked flag.
            # hold chip is attached to board rows (build_stock_library L3076-3078).
            _hold_state = _g(row, "hold", "state")
            action = _derive_action(conv, ext_grade=ext_grade, hold_state=_hold_state)

        # ── why_now — timing text from the entry ladder ─────────────────────
        # Primary source: view.decision.timing.text (present when rec["view"] is attached,
        # i.e. on per-stock page recs).  On board rows (wide["buy"/"watch"/"laggards"])
        # rec["view"] is absent; fall back to ladder.entry.text which carries the same
        # underlying timing rationale text from the ladder engine.
        why_now = (_g(row, "view", "decision", "timing", "text")
                   or _g(row, "ladder", "entry", "text"))

        # ── why_not — top 1-2 falsifiers ───────────────────────────────────
        # Primary source: view.falsifiers (present on per-stock recs via build_view).
        # On board rows view is absent; falsifiers are not independently available on the
        # row, so why_not remains empty.  no_buy_reasons (below) covers the deterministic
        # "not now" codes which serve an overlapping display role for the board dossier.
        falsifiers = _g(row, "view", "falsifiers") or []
        why_not = [f["en"] for f in falsifiers[:2] if f.get("en")]

        # ── stale_flags ─────────────────────────────────────────────────────
        stale_flags: list[str] = []
        _ext_z = row.get("ext_z")
        _ext_par  = (ext_grade in ("parabolic", "stretched")
                     or (_ext_z is not None and _ext_z > 2.0))
        if _ext_par:
            stale_flags.append(_STALE_CHASE)
        if _g(conv, "size", "capped_by_entry"):
            stale_flags.append(_STALE_CAPPED)
        _ticks = signal.get("ticks")
        if _ticks is not None and _ticks > 0:
            stale_flags.append(f"{_STALE_BARS}:{int(_ticks)}")

        # ── authority_level — trust_tier dict ───────────────────────────────
        authority_level = conv.get("trust_tier") or None

        # ── no_buy_reasons — deterministic reason codes ─────────────────────
        no_buy: list[str] = []
        # near_miss_reason from signal (compact verdict carries it when set)
        _nmr = row.get("near_miss_reason") or signal.get("near_miss_reason")
        if _nmr == "freshness_expired":
            no_buy.append("freshness_expired")
        elif _nmr in ("not_topped", "not_topped_veto"):
            no_buy.append("not_topped")
        # earnings blackout
        if es.get("in_blackout"):
            no_buy.append("earnings_blackout")
        # risk_veto: conviction cautions contain "stressed tape"
        _cautions = conv.get("cautions") or []
        if any("stressed tape" in (c or "") for c in _cautions):
            no_buy.append("risk_veto")
        # extended / parabolic
        if _ext_par:
            no_buy.append("extended")
        # capped_by_entry
        if _g(conv, "size", "capped_by_entry"):
            no_buy.append("capped_by_entry")

        dossier: dict = {}
        if action:
            dossier["action"] = action
        if why_now:
            dossier["why_now"] = why_now
        if why_not:
            dossier["why_not"] = why_not
        if stale_flags:
            dossier["stale_flags"] = stale_flags
        if authority_level:
            dossier["authority_level"] = authority_level
        if no_buy:
            dossier["no_buy_reasons"] = no_buy
        return dossier or None

    except Exception:  # noqa: BLE001 — display-only; never fatal
        return None


def _derive_action(conv: dict, *, ext_grade: str | None = None,
                   hold_state: str | None = None) -> dict | None:
    """Minimal fallback action derivation from conviction (no view required).

    Mirrors the simplified logic of stock_view._action() using only the conviction
    fields available on a board row.  Used when rec["view"] is absent (e.g. tests).

    Parameters
    ----------
    conv : dict
        Conviction chip attached to the board row.
    ext_grade : str | None
        Extension grade from ext_map ("parabolic" | "stretched" | None).
        Used to surface TRIM ONLY when extension is active and hold is intact.
    hold_state : str | None
        Hold state from the hold chip on the board row ("intact" | "launched" | "broken").
        TRIM fires on "intact" or "launched" (structure preserved) + extension.
    """
    size   = conv.get("size") or {}
    pct    = size.get("pct")
    bucket = size.get("bucket")
    band   = conv.get("band")
    trust  = conv.get("trust_tier") or {}
    tier   = trust.get("tier") if isinstance(trust, dict) else trust
    blocked = bool(conv.get("cycle_blocked"))

    def _a(en, zh, tone):
        return {"verb": en, "verb_zh": zh, "tone": tone}

    if bucket == "avoid" or pct == 0 or pct is None:
        return _a("WAIT", "等待", "wait")
    if tier in ("screen",):
        return _a("WATCH", "观察", "screen")
    if band in ("low", "na") or blocked:
        return _a("WAIT", "等待", "wait")
    # TRIM ONLY: extended (parabolic or stretched) + intact/launched hold structure.
    # Mirrors stock_view._action() demotion logic: never escalates (only reached when
    # the checks above have NOT fired a lower verb).  Display-only de-escalation.
    if (ext_grade in ("parabolic", "stretched")
            and hold_state in ("intact", "launched")):
        return _a("TRIM ONLY", "减仓", "trim")
    return _a("BUY", "买入", "go")


# ---------------------------------------------------------------------------
# Bilingual no_buy_reason code → display string helpers (for the template)
# ---------------------------------------------------------------------------
def no_buy_reason_en(code: str) -> str:
    """English display string for a no_buy_reasons code."""
    return _REASON_EN.get(code, code)


def no_buy_reason_zh(code: str) -> str:
    """Chinese display string for a no_buy_reasons code."""
    return _REASON_ZH.get(code, code)


# ---------------------------------------------------------------------------
# Expose vocabularies for tests
# ---------------------------------------------------------------------------
NO_BUY_CODES = frozenset(_REASON_EN.keys())
