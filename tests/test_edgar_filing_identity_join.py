"""Wave 1B — the EDGAR identity join, proved rather than asserted.

The finding this suite exists to close (contract freeze Q2): the estate's two
EDGAR readers shared exactly ``{ticker}``.  Neither field set was a superset of
the other, so the two planes could not be joined at ANY level — and ``ticker``
is an alias with a validity window, never a durable key.

Every gate below is written so it would FAIL on the pre-Wave-1B code:

* ``test_the_committed_corpus_pairs_cannot_be_keyed_at_all`` replays the shipped
  golden-corpus fixture and shows both readers' rows raising on the way to a
  key.  That is the red.
* ``test_one_filing_read_by_both_planes_joins_on_cik_and_accession`` drives both
  readers over ONE submissions payload and joins the results.  That is the
  green.
* ``test_the_join_reads_no_date_at_all`` and its siblings pin that the green did
  not arrive via a tolerance window.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import inspect
import json
from pathlib import Path
import socket

import pytest

import collectors.edgar_earnings_8k as e8k
from engine.earnings_release import binding, filing_key as fk
from engine.marketing import edgar_earnings_wire as wire


REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS = REPO_ROOT / "tests" / "fixtures" / "company_intelligence"


# ─────────────────────────────────────────────────────────────────────────────
# The suite may not reach the network.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse every outbound socket for the whole module.

    Both readers' real rail is SEC EDGAR, which requires a declared User-Agent
    and 403s without one.  Retrieval is exercised only through the injectable
    fetch against committed fixtures, and this fence is what makes "no network"
    checkable instead of asserted.
    """

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "Wave 1B tests must not touch the network; drive the injectable "
            "fetch against the committed fixtures instead."
        )

    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def test_the_network_fence_actually_bites() -> None:
    """Non-vacuity for the fixture above: prove the fence is live here."""
    with pytest.raises(AssertionError, match="must not touch the network"):
        socket.create_connection(("data.sec.gov", 443))


# ─────────────────────────────────────────────────────────────────────────────
# One shared submissions payload — the SAME filing, seen by both readers.
# ─────────────────────────────────────────────────────────────────────────────

CIK = 63908
ORIGINAL = "0000063908-26-000067"
AMENDMENT = "0000063908-26-000071"
SAME_DAY_OTHER = "0000063908-26-000068"

SOURCE_ACCEPTANCE = "2026-08-04T21:07:14.000Z"
SOURCE_ACCEPTANCE_ISO = "2026-08-04T21:07:14Z"
AMENDMENT_ACCEPTANCE = "2026-08-05T13:02:41.000Z"

SUBMISSIONS = {
    "filings": {
        "recent": {
            # Deliberately in EDGAR's own parallel-array shape: one list per
            # field, index-aligned.  Reading them by index in five places is how
            # accessionNumber came to be read by one module and ignored by the
            # other.
            "form": ["8-K", "8-K", "8-K/A", "10-Q"],
            "accessionNumber": [ORIGINAL, SAME_DAY_OTHER, AMENDMENT, "0000063908-26-000090"],
            "filingDate": ["2026-08-04", "2026-08-04", "2026-08-05", "2026-08-10"],
            "acceptanceDateTime": [
                SOURCE_ACCEPTANCE,
                "2026-08-04T22:41:03.000Z",
                AMENDMENT_ACCEPTANCE,
                "2026-08-10T11:00:00.000Z",
            ],
            "reportDate": ["2026-06-30", "2026-06-30", "2026-06-30", "2026-06-30"],
            "items": ["2.02,9.01", "5.02", "2.02", ""],
        }
    }
}


def _submissions_json() -> str:
    return json.dumps(SUBMISSIONS)


# ─────────────────────────────────────────────────────────────────────────────
# RED — the shipped corpus pairs cannot be keyed, in either direction.
# ─────────────────────────────────────────────────────────────────────────────

