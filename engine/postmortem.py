"""Deterministic root-cause forensics for US Buy-Board episodes (Prophet Learning Loop §2).

WHAT THIS MODULE IS
-------------------
A pure classifier + aggregator. Given (a) an episode's outcome, (b) the board's OWN
state at the entry date, (c) the price path over the holding window, and (d) the
ticker's prior episode, it emits a multi-label failure taxonomy where every label
carries the trigger values that fired it. `scripts/prophet_postmortem.py` owns all the
I/O (parquet, jsonl, git archaeology, closes caches, artifact write); this file owns the
rules, so the rules are testable on synthetic rows with no fixtures.

FOUR THINGS THIS MODULE DELIBERATELY DOES NOT DO
------------------------------------------------
1. **No LLM anywhere** (constitution A7 — LLMs never originate signals). Every label is
   a feature-threshold rule with its threshold as a module constant and its trigger
   values written onto the row. A reader can re-derive any label by hand.
2. **No authority.** Nothing here ranks, sizes, gates or vetoes. A cohort that looks
   damning (say: every loser was bought under an `avoid` theme) is a CANDIDATE for a
   pre-registered study, not a live rule. That is why `veto_cost` below is symmetric —
   see WINNERS ARE FIRST-CLASS.
3. **No re-definition of the track record.** The scoring core is
   `engine.track_scoring` used unchanged: next-bar-close fill, forced verdict at
   `horizon`, symmetric maturity gate. This study runs the PURE fixed-horizon leg (no
   stop, no oscillator target) so the postmortem measures the SIGNAL, while the public
   ledger keeps its own exit rule. The two therefore differ by exactly the exit rule's
   effect (e.g. IPGP 2026-07-15: -17.9% fixed-horizon here vs -18.7% in the ledger,
   which stopped out on day 8). Neither is wrong; they answer different questions.
4. **No pooling of matured and in-flight rows into a rate.** An in-flight row is marked
   to the latest close, and a mark is outcome-conditioned in the exact way
   track_scoring rule 2 exists to prevent: today's biggest losers are over-represented
   among names that have not yet resolved. In-flight episodes are CLASSIFIED (that is
   the forensic value — four of the operator's eleven worst names are still open) and
   are then held in a separate, labelled block that enters NO rate and NO expectancy.
   `aggregate()` enforces this structurally: every rate is computed over
   `maturity == "matured"` only.

WINNERS ARE FIRST-CLASS (the symmetric cost column)
---------------------------------------------------
The failure taxonomy is only half an answer. "Every loser had a sector headwind at
entry" is worthless on its own, because the winners may have had one too — a headwind
veto that removes six losers and eight winners is a losing trade. So the same labels
are computed for winners (>= +8%), and `veto_cost` reports, for every costable claim
(one row per label-and-leg, `VETO_COST_SPECS`), BOTH sides of the counterfactual: losses
avoided AND winners forfeited, with the net. The winners-forfeited column is a column,
never a footnote.

SYSTEMIC VS ANOMALOUS
---------------------
A label that fires on nine episodes across one board night is one bad night; the same
label across seven nights is a process fault. `aggregate()` therefore counts label share
over DISTINCT ENTRY DATES as well as over rows, and prints the largest single-date
share, because episodes surfaced on the same night are one bet (track_scoring rule 3).

THE LABELS (§2 of research/PROPHET_LEARNING_LOOP_MASTERPLAN_BY_FABLE.md)
------------------------------------------------------------------------
  sector_headwind   theme/sector basket reco in {avoid, trim} at entry, or the board's
                    own spotlight read was `out_of_play` / stage `lagging`.
                    VISIBLE AT ENTRY. `weakening` (the RRG leading-but-rolling
                    quadrant) is recorded in the context and deliberately does NOT
                    fire — it is not yet a headwind, and folding it in would push the
                    label's base rate past half the board and make it uninformative.
  bought_extended   extension evidence at entry: the alignment read said overextended /
                    "Extended — wait", the entry-status was `extended`, the conviction
                    risk carried an `ext` component, or the fill price sat above the
                    board's own `chase_above` level. VISIBLE AT ENTRY.
  thesis_break      the setup itself failed: a later board night stamped
                    `hold.state == "broken"`, else a close crossed below the entry
                    row's published stop. NOT visible at entry.
  gap_event         a single-session close-to-close move <= -8% against the position.
                    Earnings/news class. NOT visible at entry. Close-to-close is the
                    honest available measure — the caches carry no opens, so a true
                    overnight gap is UNDER-counted, never over-counted.
  market_beta       the tape, not the pick: |excess| < 40% of |absolute| loss.
                    NOT visible at entry.
  re_admission      the same ticker was re-admitted <= 10 sessions after a prior
                    episode, on either of two legs that are NOT the same claim:
                      * `open_drawdown_at_readmit` — the prior position was ALREADY
                        >= 8% under water on the night of the re-admission. BUILDABLE.
                      * `prior_episode_loss` — the prior episode RESOLVED to a >= 8%
                        loss. HINDSIGHT (the operator's IPGP case was +3.04% GREEN on
                        the night the board bought it back).
                    NOT visible at entry as a label — see BUILDABLE VS HINDSIGHT.
  idiosyncratic     none of the above fired. Not a residual bucket to be proud of —
                    a large idiosyncratic share means the taxonomy is not yet
                    explaining the losses.

BUILDABLE VS HINDSIGHT (why `re_admission` is not a visible-at-entry label)
---------------------------------------------------------------------------
`VISIBLE_AT_ENTRY_LABELS` is a promise: every label in it could have been read off the
board's own state on the night of the pick, so costing a veto out of it answers a
question somebody could act on. `re_admission` fails that promise. Its headline
counterfactual (+79.08pp avoided over 7 flagged episodes, 2026-07-31 artifact) is
carried ENTIRELY by the `prior_episode_loss` leg, which needs the prior episode's
RESOLVED outcome — a number that does not exist on the night the board re-admits the
name. Leaving the label in the visible-at-entry list published a hindsight figure under
a buildable badge, which is the exact error the promotion gauntlet exists to prevent.
So:

  * the label sits OUTSIDE `VISIBLE_AT_ENTRY_LABELS`;
  * `veto_cost` carries ONE ROW PER LEG (`VETO_COST_SPECS`), each stamped
    `variant: buildable | hindsight_upper_bound`;
  * the buildable row is PRINTED EVEN WHEN IT FIRES ZERO TIMES. On today's data it
    fires zero times, and that zero is the finding — suppressing an empty row would
    leave only the hindsight number on the page, which is how a hindsight number gets
    read as a rule.

The per-ROW `visible_at_entry` flag stays leg-specific: an episode that fired on the
open-drawdown leg really was visible at entry and says so on the row. The label-level
list is the weaker, safer claim, and it is the one the aggregations, the report and the
admin panel read.

NULLS ARE PRINTED, NEVER DROPPED
--------------------------------
A ticker with no close path cannot be asked about gaps or stop crosses. Those labels
come back as an explicit null entry in `labels_null` with a reason, the episode still
appears in the artifact, and `aggregate()` reports the null counts per label so a
reader can see the denominator each label was actually evaluated on. The same holds one
level down for `re_admission`: a prior episode that could not be priced, or an
in-window prior with no mark, nulls the LEG it starves (`re_admission:<leg>`) so each
veto variant is costed only over the rows its own input reached.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

# --------------------------------------------------------------------------- #
# thresholds — every one of these is a knob a reader may re-derive a label from
# --------------------------------------------------------------------------- #

#: An episode is a LOSER at <= -8% absolute or <= -5% benchmark-excess. Two legs
#: because a -9% name in a -8% tape is a different failure from a -9% name in a flat
#: tape, and the taxonomy needs both in the cohort so `market_beta` has something to
#: separate.
LOSER_ABS_PCT = -8.0
LOSER_EXCESS_PCT = -5.0

#: An episode is a WINNER at >= +8% absolute — the mirror of the absolute loser gate,
#: so the two tails are cut at the same distance from zero.
WINNER_ABS_PCT = 8.0

#: Basket recommendations that count as a headwind at entry.
HEADWIND_RECOS = ("avoid", "trim")
#: Spotlight sector RRG stages that count as a headwind. `weakening` is excluded on
#: purpose (see module docstring).
HEADWIND_STAGES = ("lagging",)
#: Spotlight direction values that count as a headwind.
HEADWIND_DIRS = ("out_of_play",)

#: Conviction risk `ext` component at or above this counts as extension evidence.
EXT_RISK_MIN = 0.10

#: A single-session close-to-close move at or below this is a gap event.
GAP_PCT = -8.0

#: `market_beta` fires when the excess loss is smaller than this share of the absolute
#: loss — i.e. most of the damage was the tape.
BETA_SHARE_MAX = 0.40

#: Re-admission window, in sessions, and the loss that makes a re-admission notable.
READMIT_MAX_SESSIONS = 10
READMIT_LOSS_PCT = -8.0

#: The two `re_admission` legs, named once so the classifier, the veto specs, the null
#: keys and the tests all spell them the same way.
READMIT_LEG_OPEN_DRAWDOWN = "open_drawdown_at_readmit"   # buildable at entry
READMIT_LEG_PRIOR_LOSS = "prior_episode_loss"            # hindsight only

#: Leg-scoped null keys. `evaluated()` keys off the string in `labels_null[].label`, so
#: a leg that had no input leaves ITS universe without dragging the other leg out too.
READMIT_NULL_OPEN_DRAWDOWN = f"re_admission:{READMIT_LEG_OPEN_DRAWDOWN}"
READMIT_NULL_PRIOR_LOSS = f"re_admission:{READMIT_LEG_PRIOR_LOSS}"

#: The taxonomy, in the order aggregations print it. `idiosyncratic` sorts last on
#: purpose: it is the residual, and a reader should read it after the explanations.
TAXONOMY = (
    "sector_headwind",
    "bought_extended",
    "thesis_break",
    "gap_event",
    "market_beta",
    "re_admission",
    "idiosyncratic",
)

#: Bilingual plain-word copy for every label. Any surface that shows a label shows
#: these, never the raw slug (glance-tier law: no untranslated stats, no raw slugs).
TAXONOMY_COPY: dict[str, dict[str, str]] = {
    "sector_headwind": {
        "en": "Bought into a sector the desk was avoiding",
        "zh": "买在本已建议回避的板块",
    },
    "bought_extended": {
        "en": "Bought after the move had already run",
        "zh": "涨势已走完才买入",
    },
    "thesis_break": {
        "en": "The setup itself broke",
        "zh": "形态本身被破坏",
    },
    "gap_event": {
        "en": "A one-day drop of 8% or more",
        "zh": "单日下跌 8% 以上",
    },
    "market_beta": {
        "en": "The whole tape fell, not this pick",
        "zh": "整体行情下跌，非个股问题",
    },
    "re_admission": {
        "en": "Re-bought a name that had just lost money",
        "zh": "刚亏损的股票被再次买入",
    },
    "idiosyncratic": {
        "en": "No pattern found yet",
        "zh": "暂未发现规律",
    },
}

#: Labels the engine could in principle have acted on at entry, WHOLE — every episode
#: they fire on had the trigger readable on the night of the pick.
#:
#: `re_admission` is deliberately NOT here (see BUILDABLE VS HINDSIGHT in the module
#: docstring). It fires on two legs with opposite epistemic status, and on today's data
#: 100% of its fires are the hindsight leg, so a single "visible at entry: yes" badge on
#: the label would put a hindsight counterfactual in front of a reader as a buildable
#: one. It is costed instead through `VETO_COST_SPECS`, one row per leg.
VISIBLE_AT_ENTRY_LABELS = ("sector_headwind", "bought_extended")

#: What each veto row is worth as evidence. `buildable` = the trigger exists on the
#: night of the pick, so the row is a candidate a pre-registration could be written
#: against. `hindsight_upper_bound` = the trigger needs a number that did not exist yet;
#: read the row as a CEILING on what the pattern could be worth if a buildable proxy is
#: ever found, never as the value of a rule.
VETO_VARIANT_COPY: dict[str, dict[str, str]] = {
    "buildable": {
        "en": ("Buildable — the trigger was readable on the night of the pick, so this "
               "counterfactual is about a rule someone could pre-register."),
        "zh": ("可落地 —— 触发条件在选股当晚即可读到，因此该反事实对应的是一条可以先行"
               "预注册再检验的规则。"),
    },
    "hindsight_upper_bound": {
        "en": ("Hindsight upper bound — the trigger needs a number that did not exist "
               "yet at entry. It is a ceiling on what the pattern could be worth if a "
               "buildable trigger is ever found, NOT the value of a rule."),
        "zh": ("事后上限 —— 触发条件依赖入场当时尚不存在的数字。它只是「若日后找到可落地"
               "触发条件，该规律最多值多少」的上限，并非某条规则的实际价值。"),
    },
}

#: Per-leg plain-word copy, for rows whose label is split by leg.
VETO_LEG_COPY: dict[str, dict[str, str]] = {
    READMIT_LEG_OPEN_DRAWDOWN: {
        "en": "Re-bought while the earlier position was already 8% under water",
        "zh": "前一笔仍浮亏 8% 以上时又被买入",
    },
    READMIT_LEG_PRIOR_LOSS: {
        "en": "Re-bought a name whose earlier position ended up losing 8% or more",
        "zh": "前一笔最终亏损 8% 以上的股票被再次买入",
    },
}

#: One veto row per COSTABLE claim, in print order. A row is (label, leg) rather than
#: just a label because `re_admission` is two different claims sharing one name, and
#: costing them on one line publishes the hindsight number under a buildable badge.
#: A spec with `leg=None` costs the whole label.
VETO_COST_SPECS: tuple[dict[str, Any], ...] = (
    {"label": "sector_headwind", "leg": None, "variant": "buildable"},
    {"label": "bought_extended", "leg": None, "variant": "buildable"},
    {"label": "re_admission", "leg": READMIT_LEG_OPEN_DRAWDOWN, "variant": "buildable"},
    {"label": "re_admission", "leg": READMIT_LEG_PRIOR_LOSS,
     "variant": "hindsight_upper_bound"},
)

#: GICS sector name (both the retro-ledger spelling and the board's spotlight
#: spelling) -> the equal-weight sector basket id in data/baskets/latest.json.
SECTOR_BASKET_ID: dict[str, str] = {
    "Communication Services": "us_sector_comm",
    "Communications": "us_sector_comm",
    "Consumer Discretionary": "us_sector_discretionary",
    "Consumer Staples": "us_sector_staples",
    "Energy": "us_sector_energy",
    "Financials": "us_sector_financials",
    "Health Care": "us_sector_health",
    "Industrials": "us_sector_industrials",
    "Information Technology": "us_sector_tech",
    "Technology": "us_sector_tech",
    "Materials": "us_sector_materials",
    "Real Estate": "us_sector_realestate",
    "Utilities": "us_sector_utilities",
}


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _f(v: Any) -> float | None:
    """Coerce to a finite float, else None. pandas NaN, None and '' all collapse."""
    if v is None or isinstance(v, bool):
        return None
    try:
        out = float(v)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _s(v: Any) -> str | None:
    """Coerce to a non-empty stripped string, else None."""
    if v is None or isinstance(v, bool):
        return None
    try:
        if pd.isna(v):  # type: ignore[arg-type]
            return None
    except (TypeError, ValueError):
        pass
    out = str(v).strip()
    return out or None


def _dig(obj: Any, *path: str) -> Any:
    """Walk nested mappings, returning None the moment the path leaves a mapping."""
    cur = obj
    for key in path:
        if not isinstance(cur, Mapping):
            return None
        cur = cur.get(key)
    return cur


# --------------------------------------------------------------------------- #
# entry-time context
# --------------------------------------------------------------------------- #
def entry_context(
    snap_row: Mapping[str, Any] | None,
    retro_row: Mapping[str, Any] | None,
    themes_at_entry: Mapping[str, Mapping[str, Any]] | None,
    theme_ids: Sequence[str] | None,
    basket_asof: str | None,
) -> dict:
    """Assemble everything the board KNEW about a name on the night it surfaced.

    ``snap_row``        the board's own JSON row for (entry_date, ticker), if the
                        snapshot archive covers that date. Richest source.
    ``retro_row``       the retro-grade ledger row for the same key. Covers dates
                        older than the snapshot archive, with fewer fields.
    ``themes_at_entry`` {theme_id: theme dict} reconstructed from the state of
                        data/baskets/latest.json AS OF the entry date (git archaeology).
    ``theme_ids``       basket ids the ticker belonged to (membership.json). Current
                        membership — see the drift caveat the CLI prints.
    ``basket_asof``     the `as_of` stamped inside the reconstructed baskets blob, so
                        every theme reading in the row is auditable back to one commit.

    Every field is nullable. A null here is a real "the board did not record this",
    never a zero.
    """
    themes_at_entry = themes_at_entry or {}
    conv = _dig(snap_row, "conviction") or {}
    spot = _dig(conv, "spotlight") or {}
    align = _dig(conv, "alignment") or {}
    risk = _dig(conv, "risk") or {}
    esig = _dig(snap_row, "entry_signal") or {}
    hold = _dig(snap_row, "hold") or {}

    sector = (
        _s(_dig(spot, "sector", "name"))
        or _s(_dig(snap_row, "sector"))
        or _s(_dig(retro_row, "sector"))
    )

    # --- theme leg: the name's OWN baskets, state read at the entry date -----------
    own: list[dict] = []
    for tid in sorted({str(t) for t in (theme_ids or []) if t}):
        th = themes_at_entry.get(tid)
        if not isinstance(th, Mapping):
            continue
        own.append({
            "id": tid,
            "reco": _s(th.get("reco")),
            "label": _s(th.get("label")),
            "score": _f(th.get("score")),
            "bull_days": _f(th.get("bull_days")),
            "rank": _f(th.get("rank")),
        })
    # The board's own spotlight theme, when it resolved one (PIT-exact mapping).
    spot_theme_id = _s(_dig(spot, "theme", "slug"))

    # --- sector-basket leg: always available once the sector is known --------------
    sector_basket = None
    sb_id = SECTOR_BASKET_ID.get(sector or "")
    if sb_id:
        th = themes_at_entry.get(sb_id)
        sector_basket = {
            "id": sb_id,
            "reco": _s(_dig(th, "reco")),
            "label": _s(_dig(th, "label")),
            "score": _f(_dig(th, "score")),
            "bull_days": _f(_dig(th, "bull_days")),
            "rank": _f(_dig(th, "rank")),
        }

    price = _f(_dig(snap_row, "price")) or _f(esig.get("spot"))
    chase = _f(esig.get("chase_above"))

    return {
        "sector": sector,
        "basket_asof": _s(basket_asof),
        "themes": own,
        "spotlight_theme_id": spot_theme_id,
        "sector_basket": sector_basket,
        "spotlight": {
            "dir": _s(spot.get("dir")),
            "z": _f(spot.get("z")),
            "sector_stage": _s(_dig(spot, "sector", "stage")),
            "sector_extended": _dig(spot, "sector", "extended"),
            "sector_pctile_252d": _f(_dig(spot, "sector", "pctile_252d")),
        },
        "extension": {
            "overextended": _dig(align, "overextended"),
            "entry_tier": _s(align.get("entry_tier")),
            "ext_risk": _f(_dig(risk, "components", "ext")),
            "ext_z": _f(_dig(snap_row, "ext_z")),
            "price": price,
            "chase_above": chase,
            "above_chase": (price is not None and chase is not None and price > chase),
            "off_high_pct": _f(_dig(snap_row, "off_high")) or _f(_dig(retro_row, "off_high")),
        },
        "conviction": {
            "band": _s(conv.get("band")) or _s(_dig(retro_row, "band")),
            "score": _f(conv.get("score")) or _f(_dig(retro_row, "score")),
            "composite_z": _f(conv.get("composite_z")) or _f(_dig(retro_row, "composite_z")),
            "alpha": _f(_dig(snap_row, "alpha")) or _f(_dig(retro_row, "alpha")),
            "tier": _s(_dig(retro_row, "align_tier")) or _s(_dig(snap_row, "align_tier")),
            "tier_cascade": _s(_dig(retro_row, "tier_cascade")),
            "urgency": _s(_dig(snap_row, "urgency")) or _s(_dig(retro_row, "urgency")),
            "state": _s(_dig(snap_row, "state")) or _s(_dig(retro_row, "state")),
        },
        "entry_plan": {
            "status": _s(esig.get("status")) or _s(_dig(retro_row, "entry_status")),
            "stop": _f(esig.get("stop")),
            "atr_pct": _f(esig.get("atr_pct")),
            "invalidation": _f(hold.get("invalidation")),
            "hold_state": _s(hold.get("state")) or _s(_dig(retro_row, "hold_state")),
        },
        "days_since_signal": _f(_dig(snap_row, "signal", "fresh_bars")),
        "board_tenure_days": _f(_dig(retro_row, "board_tenure_days")),
    }


# --------------------------------------------------------------------------- #
# price-path features
# --------------------------------------------------------------------------- #
def path_features(
    close: "pd.Series | None",
    fill_date: Any,
    n_bars: int | None,
    stop_level: float | None,
) -> dict | None:
    """Path facts over the holding window, or None when there is no usable path.

    ``close``      the name's close series (DatetimeIndex ascending), or None.
    ``fill_date``  the bar the position opened on.
    ``n_bars``     how many forward bars the window covers (the episode's `held`, or
                   the bars available for an in-flight row). None -> to the end.
    ``stop_level`` the entry row's published stop, if the board recorded one.

    Returning None (rather than a dict of nulls) is deliberate: the caller must be
    forced to record WHY the path labels are missing instead of silently reading
    "no gap found".
    """
    if close is None or not hasattr(close, "dropna"):
        return None
    s = close.dropna()
    if s.empty:
        return None
    try:
        fill_ts = pd.Timestamp(fill_date)
    except (TypeError, ValueError):
        return None
    i = s.index.searchsorted(fill_ts, side="left")
    if i >= len(s):
        return None
    window = s.iloc[i:] if n_bars is None else s.iloc[i:i + int(n_bars) + 1]
    if len(window) < 2:
        return None

    rets = window.pct_change().dropna() * 100.0
    worst_pct = float(rets.min()) if len(rets) else None
    worst_date = str(rets.idxmin().date()) if len(rets) else None

    stop_cross_date = None
    stop_cross_px = None
    if stop_level is not None and math.isfinite(stop_level) and stop_level > 0:
        below = window.iloc[1:][window.iloc[1:] < stop_level]
        if len(below):
            stop_cross_date = str(below.index[0].date())
            stop_cross_px = float(below.iloc[0])

    return {
        "n_bars": int(len(window) - 1),
        "worst_session_pct": worst_pct,
        "worst_session_date": worst_date,
        "stop_level": stop_level,
        "stop_cross_date": stop_cross_date,
        "stop_cross_px": stop_cross_px,
    }


# --------------------------------------------------------------------------- #
# cohort assignment
# --------------------------------------------------------------------------- #
def cohort_of(outcome_pct: float | None, excess_pct: float | None) -> str:
    """`loser` / `winner` / `neutral` / `unscored`, from the two-leg gates above.

    PRECEDENCE — THE ABSOLUTE RETURN DECIDES FIRST. The masterplan (§2) defines the
    winner gate as ">= +8%", absolute, with no excess leg; only the LOSER gate carries
    one. The excess leg exists to catch a name that LOST while the tape rose — not to
    demote a name that made money into a tape that rose faster.

    Testing the loser legs first made a +9% pick with -5.5% excess come back `loser`,
    which is wrong in both directions at once: it books a profitable pick as a loss, and
    it deletes a real winner from the winners-forfeited column, making every veto in
    `veto_cost` look cheaper than it is. Winner first, then the two loser legs, then
    neutral.
    """
    o = _f(outcome_pct)
    x = _f(excess_pct)
    if o is None and x is None:
        return "unscored"
    if o is not None and o >= WINNER_ABS_PCT:
        return "winner"
    if (o is not None and o <= LOSER_ABS_PCT) or (x is not None and x <= LOSER_EXCESS_PCT):
        return "loser"
    return "neutral"


# --------------------------------------------------------------------------- #
# the classifier
# --------------------------------------------------------------------------- #
def _label(name: str, visible: bool, **trigger: Any) -> dict:
    return {
        "label": name,
        "en": TAXONOMY_COPY[name]["en"],
        "zh": TAXONOMY_COPY[name]["zh"],
        "visible_at_entry": bool(visible),
        "trigger": {k: trigger[k] for k in sorted(trigger)},
    }


def _null_readmit(nulls: list[dict], reason: str) -> None:
    """Null `re_admission` at the label level AND on both legs, with one reason.

    The leg-scoped keys are the denominators `veto_cost` costs each variant over, so a
    row the label could not be decided on has to leave BOTH leg universes as well —
    otherwise the buildable variant's "0 of N" would quietly count rows it never got to
    look at, which is the coverage lie this module exists to refuse.
    """
    for key in ("re_admission", READMIT_NULL_OPEN_DRAWDOWN, READMIT_NULL_PRIOR_LOSS):
        nulls.append({"label": key, "reason": reason})


def classify(
    *,
    outcome_pct: float | None,
    excess_pct: float | None,
    ctx: Mapping[str, Any],
    path: Mapping[str, Any] | None,
    hold_broken: Mapping[str, Any] | None = None,
    prior: Mapping[str, Any] | None = None,
    path_missing_reason: str = "no_price_path",
) -> tuple[list[dict], list[dict]]:
    """Return ``(labels, labels_null)`` for one episode.

    ``hold_broken``  {"date": .., "source": "hold_state_history"} when a later board
                     night stamped this run's hold state `broken`; None otherwise.
    ``prior``        the prior-episode comparison the caller's scan selected:
                     {"entry_date", "outcome_pct", "prior_matured",
                      "sessions_since_prior_exit", "mark_at_readmit_pct",
                      "n_priors_in_window", "selected_by"}.
                     None means the scan found NO prior episode in the window — a
                     DECIDED NEGATIVE that stays in every denominator, not a null.
                     {"undecidable": <reason>} means a prior existed and could not be
                     measured, which nulls the label and both legs.
    ``path_missing_reason``
                     why ``path`` is None, written onto the nulled path labels. The
                     caller must distinguish these: a delisted name with no series at
                     all and a name whose fill bar has not printed yet are BOTH
                     unevaluable, but only the first is a coverage hole. Defaulting
                     everything to "no_price_path" once made the artifact report 67
                     unpriceable episodes when 12 were unpriceable and 55 were simply
                     too young.

    Multi-label by construction. `idiosyncratic` is appended only when nothing else
    fired AND no path label had to be nulled — an episode whose gap/stop legs could not
    be evaluated is NOT "no pattern found", it is "not fully checked", and the null
    list says so.
    """
    labels: list[dict] = []
    nulls: list[dict] = []

    # ── sector_headwind — VISIBLE AT ENTRY ────────────────────────────────────
    # EVIDENCE FIRST, verdict second. The board's theme artifact only grew sector
    # baskets on 2026-06-26, and the snapshot archive only starts 2026-06-30, so a
    # third of the matured sample has NO entry-state to read at all. Emitting "no
    # headwind" for those rows would put them in the clean bucket and quietly halve
    # every headwind rate — a coverage lie of exactly the vacuous-green kind. When no
    # leg has an input, the label is NULLED and `aggregate` drops the row from that
    # label's denominator.
    hw_legs: list[dict] = []
    themes = ctx.get("themes") or []
    sb = ctx.get("sector_basket") or {}
    spot = ctx.get("spotlight") or {}
    hw_evidence = (
        any(th.get("reco") for th in themes)
        or sb.get("reco") is not None
        or spot.get("sector_stage") is not None
        or spot.get("dir") is not None
    )
    for th in themes:
        if (th.get("reco") or "") in HEADWIND_RECOS:
            hw_legs.append({"leg": "theme_reco", "theme_id": th.get("id"),
                            "reco": th.get("reco"), "label": th.get("label")})
    if (sb.get("reco") or "") in HEADWIND_RECOS:
        hw_legs.append({"leg": "sector_basket_reco", "theme_id": sb.get("id"),
                        "reco": sb.get("reco"), "label": sb.get("label")})
    if (spot.get("sector_stage") or "") in HEADWIND_STAGES:
        hw_legs.append({"leg": "sector_stage", "stage": spot.get("sector_stage"),
                        "pctile_252d": spot.get("sector_pctile_252d")})
    if (spot.get("dir") or "") in HEADWIND_DIRS:
        hw_legs.append({"leg": "spotlight_dir", "dir": spot.get("dir"),
                        "z": spot.get("z")})
    if hw_legs:
        labels.append(_label("sector_headwind", True, legs=hw_legs,
                             sector=ctx.get("sector"),
                             basket_asof=ctx.get("basket_asof")))
    elif not hw_evidence:
        nulls.append({"label": "sector_headwind",
                      "reason": "no_theme_state_or_spotlight_at_entry"})

    # ── bought_extended — VISIBLE AT ENTRY ────────────────────────────────────
    ext = ctx.get("extension") or {}
    status = (ctx.get("entry_plan") or {}).get("status") or ""
    ext_risk = _f(ext.get("ext_risk"))
    # Same evidence-first discipline. `above_chase` is a computed bool that is False
    # both when the fill was below the chase level AND when either price was missing,
    # so it can never stand in for evidence — the pair must be present.
    ex_evidence = (
        ext.get("overextended") is not None
        or ext.get("entry_tier") is not None
        or bool(status)
        or ext_risk is not None
        or (ext.get("price") is not None and ext.get("chase_above") is not None)
    )
    ex_legs: list[dict] = []
    if ext.get("overextended") is True:
        ex_legs.append({"leg": "alignment_overextended", "value": True})
    tier = ext.get("entry_tier") or ""
    if tier.lower().startswith("extended"):
        ex_legs.append({"leg": "entry_tier", "value": tier})
    if status == "extended":
        ex_legs.append({"leg": "entry_status", "value": status})
    if ext_risk is not None and ext_risk >= EXT_RISK_MIN:
        ex_legs.append({"leg": "risk_ext_component", "value": ext_risk,
                        "threshold": EXT_RISK_MIN})
    if ext.get("above_chase") is True:
        ex_legs.append({"leg": "above_chase_level", "price": ext.get("price"),
                        "chase_above": ext.get("chase_above")})
    if ex_legs:
        labels.append(_label("bought_extended", True, legs=ex_legs))
    elif not ex_evidence:
        nulls.append({"label": "bought_extended",
                      "reason": "no_entry_state_recorded"})

    # ── thesis_break — path-dependent, NOT visible at entry ───────────────────
    if hold_broken:
        labels.append(_label("thesis_break", False, source="hold_state_history",
                             date=hold_broken.get("date"),
                             board_date=hold_broken.get("board_date")))
    elif path is None:
        nulls.append({"label": "thesis_break", "reason": path_missing_reason})
    elif path.get("stop_cross_date"):
        labels.append(_label("thesis_break", False, source="stop_cross",
                             date=path.get("stop_cross_date"),
                             stop_level=path.get("stop_level"),
                             close=path.get("stop_cross_px")))
    elif path.get("stop_level") is None:
        nulls.append({"label": "thesis_break", "reason": "no_stop_level_recorded"})

    # ── gap_event — path-dependent, NOT visible at entry ──────────────────────
    if path is None:
        nulls.append({"label": "gap_event", "reason": path_missing_reason})
    else:
        worst = _f(path.get("worst_session_pct"))
        if worst is not None and worst <= GAP_PCT:
            labels.append(_label("gap_event", False, pct=round(worst, 2),
                                 date=path.get("worst_session_date"),
                                 threshold=GAP_PCT, basis="close_to_close"))

    # ── market_beta — NOT visible at entry ────────────────────────────────────
    o, x = _f(outcome_pct), _f(excess_pct)
    if o is not None and o < 0:
        if x is None:
            nulls.append({"label": "market_beta", "reason": "no_benchmark_excess"})
        else:
            share = abs(x) / abs(o) if abs(o) > 1e-9 else None
            if share is not None and share < BETA_SHARE_MAX:
                labels.append(_label("market_beta", False,
                                     excess_share_of_loss=round(share, 3),
                                     threshold=BETA_SHARE_MAX,
                                     abs_pct=round(o, 2), excess_pct=round(x, 2)))

    # ── re_admission ──────────────────────────────────────────────────────────
    # Two legs that differ in WHAT THE ENGINE COULD HAVE KNOWN, and the difference is
    # the finding, not a detail: a name re-bought while ALREADY 8% under water is a rule
    # the board could apply tonight; a name re-bought two days before the first position
    # rolled over is visible only in hindsight. Both are recorded, the row's
    # `visible_at_entry` is leg-specific, and `veto_cost` costs them on separate lines.
    #
    # NULL DISCIPLINE. `prior=None` means the caller's scan found NO prior episode inside
    # the window — a DECIDED NEGATIVE, and the row belongs in the denominator. Anything
    # the caller could not resolve arrives as a dict instead:
    #   {"undecidable": <reason>}  the in-window prior could not be priced or scored, so
    #                              this row is nulled on the label AND on both legs. A
    #                              name whose previous run cannot be measured is not
    #                              evidence that it came back clean.
    # An in-window prior missing ONE leg's input (no mark, or no prior outcome) nulls
    # only that leg, so the buildable variant's "0 of N" never counts rows whose
    # open-drawdown input never existed.
    if prior is not None:
        undecidable = _s(prior.get("undecidable"))
        gap = _f(prior.get("sessions_since_prior_exit"))
        prior_out = _f(prior.get("outcome_pct"))
        mark = _f(prior.get("mark_at_readmit_pct"))
        if undecidable:
            _null_readmit(nulls, undecidable)
        elif gap is None:
            _null_readmit(nulls, "prior_gap_not_measurable")
        else:
            in_window = gap <= READMIT_MAX_SESSIONS
            open_loss = mark is not None and mark <= READMIT_LOSS_PCT
            resolved_loss = prior_out is not None and prior_out <= READMIT_LOSS_PCT
            if in_window and mark is None:
                nulls.append({"label": READMIT_NULL_OPEN_DRAWDOWN,
                              "reason": "no_mark_at_readmit"})
            if in_window and prior_out is None:
                nulls.append({"label": READMIT_NULL_PRIOR_LOSS,
                              "reason": "no_prior_episode_outcome"})
            if in_window and mark is None and prior_out is None:
                nulls.append({"label": "re_admission",
                              "reason": "no_mark_and_no_prior_episode_outcome"})
            if in_window and (open_loss or resolved_loss):
                labels.append(_label(
                    "re_admission", open_loss,
                    prior_entry_date=prior.get("entry_date"),
                    prior_outcome_pct=None if prior_out is None else round(prior_out, 2),
                    # None when the caller did not say. A missing maturity flag is a
                    # null, never a False: an UNMATURED prior's "outcome" is a mark, and
                    # a reader comparing legs has to be able to see which is which.
                    prior_matured=prior.get("prior_matured"),
                    mark_at_readmit_pct=None if mark is None else round(mark, 2),
                    sessions_since_prior_exit=None if gap is None else int(gap),
                    leg=(READMIT_LEG_OPEN_DRAWDOWN if open_loss
                         else READMIT_LEG_PRIOR_LOSS),
                    n_priors_in_window=prior.get("n_priors_in_window"),
                    selected_by=prior.get("selected_by"),
                    threshold_pct=READMIT_LOSS_PCT,
                    max_sessions=READMIT_MAX_SESSIONS,
                ))

    # ── idiosyncratic — the residual ──────────────────────────────────────────
    # Fires whenever nothing else did. It deliberately does NOT suppress itself when a
    # leg had to be nulled: an episode with no label at all reads as a classifier bug,
    # and hiding the residual would hide exactly the rows the taxonomy fails to explain.
    # Instead the trigger names which legs were actually checked and which were not, and
    # `aggregate` splits the residual into fully-checked and partially-checked counts so
    # "no pattern found" is never confused with "not looked at".
    if not labels:
        # Intersected with the taxonomy on purpose: `labels_null` also carries
        # LEG-scoped keys (`re_admission:<leg>`), which are denominator bookkeeping for
        # one variant of one label, not a taxonomy leg a reader can be told went
        # unchecked. The label-level key is appended alongside them whenever the whole
        # label is undecidable, so nothing is lost by filtering here.
        unchecked = sorted({str(n.get("label")) for n in nulls} & set(TAXONOMY))
        labels.append(_label(
            "idiosyncratic", False,
            checked=[t for t in TAXONOMY[:-1] if t not in unchecked],
            unchecked=unchecked,
            fully_checked=not unchecked,
        ))

    labels.sort(key=lambda d: TAXONOMY.index(d["label"]))
    nulls.sort(key=lambda d: (d["label"], d["reason"]))
    return labels, nulls


# --------------------------------------------------------------------------- #
# aggregation
# --------------------------------------------------------------------------- #
def _rate(num: int, den: int) -> float | None:
    return round(100.0 * num / den, 1) if den else None


def _labels_of(row: Mapping[str, Any]) -> set[str]:
    return {str(lb.get("label")) for lb in (row.get("labels") or [])}


def _fired(row: Mapping[str, Any], label: str, leg: str | None) -> bool:
    """Did ``label`` fire on this row — and, when ``leg`` is given, on THAT leg?

    Leg filtering reads the label's own recorded trigger, so a veto variant is costed
    over exactly the episodes whose trigger it names. A row carrying the label with no
    recorded leg matches only the whole-label spec (``leg=None``); it is never credited
    to a specific leg on a guess.
    """
    for lb in (row.get("labels") or []):
        if str(lb.get("label")) != label:
            continue
        if leg is None or str((lb.get("trigger") or {}).get("leg")) == leg:
            return True
    return False


def _loss(rows: Iterable[Mapping[str, Any]]) -> float:
    """Summed ABSOLUTE loss over rows, in percentage points."""
    return sum(abs(_f(r.get("outcome_pct")) or 0.0) for r in rows)


def _nulled(row: Mapping[str, Any]) -> set[str]:
    return {str(nl.get("label")) for nl in (row.get("labels_null") or [])}


def evaluated(rows: Sequence[Mapping[str, Any]], label: str) -> list[Mapping[str, Any]]:
    """Rows on which ``label`` could actually be decided.

    ``label`` is any key that appears in a row's ``labels_null`` — a taxonomy label, or
    a LEG key like ``re_admission:open_drawdown_at_readmit`` when one leg of a label had
    an input the other did not.

    The single most important filter in this module. A row whose entry state was never
    recorded is NOT evidence that the label did not apply, and letting it sit in the
    unflagged bucket would deflate every rate and every counterfactual by the size of
    the uncovered history (here: a third of the matured sample predates the snapshot
    archive). Nulls are printed, then excluded from their own denominator — never
    silently counted as negatives.
    """
    return [r for r in rows if label not in _nulled(r)]


def aggregate(rows: Sequence[Mapping[str, Any]]) -> dict:
    """Roll episode rows up into the summary artifact.

    EVERY rate below is computed over ``maturity == "matured"`` rows only. In-flight
    rows are counted, listed and classified, and are reported in their own block
    (`in_flight`) that carries no rate — see rule 4 in the module docstring.
    """
    rows = list(rows)
    matured = sorted([r for r in rows if r.get("maturity") == "matured"],
                     key=lambda r: (str(r.get("entry_date")), str(r.get("ticker"))))
    inflight = sorted([r for r in rows if r.get("maturity") == "in_flight"],
                      key=lambda r: (str(r.get("entry_date")), str(r.get("ticker"))))

    losers = [r for r in matured if r.get("cohort") == "loser"]
    winners = [r for r in matured if r.get("cohort") == "winner"]
    loss_total = _loss(losers)

    # ── label frequencies, both tails, on the denominator each label EARNED ───
    # Shares are over rows where the label could be decided (see `evaluated`), and the
    # raw counts sit beside them so the two are never confused.
    #
    # `loss_contribution_pct` is the ONE column that does not move with the label: its
    # denominator is ALWAYS the whole matured-loser book, so the column is comparable
    # down the table and across runs. Mixing it with the per-label decidable denominator
    # made a label evaluable on 34 of 109 losers look like it carried a share of a
    # 34-loser book while the row beside it was sharing a 109-loser one — two different
    # 100%s in the same column. The per-label reach is disclosed SEPARATELY, as coverage:
    # `loser_coverage_pct` (share of losers the label could be decided on) and
    # `decidable_loss_share_pct` (share of the loser BOOK those rows carry). Read
    # contribution against coverage: 18.8% of the book carried by a label that could only
    # be decided on 31% of it is a very different sentence from 18.8% out of full reach.
    label_freq: list[dict] = []
    for name in TAXONOMY:
        l_eval = evaluated(losers, name)
        w_eval = evaluated(winners, name)
        l_rows = [r for r in l_eval if name in _labels_of(r)]
        w_rows = [r for r in w_eval if name in _labels_of(r)]
        n_null = len(matured) - len(evaluated(matured, name))
        label_freq.append({
            "label": name,
            "en": TAXONOMY_COPY[name]["en"],
            "zh": TAXONOMY_COPY[name]["zh"],
            "visible_at_entry": name in VISIBLE_AT_ENTRY_LABELS,
            "n_losers": len(l_rows),
            "n_losers_evaluated": len(l_eval),
            "n_losers_total": len(losers),
            "loser_share_pct": _rate(len(l_rows), len(l_eval)),
            "n_winners": len(w_rows),
            "n_winners_evaluated": len(w_eval),
            "n_winners_total": len(winners),
            "winner_share_pct": _rate(len(w_rows), len(w_eval)),
            "loss_contribution_pct": (
                round(100.0 * _loss(l_rows) / loss_total, 1) if loss_total else None),
            "loss_contribution_basis": "all matured losers' summed absolute loss",
            "loss_contribution_denominator_pp": round(loss_total, 2),
            "loser_coverage_pct": _rate(len(l_eval), len(losers)),
            "decidable_loss_share_pct": (
                round(100.0 * _loss(l_eval) / loss_total, 1) if loss_total else None),
            "n_matured_with_label": len([r for r in matured if name in _labels_of(r)]),
            "n_evaluated": len(matured) - n_null,
            "n_null_disclosed": n_null,
        })

    # ── systemic vs anomalous: distinct DATES, not just rows ──────────────────
    loser_dates = sorted({str(r.get("entry_date")) for r in losers})
    systemic: list[dict] = []
    for name in TAXONOMY:
        l_rows = [r for r in losers if name in _labels_of(r)]
        dates = sorted({str(r.get("entry_date")) for r in l_rows})
        by_date = {d: len([r for r in l_rows if str(r.get("entry_date")) == d]) for d in dates}
        top_date = max(by_date, key=lambda d: (by_date[d], d)) if by_date else None
        systemic.append({
            "label": name,
            "n_dates": len(dates),
            "date_share_pct": _rate(len(dates), len(loser_dates)),
            "n_loser_dates_total": len(loser_dates),
            "max_single_date_share_pct": (
                _rate(by_date[top_date], len(l_rows)) if top_date else None
            ),
            "max_single_date": top_date,
            "read": (
                "unfired" if not dates
                else "anomalous" if len(dates) <= 2
                else "systemic" if (len(loser_dates) and len(dates) / len(loser_dates) >= 0.5)
                else "recurring"
            ),
        })

    # ── the SYMMETRIC counterfactual: what each would-be veto costs ───────────
    # Both sides of the ledger for every costable claim. `n_winners_forfeited` and
    # `winners_forfeited_pct` are the operator's "don't weed out real winners"
    # requirement expressed as first-class columns.
    #
    # ONE ROW PER (label, leg), not per label — `VETO_COST_SPECS`. `re_admission` is two
    # claims with opposite epistemic status, and a single line for it printed a hindsight
    # number (+79.08pp on the 2026-07-31 artifact, carried entirely by the resolved-loss
    # leg) under a visible-at-entry badge. Every row now says which it is, and a
    # buildable row that fires ZERO times is still printed — the zero is the finding.
    veto_cost: list[dict] = []
    for spec in VETO_COST_SPECS:
        name, leg, variant = spec["label"], spec["leg"], spec["variant"]
        key = name if leg is None else f"{name}:{leg}"
        universe = evaluated(matured, key)       # the veto's real reach, leg-aware
        flagged = [r for r in universe if _fired(r, name, leg)]
        f_losers = [r for r in flagged if r.get("cohort") == "loser"]
        f_winners = [r for r in flagged if r.get("cohort") == "winner"]
        loss_avoided = _loss(f_losers)
        wins_forfeited = sum(_f(r.get("outcome_pct")) or 0.0 for r in f_winners)
        pnl_flagged = [_f(r.get("outcome_pct")) for r in flagged]
        pnl_flagged = [v for v in pnl_flagged if v is not None]
        copy = VETO_LEG_COPY.get(leg or "") or TAXONOMY_COPY[name]
        veto_cost.append({
            "key": key,
            "label": name,
            "leg": leg,
            "variant": variant,
            # A row-level restatement of the label-level promise. `buildable` here means
            # the trigger existed at entry; it is NOT read off VISIBLE_AT_ENTRY_LABELS,
            # because a label can be excluded there precisely BECAUSE one of its legs is
            # hindsight while the other is not.
            "visible_at_entry": variant == "buildable",
            "en": copy["en"],
            "zh": copy["zh"],
            "variant_en": VETO_VARIANT_COPY[variant]["en"],
            "variant_zh": VETO_VARIANT_COPY[variant]["zh"],
            "basis": (
                "matured episodes on which this label could be decided" if leg is None
                else f"matured episodes on which the `{leg}` leg could be decided"
            ),
            "n_universe": len(universe),
            "n_matured_total": len(matured),
            "n_null_disclosed": len(matured) - len(universe),
            "n_flagged": len(flagged),
            "flagged_share_of_universe_pct": _rate(len(flagged), len(universe)),
            "n_losers_avoided": len(f_losers),
            "loss_avoided_pct": round(loss_avoided, 2),
            "n_winners_forfeited": len(f_winners),
            "winners_forfeited_pct": round(wins_forfeited, 2),
            "net_pct_if_vetoed": round(loss_avoided - wins_forfeited, 2),
            "mean_outcome_of_flagged_pct": (
                round(sum(pnl_flagged) / len(pnl_flagged), 2) if pnl_flagged else None
            ),
            "mean_outcome_of_unflagged_pct": _mean_outcome(
                [r for r in universe if not _fired(r, name, leg)]
            ),
            "n_dates_flagged": len({str(r.get("entry_date")) for r in flagged}),
        })

    # ── headwind-at-entry vs tailwind-at-entry ───────────────────────────────
    # Restricted to rows where the label was decidable, so an uncovered row can never
    # land in the "no headwind" bucket and flatter it.
    def _split(pred, label: str) -> dict:
        sel = [r for r in evaluated(matured, label) if pred(r)]
        outs = [_f(r.get("outcome_pct")) for r in sel]
        outs = [v for v in outs if v is not None]
        return {
            "n": len(sel),
            "n_losers": len([r for r in sel if r.get("cohort") == "loser"]),
            "loss_rate_pct": _rate(len([r for r in sel if r.get("cohort") == "loser"]), len(sel)),
            "n_winners": len([r for r in sel if r.get("cohort") == "winner"]),
            "win_rate_pct": _rate(len([r for r in sel if r.get("cohort") == "winner"]), len(sel)),
            "mean_outcome_pct": round(sum(outs) / len(outs), 2) if outs else None,
            "n_dates": len({str(r.get("entry_date")) for r in sel}),
        }

    cohort_splits = {
        "headwind_at_entry": _split(
            lambda r: "sector_headwind" in _labels_of(r), "sector_headwind"),
        "no_headwind_at_entry": _split(
            lambda r: "sector_headwind" not in _labels_of(r), "sector_headwind"),
        "extended_at_entry": _split(
            lambda r: "bought_extended" in _labels_of(r), "bought_extended"),
        "not_extended_at_entry": _split(
            lambda r: "bought_extended" not in _labels_of(r), "bought_extended"),
    }

    # ── repeat offenders ──────────────────────────────────────────────────────
    by_ticker: dict[str, list[Mapping[str, Any]]] = {}
    for r in losers:
        by_ticker.setdefault(str(r.get("ticker")), []).append(r)
    repeat = sorted(
        (
            {
                "ticker": tk,
                "n_loser_episodes": len(eps),
                "entry_dates": sorted(str(e.get("entry_date")) for e in eps),
                "total_loss_pct": round(
                    sum(abs(_f(e.get("outcome_pct")) or 0.0) for e in eps), 2),
                "labels": sorted({lb for e in eps for lb in _labels_of(e)}),
            }
            for tk, eps in by_ticker.items() if len(eps) > 1
        ),
        key=lambda d: (-d["total_loss_pct"], d["ticker"]),
    )

    # ── diagnostics: why a label did or did not fire ──────────────────────────
    # A label that never fires is a claim about the world, and a reader is entitled to
    # see the quantity it was thresholded on rather than a bare zero. `market_beta` in
    # particular reads as "the tape was never the cause" — that is only credible with
    # the excess-share distribution printed beside it.
    shares = sorted(
        abs(_f(r.get("excess_pct")) or 0.0) / abs(_f(r.get("outcome_pct")) or 1.0)
        for r in losers
        if _f(r.get("excess_pct")) is not None and _f(r.get("outcome_pct"))
    )
    idio = [r for r in matured if "idiosyncratic" in _labels_of(r)]
    idio_full = [
        r for r in idio
        if any(lb.get("label") == "idiosyncratic"
               and (lb.get("trigger") or {}).get("fully_checked") is True
               for lb in (r.get("labels") or []))
    ]
    diagnostics = {
        "market_beta_excess_share": {
            "n": len(shares),
            "threshold": BETA_SHARE_MAX,
            "min": round(shares[0], 3) if shares else None,
            "p10": round(shares[len(shares) // 10], 3) if shares else None,
            "median": round(shares[len(shares) // 2], 3) if shares else None,
            "max": round(shares[-1], 3) if shares else None,
            "note_en": ("|benchmark-excess| as a share of |absolute| loss, over matured "
                        "losers. The label fires below the threshold; a distribution "
                        "sitting entirely above it means the losses were the picks, not "
                        "the tape."),
            "note_zh": ("成熟亏损样本中「超额亏损」占「绝对亏损」的比例。低于阈值才触发该标签；"
                        "若分布整体高于阈值，说明亏损来自选股本身而非大盘。"),
        },
        "idiosyncratic_split": {
            "n_total": len(idio),
            "n_fully_checked": len(idio_full),
            "n_with_unchecked_legs": len(idio) - len(idio_full),
            "note_en": ("`idiosyncratic` fires when nothing else did. Rows with unchecked "
                        "legs are NOT 'no pattern found' — they are 'not fully looked at', "
                        "and the row's own labels_null names which leg."),
            "note_zh": ("当其他标签均未触发时才标记为「暂未发现规律」。若该行仍有未能判定的检查项，"
                        "其含义是「尚未查全」而非「确无规律」，具体缺哪一项见该行的 labels_null。"),
        },
    }

    return {
        "n_episodes": len(rows),
        "n_matured": len(matured),
        "n_in_flight": len(inflight),
        "n_unscored": len([r for r in rows if r.get("maturity") == "unscored"]),
        "n_board_dates": len({str(r.get("entry_date")) for r in matured}),
        "cohorts": {
            "n_losers": len(losers),
            "n_winners": len(winners),
            "n_neutral": len([r for r in matured if r.get("cohort") == "neutral"]),
            "loser_gate": {"abs_pct": LOSER_ABS_PCT, "excess_pct": LOSER_EXCESS_PCT},
            "winner_gate": {"abs_pct": WINNER_ABS_PCT},
            "total_loser_loss_pct": round(loss_total, 2),
        },
        "label_frequency": label_freq,
        "systemic_vs_anomalous": systemic,
        "veto_cost": veto_cost,
        "cohort_splits": cohort_splits,
        "repeat_offenders": repeat,
        "diagnostics": diagnostics,
        "in_flight": {
            "n": len(inflight),
            "note_en": ("Marked to the latest close and classified for forensics only. "
                        "These rows enter no rate and no expectancy — an unresolved "
                        "position's mark is outcome-conditioned."),
            "note_zh": ("按最新收盘价标记，仅用于复盘分类。此类记录不计入任何胜率或期望值 —— "
                        "未了结持仓的浮动盈亏会受结果选择影响。"),
            # The four marks add to `n`, so a reader can check that the two tails the
            # report prints are the whole in-flight block and not a chosen slice.
            "n_losers_marked": len([r for r in inflight if r.get("cohort") == "loser"]),
            "n_winners_marked": len([r for r in inflight if r.get("cohort") == "winner"]),
            "n_neutral_marked": len([r for r in inflight if r.get("cohort") == "neutral"]),
            "n_unscored_marked": len([r for r in inflight if r.get("cohort") == "unscored"]),
            "label_frequency": [
                {
                    "label": name,
                    "n": len([r for r in inflight if name in _labels_of(r)]),
                }
                for name in TAXONOMY
            ],
        },
        "taxonomy": [
            {"label": name, "en": TAXONOMY_COPY[name]["en"],
             "zh": TAXONOMY_COPY[name]["zh"],
             "visible_at_entry": name in VISIBLE_AT_ENTRY_LABELS,
             # Only `re_admission` needs this today: the label is not visible at entry,
             # but one of its two legs is, and a reader who sees a bare "no" is owed the
             # reason rather than left to infer that the pattern is unusable.
             "legs": [
                 {"leg": s["leg"], "variant": s["variant"],
                  "visible_at_entry": s["variant"] == "buildable",
                  "en": VETO_LEG_COPY[s["leg"]]["en"],
                  "zh": VETO_LEG_COPY[s["leg"]]["zh"]}
                 for s in VETO_COST_SPECS
                 if s["label"] == name and s["leg"] is not None
             ] or None}
            for name in TAXONOMY
        ],
        "thresholds": {
            "loser_abs_pct": LOSER_ABS_PCT,
            "loser_excess_pct": LOSER_EXCESS_PCT,
            "winner_abs_pct": WINNER_ABS_PCT,
            "headwind_recos": list(HEADWIND_RECOS),
            "headwind_stages": list(HEADWIND_STAGES),
            "headwind_dirs": list(HEADWIND_DIRS),
            "ext_risk_min": EXT_RISK_MIN,
            "gap_pct": GAP_PCT,
            "beta_share_max": BETA_SHARE_MAX,
            "readmit_max_sessions": READMIT_MAX_SESSIONS,
            "readmit_loss_pct": READMIT_LOSS_PCT,
            "readmit_legs": {
                READMIT_LEG_OPEN_DRAWDOWN: "buildable",
                READMIT_LEG_PRIOR_LOSS: "hindsight_upper_bound",
            },
            "visible_at_entry_labels": list(VISIBLE_AT_ENTRY_LABELS),
        },
    }


def _mean_outcome(rows: Iterable[Mapping[str, Any]]) -> float | None:
    vals = [_f(r.get("outcome_pct")) for r in rows]
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None
