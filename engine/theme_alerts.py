"""Theme Rotation alert engine — fires when a theme's READ changes, run over run.

Unlike the price-driven alert engines (bonds/forex/commodity recompute a full event
history from a time series), a theme's LABEL and RECOMMENDATION are model outputs with
no stored historical series, so this engine is CHANGE-DETECTION across runs: it diffs
today's engine.theme_scoring payload against the prior snapshot persisted in
data/themes/state.json and emits an event only when something actually flipped —

  reco_change          a basket's recommendation moved (e.g. HOLD -> ACCUMULATE)
  theme_emerging       a basket entered the EMERGING lifecycle
  theme_topping        a DOMINANT leader rolled over into FADING
  theme_deteriorating  a basket broke down into DETERIORATING
  leadership_rotation  a new theme took the #1 score rank

Event schema matches the other engines (id, ts, source='themes', asset, type, severity,
headline/detail + _zh, context, anchor) so engine.alert_triage picks it up with zero new
plumbing. Writes data/themes/alerts.jsonl (append + dedup by id, ~90d kept) and the
state snapshot. FIRST run (no prior state) SEEDS silently — never an alert storm.

CONSTRUCTIVE-side changes are additionally DEBOUNCED (see apply_debounce): an upgrade
into ACCUMULATE/ENTER, or a new #1 rank, only fires after it persists N_STREAK
consecutive builds (leadership also needs a real score margin). Risk-direction events
are NEVER delayed — see the asymmetry rationale at the constants below.
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

KEEP_DAYS = 90
# raw severity per (type, direction) — `high` becomes a 'major' band on the watch tier
# in alert_triage; everything else reads minor. Reserve `high` for the calls that matter.
_RECO_RANK = {"avoid": 0, "trim": 1, "hold": 2, "accumulate": 3, "enter": 4}

# ---------------------------------------------------------------------------------------
# Asymmetric debounce — constructive side ONLY. This asymmetry is the design, not an
# accident:
#   * RISK-direction alerts (theme_topping, theme_deteriorating, any reco DOWNGRADE such
#     as accumulate/enter -> hold/trim/avoid) are the validated drawdown-control channel
#     (backtested: these reads precede deeper forward drawdowns on 27y of sector history).
#     They stay IMMEDIATE — never buffered, never delayed, passed through byte-identical.
#   * CONSTRUCTIVE-direction changes (upgrades into ACCUMULATE/ENTER, and
#     leadership_rotation) have NO measured forward-return edge (rank-IC ~ 0, descriptive
#     only), so a one-build delay costs nothing measurable while killing the oscillation
#     spam. Measured churn that motivated this (data/themes_china/alerts.jsonl, 2026-06):
#     cn_ai_compute's reco flapped HOLD<->ACCUMULATE 4 times in 7 days (06-22 -> ACC,
#     06-23 -> HOLD, 06-24 -> ACC, 06-26 -> HOLD, 06-29 -> ACC) and the #1 theme rank
#     rotated 6+ times in 6 sessions, twice within a single day on 06-25 and 06-26 —
#     the per-day dedup id only blocks exact same-day duplicates, so every oscillation
#     re-fired.
# NOTE: this debounce buffers DISPLAY/alert events only. No allocation or name-selection
# path reads this state, and none may ever be added here.
N_STREAK = 2
# a constructive flip must HOLD for 2 consecutive builds before it fires; a flip that
# reverts on the next build never fires at all (kills the measured 1-build whipsaws
# like brokers' same-day HOLD->ACC->HOLD on 06-22). The count advances AT MOST ONCE PER
# SESSION DATE: the Asia lane double-builds intraday (daily + asia-close), and replaying
# the recorded churn showed pure build-counting lets a flip "confirm" within half a day
# (cn_ai_compute's 06-22 ACC confirmed on the second 06-22 build, then reverted 06-23).
# Two same-day builds are one observation, not persistence — but a same-day revert still
# kills the streak.
LEAD_MIN_MARGIN = 3
# leadership_rotation additionally needs the new #1's margin over rank-2 to be >= 3
# points on theme_scoring's 0-100 composite AT THE CONFIRMING BUILD. The measured
# rotations were photo-finishes (65 vs 65 on 06-26; the live state snapshot shows rank1
# 63 vs rank2 60) — a <3-point lead is inside the composite's day-to-day wobble, so a
# handoff below that margin is rank noise, not a leadership change worth announcing.
_CONSTRUCTIVE_RECOS = {"accumulate", "enter"}
_DEBOUNCE_KEY = "_debounce"   # reserved state.json key; theme ids never start with "_"


def _ev(asset, type_, ts, severity, headline, detail, context, to_state,
        headline_zh="", detail_zh="") -> dict:
    ts = pd.Timestamp(ts)
    bucket = ts.strftime("%Y-%m-%d")
    return {"id": f"themes:{asset}:{type_}:{bucket}:{to_state}", "ts": ts.isoformat(),
            "source": "themes", "asset": asset, "type": type_, "severity": severity,
            "headline": headline, "detail": detail,
            "headline_zh": headline_zh or headline, "detail_zh": detail_zh or detail,
            "context": context, "anchor": f"#theme-{asset}"}


def _dir(region: str = "us"):
    # US keeps the original data/themes/ path; other markets get data/themes_<region>/
    return config.data_dir() / ("themes" if region == "us" else f"themes_{region}")


def _state_path(region: str = "us"):
    return _dir(region) / "state.json"


def _path(region: str = "us"):
    return _dir(region) / "alerts.jsonl"


def load_state(region: str = "us") -> dict:
    p = _state_path(region)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text()) or {}
    except Exception:  # noqa: BLE001
        return {}


def write_state(state: dict, region: str = "us") -> None:
    p = _state_path(region)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, sort_keys=True))


def _snapshot(theme_intel: dict) -> dict:
    """The per-theme fields we diff against next run."""
    return {t["id"]: {"label": t["label"], "reco": t["reco"], "rank": t["rank"],
                      "name": t["name"], "name_zh": t["name_zh"], "score": t["score"]}
            for t in theme_intel.get("themes", [])}


def compute_events(theme_intel: dict, prior: dict | None) -> list[dict]:
    """Diff today's read vs the prior snapshot. prior empty/None -> seed run, no events."""
    if not prior:
        return []
    ts = theme_intel.get("as_of")
    cur = _snapshot(theme_intel)
    events: list[dict] = []
    labelled: set[str] = set()      # baskets that already got a label event (skip their reco dup)

    for tid, c in cur.items():
        p = prior.get(tid)
        if not p:
            continue
        nm, nz = c["name"], c["name_zh"]

        # --- label transitions (the headline narrative changes) ---
        if c["label"] == "emerging" and p.get("label") != "emerging":
            labelled.add(tid)
            events.append(_ev(tid, "theme_emerging", ts, "medium",
                              f"🌱 {nm} is emerging",
                              f"{nm} entered the EMERGING lifecycle — accelerating relative strength "
                              f"before it is extended (score {c['score']}).",
                              {"from": p.get("label"), "to": "emerging", "score": c["score"]}, "emerging",
                              f"🌱 {nz} 进入新兴阶段",
                              f"{nz} 进入「新兴」阶段 — 相对强度加速且尚未过度延展（评分 {c['score']}）。"))
        elif c["label"] == "fading" and p.get("label") == "dominant":
            labelled.add(tid)
            # Honest-claim wording: the FADING read is calibrated as a pullback-RISK timer
            # (elevated forward drawdown), NOT a directional top call — and it is a basket-level
            # read that says nothing about the strongest members inside the theme. Keep the alert
            # immediate (ratified risk-direction asymmetry); temper the claim, disclose the as-of.
            _d = str(ts)[:10]
            events.append(_ev(tid, "theme_topping", ts, "high",
                              f"⚠️ {nm}: strength fading off the high",
                              f"{nm} dropped from DOMINANT to FADING as of the {_d} close — momentum "
                              f"cooling at a high. Historically this read flags elevated pullback risk "
                              f"over the next month, not a confirmed top — leaders inside the theme can "
                              f"keep running. Recommendation now {c['reco'].upper()}.",
                              {"from": "dominant", "to": "fading", "reco": c["reco"]}, "fading",
                              f"⚠️ {nz}：高位动能减弱",
                              f"{nz} 自「主导」转入「退潮」（截至 {_d} 收盘）— 高位动能降温。历史上该读数"
                              f"指向未来约一个月的回撤风险上升，并非确认见顶 — 主题内的领涨股仍可能续涨。"
                              f"当前建议 {c['reco'].upper()}。"))
        elif c["label"] == "deteriorating" and p.get("label") != "deteriorating":
            labelled.add(tid)
            events.append(_ev(tid, "theme_deteriorating", ts, "high",
                              f"🔻 {nm} is deteriorating",
                              f"{nm} broke down into DETERIORATING — momentum and breadth weakening "
                              f"together. Recommendation now {c['reco'].upper()}.",
                              {"from": p.get("label"), "to": "deteriorating", "reco": c["reco"]}, "deteriorating",
                              f"🔻 {nz} 走弱",
                              f"{nz} 转入「走弱」 — 动量与广度同步转弱，当前建议 {c['reco'].upper()}。"))

        # --- recommendation flip (skip if a label event already narrates this basket) ---
        if c["reco"] != p.get("reco") and tid not in labelled:
            up = _RECO_RANK.get(c["reco"], 2) > _RECO_RANK.get(p.get("reco"), 2)
            into_strong = c["reco"] in ("enter", "avoid")
            sev = "high" if into_strong else "medium"
            arrow = "↑" if up else "↓"
            events.append(_ev(tid, "reco_change", ts, sev,
                              f"{arrow} {nm}: {p.get('reco','?').upper()} → {c['reco'].upper()}",
                              f"Theme recommendation for {nm} changed from {p.get('reco','?').upper()} "
                              f"to {c['reco'].upper()} (score {c['score']}, {c['label']}).",
                              {"from": p.get("reco"), "to": c["reco"], "score": c["score"]},
                              c["reco"],
                              f"{arrow} {nz}：{p.get('reco','?').upper()} → {c['reco'].upper()}",
                              f"{nz} 的主题建议由 {p.get('reco','?').upper()} 变为 {c['reco'].upper()}"
                              f"（评分 {c['score']}，{c['label']}）。"))

    # --- leadership rotation: a new #1 score rank ---
    new_lead = next((t for t in cur.values() if t["rank"] == 1), None)
    old_lead_id = next((tid for tid, p in prior.items() if p.get("rank") == 1), None)
    if new_lead and old_lead_id and old_lead_id not in (
            tid for tid, t in cur.items() if t["rank"] == 1):
        lead_id = next(tid for tid, t in cur.items() if t["rank"] == 1)
        events.append(_ev(lead_id, "leadership_rotation", ts, "medium",
                          f"🔄 New theme leader: {new_lead['name']}",
                          f"{new_lead['name']} took the #1 theme rank (score {new_lead['score']}), "
                          f"displacing {prior.get(old_lead_id, {}).get('name', old_lead_id)}.",
                          {"new_leader": lead_id, "old_leader": old_lead_id}, "lead",
                          f"🔄 新主题领涨：{new_lead['name_zh']}",
                          f"{new_lead['name_zh']} 升至主题排名第一（评分 {new_lead['score']}），"
                          f"取代 {prior.get(old_lead_id, {}).get('name_zh', old_lead_id)}。"))
    return events


