"""tests/test_prophet_origination_disclosure.py — the reconstructed-plan disclosure.

research/PROPHET_OUTAGE_BACKFILL_2026_08.md §0.10 (plain-word bilingual disclosure) and
§0.6c (the record must let a reader SPLIT the cohort).

WHAT IS ACTUALLY BEING DEFENDED. The operator's force-majeure replay mints US Prophet
plans stamped ``origination_mode: "outage_backfill_2026_08_09"``. Those rows must tell a
reader — in EN and in ZH, in plain words — that the pick was rebuilt after an outage
rather than originated live, and must never say so in the internal vocabulary of the
event ("backfill", "mixed vintage", "force majeure", the era literal, the mode slug).

THE SAFETY PROPERTY THIS SUITE EXISTS FOR. Zero such rows exist today. Every key in this
feature is ABSENT rather than zero/null when nothing was reconstructed, so shipping it is
a no-op: ``test_the_shelf_is_byte_identical_when_nothing_was_reconstructed`` pins the
rendered page character-for-character against the same page built without the feature's
context key at all. If that test ever fails, this PR started changing today's site.

BROWSER-FREE, like its sibling test_prophet_whynot_receipts.py and for the same reason:
the CI packs install a minimal dependency set, so an importorskip("playwright") here
would SKIP in CI and report green while proving nothing. The design measurements that
need a browser (both themes, both languages, the two adjacent dotted receipts) were made
against a synthetic 2-reconstructed + 2-live index and are attached to the PR.
"""
from __future__ import annotations

import sys
from pathlib import Path

import jinja2
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.prophet_bridge import (  # noqa: E402
    RECONSTRUCTED_CHIP,
    RECONSTRUCTED_ORIGINATION_PREFIX,
    is_reconstructed,
    origination_disclosure,
    origination_note,
    refusal_receipts,
)

BACKFILL_MODE = "outage_backfill_2026_08_09"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _plan(pid: str, *, mode: str | None = BACKFILL_MODE,
          recorded_at: str | None = "2026-08-09", closed: bool = False) -> dict:
    """One published index row, only the fields the disclosure reads."""
    row: dict = {"id": pid, "asset": pid.split("-")[0], "closed": closed,
                 "recorded_at": recorded_at}
    if mode is not None:
        row["origination_mode"] = mode
    return row


def _board(*tickers: str) -> dict:
    """A us_standouts buy lane whose rows all earn a refusal receipt, so the shelf draws."""
    return {"buy": [{"ticker": t, "name": f"{t} Industries", "dir": "up",
                     "entry_signal": {"status": "buy_soon"},
                     "conviction": {"band": "high"},
                     "signal": {"tier_cascade": "T1"},
                     "prophet": {"score": 50.0}} for t in tickers]}


def _env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    env.filters["min"] = lambda seq: min(seq)
    from engine import i18n  # noqa: PLC0415 — same import site as build_site.py
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    return env


def _shelf(cx) -> str:
    return str(_env().get_template("_prophet_receipts.html.j2").module.pvr_shelf(cx))


# --------------------------------------------------------------------------- #
# 1. The predicate — what counts as reconstructed
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("row", [
    None, {}, {"origination_mode": None}, {"origination_mode": ""},
    {"origination_mode": "live"}, {"origination_mode": "nightly"},
    # A near-miss that must NOT match: the prefix is anchored at the start, so an
    # unrelated mode merely CONTAINING the word is still a live plan.
    {"origination_mode": "live_after_outage_backfill_repair"},
    "not-a-mapping", 7,
])
def test_a_plan_that_is_not_stamped_is_not_reconstructed(row):
    assert is_reconstructed(row) is False
    assert origination_note(row) is None


@pytest.mark.parametrize("mode", [
    BACKFILL_MODE,
    # PREFIX, not equality: a second (hopefully never) replay dated differently must be
    # disclosed by this same code rather than ship silently as a live pick.
    "outage_backfill_2027_01_02",
    RECONSTRUCTED_ORIGINATION_PREFIX,
])
def test_the_outage_prefix_marks_a_row_reconstructed(mode):
    assert is_reconstructed({"origination_mode": mode}) is True


