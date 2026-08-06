"""CN Theme Tape — theme cycle state × member board states × why-not attributions.

Charter: research/CHINA_PROPHET_LOSER_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §5 W-C
("CN Theme Tape on china_stocks reusing the US W2 pattern (#4488) — theme heat ×
member states × why-not attributions, glance-tier, zh parity").

WHAT THIS CLOSES. The operator incident of 2026-08-04: Gold Miners showed as the
top sector on several boards, and the china_stocks page said NOTHING about why it
carried no picks. Answering it took a forensic session. The facts were all in
artifacts the page already builds — the basket was in an early turn, its members
were held out upstream, and each had a specific reason. This module joins them so
the page states it at a glance.

IT IS AN ACCOUNTING, NOT A LEADERBOARD — the same distinction the US tape draws.
Heat does not decide who shows; the CYCLE does, because "the sector turned before
its names did" is the fact the incident was about. Every member of a shown theme
lands in exactly one bucket, so a row adds up to the theme's whole membership, and
a theme with zero picks still gets a row that says so. A panel that only spoke when
it had a pick would reproduce the silence it exists to fix.

DISPLAY TIER, ZERO AUTHORITY. Nothing here ranks, gates or sizes anything. It reads
finished nightly artifacts and re-states them; it originates no signal and changes
no board row. The board below is byte-identical with this panel present or absent.

WHY THE CANDIDATES LEDGER AND NOT THE BOARD. `china_standouts.json` is the BOARD —
what made it. On 2026-08-05 not one of Gold Miners' six members appears anywhere in
that file, so a board-only join renders "6/6 quiet" and narrates nothing: the exact
silence again, one layer down. `data/china_prophet_rank/candidates.parquet` is the
full considered universe WITH its `gate_reason`, which is where the answer lives
(湖南黄金 → "veto: bearish divergence"). Same nightly producer, already committed,
read-only here.

`gate_reasons` (plural) is computed in-memory by engine/china_prophet_shadow.py and
never written to disk; `gate_reason` (singular) is the persisted column. Both were
named as candidate sources in the build brief — only the singular one exists.

SOURCES (all fail-open; a missing one drops its own chip, never the tape):
  data/baskets_china/membership.json        basket -> members, etf_proxy
  data/china_sector_cycles/forward_log.pq   kind == 'basket' -> phase, osc_slope
  data/china_prophet_rank/candidates.pq     lane, entry_status, gate_reason
  site/flowdata/desk.json                   ashare_sectors.rows -> flow state (opt)
  data/china_standout_track/board.parquet   cn_continuation_watch_v1 rows (opt)
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

log = logging.getLogger(__name__)

#: Hard ceiling on rows, not a ranking depth — see `build_cn_theme_tape` for why the
#: row SET is defined by a condition rather than sliced off the top of a ranking.
MAX_ROWS = 10

#: The board's own continuation-watch cohort. Empty until the nightly lane starts
#: appending; a zero-row read is a normal state, never an error.
CONTINUATION_BOARD = "cn_continuation_watch_v1"

#: How stale the flow desk may be before its chip is dropped. `site/flowdata/desk.json`
#: declares a DAILY cadence, so a week is already generous; on 2026-08-05 it stood at
#: 2026-07-24 (12 days) and the chip correctly does not render. The budget is a
#: freshness gate, not a feature flag — the chip lights up on its own once the lane
#: is healthy again, with nothing here to change.
FLOW_MAX_AGE_DAYS = 7

#: The cycle, in cycle order. This is the rail's geometry AND the phase vocabulary in
#: one object, so the two can never disagree about how many positions there are or
#: which one a theme sits on.
#:
#: The engine's own enum values (Trough/Recovery/Expansion/Peak/Downturn) are internal
#: vocabulary and never reach the glance tier — DESIGN_DOCTRINE Law 2 bans the desk's
#: enum printed character-for-character on a primary surface. The plain words below are
#: the ONE live definition of that mapping. A dead `PHASE_ZH` map exists in
#: templates/sector_central_china.html.j2 (defined, never consumed by any code); it is
#: not a second source of truth and was not copied — its "Recovery → 入场良机" reads as
#: a buy instruction, which is precisely what a cycle STATE must not do.
PHASES: tuple[tuple[str, str, str], ...] = (
    ("Trough",    "Still bottoming",  "仍在筑底"),
    ("Recovery",  "Early turn",       "初现拐点"),
    ("Expansion", "Running",          "上行中"),
    ("Peak",      "Late, stretched",  "高位偏晚"),
    ("Downturn",  "Rolling over",     "转弱回落"),
)
PHASE_INDEX: dict[str, int] = {p[0]: i for i, p in enumerate(PHASES)}
PHASE_WORDS: dict[str, tuple[str, str]] = {p[0]: (p[1], p[2]) for p in PHASES}

#: The phase the whole panel is about: the sector has turned up off a base.
EARLY_TURN = "Recovery"

#: The five buckets, in "most actionable first" order — a member is counted once, at
#: its most actionable state, so the row sums to the theme's membership.
#: The words match the board's own facet bar directly below this panel; a reader who
#: learns "almost" here meets the same cohort under the same idea down there.
BUCKETS: tuple[tuple[str, str, str], ...] = (
    ("live",    "live",    "可操作"),
    ("almost",  "almost",  "接近"),
    ("blocked", "blocked", "受阻"),
    ("ran",     "ran",     "已启动"),
)
BUCKET_KEYS: tuple[str, ...] = tuple(b[0] for b in BUCKETS) + ("quiet",)
_PRIORITY: dict[str, int] = {k: i for i, k in enumerate(BUCKET_KEYS)}

#: `gate_reason` (the persisted why-not prose) -> bucket + plain bilingual words.
#:
#: WHY "counter-trend, no 200-reclaim/hold" IS QUIET AND NOT BLOCKED. It is the single
#: most common value in the ledger (450 of 1,667 rows on 2026-08-05) — it says the name
#: is simply below its trend line and no setup exists yet. Bucketed as `blocked` it made
#: that column read 10/11/14 on nearly every row: a constant, and Law 4 is explicit that
#: a constant is not a signal. As `quiet` with one shared reason it is honest and the
#: `blocked` column goes back to meaning what the reader thinks it means — this name was
#: actively held out — which on Gold Miners leaves exactly 湖南黄金 standing, the name
#: the operator asked about.
#:
#: Keys are the engine's exact strings. An unrecognised one is NOT guessed at: it takes
#: the generic chip and the raw text rides the hover, because a raw machine string on the
#: glance tier is a documented doctrine violation, not a graceful degradation. The same
#: rule templates/china.html.j2's `_CN_MK` map already follows for lane reasons.
WHY_NOT: dict[str, tuple[str, str | None, str | None]] = {
    "buy blocked by filter: counter-trend, no 200-reclaim/hold":
        ("quiet", "Still below trend", "仍在趋势下方"),
    "buy blocked by filter: failed reclaim-and-hold":
        ("blocked", "Reclaim failed", "收复失败"),
    "buy blocked by filter: veto: bearish divergence":
        ("blocked", "Momentum diverging", "动能背离"),
    "buy fired; forward confirmation pending":
        ("almost", "Waiting on confirmation", "等待确认"),
    "early advance-warning (no open buy)":
        ("almost", "Early warning only", "仅早期预警"),
    "early advance-warning (last buy was filtered out)":
        ("almost", "Early warning only", "仅早期预警"),
    "forming master already topping — not a fresh entry":
        ("ran", "Already topping", "已见顶"),
    "held but topped/rolled-over — no longer a fresh entry":
        ("ran", "Rolled over", "已回落"),
    "held but risen for many days (cross 2+ ticks ago) — no longer a fresh entry":
        ("ran", "Already ran", "已经拉升"),
    "held confirmation":
        ("ran", "Confirmed, not fresh", "已确认，非新信号"),
    "flat: sell": ("quiet", None, None),
    "flat: cut": ("quiet", None, None),
}

#: entry_status families for rows that DID reach a board lane.
_ALMOST_STATUS = frozenset({"bounce_wait", "buy_soon", "await_confluence", "watch"})
_RAN_STATUS = frozenset({"extended", "hold", "topping", "wait_pullback"})

#: The shared reason under a theme's quiet list. One line, once, under the group —
#: never invented per name: the ledger has no per-name verdict for a name it never
#: scored, and writing one would be a fabricated rejection.
QUIET_WHY = ("no setup here yet", "此处尚无形态")

#: Stances, chosen MECHANICALLY from the counts by `_stance_for` — no free-form text
#: reaches the template. Verbs come from the doctrine's sanctioned stance vocabulary
#: (Act · Get ready · Watch — don't chase · Protect gains · Stand aside · Ignore).
STANCES: dict[str, tuple[str, str]] = {
    "act": ("Act — {live} live in this theme today.",
            "可操作 — 本主题今日有 {live} 只。"),
    "ready": ("Get ready — {almost} close, none has triggered.",
              "准备 — {almost} 只接近，均未触发。"),
    "watch": ("Watch — don’t chase. The sector turned; no name has.",
              "观望，勿追高。板块已转向，个股尚未。"),
    "gains": ("Protect gains — this move is already under way.",
              "保护利润 — 本轮行情已在途中。"),
    "aside": ("Stand aside — nothing here is close.",
              "暂时观望 — 此处无接近标的。"),
}


def _stance_for(counts: dict[str, int], phase: str) -> str:
    """Pick the stance key. Pure function of the counts + the phase on the same row.

    There is deliberately NO "every name is held out" variant. It was written, and on
    the incident's own row it was false: Gold Miners carries one blocked name out of
    six, the rest merely dormant. A stance keyed off `blocked > 0` states a majority
    the count does not support, and the expanded row already shows exactly which name
    was held and why. One true sentence beats two that need a proviso.
    """
    if counts.get("live"):
        return "act"
    if counts.get("almost"):
        return "ready"
    if phase == EARLY_TURN:
        return "watch"
    if counts.get("ran"):
        return "gains"
    return "aside"


def _as_date(value: Any) -> date | None:
    """Parse a YYYY-MM-DD stamp from whatever the artifact carries. Never raises."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _s(value: Any) -> str:
    """Coerce a parquet cell to a clean string.

    `or ""` is NOT enough and this bit once: pandas stores a null in a mixed object
    column as float NaN, and NaN is TRUTHY — so `(cell or "").strip()` sails past the
    guard and raises AttributeError on the first featured row, whose `gate_reason` is
    legitimately null. Type-check, never truthiness.
    """
    return value.strip() if isinstance(value, str) else ""


