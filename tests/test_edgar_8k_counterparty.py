"""GR3b — 8-K counterparty extraction unlock (collectors/edgar_8k.py).

Wave GR3 measured `counterparty` as null in all 50,667 committed rows, and all 207
filings the enrichment lane had actually read as extraction_ok=False.  Three defects
stacked, and this file pins all three closed:

  (a) the name leg was gated behind the dollar leg -- `_parse_counterparty(text) if ok
      else None` -- so a filing with no parseable $ could never yield a name;
  (b) the primary-document selector keyed on index.json's `type` field, which is the
      directory-listing ICON name ("text.gif") and never a form type, so it fell through
      to "first .htm in the listing" and read the EDGAR submission HEADER page rather
      than the 8-K body;
  (c) the fetched HTML was handed to the regexes unstripped, and a prose regex cannot
      match across a tag boundary.

Also covers the GR3b additions: bounded material-contract exhibit reads, the
deterministic garbage-name rules, primary-wins precedence, the on-disk document cache,
and the enrich_rev bookkeeping that lets the backfill re-attempt a previously-failed row
without overloading extraction_ok (whose False is a coverage fact
engine/eightk_magnitude.py grades on).

NO NETWORK: every test drives the module through a fake `_archives_get`.

Run: TZ=UTC python3 -m pytest tests/test_edgar_8k_counterparty.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.edgar_8k as m8k  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures: a fake EDGAR Archives whose documents are fixture strings
# ---------------------------------------------------------------------------

def _headers_page(docs: list[tuple[str, str]]) -> str:
    """An EDGAR `-index-headers.html` page — SGML DOCUMENT blocks, HTML-escaped."""
    blocks = []
    for i, (doc_type, name) in enumerate(docs, start=1):
        blocks.append(
            f"&lt;DOCUMENT&gt;\n&lt;TYPE&gt;{doc_type}\n&lt;SEQUENCE&gt;{i}\n"
            f"&lt;FILENAME&gt;{name}\n&lt;DESCRIPTION&gt;doc {i}\n&lt;TEXT&gt;\n"
            f'<a href="{name}">Document {i}</a><br>\n&lt;/DOCUMENT&gt;'
        )
    return "<HTML><HEAD><TITLE>SEC EDGAR Submission</TITLE>\n&lt;SEC-HEADER&gt;\n" + "\n".join(blocks)


class _FakeResponse:
    def __init__(self, body: str, status: int = 200):
        self.status_code = status
        self.text = body
        self.encoding = "utf-8"
        self._raw = body.encode("utf-8")

    def iter_content(self, chunk_size: int = 65536):
        for i in range(0, len(self._raw), chunk_size):
            yield self._raw[i:i + chunk_size]

    def close(self):
        pass


class FakeArchives:
    """URL -> body, with a call counter so cache reuse is observable."""

    def __init__(self, files: dict[str, str]):
        self.files = files
        self.calls: list[str] = []

    def __call__(self, url, pace_s=0.0, timeout=30, stream=False):
        self.calls.append(url)
        name = url.rsplit("/", 1)[-1]
        if name not in self.files:
            return _FakeResponse("", status=404)
        return _FakeResponse(self.files[name])


CIK = 1018724
ACC = "0001104659-26-072140"
ACC_N = ACC.replace("-", "")

# A realistic Item 1.01 body: the parties clause names the registrant FIRST (as every
# credit agreement does) and the actual counterparty second.
PRIMARY_WITH_BOTH = (
    "<html><body><p>On June 8, 2026, Amazon.com, Inc. entered into a Credit Agreement, "
    "dated as of June 8, 2026, by and among Amazon.com, Inc., the lenders party thereto, "
    "and Wells Fargo Bank, National Association, as Administrative Agent.</p>"
    "<table><tr><td>Aggregate commitments of </td><td>$</td><td>1,500,000,000</td></tr></table>"
    "</body></html>"
)
# Same filing shape with the dollar figure removed — the (a) defect's exact case.
PRIMARY_NAME_NO_DOLLARS = (
    "<html><body><p>The Company entered into a Master Supply Agreement "
    "with Fabrinet Technologies Inc., dated as of June 8, 2026. The financial terms "
    "are set out in the exhibits hereto.</p></body></html>"
)
# No valid name at all — every party is a defined term or a role.
PRIMARY_NO_NAME = (
    "<html><body><p>On June 8, 2026, the Company entered into a Material Definitive "
    "Agreement with the lenders party thereto and the Administrative Agent, providing "
    "for aggregate commitments of $250,000,000.</p></body></html>"
)
EXHIBIT_CONTRACT = (
    "<html><body><p>Exhibit 10.1 CREDIT AGREEMENT dated as of June 8, 2026 by and among "
    "Amazon.com, Inc., as Borrower, and Barclays Bank PLC, as Lender, providing for a "
    "facility of $9,900,000,000.</p></body></html>"
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Point the doc cache at tmp, drop module-global state, forbid real requests."""
    monkeypatch.setattr(m8k.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(m8k, "_LAST_ARCHIVES_REQ", [0.0])
    monkeypatch.setattr(m8k._registrant_name, "_cache", {CIK: "Amazon.com, Inc."})

    def _no_network(*a, **k):  # pragma: no cover - only fires on a leak
        raise AssertionError("test attempted a real network request")

    monkeypatch.setattr(m8k.requests, "get", _no_network)
    yield


def _install(monkeypatch, files: dict[str, str]) -> FakeArchives:
    fake = FakeArchives(files)
    monkeypatch.setattr(m8k, "_archives_get", fake)
    return fake


def _filing(monkeypatch, docs: list[tuple[str, str]], bodies: dict[str, str]) -> FakeArchives:
    files = {f"{ACC}-index-headers.html": _headers_page(docs)}
    files.update(bodies)
    return _install(monkeypatch, files)


# ---------------------------------------------------------------------------
# (a) THE DEFECT: the two legs must be independent
# ---------------------------------------------------------------------------

class TestDecoupledLegs:
    def test_name_extracted_when_no_dollar_amount_parses(self, monkeypatch):
        """The GR3 defect, pinned: no $ in the filing must NOT suppress the name."""
        _filing(monkeypatch, [("8-K", "body.htm")], {"body.htm": PRIMARY_NAME_NO_DOLLARS})
        got = m8k._extract_filing(CIK, ACC, "1.01", pace_s=0.0)
        assert got["amount_usd"] is None
        assert got["extraction_ok"] is False
        # trailing period normalised off — see _parse_counterparty's docstring
        assert got["counterparty"] == "Fabrinet Technologies Inc"
        assert got["counterparty_ok"] is True

    def test_amount_extracted_when_no_name_parses(self, monkeypatch):
        _filing(monkeypatch, [("8-K", "body.htm")], {"body.htm": PRIMARY_NO_NAME})
        got = m8k._extract_filing(CIK, ACC, "1.01", pace_s=0.0)
        assert got["amount_usd"] == 250_000_000
        assert got["extraction_ok"] is True
        assert got["counterparty"] is None
        assert got["counterparty_ok"] is False

    def test_extraction_ok_still_means_amount_not_name(self, monkeypatch):
        """extraction_ok must NOT become 'we read the filing'.

        engine/eightk_magnitude.py sums it as n_extraction_ok, divides it into
        extraction_ok_pct, and gates the amount_usd read on it.  Overloading it to mean
        name-success would inflate a published coverage percentage.
        """
        _filing(monkeypatch, [("8-K", "body.htm")], {"body.htm": PRIMARY_NAME_NO_DOLLARS})
        got = m8k._extract_filing(CIK, ACC, "1.01", pace_s=0.0)
        assert got["counterparty_ok"] is True and got["extraction_ok"] is False

    def test_html_is_stripped_so_a_split_table_amount_parses(self, monkeypatch):
        """Defect (c): '$' and '1,500,000,000' sit in adjacent <td> cells."""
        _filing(monkeypatch, [("8-K", "body.htm")], {"body.htm": PRIMARY_WITH_BOTH})
        got = m8k._extract_filing(CIK, ACC, "1.01", pace_s=0.0)
        assert got["amount_usd"] == 1_500_000_000


# ---------------------------------------------------------------------------
# (b) Document selection — the index.json `type` trap
# ---------------------------------------------------------------------------

class TestManifestAndPrimarySelection:
    def test_sgml_manifest_parses_type_filename_pairs(self):
        page = _headers_page([("8-K", "body.htm"), ("EX-10.1", "ex101.htm")])
        assert m8k._parse_sgml_manifest(page) == [("8-K", "body.htm"), ("EX-10.1", "ex101.htm")]

    def test_primary_is_the_8k_body_not_the_first_htm(self, monkeypatch):
        """The header page sorts first in the directory listing; it must never win."""
        docs = [("8-K", "body.htm"), ("EX-10.1", "ex101.htm")]
        fake = _filing(monkeypatch, docs, {"body.htm": PRIMARY_WITH_BOTH,
                                           "ex101.htm": EXHIBIT_CONTRACT})
        text = m8k._fetch_primary_doc_text(CIK, ACC, pace_s=0.0)
        assert "Wells Fargo Bank" in text
        assert not any("index-headers" in c for c in fake.calls[1:])

    def test_unreadable_filing_returns_none(self, monkeypatch):
        _install(monkeypatch, {})   # every fetch 404s
        assert m8k._extract_filing(CIK, ACC, "1.01", pace_s=0.0) is None

    def test_stripper_unescapes_and_flattens(self):
        out = m8k._strip_doc_text("<p>A&nbsp;&amp;&nbsp;B</p><style>.x{color:red}</style>")
        assert out == "A & B"


# ---------------------------------------------------------------------------
# Exhibit selection + caps
# ---------------------------------------------------------------------------

class TestExhibitSelection:
    def test_xbrl_taxonomy_is_not_a_contract_exhibit(self):
        """EX-101.SCH/LAB/PRE/DEF all start with 'EX-10' and are on every filing.

        A prefix test burns the whole exhibit budget on ~110 characters of
        link:presentationLink boilerplate.
        """
        manifest = [("8-K", "b.htm"), ("EX-101.SCH", "x.xsd"), ("EX-101.LAB", "l.xml"),
                    ("EX-101.PRE", "p.xml"), ("EX-101.DEF", "d.xml"), ("EX-10.1", "ex101.htm")]
        picked, n = m8k._select_exhibits(manifest, "1.01")
        assert picked == [("EX-10.1", "ex101.htm")]
        assert n == 1

    def test_merger_exhibits_only_for_item_201(self):
        manifest = [("8-K", "b.htm"), ("EX-2.1", "ex21.htm")]
        assert m8k._select_exhibits(manifest, "1.01")[0] == []
        assert m8k._select_exhibits(manifest, "1.01,2.01")[0] == [("EX-2.1", "ex21.htm")]

    def test_cap_limits_to_three_and_reports_the_bind(self, monkeypatch):
        docs = [("8-K", "body.htm")] + [(f"EX-10.{i}", f"ex{i}.htm") for i in range(1, 6)]
        bodies = {"body.htm": PRIMARY_NO_NAME}
        bodies.update({f"ex{i}.htm": "<p>filler</p>" for i in range(1, 6)})
        fake = _filing(monkeypatch, docs, bodies)
        stats: dict = {}
        m8k._extract_filing(CIK, ACC, "1.01", pace_s=0.0, stats=stats)
        assert stats["exhibits_eligible"] == 5
        assert stats["exhibits_read"] == m8k._EXHIBIT_CAP == 3
        assert stats["exhibit_cap_binds"] == 1
        assert stats["exhibits_skipped"] == 2
        assert sum(1 for c in fake.calls if "/ex" in c) == 3

    def test_oversize_exhibit_is_truncated_and_counted(self, monkeypatch):
        big = "<p>" + ("filler word " * 200_000) + "</p>"
        assert len(big.encode()) > m8k._EXHIBIT_MAX_BYTES
        _filing(monkeypatch, [("8-K", "body.htm"), ("EX-10.1", "ex1.htm")],
                {"body.htm": PRIMARY_NO_NAME, "ex1.htm": big})
        stats: dict = {}
        m8k._extract_filing(CIK, ACC, "1.01", pace_s=0.0, stats=stats)
        assert stats["exhibit_truncated"] == 1

    def test_exhibits_are_not_fetched_when_primary_answers_both_legs(self, monkeypatch):
        """Nightly budget: the common case must stay at manifest + primary."""
        fake = _filing(monkeypatch, [("8-K", "body.htm"), ("EX-10.1", "ex1.htm")],
                       {"body.htm": PRIMARY_WITH_BOTH, "ex1.htm": EXHIBIT_CONTRACT})
        stats: dict = {}
        m8k._extract_filing(CIK, ACC, "1.01", pace_s=0.0, stats=stats)
        assert len(fake.calls) == 2
        assert stats.get("exhibits_read", 0) == 0


# ---------------------------------------------------------------------------
# Precedence: primary wins, exhibits fill gaps
# ---------------------------------------------------------------------------

class TestPrecedence:
    def test_primary_name_wins_over_exhibit_name(self, monkeypatch):
        _filing(monkeypatch, [("8-K", "body.htm"), ("EX-10.1", "ex1.htm")],
                {"body.htm": PRIMARY_WITH_BOTH, "ex1.htm": EXHIBIT_CONTRACT})
        got = m8k._extract_filing(CIK, ACC, "1.01", pace_s=0.0)
        assert got["counterparty"] == "Wells Fargo Bank"
        assert got["counterparty_src"] == "primary"

    def test_exhibit_fills_the_gap_when_primary_has_no_name(self, monkeypatch):
        _filing(monkeypatch, [("8-K", "body.htm"), ("EX-10.1", "ex1.htm")],
                {"body.htm": PRIMARY_NO_NAME, "ex1.htm": EXHIBIT_CONTRACT})
        got = m8k._extract_filing(CIK, ACC, "1.01", pace_s=0.0)
        assert got["counterparty"] == "Barclays Bank PLC"
        assert got["counterparty_src"] == "exhibit"
        # …and the primary's amount still wins over the exhibit's larger figure.
        assert got["amount_usd"] == 250_000_000
        assert got["amount_src"] == "primary"

    def test_exhibit_amount_used_only_when_primary_has_none(self, monkeypatch):
        _filing(monkeypatch, [("8-K", "body.htm"), ("EX-10.1", "ex1.htm")],
                {"body.htm": PRIMARY_NAME_NO_DOLLARS, "ex1.htm": EXHIBIT_CONTRACT})
        got = m8k._extract_filing(CIK, ACC, "1.01", pace_s=0.0)
        assert got["amount_usd"] == 9_900_000_000
        assert got["amount_src"] == "exhibit"
        assert got["counterparty_src"] == "primary"


# ---------------------------------------------------------------------------
# Deterministic garbage-name rules
# ---------------------------------------------------------------------------

class TestCounterpartyQuality:
    # Every rejected string below was produced by the extractor against a real filing
    # during GR3b development (2026-08-08) before the rule that kills it was added.
    @pytest.mark.parametrize("bad", [
        "the Company", "Company", "Borrower", "the Borrower", "Lender", "Lenders",
        "Administrative Agent", "Material Definitive", "a Material Definitive",
        "Plan of Merger", "First Merger", "General Partner", "Private Placement",
        "Company Class A Common Stock", "the lenders party thereto",
        "financial institutions party hereto", "New York Stock Exchange",
        "Securities and Exchange Commission", "Trustee", "Alphabet", "AB",
    ])
    def test_rejects_roles_defined_terms_and_boilerplate(self, bad):
        assert m8k._counterparty_is_valid(bad) is False

    @pytest.mark.parametrize("good", [
        "Wells Fargo Bank", "Goldman Sachs & Co. LLC", "Barclays Bank PLC",
        "JPMorgan Chase Bank", "Deutsche Bank Trust Company Americas",
        "Iridium Communications Inc", "Alphabet Inc.", "Mizuho Bank",
        "Elliott Investment Management L.P.", "Bank of America",
    ])
    def test_accepts_real_entity_names(self, good):
        assert m8k._counterparty_is_valid(good) is True

    def test_one_token_needs_a_legal_suffix(self):
        assert m8k._counterparty_is_valid("Alphabet") is False
        assert m8k._counterparty_is_valid("Alphabet Inc.") is True

    def test_rejects_the_registrants_own_name(self):
        reg = "Realty Income Corp"
        assert m8k._counterparty_is_valid("REALTY INCOME CORPORATION", reg) is False
        assert m8k._counterparty_is_valid("Wells Fargo Bank", reg) is True

    def test_rejects_a_financing_subsidiary_by_distinctive_head_token(self):
        reg = "COGNIZANT TECHNOLOGY SOLUTIONS CORP"
        assert m8k._counterparty_is_valid("Cognizant Worldwide Limited", reg) is False

    def test_generic_head_token_does_not_trigger_self_name(self):
        """'Bank' is too common to be a self-name signal."""
        assert m8k._counterparty_is_valid("Bank of America", "Bank of New York Mellon") is True

    def test_walks_past_the_registrant_to_the_real_counterparty(self):
        text = ("entered into a Credit Agreement by and among Amazon.com, Inc., the lenders "
                "party thereto, and Wells Fargo Bank, National Association, as Agent.")
        assert m8k._parse_counterparty(text, "Amazon.com, Inc.") == "Wells Fargo Bank"

    def test_window_truncation_does_not_emit_a_half_word(self):
        """A clause cut at the window edge must drop its trailing fragment."""
        text = "entered into an agreement with " + ("Placeholder Holdings Corp, " * 40) + "Exchange Commis"
        assert m8k._parse_counterparty(text) != "Exchange Commis"

    def test_no_candidate_is_a_clean_null(self):
        assert m8k._parse_counterparty("A material agreement was entered into.") is None


# ---------------------------------------------------------------------------
# Document cache
# ---------------------------------------------------------------------------

class TestDocCache:
    def test_second_extraction_issues_no_requests(self, monkeypatch):
        fake = _filing(monkeypatch, [("8-K", "body.htm")], {"body.htm": PRIMARY_WITH_BOTH})
        first = m8k._extract_filing(CIK, ACC, "1.01", pace_s=0.0)
        n_after_first = len(fake.calls)
        stats: dict = {}
        second = m8k._extract_filing(CIK, ACC, "1.01", pace_s=0.0, stats=stats)
        assert len(fake.calls) == n_after_first, "cached filing refetched"
        assert stats["cache_hits"] == 2      # manifest + primary
        assert first == second

    def test_cache_write_lands_under_the_data_dir(self, tmp_path, monkeypatch):
        _filing(monkeypatch, [("8-K", "body.htm")], {"body.htm": PRIMARY_WITH_BOTH})
        m8k._extract_filing(CIK, ACC, "1.01", pace_s=0.0)
        cached = tmp_path / "edgar" / m8k._DOC_CACHE_DIR / str(CIK) / ACC_N / "body.htm.txt"
        assert cached.exists() and "Wells Fargo" in cached.read_text()

    @pytest.mark.parametrize("evil", ["../../etc/passwd", "a/b.htm", "..", ""])
    def test_untrusted_filenames_are_refused_not_sanitised(self, evil):
        assert m8k._doc_cache_path(CIK, ACC_N, evil) is None


# ---------------------------------------------------------------------------
# Backfill bookkeeping: re-attempt, idempotence, resume, nightly containment
# ---------------------------------------------------------------------------

def _events_frame() -> pd.DataFrame:
    """Three 1.01 rows: one never enriched, one previously FAILED, one out of scope."""
    today = pd.Timestamp.now(tz="UTC").normalize()
    return pd.DataFrame([
        {"ticker": "AMZN", "cik": CIK, "form": "8-K",
         "filing_date": (today - pd.Timedelta(days=5)).date().isoformat(),
         "items": "1.01", "accession": ACC, "_first_seen": "2026-06-10T00:00:00+00:00"},
        {"ticker": "AMZN", "cik": CIK, "form": "8-K",
         "filing_date": (today - pd.Timedelta(days=400)).date().isoformat(),
         "items": "1.01,2.03", "accession": "0001104659-26-000002",
         "_first_seen": "2025-07-01T00:00:00+00:00",
         "amount_usd": None, "counterparty": None, "extraction_ok": False},
        {"ticker": "AMZN", "cik": CIK, "form": "8-K",
         "filing_date": (today - pd.Timedelta(days=10)).date().isoformat(),
         "items": "5.02", "accession": "0001104659-26-000003",
         "_first_seen": "2026-07-01T00:00:00+00:00"},
    ])


@pytest.fixture
def _all_filings(monkeypatch):
    files = {}
    for acc in (ACC, "0001104659-26-000002", "0001104659-26-000003"):
        files[f"{acc}-index-headers.html"] = _headers_page([("8-K", f"{acc}-body.htm")])
        files[f"{acc}-body.htm"] = PRIMARY_WITH_BOTH
    return _install(monkeypatch, files)


class TestBackfillBookkeeping:
    def test_backfill_reattempts_a_previously_failed_row(self, _all_filings):
        """extraction_ok=False rows are invisible to an isna() mask — enrich_rev fixes it."""
        out = m8k.enrich_contract_amounts(_events_frame(), incremental=False, pace_s=0.0,
                                          window_days=730)
        failed = out[out["accession"] == "0001104659-26-000002"].iloc[0]
        assert failed["counterparty"] == "Wells Fargo Bank"
        assert failed["extraction_ok"] is True
        assert failed["enrich_rev"] == m8k._ENRICH_REV

    def test_backfill_is_idempotent(self, _all_filings):
        first = m8k.enrich_contract_amounts(_events_frame(), incremental=False, pace_s=0.0,
                                            window_days=730)
        stats: dict = {}
        second = m8k.enrich_contract_amounts(first, incremental=False, pace_s=0.0,
                                             window_days=730, stats=stats)
        assert stats["targeted"] == 0
        pd.testing.assert_frame_equal(first, second)

    def test_only_101_203_rows_are_targeted(self, _all_filings):
        stats: dict = {}
        out = m8k.enrich_contract_amounts(_events_frame(), incremental=False, pace_s=0.0,
                                          window_days=730, stats=stats)
        assert stats["targeted"] == 2
        other = out[out["accession"] == "0001104659-26-000003"].iloc[0]
        assert pd.isna(other["counterparty"]) and pd.isna(other["enrich_rev"])

    def test_window_days_bounds_the_backfill(self, _all_filings):
        stats: dict = {}
        m8k.enrich_contract_amounts(_events_frame(), incremental=False, pace_s=0.0,
                                    window_days=30, stats=stats)
        assert stats["targeted"] == 1   # the 400-day-old row is out of the horizon

    def test_limit_and_skip_accessions_advance_a_chunked_run(self, _all_filings):
        df = _events_frame()
        s1: dict = {}
        df = m8k.enrich_contract_amounts(df, incremental=False, pace_s=0.0,
                                         window_days=730, limit=1, stats=s1)
        assert s1["targeted"] == 1
        s2: dict = {}
        df = m8k.enrich_contract_amounts(df, incremental=False, pace_s=0.0, window_days=730,
                                         limit=1, skip_accessions=set(s1["attempted_accessions"]),
                                         stats=s2)
        assert s2["targeted"] == 1
        assert set(s1["attempted_accessions"]).isdisjoint(s2["attempted_accessions"])

    def test_nightly_path_does_not_reattempt_failed_history(self, _all_filings):
        """Acceptance 7: the nightly increment must not balloon on the backfill's behalf."""
        stats: dict = {}
        m8k.enrich_contract_amounts(_events_frame(), incremental=True, pace_s=0.0, stats=stats)
        assert stats["targeted"] == 1   # only the never-read row inside the 45d window

    def test_unreadable_row_stays_unstamped_and_retryable(self, monkeypatch):
        _install(monkeypatch, {})   # every fetch 404s
        stats: dict = {}
        out = m8k.enrich_contract_amounts(_events_frame(), incremental=False, pace_s=0.0,
                                          window_days=730, stats=stats)
        assert stats["unread"] == 2
        row = out[out["accession"] == ACC].iloc[0]
        assert row["enrich_rev"] is None
        assert pd.isna(row["extraction_ok"]) or row["extraction_ok"] is None

    def test_row_without_ids_is_stamped_not_retried_forever(self, _all_filings):
        df = _events_frame()
        df.loc[df["accession"] == ACC, "cik"] = None
        out = m8k.enrich_contract_amounts(df, incremental=False, pace_s=0.0, window_days=730)
        row = out[out["accession"] == ACC].iloc[0]
        assert row["extraction_ok"] is False and row["enrich_rev"] == m8k._ENRICH_REV

    def test_cap_bind_emits_a_column_zero_annotation(self, monkeypatch, capsys):
        docs = [("8-K", "body.htm")] + [(f"EX-10.{i}", f"ex{i}.htm") for i in range(1, 6)]
        bodies = {"body.htm": PRIMARY_NO_NAME}
        bodies.update({f"ex{i}.htm": "<p>filler</p>" for i in range(1, 6)})
        files = {f"{ACC}-index-headers.html": _headers_page(docs)}
        files.update(bodies)
        _install(monkeypatch, files)
        df = _events_frame().head(1)
        m8k.enrich_contract_amounts(df, incremental=False, pace_s=0.0, window_days=730,
                                    stats={})
        # stats={} carries no cap counter into the summary; run again with a live dict
        stats: dict = {}
        m8k.enrich_contract_amounts(_events_frame().head(1), incremental=False, pace_s=0.0,
                                    window_days=730, stats=stats)
        out = capsys.readouterr().out
        line = next(ln for ln in out.splitlines() if "edgar-8k-exhibit-cap" in ln)
        assert line.startswith("::warning "), f"annotation must start the line: {line!r}"


# ---------------------------------------------------------------------------
# The accession-dedup merge must not blank the new columns
# ---------------------------------------------------------------------------

class TestMergeKeepsEnrichment:
    def test_enrichment_survives_an_accession_rescan(self, tmp_path, monkeypatch):
        adapter = m8k.Edgar8KAdapter()
        path = tmp_path / "edgar" / "material_8k_events.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(adapter, "_events_path", lambda: path)

        enriched = pd.DataFrame([{
            "ticker": "AMZN", "cik": CIK, "form": "8-K", "filing_date": "2026-06-10",
            "items": "1.01", "accession": ACC, "_first_seen": "2026-06-10T00:00:00+00:00",
            "amount_usd": 1.5e9, "counterparty": "Wells Fargo Bank", "extraction_ok": True,
            "counterparty_ok": True, "amount_src": "primary", "counterparty_src": "primary",
            "enrich_rev": m8k._ENRICH_REV,
        }])
        enriched.to_parquet(path)

        rescan = pd.DataFrame([{
            "ticker": "AMZN", "cik": CIK, "form": "8-K", "filing_date": "2026-06-10",
            "items": "1.01,2.03", "accession": ACC,
        }])
        merged = adapter._merge_events(rescan)
        row = merged.iloc[0]
        assert len(merged) == 1
        assert row["items"] == "1.01,2.03"            # union of codes
        assert row["counterparty"] == "Wells Fargo Bank"
        assert bool(row["counterparty_ok"]) is True
        assert row["counterparty_src"] == "primary"
        assert row["enrich_rev"] == m8k._ENRICH_REV

    def test_writer_and_merge_agree_on_the_column_list(self, monkeypatch):
        """A field added to the writer but not to _ENRICH_COLS is blanked on the next
        re-scan of an already-enriched accession — silently, and only for filings that
        happen to be re-scanned. Pin the two lists to each other."""
        _filing(monkeypatch, [("8-K", "body.htm")], {"body.htm": PRIMARY_WITH_BOTH})
        written = m8k._extract_filing(CIK, ACC, "1.01", pace_s=0.0)
        assert set(written) == set(m8k._ENRICH_COLS)