# --------------------------------------------------------------------------- #
# 2. The per-row note — chip (Tier 1) + receipt (Tier 2), bilingual
# --------------------------------------------------------------------------- #

def test_the_row_note_is_a_bilingual_chip_with_a_bilingual_receipt():
    note = origination_note(_plan("AVGO-BULL-20260809"))
    assert note is not None
    assert note["en"] == RECONSTRUCTED_CHIP[0] and note["zh"] == RECONSTRUCTED_CHIP[1]
    # Every EN string ships with its ZH pair — house law, and the reason a renderer can
    # draw this row in either language without knowing what it says.
    for en_key, zh_key in (("en", "zh"), ("tip_en", "tip_zh")):
        assert note[en_key] and note[zh_key]
        assert note[en_key] != note[zh_key]
    # ZH is real ZH, not an English string wearing a zh key.
    assert any("一" <= ch <= "鿿" for ch in note["zh"])
    assert any("一" <= ch <= "鿿" for ch in note["tip_zh"])


def test_the_receipt_names_the_origination_date_at_full_precision():
    """Law 3: the date is the day every window is graded from — it must be readable."""
    note = origination_note(_plan("X-BULL", recorded_at="2026-08-09"))
    assert "9 Aug 2026" in note["tip_en"]
    assert "2026年8月9日" in note["tip_zh"]
    assert note["date_en"] == "9 Aug 2026" and note["date_zh"] == "2026年8月9日"


def test_the_receipt_answers_the_three_questions_a_reader_has():
    """Why it exists, what it was rebuilt from and when, how the record treats it."""
    tip = origination_note(_plan("X-BULL"))["tip_en"].lower()
    assert "didn't finish" in tip                 # why there is no live pick
    assert "rebuilt" in tip and "9 aug 2026" in tip  # from what, and when
    assert "record" in tip                        # how it is counted


@pytest.mark.parametrize("bad", [None, "", "not-a-date", "2026-13-09", "20260809"])
def test_an_unreadable_date_ships_the_chip_with_no_receipt(bad):
    """FAIL-SOFT: a chip with no hover, never a hover with a blank or wrong day."""
    note = origination_note(_plan("X-BULL", recorded_at=bad))
    assert note["en"] == RECONSTRUCTED_CHIP[0]
    assert "tip_en" not in note and "tip_zh" not in note


# --------------------------------------------------------------------------- #
# 3. The board-level disclosure — absent, never zero
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("rows", [
    None, [], [_plan("A-BULL", mode=None)], [_plan("A-BULL", mode="live")],
])
def test_no_board_disclosure_at_all_when_nothing_was_reconstructed(rows):
    assert origination_disclosure(rows) is None


def test_the_board_disclosure_counts_only_the_reconstructed_rows():
    d = origination_disclosure([
        _plan("A-BULL"), _plan("B-BULL"),
        _plan("C-BULL", mode=None), _plan("D-BULL", mode="live"),
    ])
    assert d["n"] == 2
    assert d["date"] == "2026-08-09"
    assert "2 of the plans now running were reconstructed after an outage" == d["en"]
    assert any("一" <= ch <= "鿿" for ch in d["zh"])


def test_english_singular_and_plural_agree():
    one = origination_disclosure([_plan("A-BULL")])["en"]
    two = origination_disclosure([_plan("A-BULL"), _plan("B-BULL")])["en"]
    assert one.startswith("1 of the plans now running was ")
    assert two.startswith("2 of the plans now running were ")


def test_the_count_names_its_population_rather_than_implying_one():
    """Design fix, pinned.

    On the US board this clause lands one line under "N more already have a plan
    running". A bare "N running plans were reconstructed" reads as "N OF THOSE", which
    is false — the count is over EVERY open plan. Naming the population removes it.
    """
    en = origination_disclosure([_plan("A-BULL")])["en"]
    assert "of the plans now running" in en


def test_the_earliest_origination_date_is_the_one_reported():
    d = origination_disclosure([
        _plan("A-BULL", recorded_at="2026-08-12"),
        _plan("B-BULL", recorded_at="2026-08-09"),
    ])
    assert d["date"] == "2026-08-09" and "9 Aug 2026" in d["tip_en"]


