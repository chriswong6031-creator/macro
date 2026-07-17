"""engine/importance_v0.py — the novelty-first importance challenger (W3, spec D6 / §2.4).

LEAF · CONTEXT-ONLY · DETERMINISTIC · SHADOW-ONLY. Imports only the two qual leaf
primitives (engine.qbus, engine.qkernel); nothing in the mechanical scoring path
imports it, and this module NEVER renders. It is the *challenger* in a
champion-challenger duel against the hand importance formulas: the hand formula's
HIGH/LOW bands were shown to be indistinguishable from the placebo tape at 5d, so
a genuinely-novel scorer has to earn its place by beating both on the same
scoreboard (qledger) rather than by fiat.

`importance_v0(item, asof, df)` returns a deterministic float in [0, 1] built from
five *provisional* priors — this is a v0 prior, NOT a fit (D6: "Document each
weight as a provisional constant … a v0 prior, not a fit"). Learning (logistic /
GBM ≤8 features) begins only once the scoreboard holds ≥500 graded relevance
labels; until then the weights below are frozen hand-set constants and the whole
point of the shadow lane is to grade whether these priors carry any forward
signal at all.

The five features (D6 verbatim, plus the crowding penalty):
  (a) novelty_z   — qbus.novelty_z of the item's PRIMARY entity-or-theme at asof.
                    High novelty (attention unusually elevated for a normally-quiet
                    subject) pushes the score UP. This is the headline feature.
  (b) corroboration — qbus.echo_stats on the item's event_key: cross-DESK breadth
                    (many independent desks carried the SAME event) pushes UP, but
                    it is gated by novelty so that WITHIN-window echo of an OLD
                    story (a big cluster of near-duplicate items with LOW subject
                    novelty) pushes DOWN, not up. Corroboration is novelty ×
                    breadth, never raw item volume (D6: "novelty × corroboration,
                    not volume").
  (c) source_tier — qkernel.TIER_WEIGHT of the item's source_tier. A wire (tier 1)
                    outweighs an aggregator (tier 3); tier 0 (blocked / unlisted)
                    contributes nothing.
  (d) scheduled-surprise — EXCLUDED at v0. See _SURPRISE_EXCLUDED below: the only
                    is_surprise implementation in the tree
                    (china_news_intel.is_surprise) is a DATE-COLLISION test with no
                    topic gate, and qbus rows carry no scheduled_ref column, so the
                    feature is neither valid (per the task's opt-out rule) nor even
                    derivable from the bus. It is left out and its weight is folded
                    into the remaining features (documented, not hidden).
  (e) crowding    — attention-crowding PENALTY (D6: "attention is late and
                    crowded"). The trailing-7d item-volume z on the SAME subject
                    reduces the score: a subject that has already been loud for a
                    week is late, not novel, even if today's bar is high.

All features are PIT — `asof` is passed by the caller (no ambient clock), the
same discipline as qbus / qkernel. Every function returns plain data and NEVER
raises into a caller; a missing feature degrades to a neutral contribution rather
than a crash (the alt-data degraded-mode lesson: absent, not wrong).
"""
from __future__ import annotations

import logging
import math
from datetime import date

from engine import qbus, qkernel

log = logging.getLogger(__name__)

VERSION = "importance_v0.1"

# --------------------------------------------------------------------------- #
# PROVISIONAL WEIGHTS — v0 PRIOR, NOT A FIT (D6).
#
# These are hand-set constants, frozen until the scoreboard holds ≥500 graded
# relevance labels (D6). They are exposed as a module constant so the duel report
# and the tests can assert on them, and so a future learned model reads them as
# its warm-start prior rather than re-deriving them. The four LIVE features
# (novelty, corroboration, source_tier, crowding-penalty) are convex-combined;
# the excluded scheduled-surprise weight is folded proportionally into the rest
# (its nominal 0.10 share is redistributed), so the live weights still sum to 1.0
# and the score stays in [0, 1] without a surprise term.
# --------------------------------------------------------------------------- #
# nominal design weights (BEFORE folding out the excluded surprise term):
#   novelty 0.40 · corroboration 0.25 · source_tier 0.15 · surprise 0.10 ·
#   crowding-penalty 0.10
# After removing surprise (0.10) and renormalising the four live positive/penalty
# terms to sum to 1.0:
W_NOVELTY = 0.44        # (a) novelty-z of the primary subject — the headline prior
W_CORROBORATION = 0.28  # (b) novelty-gated cross-desk breadth
W_SOURCE_TIER = 0.17    # (c) qkernel source-tier weight
W_CROWDING = 0.11       # (e) trailing-7d volume-z PENALTY (subtracted)

