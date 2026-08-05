"""engine/us_act_now.py — US Act-Now bottoming-watch lane assembler (W-A).

The US port of China's `bottoming_watch` lane + FT-R1 dual-read law
(`engine/china_act_now.py:348-391` is the pinned reference implementation; the CN
module is NOT touched by this port and remains the control).

Why this exists
---------------
The nightly US cycle engine writes `data/sector_cycles/forward_log.parquet`, which
on 2026-08-04 carried `b-gold_miners: phase=Trough, pos=2.0, osc_slope=+1.3,
signal=BUY` — while the Act board showed gold_miners on reduce/avoid (score 31,
rank 44/47) and nothing anywhere told the operator the cycle organ had turned.
China's board never buries a bottoming candidate because it has a dedicated lane
and a dual-read chip. This module gives the US board the same two mechanisms.

Scope / authority (G0.1)
------------------------
DISPLAY TIER, ZERO SCORED AUTHORITY. This assembler ranks nothing, gates nothing,
sizes nothing, and escalates nothing. It surfaces state the cycle engine already
computed and committed. The existing buy / wait / reduce lanes are read-only
inputs here — this module never adds to, removes from, or reorders them (G0.3).

Honest null (G0.4)
------------------
Sector washout→turn as a *scored trigger* is a measured NULL (Oracle P8 P-W1;
DO_NOT_REBUILD "Washout × turn"). So every row here is a disclosure of engine
state, never a buy claim. `authority.null_disclosure_en/zh` carries that in plain
words and the template prints it under the lane.

BUY-WORD PROHIBITION (mirrors CN F1/W8-R3)
------------------------------------------
The lane is a WATCH surface. No rendered string may use a buy/enter verb. Two
fields in the source row are buy-word carriers and are therefore **payload-only,
never rendered**:
  * `signal`       — the literal cycle-engine output, "BUY" | "SELL"
  * `timing_state` — vocabulary includes the literal value "FRESH BUY"
The template renders the fixed phrase "cycle turn signal — watch only" instead,
which is the masterplan §6 sanctioned form: the organ's registered output is
*quoted as the organ's*, with its trend-gate conflict printed beside it.
`tests/test_us_act_now.py` pins both halves.

Input
-----
cycle_rows  list[dict] | None
    Latest-date rows of `data/sector_cycles/forward_log.parquet`. Columns used:
    id, kind, name, phase, pos, osc_slope, signal, above200d, timing_state.
    None → lane empty + "log absent" note. [] → lane empty, no note.
reduce_ids  iterable[str] | None
    The ids already sitting in the Act board's reduce/avoid lane, used only to
    compute the dual-read id set. Never mutated.
names_zh    dict[str, str] | None
    Chinese display names by id. The forward log is English-only, so the caller
    supplies these from `theme_intel.themes[].name_zh` (baskets) and
    `sectordata/sector_central.json -> sectors[].name_zh` (sector ETFs).

Output
------
{
  'bottoming_watch': list[BottomingRow],   # sorted pos ASC, capped at BOTTOMING_CAP
  'dual_read_ids':   list[str],            # sorted; ids to chip on the reduce lane
  'authority':       {...},                # tier + null disclosure (G0.1/G0.4)
  'notes':           list[str],
}

BottomingRow = {
    'id':           str,          # raw forward-log id ('b-gold_miners' | 'xlc')
    'cid':          str,          # canonical id, 'b-' stripped ('gold_miners')
    'kind':         'BASKET' | 'SECTOR',
    'name':         str,
    'name_zh':      str | None,   # from the caller's lookup; None → EN fallback
    'pos':          float | None, # cycle position 0-100; lower = deeper in the low
    'osc_slope':    float | None, # oscillator slope; >0 is the lane's gate
    'signal':       str | None,   # PAYLOAD ONLY — never rendered (see above)
    'timing_state': str | None,   # PAYLOAD ONLY — never rendered (see above)
    'above200d':    bool | None,
    'cycle_signal': 'BUY' | None, # set only when signal == 'BUY'
    'gate_conflict': bool,        # True when the cycle turned but above200d is False
    'href':         str | None,   # site-root-relative detail page, or None
}

ID NAMESPACES
-------------
Basket rows in the forward log carry a 'b-' prefix ('b-gold_miners') while the
theme/act_now ids do not ('gold_miners'). Dual-read matching normalizes by
stripping the prefix, exactly as CN does. Sector ETF rows ('xlc', 'xlu') have no
prefix and no theme counterpart — they keep their own id and name and simply do
not dual-read.
"""
from __future__ import annotations

import logging
import math
import re
from collections.abc import Iterable
from typing import Any

log = logging.getLogger(__name__)

# Max rows carried on the lane. The board caps display separately; this is the
# payload cap so a pathological night cannot ship 40 rows into the artifact.
BOTTOMING_CAP = 8

