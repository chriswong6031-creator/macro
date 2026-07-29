"""engine.marketing.congress_feed — congressional-disclosure post candidates (E2).

Lane 7 of the masterplan lane matrix (research/
MARKETING_CONTENT_STUDIO_LLM_FIRST_MASTERPLAN_BY_FABLE.md §10): politician
trades, daily batch, fact-locked LLM writer, OBSERVATION register, display-tier,
no calls. The editorial law is research/marketing_dockets/
CODEX_CONTENT_CASE_STUDIES_2026_07_28.md §Insider-signal post family — adopted
in OUR register (sentence case, one cashtag, no hashtag piles, no portraits).

SOURCE. ``data/quiver/congress.parquet`` (Representative, BioGuideID,
ReportDate, TransactionDate, Ticker, Transaction, Range, House, Amount, Party,
TickerType, Description, ExcessReturn, ``_first_seen``). ``_first_seen`` is OUR
crawl stamp, which is the only column that can answer "new tonight": ReportDate
is the clerk's date and a backfill can land a three-week-old ReportDate today.

THREE THINGS THIS MODULE REFUSES TO DO
--------------------------------------
1. **It never surfaces ExcessReturn.** ``engine/congress_members.py`` documents
   why in its own header: ExcessReturn accrues from TransactionDate to Quiver's
   snapshot, so a July-2025 trade carries twelve months of compounding and a
   June-2026 trade carries two weeks. It is horizon-inconsistent BY
   CONSTRUCTION — fine as an internal ranking input, a performance claim we
   cannot stand behind once printed beside a politician's name.
   :func:`member_context` therefore returns PLAIN WORDS and
   :func:`assert_no_score` proves the phrase carries no digit.

2. **It never ranks on member skill.** Skill is display-tier context (house law:
   display-tier ships freely, authority is gauntleted). Ranking is materiality
   and side, full stop — so a well-regarded member cannot buy their way onto the
   flagship with a $1,001 dividend reinvestment.

3. **It never omits the reporting lag.** The STOCK Act allows up to 45 days, and
   the site's own writing says these are not real-time signals. Every packet
   carries the gap as a WRITER-VISIBLE fact ("traded Jun 12, disclosed today") —
   enforced by :func:`assert_lag_disclosed`, which RAISES rather than warns.

SHARED PRIMITIVES. The display/rounding/whitelist helpers below are used by BOTH
filing lanes; ``insider_feed`` imports them from here rather than keeping a
second copy, because the one thing two lanes must never disagree about is how a
number is spelled.

Public API::

    lane_cfg(cfg)                              -> dict
    load_congress(root)                        -> "pd.DataFrame | None"
    parse_range(text, fallback)                -> (low, high, mid) | None
    member_context(member)                     -> str          (plain words)
    new_disclosures(df, *, today, cfg, cooled) -> list[dict]
    congress_facts(cand)                       -> dict          (FactPacket)
    assert_lag_disclosed(packet)               -> None          (raises)
    assert_no_score(text)                      -> None          (raises)
    candidates(root, *, today, cfg, cooled, member_stats) -> list[dict]

Everything except :func:`load_congress` and :func:`candidates` is a PURE
function of its arguments — no wall clock, no RNG, no I/O — so replanning the
same night twice yields the same candidates, which is the only property that
makes the lane auditable.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable

__all__ = [
    # shared filing-lane primitives
    "LagDisclosureError",
    "ScoreLeakError",
    "TOP_FACTS_VISIBLE",
    "display_date",
    "display_entity_name",
    "display_pct",
    "display_price",
    "display_tokens",
    "display_usd",
    "fold_numbers",
    "lag_days_between",
    "number_tokens",
    "parse_iso_date",
    "sentence_case",
    # congress lane
    "DEFAULTS",
    "LAG_FACT_ID",
    "lane_cfg",
    "load_congress",
    "parse_range",
    "member_context",
    "new_disclosures",
    "congress_facts",
    "assert_lag_disclosed",
    "assert_no_score",
    "candidates",
]


# ═════════════════════════════════════════════════════════════════════════════
# SHARED FILING-LANE PRIMITIVES (imported by engine.marketing.insider_feed)
# ═════════════════════════════════════════════════════════════════════════════

class LagDisclosureError(ValueError):
    """A fact packet reached the writer without a visible reporting-lag fact."""


class ScoreLeakError(ValueError):
    """A calibrated internal number tried to leave through display-tier copy."""


#: How many facts `copywriter.build_context` actually shows the writer
#: (``all_facts[:3]`` after sorting by ``(-salience, id)``). Anything ranked
#: below this is in the packet and absent from the post.
TOP_FACTS_VISIBLE = 3

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def parse_iso_date(value: Any) -> date | None:
    """``"2026-06-12"`` / ``"2026-06-12T00:00:00Z"`` / a date → ``date``. None on failure."""
    if isinstance(value, date):
        return value
    try:
        parts = str(value)[:10].split("-")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:  # noqa: BLE001
        return None


def lag_days_between(earlier: Any, later: Any) -> int | None:
    """Calendar days from *earlier* to *later*. None when either is undatable."""
    a, b = parse_iso_date(earlier), parse_iso_date(later)
    if a is None or b is None:
        return None
    return (b - a).days


def display_date(value: Any, *, with_year: bool = False) -> str:
    """``"Jun 12"`` (or ``"Jun 12, 2025"``). "" when undatable.

    Built from a month table rather than ``strftime("%b %-d")`` because the
    zero-stripping directive is platform-specific and this string ends up in
    published copy.
    """
    d = parse_iso_date(value)
    if d is None:
        return ""
    stamp = f"{_MONTHS[d.month - 1]} {d.day}"
    return f"{stamp}, {d.year}" if with_year else stamp


def display_price(value: Any) -> str:
    """A price in the W1 display register. "" when unparseable.

    Delegates to `copywriter.format_display_price` — the contract §Rounding law
    lives there and this package gets exactly one copy of it. The local fallback
    exists only so a caller that imported this module without the copywriter
    (never true in the nightly) degrades instead of raising.
    """
    try:
        from engine.marketing.copywriter import format_display_price  # noqa: PLC0415
        return format_display_price(value) or ""
    except Exception:  # noqa: BLE001
        f = _finite(value)
        if f is None:
            return ""
        s = f"{f:.0f}" if abs(f) >= 100 else (f"{f:.1f}" if abs(f) >= 10 else f"{f:.2f}")
        return s[:-2] if s.endswith(".0") else s


def display_pct(value: Any, *, signed: bool = False) -> str:
    """A percentage at one decimal, trailing ".0" stripped. "" when unparseable."""
    try:
        from engine.marketing.copywriter import format_display_pct  # noqa: PLC0415
        return format_display_pct(value, signed=signed) or ""
    except Exception:  # noqa: BLE001
        f = _finite(value)
        if f is None:
            return ""
        s = f"{f:+.1f}" if signed else f"{f:.1f}"
        return (s[:-2] if s.endswith(".0") else s) + "%"


def display_usd(value: Any) -> str:
    """``298500`` → ``"$298K"``; ``6_920_000`` → ``"$6.92M"``; ``1001`` → ``"$1,001"``.

    The MANTISSA is rounded by the same magnitude law as a price
    (:func:`display_price`), so the lane introduces no second rounding table —
    "$6.92M" and "$94.9K" are the register the corpus actually writes, and
    `copywriter.display_round_text` leaves both untouched (a suffixed token is
    not a bare decimal).

    ABBREVIATION STARTS AT 10K, not 1K, because the mantissa law pads below ten:
    $1,001 came out as "$1.00K", which is both uglier and less precise than the
    number it replaced. Under the threshold the figure is written in full.
    """
    f = _finite(value)
    if f is None:
        return ""
    sign = "-" if f < 0 else ""
    a = abs(f)
    for scale, suffix in ((1e9, "B"), (1e6, "M"), (1e4, "K")):
        if a >= scale:
            # The K leg divides by 1e3 even though it triggers at 1e4.
            return f"{sign}${display_price(a / (1e3 if suffix == 'K' else scale))}{suffix}"
    return f"{sign}${a:,.0f}"


def display_multiple(value: Any) -> str:
    """``12.01`` → ``"12x"``; ``1.83`` → ``"1.8x"``. "" when unparseable.

    The codex's own worked rewrite prefers "about a 12× increase" over
    "1,101%" — above a few hundred percent a multiple is the readable form and
    the percentage is the pedantic one. Both are emitted; the writer picks.
    """
    f = _finite(value)
    if f is None or f <= 0:
        return ""
    return f"{f:.0f}x" if f >= 10 else f"{f:.1f}x".replace(".0x", "x")


#: Name fragments that must survive title-casing an ALL-CAPS filed name.
_NAME_KEEP: dict[str, str] = {
    "LP": "LP", "L.P.": "L.P.", "LLC": "LLC", "INC": "Inc.", "INC.": "Inc.",
    "LTD": "Ltd.", "LTD.": "Ltd.", "CO": "Co.", "CO.": "Co.", "PLC": "PLC",
    "II": "II", "III": "III", "IV": "IV", "JR": "Jr.", "JR.": "Jr.",
    "SR": "Sr.", "SR.": "Sr.", "USA": "USA", "NV": "NV", "SA": "SA",
}


def display_entity_name(raw: Any) -> str:
    """A filed name or company name, de-shouted. NEVER reordered.

    Both source estates ship a mix of registers — "Alon Haggai" next to
    "ENGINEER ADIL", "Autohome" next to "ASHLAND INC." — and ALL-CAPS reads as
    shouting in a post. Caps-only strings are title-cased with entity and
    generation suffixes preserved; anything already carrying a lowercase letter
    is passed through untouched, because the codex requires the exact filed name
    and "Moriarty Thomas M" is how the filing reads.
    """
    name = str(raw or "").strip()
    if not name or any(c.islower() for c in name):
        return name
    words: list[str] = []
    for word in name.split():
        core = word.rstrip(",")
        tail = word[len(core):]
        words.append(_NAME_KEEP.get(core.upper(), core.title()) + tail)
    return " ".join(words)


def sentence_case(text: str) -> str:
    """Capitalise the first letter and leave the rest alone.

    House register is sentence case, and a lead fact composed from a lowercase
    desk phrase ("our momentum screen has …") opens a post mid-breath.
    ``str.capitalize`` cannot be used: it lowercases everything after the first
    character, which would turn every ticker in the sentence into prose.
    """
    s = str(text or "")
    return s[:1].upper() + s[1:] if s else s


def _finite(value: Any) -> float | None:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def number_tokens(text: str) -> list[str]:
    """Every token `copywriter.validate_copy` will demand a licence for.

    Uses the VALIDATOR'S OWN extractor rather than a second regex. That coupling
    is deliberate: a whitelist derived from a private copy of the pattern is a
    whitelist that drifts, and the failure mode is the writer being rejected for
    quoting its own packet verbatim. (It also catches the non-obvious cases —
    "27,270" yields the fragment "270", because the extractor's ``\\b\\d{3,6}\\b``
    arm sees the comma as a word boundary.)
    """
    try:
        from engine.marketing.copywriter import _extract_number_tokens  # noqa: PLC0415
        return list(_extract_number_tokens(str(text or "")))
    except Exception:  # noqa: BLE001
        return list(_NUMBER_FALLBACK_RE.findall(str(text or "")))


#: Last-resort mirror of `copywriter._NUMBER_RE`, used only when that import
#: fails. Kept deliberately dumb — the real one is the source of truth.
_NUMBER_FALLBACK_RE = re.compile(
    r"[+-]?\d+\.?\d*%|\d+\.?\d*x|\b\d{2,4}\.\d{2}\b|\b\d{1,4}\.\d\b|\b\d{3,6}\b")

#: A figure AS A READER SEES IT — "$298K", "25,000", "12x", "0.9%", "38".
#: Complements :func:`number_tokens`, which reports only what the VALIDATOR
#: polices. The two answer different questions and the packet needs both.
#:
#: The thousands group is `\d{1,3}(?:,\d{3})+` rather than a loose `[\d,]*`,
#: which swallowed the SENTENCE comma after a date and licensed the token
#: "26," — a whitelist entry no copy can ever legally contain.
_DISPLAY_TOKEN_RE = re.compile(
    r"(?<![\w.])\$?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[KMB]\b|%|x\b)?")


def display_tokens(text: str) -> list[str]:
    """Every figure the packet SAYS, spelled the way the copy spells it."""
    return [m.group(0) for m in _DISPLAY_TOKEN_RE.finditer(str(text or ""))]


def fold_numbers(facts: list[dict], extra: Iterable[str] = ()) -> dict:
    """``[fact, …]`` → ``{"facts": […], "numbers_whitelist": […]}``.

    Stamps each fact's ``numbers`` from ITS OWN rendered text and unions them in
    salience order, so the packet is self-consistent by construction.

    THE WHITELIST IS THE UNION OF TWO VIEWS, and it is wrong with either one
    alone. `number_tokens` reports what `validate_copy` will demand a licence
    for — which SKIPS one- and two-digit bare integers, so a packet whose only
    figures are "38 days" and "$15K" licensed literally NOTHING. The writer
    prompt hands that same list to the model as "use ONLY these numbers", so an
    empty whitelist reads as "write no numbers" and quietly strips the post of
    the facts it exists to carry. `display_tokens` reports what the copy
    actually says. Union: the validator's tokens keep the post legal, the
    display tokens make the instruction true.
    """
    ordered = sorted(
        (dict(f) for f in facts),
        key=lambda f: (-int(f.get("salience") or 0), str(f.get("id") or "")),
    )
    whitelist: list[str] = []
    for fact in ordered:
        text = str(fact.get("text") or "")
        nums: list[str] = []
        for tok in list(display_tokens(text)) + list(number_tokens(text)):
            if tok and tok not in nums:
                nums.append(tok)
            if tok and tok not in whitelist:
                whitelist.append(tok)
        fact["numbers"] = nums
    for tok in extra:
        tok = str(tok)
        if tok and tok not in whitelist:
            whitelist.append(tok)
    return {"facts": ordered, "numbers_whitelist": whitelist}


def narrow_by_day(df: Any, column: str, days: set[str]) -> Any:
    """Pre-filter a frame to rows whose *column* date-prefix is in *days*.

    Pure performance, zero semantics: the row-wise filters below re-check the
    same condition, so a frame that cannot be masked is returned untouched. It
    matters because the congress parquet is ~100k rows and the insider parquet
    ~40k, and the lane wants the ~dozen the crawler added tonight.
    """
    try:
        return df[df[column].astype(str).str[:10].isin(days)]
    except Exception:  # noqa: BLE001
        return df


def clean_record(rec: dict) -> dict:
    """One parquet row as plain Python, with every flavour of NA → None.

    pandas hands back three different absences from one frame — ``float('nan')``
    from numeric columns, ``pd.NA`` from the string dtype, ``NaT`` from
    datetimes — and ``str(pd.NA)`` is the perfectly truthy ``"<NA>"``, which is
    how an unnamed representative becomes a post about "<NA>".
    """
    out: dict[str, Any] = {}
    for key, value in rec.items():
        if value is None:
            out[key] = None
            continue
        try:
            if value != value:  # NaN / NaT
                out[key] = None
                continue
        except Exception:  # noqa: BLE001 — pd.NA comparisons are ambiguous
            out[key] = None
            continue
        out[key] = None if str(value) in ("<NA>", "NaT", "nan", "None") else value
    return out


def records(df: Any) -> list[dict]:
    """DataFrame → cleaned dicts. The one place pandas types leave a frame."""
    try:
        return [clean_record(rec) for rec in df.to_dict("records")]
    except Exception:  # noqa: BLE001
        return []


# ═════════════════════════════════════════════════════════════════════════════
# CONGRESS LANE
# ═════════════════════════════════════════════════════════════════════════════

#: Repo-relative source. Read-only — this lane never writes to `data/`.
_CONGRESS_REL = Path("data") / "quiver" / "congress.parquet"

#: The fact id every packet must carry inside the writer-visible top three.
LAG_FACT_ID = "congress_report_lag"

#: Config defaults (`config/marketing.yml` → `congress_lane:`). In-code floor so
#: a caller shipping no config still gets the safe lane, not a firehose.
DEFAULTS: dict[str, Any] = {
    # SHIP ENABLED (operator 2026-07-29: the lanes go live). Enabling a SUPPLY
    # lane is not enabling a publisher — the outbox approval gate is what still
    # stands between a candidate and a timeline.
    "enabled": True,
    #: Fleet-wide cap per day. Two is a lane; five is a newsletter.
    "max_per_day": 2,
    #: Materiality floor on the DISCLOSED RANGE MIDPOINT. 73,206 of 99,585 rows
    #: sit in the $1,001–$15,000 bucket — that bucket IS the noise floor.
    "min_amount_usd": 50_000.0,
    #: Sales stay eligible but always rank below purchases: a sale has a dozen
    #: innocent explanations (tax, divorce, blind trust), a purchase spends money.
    "include_sales": True,
    #: 0 = strictly rows first seen TODAY. 1 also admits yesterday's crawl, for
    #: the nights the collector lands the far side of the UTC boundary.
    "first_seen_lookback_days": 1,
    #: A trade disclosed later than this is a filing-compliance story, not a
    #: market one. The STOCK Act window is 45 days; 90 keeps late filers in
    #: scope while cutting ancient amendments.
    "max_report_lag_days": 90,
}

#: Descriptions that are NOT a discretionary decision. Dividend reinvestment is
#: a standing instruction — publishing it as "bought" is the same class of error
#: as the codex's "a grant counted as a purchase".
_EXCLUDED_DESCRIPTIONS: tuple[str, ...] = ("dividend reinvestment", "automatic", "exchange")

#: TickerType values that are not the common stock the post would name.
_EXCLUDED_TICKER_TYPES: tuple[str, ...] = ("option", "other")

#: US common-stock ticker shape (BF-B and BRK-B keep their hyphen).
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")

#: Any digit — the tripwire for :func:`assert_no_score`.
_DIGIT_RE = re.compile(r"\d")

#: Money tokens inside a Range string ("$1,001 - $15,000").
_MONEY_RE = re.compile(r"\$?\s*([\d,]+(?:\.\d+)?)")

#: Internal tier slugs from `engine.congress_members` mapped to plain words.
#: This mapping is their ONLY exit: the doctrine bans internal state names and
#: raw slugs from user-facing copy, and "proven"/"watch"/"limited" are both.
_TIER_WORDS: dict[str, str] = {
    "proven": "has one of the chamber's better-documented disclosure records",
    "watch": "has only a short disclosure history to read from",
    "limited": "has too little disclosed history to judge by",
}


def lane_cfg(cfg: dict | None) -> dict[str, Any]:
    """Resolved `congress_lane` block — defaults filled, types coerced."""
    block = ((cfg or {}).get("congress_lane") or {}) if isinstance(cfg, dict) else {}
    out = dict(DEFAULTS)
    if isinstance(block, dict):
        for key in DEFAULTS:
            if block.get(key) is not None:
                out[key] = block[key]
    out["enabled"] = bool(out["enabled"])
    out["include_sales"] = bool(out["include_sales"])
    for key in ("max_per_day", "first_seen_lookback_days", "max_report_lag_days"):
        try:
            out[key] = max(int(out[key]), 0)
        except (TypeError, ValueError):
            out[key] = DEFAULTS[key]
    try:
        out["min_amount_usd"] = max(float(out["min_amount_usd"]), 0.0)
    except (TypeError, ValueError):
        out["min_amount_usd"] = DEFAULTS["min_amount_usd"]
    return out


def load_congress(root: Path | str | None = None) -> Any:
    """The congress parquet, or None when missing/unreadable.

    Fail-soft on purpose: an absent alt-data file costs the nightly this lane
    and nothing else (same contract as `confluence_source.load_confluence`).
    """
    try:
        import pandas as pd  # noqa: PLC0415
        path = (Path(root) if root is not None else Path(".")) / _CONGRESS_REL
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        return df if len(df) else None
    except Exception:  # noqa: BLE001
        return None


def parse_range(text: Any, fallback: Any = None) -> tuple[float, float, float] | None:
    """``"$50,001 - $100,000"`` → ``(50001.0, 100000.0, 75000.5)``.

    A single-value Range ("$2,722.50") returns it as both bounds. An empty or
    unparseable Range falls back to the `Amount` column, where Quiver stores the
    range's LOW bound as a string — a floor rather than a midpoint, so a row that
    reaches the materiality gate through the fallback is understated, never
    overstated. None when nothing parses.
    """
    nums: list[float] = []
    for raw in _MONEY_RE.findall(str(text or "")):
        try:
            nums.append(float(raw.replace(",", "")))
        except (TypeError, ValueError):
            continue
    if not nums:
        try:
            v = float(str(fallback).replace(",", "").replace("$", ""))
        except (TypeError, ValueError):
            return None
        return (v, v, v) if v > 0 else None
    if len(nums) == 1:
        return (nums[0], nums[0], nums[0])
    low, high = min(nums[0], nums[1]), max(nums[0], nums[1])
    return (low, high, (low + high) / 2.0)


def assert_no_score(text: str) -> None:
    """Raise :class:`ScoreLeakError` when *text* carries a digit.

    Deliberately blunt. "39.3% hit rate", "tier 2" and "quality 0.71" are one
    defect — a calibrated internal number wearing display-tier clothes — and
    every spelling of it contains a digit. Plain words do not.
    """
    if _DIGIT_RE.search(str(text or "")):
        raise ScoreLeakError(
            f"member context must be plain words, never a score: {text!r}")


def member_context(member: Any) -> str:
    """Plain-word record context completing "<Name> …", or "" when we have none.

    *member* is a `congress_members.MemberStats` (or any dict/object carrying
    ``tier``). Never a rate, never a tier slug, never the word "validated"
    (CI-guarded house law), never a claim the horizon problem cannot support.
    """
    if member is None:
        return ""
    get = member.get if isinstance(member, dict) else (
        lambda k, d=None: getattr(member, k, d))
    phrase = _TIER_WORDS.get(str(get("tier", "") or "").strip().lower())
    if not phrase:
        return ""
    assert_no_score(phrase)
    return phrase


def _side(transaction: Any) -> str | None:
    """"purchase" / "sale", or None for exchanges and everything unrecognised."""
    t = str(transaction or "").strip().lower()
    if t.startswith("purchase"):
        return "purchase"
    if t.startswith("sale"):
        return "sale"
    return None


def _is_senate(house: Any) -> bool:
    return str(house or "").strip().lower().startswith("sen")


def new_disclosures(
    df: Any,
    *,
    today: str,
    cfg: dict | None = None,
    cooled: frozenset[str] | set[str] | None = None,
) -> list[dict]:
    """Tonight's postable disclosures, best first, capped at `max_per_day`.

    Ordering is (purchases before sales, larger midpoint first, then ticker and
    representative) — a total order with no RNG and no wall clock, so two runs
    of the same night agree.

    `cooled` is the ledger cooldown from `content_studio.cooled_tickers`. A name
    a desk posted inside the window DEFERS here rather than being dropped
    downstream, because a filing lane that spends its two daily slots on cooled
    names is a lane that publishes nothing.
    """
    lane = lane_cfg(cfg)
    if not lane["enabled"] or df is None:
        return []
    today_d = parse_iso_date(today)
    if today_d is None:
        return []
    allowed_days = {
        date.fromordinal(today_d.toordinal() - back).isoformat()
        for back in range(lane["first_seen_lookback_days"] + 1)
    }
    blocked = {str(t).upper() for t in (cooled or ())}

    picks: list[dict] = []
    for row in records(narrow_by_day(df, "_first_seen", allowed_days)):
        if str(row.get("_first_seen") or "")[:10] not in allowed_days:
            continue

        ticker = str(row.get("Ticker") or "").strip().upper()
        if not ticker or not _TICKER_RE.match(ticker) or ticker in blocked:
            continue
        if any(bad in str(row.get("TickerType") or "").lower() for bad in _EXCLUDED_TICKER_TYPES):
            continue
        if any(bad in str(row.get("Description") or "").lower() for bad in _EXCLUDED_DESCRIPTIONS):
            continue

        side = _side(row.get("Transaction"))
        if side is None or (side == "sale" and not lane["include_sales"]):
            continue

        rng = parse_range(row.get("Range"), row.get("Amount"))
        if rng is None or rng[2] < lane["min_amount_usd"]:
            continue

        tx_d = parse_iso_date(row.get("TransactionDate"))
        rd_d = parse_iso_date(row.get("ReportDate"))
        lag = lag_days_between(tx_d, rd_d)
        # FAIL CLOSED on an undatable row. The lag sentence is not decoration —
        # it is the honesty the lane exists to carry — so a row we cannot date
        # is a row we cannot post.
        if lag is None or lag < 0 or lag > lane["max_report_lag_days"]:
            continue

        name = str(row.get("Representative") or "").strip()
        if not name:
            continue

        picks.append({
            "ticker": ticker,
            "representative": name,
            "title": "Sen." if _is_senate(row.get("House")) else "Rep.",
            "chamber": "Senate" if _is_senate(row.get("House")) else "House",
            "party": str(row.get("Party") or "").strip().upper()[:1],
            "bio_guide_id": str(row.get("BioGuideID") or "").strip(),
            "side": side,
            "transaction_date": tx_d.isoformat() if tx_d else "",
            "report_date": rd_d.isoformat() if rd_d else "",
            "lag_days": lag,
            "amount_low": rng[0],
            "amount_high": rng[1],
            "amount_mid": rng[2],
            "range_label": str(row.get("Range") or "").strip(),
            "member_context": "",
            "source": "congress",
        })

    picks.sort(key=lambda c: (
        0 if c["side"] == "purchase" else 1,
        -c["amount_mid"],
        c["ticker"],
        c["representative"],
    ))

    # One disclosure per ticker per night: two members buying the same name is
    # one fact about that name, not two posts.
    seen: set[str] = set()
    out: list[dict] = []
    for cand in picks:
        if cand["ticker"] in seen:
            continue
        seen.add(cand["ticker"])
        out.append(cand)
    return out[: lane["max_per_day"]]


def assert_lag_disclosed(packet: dict) -> None:
    """Raise :class:`LagDisclosureError` unless the lag fact is WRITER-VISIBLE.

    Presence is not enough. `copywriter.build_context` hands the writer
    ``all_facts[:3]`` after sorting by ``(-salience, id)``; a lag fact ranked
    fourth is in the packet, absent from the prompt, and absent from the post.
    The guard therefore checks RANK — the defect it exists to catch is a fact
    that is technically present and practically invisible.
    """
    facts = list((packet or {}).get("facts") or [])
    ordered = sorted(facts, key=lambda f: (-int(f.get("salience") or 0), str(f.get("id") or "")))
    visible = [str(f.get("id") or "") for f in ordered[:TOP_FACTS_VISIBLE]]
    if LAG_FACT_ID not in visible:
        raise LagDisclosureError(
            f"congress packet must carry {LAG_FACT_ID!r} inside the top "
            f"{TOP_FACTS_VISIBLE} facts by salience; visible ids were {visible}")


def congress_facts(cand: dict) -> dict:
    """FactPacket for one disclosure: ``{facts, numbers_whitelist}``.

    Shape matches `chart_facts` / `market_facts` / `movers_source.mover_facts`
    exactly, so `copywriter.build_context` consumes it with no special case.
    Every number is written in the W1 display register AT PACKET BUILD (contract
    §Rounding), and the whitelist is derived from the rendered text by the
    validator's own extractor, so the writer cannot be rejected for quoting its
    own packet.
    """
    ticker = str(cand.get("ticker") or "")
    name = str(cand.get("representative") or "")
    title = str(cand.get("title") or "Rep.")
    side = str(cand.get("side") or "purchase")
    lag = int(cand.get("lag_days") or 0)
    low, high = display_usd(cand.get("amount_low")), display_usd(cand.get("amount_high"))

    tx_d, rd_d = parse_iso_date(cand.get("transaction_date")), parse_iso_date(cand.get("report_date"))
    straddles = bool(tx_d and rd_d and tx_d.year != rd_d.year)
    tx_disp = display_date(tx_d, with_year=straddles)
    rd_disp = display_date(rd_d)

    verb = "bought" if side == "purchase" else "sold"
    # The disclosed RANGE is the disclosure's real precision. Writing it as a
    # range rather than collapsing to the midpoint is the honest register, and
    # it removes the temptation to print a dollar figure nobody ever filed.
    if low and high and low != high:
        size = f"somewhere between {low} and {high} of"
    elif low:
        size = f"about {low} of"
    else:
        size = "a disclosed amount of"

    facts: list[dict] = [
        {
            "id": "congress_trade",
            "text": f"{title} {name} {verb} {size} {ticker}.",
            "salience": 10,
        },
        {
            # THE LAG FACT — mandatory, ranked to survive the top-three cut.
            "id": LAG_FACT_ID,
            "text": (
                f"The trade happened {tx_disp}; it only became public {rd_disp}, "
                f"{lag} {'day' if lag == 1 else 'days'} later. "
                f"Congressional filings always run behind the tape."
            ),
            "salience": 9,
        },
    ]

    phrase = str(cand.get("member_context") or "").strip()
    if phrase:
        assert_no_score(phrase)
        facts.append({
            "id": "congress_member_record",
            "text": f"{name} {phrase}.",
            "salience": 8,
        })

    facts.append({
        "id": "congress_disclosure_note",
        "text": ("A disclosure names the trade, never the reason for it. "
                 "This is a filing, not a call."),
        "salience": 2,
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
    member_stats: dict | None = None,
    exclude: frozenset[str] | set[str] | None = None,
) -> list[dict]:
    """Load → filter → enrich → pack. Candidates come back with `facts` attached.

    `member_stats` is `congress_members.compute(df)` output keyed by BioGuideID;
    absent, candidates simply carry no record context — the lane never blocks on
    an enrichment source.

    `exclude` is the set of tickers the plan has ALREADY claimed tonight (same
    contract as `house_picks.house_picks`). Without it a desk could carry a
    Prophet signal on NVDA and a congressional disclosure on NVDA in the same
    evening — two posts, one name, from one account, which reads as a campaign
    rather than as two independent facts. Merged into `cooled` because both are
    the same predicate at this layer: a ticker this lane may not use tonight.
    """
    if today is None:
        today = date.today().isoformat()
    df = load_congress(root)
    if df is None:
        return []
    blocked = frozenset(cooled or ()) | frozenset(exclude or ())
    out: list[dict] = []
    for cand in new_disclosures(df, today=today, cfg=cfg, cooled=blocked):
        try:
            cand["member_context"] = member_context(
                (member_stats or {}).get(cand.get("bio_guide_id")))
        except ScoreLeakError:
            cand["member_context"] = ""
        try:
            cand["facts"] = congress_facts(cand)
        except (LagDisclosureError, ScoreLeakError):
            # A packet that cannot carry its own honesty is DROPPED, never
            # published bare.
            continue
        out.append(cand)
    return out