def test_the_committed_corpus_pairs_cannot_be_keyed_at_all() -> None:
    payload = json.loads(
        (CORPUS / "golden_corpus_edgar_identity.v1.json").read_text(encoding="utf-8")
    )
    pairs = payload["pairs"]
    assert pairs, "no EDGAR identity pairs in the corpus"

    for row in pairs:
        collector_row = row["collector_edgar_earnings_8k_row"]
        wire_row = row["engine_edgar_earnings_wire_row"]

        with pytest.raises(fk.FilingIdentityError, match="no accession"):
            fk.filing_key_from_8k_row(collector_row)
        with pytest.raises(fk.FilingIdentityError, match="no cik"):
            fk.filing_key_from_wire_event(wire_row)

        shared = set(collector_row) & (set(wire_row) - {"when_semantics"})
        assert shared == {"ticker"}, f"{row['case_ref']} intersection drifted"

    result = fk.join_filings(
        [row["collector_edgar_earnings_8k_row"] for row in pairs],
        [row["engine_edgar_earnings_wire_row"] for row in pairs],
    )
    assert result.joined == ()
    assert len(result.unjoinable_collector) == len(pairs)
    assert len(result.unjoinable_wire) == len(pairs)


def test_unjoinable_is_reported_separately_from_unmatched() -> None:
    """A schema regression must not hide behind a coverage number."""
    result = fk.join_filings(
        [{"ticker": "MCD", "cik": CIK, "filing_date": "2026-08-04"}],
        [{"ticker": "MCD", "cik": CIK, "accession": ORIGINAL}],
    )
    assert result.joined == ()
    assert len(result.unjoinable_collector) == 1
    assert result.unmatched_collector == ()
    assert len(result.unmatched_wire) == 1
    assert result.unjoinable_wire == ()


# ─────────────────────────────────────────────────────────────────────────────
# GREEN — one filing, both readers, an exact join.
# ─────────────────────────────────────────────────────────────────────────────

def _collector_rows() -> list[dict]:
    return e8k._extract_8k_rows("MCD", CIK, SUBMISSIONS["filings"]["recent"])


def _wire_event(accession: str = ORIGINAL) -> dict:
    record = wire.submission_record(CIK, accession, fetch=lambda url: _submissions_json())
    figures = wire.Figures(
        revenue=6_500.0, revenue_label="Total revenues", eps=3.38,
        eps_label="Diluted earnings per share", table_index=0,
    )
    return wire.build_event(
        wire.Expectation(ticker="MCD", cik=CIK, session="premarket", eps_forecast=3.32),
        figures,
        when=datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc),
        accession=accession,
        cik=CIK,
        acceptance_datetime=record.acceptance_datetime,
        filing_date=record.filing_date,
        form=record.form,
    )


def test_the_collector_now_captures_the_accession_number() -> None:
    rows = _collector_rows()
    assert [row["accession"] for row in rows] == [ORIGINAL, AMENDMENT]
    assert [row["form"] for row in rows] == ["8-K", "8-K/A"]
    assert all(row["report_date"] == "2026-06-30" for row in rows)


def test_the_wire_now_emits_the_cik_and_the_filing_key() -> None:
    event = _wire_event()
    assert event["cik"] == CIK
    assert event["accession"] == ORIGINAL
    assert event["filing_key"] == f"{CIK:010d}:{ORIGINAL}"


def test_one_filing_read_by_both_planes_joins_on_cik_and_accession() -> None:
    """The gate: the same submission, read by both readers, joins exactly once."""
    collector_rows = _collector_rows()
    events = [_wire_event(ORIGINAL)]

    result = fk.join_filings(collector_rows, events)

    assert len(result.joined) == 1
    joined = result.joined[0]
    assert joined.filing_key == fk.FilingKey(cik=CIK, accession=ORIGINAL)
    assert joined.collector_row["accession"] == ORIGINAL
    assert joined.wire_event["cik"] == CIK
    # The amendment is a DIFFERENT filing and correctly finds no wire partner.
    assert len(result.unmatched_collector) == 1
    assert result.unmatched_collector[0]["accession"] == AMENDMENT
    assert result.unjoinable_collector == ()
    assert result.unjoinable_wire == ()


# ─────────────────────────────────────────────────────────────────────────────
# The join is EXACT — no date tolerance, by construction.
# ─────────────────────────────────────────────────────────────────────────────

def test_the_join_advertises_a_zero_date_tolerance() -> None:
    result = fk.join_filings([], [])
    assert result.joined_on == ("cik", "accession")
    assert "filing_date" not in result.joined_on
    assert result.date_tolerance_days == 0
    assert fk.JOIN_DATE_TOLERANCE_DAYS == 0


def test_the_join_reads_no_date_at_all() -> None:
    """Source-level refutation: a date field never reaches the key.

    A behavioural test alone could pass with a tolerance of zero days that a
    later edit widens to one.  This one fails the moment a date is read.
    """
    source = "".join(
        inspect.getsource(fn)
        for fn in (
            fk.join_filings,
            fk.filing_key_from_8k_row,
            fk.filing_key_from_wire_event,
            fk.FilingKey.__post_init__,
        )
    )
    for forbidden in ("filing_date", "filingDate", "acceptance", "timedelta", "days="):
        assert forbidden not in source, f"the join reads {forbidden!r}"