# The lane's gate — the exact CN rule (china_act_now.py:353-358).
_TROUGH_PHASE = "Trough"

# ── Honest-null disclosure (G0.4) ──────────────────────────────────────────
# Plain words, no study names, no untranslated stats, no raw slugs. States what
# the lane IS (engine state) and what it is NOT (a buy claim), and that a basing
# turn on its own has not been shown to predict what comes next.
NULL_DISCLOSURE_EN = (
    "This is what the cycle read says tonight, shown as-is. A forming low on its "
    "own has not been shown to predict what comes next — watch, don't chase."
)
NULL_DISCLOSURE_ZH = (
    "这是今晚周期读数的原样呈现。单独的底部形成迹象尚未被证明能预测后续走势"
    "——观察，勿追。"
)

# Buy-family words banned from any RENDERED lane string (CN F1/W8-R3 parity).
# `signal` and `timing_state` are payload-only precisely because they carry these.
_BUY_WORD_RE = re.compile(
    r"(?:^|[^a-z])(buy|buys|buying|bought|entry|enter|entering|accumulate|"
    r"accumulating|add|adding|long)(?:[^a-z]|$)",
    re.IGNORECASE,
)

# Fields that must never reach a rendered surface (they carry buy-family words).
DISPLAY_FORBIDDEN_FIELDS = ("signal", "timing_state")


def contains_buy_word(text: str | None) -> bool:
    """True when `text` uses a buy-family verb. Used by the lane's own tests."""
    if not text:
        return False
    return bool(_BUY_WORD_RE.search(str(text)))


# ── coercion helpers ───────────────────────────────────────────────────────
# forward_log rows arrive from pandas: numpy scalars and NaN, neither of which is
# JSON-serializable in the shape the site expects. Coerce at the boundary.
def _f(v: Any) -> float | None:
    """numpy/py number → float, NaN/None/unparseable → None."""
    if v is None:
        return None
    try:
        out = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) else out


def _b(v: Any) -> bool | None:
    """numpy.bool_/bool → bool; None/NaN → None (unknown, not False)."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        return bool(v)
    except (TypeError, ValueError):
        return None


def _s(v: Any) -> str | None:
    """Value → stripped str; None/NaN/empty → None."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    out = str(v).strip()
    return out or None


def canonical_id(id_: str | None) -> str:
    """Strip the forward-log basket prefix so 'b-gold_miners' matches 'gold_miners'."""
    return (id_ or "").strip().removeprefix("b-")


def _href(kind: str, cid: str, raw_id: str) -> str | None:
    """Site-root-relative detail page for a lane row, or None when there is none.

    BASKET → basket/<cid>.html   (site/basket/gold_miners.html)
    SECTOR → sectors/<TICKER>.html (site/sectors/XLC.html — uppercase on disk)
    """
    if not cid:
        return None
    if kind == "BASKET":
        return f"basket/{cid}.html"
    if kind == "SECTOR":
        return f"sectors/{raw_id.strip().upper()}.html"
    return None


def _bottoming_row(r: dict, names_zh: dict[str, str] | None = None) -> dict:
    """Build one BottomingRow from a forward_log record."""
    raw_id = _s(r.get("id")) or ""
    cid = canonical_id(raw_id)
    kind = "BASKET" if (_s(r.get("kind")) or "").lower() == "basket" else "SECTOR"
    signal = _s(r.get("signal"))
    above = _b(r.get("above200d"))
    # The cycle organ's own registered output, quoted as such (masterplan §6).
    cycle_signal = "BUY" if (signal or "").upper() == "BUY" else None
    # Bilingual law (G0.5): the forward log is English-only, so the zh display name
    # comes from the caller's lookup (theme_intel themes + sector_central sectors).
    # Absent → None, and the template falls back to the English name.
    _zh = names_zh or {}
    name_zh = _s(_zh.get(raw_id)) or _s(_zh.get(cid))
    return {
        "id": raw_id,
        "cid": cid,
        "kind": kind,
        "name": _s(r.get("name")) or cid or raw_id,
        "name_zh": name_zh,
        "pos": _f(r.get("pos")),
        "osc_slope": _f(r.get("osc_slope")),
        # PAYLOAD ONLY — see module docstring. Never render these two.
        "signal": signal,
        "timing_state": _s(r.get("timing_state")),
        "above200d": above,
        "cycle_signal": cycle_signal,
        # The D10 conflict: the cycle says it turned, the trend gate is shut.
        # Only meaningful when the cycle actually signalled; `above is False`
        # (not `not above`) so an UNKNOWN above200d never fabricates a conflict.
        "gate_conflict": bool(cycle_signal) and above is False,
        "href": _href(kind, cid, raw_id),
    }


