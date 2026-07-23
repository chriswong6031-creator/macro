"""Dark-pool positioning context — turns the raw off-exchange desk into an
actionable, plain-word read plus a same-day-idempotent change-feed.

WHAT THIS IS (and is not)
-------------------------
The Dark Pool desk reports, per name, what share of the day's volume printed
off-exchange (`oe_share` = FINRA-facility volume ÷ consolidated volume), how that
compares to the name's own history (`oe_z`), and how short-marked that off-exchange
selling is (`short_ratio`, `trend_pp` = recent-minus-baseline short ratio in pp,
`ratio_z` = short ratio vs own norm).

Off-exchange volume hides *who* is trading, so on its own it cannot call direction.
Pairing heavy, unusual-vs-own-norm dark volume with the *change* in short-marked
selling gives an honest LEAN — a heads-up to watch, never a buy or sell call:

    accumulation  heavy dark volume, short-marking light or fading      → leaning up
    distribution  heavy dark volume, short-marking building fast         → leaning down
    unusual       heavy dark volume, short-marking mixed/flat            → direction unclear

EPISTEMICS (house law)
----------------------
Every tag here is a DETERMINISTIC threshold on already-observed data — no model, no
LLM origination, no score with authority. This is display / context tier only
(is_context_only=True, display_only=True): it never gates, ranks, sizes, or escalates
any surface, and the word "validated" is never emitted. Roughly half of off-exchange
volume is short-marked by default, so we read the short-marking *trend* and each name's
*own norm* — never the raw level. Mirrors the existing `short_volume.py` /
`altdata.offexchange_flow` "context confirmer, not a scored factor" discipline.

The change-feed (compact_state / diff_changes / build_changes) mirrors
`transmission_context` exactly: same-day rebuilds reuse the stored prev_state so the
day's accumulated diff is never wiped.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA = "darkpool_context.v1"

# ── Standout + lean thresholds (deterministic; documented on the page) ──────────
STANDOUT_Z   = 1.5    # oe_z ≥ this → off-exchange share unusually high vs own norm
STANDOUT_OE  = 0.40   # and ≥ 40% of the day's volume printed off-exchange
ACC_TREND    = -2.0   # short-marking fading ≥ 2pp vs baseline → accumulation lean
ACC_RZ       = -0.75  # …or short ratio ≥ 0.75σ below the name's own norm
DIS_TREND    = 4.0    # short-marking building ≥ 4pp vs baseline → distribution lean
DIS_RZ       = 1.0    # …or short ratio ≥ 1σ above the name's own norm
BOARD_CAP    = 16     # standouts laid out on the glance board (rest live in the desk)
VENUE_MOVE   = 1.0    # |WoW share change| ≥ this (pp) → a venue "mover"

_LEAN_KEYS = ("accumulation", "distribution", "unusual")


# ── plain-word copy (bilingual; ZH kept equally plain — house doctrine) ─────────
_LEAN_LABEL = {
    "accumulation": {"en": "Quiet accumulation", "zh": "悄然吸筹"},
    "distribution": {"en": "Distribution pressure", "zh": "派发压力"},
    "unusual":      {"en": "Unusual, unclear", "zh": "异常但方向不明"},
}
_LEAN_DIR = {
    "accumulation": {"en": "leaning up", "zh": "偏多"},
    "distribution": {"en": "leaning down", "zh": "偏空"},
    "unusual":      {"en": "off their norm", "zh": "偏离常态"},
}
_LEAN_READ = {
    "accumulation": {
        "en": "Big blocks trading in the dark while short-marked selling stays light — "
              "the footprint left when institutions build a position quietly.",
        "zh": "大额成交在暗池进行，而卖空标记偏轻——机构悄然建仓时留下的痕迹。",
    },
    "distribution": {
        "en": "Heavy dark volume with short-marked selling building faster than usual for "
              "the name — the footprint of quiet distribution or a short campaign.",
        "zh": "暗池成交沉重，且卖空标记的增速快于该股常态——悄然派发或做空行动的痕迹。",
    },
    "unusual": {
        "en": "Off-exchange share is running well above each name's own baseline, but "
              "short-marked selling is mixed — something is happening, direction not yet readable.",
        "zh": "场外占比明显高于各自基线，但卖空标记方向不一——有异动，但方向尚不明朗。",
    },
}
_LEAN_STANCE = {
    "accumulation": {"en": "Watch — don't chase", "zh": "观察——勿追高"},
    "distribution": {"en": "Watch for weakness", "zh": "留意走弱"},
    "unusual":      {"en": "Watch closely", "zh": "密切观察"},
}


# ── per-name label helpers ──────────────────────────────────────────────────────

def _norm_label(oe_z: float | None) -> dict:
    """Plain-word 'vs its own norm' from oe_z (already display-tier on the desk)."""
    if oe_z is None:
        return {"en": "—", "zh": "—"}
    if oe_z >= 2.5:
        return {"en": "Far above", "zh": "远超常态"}
    if oe_z >= 1.5:
        return {"en": "Well above", "zh": "明显高于"}
    return {"en": "Above", "zh": "高于常态"}


def _short_label(trend_pp: float | None, short_ratio: float | None, ratio_z: float | None) -> dict:
    """Plain-word short-marking read, leaning on the CHANGE not the raw level."""
    if trend_pp is not None and trend_pp >= DIS_TREND:
        return {"en": f"Building ▲{abs(trend_pp):.0f}pp", "zh": f"上升 ▲{abs(trend_pp):.0f}pp"}
    if trend_pp is not None and trend_pp <= ACC_TREND:
        return {"en": f"Fading ▼{abs(trend_pp):.0f}pp", "zh": f"回落 ▼{abs(trend_pp):.0f}pp"}
    if ratio_z is not None and ratio_z <= ACC_RZ:
        return {"en": "Light vs norm", "zh": "低于常态"}
    if ratio_z is not None and ratio_z >= DIS_RZ:
        return {"en": "Heavy vs norm", "zh": "高于常态"}
    return {"en": "About normal", "zh": "大致正常"}


def _name_read(lean: str, oe_share: float | None, trend_pp: float | None) -> dict:
    """One-line, name-level plain read for the standout card."""
    if lean == "accumulation":
        return {
            "en": "Heavy dark footprint and short-marked selling backing off — a quiet-accumulation lean.",
            "zh": "暗池痕迹沉重、卖空标记回落——偏向悄然吸筹。",
        }
    if lean == "distribution":
        return {
            "en": "Dark volume elevated and short-marked selling climbing fast — a distribution lean.",
            "zh": "暗池成交偏高、卖空标记快速攀升——偏向派发。",
        }
    return {
        "en": "Dark volume well above its norm with mixed short-marking — heavy activity, direction unclear.",
        "zh": "暗池成交远高于常态、卖空标记不一——异动明显，方向不明。",
    }


# ── classification ──────────────────────────────────────────────────────────────

def classify(row: dict) -> str | None:
    """Deterministic lean tag for one desk row, or None if the name is not a standout.

    A *standout* has off-exchange share both unusually high vs its own norm
    (oe_z ≥ STANDOUT_Z) and materially dark (oe_share ≥ STANDOUT_OE). Requires
    oe_z (needs ≥20 matched days upstream) — names without enough history are
    never tagged (honest-null, not forced).
    """
    oe_z = row.get("oe_z")
    oe = row.get("oe_share")
    if oe_z is None or oe is None:
        return None
    if oe_z < STANDOUT_Z or oe < STANDOUT_OE:
        return None

    tpp = row.get("trend_pp")
    rz = row.get("ratio_z")
    building = (tpp is not None and tpp >= DIS_TREND) or (rz is not None and rz >= DIS_RZ)
    fading = (tpp is not None and tpp <= ACC_TREND) or (rz is not None and rz <= ACC_RZ)
    if building and not fading:
        return "distribution"
    if fading and not building:
        return "accumulation"
    return "unusual"


def _conviction(row: dict) -> float:
    """Display-only ordering key for the standout board (NOT a scored signal).

    Bigger = more worth a look: more unusual vs norm, deeper in the dark, and a
    stronger short-marking swing either way.
    """
    oe_z = row.get("oe_z") or 0.0
    oe = row.get("oe_share") or 0.0
    tpp = abs(row.get("trend_pp") or 0.0)
    return float(oe_z) + 2.0 * float(oe) + min(tpp / 10.0, 1.0)


# ── snapshot ────────────────────────────────────────────────────────────────────

def _hero(tally: dict) -> dict:
    """Deterministic plain-word verdict from the balance of leans."""
    acc, dis, unc = tally["accumulation"], tally["distribution"], tally["unusual"]
    total = acc + dis + unc
    if total == 0:
        return {
            "en": "Off-exchange activity is quiet today — no names are trading unusually in the dark.",
            "zh": "今日场外活动平静——没有个股在暗池出现异常成交。",
        }
    if acc > dis:
        return {
            "en": f"Hidden volume is running hot in {total} names — quiet-accumulation "
                  f"footprints lead distribution, {acc} to {dis}.",
            "zh": f"暗池成交在{total}只个股中异常活跃——悄然吸筹的痕迹以{acc}比{dis}领先派发。",
        }
    if dis > acc:
        return {
            "en": f"Hidden volume is running hot in {total} names — distribution "
                  f"footprints lead accumulation, {dis} to {acc}.",
            "zh": f"暗池成交在{total}只个股中异常活跃——派发的痕迹以{dis}比{acc}领先吸筹。",
        }
    return {
        "en": f"Hidden volume is running hot in {total} names — accumulation and "
              f"distribution footprints are balanced, {acc} each.",
        "zh": f"暗池成交在{total}只个股中异常活跃——吸筹与派发的痕迹势均力敌，各{acc}只。",
    }


def _venue_block(ats_table: dict | None) -> dict:
    """Prettified venue rollup: top venues by share + the biggest WoW mover."""
    if not ats_table or not ats_table.get("venues"):
        return {"week_start": None, "lag_note": None, "top": [], "mover": None}
    top = []
    for v in ats_table["venues"][:8]:
        top.append({
            "name": v.get("venue_name") or v.get("mpid"),
            "mpid": v.get("mpid"),
            "share_pct": v.get("share_of_total_pct"),
            "wow_pp": v.get("wow_pp"),
            "is_new": bool(v.get("wow_is_new")),
        })
    # mover = largest |WoW| among established venues, or the first genuinely-new one
    movers = [v for v in ats_table["venues"]
              if v.get("wow_pp") is not None and abs(v["wow_pp"]) >= VENUE_MOVE and not v.get("wow_is_new")]
    mover = None
    if movers:
        m = max(movers, key=lambda v: abs(v["wow_pp"]))
        mover = {"name": m.get("venue_name") or m.get("mpid"), "mpid": m.get("mpid"),
                 "wow_pp": m.get("wow_pp"), "share_pct": m.get("share_of_total_pct")}
    return {
        "week_start": ats_table.get("week_start"),
        "lag_note": ats_table.get("lag_note") or "2–4 wk publication lag",
        "top": top,
        "mover": mover,
    }


def build_snapshot(rows: list[dict], ats_table: dict | None, asof: str) -> dict:
    """Classify the desk rows into leans + a laid-out standout board + hero verdict.

    Returns the display payload consumed by the page template and (compactly) by the
    Neural Web lobe. Pure — no IO.
    """
    tagged: list[tuple[str, dict]] = []
    for r in rows:
        lean = classify(r)
        if lean is not None:
            tagged.append((lean, r))

    tally = {k: sum(1 for lean, _ in tagged if lean == k) for k in _LEAN_KEYS}

    leans: dict = {}
    for k in _LEAN_KEYS:
        names = [r["ticker"] for lean, r in
                 sorted((t for t in tagged if t[0] == k), key=lambda t: -_conviction(t[1]))]
        leans[k] = {
            "n": tally[k],
            "label": _LEAN_LABEL[k],
            "dir": _LEAN_DIR[k],
            "read": _LEAN_READ[k],
            "stance": _LEAN_STANCE[k],
            "names": names,
        }

    standouts = []
    for lean, r in sorted(tagged, key=lambda t: -_conviction(t[1]))[:BOARD_CAP]:
        standouts.append({
            "ticker": r.get("ticker"),
            "lean": lean,
            "lean_label": _LEAN_LABEL[lean],
            "oe_share": r.get("oe_share"),
            "oe_share_40d": r.get("oe_share_40d"),   # the name's own baseline → depth-bar 'norm' marker
            "oe_z": r.get("oe_z"),
            "oe_trend_pp": r.get("oe_trend_pp"),
            "short_ratio": r.get("short_ratio"),
            "trend_pp": r.get("trend_pp"),
            "ratio_z": r.get("ratio_z"),
            "ats_top_venue": r.get("ats_top_venue"),
            "norm_label": _norm_label(r.get("oe_z")),
            "short_label": _short_label(r.get("trend_pp"), r.get("short_ratio"), r.get("ratio_z")),
            "read": _name_read(lean, r.get("oe_share"), r.get("trend_pp")),
        })

    return {
        "asof": asof,
        "hero": _hero(tally),
        "tally": tally,
        "leans": leans,
        "standouts": standouts,
        "n_standouts": len(tagged),
        "venues": _venue_block(ats_table),
    }


# ── change-feed (mirrors engine/transmission_context.py idempotence) ────────────

_DIFF_ORDER = [
    "into_distribution", "into_accumulation", "into_unusual",
    "left_distribution", "left_accumulation", "left_unusual",
    "venue_mover", "venue_new",
]
_MAX_CHANGES = 6


def compact_state(snapshot: dict) -> dict:
    """Comparison fingerprint: which names sit in each lean + the venue leader/mover."""
    leans = snapshot.get("leans") or {}
    venues = snapshot.get("venues") or {}
    top = venues.get("top") or []
    return {
        "accumulation": sorted((leans.get("accumulation") or {}).get("names") or []),
        "distribution": sorted((leans.get("distribution") or {}).get("names") or []),
        "unusual": sorted((leans.get("unusual") or {}).get("names") or []),
        "venue_leader": top[0]["name"] if top else None,
        "venue_mover": (venues.get("mover") or {}).get("name") if venues.get("mover") else None,
        "venue_mover_pp": (venues.get("mover") or {}).get("wow_pp") if venues.get("mover") else None,
    }


def _names_phrase(names: list[str], zh: bool = False) -> str:
    """Join tickers into a plain phrase — connectors localised (tickers stay Latin)."""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}、{names[1]}" if zh else f"{names[0]} and {names[1]}"
    if zh:
        return f"{names[0]}、{names[1]} 等{len(names)}只"
    return f"{names[0]}, {names[1]} and {len(names) - 2} more"


def diff_changes(prev: dict, curr: dict) -> list[dict]:
    """≤6 bilingual change items between two compact_state dicts.

    First-appearance (empty prev) emits nothing to avoid phantom "appeared" diffs.
    """
    if not prev:
        return []
    candidates: list[tuple[int, dict]] = []

    def _add(key: str, en: str, zh: str):
        idx = _DIFF_ORDER.index(key) if key in _DIFF_ORDER else 99
        candidates.append((idx, {"key": key, "en": en, "zh": zh}))

    moves = [
        ("distribution", "into_distribution", "left_distribution",
         ("entered distribution watch", "进入派发观察"),
         ("left distribution watch", "移出派发观察")),
        ("accumulation", "into_accumulation", "left_accumulation",
         ("entered quiet-accumulation watch", "进入悄然吸筹观察"),
         ("left quiet-accumulation watch", "移出悄然吸筹观察")),
        ("unusual", "into_unusual", "left_unusual",
         ("flagged unusual dark activity", "出现异常暗池活动"),
         ("cleared unusual dark activity", "异常暗池活动消退")),
    ]
    for lean, in_key, out_key, (in_en, in_zh), (out_en, out_zh) in moves:
        pset, cset = set(prev.get(lean) or []), set(curr.get(lean) or [])
        entered = sorted(cset - pset)
        left = sorted(pset - cset)
        if entered:
            _add(in_key, f"{_names_phrase(entered)} {in_en}", f"{_names_phrase(entered, zh=True)}{in_zh}")
        if left:
            _add(out_key, f"{_names_phrase(left)} {out_en}", f"{_names_phrase(left, zh=True)}{out_zh}")

    # venue mover (WoW) — only when the mover changed identity or is fresh
    mover, pp = curr.get("venue_mover"), curr.get("venue_mover_pp")
    if mover and pp is not None and mover != prev.get("venue_mover"):
        arrow = "▲" if pp > 0 else "▼"
        _add("venue_mover",
             f"Venue: {mover} pool share {arrow}{abs(pp):.1f}pp",
             f"场所：{mover} 暗池占比 {arrow}{abs(pp):.1f}pp")

    candidates.sort(key=lambda x: x[0])
    return [item for _, item in candidates[:_MAX_CHANGES]]


def build_changes(old_contract: dict | None, new_snapshot: dict, new_asof: str) -> tuple[dict, dict]:
    """Same-day-idempotent (changes_block, prev_state_block). Mirrors transmission_context.

    - old_contract None (first run): empty changes.
    - new day: diff yesterday's state → today.
    - same-day rebuild: reuse stored prev_state so the day's diff isn't wiped.
    """
    if old_contract is None:
        return {"vs_asof": None, "items": []}, {"as_of": None, "state": {}}

    new_cs = compact_state(new_snapshot)
    old_asof = old_contract.get("asof")
    if old_asof != new_asof:
        base = compact_state(old_contract)   # old_contract carries the same top-level shape
        base_asof = old_asof
    else:
        prev_stored = old_contract.get("prev_state") or {}
        base = prev_stored.get("state") or {}
        base_asof = prev_stored.get("as_of")

    items = diff_changes(base, new_cs) if (base_asof and base) else []
    return {"vs_asof": base_asof, "items": items}, {"as_of": base_asof, "state": base}


# ── artifact assembly + persistence (the only IO in this module) ────────────────

def _default_path(root: Path | str | None = None) -> Path:
    if root is None:
        from lib import config
        root = config.ROOT
    return Path(root) / "data" / "darkpool" / "context" / "latest.json"


def build_context_feed(
    rows: list[dict],
    ats_table: dict | None,
    *,
    asof: str,
    built: str,
    tier: str = "eod",
    root: Path | str | None = None,
    write: bool = True,
) -> dict:
    """Assemble + (optionally) persist the darkpool_context.v1 artifact.

    Reads the prior artifact BEFORE overwriting so the change-feed can diff against
    it (same-day-idempotent via build_changes). Returns the full artifact — the page
    template renders it directly and the Neural Web lobe reads a compact projection.

    Fail-open by construction: a missing prior file just means empty changes; the
    caller (build_darkpool_desk) wraps this so it can never break the HTML desk.
    """
    out_path = _default_path(root)
    snapshot = build_snapshot(rows, ats_table, asof)

    old_contract: dict | None = None
    if out_path.exists():
        try:
            old_contract = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("darkpool_context: prior artifact unreadable (%s) — no change-feed", exc)

    changes, prev_state = build_changes(old_contract, snapshot, asof)

    artifact = {
        "schema": SCHEMA,
        "asof": asof,
        "built": built,
        "tier": tier,
        "is_context_only": True,
        "display_only": True,
        "hero": snapshot["hero"],
        "tally": snapshot["tally"],
        "leans": snapshot["leans"],
        "standouts": snapshot["standouts"],
        "n_standouts": snapshot["n_standouts"],
        "venues": snapshot["venues"],
        "changes": changes,
        "prev_state": prev_state,
    }

    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(artifact, ensure_ascii=False, separators=(",", ":")),
                            encoding="utf-8")
        log.info("wrote %s (%d standouts: %d acc / %d dist / %d unusual, %d changes)",
                 out_path, snapshot["n_standouts"], snapshot["tally"]["accumulation"],
                 snapshot["tally"]["distribution"], snapshot["tally"]["unusual"],
                 len(changes["items"]))

    return artifact