def test_two_filings_on_the_same_day_do_not_cross_join() -> None:
    """A tolerance-window join would pair these; an exact key cannot."""
    collector_rows = [
        {"ticker": "MCD", "cik": CIK, "accession": ORIGINAL, "filing_date": "2026-08-04"},
        {"ticker": "MCD", "cik": CIK, "accession": SAME_DAY_OTHER, "filing_date": "2026-08-04"},
    ]
    events = [{"ticker": "MCD", "cik": CIK, "accession": SAME_DAY_OTHER}]

    result = fk.join_filings(collector_rows, events)
    assert len(result.joined) == 1
    assert result.joined[0].filing_key.accession == SAME_DAY_OTHER
    assert [row["accession"] for row in result.unmatched_collector] == [ORIGINAL]


def test_an_amendment_does_not_join_to_its_original() -> None:
    """Same issuer, same period of report, adjacent days — still two filings."""
    result = fk.join_filings(
        [{"ticker": "MCD", "cik": CIK, "accession": ORIGINAL, "filing_date": "2026-08-04"}],
        [{"ticker": "MCD", "cik": CIK, "accession": AMENDMENT, "filing_date": "2026-08-05"}],
    )
    assert result.joined == ()
    assert len(result.unmatched_collector) == 1
    assert len(result.unmatched_wire) == 1


def test_one_digit_of_accession_is_enough_to_refuse_the_join() -> None:
    near_miss = ORIGINAL[:-1] + ("8" if ORIGINAL[-1] != "8" else "9")
    result = fk.join_filings(
        [{"ticker": "MCD", "cik": CIK, "accession": ORIGINAL}],
        [{"ticker": "MCD", "cik": CIK, "accession": near_miss}],
    )
    assert result.joined == ()


def test_the_same_accession_under_a_different_cik_does_not_join() -> None:
    result = fk.join_filings(
        [{"ticker": "MCD", "cik": CIK, "accession": ORIGINAL}],
        [{"ticker": "MCD", "cik": CIK + 1, "accession": ORIGINAL}],
    )
    assert result.joined == ()


# ─────────────────────────────────────────────────────────────────────────────
# Key normalization
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [ORIGINAL, ORIGINAL.replace("-", "")])
def test_dashed_and_undashed_accessions_are_the_same_key(raw: str) -> None:
    assert fk.normalize_accession(raw) == ORIGINAL


@pytest.mark.parametrize("raw", ["", "not-an-accession", "0000063908-26-00006", None, 12345])
def test_a_malformed_accession_is_refused_not_coerced(raw: object) -> None:
    with pytest.raises(fk.FilingIdentityError):
        fk.normalize_accession(raw)


@pytest.mark.parametrize("raw", [63908, "63908", "0000063908", "CIK0000063908"])
def test_cik_spellings_normalize_to_one_integer(raw: object) -> None:
    assert fk.normalize_cik(raw) == CIK


def test_a_boolean_is_not_a_cik() -> None:
    """``isinstance(True, int)`` is True, so True would silently become CIK 1."""
    with pytest.raises(fk.FilingIdentityError):
        fk.normalize_cik(True)


def test_the_wire_event_id_is_not_parsed_for_the_key() -> None:
    """``id`` is ``TICKER-ACCESSION``; splitting it breaks on BRK-B."""
    with pytest.raises(fk.FilingIdentityError, match="no cik"):
        fk.filing_key_from_wire_event({"id": f"BRK-B-{ORIGINAL}", "accession": ORIGINAL})


# ─────────────────────────────────────────────────────────────────────────────
# GATE 2 — the emitted acceptance timestamp is the SOURCE's.
# ─────────────────────────────────────────────────────────────────────────────

def test_the_emitted_acceptance_timestamp_is_the_sources_not_the_clock() -> None:
    frozen_now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
    event = _wire_event(ORIGINAL)

    assert event["acceptance_datetime"] == SOURCE_ACCEPTANCE_ISO
    assert event["when"] == frozen_now.strftime("%Y-%m-%dT%H:%M:%S")
    # The two clocks must be different values, or the assertion above proves
    # nothing: a processing clock that happened to equal the source would pass.
    assert event["acceptance_datetime"][:19] != event["when"][:19]
    assert event["when_semantics"] == "processing_wall_clock"
    assert event["acceptance_datetime_source"] == "sec_submissions.acceptanceDateTime"
    assert event["filing_date"] == "2026-08-04"


