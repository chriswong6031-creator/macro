"""engine.marketing.insider_feed — Form-4 open-market-purchase candidates (E2).

Lane 6 of the masterplan lane matrix (research/
MARKETING_CONTENT_STUDIO_LLM_FIRST_MASTERPLAN_BY_FABLE.md §10): insider buys,
daily batch, fact-locked LLM writer, OBSERVATION register, display-tier, no
calls. The editorial law is research/marketing_dockets/
CODEX_CONTENT_CASE_STUDIES_2026_07_28.md §Insider-signal post family, whose
§Signal-calculation framework is implemented here VERBATIM::

    purchase_value            = purchased_shares × weighted_average_price
    prior_shares              = post_transaction_shares − purchased_shares
    relative_stake_increase   = purchased_shares ÷ prior_shares × 100

THE DEFECT THIS LANE EXISTS TO NOT REPEAT. The codex measured five real insider
posts and found the format's central failure is that **absolute dollars mislead**:
a $6.92M purchase read as more important than a $299K one, while the filings
imply the $6.92M added ~0.85% to an already-large holding and the $299K one
multiplied its holder's stake about twelve-fold. The observed style then spent
that fact on "I'm paying attention". So the RELATIVE arithmetic is computed
first, the mechanism is classified from it, and the mechanism sentence is a
TOP-THREE fact — the only three `copywriter.build_context` shows the writer.

WHAT THE SOURCE CAN AND CANNOT TELL US. ``data/quiver/insiders.parquet`` carries
Ticker, Date (transaction), fileDate, Name, officerTitle, isDirector/isOfficer/
isTenPercentOwner, TransactionCode, AcquiredDisposedCode, Shares, PricePerShare,
SharesOwnedFollowing, directOrIndirectOwnership, ``_first_seen``. It does NOT
carry a Rule 10b5-1 indication or an original/amended flag, both of which the
codex's validation step asks for. That absence is recorded per candidate in
``risk_flags`` rather than papered over, and it is why the lane's copy never
claims a purchase was discretionary or unplanned — only that it happened, at
transaction code P, on the open market.

``engine/insider_power.py`` (0-100 conviction score) is used ONLY as display-tier
context words via :func:`power_context`; the score itself never reaches copy —
LLMs may de-escalate calibrated keys, never originate or print them.

Public API::

    lane_cfg(cfg)                                -> dict
    load_insiders(root)                          -> "pd.DataFrame | None"
    derive_transaction(shares, price, following) -> dict
    classify_mechanism(derived, *, cluster_n, repeat_n, cfg) -> (str, str)
    power_context(payload)                       -> str      (plain words)
    open_market_purchases(df, *, today, cfg, cooled) -> list[dict]
    insider_facts(cand)                          -> dict     (FactPacket)
    assert_lag_disclosed(packet)                 -> None     (raises)
    candidates(root, *, today, cfg, cooled, power) -> list[dict]
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

# Shared filing-lane primitives live in `congress_feed` — the first of the two
# lanes to land — rather than in a fourth module, so the two lanes cannot
# disagree about how a number is spelled. (A `filing_format` extraction would
# read better; it is out of this build's file scope.)
from engine.marketing.congress_feed import (
    LagDisclosureError,
    ScoreLeakError,
    TOP_FACTS_VISIBLE,
    assert_no_score,
    display_date,
    display_entity_name,
    display_multiple,
    display_pct,
    display_price,
    display_usd,
    fold_numbers,
    lag_days_between,
    narrow_by_day,
    parse_iso_date,
    records,
)

__all__ = [
    "DEFAULTS",
    "LAG_FACT_ID",
    "MECHANISMS",
    "lane_cfg",
    "load_insiders",
    "derive_transaction",
    "classify_mechanism",
    "power_context",
    "open_market_purchases",
    "insider_facts",
    "assert_lag_disclosed",
    "candidates",
]

#: Repo-relative source. Read-only — this lane never writes to `data/`.
_INSIDERS_REL = Path("data") / "quiver" / "insiders.parquet"

#: The fact id every packet must carry inside the writer-visible top three.
LAG_FACT_ID = "insider_report_lag"

#: The codex's mechanism vocabulary, in the order it lists them.
MECHANISMS: tuple[str, ...] = (
    "NEW_POSITION",
    "MATERIAL_ADDITION",
    "REPEAT_BUY",
    "CLUSTER_BUY",
    "SMALL_ADDITION_TO_LARGE_STAKE",
    "NEEDS_REVIEW",
)

#: Config defaults (`config/marketing.yml` → `insider_lane:`).
DEFAULTS: dict[str, Any] = {
    # SHIP ENABLED (operator 2026-07-29). The outbox approval gate is what still
    # stands between a candidate and a timeline.
    "enabled": True,
    "max_per_day": 2,
    #: Absolute-size floor. Below this the relative arithmetic is usually noise
    #: too (a 400% increase on a 50-share stake is not a fact about a company).
    "min_value_usd": 100_000.0,
    "first_seen_lookback_days": 1,
    #: A Form 4 is due within two business days; anything filed much later than
    #: this is a compliance story, not a market one.
    "max_file_lag_days": 10,
    #: relative_stake_increase_pct at or above this ⇒ MATERIAL_ADDITION.
    "material_pct": 25.0,
    #: … and below this, with a large dollar amount, ⇒ SMALL_ADDITION_TO_LARGE_STAKE.
    "small_pct": 5.0,
    "large_value_usd": 250_000.0,
    #: Cluster thresholds mirror `engine.insider_power` (CLUSTER_MIN_SELLERS=3,
    #: CLUSTER_WINDOW_DAYS=45) so one house definition of "a cluster" exists.
    "cluster_min_insiders": 3,
    "cluster_window_days": 45,
    #: "the insider's Nth verified open-market purchase in [period]" (codex).
    "repeat_min_purchases": 2,
    "repeat_window_days": 180,
}

#: The ONLY transaction that may be called a purchase: SEC code P (open-market
#: or private purchase) acquiring shares. A (award/grant), M (option exercise),
#: F (tax withholding), C (conversion), G (gift) and J (other) are exactly the
#: codex's "compensation, exercise, award, conversion or internal transfer".
_PURCHASE_CODE = "P"
_ACQUIRED_CODE = "A"

#: US common-stock ticker shape; a Quiver multi-ticker cell ("SMX; SMXWW")
#: is split on the separator and the first leg is used.
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")
_TICKER_SPLIT_RE = re.compile(r"[;,/]")
_TICKER_JUNK: frozenset[str] = frozenset({"", "N/A", "NA", "NONE", "NAN"})

#: `insider_power` posture → plain words. The 0-100 score never leaves the
#: engine; these phrases carry no digit and :func:`assert_no_score` proves it.
_POSTURE_WORDS: dict[str, str] = {
    "insider_buy": "the wider insider tape at this company has leaned toward buying",
    "insider_sell": "the wider insider tape at this company has leaned toward selling",
}


# ─────────────────────────────────────────────────────────────────────────────
# Config + source
# ─────────────────────────────────────────────────────────────────────────────

def lane_cfg(cfg: dict | None) -> dict[str, Any]:
    """Resolved `insider_lane` block — defaults filled, types coerced."""
    block = ((cfg or {}).get("insider_lane") or {}) if isinstance(cfg, dict) else {}
    out = dict(DEFAULTS)
    if isinstance(block, dict):
        for key in DEFAULTS:
            if block.get(key) is not None:
                out[key] = block[key]
    out["enabled"] = bool(out["enabled"])
    for key in ("max_per_day", "first_seen_lookback_days", "max_file_lag_days",
                "cluster_min_insiders", "cluster_window_days",
                "repeat_min_purchases", "repeat_window_days"):
        try:
            out[key] = max(int(out[key]), 0)
        except (TypeError, ValueError):
            out[key] = DEFAULTS[key]
    for key in ("min_value_usd", "material_pct", "small_pct", "large_value_usd"):
        try:
            out[key] = max(float(out[key]), 0.0)
        except (TypeError, ValueError):
            out[key] = DEFAULTS[key]
    return out


def load_insiders(root: Path | str | None = None) -> Any:
    """The Quiver Form-4 parquet, or None when missing/unreadable (fail-soft)."""
    try:
        import pandas as pd  # noqa: PLC0415
        path = (Path(root) if root is not None else Path(".")) / _INSIDERS_REL
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        return df if len(df) else None
    except Exception:  # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────────────────────────
# The codex §Signal-calculation framework
# ─────────────────────────────────────────────────────────────────────────────

def _looks_rounded(shares: float) -> bool:
    """Do the post-transaction holdings look reported to the nearest lot?

    The codex: "If post-transaction holdings are rounded, label the derived
    change approximate." A holding of exactly 46,000 is almost certainly a
    rounded figure and the prior-share subtraction inherits that error; 46,977
    is not. Thresholded by magnitude so a genuine 100-share holding is not
    called approximate.
    """
    if shares <= 0:
        return False
    if shares >= 10_000 and shares % 1_000 == 0:
        return True
    return shares >= 100_000 and shares % 100 == 0


def derive_transaction(
    *,
    shares: Any,
    price: Any,
    shares_following: Any,
) -> dict[str, Any]:
    """The codex's three derived fields, plus the precision caveats.

    Returns ``{purchase_value, prior_shares, relative_stake_increase_pct,
    stake_multiple, approximate, reconciles, new_position}``. Every field is
    None when it cannot be computed — never zero, because zero is a claim.

    ``reconciles`` is the codex's validation step "do post-transaction shares
    reconcile with prior shares plus the purchase?": post-transaction holdings
    BELOW the purchased quantity are internally impossible for a purchase, and a
    row that fails it is sent to NEEDS_REVIEW rather than guessed at.
    """
    def _num(v: Any) -> float | None:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return None if (f != f or f in (float("inf"), float("-inf"))) else f

    n_shares, n_price, n_after = _num(shares), _num(price), _num(shares_following)

    out: dict[str, Any] = {
        "purchase_value": None,
        "prior_shares": None,
        "relative_stake_increase_pct": None,
        "stake_multiple": None,
        "approximate": False,
        "reconciles": False,
        "new_position": False,
    }
    if n_shares is None or n_shares <= 0:
        return out

    if n_price is not None and n_price > 0:
        out["purchase_value"] = n_shares * n_price

    if n_after is None:
        return out

    prior = n_after - n_shares
    # Floating-point crumbs on fractional share counts (10190.823) must not
    # decide NEW_POSITION vs a negative prior.
    if abs(prior) < 1e-6:
        prior = 0.0
    if prior < 0:
        return out  # reconciles stays False → NEEDS_REVIEW

    out["reconciles"] = True
    out["prior_shares"] = prior
    out["approximate"] = _looks_rounded(n_after)
    if prior == 0:
        # "If prior shares are zero, classify the transaction as a new disclosed
        # position instead of calculating a percentage." — codex §framework.
        out["new_position"] = True
        return out
    out["relative_stake_increase_pct"] = n_shares / prior * 100.0
    out["stake_multiple"] = n_after / prior
    return out


def classify_mechanism(
    derived: dict,
    *,
    cluster_n: int = 0,
    repeat_n: int = 0,
    cfg: dict | None = None,
) -> tuple[str, str]:
    """(mechanism, "why it matters" sentence) for one derived transaction.

    PRECEDENCE, and why it is not the codex's listing order. NEW_POSITION and
    MATERIAL_ADDITION are properties of THIS transaction's own arithmetic, and
    they are precisely the facts the codex measured the observed style throwing
    away ("nearly doubles down" concealing a twelve-fold increase). CLUSTER_BUY
    and REPEAT_BUY are pattern facts ABOUT OTHER FILINGS; they are strong, but a
    cluster label on a twelve-fold personal increase would bury the better fact.
    So the arithmetic wins the label and the pattern survives as its own fact in
    the packet — nothing is lost, one thing leads.

        NEW_POSITION → MATERIAL_ADDITION → CLUSTER_BUY → REPEAT_BUY
                     → SMALL_ADDITION_TO_LARGE_STAKE → NEEDS_REVIEW

    NEEDS_REVIEW is a REFUSAL, not a weak label: `open_market_purchases` drops
    it. A transaction we cannot characterise is one we cannot write a mechanism
    sentence about, and the codex's own instruction for a failed validation is
    "output DO NOT PUBLISH".
    """
    lane = lane_cfg(cfg)
    value = derived.get("purchase_value")
    rel = derived.get("relative_stake_increase_pct")
    mult = derived.get("stake_multiple")

    if not derived.get("reconciles"):
        return "NEEDS_REVIEW", (
            "The filed share counts do not reconcile, so no stake change is claimed here.")

    approx = "about " if derived.get("approximate") else ""

    if derived.get("new_position"):
        return "NEW_POSITION", (
            "This is a newly disclosed position — there was no prior stake to add to.")

    if _is_material(rel, lane):
        if mult and mult >= 2.0:
            return "MATERIAL_ADDITION", (
                f"The purchase took the disclosed holding to {approx}"
                f"{display_multiple(mult)} its previous size. The relative change "
                f"is the part that matters, not the dollar headline.")
        return "MATERIAL_ADDITION", (
            f"The purchase raised the disclosed holding by {approx}"
            f"{display_pct(rel)}. The relative change is the part that matters, "
            f"not the dollar headline.")

    if cluster_n >= max(lane["cluster_min_insiders"], 1):
        return "CLUSTER_BUY", (
            f"{cluster_n} separate insiders bought this name inside the same "
            f"{lane['cluster_window_days']}-day window.")

    if repeat_n >= max(lane["repeat_min_purchases"], 1):
        return "REPEAT_BUY", (
            f"This is the same insider's {_ordinal(repeat_n)} open-market purchase "
            f"here in {lane['repeat_window_days']} days.")

    if (rel is not None and rel < lane["small_pct"]
            and value is not None and value >= lane["large_value_usd"]):
        return "SMALL_ADDITION_TO_LARGE_STAKE", (
            f"The dollar amount is large, but it added only {approx}"
            f"{display_pct(rel)} to a holding that was already big.")

    return "NEEDS_REVIEW", (
        "Nothing in the filing separates this from routine activity.")


def _is_material(rel: Any, lane: dict) -> bool:
    """Is the relative stake increase at or above the material threshold?"""
    try:
        return rel is not None and float(rel) >= float(lane["material_pct"])
    except (TypeError, ValueError):
        return False


def _ordinal(n: int) -> str:
    """2 → "second". Falls back to "2nd" past the words we need."""
    words = {2: "second", 3: "third", 4: "fourth", 5: "fifth",
             6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth"}
    if n in words:
        return words[n]
    suffix = "th" if 11 <= (n % 100) <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def power_context(payload: Any) -> str:
    """Plain-word context from an `insider_power` payload, or "".

    Takes the payload's POSTURE (a categorical the engine already publishes),
    never its 0-100 score. Returns a clause completing "Separately, …".
    """
    if not isinstance(payload, dict):
        return ""
    signal = str(payload.get("signal") or payload.get("posture") or "").strip().lower()
    phrase = _POSTURE_WORDS.get(signal)
    if not phrase:
        return ""
    assert_no_score(phrase)
    return phrase


# ─────────────────────────────────────────────────────────────────────────────
# Candidate selection
# ─────────────────────────────────────────────────────────────────────────────

def _clean_ticker(raw: Any) -> str:
    """"SMX; SMXWW" → "SMX"; "N/A"/None/"" → ""."""
    first = _TICKER_SPLIT_RE.split(str(raw or ""))[0].strip().upper()
    if first in _TICKER_JUNK or not _TICKER_RE.match(first):
        return ""
    return first


def _role(row: dict) -> str:
    """The insider's filed role, in the words the filing uses."""
    title = str(row.get("officerTitle") or "").strip()
    if title and title.lower() not in ("nan", "none"):
        return title
    if _truthy(row.get("isDirector")):
        return "Director"
    if _truthy(row.get("isTenPercentOwner")):
        # NOT "10% owner". That phrase is an SEC checkbox, not a filed title,
        # and rendering it verbatim opens a post with a percentage the filer
        # never stated — which then lands in the numbers whitelist as a real
        # figure ("10%") the copy is licensed to reason about. "Large
        # shareholder" says the same thing and invents no number.
        return "Large shareholder"
    if _truthy(row.get("isOfficer")):
        return "Officer"
    return "Insider"


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("true", "1", "yes")