# --------------------------------------------------------------------------- #
# 4. The rendered surface — the US board's prophet shelf footnote
# --------------------------------------------------------------------------- #

def _cx(reconstructed):
    return refusal_receipts(_board("AAA", "BBB", "CCC"), open_keys=("DDD-BULL",),
                            reconstructed_plans=reconstructed)


def test_the_shelf_is_byte_identical_when_nothing_was_reconstructed():
    """THE SAFETY PROPERTY. Zero reconstructed rows ⇒ today's page, unchanged.

    Compared against a context with the key REMOVED entirely — i.e. what the shelf saw
    before this feature existed — so the assertion is "no rendered difference", not
    merely "the count says 0".
    """
    live_only = _cx([_plan("A-BULL", mode=None), _plan("B-BULL", mode="live")])
    assert "reconstructed" not in live_only, "absent, never zero"
    before = dict(live_only)
    before.pop("reconstructed", None)
    assert _shelf(live_only) == _shelf(before)


def test_the_clause_renders_in_both_languages_with_both_hovers():
    html = _shelf(_cx([_plan("A-BULL"), _plan("B-BULL")]))
    assert "pvr-recon" in html
    assert "2 of the plans now running were reconstructed after an outage" in html
    assert "在跑的计划中有 2 只是中断后补记的" in html
    assert 'data-tip-en="The nightly run didn' in html
    assert "data-tip-zh=" in html
    # Both language halves present — the l-en/l-zh pair is how the page swaps.
    assert html.count('class="l-en"') == html.count('class="l-zh"')


def test_the_clause_rides_the_existing_footnote_and_adds_no_second_one():
    """Doctrine Law 4: one footnote per panel, merged — never a second stamp."""
    html = _shelf(_cx([_plan("A-BULL")]))
    assert html.count('class="pvr-ft"') == 1
    ft = html.split('class="pvr-ft"', 1)[1]
    assert "pvr-recon" in ft, "the clause must sit inside the one merged footnote"


def test_the_separator_sits_outside_the_hover_span():
    """Design fix, pinned.

    Rendered side by side, the era clause's dotted rule and this one ran together
    THROUGH the " · " and read as a single receipt spanning both. The separator now
    precedes the span, so the two hovers are visibly two.
    """
    html = _shelf(_cx([_plan("A-BULL")]))
    head, _, tail = html.partition('<span class="pvr-recon"')
    assert head.rstrip().endswith("·"), "separator must precede the span"
    assert not tail.split(">", 1)[1].lstrip().startswith("·")


def test_a_clause_without_a_receipt_carries_no_dotted_tell():
    """The underline is gated on [data-tip-en]: no promise of a hover that isn't there."""
    html = _shelf(_cx([_plan("A-BULL", recorded_at=None)]))
    assert "pvr-recon" in html
    assert "data-tip-en" not in html.split('class="pvr-recon"', 1)[1].split(">", 1)[0]
    css = str(_env().get_template("_prophet_receipts.html.j2").module.pvr_css())
    assert ".pvr-recon[data-tip-en]" in css


def test_the_clause_carries_no_title_attribute():
    """CI-guarded house law: no translated text in `title=`. Hovers are data-tip-*."""
    assert "title=" not in _shelf(_cx([_plan("A-BULL"), _plan("B-BULL")]))


# --------------------------------------------------------------------------- #
# 5. Vocabulary — §0.10's own ban, enforced on every string this feature can emit
# --------------------------------------------------------------------------- #

#: Never front-facing. Three families:
#:   · §0.10's named ban — the internal name of this event in any of its forms,
#:   · the operator's standing verdict/refutation ban (2026-07-27), and
#:   · the doctrine's Law 2 staples (era literals, machine slugs, bare stats).
BANNED = (
    "backfill", "back-fill", "补录",           # the event's internal name
    "mixed vintage", "mixed_vintage", "混合",
    "force majeure", "force-majeure", "不可抗力",
    "origination_mode", "outage_backfill", "anticipation-v1",
    "selection_era", "recorded_at", "display-tier", "display tier",
    "falsifier", "refuted", "证伪", "invalidated", "quarantine",
    "validated", "n=", "z-score", "base rate",
)


