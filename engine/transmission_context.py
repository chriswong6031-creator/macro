"""FX / Dollar Transmission context-layer composer.

Reads ``data/forex/latest.json`` (produced by build_forex, which runs before
build_transmission in daily.yml) and the transmission snapshot dict that
build_transmission will write to ``data/transmission/latest.json``.

PUBLIC API
----------
compose_dollar_channel(root)  — read forex artifact → dollar-channel context dict
compact_state(contract, dx)   — extract comparison fingerprint from tx contract + dx
diff_changes(prev, curr)      — pure diff of two compact states → ≤ 6 change items
build_changes(old, new, dx, asof) — same-day-idempotent changes block
compose_hero(tx, dx)          — one-line verdict + per-channel stance dicts

HOUSE LAWS
----------
* Display-tier context only. Every emitted dict carries display_only=True.
* Fail-open everywhere: absent/corrupt inputs → None / empty, never raises.
* Additive only: never rename or remove keys in existing artifacts.
* No LLM-originated content. The word "validated" is banned from emitted text.
* No gating, ranking, sizing, or escalation.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Label maps
# ---------------------------------------------------------------------------

# EN label (as emitted by forex_transmission.py headwind_for/tailwind_for)
# → {"en": ..., "zh": ...}
_HW_TW_LABEL_ZH: dict[str, str] = {
    "US equities":  "美国股票",
    "EM equities":  "新兴市场股票",
    "Gold":         "黄金",
    "Oil (WTI)":    "原油",
    "Copper":       "铜",
    "10y Treasury": "10年期国债",  # matches forex_transmission._ASSET_META's own ZH
    "Bitcoin":      "比特币",
}

# dollar_desk.real_rate_regime — full string as stored in the artifact
# (e.g. "Restrictive real yields") → plain short label pair
_REAL_RATE_REGIME_LABELS: dict[str, tuple[str, str]] = {
    "Restrictive real yields": ("High real rates", "高实际利率"),
    "Accommodative real yields": ("Easy money", "宽松实际利率"),
    "Neutral real yields": ("Neutral", "中性实际利率"),
    "Reflationary": ("Reflation", "再通胀"),
    "reflation": ("Reflation", "再通胀"),
    "restrictive": ("High real rates", "高实际利率"),
    "accommodative": ("Easy money", "宽松实际利率"),
    "neutral": ("Neutral", "中性实际利率"),
}

# Scenario key → plain bilingual label for display/diff sentences
_SCENARIO_LABELS: dict[str, tuple[str, str]] = {
    "carry_unwind": ("Carry unwind", "套息平仓"),
    "dollar_wrecking_ball": ("Dollar wrecking ball", "美元压路机"),
    "em_crisis_capital_flight": ("EM crisis / capital flight", "新兴市场危机"),
    "haven_flight_risk_off": ("Safe-haven flight", "避险飞向"),
    "reflation_risk_on": ("Reflation / risk-on", "再通胀 / 风险偏好"),
    "intervention_risk": ("FX intervention risk", "外汇干预风险"),
}

# regime_radar scenario key names also used in mastermind_context.py _summarize_
_SCENARIO_KEYS = list(_SCENARIO_LABELS.keys())

# curve_regime key → plain EN label (for diff sentences)
_CURVE_REGIME_LABELS: dict[str, tuple[str, str]] = {
    "bull_steepener":  ("bull steepener", "牛市变陡"),
    "bull_flattener":  ("bull flattener", "牛市变平"),
    "bear_steepener":  ("bear steepener", "熊市变陡"),
    "bear_flattener":  ("bear flattener", "熊市变平"),
    "flat":            ("flat curve", "平坦曲线"),
    "inverted":        ("inverted curve", "倒挂曲线"),
}

# rates regime (from rate_inflation_transmission.current_state)
_RATES_REGIME_LABELS: dict[str, tuple[str, str]] = {
    "restrictive":   ("restrictive", "偏紧"),
    "neutral":       ("neutral", "中性"),
    "accommodative": ("accommodative", "宽松"),
}

# usd_dir
_USD_DIR_LABELS: dict[str, tuple[str, str]] = {
    "strengthening": ("rising", "走强"),
    "weakening":     ("falling", "走软"),
    "flat":          ("flat", "横盘"),
}

# usd_dir → state plain words
_USD_STATE: dict[str, dict[str, str]] = {
    "strengthening": {"en": "Rising", "zh": "走强"},
    "weakening":     {"en": "Falling", "zh": "走软"},
    "flat":          {"en": "Flat", "zh": "横盘"},
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _data_root(root=None) -> Path:
    """Resolve data directory.  Supports root override for tests."""
    if root is not None:
        return Path(root)
    try:
        from lib import config as _cfg
        return _cfg.data_dir()
    except Exception:
        return Path(__file__).resolve().parent.parent / "data"


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _bil_label(en: str, zh_map: dict[str, str], fallback_zh: str | None = None) -> dict[str, str]:
    """Resolve bilingual label for a known EN label string."""
    return {"en": en, "zh": zh_map.get(en, fallback_zh or en)}


def _label_pair(en: str) -> dict[str, str]:
    return {"en": en, "zh": _HW_TW_LABEL_ZH.get(en, en)}


def _hw_tw_bilingual(lst: list | None) -> list[dict[str, str]]:
    """Convert list of EN label strings to bilingual dicts."""
    if not lst:
        return []
    return [_label_pair(item) for item in lst if isinstance(item, str)]


def _real_rate_regime_label(raw: str | None) -> dict[str, str] | None:
    if not raw:
        return None
    pair = _REAL_RATE_REGIME_LABELS.get(raw)
    if pair:
        return {"en": pair[0], "zh": pair[1]}
    # Fallback: return raw string both languages
    return {"en": raw, "zh": raw}


# ---------------------------------------------------------------------------
# Task 1a: compose_dollar_channel
# ---------------------------------------------------------------------------

def compose_dollar_channel(root=None) -> dict | None:
    """Read data/forex/latest.json and return a dollar-channel context dict.

    Returns None if the file is absent or unreadable.  All sub-fields are
    fail-open (absent key → None).  display_only=True on the output.

    REAL ARTIFACT NOTES (inspected 2026-07-17):
    - transmission.usd_roc_pct is NOT in the artifact (it is computed inside
      engine/forex_transmission.py but not persisted to latest.json).  roc_pct
      is therefore always None.
    - regime_radar.active is a list of active scenario key strings (or dicts
      from older builds) — may be empty.  n_active is derived from len(active).
    - dollar_desk.real_rate_regime is a full string ("Restrictive real yields"),
      not a key.
    - regime_radar has dominant (str | null), active (list), intensity (dict),
      as_of (str) — NOT a scenarios[] sub-list with labels.
    """
    data_dir = _data_root(root)
    path = data_dir / "forex" / "latest.json"

    raw = _read_json(path)
    if raw is None:
        return None

    try:
        dd  = raw.get("dollar_desk") or {}
        tx  = raw.get("transmission") or {}
        rr  = raw.get("regime_radar") or {}

        usd_dir = tx.get("usd_dir") or None

        # regime_radar active list: may be list of strings or list of dicts
        active_raw = rr.get("active") or []
        n_active = len(active_raw) if isinstance(active_raw, list) else 0
        dominant = rr.get("dominant") or None

        # Build scenario label from dominant key
        scenario: dict | None = None
        if dominant and isinstance(dominant, str):
            pair = _SCENARIO_LABELS.get(dominant, (dominant, dominant))
            scenario = {
                "key": dominant,
                "label": {"en": pair[0], "zh": pair[1]},
                "n_active": n_active,
            }

        # Normalize asof
        asof_raw = raw.get("asof") or raw.get("date")
        try:
            import re as _re
            # If it's already ISO ("2026-07-17") keep it; else try to parse
            if asof_raw and _re.match(r"\d{4}-\d{2}-\d{2}", str(asof_raw)):
                asof = str(asof_raw)[:10]
            elif asof_raw:
                # display-string like "Jul 17, 2026"
                from datetime import datetime
                asof = datetime.strptime(str(asof_raw), "%b %d, %Y").strftime("%Y-%m-%d")
            else:
                asof = None
        except Exception:
            asof = str(asof_raw) if asof_raw else None

        return {
            "asof": asof,
            "usd_dir": usd_dir,
            "roc_pct": None,  # not persisted in artifact — see docstring
            "state": _USD_STATE.get(usd_dir, {"en": "Unknown", "zh": "未知"}) if usd_dir else None,
            "regime": _real_rate_regime_label(dd.get("real_rate_regime")),
            "lean": dd.get("lean"),
            "liquidity_dir": dd.get("liquidity_dir"),
            "headwind_for": _hw_tw_bilingual(tx.get("headwind_for")),
            "tailwind_for": _hw_tw_bilingual(tx.get("tailwind_for")),
            "corr": tx.get("corr"),
            "scenario": scenario,
            "display_only": True,
        }
    except Exception as exc:
        log.warning("transmission_context.compose_dollar_channel failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Task 1b: compact_state
# ---------------------------------------------------------------------------

def compact_state(contract: dict, dx: dict | None) -> dict:
    """Extract a comparison fingerprint from a transmission contract + dollar channel.

    ``contract`` is the dict that build_transmission writes to
    data/transmission/latest.json (includes state, yield_curve, headwinds,
    tailwinds, breakeven_decomp keys from rate_inflation_transmission.snapshot()).
    ``dx`` is the output of compose_dollar_channel().

    All keys fail-open to None / [].
    """
    def _g(*path, src=None):
        """Safe nested get."""
        obj = contract if src is None else src
        for p in path:
            if not isinstance(obj, dict):
                return None
            obj = obj.get(p)
        return obj

    state = _g("state") or {}
    rates  = state.get("rates") or {} if isinstance(state, dict) else {}
    infl   = state.get("inflation") or {} if isinstance(state, dict) else {}
    exp    = state.get("expectations") or {} if isinstance(state, dict) else {}

    yc_raw = _g("yield_curve") or {}
    yc_regime = (yc_raw.get("regime") or {}) if isinstance(yc_raw, dict) else {}
    yc_rec    = (yc_raw.get("recession") or {}) if isinstance(yc_raw, dict) else {}

    bd = _g("breakeven_decomp") or {}
    cause_badge = (bd.get("cause_badge") or {}) if isinstance(bd, dict) else {}

    # headwinds/tailwinds: list of dicts with label.en or just label string
    def _label_list(lst):
        out = []
        for item in (lst or []):
            if not isinstance(item, dict):
                continue
            lbl = item.get("label")
            if isinstance(lbl, dict):
                out.append(lbl.get("en") or lbl.get("zh") or "")
            elif isinstance(lbl, str):
                out.append(lbl)
        return sorted(out)

    dx = dx or {}
    return {
        "rates_regime":  rates.get("regime"),
        "rates_dir":     rates.get("direction"),
        "infl_regime":   infl.get("regime"),
        "infl_dir":      infl.get("direction"),
        "anchoring":     exp.get("anchoring"),
        "be_cause":      cause_badge.get("cause"),
        "curve_regime":  yc_regime.get("key"),
        "rec_flags":     yc_rec.get("n_flags"),
        "usd_dir":       dx.get("usd_dir"),
        "fx_scenario":   (dx.get("scenario") or {}).get("key") if dx.get("scenario") else None,
        "headwinds":     _label_list(contract.get("headwinds")),
        "tailwinds":     _label_list(contract.get("tailwinds")),
    }


# ---------------------------------------------------------------------------
# Task 1c: diff_changes
# ---------------------------------------------------------------------------

# Importance order for cap enforcement
_DIFF_ORDER = [
    "curve_regime",
    "rates_regime",
    "usd_dir",
    "infl_regime",
    "infl_dir",
    "anchoring",
    "fx_scenario",
    "be_cause",
    "rec_flags",
    "_headwinds_added",
    "_headwinds_removed",
    "_tailwinds_added",
    "_tailwinds_removed",
]

_MAX_CHANGES = 6


def _curve_sentence(old: str | None, new: str | None) -> tuple[str, str]:
    oe, oz = _CURVE_REGIME_LABELS.get(old or "", (old or "—", old or "—"))
    ne, nz = _CURVE_REGIME_LABELS.get(new or "", (new or "—", new or "—"))
    return (f"Curve regime changed: {oe} → {ne}",
            f"曲线形态转变：{oz} → {nz}")


def _rates_sentence(old: str | None, new: str | None) -> tuple[str, str]:
    oe, oz = _RATES_REGIME_LABELS.get(old or "", (old or "—", old or "—"))
    ne, nz = _RATES_REGIME_LABELS.get(new or "", (new or "—", new or "—"))
    return (f"Rates regime shifted: {oe} → {ne}",
            f"利率环境切换：{oz} → {nz}")


def _usd_sentence(old: str | None, new: str | None) -> tuple[str, str]:
    oe, oz = _USD_DIR_LABELS.get(old or "", (old or "—", old or "—"))
    ne, nz = _USD_DIR_LABELS.get(new or "", (new or "—", new or "—"))
    return (f"The dollar turned: {oe} → {ne}",
            f"美元转向：{oz} → {nz}")


def _infl_sentence(old_r, new_r, old_d, new_d) -> tuple[str, str]:
    r_part = f"{old_r or '—'} → {new_r or '—'}" if old_r != new_r else old_r or "—"
    d_part = f"{old_d or '—'} → {new_d or '—'}" if old_d != new_d else old_d or "—"
    r_zh = {"above target": "高于目标", "at target": "达标", "below target": "低于目标"}
    d_zh = {"re-accelerating": "再加速", "cooling": "降温", "steady": "平稳"}
    r_pz = f"{r_zh.get(old_r, old_r or '—')} → {r_zh.get(new_r, new_r or '—')}" if old_r != new_r else r_zh.get(old_r, old_r or "—")
    d_pz = f"{d_zh.get(old_d, old_d or '—')} → {d_zh.get(new_d, new_d or '—')}" if old_d != new_d else d_zh.get(old_d, old_d or "—")
    return (f"Inflation: {r_part}, {d_part}",
            f"通胀：{r_pz}，{d_pz}")


def _anchor_sentence(old: str | None, new: str | None) -> tuple[str, str]:
    a_zh = {"anchored": "锚定", "drifting up": "上行脱锚", "drifting down": "下行"}
    return (f"Inflation expectations shifted: {old or '—'} → {new or '—'}",
            f"通胀预期变化：{a_zh.get(old, old or '—')} → {a_zh.get(new, new or '—')}")


def _scenario_sentence(old: str | None, new: str | None) -> tuple[str, str]:
    oe, oz = _SCENARIO_LABELS.get(old or "", (old or "none", old or "无"))
    ne, nz = _SCENARIO_LABELS.get(new or "", (new or "none", new or "无"))
    return (f"FX stress scenario: {oe} → {ne}",
            f"外汇压力情景：{oz} → {nz}")


def _be_cause_sentence(old: str | None, new: str | None) -> tuple[str, str]:
    bc_zh = {
        "real_rate": "实际利率", "oil": "油价", "growth": "增长预期",
        "liquidity": "流动性", "reflation": "再通胀", "quiet": "平稳",
    }
    oe = old or "—"; oz = bc_zh.get(old or "", old or "—")
    ne = new or "—"; nz = bc_zh.get(new or "", new or "—")
    return (f"Breakeven driver changed: {oe} → {ne}",
            f"盈亏平衡驱动因素变化：{oz} → {nz}")


def _rec_flags_sentence(old, new) -> tuple[str, str]:
    return (f"Recession flags: {old} of 4 → {new} of 4",
            f"衰退信号：4项中{old}项 → {new}项")


def diff_changes(prev: dict, curr: dict) -> list[dict]:
    """Compare two compact_state dicts; emit at most 6 change items.

    Items ordered by importance (see _DIFF_ORDER).  None-side transitions
    are skipped (no noise on first appearance).  Returns [].
    """
    candidates: list[tuple[int, dict]] = []

    def _add(key: str, old, new, en: str, zh: str):
        if old is None or new is None:
            return
        if old == new:
            return
        idx = _DIFF_ORDER.index(key) if key in _DIFF_ORDER else 99
        candidates.append((idx, {
            "key": key, "from": old, "to": new, "en": en, "zh": zh,
        }))

    # Scalar changes
    if prev.get("curve_regime") != curr.get("curve_regime"):
        en, zh = _curve_sentence(prev.get("curve_regime"), curr.get("curve_regime"))
        _add("curve_regime", prev.get("curve_regime"), curr.get("curve_regime"), en, zh)

    if prev.get("rates_regime") != curr.get("rates_regime"):
        en, zh = _rates_sentence(prev.get("rates_regime"), curr.get("rates_regime"))
        _add("rates_regime", prev.get("rates_regime"), curr.get("rates_regime"), en, zh)

    if prev.get("usd_dir") != curr.get("usd_dir"):
        en, zh = _usd_sentence(prev.get("usd_dir"), curr.get("usd_dir"))
        _add("usd_dir", prev.get("usd_dir"), curr.get("usd_dir"), en, zh)

    # Inflation: emit as one item if either sub-key changed
    ir_changed = prev.get("infl_regime") != curr.get("infl_regime")
    id_changed = prev.get("infl_dir") != curr.get("infl_dir")
    if ir_changed or id_changed:
        if prev.get("infl_regime") is not None or curr.get("infl_regime") is not None:
            en, zh = _infl_sentence(
                prev.get("infl_regime"), curr.get("infl_regime"),
                prev.get("infl_dir"), curr.get("infl_dir"),
            )
            # Use infl_regime slot for ordering
            old_val = (prev.get("infl_regime"), prev.get("infl_dir"))
            new_val = (curr.get("infl_regime"), curr.get("infl_dir"))
            if old_val != new_val and prev.get("infl_regime") is not None and curr.get("infl_regime") is not None:
                idx = _DIFF_ORDER.index("infl_regime")
                candidates.append((idx, {
                    "key": "infl_regime",
                    "from": old_val,
                    "to": new_val,
                    "en": en,
                    "zh": zh,
                }))

    if prev.get("anchoring") != curr.get("anchoring"):
        en, zh = _anchor_sentence(prev.get("anchoring"), curr.get("anchoring"))
        _add("anchoring", prev.get("anchoring"), curr.get("anchoring"), en, zh)

    if prev.get("fx_scenario") != curr.get("fx_scenario"):
        en, zh = _scenario_sentence(prev.get("fx_scenario"), curr.get("fx_scenario"))
        _add("fx_scenario", prev.get("fx_scenario"), curr.get("fx_scenario"), en, zh)

    if prev.get("be_cause") != curr.get("be_cause"):
        en, zh = _be_cause_sentence(prev.get("be_cause"), curr.get("be_cause"))
        _add("be_cause", prev.get("be_cause"), curr.get("be_cause"), en, zh)

    # rec_flags: emit only when count changes
    rf_old = prev.get("rec_flags")
    rf_new = curr.get("rec_flags")
    if rf_old is not None and rf_new is not None and rf_old != rf_new:
        en, zh = _rec_flags_sentence(rf_old, rf_new)
        idx = _DIFF_ORDER.index("rec_flags")
        candidates.append((idx, {
            "key": "rec_flags", "from": rf_old, "to": rf_new, "en": en, "zh": zh,
        }))

    # Headwind/tailwind set membership changes
    hw_prev = set(prev.get("headwinds") or [])
    hw_curr = set(curr.get("headwinds") or [])
    for asset in sorted(hw_curr - hw_prev):
        idx = _DIFF_ORDER.index("_headwinds_added")
        candidates.append((idx, {
            "key": "headwind_added", "from": None, "to": asset,
            "en": f"{asset} moved into the headwind column",
            "zh": f"{_HW_TW_LABEL_ZH.get(asset, asset)}转入逆风",
        }))
    for asset in sorted(hw_prev - hw_curr):
        idx = _DIFF_ORDER.index("_headwinds_removed")
        candidates.append((idx, {
            "key": "headwind_removed", "from": asset, "to": None,
            "en": f"{asset} left the headwind column",
            "zh": f"{_HW_TW_LABEL_ZH.get(asset, asset)}移出逆风",
        }))

    tw_prev = set(prev.get("tailwinds") or [])
    tw_curr = set(curr.get("tailwinds") or [])
    for asset in sorted(tw_curr - tw_prev):
        idx = _DIFF_ORDER.index("_tailwinds_added")
        candidates.append((idx, {
            "key": "tailwind_added", "from": None, "to": asset,
            "en": f"{asset} moved into the tailwind column",
            "zh": f"{_HW_TW_LABEL_ZH.get(asset, asset)}转入顺风",
        }))
    for asset in sorted(tw_prev - tw_curr):
        idx = _DIFF_ORDER.index("_tailwinds_removed")
        candidates.append((idx, {
            "key": "tailwind_removed", "from": asset, "to": None,
            "en": f"{asset} left the tailwind column",
            "zh": f"{_HW_TW_LABEL_ZH.get(asset, asset)}移出顺风",
        }))

    # Sort by importance, cap at _MAX_CHANGES
    candidates.sort(key=lambda x: x[0])
    return [item for _, item in candidates[:_MAX_CHANGES]]


# ---------------------------------------------------------------------------
# Task 1d: build_changes
# ---------------------------------------------------------------------------

def build_changes(
    old_contract: dict | None,
    new_contract: dict,
    dx: dict | None,
    new_asof: str,
) -> tuple[dict, dict]:
    """Same-day-idempotent changes block builder.

    Returns (changes_block, prev_state_block).

    Semantics:
    - old_contract is None (first run): empty changes, no prev_state.
    - old_contract["asof"] != new_asof: diff old → new (new day).
    - old_contract["asof"] == new_asof (same-day rebuild): reuse the
      prev_state already stored in old_contract so re-renders don't wipe
      the day's accumulated diff.
    """
    if old_contract is None:
        return (
            {"vs_asof": None, "items": []},
            {"as_of": None, "state": {}},
        )

    new_cs = compact_state(new_contract, dx)
    old_asof = old_contract.get("asof")

    if old_asof != new_asof:
        # New day — diff against yesterday's full state
        old_dx = old_contract.get("dollar_channel")
        base = compact_state(old_contract, old_dx)
        base_asof = old_asof
    else:
        # Same-day rebuild — reuse prev_state so changes accumulate correctly
        prev_state_stored = old_contract.get("prev_state") or {}
        base = prev_state_stored.get("state") or {}
        base_asof = prev_state_stored.get("as_of")

    if base_asof is None or not base:
        # No genuine baseline (feature's first day, or a same-day rebuild whose
        # predecessor carried no history) — emit no items rather than phantom
        # "appeared from nothing" set diffs.
        items = []
    else:
        items = diff_changes(base, new_cs)
    changes = {"vs_asof": base_asof, "items": items}
    prev_state = {"as_of": base_asof, "state": base}

    return changes, prev_state


# ---------------------------------------------------------------------------
# Task 1e: compose_hero
# ---------------------------------------------------------------------------

# All state/stance mappings: (rates_regime, rates_dir) → (state_en, state_zh)
_RATES_STATE: dict[tuple[str, str], tuple[str, str]] = {
    ("restrictive", "rising"):  ("High & rising", "高位上行"),
    ("restrictive", "stable"):  ("High & holding", "高位持稳"),
    ("restrictive", "falling"): ("High & easing", "高位回落"),
    ("neutral", "rising"):      ("Rising toward tight", "趋向偏紧"),
    ("neutral", "stable"):      ("Steady", "平稳"),
    ("neutral", "falling"):     ("Easing", "趋向宽松"),
    ("accommodative", "rising"):  ("Easy & rising", "宽松中上行"),
    ("accommodative", "stable"):  ("Easy & holding", "宽松持稳"),
    ("accommodative", "falling"): ("Easy & falling", "宽松走低"),
}

_RATES_STANCE: dict[tuple[str, str], tuple[str, str]] = {
    ("restrictive", "rising"):  ("Headwind building — watch", "逆风累积 — 观察"),
    ("restrictive", "stable"):  ("Headwind holding — watch", "逆风持续 — 观察"),
    ("restrictive", "falling"): ("Headwind easing — watch", "逆风减弱 — 观察"),
    ("neutral", "rising"):      ("Watch — conditions shifting", "观察 — 环境转变中"),
    ("neutral", "stable"):      ("No action needed", "无需行动"),
    ("neutral", "falling"):     ("Supportive — no action needed", "偏利好 — 无需行动"),
    ("accommodative", "rising"):  ("Easy backdrop — watch for turn", "宽松环境 — 观察拐点"),
    ("accommodative", "stable"):  ("Supportive — no action needed", "偏利好 — 无需行动"),
    ("accommodative", "falling"): ("Very supportive — no action needed", "强利好 — 无需行动"),
}

# (infl_regime, infl_dir) → (state_en, state_zh)
_INFL_STATE: dict[tuple[str, str], tuple[str, str]] = {
    ("above target", "re-accelerating"): ("Re-heating above target", "高于目标且再度升温"),
    ("above target", "steady"):          ("Sticky above target", "高于目标且粘性"),
    ("above target", "cooling"):         ("Cooling toward target", "降温接近目标"),
    ("at target", "re-accelerating"):    ("Ticking back up", "小幅上行"),
    ("at target", "steady"):             ("On target", "达标"),
    ("at target", "cooling"):            ("Below target soon", "即将低于目标"),
    ("below target", "re-accelerating"): ("Recovering toward target", "回升中"),
    ("below target", "steady"):          ("Below target, stable", "低于目标，平稳"),
    ("below target", "cooling"):         ("Falling below target", "低于目标且下行"),
}

_INFL_STANCE: dict[tuple[str, str], tuple[str, str]] = {
    ("above target", "re-accelerating"): ("Get ready — inflation pressure building", "准备行动 — 通胀压力上升"),
    ("above target", "steady"):          ("Watch — still above target", "观察 — 仍高于目标"),
    ("above target", "cooling"):         ("Supportive — no action needed", "偏利好 — 无需行动"),
    ("at target", "re-accelerating"):    ("Watch — may drift up", "观察 — 可能上行"),
    ("at target", "steady"):             ("No action needed", "无需行动"),
    ("at target", "cooling"):            ("No action needed", "无需行动"),
    ("below target", "re-accelerating"): ("No action needed", "无需行动"),
    ("below target", "steady"):          ("No action needed", "无需行动"),
    ("below target", "cooling"):         ("Supportive — no action needed", "偏利好 — 无需行动"),
}

_USD_STANCE: dict[str, tuple[str, str]] = {
    "strengthening": ("Headwind building — watch", "逆风累积 — 观察"),
    "weakening":     ("Tailwind — watch for reversal", "顺风 — 观察反转"),
    "flat":          ("Quiet — ignore for now", "平静 — 暂可忽略"),
}

_DEFAULT_STANCE = ("Watch", "观察")


def _bil(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


def compose_hero(tx: dict, dx: dict | None) -> dict:
    """Deterministic one-line verdict + per-channel stances for the page hero.

    ``tx`` is the transmission contract (rate_inflation_transmission.snapshot()
    output, as written to data/transmission/latest.json).
    ``dx`` is compose_dollar_channel() output (may be None).

    Never raises.
    """
    try:
        dx = dx or {}
        state = (tx.get("state") or {}) if isinstance(tx, dict) else {}
        rates_block = (state.get("rates") or {}) if isinstance(state, dict) else {}
        infl_block  = (state.get("inflation") or {}) if isinstance(state, dict) else {}

        r_reg = rates_block.get("regime") or "neutral"
        r_dir = rates_block.get("direction") or "stable"
        i_reg = infl_block.get("regime") or "at target"
        i_dir = infl_block.get("direction") or "steady"
        usd_dir = dx.get("usd_dir")

        rk = (r_reg, r_dir)
        ik = (i_reg, i_dir)

        r_state_en, r_state_zh = _RATES_STATE.get(rk, (f"{r_reg}, {r_dir}", f"{r_reg}, {r_dir}"))
        r_stance_en, r_stance_zh = _RATES_STANCE.get(rk, _DEFAULT_STANCE)

        i_state_en, i_state_zh = _INFL_STATE.get(ik, (f"{i_reg}, {i_dir}", f"{i_reg}, {i_dir}"))
        i_stance_en, i_stance_zh = _INFL_STANCE.get(ik, _DEFAULT_STANCE)

        # One-sentence verdict (≤ ~20 words). When the dollar read is absent
        # (stale/missing forex artifact), the sentence simply omits the dollar —
        # a missing read is never presented as a real "flat" stance.
        if usd_dir:
            usd_state = _USD_STATE.get(usd_dir, {"en": "Unknown", "zh": "未知"})
            usd_stance_en, usd_stance_zh = _USD_STANCE.get(usd_dir, _DEFAULT_STANCE)
            line_en = (
                f"Rates are {r_state_en.lower()}, "
                f"inflation is {i_state_en.lower()}, "
                f"and the dollar is {usd_state['en'].lower()}."
            )
            line_zh = f"利率{r_state_zh}，通胀{i_state_zh}，美元{usd_state['zh']}。"
        else:
            usd_state = {"en": "No read", "zh": "暂无读数"}
            usd_stance_en, usd_stance_zh = "—", "—"
            line_en = (
                f"Rates are {r_state_en.lower()}, "
                f"and inflation is {i_state_en.lower()}."
            )
            line_zh = f"利率{r_state_zh}，通胀{i_state_zh}。"

        return {
            "line":      _bil(line_en, line_zh),
            "rates":     {"state": _bil(r_state_en, r_state_zh),
                          "stance": _bil(r_stance_en, r_stance_zh)},
            "inflation": {"state": _bil(i_state_en, i_state_zh),
                          "stance": _bil(i_stance_en, i_stance_zh)},
            "dollar":    {"state": usd_state,
                          "stance": _bil(usd_stance_en, usd_stance_zh)},
        }
    except Exception as exc:
        log.warning("transmission_context.compose_hero failed: %s", exc)
        return {
            "line":      _bil("Context unavailable.", "上下文不可用。"),
            "rates":     {"state": _bil("—", "—"), "stance": _bil("Watch", "观察")},
            "inflation": {"state": _bil("—", "—"), "stance": _bil("Watch", "观察")},
            "dollar":    {"state": _bil("—", "—"), "stance": _bil("Watch", "观察")},
        }