def test_the_provider_carries_the_source_clock_end_to_end(tmp_path: Path) -> None:
    """Same proof, through the real provider seam rather than one function."""
    pd = pytest.importorskip("pandas")
    earnings = tmp_path / "data" / "earnings"
    earnings.mkdir(parents=True)
    pd.DataFrame(
        {"next_date": ["2026-08-04"], "next_time": ["time-pre-market"], "eps_forecast": [3.32]},
        index=pd.Index(["MCD"], name="ticker"),
    ).to_parquet(earnings / "earnings.parquet")
    edgar = tmp_path / "data" / "edgar"
    edgar.mkdir(parents=True)
    (edgar / "company_tickers.json").write_text(
        json.dumps({"0": {"cik_str": CIK, "ticker": "MCD", "title": "MCDONALDS CORP"}}),
        encoding="utf-8",
    )

    # EDGAR writes the CIK zero-padded to ten digits in the entry title; the
    # feed parser requires 7-10 digits there, so a bare "63908" parses to
    # nothing and the provider reports an unreadable feed rather than a filing.
    feed = (
        '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        f"<title>8-K - MCDONALDS CORP ({CIK:010d}) (Filer)</title>"
        f'<link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/{CIK}/'
        f'{ORIGINAL.replace("-", "")}/{ORIGINAL}-index.htm"/>'
        "<updated>2026-08-04T22:00:00-04:00</updated>"
        f"<id>urn:tag:sec.gov,2008:accession-number={ORIGINAL}</id>"
        "</entry></feed>"
    )
    # The wire declines a GAAP-only print against an adjusted consensus, so the
    # exhibit carries the reconciliation it would need in the wild.
    exhibit = (
        "<html><body><p>Dollars in millions, except per share data</p><table>"
        "<tr><td>Revenues</td><td>$</td><td>6,500</td></tr>"
        "<tr><td>Earnings per share-diluted</td><td>$</td><td>3.32</td></tr>"
        "</table><p>Reconciliation of non-GAAP measures</p><table>"
        "<tr><td>Adjusted earnings per share-diluted</td><td>$</td><td>3.38</td></tr>"
        "</table></body></html>"
    )

    def router(url: str) -> str:
        if "getcurrent" in url:
            return feed
        if "submissions" in url:
            return _submissions_json()
        if url.endswith("/"):
            return '<a href="/Archives/x/exhibit991.htm">EX-99.1</a>'
        return exhibit

    provider = wire.EdgarEarningsProvider(
        root=tmp_path, fetch=router, day=date(2026, 8, 4))
    events = provider.fetch(datetime(2026, 8, 4, tzinfo=timezone.utc))

    assert len(events) == 1, provider.last_stats.as_dict()
    event = events[0]
    assert event["cik"] == CIK
    assert event["acceptance_datetime"] == SOURCE_ACCEPTANCE_ISO
    assert event["acceptance_datetime"][:19] != event["when"][:19]
    # And the event this provider emitted joins to the collector's row.
    assert len(fk.join_filings(_collector_rows(), events).joined) == 1


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-08-04T21:07:14.000Z", "2026-08-04T21:07:14Z"),
        ("2026-08-04 21:07:14", "2026-08-04T21:07:14Z"),
        ("2026-08-04T17:07:14-04:00", "2026-08-04T21:07:14Z"),
        ("", ""),
        ("not a timestamp", ""),
    ],
)
def test_source_acceptance_spellings_normalize_without_inventing_one(
    raw: str, expected: str
) -> None:
    assert binding.normalize_acceptance(raw) == expected


def test_an_absent_source_clock_is_left_empty_and_announced(capsys) -> None:
    """Never borrow the processing clock to fill a missing source clock."""
    payload = json.loads(_submissions_json())
    del payload["filings"]["recent"]["acceptanceDateTime"]
    record = wire.submission_record(CIK, ORIGINAL, fetch=lambda url: json.dumps(payload))
    assert record.confirmed_earnings is True
    assert record.acceptance_datetime == ""


# ─────────────────────────────────────────────────────────────────────────────
# GATE 5 — amendments preserve event identity; duplicates do not duplicate.
# ─────────────────────────────────────────────────────────────────────────────