# ------------------------------------------------------------------ debounce machine
def _rank1_id(snap: dict) -> str | None:
    return next((tid for tid, t in snap.items()
                 if isinstance(t, dict) and t.get("rank") == 1), None)


def _confirmed_emerging_event(tid: str, c: dict, frm: str, ts, held: int) -> dict:
    """The deferred theme_emerging event, re-rendered at CONFIRM time so its ts/id reflects
    the build that proved the flip is sustained (id schema unchanged)."""
    nm, nz = c["name"], c["name_zh"]
    return _ev(tid, "theme_emerging", ts, "medium",
               f"🌱 {nm} is emerging",
               f"{nm} entered the EMERGING lifecycle — accelerating relative strength "
               f"before it is extended (score {c['score']}) — held {held} consecutive "
               f"sessions (constructive label shifts are debounced; risk label shifts fire "
               f"immediately).",
               {"from": frm, "to": "emerging", "score": c["score"], "held_sessions": held},
               "emerging",
               f"🌱 {nz} 进入新兴阶段",
               f"{nz} 进入「新兴」阶段 — 相对强度加速且尚未过度延展（评分 {c['score']}），"
               f"已连续 {held} 个交易日确认（进取方向去抖，风险方向即时）。")


def _confirmed_reco_event(tid: str, c: dict, frm: str, ts, held: int) -> dict:
    """The deferred constructive reco_change, re-rendered at CONFIRM time so its ts/id/
    score reflect the build that proved the flip (id schema unchanged)."""
    nm, nz = c["name"], c["name_zh"]
    to = c["reco"]
    sev = "high" if to == "enter" else "medium"
    return _ev(tid, "reco_change", ts, sev,
               f"↑ {nm}: {frm.upper()} → {to.upper()}",
               f"Theme recommendation for {nm} changed from {frm.upper()} to {to.upper()} "
               f"(score {c['score']}, {c['label']}) — held {held} consecutive sessions "
               f"(constructive flips are debounced; risk flips fire immediately).",
               {"from": frm, "to": to, "score": c["score"], "held_sessions": held},
               to,
               f"↑ {nz}：{frm.upper()} → {to.upper()}",
               f"{nz} 的主题建议由 {frm.upper()} 变为 {to.upper()}"
               f"（评分 {c['score']}，{c['label']}），已连续 {held} 个交易日确认"
               f"（进取方向去抖，风险方向即时）。")


