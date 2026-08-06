"""Theme Tape — market heat reconciled against the Prophet board (DISPLAY-TIER).

WHAT THIS IS
------------
A presentation join, and nothing else. It answers one question the US board has
never been able to answer on its own:

    "Software is the hottest thing in the market right now — is the board on it,
     and if not, why not?"

Charter: research/PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §W2.
Standing defect class it closes: detection-without-narration (the Mag-7 silence
postmortem, 2026-08-03) — the engine knew, the surface said nothing.

ZERO AUTHORITY (hard fence)
---------------------------
This module reads two already-published artifacts and returns a dict for a
template. It writes no file, mutates no input, and produces no rank, gate,
score, size or membership field. Nothing here can change which names are on the
board or in what order — the board is joined against, never re-sorted. The one
ordering that exists (which THEMES to show) is the rotation artifact's own
`emerging_score`, quoted, not recomputed.

THE THREE FENCES THAT SHAPED IT
-------------------------------
1. `research/DO_NOT_REBUILD.md` DNR:HOLD-IGNITION-SURFACES (Ignition Radar, suspended 2026-07-23)
   requires "an honest-null state, no forced top-K ranking in a dead tape".
   So the tape is FLOOR-gated, not rank-gated: a theme must actually be
   accelerating (`emerging_score > 0`) and sit in a constructive quadrant to
   appear at all. When nothing clears the floor the builder returns None and
   the panel renders nothing — silence is the correct read on a dead tape.
2. The rotation read grades ITSELF and is not yet proven (`track_record.verdict
   == "measuring"`, every horizon `proven: false`, and the h5 emerging bucket is
   NEGATIVE at -0.09% with a 48.3% hit rate). Doctrine Law 5 therefore requires a
   plain-word null on Tier 1; `measuring` carries that flag to the template.
   This is also WHY the panel narrates coverage rather than opportunity: what the
   board is doing with a theme's names is an observable fact and needs no edge
   claim, so the panel stays honest whether or not the heat read ever proves out.
3. Doctrine Law 2 bans machine slugs from the glance tier. Every reason a member
   is not on the buy lanes is translated here, in Python, through an explicit
   table. An unknown slug is DROPPED, never printed — a raw slug on a user
   surface is a defect, and a guessed translation is a worse one.

THE PARTITION
-------------
Every member of a shown theme lands in exactly one bucket (the CN total-partition
principle, masterplan §W2.4 — nothing eligible is invisible):

    live · setting_up · ran · leading · watching · quiet

`quiet` is the remainder: a member with no row anywhere on the board. It carries
ONE shared reason ("no fresh entry trigger today"), never a per-name invention —
the board never looked at most of these names, and saying otherwise would be a
fabricated rejection.

CONTEXT IT READS (both fail-open, both already published)
---------------------------------------------------------
    site/marketdata/subsector_rotation.json  themes[] + subsectors[].members[]
    site/factordata/us_standouts.json        buy/ran/leaders/watch/laggards

The rotation artifact is written LATER in the same nightly than the page that
consumes it, so a first render reads the previous day's file. That is why the
view carries the artifact's own `as_of` and the panel stamps it: a one-day-old
heat read labelled with its own date is honest; an unlabelled one is not.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

__all__ = [
    "build_theme_tape",
    "STANCES",
    "QUADRANT_HEAT",
    "REASON_TEXT",
    "STAGE_LABEL",
    "FORESIGHT_LABELS",
    "THEME_MAP",
    "THEME_UNMAPPED",
    "THEME_NAME_ZH",
    "TURN_N",
    "TURN_1W_MIN",
    "TURN_1M_MAX",
]

# ── tunables ────────────────────────────────────────────────────────────────
TOP_N = 5           # themes shown at most; fewer when fewer clear the floor
QUIET_SAMPLE = 8    # named sample of the quiet remainder (rest becomes "+N")
SHELF_SAMPLE = 8    # named sample of the off-heat foresight shelf (rest → "+N")
MAX_AGE_DAYS = 10   # older rotation artifact than this → no panel at all

# A theme must be accelerating AND not decaying to appear. This is the floor that
# makes the tape self-empty on a dead tape (fence 1); it is not a ranker.
CONSTRUCTIVE_QUADRANTS = ("leading", "improving")

# ── the washout-turn group (W-D) ────────────────────────────────────────────
# The floor above is a MOMENTUM floor, and a washout-turn is by construction the
# state a momentum lens certifies last: a theme down hard over a month and up over
# the past week prints `quadrant="lagging"` with a negative `emerging_score`, so it
# is structurally invisible on the ladder. Space Tech on 2026-08-02 is the case —
# 28th of 41, "lagging", emerging_score −0.485, while its Satellites subsector ran
# +2.03% against the market on the week after −14.17% on the month. The tape could
# not say "washed out, now turning" at all.
#
# This is a SECOND, CLEARLY-LABELLED group, never a floor change: the TOP_N
# selection above is untouched, and nothing here can add, remove or reorder a heat
# row. Charter: research/PROPHET_US_MISSED_IGNITIONS_MASTERPLAN_BY_FABLE.md §W-D.
#
# ZERO AUTHORITY, AND A MEASURED NULL BEHIND IT. The sector washout→turn
# construction is a measured NULL as a scored trigger (Oracle P8 / DNR "Washout ×
# turn"), so this group is a disclosure of engine state and never a buy claim —
# the copy is watch-vocabulary throughout and no row carries a stance sentence.
TURN_N = 3            # at most three rows; honest-null (no group) when none qualify
TURN_1W_MIN = 2.0     # relative 1W, %  — the turn leg
TURN_1M_MAX = -10.0   # relative 1M, %  — the washout leg

# WHY THE SHAPE IS READ AT BOTH GRAINS.
# Measured over the 25 archived rotation days (2026-07-05..08-02), the theme-grain
# test alone fires on ONE day in 25 (Semiconductors, 07-24) and never once selects
# Space Tech: a theme rolls up as the MEAN of its subsectors, so the two Space Tech
# sleeves still falling (Defense −1.05% 1W, Launch −0.08%) average the turning ones
# away and the theme's own 1W lands at −0.92%. The same thresholds at subsector
# grain select the turn exactly — Satellites +2.03 / −14.17 on 2026-08-02.
# So a theme qualifies on its OWN figures or on any ONE of its subsectors, and a
# row that qualified through a sleeve NAMES that sleeve. Naming it is not a
# decoration: an unnamed row would say "Space Tech is turning" when what is turning
# is one of its five sleeves, which is precisely the slice-overstates-the-row
# failure THEME_UNMAPPED documents below.

# ── vocabulary ──────────────────────────────────────────────────────────────
# Quadrant → the plain-word heat phrase. The raw quadrant slug never reaches the
# page. Kept to ≤4 words: this sits on the glance tier beside the theme name.
QUADRANT_HEAT: dict[str, tuple[str, str]] = {
    "leading": ("leading the market", "领先大盘"),
    "improving": ("catching up fast", "快速追赶"),
    # Below the floor today, mapped anyway so a floor change can never leak a slug.
    "weakening": ("losing its lead", "领先在减弱"),
    "lagging": ("still behind", "仍落后"),
}

# Why a member is on the board but not on a buy lane. Keys are the slugs the
# artifacts actually emit; values are what a person reads.
#
#   extended / capped_by_entry / earnings_blackout
#       live today in us_standouts[*].dossier.no_buy_reasons.
#   not_topped_veto / not_topped / freshness_expired
#       signal_gate near-miss reasons (W0.2, concurrent). Absent today; mapped
#       now so they narrate the moment they appear rather than waiting on a
#       second PR. Wording is taken from the engine's own rule text —
#       "buying into a topped oscillator blocked" and "aged cross excluded"
#       (engine/grading.py) — not invented.
REASON_TEXT: dict[str, tuple[str, str]] = {
    "extended": ("already extended — watch, don't chase", "已过热 — 观望，勿追高"),
    "capped_by_entry": ("entry window has passed", "入场窗口已过"),
    "earnings_blackout": ("earnings due — held back", "临近财报 — 暂缓"),
    "not_topped_veto": ("overbought — watch, don't chase", "超买 — 观望，勿追高"),
    "not_topped": ("overbought — watch, don't chase", "超买 — 观望，勿追高"),
    "freshness_expired": ("already ran — waiting for a re-entry", "已启动 — 等待再次入场"),
}

# The six buckets, in decision order. This order is the panel's column order and
# the stance priority below reads down it.
BUCKETS = ("live", "setting_up", "ran", "leading", "watching", "quiet")

# ── the Foresight Desk join (W5a) ───────────────────────────────────────────
# The tape answers "what is the board doing with the hot theme's names". The
# Thematic Foresight Desk (engine/foresight_cascade.py) answers the question that
# comes BEFORE it — which themes are loading while price is still quiet. Joining
# the two is display-only in the strictest sense: nothing here reads a price, and
# the desk's stage cannot move a theme up, down, on or off the tape. Heat rank
# stays the only ordering that exists.
#
# TWO PLAIN WORDS, AND NOTHING ELSE.
# The desk's stage enum has ten values. Nine of them are internal state names in
# exactly the family Doctrine Law 2 bans from the glance tier (the same family as
# IGNITION / UPTURN_CONFIRMED), so none of them is ever printed. They collapse to
# two words a reader already owns, and every stage that does not map cleanly onto
# one of those two gets NO chip at all — absence beats a chip a reader has to
# decode. The grouping is the desk's OWN: `foresight_cascade.THESIS_STAGES` and
# its text/fingerprint twins are the stages where the desk says edge remains; the
# split is quoted from that module, not invented here.
#
#   loading    the six thesis stages — supply tightening while estimates are flat
#              or only starting to move. The state the desk exists to catch.
#   re-rating  RE-RATING — estimates already broad. Late, by the desk's own read.
#   (no chip)  GLUT-RISK  an exit-risk state; the tape is not a risk surface and a
#                         warning it is not chartered to give would be read as one
#              WATCH      the desk's explicit "nothing here yet"
#              UNKNOWN    no read at all
#
# Anything the desk adds later falls through to None and prints nothing, which is
# the safe direction: a new stage is silent until someone decides its word.
STAGE_LABEL: dict[str, str | None] = {
    "PRECIPICE": "loading",
    "PRECIPICE (text)": "loading",
    "PRECIPICE (fingerprint)": "loading",
    "BROADENING": "loading",
    "BROADENING (text)": "loading",
    "BROADENING (fingerprint)": "loading",
    "RE-RATING": "re_rating",
    "GLUT-RISK": None,
    "WATCH": None,
    "UNKNOWN": None,
}

# "loading up", not "loading": on a web page a small grey chip reading "loading"
# is a spinner, and beside a LIST of names the whole list reads as still
# arriving. The particle costs one word and removes the reading entirely. The
# Chinese carries no such collision, so 蓄势 is unchanged.
FORESIGHT_LABELS: dict[str, tuple[str, str]] = {
    "loading": ("loading up", "蓄势"),
    "re_rating": ("re-rating", "重估"),
}

# What the word means, for the row's hover (Tier 2). A chip four characters wide
# states a condition; this is where it says what the condition IS. Both are
# written from the desk's own rationale text, not paraphrased upward into a
# claim the desk never made.
FORESIGHT_TIP: dict[str, tuple[str, str]] = {
    "loading": ("supply tightening while earnings estimates are still flat",
                "供给正在收紧，而盈利预期尚未跟上"),
    "re_rating": ("earnings estimates already broad — the early part is behind it",
                  "盈利预期已普遍上调 — 早期阶段已经过去"),
}

# Stage strings that carry their own admission that no numeric measurement stands
# behind them. The desk appends the qualifier itself, so this reads the desk's
# vocabulary rather than second-guessing it.
_UNCONFIRMED_STAGES = frozenset({
    "PRECIPICE (text)", "PRECIPICE (fingerprint)",
    "BROADENING (text)", "BROADENING (fingerprint)",
})

# ── the taxonomy join: an explicit table, never a fuzzy match ───────────────
# The two vocabularies were built by different programs and do not line up: the
# desk keys 18 physical supply-chain themes, the rotation artifact publishes 41
# market themes by display name. A string-similarity join would silently marry
# "Solar" to "Social Media" on a bad day and no test would see it, so every pair
# below is hand-decided, and every desk theme that is NOT paired is listed in
# THEME_UNMAPPED with the reason. Coverage of both tables is asserted in
# tests/test_theme_tape.py, as is the existence of every target — a mistyped
# target does not raise, it just never joins, which is the failure mode that
# would ship a dead feature looking alive.
#
# THE ADMISSION TEST — composition, not resemblance.
# Several desk themes may share one target, but only when they JOINTLY COMPOSE
# it: AI semis + memory + equipment together substantially ARE the rotation
# theme "Semiconductors", so a chip on that row is a statement about the row.
# Resemblance is not enough. A desk theme that is a narrow slice of a much
# broader row fails the test and is left unmapped, because a row-level chip
# would overstate the slice — the reader sees one word against a hundred-member
# theme and has no way to know it was about three of them. The slice still
# reaches them, by name, on the shelf. (Ruling 2026-08-04; the three healthcare
# desk themes were mapped here in the first pass and cut for exactly this.)
# Where two mapped desk themes disagree about the word, the chip is dropped —
# see `_foresight_index`.
THEME_MAP: dict[str, str] = {
    # composition — the three desk themes together are the rotation theme
    "ai_semiconductors": "Semiconductors",
    "memory_storage": "Semiconductors",
    "semicap_equipment": "Semiconductors",
    # exact or head-noun identity
    "defense_aerospace": "Defense & Aerospace",
    "fintech_payments": "FinTech",
    "cybersecurity": "Cybersecurity",
    "space_satellite": "Space Tech",
    "robotics_automation": "Robotics",
    # dominant constituent — the desk theme drives the rotation theme
    "solar": "Energy Renewable",
    "rare_earth_critical_min": "Commodities Metals",
    "copper_steel_electrify": "Commodities Metals",
}

# Deliberately unpaired, with the reason. These themes still reach the reader —
# they appear on the off-heat shelf under their own name — they simply cannot be
# attached to a tape row, because no rotation theme means the same thing.
THEME_UNMAPPED: dict[str, str] = {
    # failed the composition test (2026-08-04). Each is a narrow slice of
    # "Healthcare & Biotech", and unlike the semiconductor trio they do not add
    # up to it — pharma, managed care and hospitals are most of that row. A chip
    # there would say "loading up" about a theme where three slices are.
    "glp1_obesity":
        "a narrow slice of Healthcare & Biotech, not a constituent that "
        "composes it — a row-level word would overstate the slice",
    "medical_devices":
        "a narrow slice of Healthcare & Biotech, not a constituent that "
        "composes it — a row-level word would overstate the slice",
    "diagnostics_lifesci":
        "a narrow slice of Healthcare & Biotech, not a constituent that "
        "composes it — a row-level word would overstate the slice",
    "nuclear_power":
        "no rotation counterpart; the SMR thesis is neither Energy Traditional "
        "nor Energy Renewable and choosing either would misstate it",
    "ag_fertilizer":
        "two candidate targets (Agriculture & FoodTech / Commodities Agriculture) "
        "with no principled tiebreak — fertilizer is an input to both",
    "data_center_power":
        "no rotation counterpart; Big Data and Cloud Computing are the software "
        "layer, not the power and cooling build-out",
    "grid_electrification":
        "no rotation counterpart; transmission build-out is not any published "
        "rotation theme",
}

# The desk publishes English display names only. These are the Chinese twins, so
# the shelf reads in both languages (Doctrine §5.5 — bilingual parity).
THEME_NAME_ZH: dict[str, str] = {
    "ai_semiconductors": "人工智能半导体",
    "memory_storage": "存储与 HBM",
    "semicap_equipment": "半导体设备",
    "defense_aerospace": "国防与航空航天",
    "fintech_payments": "金融科技与支付",
    "cybersecurity": "网络安全",
    "space_satellite": "太空与卫星",
    "robotics_automation": "机器人与自动化",
    "solar": "光伏",
    "rare_earth_critical_min": "稀土与关键矿产",
    "copper_steel_electrify": "铜、钢与电气化",
    "glp1_obesity": "GLP-1 与减重",
    "medical_devices": "医疗器械",
    "diagnostics_lifesci": "诊断与生命科学工具",
    "nuclear_power": "核电与小型堆",
    "ag_fertilizer": "农业与化肥",
    "data_center_power": "数据中心电力与散热",
    "grid_electrification": "电网与电气化",
}

# ── the stance table (Doctrine Law 1) ───────────────────────────────────────
# Chosen MECHANICALLY from the counts, never generated. The rule is a strict
# priority walk down BUCKETS: the strongest state the board actually holds in
# this theme decides the verb, because that is the row a reader would act on
# first. Every verb comes from the doctrine's sanctioned stance vocabulary
# (Act · Get ready · Watch — don't chase · Stand aside · Ignore).
#
#   live > 0                    → act          "act per row"
#   setting_up > 0              → get_ready    "get ready, no entry yet"
#   ran + leading > 0           → dont_chase   "watch, don't chase"
#   watching > 0                → stand_aside  "watch list only"
#   otherwise (all board = 0)   → nothing      "no board names here"
#
# Note the last one is the whole point of the panel: a hot theme the board is
# silent on still prints a line, and the line says so.
STANCES: dict[str, tuple[str, str]] = {
    "act": ("Members live on the board — act per row.",
            "榜上有可操作成分股 — 按行操作。"),
    "get_ready": ("Setting up — get ready, no entry yet.",
                  "正在形成 — 做好准备，尚无入场。"),
    "dont_chase": ("Already extended — watch, don't chase.",
                   "已经拉升 — 观望，勿追高。"),
    "stand_aside": ("On the watch list only — stand aside.",
                    "仅在观察名单 — 暂不操作。"),
    "nothing": ("No board names here — nothing to do.",
                "榜上没有成分股 — 无需操作。"),
}


def _stance_for(counts: dict[str, int]) -> str:
    """Pick the stance key from the counts. Pure, total, and order-defining."""
    if counts.get("live"):
        return "act"
    if counts.get("setting_up"):
        return "get_ready"
    if counts.get("ran") or counts.get("leading"):
        return "dont_chase"
    if counts.get("watching"):
        return "stand_aside"
    return "nothing"


def _reasons_for(row: dict[str, Any]) -> tuple[str, str] | tuple[None, None]:
    """First translatable reason this board row carries, in plain words.

    Reads the two places a reason lives, in order of specificity:
      1. `dossier.no_buy_reasons`  — the explicit held-back slugs
      2. `near_miss_reason`        — signal_gate's W0.2 stamp (row or verdict)
    An unrecognised slug yields nothing rather than a raw slug on the page.
    """
    slugs: list[str] = []
    dossier = row.get("dossier")
    if isinstance(dossier, dict):
        for slug in dossier.get("no_buy_reasons") or []:
            if isinstance(slug, str):
                slugs.append(slug)
    signal = row.get("signal") if isinstance(row.get("signal"), dict) else {}
    for candidate in (row.get("near_miss_reason"), signal.get("near_miss_reason")):
        if isinstance(candidate, str):
            slugs.append(candidate)
    for slug in slugs:
        text = REASON_TEXT.get(slug)
        if text:
            return text
    return (None, None)


def _board_index(standouts: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """ticker → {bucket, why_en, why_zh}. First lane to claim a ticker wins.

    Lane order is the board's own decision order, so a name that is both a fresh
    buy and (say) a leader is reported at its most actionable state — which is
    the state the reader would act on. `buy` splits by the row's `stage` field
    (live / setting_up / ran), which is the board's own vocabulary.
    """
    index: dict[str, dict[str, Any]] = {}
    if not isinstance(standouts, dict):
        return index

    def claim(row: Any, bucket: str) -> None:
        if not isinstance(row, dict):
            return
        ticker = row.get("ticker")
        if not isinstance(ticker, str) or not ticker or ticker in index:
            return
        why_en, why_zh = _reasons_for(row)
        index[ticker] = {"bucket": bucket, "why_en": why_en, "why_zh": why_zh}

    for row in standouts.get("buy") or []:
        if not isinstance(row, dict):
            continue
        stage = row.get("stage")
        bucket = stage if stage in ("live", "setting_up", "ran") else "watching"
        claim(row, bucket)
    for row in standouts.get("ran") or []:
        claim(row, "ran")
    for row in standouts.get("leaders") or []:
        claim(row, "leading")
    for row in standouts.get("watch") or []:
        claim(row, "watching")
    for row in standouts.get("laggards") or []:
        claim(row, "watching")
    return index


def _theme_members(rotation: dict[str, Any], theme_name: str) -> list[str]:
    """Union of every member ticker across the theme's subsectors, order kept.

    The theme records carry no member list of their own (`n_members` there counts
    SUBSECTORS, not tickers) — membership lives one level down, so this walks the
    subsector table. Order is the artifact's own, which is its rank order, so the
    named sample a reader sees is the theme's strongest names first.
    """
    seen: set[str] = set()
    members: list[str] = []
    for sub in rotation.get("subsectors") or []:
        if not isinstance(sub, dict) or sub.get("theme") != theme_name:
            continue
        for member in sub.get("members") or []:
            ticker = member.get("t") if isinstance(member, dict) else None
            if isinstance(ticker, str) and ticker and ticker not in seen:
                seen.add(ticker)
                members.append(ticker)
    return members


def _member_state(
    members: list[str], board: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Partition a theme's members across BUCKETS, with the Law-4 reason lifting.

    Extracted verbatim from the row loop so the washout-turn group below narrates
    membership through the SAME machinery as a heat row — one implementation, so
    the two groups cannot drift into describing the board differently. Pure: it
    reads the board index and returns a new dict, touching neither input.
    """
    counts = dict.fromkeys(BUCKETS, 0)
    grouped: dict[str, list[dict[str, Any]]] = {b: [] for b in BUCKETS if b != "quiet"}
    quiet: list[str] = []

    for ticker in members:
        hit = board.get(ticker)
        if hit is None:
            counts["quiet"] += 1
            quiet.append(ticker)
            continue
        bucket = hit["bucket"]
        counts[bucket] += 1
        grouped[bucket].append(
            {"t": ticker, "why_en": hit["why_en"], "why_zh": hit["why_zh"]}
        )

    # Law 4 — a constant belongs in one place, not on every row. When every name
    # in a group was held back for the SAME reason (the common case: a whole
    # leading group is "already extended"), the reason is lifted to the group and
    # struck from the names, so the list reads "SNOW · OKTA — already extended"
    # instead of saying it once per ticker. Mixed groups keep per-name reasons.
    shared: dict[str, tuple[str, str] | None] = {}
    for bucket, rows_in in grouped.items():
        reasons = {(r["why_en"], r["why_zh"]) for r in rows_in}
        if len(rows_in) > 1 and len(reasons) == 1 and rows_in[0]["why_en"]:
            shared[bucket] = (rows_in[0]["why_en"], rows_in[0]["why_zh"])
            for r in rows_in:
                r["why_en"] = r["why_zh"] = None
        else:
            shared[bucket] = None

    return {
        "n_members": len(members),
        "n_on_board": len(members) - counts["quiet"],
        "counts": counts,
        "members": grouped,
        "shared_why": shared,
        "quiet_sample": quiet[:QUIET_SAMPLE],
        "quiet_more": max(0, len(quiet) - QUIET_SAMPLE),
    }


