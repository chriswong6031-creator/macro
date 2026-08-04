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
1. `research/DO_NOT_REBUILD.md` row 151 (Ignition Radar, suspended 2026-07-23)
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

__all__ = ["build_theme_tape", "STANCES", "QUADRANT_HEAT", "REASON_TEXT"]

# ── tunables ────────────────────────────────────────────────────────────────
TOP_N = 5           # themes shown at most; fewer when fewer clear the floor
QUIET_SAMPLE = 8    # named sample of the quiet remainder (rest becomes "+N")
MAX_AGE_DAYS = 10   # older rotation artifact than this → no panel at all

# A theme must be accelerating AND not decaying to appear. This is the floor that
# makes the tape self-empty on a dead tape (fence 1); it is not a ranker.
CONSTRUCTIVE_QUADRANTS = ("leading", "improving")

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
) -> dict[str, Any] | None:
    """Join the hottest themes against the board. None → render nothing.

    Returns None (and the panel disappears) when the rotation artifact is
    missing, unreadable, stale beyond MAX_AGE_DAYS, or when no theme clears the
    constructive floor. That last case is the honest-null the Ignition Radar
    ruling requires: a dead tape prints no tape.
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

        heat_en, heat_zh = QUADRANT_HEAT.get(quadrant, (None, None))
        relative = theme.get("rs") if isinstance(theme.get("rs"), dict) else {}
        stance = _stance_for(counts)
        say_en, say_zh = STANCES[stance]
        rows.append(
            {
                "name": name,
                "name_zh": theme.get("theme_zh") or name,
                "rank": position,
                "quadrant": quadrant,
                "heat_en": heat_en,
                "heat_zh": heat_zh,
                "n_members": len(members),
                "n_on_board": len(members) - counts["quiet"],
                "counts": counts,
                "members": grouped,
                "shared_why": shared,
                "quiet_sample": quiet[:QUIET_SAMPLE],
                "quiet_more": max(0, len(quiet) - QUIET_SAMPLE),
                # The stance key stays for tests and styling; the resolved pair is
                # carried on the row so the template never indexes a table itself.
                "stance": stance,
                "say_en": say_en,
                "say_zh": say_zh,
                # Tier-2 receipt figures only — never rendered on the glance tier.
                "rs_1w": relative.get("1W"),
                "rs_1m": relative.get("1M"),
                "score": round(float(score), 2),
            }
        )

    if not rows:
        return None

    track = rotation.get("track_record")
    track = track if isinstance(track, dict) else {}
    proven = track.get("proven") if isinstance(track.get("proven"), dict) else {}

    return {
        "as_of": as_of,
        "board_as_of": (standouts or {}).get("as_of") if isinstance(standouts, dict) else None,
        "rank_of": rank_of,
        "rows": rows,
        # Doctrine Law 5 — the null the template must disclose in plain words.
        # True whenever no horizon has cleared the artifact's own significance bar.
        "measuring": not any(bool(v) for v in proven.values()),
        "n_days": track.get("n_days"),
    }