def _every_user_string() -> list[str]:
    """Every string this feature can put in front of a reader, in both languages."""
    note = origination_note(_plan("A-BULL"))
    disclosure = origination_disclosure([_plan("A-BULL"), _plan("B-BULL")])
    from scripts.build_prophet import record_summary  # noqa: PLC0415
    record = record_summary(
        [{"id": "A-BULL", "outcome": "T1_HIT", "stock_result_pct": 4.2,
          "recorded_at": "2026-08-09"}],
        set(), {"A-BULL"},
    )
    return [
        *(v for v in note.values() if isinstance(v, str)),
        *(v for v in disclosure.values() if isinstance(v, str)),
        record["reconstructed_note"], record["reconstructed_note_zh"],
    ]


def test_the_copy_leaks_no_banned_vocabulary():
    for text in _every_user_string():
        lowered = text.lower()
        for word in BANNED:
            assert word.lower() not in lowered, f"{word!r} leaked into {text!r}"


def _rendered_clause() -> str:
    """Just the reconstructed clause — markup, copy and hovers, nothing around it.

    SCOPED ON PURPOSE, and the first run of this suite is why. Asserted over the whole
    shelf it failed on ``anticipation-v1-2026-08-08``, which is the ERA clause's Tier-2
    hover — a separately ratified receipt whose literal the doctrine deliberately puts
    on hover (§2 Law 5). Banning it shelf-wide would have made this suite demand the
    removal of copy another ruling requires. A banned list belongs to the copy it was
    written for; this one belongs to §0.10's clause.
    """
    html = _shelf(_cx([_plan("A-BULL"), _plan("B-BULL")]))
    assert '<span class="pvr-recon"' in html
    return html.split('<span class="pvr-recon"', 1)[1].split("</span>\n", 1)[0]


def test_the_rendered_clause_leaks_no_banned_vocabulary():
    clause = _rendered_clause().lower()
    for word in BANNED:
        if word in ("quarantine", "invalidated", "n="):
            continue  # not emittable by this clause; covered on the strings above
        assert word.lower() not in clause, word


def test_the_mode_slug_never_reaches_the_dom():
    """The machine identifier stays in the JSON so a reader CAN split — never in HTML."""
    html = _shelf(_cx([_plan("A-BULL")]))
    assert BACKFILL_MODE not in html
    assert RECONSTRUCTED_ORIGINATION_PREFIX not in html


def test_the_copy_makes_no_claim_about_what_to_do():
    """No stance clause, deliberately.

    How a pick was originated does not change what to do about it today, and the row's
    stance is already the card's whole point. A verb here would either duplicate that
    stance or contradict it — both are the false claim this disclosure exists to avoid.
    """
    for text in _every_user_string():
        lowered = text.lower()
        for verb in ("buy", "sell", "avoid", "don't chase", "act now",
                     "买入", "卖出", "回避", "追高"):
            assert verb not in lowered, f"{verb!r} is a stance, in {text!r}"


# --------------------------------------------------------------------------- #
# 6. The record — §0.6c split, with the rate untouched
# --------------------------------------------------------------------------- #

def _ledger():
    return [
        {"id": "R1", "outcome": "T1_HIT", "stock_result_pct": 8.0,
         "recorded_at": "2026-08-09"},
        {"id": "R2", "outcome": "INVALIDATED", "stock_result_pct": -3.0,
         "recorded_at": "2026-08-09"},
        {"id": "L1", "outcome": "T2_HIT", "stock_result_pct": 12.0,
         "recorded_at": "2026-07-20"},
        {"id": "L2", "outcome": "NO_ENTRY", "stock_result_pct": None,
         "recorded_at": "2026-07-21"},
    ]