def _revision(accession: str, *, form: str, accepted: str, body: str,
              supersedes: str = "", report: str = "2026-06-30") -> binding.ReleaseRevision:
    return binding.revision_from_submissions_row(
        cik=CIK,
        row={
            "accessionNumber": accession,
            "form": form,
            "filingDate": accepted[:10],
            "acceptanceDateTime": accepted,
            "reportDate": report,
        },
        source_sha256=body,
        supersedes_source_sha256=supersedes,
    )


def test_an_amendment_is_a_second_revision_of_one_event() -> None:
    original = _revision(ORIGINAL, form="8-K", accepted=SOURCE_ACCEPTANCE, body="body-a")
    amended = _revision(AMENDMENT, form="8-K/A", accepted=AMENDMENT_ACCEPTANCE,
                        body="body-b", supersedes="body-a")

    result = binding.collapse_release_events([original, amended])

    assert len(result.events) == 1, "an amendment must not mint a second event"
    event = result.events[0]
    assert event.event_key == f"{CIK:010d}|2026-06-30"
    assert len(event.revisions) == 2
    assert event.original.filing_key.accession == ORIGINAL
    assert event.current.filing_key.accession == AMENDMENT
    assert event.amended is True
    assert result.collapsed == ()
    # Both filings still resolve to the one event.
    assert result.event_for(original.filing_key) is result.event_for(amended.filing_key)


def test_a_duplicate_release_does_not_duplicate() -> None:
    original = _revision(ORIGINAL, form="8-K", accepted=SOURCE_ACCEPTANCE, body="body-a")
    same_bytes = _revision(SAME_DAY_OTHER, form="8-K",
                           accepted="2026-08-04T22:41:03.000Z", body="body-a")

    result = binding.collapse_release_events([original, same_bytes])

    assert len(result.events) == 1
    assert len(result.events[0].revisions) == 1
    assert [row.reason for row in result.collapsed] == ["identical_body_sha256"]


def test_the_same_filing_seen_twice_is_one_filing() -> None:
    original = _revision(ORIGINAL, form="8-K", accepted=SOURCE_ACCEPTANCE, body="body-a")
    result = binding.collapse_release_events([original, original])
    assert len(result.events) == 1
    assert len(result.events[0].revisions) == 1
    assert [row.reason for row in result.collapsed] == ["duplicate_filing_key"]


def test_a_filing_with_no_period_of_report_says_so_instead_of_guessing() -> None:
    lone = _revision(ORIGINAL, form="8-K", accepted=SOURCE_ACCEPTANCE,
                     body="body-a", report="")
    other = _revision(SAME_DAY_OTHER, form="8-K",
                      accepted="2026-08-04T22:41:03.000Z", body="body-b", report="")

    result = binding.collapse_release_events([lone, other])

    assert len(result.events) == 2, "no period of report means no grouping"
    assert {row.reason for row in result.ungrouped} == {"report_date_absent"}
    assert "tolerance-window join" in result.ungrouped[0].detail


# ─────────────────────────────────────────────────────────────────────────────
# The corpus's own amendment (16) and duplicate_release (14) classes.
# ─────────────────────────────────────────────────────────────────────────────

def _corpus_cases(difficulty_class: str) -> list[dict]:
    manifest = json.loads(
        (REPO_ROOT / "research" / "company_intelligence" / "GOLDEN_CORPUS_MANIFEST.json")
        .read_text(encoding="utf-8")
    )
    return [
        case for case in manifest["cases"]
        if case["difficulty_class"] == difficulty_class and case.get("document_revisions")
    ]


_FORM_FOR_KIND = {
    "release": "8-K",
    "release_amendment": "8-K/A",
    "release_duplicate": "8-K",
}


def _revisions_from_case(case: dict) -> list[binding.ReleaseRevision]:
    cik = abs(hash(case["issuer_id"])) % 9_999_999 + 1
    rows = []
    for index, revision in enumerate(case["document_revisions"]):
        rows.append(binding.revision_from_submissions_row(
            cik=cik,
            row={
                "accessionNumber": revision["accession_synthetic"],
                "form": _FORM_FOR_KIND[revision["document_kind"]],
                "filingDate": case["call_date"],
                "acceptanceDateTime": f"{case['call_date']}T{12 + index:02d}:00:00Z",
                "reportDate": case["call_date"],
            },
            source_sha256=revision["source_sha256"],
            supersedes_source_sha256=revision.get("supersedes_source_sha256") or "",
        ))
    return rows