def _rs_pair(row: Any) -> tuple[float | None, float | None]:
    """(1W, 1M) relative strength off a theme or subsector record, or (None, None)."""
    rs = row.get("rs") if isinstance(row, dict) else None
    if not isinstance(rs, dict):
        return (None, None)
    out: list[float | None] = []
    for horizon in ("1W", "1M"):
        value = rs.get(horizon)
        out.append(float(value) if isinstance(value, (int, float)) else None)
    return (out[0], out[1])


def _turn_shape(one_w: float | None, one_m: float | None) -> bool:
    """The washout-turn shape: up hard on the week, down hard on the month."""
    return (one_w is not None and one_m is not None
            and one_w > TURN_1W_MIN and one_m < TURN_1M_MAX)


def _numerically_confirmed(theme: dict[str, Any]) -> bool:
    """Does a price- or flow-independent NUMBER stand behind this stage?

    Three ways a stage can be unconfirmed, and a row must clear all three:
      1. the stage string carries its own qualifier — "(text)" / "(fingerprint)"
      2. `bottleneck_text_only`        — language evidence alone
      3. `bottleneck_fingerprint_only` — annual filing evidence alone

    Leg 3 is why RE-RATING has to be checked and not assumed: the stage string
    for a re-rating theme carries no qualifier at all, so on the stage alone it
    would read as confirmed while its band is text-only — which is exactly the
    state today's desk is in. Written as a per-theme predicate on purpose: the
    disclosure it drives is conditional, so it retires by itself, one theme at a
    time, the day real measurements arrive. Nothing here needs editing then.
    """
    if theme.get("stage") in _UNCONFIRMED_STAGES:
        return False
    if theme.get("bottleneck_text_only") or theme.get("bottleneck_fingerprint_only"):
        return False
    return True