def test_the_record_splits_the_cohort_without_moving_the_rate():
    """§0.6c is a SPLIT, not a fourth exclusion.

    A reconstructed plan was graded by the nightly on its own real bars — the replay
    never writes the ledger — so its outcome is as honest as any other row's. Dropping
    it would be its own distortion; what a reader is owed is the count that lets them
    take it out downstream.
    """
    from scripts.build_prophet import record_summary  # noqa: PLC0415
    plain = record_summary(_ledger(), set())
    split = record_summary(_ledger(), set(), {"R1", "R2"})
    for key in ("n_rows_total", "n_quarantined", "n_no_entry", "n_scored",
                "n_wins", "win_rate", "avg_result_pct"):
        assert plain[key] == split[key], f"{key} moved — the rate must not change"
    assert split["n_reconstructed"] == 2
    assert split["reconstructed_ids"] == ["R1", "R2"]


def test_the_record_note_is_bilingual_and_names_the_outage_date():
    from scripts.build_prophet import record_summary  # noqa: PLC0415
    rec = record_summary(_ledger(), set(), {"R1", "R2"})
    assert "2 of these were reconstructed after an outage on 9 Aug 2026" in \
        rec["reconstructed_note"]
    assert "2026年8月9日" in rec["reconstructed_note_zh"]
    # It claims a SPLIT, never an exclusion — these rows ARE in the rate above it.
    assert "counted here" in rec["reconstructed_note"]
    assert "已计入" in rec["reconstructed_note_zh"]


def test_the_record_counts_over_the_scored_rows_it_sits_beside():
    """"N of these" must mean N of the number printed next to it, not of a wider set."""
    from scripts.build_prophet import record_summary  # noqa: PLC0415
    # L2 is NO_ENTRY: never scored, so a reconstructed L2 is not "one of these".
    rec = record_summary(_ledger(), set(), {"R1", "L2"})
    assert rec["n_reconstructed"] == 1 and rec["reconstructed_ids"] == ["R1"]


def test_the_record_omits_the_split_keys_entirely_when_none_were_reconstructed():
    from scripts.build_prophet import record_summary  # noqa: PLC0415
    for ids in (None, set(), {"NOT-IN-LEDGER"}):
        rec = record_summary(_ledger(), set(), ids)
        assert "n_reconstructed" not in rec
        assert "reconstructed_ids" not in rec
        assert "reconstructed_note" not in rec
    # …and the summary is exactly what it was before the parameter existed.
    assert record_summary(_ledger(), set()) == record_summary(_ledger(), set(), None)


# --------------------------------------------------------------------------- #
# 7. Wiring — the published row, and the board's read of it
# --------------------------------------------------------------------------- #

def test_build_prophet_publishes_the_note_and_keeps_the_machine_mode():
    """§0.6c: the field must SURVIVE the index render so readers can split.

    Pins the source, not a live artifact: build_prophet's index pass is a single loop
    over `active_entries`, and this asserts the three things it writes.
    """
    src = (ROOT / "scripts" / "build_prophet.py").read_text(encoding="utf-8")
    for fragment in ('_entry["origination_mode"] = _plan.get("origination_mode")',
                     '_entry["origination_note"] = _note',
                     'index["origination_disclosure"] = _origination'):
        assert fragment in src, fragment


def test_build_site_reads_reconstructed_open_plans_from_the_published_index():
    """The board's count comes from the SAME index read the open-plan set does.

    Safe for the same reason that read is: an origination mode is a settled fact about
    a plan's past, so last night's file cannot make it stale into a wrong number the
    way a refusal REASON would.
    """
    src = (ROOT / "scripts" / "build_site.py").read_text(encoding="utf-8")
    assert "reconstructed = [p for p in _open if is_reconstructed(p)]" in src
    assert "reconstructed_plans=reconstructed" in src


def test_a_reconstructed_plan_survives_a_load_write_round_trip():
    """§0.7 in miniature: the nightly must not drop the stamps it did not mint."""
    import json  # noqa: PLC0415
    plan = {"id": "A-BULL-20260809", "asset": "A", "direction": "BULL",
            "origination_mode": BACKFILL_MODE, "backfill_executed_at": "2026-08-11",
            "recorded_at": "2026-08-09"}
    reloaded = json.loads(json.dumps(plan, allow_nan=False, default=str))
    assert is_reconstructed(reloaded)
    assert reloaded["backfill_executed_at"] == "2026-08-11"
    assert origination_note(reloaded)["en"] == RECONSTRUCTED_CHIP[0]