def _confirmed_lead_event(new_id: str, cur: dict, old_id: str, prior: dict, ts,
                          held: int, margin) -> dict:
    """The deferred leadership_rotation, emitted only once the new #1 is both persistent
    (held N_STREAK builds) and decisive (margin over rank-2)."""
    c = cur[new_id]
    old = cur.get(old_id) or prior.get(old_id) or {}
    m_en = f" with a {margin:g}-point margin over #2" if margin is not None else ""
    m_zh = f"，领先第二名 {margin:g} 分" if margin is not None else ""
    return _ev(new_id, "leadership_rotation", ts, "medium",
               f"🔄 New theme leader: {c['name']}",
               f"{c['name']} took the #1 theme rank (score {c['score']}), displacing "
               f"{old.get('name', old_id)} — held #1 for {held} consecutive sessions{m_en}.",
               {"new_leader": new_id, "old_leader": old_id, "held_sessions": held,
                "margin": margin}, "lead",
               f"🔄 新主题领涨：{c['name_zh']}",
               f"{c['name_zh']} 升至主题排名第一（评分 {c['score']}），取代 "
               f"{old.get('name_zh', old_id)} — 已连续 {held} 个交易日保持第一{m_zh}。")


def apply_debounce(events: list[dict], cur: dict, prior: dict, deb: dict | None,
                   ts) -> tuple[list[dict], dict]:
    """The asymmetric debounce state machine. Pure:
    (raw compute_events output, current snapshot, prior snapshot, prior debounce state,
    build ts) -> (events to emit this build, next debounce state to persist).

    RISK-direction events pass through UNTOUCHED (same dict, same id, zero delay).
    Constructive reco upgrades are buffered in a per-theme pending streak; leadership
    rotations in a single pending-leader streak. `deb` from an OLD-format state file
    (missing entirely, or missing keys) degrades to "no streak" — never raises.
    Default is fail-open: any transition the machine does not explicitly recognise
    behaves exactly like the pre-debounce code (event passes through).
    """
    deb = deb if isinstance(deb, dict) else {}
    prior_reco = {k: v for k, v in (deb.get("reco") or {}).items() if isinstance(v, dict)}
    prior_label = {k: v for k, v in (deb.get("label") or {}).items() if isinstance(v, dict)}
    lead = deb.get("lead") if isinstance(deb.get("lead"), dict) else {}
    out: list[dict] = []
    next_reco: dict[str, dict] = {}
    next_label: dict[str, dict] = {}
    try:
        bucket = pd.Timestamp(ts).strftime("%Y-%m-%d")   # session date of THIS build
    except Exception:  # noqa: BLE001
        bucket = None

    # ---- label events: risk direction immediate; theme_emerging buffered (constructive) ----
    for e in events:
        if e.get("type") == "leadership_rotation":
            continue                      # regenerated below by the leadership machine
        if e.get("type") == "theme_emerging":
            # constructive label flip: buffer with N_STREAK=2, same as reco upgrades.
            # The "from" label is preserved so the confirm event narrates correctly.
            tid = e.get("asset")
            frm = (e.get("context") or {}).get("from")
            streak = prior_label.get(tid)
            next_label[tid] = {"from": streak.get("from", frm) if streak else frm,
                               "count": 1, "bucket": bucket}
            continue
        if e.get("type") != "reco_change":
            out.append(e)                 # topping/deteriorating: immediate
            continue
        tid = e.get("asset")
        ctx = e.get("context") or {}
        frm, to = ctx.get("from"), ctx.get("to")
        streak = prior_reco.get(tid)
        up = _RECO_RANK.get(to, 2) > _RECO_RANK.get(frm, 2)
        if up and to in _CONSTRUCTIVE_RECOS:
            # constructive flip -> start (or re-base) a pending streak. The DISPLAYED reco
            # stays streak['from'] until confirmed, so the confirm event narrates from the
            # last reco the reader actually saw.
            next_reco[tid] = {"from": streak.get("from", frm) if streak else frm,
                              "to": to, "count": 1, "bucket": bucket}
            continue
        if streak and to == streak.get("from"):
            # pure reversion echo: raw reco fell straight back to the reco still on
            # display (the buffered upgrade never fired), so the net displayed change is
            # zero and the whipsaw pair dies without a trace. NOT a risk delay — there
            # was no displayed lean to unwind.
            continue
        # everything else — downgrades (including below the displayed reco) and upgrades
        # that stop at HOLD — fires immediately, byte-identical to the old behaviour.
        out.append(e)

    # ---- advance held streaks (a reco that merely persists produces no raw event) ----
    for tid, streak in prior_reco.items():
        if tid in next_reco:
            continue                      # re-based this build
        c = cur.get(tid)
        if not isinstance(c, dict) or c.get("reco") != streak.get("to"):
            continue                      # theme gone or reverted -> streak dies silently
        if bucket is not None and streak.get("bucket") == bucket:
            # intraday double-build: same session date counts once, but the streak lives
            next_reco[tid] = streak
            continue
        held = int(streak.get("count", 0)) + 1
        if held >= N_STREAK:
            out.append(_confirmed_reco_event(tid, c, streak.get("from", "?"), ts, held))
        else:
            next_reco[tid] = {**streak, "count": held, "bucket": bucket}

    # ---- advance held label streaks (theme_emerging that merely persists: no raw event) ----
    for tid, streak in prior_label.items():
        if tid in next_label:
            continue                      # re-based this build
        c = cur.get(tid)
        if not isinstance(c, dict) or c.get("label") != "emerging":
            continue                      # theme gone or label reverted -> streak dies silently
        if bucket is not None and streak.get("bucket") == bucket:
            # intraday double-build: same session date counts once, streak lives
            next_label[tid] = streak
            continue
        held = int(streak.get("count", 0)) + 1
        if held >= N_STREAK:
            out.append(_confirmed_emerging_event(tid, c, streak.get("from", "?"), ts, held))
        else:
            next_label[tid] = {**streak, "count": held, "bucket": bucket}

    # ---- leadership: needs N_STREAK builds at #1 AND a decisive margin, same build ----
    cur_lead = _rank1_id(cur)
    displayed = lead.get("displayed") or _rank1_id(prior) or cur_lead
    pending = lead.get("pending") if isinstance(lead.get("pending"), dict) else None
    next_lead: dict = {"displayed": displayed, "pending": None}
    if cur_lead and displayed and cur_lead != displayed:
        same = pending and pending.get("tid") == cur_lead
        if same and bucket is not None and pending.get("bucket") == bucket:
            held = int(pending.get("count", 0))     # same session date counts once
        else:
            held = int(pending.get("count", 0)) + 1 if same else 1
        rank2 = next((t for t in cur.values()
                      if isinstance(t, dict) and t.get("rank") == 2), None)
        margin = (cur[cur_lead].get("score", 0) - rank2.get("score", 0)) if rank2 else None
        if held >= N_STREAK and (margin is None or margin >= LEAD_MIN_MARGIN):
            out.append(_confirmed_lead_event(cur_lead, cur, displayed, prior, ts,
                                             held, margin))
            next_lead = {"displayed": cur_lead, "pending": None}
        else:
            # not confirmed yet: a photo-finish keeps counting sessions but never emits
            # until the lead is both persistent AND decisive on the same build.
            next_lead["pending"] = {"tid": cur_lead, "count": held, "bucket": bucket}
    return out, {"reco": next_reco, "label": next_label, "lead": next_lead}