def _foresight_themes(
    foresight: dict[str, Any] | None, today: Any = None
) -> list[dict[str, Any]]:
    """The desk's staged themes, translated, in the desk's own published order.

    Order is quoted, never recomputed — the artifact already sorts by edge
    remaining, and re-sorting here would manufacture a second ranking on a panel
    whose whole argument is that it has none. Themes whose stage earns no word
    are dropped here, so nothing downstream has to know the enum.

    Returns [] for a missing, malformed or stale desk read: a filing-language
    read weeks old is not evidence that anything is loading today, and the same
    age rule the rotation artifact answers to applies here.
    """
    if not isinstance(foresight, dict):
        return []
    age = _age_days(foresight.get("asof"), today)
    if age is not None and age > MAX_AGE_DAYS:
        log.info("theme_tape: foresight desk read is %sd old — chips suppressed", age)
        return []

    staged: list[dict[str, Any]] = []
    for theme in foresight.get("themes") or []:
        if not isinstance(theme, dict):
            continue
        key = theme.get("theme")
        label = STAGE_LABEL.get(theme.get("stage"))
        if not isinstance(key, str) or not key or label is None:
            continue
        name = theme.get("name")
        if not isinstance(name, str) or not name:
            continue
        staged.append(
            {
                "key": key,
                "name": name,
                "name_zh": THEME_NAME_ZH.get(key) or name,
                "label": label,
                "label_en": FORESIGHT_LABELS[label][0],
                "label_zh": FORESIGHT_LABELS[label][1],
                "target": THEME_MAP.get(key),
                "confirmed": _numerically_confirmed(theme),
            }
        )
    return staged