def _is_purchase(row: dict) -> bool:
    return (str(row.get("TransactionCode") or "").strip().upper() == _PURCHASE_CODE
            and str(row.get("AcquiredDisposedCode") or "").strip().upper() == _ACQUIRED_CODE)


def open_market_purchases(
    df: Any,
    *,
    today: str,
    cfg: dict | None = None,
    cooled: frozenset[str] | set[str] | None = None,
) -> list[dict]:
    """Tonight's postable Form-4 purchases, best first, capped at `max_per_day`.

    Two passes over the frame. The FIRST builds the pattern history — every
    open-market purchase in the repeat/cluster windows, which is what
    CLUSTER_BUY and REPEAT_BUY are counted from; a cluster measured only over
    tonight's crawl would be a cluster of one filing agent's batch upload. The
    SECOND selects tonight's rows.

    Ranking: mechanism strength first (the codex's whole argument is that the
    dollar headline is the wrong sort key), then relative stake change, then
    dollar value, then ticker — a total order, no RNG, no wall clock.
    """
    lane = lane_cfg(cfg)
    if not lane["enabled"] or df is None:
        return []
    today_d = parse_iso_date(today)
    if today_d is None:
        return []
    blocked = {str(t).upper() for t in (cooled or ())}
    allowed_days = {
        date.fromordinal(today_d.toordinal() - back).isoformat()
        for back in range(lane["first_seen_lookback_days"] + 1)
    }

    # ── pass 1: pattern history ──────────────────────────────────────────────
    history: list[dict] = []
    for row in records(df):
        if not _is_purchase(row):
            continue
        ticker = _clean_ticker(row.get("Ticker"))
        trade_d = parse_iso_date(row.get("Date"))
        if not ticker or trade_d is None:
            continue
        history.append({
            "ticker": ticker,
            "name": str(row.get("Name") or "").strip().upper(),
            "trade_date": trade_d,
        })

    def _cluster_n(ticker: str, anchor: date) -> int:
        lo = date.fromordinal(anchor.toordinal() - lane["cluster_window_days"])
        return len({h["name"] for h in history
                    if h["ticker"] == ticker and h["name"] and lo <= h["trade_date"] <= anchor})

    def _repeat_n(ticker: str, name: str, anchor: date) -> int:
        lo = date.fromordinal(anchor.toordinal() - lane["repeat_window_days"])
        return sum(1 for h in history
                   if h["ticker"] == ticker and h["name"] == name
                   and lo <= h["trade_date"] <= anchor)

    # ── pass 2: tonight's rows ───────────────────────────────────────────────
    picks: list[dict] = []
    for row in records(narrow_by_day(df, "_first_seen", allowed_days)):
        if str(row.get("_first_seen") or "")[:10] not in allowed_days:
            continue
        if not _is_purchase(row):
            continue

        ticker = _clean_ticker(row.get("Ticker"))
        if not ticker or ticker in blocked:
            continue

        name = str(row.get("Name") or "").strip()
        if not name:
            continue

        trade_d = parse_iso_date(row.get("Date"))
        file_d = parse_iso_date(row.get("fileDate"))
        lag = lag_days_between(trade_d, file_d)
        # FAIL CLOSED: the lag sentence is mandatory, so an undatable row is
        # unpostable.
        if lag is None or lag < 0 or lag > lane["max_file_lag_days"]:
            continue

        derived = derive_transaction(
            shares=row.get("Shares"),
            price=row.get("PricePerShare"),
            shares_following=row.get("SharesOwnedFollowing"),
        )
        value = derived.get("purchase_value")
        if value is None or value < lane["min_value_usd"]:
            continue

        anchor = trade_d
        cluster_n = _cluster_n(ticker, anchor)
        repeat_n = _repeat_n(ticker, name.upper(), anchor)
        mechanism, why = classify_mechanism(
            derived, cluster_n=cluster_n, repeat_n=repeat_n, cfg=cfg)
        # NEEDS_REVIEW is a refusal (codex: "if primary verification fails,
        # output DO NOT PUBLISH"), not a publishable weak label.
        if mechanism == "NEEDS_REVIEW":
            continue

        risk_flags: list[str] = [
            # Recorded, not hidden: the codex's validation list asks for both and
            # the Quiver feed carries neither column.
            "rule_10b5_1_status_unavailable",
            "original_or_amended_flag_unavailable",
        ]
        if derived.get("approximate"):
            risk_flags.append("post_transaction_holdings_look_rounded")

        picks.append({
            "ticker": ticker,
            "insider_name": display_entity_name(name),
            "insider_name_raw": name,
            "role": _role(row),
            "trade_date": trade_d.isoformat() if trade_d else "",
            "file_date": file_d.isoformat() if file_d else "",
            "lag_days": lag,
            "shares": float(row.get("Shares") or 0.0),
            "price": float(row.get("PricePerShare") or 0.0),
            "shares_following": float(row.get("SharesOwnedFollowing") or 0.0),
            "ownership": ("indirect"
                          if str(row.get("directOrIndirectOwnership") or "").strip().upper() == "I"
                          else "direct"),
            "mechanism": mechanism,
            "why_it_matters": why,
            "cluster_n": cluster_n,
            "repeat_n": repeat_n,
            "risk_flags": risk_flags,
            "power_context": "",
            "source": "insider",
            **derived,
        })

    rank = {m: i for i, m in enumerate(MECHANISMS)}
    picks.sort(key=lambda c: (
        rank.get(c["mechanism"], len(MECHANISMS)),
        -(c.get("relative_stake_increase_pct") or 0.0),
        -(c.get("purchase_value") or 0.0),
        c["ticker"],
    ))

    seen: set[str] = set()
    out: list[dict] = []
    for cand in picks:
        if cand["ticker"] in seen:
            continue
        seen.add(cand["ticker"])
        out.append(cand)
    return out[: lane["max_per_day"]]