# scheduled-surprise (feature d) is EXCLUDED at v0. Documented, not silently
# dropped: the task's opt-out rule says the surprise feature only counts when
# TOPIC-GATED, but china_news_intel.is_surprise is a pure date-collision test and
# qbus rows carry no scheduled_ref, so the feature is both invalid and underivable.
# 2026-07-16: china_news_intel's scheduled_ref stamp is now channel-gated at
# accrual (MN-06 CN port), so FORWARD rows are topic-gated — but the exclusion
# still stands on the second leg (qbus rows carry no scheduled_ref) and pre-fix
# accrued rows keep their blanket stamps. Un-excluding needs its own adjudication.
_SURPRISE_EXCLUDED = True
_SURPRISE_NOMINAL_WEIGHT = 0.10   # folded into the four live terms above

# novelty_z is unbounded above; squash it into [0, 1] with a logistic centred so
# that z=0 → 0.5 and z≈+3 (qbus's "maximally novel over a flat-zero window")
# → ~0.95. k chosen so the mid-range (z∈[-2, +2]) spans most of the (0, 1) band.
_NOVELTY_K = 0.9
# trailing crowding window (D6: "trailing 7d item-volume z on the same entity/theme")
_CROWDING_WINDOW_DAYS = 7
# novelty trailing window — qbus default is 30d; keep it explicit here for the duel.
_NOVELTY_WINDOW_DAYS = 30
# corroboration breadth saturates: 1 desk = no corroboration, 3+ desks ≈ full.
_BREADTH_SAT = 3.0


# --------------------------------------------------------------------------- #
# squashers — pure, bounded, deterministic
# --------------------------------------------------------------------------- #
def _logistic(x: float, k: float = 1.0, x0: float = 0.0) -> float:
    """Standard logistic squash into (0, 1). PURE. Never raises/overflows."""
    try:
        return 1.0 / (1.0 + math.exp(-k * (x - x0)))
    except OverflowError:
        return 0.0 if (x - x0) < 0 else 1.0


def _novelty_feature(z: float | None) -> float:
    """Map novelty_z → [0, 1]. None (no store / no trailing variance to score
    against) is NEUTRAL (0.5), not zero — absence of a novelty read is not
    evidence of a stale story. PURE."""
    if z is None:
        return 0.5
    return _logistic(float(z), k=_NOVELTY_K, x0=0.0)


def _breadth_feature(echo: dict | None) -> float:
    """Cross-desk breadth → [0, 1], saturating at _BREADTH_SAT desks. A single
    desk (or an absent echo) is 0 corroboration. PURE."""
    if not echo:
        return 0.0
    breadth = float(echo.get("breadth") or echo.get("n_desks") or 0)
    if breadth <= 1.0:
        return 0.0
    return min(1.0, (breadth - 1.0) / (_BREADTH_SAT - 1.0))


def _tier_feature(source_tier) -> float:
    """qkernel tier weight → [0, 1]. tier 1 → 1.0, tier 3 → 0.58, tier 0 → 0.0.
    PURE."""
    try:
        t = int(source_tier)
    except (TypeError, ValueError):
        t = 0
    return float(qkernel.TIER_WEIGHT.get(t, 0.0))


def _crowding_penalty(z_crowd: float | None) -> float:
    """Trailing-window volume-z → a [0, 1] PENALTY magnitude. High positive z
    (subject already loud for a week) → large penalty; z ≤ 0 (quiet or cooling)
    → ~0 penalty. None → 0 penalty (no crowding evidence). PURE.

    Only the POSITIVE tail is a penalty: crowding is 'attention is late', which is
    a high-recent-volume state, so a below-mean z must not become a *bonus*.
    """
    if z_crowd is None:
        return 0.0
    z = float(z_crowd)
    if z <= 0.0:
        return 0.0
    # logistic on the positive tail, re-based so z=0 → 0 penalty, z→∞ → 1.
    return 2.0 * (_logistic(z, k=_NOVELTY_K, x0=0.0) - 0.5)