def _foresight_index(staged: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """rotation theme name → the one chip it earns, or no entry at all.

    Several desk themes can point at one rotation theme (three semiconductor
    themes do). Resolution is deliberately unclever:

      * a desk theme whose stage earns no word never reached this list, so it
        does not vote — a WATCH sibling cannot veto a live read;
      * if every voter says the same word, that word is the chip;
      * if two voters disagree, the row gets NO chip.

    That last rule is the conservative one and it costs real coverage — a
    semiconductor complex that is re-rating at the leading edge while memory is
    still tightening prints nothing. It is still right: the chip is four
    characters wide and has no room to hold a contradiction, and a reader who
    sees one word cannot tell it was a coin flip.
    """
    votes: dict[str, dict[str, Any]] = {}
    for item in staged:
        target = item.get("target")
        if not target:
            continue
        seen = votes.setdefault(target, {"labels": set(), "sources": []})
        seen["labels"].add(item["label"])
        seen["sources"].append(item)

    index: dict[str, dict[str, Any]] = {}
    for target, seen in votes.items():
        if len(seen["labels"]) != 1:
            log.info("theme_tape: %s carries disagreeing desk stages — no chip", target)
            continue
        label = next(iter(seen["labels"]))
        sources = seen["sources"]
        index[target] = {
            "label": label,
            "label_en": FORESIGHT_LABELS[label][0],
            "label_zh": FORESIGHT_LABELS[label][1],
            # Named because a target can be composed of several desk themes:
            # "Semiconductors · loading up" is more useful when the hover says
            # it is the memory and equipment legs the desk is reading.
            "sources_en": " · ".join(s["name"] for s in sources),
            "sources_zh": " · ".join(s["name_zh"] for s in sources),
            "tip_en": FORESIGHT_TIP[label][0],
            "tip_zh": FORESIGHT_TIP[label][1],
            "confirmed": all(s["confirmed"] for s in sources),
        }
    return index


def _washout_turns(
    rotation: dict[str, Any],
    ranked: list[dict[str, Any]],
    shown: set[str],
    board: dict[str, dict[str, Any]],
    top_n: int = TURN_N,
) -> list[dict[str, Any]]:
    """Themes the momentum floor rejects that are nonetheless turning up.

    Runs AFTER the heat rows are final and reads none of their state beyond the
    set of names already shown, so it is structurally incapable of changing the
    TOP_N selection or its order.

    A theme qualifies when it is NOT on the heat list and the washout-turn shape
    holds on its own relative figures OR on any one of its subsectors; a row that
    qualified through a subsector carries that subsector's name and figures, since
    those are the numbers that earned it its place. Capped, sorted by the
    qualifying 1W descending — the strongest turn first.
    """
    subs_by_theme: dict[str, list[dict[str, Any]]] = {}
    for sub in rotation.get("subsectors") or []:
        if isinstance(sub, dict) and isinstance(sub.get("theme"), str):
            subs_by_theme.setdefault(sub["theme"], []).append(sub)

    turns: list[dict[str, Any]] = []
    for position, theme in enumerate(ranked, start=1):
        name = theme.get("theme")
        if not isinstance(name, str) or not name or name in shown:
            continue

        one_w, one_m = _rs_pair(theme)
        lead: dict[str, Any] | None = None
        if _turn_shape(one_w, one_m):
            turn_w, turn_m = one_w, one_m
        else:
            # The sleeve read. Best (largest 1W) qualifying subsector wins the row.
            candidates = []
            for sub in subs_by_theme.get(name, []):
                sub_w, sub_m = _rs_pair(sub)
                if _turn_shape(sub_w, sub_m):
                    candidates.append((sub_w, sub_m, sub))
            if not candidates:
                continue
            turn_w, turn_m, lead = max(candidates, key=lambda c: c[0])

        members = _theme_members(rotation, name)
        if not members:
            continue

        lead_en = lead.get("name") if lead else None
        lead_zh = (lead.get("name_zh") or lead_en) if lead else None
        turns.append(
            {
                "name": name,
                "name_zh": theme.get("theme_zh") or name,
                # Its place on the heat ladder it just failed — the row's own
                # admission that the acceleration read ranks it near the bottom.
                "rank": position,
                "turn_1w": round(float(turn_w), 2),
                "turn_1m": round(float(turn_m), 2),
                # None when the theme's own figures earned the row; the subsector's
                # display name when a single sleeve did.
                "lead_en": lead_en if isinstance(lead_en, str) else None,
                "lead_zh": lead_zh if isinstance(lead_zh, str) else None,
                **_member_state(members, board),
            }
        )

    turns.sort(key=lambda t: -t["turn_1w"])
    return turns[:top_n]


def _age_days(as_of: Any, today: Any = None) -> int | None:
    """Whole days between an ISO date string and today. None when unparseable."""
    from datetime import date

    if not isinstance(as_of, str) or len(as_of) < 10:
        return None
    try:
        stamped = date.fromisoformat(as_of[:10])
    except ValueError:
        return None
    return ((today or date.today()) - stamped).days


def build_theme_tape(
    rotation: dict[str, Any] | None,
    standouts: dict[str, Any] | None,
    top_n: int = TOP_N,
    today: Any = None,
    foresight: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Join the hottest themes against the board. None → render nothing.

    Returns None (and the panel disappears) when the rotation artifact is
    missing, unreadable, stale beyond MAX_AGE_DAYS, or when no theme clears the
    constructive floor. That last case is the honest-null the Ignition Radar
    ruling requires: a dead tape prints no tape.

    `foresight` is the Thematic Foresight Desk read (site/basketdata/
    foresight_cascade.json), and it is optional in the strongest sense: omit it,
    hand it None, hand it a stale or malformed file, and every byte of the panel
    below is unchanged. It adds a word to rows that earn one and a shelf of the
    themes loading off the heat list — it never adds, removes, or reorders a row.
    """
    if not isinstance(rotation, dict):
        return None
    themes = rotation.get("themes")
    if not isinstance(themes, list) or not themes:
        return None

    as_of = rotation.get("asof")
    age = _age_days(as_of, today)
    if age is not None and age > MAX_AGE_DAYS:
        log.info("theme_tape: rotation artifact is %sd old — panel suppressed", age)
        return None

    # Rank by the artifact's own score. Sorting here does not create authority:
    # it quotes an ordering the artifact already publishes and the rotation page
    # already renders.
    ranked = sorted(
        (t for t in themes if isinstance(t, dict)),
        key=lambda t: -(t.get("emerging_score") or 0.0),
    )
    rank_of = len(ranked)

    board = _board_index(standouts)
    staged = _foresight_themes(foresight, today)
    chips = _foresight_index(staged)
    rows: list[dict[str, Any]] = []

    for position, theme in enumerate(ranked, start=1):
        if len(rows) >= top_n:
            break
        score = theme.get("emerging_score") or 0.0
        quadrant = theme.get("quadrant")
        # THE FLOOR (fence 1) — not a ranker, a gate.
        if score <= 0 or quadrant not in CONSTRUCTIVE_QUADRANTS:
            continue
        name = theme.get("theme")
        if not isinstance(name, str) or not name:
            continue

        members = _theme_members(rotation, name)
        if not members:
            continue

        state = _member_state(members, board)

        heat_en, heat_zh = QUADRANT_HEAT.get(quadrant, (None, None))
        relative = theme.get("rs") if isinstance(theme.get("rs"), dict) else {}
        stance = _stance_for(state["counts"])
        say_en, say_zh = STANCES[stance]
        rows.append(
            {
                "name": name,
                "name_zh": theme.get("theme_zh") or name,
                "rank": position,
                "quadrant": quadrant,
                "heat_en": heat_en,
                "heat_zh": heat_zh,
                **state,
                # The stance key stays for tests and styling; the resolved pair is
                # carried on the row so the template never indexes a table itself.
                "stance": stance,
                "say_en": say_en,
                "say_zh": say_zh,
                # The desk's word for this theme, or nothing. Attached AFTER the
                # row is otherwise complete, so it is visibly incapable of
                # changing which themes are here or in what order.
                "foresight": chips.get(name),
                # Tier-2 receipt figures only — never rendered on the glance tier.
                "rs_1w": relative.get("1W"),
                "rs_1m": relative.get("1M"),
                "score": round(float(score), 2),
            }
        )

    if not rows:
        return None

    # THE SHELF — desk-staged themes the heat list did not surface. This is the
    # majority case and the reason the join is worth making: the desk reads
    # filings and language, so it sees a theme tighten while the tape, which
    # reads price, still has nothing to say. A theme already on a row above is
    # excluded — it is on the heat list by definition, and printing it here too
    # would say the opposite. Grouped by word, each group in the desk's order.
    shown = {r["name"] for r in rows}

    # THE WASHOUT-TURN GROUP (W-D) — the states the momentum floor above rejects
    # by construction. Computed here, off the finished heat rows, so it can only
    # ever be a second group BELOW them and never a change to them. Empty list on
    # a night when nothing is turning, and the template then renders exactly what
    # it rendered before this group existed: no header, no rows, no shell.
    turns = _washout_turns(rotation, ranked, shown, board)

    shelf: list[dict[str, Any]] = []
    for label in ("loading", "re_rating"):
        off = [s for s in staged if s["label"] == label and s.get("target") not in shown]
        if not off:
            continue
        shelf.append(
            {
                "label": label,
                "label_en": FORESIGHT_LABELS[label][0],
                "label_zh": FORESIGHT_LABELS[label][1],
                "names_en": [s["name"] for s in off][:SHELF_SAMPLE],
                "names_zh": [s["name_zh"] for s in off][:SHELF_SAMPLE],
                "more": max(0, len(off) - SHELF_SAMPLE),
            }
        )

    # Doctrine Law 5, as a CONDITION and never as a constant. Today every staged
    # theme is an early read with no measurement behind it, so the panel says so;
    # the flag is computed per build from the themes a reader can actually SEE —
    # a chip on a row above, or a name on the shelf — so it retires itself the
    # day the desk's numeric legs light up, one theme at a time and with nothing
    # here to edit. A fixed string would still be claiming this in a year.
    visible = [
        s for s in staged
        if (s.get("target") in shown and s.get("target") in chips)
        or s.get("target") not in shown
    ]
    unconfirmed = any(not s["confirmed"] for s in visible)

    track = rotation.get("track_record")
    track = track if isinstance(track, dict) else {}
    proven = track.get("proven") if isinstance(track.get("proven"), dict) else {}

    return {
        "as_of": as_of,
        "board_as_of": (standouts or {}).get("as_of") if isinstance(standouts, dict) else None,
        "rank_of": rank_of,
        "rows": rows,
        # The washout-turn group (W-D). [] is the honest null: no group is drawn.
        "washout_turns": turns,
        # Doctrine Law 5 — the null the template must disclose in plain words.
        # True whenever no horizon has cleared the artifact's own significance bar.
        "measuring": not any(bool(v) for v in proven.values()),
        "n_days": track.get("n_days"),
        # The Foresight Desk layer. Empty shelf and False flag when the desk read
        # is absent, stale or silent — the template then renders exactly what it
        # rendered before this layer existed.
        "foresight_shelf": shelf,
        "foresight_unconfirmed": unconfirmed,
        "foresight_as_of": (foresight or {}).get("asof") if isinstance(foresight, dict) else None,
    }