def load_events(region: str = "us") -> list[dict]:
    p = _path(region)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def write_events(events: list[dict], region: str = "us") -> None:
    p = _path(region)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


def recent(days: int = 30, as_of: str | None = None, region: str = "us") -> list[dict]:
    """Events within the trailing window, newest first (for the page bell dropdown)."""
    evs = load_events(region)
    if not evs:
        return []
    ref = pd.Timestamp(as_of) if as_of else max(pd.Timestamp(e["ts"]) for e in evs)
    cutoff = ref - pd.Timedelta(days=days)
    out = [e for e in evs if pd.Timestamp(e["ts"]) >= cutoff]
    out.sort(key=lambda e: e["ts"], reverse=True)
    return out


_RISK_TYPES = {"theme_topping", "theme_deteriorating"}
_CONT_TYPES = {"theme_emerging", "leadership_rotation"}


def _annotate_confidence(events: list[dict], cal: dict) -> list[dict]:
    """Tag each fired event with a BACKTESTED-vs-DESCRIPTIVE confidence from the basket-
    signal calibration (engine.theme_scoring._signal_calibration), and stop a CONTINUATION
    event — which has NO measured forward-return edge (rank-IC ~ 0) — from ever firing at
    'high'. Risk events the proxy MEASURED (topping/deteriorating → deeper drawdowns) keep
    full confidence with a backtested badge. This is the honest 'needle-pinpoint' gate:
    appearances are not suppressed (audit trail preserved), but unvalidated calls can't
    shout. Additive — cal {} leaves every event byte-identical."""
    if not cal:
        return events
    for e in events:
        t = e.get("type")
        to = (e.get("context") or {}).get("to")
        if t in _RISK_TYPES or (t == "reco_change" and to in ("avoid", "trim")):
            lab = "deteriorating" if (t == "theme_deteriorating" or to == "avoid") else "fading"
            measured = (cal.get(lab) or {}).get("verdict") == "measurable_edge"
            e["confidence"] = "backtested" if measured else "unconfirmed"
            e["confidence_en"] = ("Backtested — this risk read precedes deeper forward "
                                  "drawdowns on 27y of clean sector history." if measured else
                                  "Risk read — not separately confirmed on the proxy.")
            e["confidence_zh"] = ("已回测 — 在27年干净行业历史上该风险信号领先于更深前向回撤。"
                                  if measured else "风险信号 — 代理上未单独验证。")
        elif t in _CONT_TYPES or (t == "reco_change" and to in ("enter", "accumulate")):
            e["confidence"] = "descriptive"
            e["confidence_en"] = ("Descriptive — no measured forward-return edge (rank-IC ~ 0) "
                                  "on the 27y proxy. A flow / focus read, not a buy signal.")
            e["confidence_zh"] = ("描述性 — 在27年代理上无可测前向收益优势（rank-IC≈0）。"
                                  "资金流/聚焦提示，非买入信号。")
            if e.get("severity") == "high":     # an unvalidated continuation must not shout
                e["severity"] = "medium"
    return events