# --------------------------------------------------------------------------- #
# lane + primary-subject resolution
# --------------------------------------------------------------------------- #
def lane_of(item: dict) -> str:
    """'cn' | 'us' lane for an item. The bus stores lang zh for the CN desk and
    en for the US desks; a mixed/auto row with any CJK title routes CN (the CJK
    content is the discriminating signal, matching qkernel.norm_title). PURE."""
    lang = str(item.get("lang") or "").lower()
    if lang in ("zh", "cjk", "chinese"):
        return "cn"
    if lang in ("en", "latin"):
        return "us"
    # auto / unknown — sniff the title.
    return "cn" if qkernel.has_cjk(str(item.get("title") or "")) else "us"


def primary_subject(item: dict) -> str | None:
    """The item's PRIMARY entity-or-theme (spec: novelty of 'the item's primary
    entity-or-theme'). First entity wins; else first theme; else None. The
    entities/themes fields are comma-joined strings in the bus (or lists from a
    caller) — reuse qbus._split so the parsing is identical to the store's. PURE."""
    ents = qbus._split(item.get("entities"))
    if ents:
        return ents[0]
    thms = qbus._split(item.get("themes"))
    if thms:
        return thms[0]
    return None


# --------------------------------------------------------------------------- #
# trailing crowding-z — same subject, trailing window, item VOLUME (not novelty)
# --------------------------------------------------------------------------- #
def _crowding_z(subject: str, asof, df, window_days: int = _CROWDING_WINDOW_DAYS
                ) -> float | None:
    """z-score of the subject's trailing-`window_days` mean daily volume vs its
    own longer novelty window — i.e. 'has this subject been unusually loud over
    the last week?'. Distinct from novelty_z (which compares TODAY to the
    trailing window): crowding compares the RECENT WINDOW's level to the baseline,
    so a story that broke a week ago and stayed loud is crowded even if today is
    flat. PURE-ish (reads the bus unless df injected). Never raises.

    Implementation reuses qbus._subject_daily_counts to avoid a second, divergent
    volume counter: it returns (today, trailing_series) over a window; we take the
    trailing series over the long novelty window and z-score the LAST
    `window_days` of it against the whole series.
    """
    try:
        a = qbus._asof_date(asof)
        if a is None:
            return None
        _, series = qbus._subject_daily_counts(df, subject, a, _NOVELTY_WINDOW_DAYS)
        if not series or len(series) < window_days + 1:
            return None
        n = len(series)
        mean = sum(series) / n
        var = sum((x - mean) ** 2 for x in series) / n
        sd = var ** 0.5
        recent = series[-window_days:]
        recent_mean = sum(recent) / len(recent)
        if sd <= 1e-9:
            # flat history: recent above the flat level = crowded, else not.
            return 3.0 if recent_mean > mean else 0.0
        return round((recent_mean - mean) / sd, 3)
    except Exception as e:  # noqa: BLE001
        log.debug("importance_v0._crowding_z failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# the score
# --------------------------------------------------------------------------- #
def clean_df(df):
    """Return a bus-frame COPY whose `seendate` is a uniform date-only ISO string
    (YYYY-MM-DD) and whose rows all carry a resolvable date — the volume basis
    novelty/crowding count against.

    WHY (the upstream bugs this read-side guard works around, now FIXED in qbus
    as of W4 but clean_df is retained for explicit pre-normalisation by callers
    that want to share one clean snapshot across many score_components calls):

      1. The store previously mixed tz-AWARE and tz-NAIVE seendate strings.
         qbus._subject_daily_counts now uses utc=True + .map(ts.date()) so the
         tz-mixed column no longer causes NaT.  clean_df normalises on the
         read-side anyway for callers that pass a raw store snapshot.
      2. Dateless rows (both seendate AND _crawled_at empty) cannot anchor a
         daily count; we drop them here so per-item scoring always has a valid
         asof, matching the score_store behaviour (which also calls clean_df).

    Normalising seendate to a date-only ISO string keeps qbus's downstream parse
    fast (format='mixed', utc=True, .dt.strftime('%Y-%m-%d')). A row with no
    usable date is dropped — the PIT-safe basis for the z-scores.
    PURE (no clock). Never raises."""
    try:
        import pandas as pd
        if df is None or len(df) == 0:
            return df
        out = df.copy()
        d = pd.to_datetime(out["seendate"], errors="coerce", format="mixed", utc=True)
        fb = pd.to_datetime(out["_crawled_at"], errors="coerce", format="mixed", utc=True)
        d = d.fillna(fb)
        keep = d.notna()
        out = out[keep].copy()
        # rewrite seendate to a uniform date-only ISO string so qbus's internal
        # tz-naive to_datetime parses every row identically and NaT-free.
        out["seendate"] = d[keep].dt.strftime("%Y-%m-%d")
        return out.reset_index(drop=True)
    except Exception as e:  # noqa: BLE001
        log.debug("importance_v0.clean_df failed (%s)", e)
        return df


def score_components(item: dict, asof, df=None) -> dict:
    """Return every feature contribution for ONE item (for the duel report /
    tests / audit), plus the final importance_v0 in [0, 1]. Deterministic — asof
    REQUIRED, df injectable. Never raises.

    Keys: subject, lane, novelty_z, novelty, breadth, tier, crowding_z,
          crowding_penalty, importance_v0.

    The df passed here is expected to be date-clean (see clean_df); score_store
    cleans once up-front so per-item scoring shares one clean snapshot.
    """
    if df is None:
        df = clean_df(qbus.read_items())

    subject = primary_subject(item)
    lane = lane_of(item)

    nz = qbus.novelty_z(subject, asof, window_days=_NOVELTY_WINDOW_DAYS, df=df) \
        if subject else None
    novelty = _novelty_feature(nz)

    # Pass asof to echo_stats so corroboration is PIT-filtered: only items seen
    # on or before the scoring date count as corroborators (W4 bug-fix, see
    # qbus.echo_stats for the full explanation).
    echo = qbus.echo_stats(str(item.get("event_key") or ""), df=df, asof=asof)
    breadth = _breadth_feature(echo)
    # (b) corroboration is novelty-GATED breadth: within-window echo of a LOW-novelty
    # subject (breadth high but novelty low) must NOT inflate the score. Multiply
    # breadth by novelty so a big cluster of an old story pushes the term toward 0.
    corroboration = breadth * novelty

    tier = _tier_feature(item.get("source_tier"))

    cz = _crowding_z(subject, asof, df) if subject else None
    penalty = _crowding_penalty(cz)

    raw = (
        W_NOVELTY * novelty
        + W_CORROBORATION * corroboration
        + W_SOURCE_TIER * tier
        - W_CROWDING * penalty
    )
    imp = max(0.0, min(1.0, raw))

    return {
        "subject": subject,
        "lane": lane,
        "novelty_z": nz,
        "novelty": round(novelty, 6),
        "breadth": round(breadth, 6),
        "corroboration": round(corroboration, 6),
        "tier": round(tier, 6),
        "crowding_z": cz,
        "crowding_penalty": round(penalty, 6),
        "importance_v0": round(imp, 6),
        "version": VERSION,
    }


def importance_v0(item: dict, asof, df=None) -> float:
    """Deterministic novelty-first importance in [0, 1] for ONE qbus item.
    Convenience wrapper over score_components. asof REQUIRED (PIT). Never raises."""
    return score_components(item, asof, df=df)["importance_v0"]


# --------------------------------------------------------------------------- #
# batch scoring — score every bus item per lane, at ITS OWN asof
# --------------------------------------------------------------------------- #
def _item_asof(row: dict) -> str | None:
    """The PIT asof for an item = its seendate day (fallback _crawled_at day)."""
    for k in ("seendate", "_crawled_at"):
        v = str(row.get(k) or "")[:10]
        if v:
            try:
                date.fromisoformat(v)
                return v
            except ValueError:
                continue
    return None


def score_store(df=None, lane: str | None = None) -> list[dict]:
    """Score EVERY item in the bus store (both lanes unless `lane` filters) at its
    own asof. Returns a list of dicts with the item_id, lane, asof, and the full
    component breakdown. The novelty/echo/crowding reads are all PIT against the
    SAME df snapshot (so the score of a row uses only what the bus knew as of that
    row's day-of-store — the store is append-only keep-first, so this is a faithful
    replay). Deterministic. Never raises into the caller.
    """
    if df is None:
        df = qbus.read_items()
    df = clean_df(df)
    if df is None or len(df) == 0:
        return []

    out: list[dict] = []
    for row in df.to_dict("records"):
        ln = lane_of(row)
        if lane and ln != lane:
            continue
        asof = _item_asof(row)
        if asof is None:
            continue
        comp = score_components(row, asof, df=df)
        comp["item_id"] = str(row.get("item_id") or "")
        comp["event_key"] = str(row.get("event_key") or "")
        comp["asof"] = asof
        comp["source_tier"] = int(row.get("source_tier") or 0)
        out.append(comp)
    return out