def _authority() -> dict[str, Any]:
    """The tier block every shipped key carries (G0.1) + the honest null (G0.4)."""
    return {
        "tier": "display",
        "may_rank": False,
        "may_gate": False,
        "may_size": False,
        "may_escalate": False,
        "null_disclosure_en": NULL_DISCLOSURE_EN,
        "null_disclosure_zh": NULL_DISCLOSURE_ZH,
    }


# --------------------------------------------------------------------------- #
#  Main assembler                                                              #
# --------------------------------------------------------------------------- #
def assemble_bottoming_watch(
    cycle_rows: list[dict] | None,
    reduce_ids: Iterable[str] | None = None,
    cap: int = BOTTOMING_CAP,
    names_zh: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble the US bottoming-watch lane + its dual-read id set.

    The gate is the exact CN rule: ``phase == "Trough" AND osc_slope > 0``.
    Rows are sorted by ``pos`` ASCENDING (deepest in the cycle low first) and
    capped at `cap`.

    Parameters
    ----------
    cycle_rows  latest-date forward_log rows; None → lane empty + note
    reduce_ids  ids currently on the reduce/avoid lane (for the FT-R1 chip)
    cap         max rows carried on the lane
    names_zh    {id -> Chinese display name}; keys may be raw ('b-gold_miners')
                or canonical ('gold_miners'). Absent name → English fallback.

    Returns
    -------
    dict with 'bottoming_watch', 'dual_read_ids', 'authority', 'notes'
    """
    notes: list[str] = []
    rows: list[dict] = []

    if cycle_rows is None:
        notes.append("cycle forward log absent — bottoming lane empty")
        cycle_rows = []

    # ── the lane gate: Trough AND rising oscillator ───────────────────────
    qualifying: list[dict] = []
    for r in cycle_rows or []:
        if not isinstance(r, dict):
            continue
        if (_s(r.get("phase")) or "") != _TROUGH_PHASE:
            continue
        slope = _f(r.get("osc_slope"))
        # Strictly rising. None/NaN slope is UNKNOWN, not rising — it does not
        # qualify (a missing slope must never manufacture a bottoming call).
        if slope is None or slope <= 0:
            continue
        qualifying.append(r)

    # Deepest in the low first. `pos` is None-safe: unknown position sorts last
    # rather than crashing or pretending to be 0 (which would rank it first).
    qualifying.sort(
        key=lambda r: (_f(r.get("pos")) is None, _f(r.get("pos")) or 0.0, _s(r.get("id")) or "")
    )

    n_qualifying = len(qualifying)
    for r in qualifying[: max(0, int(cap))]:
        rows.append(_bottoming_row(r, names_zh))
    if n_qualifying > len(rows):
        notes.append(f"bottoming lane capped: {len(rows)} of {n_qualifying} shown")

    # ── FT-R1 dual read ──────────────────────────────────────────────────
    # A row on the reduce/avoid lane that ALSO qualifies here keeps its place in
    # BOTH lanes — never merged, never re-ranked. The reduce row gets a chip.
    # Match on the canonical id so 'b-gold_miners' finds theme id 'gold_miners';
    # emit BOTH spellings so the template can look up either without knowing which
    # namespace produced the row.
    reduce_set = {str(x).strip() for x in (reduce_ids or []) if str(x).strip()}
    dual: set[str] = set()
    for row in rows:
        for variant in (row["id"], row["cid"]):
            if variant and variant in reduce_set:
                dual.add(row["id"])
                dual.add(row["cid"])

    return {
        "bottoming_watch": rows,
        "dual_read_ids": sorted(dual),
        "authority": _authority(),
        "notes": notes,
    }


# --------------------------------------------------------------------------- #
#  Null-safe loader (used by scripts/build_baskets.py)                          #
# --------------------------------------------------------------------------- #
def load_cycle_rows(forward_log_path: str | None = None) -> list[dict] | None:
    """Load latest-date `sector_cycles/forward_log.parquet` rows.

    Returns None when the store is absent or unreadable (the caller renders the
    lane empty and the note explains why); [] when the store is present but has
    no usable rows. Never raises — this rides an additive nightly path.
    """
    try:
        from pathlib import Path

        import pandas as pd

        if forward_log_path:
            p = Path(forward_log_path)
        else:
            from lib import config
            p = config.data_dir() / "sector_cycles" / "forward_log.parquet"
        if not p.exists():
            log.warning("us_act_now: forward_log.parquet not found at %s", p)
            return None
        df = pd.read_parquet(p)
        if df.empty or "date" not in df.columns:
            return []
        latest = df["date"].max()
        return df[df["date"] == latest].to_dict(orient="records")
    except Exception as exc:  # noqa: BLE001 — additive lane, never fatal
        log.warning("us_act_now: failed to load forward_log: %s", exc)
        return None