def _classify(row: Any) -> tuple[str, str | None, str | None]:
    """One member -> (bucket, plain EN, plain ZH). Lane first, then the gate reason."""
    if row is None:
        return "quiet", None, None
    lane = _s(row.get("lane"))
    status = _s(row.get("entry_status"))
    reason = _s(row.get("gate_reason"))

    if lane == "featured":
        return "live", None, None
    if lane == "late_or_unfillable":
        return "blocked", "Cannot fill today", "今日无法成交"
    if lane in ("more_actionable", "forming"):
        if status in _RAN_STATUS:
            return "ran", "Already ran", "已经拉升"
        return "almost", "Turn not confirmed", "转向未确认"

    hit = WHY_NOT.get(reason)
    if hit is not None:
        return hit
    if reason.startswith("tier T"):
        # A bare tier stamp is a scoring note, not a rejection.
        return "quiet", None, None
    if reason:
        # Unknown code: generic chip, raw text demoted to the hover by the template.
        return "blocked", None, None
    return "quiet", None, None


def _flow_index(flow: dict[str, Any] | None, today: date | None) -> dict[str, dict]:
    """Basket key -> flow row, but ONLY while the desk is fresh.

    The desk ships its own bilingual `state`/`state_zh`, so there is no vocabulary to
    invent here — the only judgement is whether it may speak at all. A 12-day-old read
    printed beside today's board is a silent claim of same-day parity, so a stale desk
    drops the chip everywhere rather than dating it per row.
    """
    if not isinstance(flow, dict):
        return {}
    section = flow.get("ashare_sectors")
    if not isinstance(section, dict):
        return {}
    stamped = _as_date(section.get("as_of") or flow.get("as_of"))
    if stamped is None:
        return {}
    age = ((today or date.today()) - stamped).days
    if age > FLOW_MAX_AGE_DAYS:
        log.info("cn theme tape: flow desk %s is %d days old — flow chips dropped",
                 stamped, age)
        return {}
    out: dict[str, dict] = {}
    for row in section.get("rows") or []:
        if isinstance(row, dict) and row.get("id"):
            out[str(row["id"])] = row
    return out


