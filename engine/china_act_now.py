"""engine/china_act_now.py — Act-Now v2 pure lane assembler (W8-R3).

Inputs
------
sectors      list[dict]  – sector cards from build_china._sector_cards() with
                           entry.urgency/tag per cycles.py vocab
theme_intel  dict|None   – baskets.json['theme_intel'] (entire dict); absent/
                           stale → themes omitted, note appended
cycle_rows   list[dict]  – latest forward_log rows (from data/china_sector_cycles/
                           forward_log.parquet), each row a dict; None/[] → bottoming
                           lane skipped
basket_turn  dict|None   – basket_turn_cn.json artifact (W8-R7 rider); absent/None
                           → organ chips omitted, existing forward_log-only logic
                           unchanged. Used to add TURNING/CONFIRMED organ chips
                           to bottoming_watch rows AND upgrade WASHED_OUT/BASING
                           baskets already in the lane via forward_log Trough+osc
                           rule. The organ ADDS evidence chips and members; it does
                           NOT remove rows selected by the forward_log rule.

Output
------
{
  'lanes': {
      'buy_now':        list[LaneRow],
      'wait_pullback':  list[LaneRow],
      'bottoming_watch': list[LaneRow],
      'reduce_avoid':   list[LaneRow],
  },
  'as_of':   str | None,
  'notes':   list[str],
}

LaneRow = {
    'kind':         'THEME' | 'SECTOR' | 'BASKET',
    'id':           str,               # basket/theme id or sector ticker
    'name':         str,
    'name_zh':      str | None,
    'score':        int | None,        # theme score 0-100; None for sector rows
    'reco':         str | None,        # accumulate/enter/hold/trim/avoid
    'reco_en':      str | None,
    'reco_zh':      str | None,
    'rel20':        float | None,      # 20d relative perf vs benchmark (fraction)
    'rel5':         float | None,      # 5d relative perf vs benchmark (fraction); themes only
    'tag':          str | None,        # sector ladder tag, kept verbatim
    'urgency':      str | None,        # sector urgency
    'reasons':      list[str],         # human-readable reasons (themes) or []
    # bottoming-watch specific
    'phase':        str | None,
    'osc_slope':    float | None,
    'pos':          float | None,
    'rs_63d':       float | None,
    'rs_rank':      int | None,
    # dual-read flag (FT-R1): row is in reduce_avoid AND bottoming_watch
    'dual_read':    bool,
    'dual_chip_en': str | None,        # text for secondary chip on reduce_avoid row
    'dual_chip_zh': str | None,
    # W8-R7 rider — basket-turn organ chip
    'organ_state':  str | None,        # TURNING | CONFIRMED (from basket_turn_cn)
    'organ_chip_en': str | None,       # "organ: TURNING (tape)"
    'organ_chip_zh': str | None,       # "器官：转向（纸带）"
    # detail-page navigation (site-root-relative href or None when page absent)
    # convention:
    #   THEME/BASKET  cid = id[2:] if id.startswith('b-') else id
    #                 if cid starts with 'ths' -> subsector_china/{cid.replace('_','-')}.html
    #                 else                     -> basket_china/{cid}.html
    #   SECTOR        '.' in id (ETF ticker)   -> sectors/{id}.html
    #                 else (SW code)            -> sector_cycles_china.html
    #   empty id -> None
    'href':         str | None,
}

Lane mapping
-----------
buy_now        ← theme act_now.buy (score desc) + sectors urgency now only
                 (clean entry open today)
wait_pullback  ← theme act_now.add_on_pullback (score desc)
                 + sectors urgency imminent (BUY SOON — conditional trigger not yet
                   fired, don't front-run)
                 + sectors urgency soon (WATCH/BUY-SOON — setting up, not yet actionable)
                 + sectors urgency caution with non-REDUCE tag (DON'T CHASE, HOLD, etc.)
                 + sectors urgency hold / later
bottoming_watch← cycle_rows latest: phase=='Trough' AND osc_slope>0 (both kind=sector
                 and kind=basket); sorted osc_slope desc; never buy words
reduce_avoid   ← theme act_now.reduce (score asc — worst first) + sectors urgency
                 exit/avoid + caution with REDUCE tag (TAKE PROFITS, SELL / REDUCE,
                 UNCONFIRMED — HIGH RISK); dual-read rows carry secondary chip

DUAL-READ LAW (FT-R1)
A name in reduce_avoid that is ALSO in bottoming_watch keeps entries in BOTH lanes.
The reduce_avoid row gets dual_read=True + dual_chip_en/zh set.
Basket cycle ids use a 'b-' prefix (e.g. 'b-cn_baijiu') while theme ids do not
('cn_baijiu'); dual-read matching normalizes by stripping the 'b-' prefix.
Never merged, never re-ranked.

BUY-WORD PROHIBITION (F1/W8-R3)
bottoming_watch rows must not contain: buy, entry, accumulate, enter (case-insensitive)
in any name, tag, reco field.  The lane caption enforces this at template level.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  Sector urgency routing (mirrors _china_action_board vocabulary)             #
# --------------------------------------------------------------------------- #
# buy_now:       urgency 'now' ONLY — clean entry open today.
# wait_pullback: 'imminent' (cycles.py BUY SOON fall-through — conditional
#                trigger UNFIRED, don't front-run) + 'soon' (WATCH/WAIT,
#                setting-up, not yet actionable).
_BUY_URGENCIES = {"now"}
_SOON_URGENCIES = {"soon", "imminent"}  # imminent = BUY SOON, not yet fired → wait
_WAIT_URGENCIES = {"caution", "hold", "later"}
# Within caution, tags determine the sub-route:
#   TAKE PROFITS / SELL / REDUCE / UNCONFIRMED → reduce_avoid
#   DON'T CHASE / HOLD / WAIT / anything else  → wait_pullback
_REDUCE_TAGS = {
    "TAKE PROFITS", "SELL / REDUCE", "UNCONFIRMED — HIGH RISK",
    "SELL", "AVOID",
}
# Tags explicitly routed to wait_pullback (on_the_run / not-actionable-yet)
_WAIT_TAGS = {
    "DON'T CHASE", "HOLD", "WAIT",
    "BOTTOMING · EXTENDED — WAIT", "BOTTOMING · UNCONFIRMED — WAIT",
}
_REDUCE_URGENCIES = {"exit", "avoid"}

# Named constants used in routing logic
_DONT_CHASE_TAG = "DON'T CHASE"
_UNCONFIRMED_TAG = "UNCONFIRMED — HIGH RISK"


# --------------------------------------------------------------------------- #
#  Helper builders                                                              #
# --------------------------------------------------------------------------- #
def _blank_row(kind: str, id_: str, name: str, name_zh: str | None = None) -> dict:
    return {
        "kind": kind,
        "id": id_,
        "name": name,
        "name_zh": name_zh,
        "score": None,
        "reco": None,
        "reco_en": None,
        "reco_zh": None,
        "rel20": None,
        "rel5": None,
        "tag": None,
        "urgency": None,
        "reasons": [],
        "phase": None,
        "osc_slope": None,
        "pos": None,
        "rs_63d": None,
        "rs_rank": None,
        "dual_read": False,
        "dual_chip_en": None,
        "dual_chip_zh": None,
        # W8-R7 rider fields (organ chip; None when basket_turn absent)
        "organ_state": None,
        "organ_chip_en": None,
        "organ_chip_zh": None,
        # detail-page href (site-root-relative); None when page absent or id empty
        "href": None,
    }


def _theme_row(item: dict, themes_by_id: dict) -> dict:
    """Build a LaneRow from a theme act_now item (buy/add_on_pullback/reduce)."""
    tid = item.get("id") or ""
    row = _blank_row("THEME", tid, item.get("name", tid), item.get("name_zh"))
    row["score"] = item.get("score")
    row["reco"] = item.get("action") or item.get("reco")
    row["reco_en"] = item.get("action_en") or item.get("reco_en")
    row["reco_zh"] = item.get("action_zh") or item.get("reco_zh")
    row["reasons"] = list(item.get("reasons") or [])
    # rel20 / rel5 live in themes_by_id[].perf[period]['rel']
    td = themes_by_id.get(tid, {})
    perf = td.get("perf") or {}
    p20 = perf.get("20d") or {}
    row["rel20"] = p20.get("rel")
    p5 = perf.get("5d") or {}
    row["rel5"] = p5.get("rel")
    return row


def _sector_row(s: dict) -> dict:
    """Build a LaneRow from a sector card (from build_china._sector_cards)."""
    e = s.get("entry") or {}
    row = _blank_row("SECTOR", s.get("ticker", ""), s.get("name", ""))
    row["tag"] = e.get("tag")
    row["urgency"] = e.get("urgency")
    row["reasons"] = [s.get("label") or s.get("state") or ""] if (
        s.get("label") or s.get("state")
    ) else []
    return row


def _cycle_row(r: dict) -> dict:
    """Build a LaneRow from a forward_log row (bottoming watch)."""
    kind = "BASKET" if (r.get("kind") or "").lower() == "basket" else "SECTOR"
    row = _blank_row(kind, r.get("id", ""), r.get("name", ""))
    row["phase"] = r.get("phase")
    row["osc_slope"] = r.get("osc_slope")
    row["pos"] = r.get("pos")
    row["rs_63d"] = r.get("rs_63d")
    row["rs_rank"] = r.get("rs_rank")
    return row


# --------------------------------------------------------------------------- #
#  Main assembler                                                               #
# --------------------------------------------------------------------------- #
def assemble_act_now(
    sectors: list[dict],
    theme_intel: dict | None,
    cycle_rows: list[dict] | None,
    basket_turn: dict | None = None,
    ths_baskets: dict | None = None,
    href_exists: "((str) -> bool) | None" = None,
) -> dict[str, Any]:
    """Assemble the four-lane Act-Now v2 board.

    Parameters
    ----------
    sectors     list of sector card dicts (each has 'entry' sub-dict with
                urgency + tag, 'ticker', 'name', 'label', 'state', 'dir')
    theme_intel baskets.json['theme_intel'] dict or None
    cycle_rows  list of forward_log row dicts for latest date (both kind='sector'
                and kind='basket'); None / [] means bottoming lane is empty
    basket_turn basket_turn_cn.json artifact dict (W8-R7 rider) or None;
                when present, adds organ chips to bottoming_watch rows for baskets
                whose state is TURNING or CONFIRMED. Also surfaces WASHED_OUT/
                BASING baskets already in the lane with an organ-state chip.
                The organ ADDS evidence — never removes forward_log-selected rows.
    ths_baskets {id: basket_dict} from baskets_ths.json for organ-rider name
                enrichment of ths_*/thsc* ids; None → skip THS lookup
    href_exists optional callable (str -> bool); when provided, each candidate
                href is tested and set to None when the callable returns False
                (degrade-safe: no link rather than a 404)

    Returns
    -------
    dict with 'lanes', 'as_of', 'notes'
    """
    buy_now: list[dict] = []
    wait_pullback: list[dict] = []
    bottoming_watch: list[dict] = []
    reduce_avoid: list[dict] = []
    notes: list[str] = []
    as_of: str | None = None

    # ── 1. THEMES from theme_intel.act_now ─────────────────────────────────
    themes_by_id: dict[str, dict] = {}
    if theme_intel:
        as_of = theme_intel.get("as_of")
        # build id→theme lookup for perf/rel20
        for t in (theme_intel.get("themes") or []):
            tid = t.get("id")
            if tid:
                themes_by_id[tid] = t

        an = theme_intel.get("act_now") or {}

        # buy lane: clean-entry accumulate/enter
        for item in an.get("buy") or []:
            row = _theme_row(item, themes_by_id)
            buy_now.append(row)
        # themes sorted by score desc (already in theme_scoring order, but enforce)
        buy_now.sort(key=lambda r: -(r["score"] or 0))

        # wait_pullback: add_on_pullback (no clean entry)
        for item in an.get("add_on_pullback") or []:
            row = _theme_row(item, themes_by_id)
            wait_pullback.append(row)
        wait_pullback.sort(key=lambda r: -(r["score"] or 0))

        # reduce_avoid: trim/avoid themes
        for item in an.get("reduce") or []:
            row = _theme_row(item, themes_by_id)
            reduce_avoid.append(row)
        # reduce sorted asc (worst/lowest score first)
        reduce_avoid.sort(key=lambda r: (r["score"] or 0))
    else:
        notes.append("theme artifact absent — themes omitted")

    # ── 2. SECTORS from cycle ladder urgency ──────────────────────────────
    for s in (sectors or []):
        e = s.get("entry") or {}
        urgency = e.get("urgency") or ""
        tag = e.get("tag") or ""

        if urgency in _BUY_URGENCIES:
            # now → clean-entry buy lane (open today)
            buy_now.append(_sector_row(s))

        elif urgency in _SOON_URGENCIES:
            # imminent (BUY SOON — unfired trigger) / soon (WATCH/BUY-SOON tag)
            # → setting up, not yet actionable → wait
            wait_pullback.append(_sector_row(s))

        elif urgency == "caution":
            # caution: route by tag first, urgency second
            if tag in _REDUCE_TAGS:
                # TAKE PROFITS, SELL / REDUCE, UNCONFIRMED — HIGH RISK → reduce lane
                reduce_avoid.append(_sector_row(s))
            else:
                # DON'T CHASE, HOLD, WAIT, or unlisted caution tag → wait lane
                wait_pullback.append(_sector_row(s))

        elif urgency == "hold" or urgency == "later":
            # hold / later → wait lane (not-yet-actionable)
            wait_pullback.append(_sector_row(s))

        elif urgency in _REDUCE_URGENCIES:
            reduce_avoid.append(_sector_row(s))

    # ── 3. BOTTOMING WATCH from cycle_rows ───────────────────────────────
    bottoming_ids: set[str] = set()
    if cycle_rows:
        # latest date rows only — caller should pass pre-filtered rows, but
        # if not, we take the rows as-is (null-safe: missing phase/osc_slope → skip)
        trough_rows = [
            r for r in cycle_rows
            if (r.get("phase") or "") == "Trough"
            and (r.get("osc_slope") is not None)
            and float(r.get("osc_slope", 0)) > 0
        ]
        trough_rows.sort(key=lambda r: -float(r.get("osc_slope", 0)))
        for r in trough_rows:
            crow = _cycle_row(r)
            bottoming_watch.append(crow)
            # Register the raw id AND the canonical id (strip leading 'b-' used by
            # basket forward_log rows so that theme reduce ids like 'cn_baijiu'
            # match basket cycle ids like 'b-cn_baijiu' (FT-R1 dual-read fix).
            bottoming_ids.add(crow["id"])
            canonical = crow["id"][2:] if crow["id"].startswith("b-") else crow["id"]
            bottoming_ids.add(canonical)
    else:
        if cycle_rows is None:
            notes.append("forward_log absent — bottoming lane empty")

    # ── 4. DUAL-READ (FT-R1) ─────────────────────────────────────────────
    # Collect reduce_avoid ids (themes and sectors)
    reduce_ids: set[str] = set()
    for r in reduce_avoid:
        reduce_ids.add(r["id"])

    # Any bottoming-watch id that is also in reduce_avoid → dual_read on
    # the reduce_avoid row; both rows kept as-is, never merged
    for r in reduce_avoid:
        if r["id"] in bottoming_ids:
            r["dual_read"] = True
            # Plain-language chip copy (operator request 2026-07-10): no house
            # jargon ("washout turning (tape)") on user-facing chips. ZH keeps
            # 洗盘 — standard A-share vernacular.
            r["dual_chip_en"] = "may be bottoming"
            r["dual_chip_zh"] = "洗盘转向"

    # Any bottoming-watch id that is also in reduce_avoid already has the
    # dual_chip on the reduce side; the bottoming row keeps its normal copy.
    # (No change needed to bottoming rows — they are shown side-by-side)

    # ── 5. W8-R7 RIDER — basket-turn organ chips ─────────────────────────
    # The basket_turn_cn artifact (W8-R5) annotates baskets with per-basket
    # states: FALLING / WASHED_OUT / BASING / TURNING / CONFIRMED.
    #
    # For bottoming_watch rows:
    #   - TURNING or CONFIRMED state → add organ chip ("organ: TURNING (tape)")
    #   - Other states (WASHED_OUT, BASING) → add organ_state chip only if already in lane
    #
    # The organ ADDS chips; it does NOT remove rows. Forward_log Trough+osc
    # rule remains the gate for inclusion in the lane.
    if basket_turn:
        _bt_baskets: dict = basket_turn.get("baskets") or {}
        # Build a normalized id → organ_state map (strip 'b-' prefix for matching)
        _organ_state_map: dict[str, str] = {}
        for _bt_id, _bt_info in _bt_baskets.items():
            _bt_state = _bt_info.get("state") if isinstance(_bt_info, dict) else None
            if _bt_state and _bt_state != "NONE":
                _organ_state_map[_bt_id] = _bt_state
                # Also register canonical id without 'b-' prefix
                _canonical = _bt_id[2:] if _bt_id.startswith("b-") else _bt_id
                _organ_state_map[_canonical] = _bt_state

        # Annotate existing bottoming_watch rows with organ chips
        _existing_bw_ids: set[str] = set()
        for _bw_row in bottoming_watch:
            _bw_id = _bw_row["id"]
            _existing_bw_ids.add(_bw_id)
            _canonical_id = _bw_id[2:] if _bw_id.startswith("b-") else _bw_id
            # Register canonical so the organ-surfacing loop skips both b- and non-b- variants
            _existing_bw_ids.add(_canonical_id)
            _organ_st = _organ_state_map.get(_bw_id) or _organ_state_map.get(_canonical_id)
            if _organ_st:
                _bw_row["organ_state"] = _organ_st
                if _organ_st in ("TURNING", "CONFIRMED"):
                    _bw_row["organ_chip_en"] = f"organ: {_organ_st} (tape)"
                    _bw_row["organ_chip_zh"] = f"器官：{_organ_st}（纸带）"
                else:
                    _bw_row["organ_chip_en"] = f"organ: {_organ_st}"
                    _bw_row["organ_chip_zh"] = f"器官：{_organ_st}"

        # Surface NEW baskets from organ (TURNING/CONFIRMED) not already in the lane
        # These are baskets the forward_log Trough+osc rule did not surface but the
        # organ detects as turning — add them as additional evidence rows.
        for _org_id, _org_st in _organ_state_map.items():
            if _org_st not in ("TURNING", "CONFIRMED"):
                continue
            if _org_id in _existing_bw_ids:
                continue
            # Avoid duplicates from the canonical/b- prefix both mapping (Fix 2)
            _canonical_org = _org_id[2:] if _org_id.startswith("b-") else _org_id
            if _canonical_org in _existing_bw_ids:
                continue
            # Fix 1: resolve display name + enrichment via fallback chain
            _name = _org_id
            _name_zh: str | None = None
            _score: int | None = None
            _reco: str | None = None
            _reco_en: str | None = None
            _reco_zh: str | None = None
            _rel20: float | None = None
            # 1a. themes_by_id covers cn_* ids (both _org_id and canonical)
            _td = themes_by_id.get(_org_id) or themes_by_id.get(_canonical_org)
            if _td:
                _name = _td.get("name") or _org_id
                _name_zh = _td.get("name_zh")
                _score = _td.get("score")
                _reco = _td.get("action") or _td.get("reco")
                _reco_en = _td.get("action_en") or _td.get("reco_en")
                _reco_zh = _td.get("action_zh") or _td.get("reco_zh")
                _p20 = ((_td.get("perf") or {}).get("20d") or {})
                _rel20 = _p20.get("rel")
            elif ths_baskets:
                # 1b. ths_baskets covers ths_*/thsc* ids from baskets_ths.json
                _tb = ths_baskets.get(_org_id) or ths_baskets.get(_canonical_org)
                if _tb:
                    _name = _tb.get("name") or _org_id
                    _name_zh = _tb.get("name_zh")
                    _p20 = ((_tb.get("perf") or {}).get("20d") or {})
                    _rel20 = _p20.get("rel")
                else:
                    log.warning("organ-rider: unknown basket id %r — using slug as name", _org_id)
            else:
                log.warning("organ-rider: no lookup available for id %r — using slug as name", _org_id)

            _new_bw_row = _blank_row("BASKET", _org_id, _name, _name_zh)
            _new_bw_row["score"] = _score
            _new_bw_row["reco"] = _reco
            _new_bw_row["reco_en"] = _reco_en
            _new_bw_row["reco_zh"] = _reco_zh
            _new_bw_row["rel20"] = _rel20
            _new_bw_row["organ_state"] = _org_st
            _new_bw_row["organ_chip_en"] = f"organ: {_org_st} (tape)"
            _new_bw_row["organ_chip_zh"] = f"器官：{_org_st}（纸带）"
            bottoming_watch.append(_new_bw_row)
            # Fix 2: register both raw and canonical ids so b-/non-b- variants
            # can't produce duplicate rows across nightly passes
            _existing_bw_ids.add(_org_id)
            _existing_bw_ids.add(_canonical_org)

    # ── 6. HREF post-pass — compute site-root-relative detail page urls ─────
    # Covers all four lanes including organ-rider-surfaced BASKET rows in
    # bottoming_watch. Convention documented in the LaneRow docstring.
    _all_lanes = [buy_now, wait_pullback, bottoming_watch, reduce_avoid]
    for _lane in _all_lanes:
        for _row in _lane:
            _rid = _row.get("id") or ""
            if not _rid:
                continue  # empty id → href stays None
            _kind = _row.get("kind") or ""
            if _kind in ("THEME", "BASKET"):
                # strip leading 'b-' to get canonical id for path construction
                _cid = _rid[2:] if _rid.startswith("b-") else _rid
                if _cid.startswith("ths"):
                    _candidate = f"subsector_china/{_cid.replace('_', '-')}.html"
                else:
                    _candidate = f"basket_china/{_cid}.html"
            elif _kind == "SECTOR":
                if "." in _rid:
                    # ETF ticker e.g. 512760.SS
                    _candidate = f"sectors/{_rid}.html"
                else:
                    # Shenwan numeric industry code e.g. 801080
                    _candidate = "sector_cycles_china.html"
            else:
                continue
            # degrade-safe: skip if caller says page does not exist. A raising
            # probe (e.g. Path.exists on a path-invalid id) must drop only this
            # row's link, never the whole board.
            if href_exists is not None:
                try:
                    _ok = href_exists(_candidate)
                except Exception:  # noqa: BLE001 — additive, never fatal
                    continue
                if not _ok:
                    continue
            _row["href"] = _candidate

    return {
        "lanes": {
            "buy_now": buy_now,
            "wait_pullback": wait_pullback,
            "bottoming_watch": bottoming_watch,
            "reduce_avoid": reduce_avoid,
        },
        "as_of": as_of,
        "notes": notes,
    }


# --------------------------------------------------------------------------- #
#  Null-safe loader helpers (used by build_china.py)                            #
# --------------------------------------------------------------------------- #
def load_theme_intel(baskets_json_path: str | None) -> dict | None:
    """Load theme_intel from baskets.json — returns None on any failure."""
    if not baskets_json_path:
        return None
    try:
        import json
        from pathlib import Path
        p = Path(baskets_json_path)
        if not p.exists():
            log.warning("baskets.json not found at %s", baskets_json_path)
            return None
        with open(p) as f:
            d = json.load(f)
        return d.get("theme_intel")
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to load theme_intel from %s: %s", baskets_json_path, exc)
        return None


def load_cycle_rows(forward_log_path: str | None) -> list[dict] | None:
    """Load latest-date forward_log rows — returns None on absent store."""
    if not forward_log_path:
        return None
    try:
        import pandas as pd
        from pathlib import Path
        p = Path(forward_log_path)
        if not p.exists():
            log.warning("forward_log.parquet not found at %s", forward_log_path)
            return None
        df = pd.read_parquet(p)
        if df.empty or "date" not in df.columns:
            return []
        latest_date = df["date"].max()
        rows = df[df["date"] == latest_date].to_dict(orient="records")
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to load forward_log from %s: %s", forward_log_path, exc)
        return None