# ─────────────────────────────────────────────────────────────────────────────
# Fact packet
# ─────────────────────────────────────────────────────────────────────────────

def assert_lag_disclosed(packet: dict) -> None:
    """Raise :class:`LagDisclosureError` unless the lag fact is WRITER-VISIBLE.

    Same rank check as the congress lane, and for the same reason: a fact ranked
    below `TOP_FACTS_VISIBLE` is in the packet and absent from the prompt.
    """
    facts = list((packet or {}).get("facts") or [])
    ordered = sorted(facts, key=lambda f: (-int(f.get("salience") or 0), str(f.get("id") or "")))
    visible = [str(f.get("id") or "") for f in ordered[:TOP_FACTS_VISIBLE]]
    if LAG_FACT_ID not in visible:
        raise LagDisclosureError(
            f"insider packet must carry {LAG_FACT_ID!r} inside the top "
            f"{TOP_FACTS_VISIBLE} facts by salience; visible ids were {visible}")


def _shares_phrase(n: float) -> str:
    """A share count in the corpus register: "25,000 shares", "1.3M shares"."""
    if n >= 1_000_000:
        return f"{display_price(n / 1_000_000)}M shares"
    return f"{n:,.0f} shares"


def insider_facts(cand: dict) -> dict:
    """FactPacket for one Form-4 purchase: ``{facts, numbers_whitelist}``.

    The three WRITER-VISIBLE facts are, in order: the transaction, the filing
    lag, and the mechanism — which is the codex's recommended template minus the
    portrait and the hashtag pile. Verification, ownership type and the rounded-
    holdings caveat ride below as licensed context.
    """
    ticker = str(cand.get("ticker") or "")
    name = str(cand.get("insider_name") or "")
    role = str(cand.get("role") or "Insider")
    shares = float(cand.get("shares") or 0.0)
    price_s = display_price(cand.get("price"))
    value_s = display_usd(cand.get("purchase_value"))
    after = float(cand.get("shares_following") or 0.0)
    prior = cand.get("prior_shares")
    approx = "about " if cand.get("approximate") else ""

    trade_d, file_d = parse_iso_date(cand.get("trade_date")), parse_iso_date(cand.get("file_date"))
    straddles = bool(trade_d and file_d and trade_d.year != file_d.year)

    bought = f"{role} {name} bought {_shares_phrase(shares)} of {ticker}"
    if price_s:
        bought += f" at an average ${price_s}"
    if value_s:
        bought += f", roughly {value_s}"

    lag = int(cand.get("lag_days") or 0)
    facts: list[dict] = [
        {"id": "insider_purchase", "text": bought + ".", "salience": 10},
        {
            # THE LAG FACT — mandatory, ranked to survive the top-three cut.
            "id": LAG_FACT_ID,
            "text": (
                f"The buy is dated {display_date(trade_d, with_year=straddles)}; "
                f"the Form 4 only reached the tape {display_date(file_d)}, "
                f"{lag} {'day' if lag == 1 else 'days'} later."
            ),
            "salience": 9,
        },
        {
            "id": "insider_mechanism",
            "text": str(cand.get("why_it_matters") or "").strip(),
            "salience": 8,
        },
    ]

    # "up from 0 shares" is not a baseline, it is the NEW_POSITION mechanism
    # restated as arithmetic — and it puts a meaningless "0" in the whitelist.
    if prior is not None and float(prior) > 0 and after > 0:
        facts.append({
            "id": "insider_stake",
            "text": (f"{name} now holds {approx}{_shares_phrase(after)}, "
                     f"up from {approx}{_shares_phrase(float(prior))}."),
            "salience": 7,
        })

    if int(cand.get("cluster_n") or 0) >= 2 and cand.get("mechanism") != "CLUSTER_BUY":
        facts.append({
            "id": "insider_cluster_context",
            "text": (f"{int(cand['cluster_n'])} different insiders have bought "
                     f"{ticker} on the open market recently."),
            "salience": 5,
        })

    phrase = str(cand.get("power_context") or "").strip()
    if phrase:
        assert_no_score(phrase)
        facts.append({
            "id": "insider_power_context",
            "text": f"Separately, {phrase}.",
            "salience": 4,
        })

    facts.append({
        "id": "insider_open_market",
        "text": (f"Filed as an open-market purchase held {cand.get('ownership', 'direct')}ly "
                 f"— not a grant, an award, or an option exercise."),
        "salience": 3,
    })

    if cand.get("approximate"):
        facts.append({
            "id": "insider_rounded_caveat",
            "text": ("The filed post-transaction holding looks rounded, so the "
                     "implied prior stake is approximate."),
            "salience": 2,
        })

    facts.append({
        "id": "insider_disclosure_note",
        "text": ("A Form 4 proves the transaction, never the reason behind it. "
                 "This is a filing, not a call."),
        "salience": 1,
    })

    packet = fold_numbers(facts)
    assert_lag_disclosed(packet)
    return packet


def candidates(
    root: Path | str | None = None,
    *,
    today: str | None = None,
    cfg: dict | None = None,
    cooled: frozenset[str] | set[str] | None = None,
    power: dict | None = None,
) -> list[dict]:
    """Load → validate → derive → classify → pack.

    `power` is `insider_power.compute()` output keyed by ticker; absent,
    candidates carry no posture context. The lane never blocks on enrichment.
    """
    if today is None:
        today = date.today().isoformat()
    df = load_insiders(root)
    if df is None:
        return []
    out: list[dict] = []
    for cand in open_market_purchases(df, today=today, cfg=cfg, cooled=cooled):
        try:
            cand["power_context"] = power_context((power or {}).get(cand["ticker"]))
        except ScoreLeakError:
            cand["power_context"] = ""
        try:
            cand["facts"] = insider_facts(cand)
        except (LagDisclosureError, ScoreLeakError):
            continue
        out.append(cand)
    return out