def _latest_rows(frame: Any, column: str) -> dict[str, Any]:
    """Index a dataframe's most recent stamp by ticker/id. Fail-open on any shape."""
    if frame is None or not hasattr(frame, "empty") or frame.empty:
        return {}
    if column not in frame.columns:
        return {}
    try:
        newest = frame[frame[column] == frame[column].max()]
    except (TypeError, ValueError):
        return {}
    return newest


def build_cn_theme_tape(
    membership: dict[str, Any] | None,
    cycles: Any = None,
    candidates: Any = None,
    flow: dict[str, Any] | None = None,
    watch: Any = None,
    max_rows: int = MAX_ROWS,
    today: date | None = None,
) -> dict[str, Any] | None:
    """Join the CN theme artifacts into the finished panel dict.

    THE ROW SET IS A CONDITION, NOT A TOP-N SLICE, and that is load-bearing twice.

    A theme earns a row when its cycle has TURNED (`Recovery`) or when the board has a
    live pick in it — a stated rule a reader can hold, not a ranking. This panel ranks
    nothing and says so; slicing the top 5 off an activity count would assert exactly
    the ordering authority it disclaims, and the count is dominated by basket SIZE
    (Banks has 18 members, Gold Miners 6), so the "top" would mostly track membership.

    It is also what makes the panel survive its own reason for existing. Ranked by
    activity against the 2026-08-05 artifacts, Gold Miners — the theme whose silence
    caused the incident this panel closes — sorts 8th and falls off a top-5. A panel
    that drops the row it was built for is not a smaller panel; it is a broken one.

    Returns None when the tape has nothing to say — no baskets, no cycle read, or not
    one shown theme with a live/almost/blocked member. The template renders NOTHING at
    all on None: no shell, no <style>, no empty box. A forced "best available" row on a
    dead night is the kind of manufactured ranking the house forbids.
    """
    baskets = (membership or {}).get("baskets")
    if not isinstance(baskets, dict) or not baskets:
        return None

    # ── basket cycle state (kind == 'basket', newest stamp) ────────────────────────
    cyc: dict[str, Any] = {}
    cycles_as_of = None
    if cycles is not None and hasattr(cycles, "empty") and not cycles.empty:
        try:
            frame = cycles[cycles["kind"] == "basket"] if "kind" in cycles.columns else cycles
            frame = _latest_rows(frame, "date")
            if hasattr(frame, "iterrows"):
                for _, row in frame.iterrows():
                    cyc[str(row.get("id"))] = row
                    cycles_as_of = cycles_as_of or row.get("date")
        except Exception as exc:  # noqa: BLE001 — a bad cycle frame must not kill the page
            log.warning("cn theme tape: cycle frame unreadable (%s)", exc)
    if not cyc:
        return None

    # ── the considered universe, newest stamp ─────────────────────────────────────
    cand: dict[str, Any] = {}
    board_as_of = None
    if candidates is not None and hasattr(candidates, "empty") and not candidates.empty:
        try:
            frame = _latest_rows(candidates, "stamp_date")
            if hasattr(frame, "iterrows"):
                for _, row in frame.iterrows():
                    cand[str(row.get("ticker"))] = row
                    board_as_of = board_as_of or row.get("stamp_date")
        except Exception as exc:  # noqa: BLE001 — absence renders a quiet tape
            log.warning("cn theme tape: candidate ledger unreadable (%s)", exc)

    flows = _flow_index(flow, today or _as_date(cycles_as_of))

    # ── the continuation-watch cohort (accruing; zero rows is normal) ─────────────
    watching: set[str] = set()
    if watch is not None and hasattr(watch, "empty") and not watch.empty:
        try:
            if "board_definition" in watch.columns:
                rows = watch[watch["board_definition"] == CONTINUATION_BOARD]
                rows = _latest_rows(rows, "date")
                if hasattr(rows, "iterrows"):
                    watching = {str(r.get("ticker")) for _, r in rows.iterrows()}
        except Exception as exc:  # noqa: BLE001 — an empty cohort is a normal state
            log.warning("cn theme tape: continuation watch unreadable (%s)", exc)

    # ── per-theme accounting ──────────────────────────────────────────────────────
    rows: list[dict[str, Any]] = []
    for key, basket in baskets.items():
        if not isinstance(basket, dict):
            continue
        cycle = cyc.get("b-" + str(key))
        if cycle is None:
            continue
        phase = str(cycle.get("phase") or "")
        if phase not in PHASE_INDEX:
            continue
        members = [m for m in (basket.get("members") or [])
                   if isinstance(m, dict) and not m.get("removed")]
        if not members:
            continue

        counts = dict.fromkeys(BUCKET_KEYS, 0)
        grouped: dict[str, list[dict[str, Any]]] = {k: [] for k in BUCKET_KEYS}
        for member in members:
            ticker = str(member.get("ticker") or "")
            bucket, why_en, why_zh = _classify(cand.get(ticker))
            counts[bucket] += 1
            entry: dict[str, Any] = {"t": ticker, "zh": member.get("name_zh") or ticker}
            if why_en:
                entry["why_en"], entry["why_zh"] = why_en, why_zh
            if ticker in watching:
                entry["watched"] = True
            grouped[bucket].append(entry)

        # ONE reason under a group whose members all share it (Law 4: a constant
        # belongs in one place). Banks came back with "Reclaim failed" printed five
        # times on one line and Industrial Metals three; at that point the reason has
        # stopped discriminating between the names and is just noise between them.
        # A group with mixed reasons keeps them per name, which is where they earn
        # their place — that is the whole test.
        shared: dict[str, tuple[str, str]] = {}
        for bucket, entries in grouped.items():
            reasons = {(e.get("why_en"), e.get("why_zh")) for e in entries}
            if len(entries) > 1 and len(reasons) == 1:
                only = next(iter(reasons))
                if only[0]:
                    shared[bucket] = only
                    for entry in entries:
                        entry.pop("why_en", None)
                        entry.pop("why_zh", None)

        slope = cycle.get("osc_slope")
        try:
            slope = float(slope) if slope is not None else None
        except (TypeError, ValueError):
            slope = None
        flow_row = flows.get(str(key)) or {}
        stance = _stance_for(counts, phase)
        say_en, say_zh = STANCES[stance]
        words = PHASE_WORDS[phase]
        rows.append({
            "key": str(key),
            "name": basket.get("name") or str(key),
            "name_zh": basket.get("name_zh") or basket.get("name") or str(key),
            "phase": phase,
            "phase_i": PHASE_INDEX[phase],
            "state_en": words[0],
            "state_zh": words[1],
            "early": phase == EARLY_TURN,
            "slope": slope,
            "n_members": len(members),
            "counts": counts,
            "members": {k: v for k, v in grouped.items() if v and k != "quiet"},
            "shared_why": {k: v for k, v in shared.items() if k != "quiet"},
            "quiet_sample": [m["t"] for m in grouped["quiet"]][:6],
            "quiet_more": max(0, len(grouped["quiet"]) - 6),
            "quiet_why": shared.get("quiet", (None, None))[0]
                         or next((m.get("why_en") for m in grouped["quiet"]
                                  if m.get("why_en")), None),
            "quiet_why_zh": shared.get("quiet", (None, None))[1]
                            or next((m.get("why_zh") for m in grouped["quiet"]
                                     if m.get("why_zh")), None),
            "etf_proxy": basket.get("etf_proxy") or None,
            "flow_en": flow_row.get("state") or None,
            "flow_zh": flow_row.get("state_zh") or flow_row.get("state") or None,
            "stance": stance,
            "say_en": say_en.format(**counts),
            "say_zh": say_zh.format(**counts),
        })

    if not rows:
        return None

    # The condition (see the docstring): turned, or holding a live pick.
    qualified = [r for r in rows if r["early"] or r["counts"]["live"]]
    if not qualified:
        return None

    # Within the qualified set: something to trade first, then the sharpest turns.
    # Never by score — this panel ranks nothing, it only decides reading order.
    qualified.sort(key=lambda r: (
        -r["counts"]["live"],
        0 if r["early"] else 1,
        -(r["slope"] if r["slope"] is not None else -999.0),
        r["name"],
    ))
    ceiling = max(1, int(max_rows or MAX_ROWS))
    shown, overflow = qualified[:ceiling], max(0, len(qualified) - ceiling)

    # Honest-null gate: a tape where nothing is live, close or held out is a dead tape.
    if not any(r["counts"]["live"] or r["counts"]["almost"] or r["counts"]["blocked"]
               for r in shown):
        return None

    return {
        "as_of": str(cycles_as_of) if cycles_as_of else None,
        "board_as_of": str(board_as_of) if board_as_of else None,
        "rows": shown,
        "n_themes": len(rows),
        "overflow": overflow,
        "measuring": True,
        "flow_live": bool(flows),
        "watch_live": bool(watching),
    }