def _calibration() -> dict:
    """Local reader of the backtested signal-precision verdict (avoids importing the heavy
    theme_scoring module into the alert path). Mirrors theme_scoring._signal_calibration."""
    try:
        p = config.data_dir() / "strategies" / "baskets_calibration.json"
        d = json.loads(p.read_text()) if p.exists() else {}
        return d.get("verdict", {}) if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def rebuild(theme_intel: dict, region: str = "us") -> list[dict]:
    """Diff vs prior state, debounce the constructive side, append+dedup new events into
    the jsonl, persist new state (+ the debounce streaks under the reserved "_debounce"
    key — an old-format state file without it reads as "no streak", never breaks).
    Returns the events fired THIS run (empty on the seed run)."""
    if not theme_intel or not theme_intel.get("themes"):
        return []
    state = load_state(region)
    prior = {k: v for k, v in state.items() if not str(k).startswith("_")}
    cur = _snapshot(theme_intel)
    raw = compute_events(theme_intel, prior)
    kept, deb_next = apply_debounce(raw, cur, prior, state.get(_DEBOUNCE_KEY),
                                    theme_intel.get("as_of"))
    new_events = _annotate_confidence(kept, _calibration())

    # merge into history: keep-first by id, then trim to the KEEP_DAYS window
    by_id = {e["id"]: e for e in load_events(region)}
    for e in new_events:
        by_id.setdefault(e["id"], e)
    merged = list(by_id.values())
    if merged:
        ref = max(pd.Timestamp(e["ts"]) for e in merged)
        cutoff = ref - pd.Timedelta(days=KEEP_DAYS)
        merged = [e for e in merged if pd.Timestamp(e["ts"]) >= cutoff]
        merged.sort(key=lambda e: e["ts"])
    write_events(merged, region)
    out_state = dict(cur)
    out_state[_DEBOUNCE_KEY] = deb_next
    write_state(out_state, region)
    log.info("theme alerts [%s]: %d new event(s), %d in window (seed=%s)",
             region, len(new_events), len(merged), not prior)
    return new_events