def test_every_corpus_amendment_case_keeps_one_event() -> None:
    cases = _corpus_cases("amendment")
    assert len(cases) >= 16, f"expected the corpus's 16 amendment cases, saw {len(cases)}"
    for case in cases:
        result = binding.collapse_release_events(_revisions_from_case(case))
        assert len(result.events) == 1, case["case_id"]
        event = result.events[0]
        assert len(event.revisions) == 2, case["case_id"]
        assert event.amended is True, case["case_id"]
        assert event.original.filing_key != event.current.filing_key


def test_every_corpus_duplicate_release_case_collapses() -> None:
    cases = _corpus_cases("duplicate_release")
    assert len(cases) >= 14, f"expected the corpus's 14 duplicate cases, saw {len(cases)}"
    for case in cases:
        assert case["expected_v2_outcome"] == "duplicate_collapsed", case["case_id"]
        result = binding.collapse_release_events(_revisions_from_case(case))
        assert len(result.events) == 1, case["case_id"]
        assert len(result.events[0].revisions) == 1, case["case_id"]
        assert result.collapsed and result.collapsed[0].reason == "supersedes_without_amending"


# ─────────────────────────────────────────────────────────────────────────────
# The store keeps amendments; legacy rows still dedupe the old way.
# ─────────────────────────────────────────────────────────────────────────────

def test_the_store_no_longer_collapses_an_amendment_into_its_original() -> None:
    pd = pytest.importorskip("pandas")
    rows = _collector_rows()
    same_day = dict(rows[0])
    same_day.update({"accession": SAME_DAY_OTHER, "acceptance_datetime": "2026-08-04T22:41:03.000Z"})

    store = e8k.append_and_dedup(
        pd.DataFrame(columns=e8k.STORE_COLUMNS), rows + [same_day]
    )
    assert sorted(store["accession"]) == sorted([ORIGINAL, SAME_DAY_OTHER, AMENDMENT])
    # The old (ticker, filing_date) key would have kept ONE of the two 8-Ks
    # filed on 2026-08-04.
    same_day_rows = store[store["filing_date"] == "2026-08-04"]
    assert len(same_day_rows) == 2


def test_a_legacy_row_without_an_accession_still_dedupes_the_old_way() -> None:
    pd = pytest.importorskip("pandas")
    legacy = pd.DataFrame(
        [{"ticker": "MCD", "cik": CIK, "filing_date": "2022-10-28",
          "acceptance_datetime": "", "items": "2.02,9.01"}]
    )
    store = e8k.append_and_dedup(legacy, [
        {"ticker": "MCD", "cik": CIK, "filing_date": "2022-10-28",
         "acceptance_datetime": "2022-10-28T20:00:00Z", "items": "2.02,9.01"},
    ])
    assert len(store) == 1
    assert store.iloc[0]["accession"] == ""


def test_a_keyed_row_supersedes_the_legacy_row_it_upgrades() -> None:
    pd = pytest.importorskip("pandas")
    legacy = pd.DataFrame(
        [{"ticker": "MCD", "cik": CIK, "filing_date": "2026-08-04",
          "acceptance_datetime": "", "items": "2.02,9.01"}]
    )
    store = e8k.append_and_dedup(legacy, [
        {"ticker": "MCD", "cik": CIK, "accession": ORIGINAL, "form": "8-K",
         "filing_date": "2026-08-04", "acceptance_datetime": SOURCE_ACCEPTANCE,
         "report_date": "2026-06-30", "items": "2.02,9.01"},
    ])
    assert len(store) == 1, "re-running the collector must upgrade, not double"
    assert store.iloc[0]["accession"] == ORIGINAL


# ─────────────────────────────────────────────────────────────────────────────
# House law
# ─────────────────────────────────────────────────────────────────────────────

def test_wave_1b_modules_emit_no_ranking_or_gating_authority() -> None:
    for module in (fk, binding):
        source = Path(module.__file__).read_text(encoding="utf-8")
        for forbidden in ("def rank", "def size_", "def gate", "escalate"):
            assert forbidden not in source, f"{module.__name__} claims authority: {forbidden}"
    assert binding.AUTHORITY == "context_only"


def test_annotations_start_their_line_in_the_wire() -> None:
    source = Path(wire.__file__).read_text(encoding="utf-8")
    import re as _re
    assert not _re.findall(r"log(?:ger)?\.\w+\(\s*[\"']::", source)
