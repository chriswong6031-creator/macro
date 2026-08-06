"""The recovered half of the US board track record must be POINT-IN-TIME, ERA-SPLIT,
and re-runnable without moving.

WHAT THIS PINS (2026-08-06 recovery). `data/us_board_ledger/snapshots.jsonl` held 17
entries against 524 git revisions spanning 32 board dates, because the nightly checks out
at `fetch-depth: 1` and the grader's archaeology leg has therefore contributed nothing
for a month. The ratified repair reconstructs those dates ONCE from git and then has the
grader read the ledger. Every way that repair could quietly lie is a class below:

  1. PIT. A recovered entry must be the board AS IT WAS in that commit — not today's
     schema, not today's code, not a later revision of the same date.
     -> TestRecoveredEntriesArePointInTime
  2. ERA. Cohorts selected by different rules must not be poolable. The stamp is what
     the artifact DECLARED (with `unknown` + a reason when it declared nothing), never
     an inference.  -> TestEraStampIsTheArtifactsOwnDeclaration
  3. IDEMPOTENCE. A recovery that appends again on the second run turns a track record
     into a function of how many times someone ran a script.
     -> TestIdempotentAndAppendOnly
  4. NATIVE WINS. Where a native entry and a recovered one describe the same date, the
     native is authoritative and the disagreement is RECORDED, not resolved silently.
     -> TestNativeWinsOnCollision
  5. DISCLOSURE. A shallow checkout must never be a silent zero — before the recovery it
     is an outage warning, after it a notice that names the numbers.
     -> TestShallowCheckoutIsDisclosedEitherWay

Both directions are pinned. A guard that cannot fail is the defect it was written for,
so the era test and the idempotency test each carry a MUTATION check that breaks the
implementation on purpose and requires the assertion to notice.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import backfill_us_board_snapshots as bf  # noqa: E402
from scripts import grade_us_board as g  # noqa: E402

BOARD = "site/factordata/us_standouts.json"
ENGINE = bf.ENGINE_COMMIT_PREFIX + " 2026-01-01"


# --------------------------------------------------------------------------- #
# synthetic repo — a real git history, so the tool is exercised through git
# --------------------------------------------------------------------------- #
def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "site" / "factordata").mkdir(parents=True)
    _git(repo.parent, "init", "-q", "-b", "main", str(repo))
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    return repo


def _commit(repo: Path, artifact, subject: str = ENGINE) -> str:
    """Write the artifact (dict, or raw str for a corrupt revision) and commit it."""
    p = repo / BOARD
    p.write_text(artifact if isinstance(artifact, str) else json.dumps(artifact))
    _git(repo, "add", BOARD)
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", subject)
    return _git(repo, "rev-parse", "HEAD").strip()


def _board(as_of: str, buy: list[str], laggards: list[str] | None = None, **top) -> dict:
    d = {"as_of": as_of,
         "buy": [{"ticker": t, "sector": "Materials"} for t in buy],
         "laggards": [{"ticker": t, "sector": "Utilities"}
                      for t in (["ZZZ"] if laggards is None else laggards)]}
    d.update(top)
    return d


def _entries(ledger: Path) -> list[dict]:
    return [json.loads(ln) for ln in ledger.read_text().splitlines() if ln.strip()]


# --------------------------------------------------------------------------- #
# 1 — point-in-time
# --------------------------------------------------------------------------- #
class TestRecoveredEntriesArePointInTime:
    def test_each_entry_is_the_artifact_at_its_own_revision(self, tmp_path):
        """Three board dates, three different schemas. Each recovered entry must carry
        ITS OWN date's rows — recovering all three from the newest blob would still
        produce three entries, three as_of values and a plausible-looking ledger."""
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["AAA", "BBB"], rank_by="conviction"))
        _commit(repo, _board("2026-06-16", ["CCC"], rank_by="conviction"))
        _commit(repo, _board("2026-06-17", ["DDD", "EEE", "FFF"],
                             rank_by="confluence", board_definition="us_prophet_v1"))

        plan = bf.plan_backfill(repo, BOARD, tmp_path / "snap.jsonl")
        by = {e["as_of"]: e for e in plan["_entries"]}
        assert sorted(by) == ["2026-06-15", "2026-06-16", "2026-06-17"]
        assert [r["ticker"] for r in by["2026-06-15"]["buy"]] == ["AAA", "BBB"]
        assert [r["ticker"] for r in by["2026-06-16"]["buy"]] == ["CCC"]
        assert [r["ticker"] for r in by["2026-06-17"]["buy"]] == ["DDD", "EEE", "FFF"]

    def test_a_field_that_only_exists_later_never_appears_on_an_earlier_entry(self, tmp_path):
        """The schema-drift trap: `board_definition` arrives on the LAST revision only.
        An entry stamped from the working tree (today's code) would carry it on all
        three."""
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["AAA"], rank_by="conviction"))
        _commit(repo, _board("2026-06-16", ["BBB"], rank_by="conviction"))
        _commit(repo, _board("2026-06-17", ["CCC"], rank_by="us_prophet_v1",
                             board_definition="us_prophet_v1"))

        by = {e["as_of"]: e for e in
              bf.plan_backfill(repo, BOARD, tmp_path / "snap.jsonl")["_entries"]}
        assert "board_definition" not in by["2026-06-15"]
        assert "board_definition" not in by["2026-06-16"]
        assert by["2026-06-17"]["board_definition"] == "us_prophet_v1"

    def test_the_revision_recovered_is_the_nightly_engine_commit(self, tmp_path):
        """A board date has many revisions (renders, re-bakes). The one the ledger would
        have recorded is the NIGHTLY ENGINE job's — the job that runs the snapshotter.
        Here the engine commit is neither the first nor the last revision of the date."""
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["EARLY"]), subject="render: site re-render")
        _commit(repo, _board("2026-06-15", ["PUBLISHED"]), subject=ENGINE)
        _commit(repo, _board("2026-06-15", ["LATE"]), subject="render: site re-render")

        e = bf.plan_backfill(repo, BOARD, tmp_path / "snap.jsonl")["_entries"][0]
        assert [r["ticker"] for r in e["buy"]] == ["PUBLISHED"]
        assert e["recovery"]["selection"] == bf.SELECT_ENGINE
        assert e["recovery"]["revision_index"] == 1

    def test_a_date_with_no_engine_commit_falls_back_and_SAYS_SO(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["AAA"]), subject="render: site re-render")
        _commit(repo, _board("2026-06-15", ["BBB"]), subject="render: site re-render")

        e = bf.plan_backfill(repo, BOARD, tmp_path / "snap.jsonl")["_entries"][0]
        assert e["recovery"]["selection"] == bf.SELECT_FALLBACK
        assert e["recovery"]["n_engine_revisions_for_as_of"] == 0
        assert [r["ticker"] for r in e["buy"]] == ["AAA"]

    def test_every_entry_carries_its_source_commit_and_the_recovery_marker(self, tmp_path):
        repo = _repo(tmp_path)
        sha = _commit(repo, _board("2026-06-15", ["AAA"], rank_by="conviction"))

        e = bf.plan_backfill(repo, BOARD, tmp_path / "snap.jsonl")["_entries"][0]
        assert e["recovery"]["source"] == bf.RECOVERY_SOURCE
        assert e["recovery"]["commit"] == sha, "a recovered row must name its evidence"
        assert e["recovery"]["commit_time"]

    def test_an_unparseable_or_as_of_less_revision_is_SKIPPED_with_a_reason(self, tmp_path):
        """'Do not guess' is the rule; 'do not guess silently' is the test."""
        repo = _repo(tmp_path)
        _commit(repo, "{not json at all")
        _commit(repo, {"buy": [{"ticker": "AAA"}]})           # no as_of
        _commit(repo, _board("2026-06-15", [], laggards=[]), subject=ENGINE)  # no rows
        _commit(repo, _board("2026-06-16", ["AAA"]), subject=ENGINE)

        plan = bf.plan_backfill(repo, BOARD, tmp_path / "snap.jsonl")
        assert plan["n_to_append"] == 1
        assert plan["n_revisions_skipped"] == 3
        reasons = {s["reason"].split(":")[0] for s in plan["skips"]}
        assert reasons == {"json_decode_error", "no_as_of", "no_lane_rows"}
        assert all(s["commit"] and s["reason"] for s in plan["skips"])

    def test_a_git_error_raises_rather_than_recovering_less(self, tmp_path):
        """Same law as grade_us_board._git_revisions: a short recovery that looks like
        the whole history is worse than no recovery."""
        with pytest.raises(RuntimeError, match="silently truncated"):
            bf.board_revisions(tmp_path / "not-a-repo", BOARD)


# --------------------------------------------------------------------------- #
# 2 — era stamping
# --------------------------------------------------------------------------- #
class TestEraStampIsTheArtifactsOwnDeclaration:
    def test_a_multi_construction_history_yields_per_era_entries(self, tmp_path):
        """The pooling read is the one that must fail: five board dates built under
        three declared constructions must NOT collapse to one era."""
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["A"]))                       # no declaration
        _commit(repo, _board("2026-06-16", ["B"], rank_by="conviction"))
        _commit(repo, _board("2026-06-17", ["C"], rank_by="conviction"))
        _commit(repo, _board("2026-06-18", ["D"], rank_by="confluence"))
        _commit(repo, _board("2026-06-19", ["E"], rank_by="us_prophet_v1",
                             board_definition="us_prophet_v1"))

        plan = bf.plan_backfill(repo, BOARD, tmp_path / "snap.jsonl")
        eras = {e["as_of"]: e["recovery"]["era_key"] for e in plan["_entries"]}
        assert eras == {
            "2026-06-15": "unknown",
            "2026-06-16": "rank_by:conviction",
            "2026-06-17": "rank_by:conviction",
            "2026-06-18": "rank_by:confluence",
            "2026-06-19": "board_definition:us_prophet_v1",
        }
        # the pooling read — one era over the whole span — must be false
        assert len(set(eras.values())) == 4, "a pooled cohort is not a track record"
        assert plan["per_era"] == {"board_definition:us_prophet_v1": 1,
                                   "rank_by:confluence": 1,
                                   "rank_by:conviction": 2,
                                   "unknown": 1}

    def test_an_undeclared_era_is_unknown_WITH_A_REASON(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["A"]))

        r = bf.plan_backfill(repo, BOARD, tmp_path / "snap.jsonl")["_entries"][0]["recovery"]
        assert r["era_key"] == "unknown"
        assert r["era_source"] == "unknown"
        assert r["era_declared"] is None
        assert "declared neither" in (r["era_unknown_reason"] or ""), \
            "an unknown era with no reason is a guess wearing a label"

    def test_board_definition_outranks_rank_by_and_is_copied_verbatim(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["A"], rank_by="confluence",
                             board_definition="us_prophet_v1"))

        e = bf.plan_backfill(repo, BOARD, tmp_path / "snap.jsonl")["_entries"][0]
        assert e["recovery"]["era_key"] == "board_definition:us_prophet_v1"
        assert e["board_definition"] == "us_prophet_v1"
        assert e["rank_by"] == "confluence", "the artifact's own rank_by is preserved too"

    def test_an_empty_stamp_is_not_a_declaration(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["A"], board_definition="", rank_by="  "))

        e = bf.plan_backfill(repo, BOARD, tmp_path / "snap.jsonl")["_entries"][0]
        assert e["recovery"]["era_key"] == "unknown"
        assert "board_definition" not in e, "an empty stamp must not be written as a stamp"

    def test_a_date_whose_revisions_disagree_records_the_churn(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["A"]), subject=ENGINE)
        _commit(repo, _board("2026-06-15", ["A"], rank_by="conviction"),
                subject="render: site re-render")

        r = bf.plan_backfill(repo, BOARD, tmp_path / "snap.jsonl")["_entries"][0]["recovery"]
        assert r["era_key"] == "unknown"
        assert r["construction_churn"] == ["rank_by:conviction", "unknown"], \
            "one chosen revision must not imply the whole day was one construction"

    def test_a_stamp_that_cannot_separate_two_constructions_is_REPORTED(self, tmp_path):
        """The measured 2026-06-25 case in miniature: one declared era spanning a
        120-name broad screen AND a narrow selection. The declaration is kept as-is —
        and the tool says out loud that it does not separate them."""
        repo = _repo(tmp_path)
        wide = [f"T{i}" for i in range(g.LEDGER_BROAD_SCREEN_BUY_MIN + 20)]
        _commit(repo, _board("2026-06-15", wide, rank_by="bottoming-alignment"))
        _commit(repo, _board("2026-06-16", ["A", "B"], rank_by="bottoming-alignment"))

        plan = bf.plan_backfill(repo, BOARD, tmp_path / "snap.jsonl")
        assert plan["eras_the_declaration_cannot_separate"] == ["rank_by:bottoming-alignment"]
        span = plan["era_span_over_all_git_dates"]["rank_by:bottoming-alignment"]
        assert span["spans_broad_screen_boundary"] is True
        assert span["broad_screen_dates"] == ["2026-06-15"]
        # the observed width ships on the entry, beside (never inside) the declaration
        widths = {e["as_of"]: e["recovery"]["lane_widths"]["buy"] for e in plan["_entries"]}
        assert widths == {"2026-06-15": len(wide), "2026-06-16": 2}

    def test_MUTATION_a_pooled_era_stamp_is_caught(self, tmp_path, monkeypatch):
        """Mutation check: make era_stamp return one constant era for everything — the
        exact shape of a pooling bug — and require the era assertions to fail."""
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["A"], rank_by="conviction"))
        _commit(repo, _board("2026-06-16", ["B"], rank_by="confluence"))

        monkeypatch.setattr(bf, "era_stamp", lambda d: {
            "era_key": "rank_by:one", "era_source": "rank_by",
            "era_declared": "one", "era_unknown_reason": None}, raising=True)
        plan = bf.plan_backfill(repo, BOARD, tmp_path / "snap.jsonl")
        eras = {e["recovery"]["era_key"] for e in plan["_entries"]}
        assert len(eras) == 1, "mutation did not take — the rest of this check is vacuous"
        with pytest.raises(AssertionError):
            assert len(eras) == 2, "two declared constructions must yield two eras"


# --------------------------------------------------------------------------- #
# 3 — idempotence / append-only
# --------------------------------------------------------------------------- #
class TestIdempotentAndAppendOnly:
    def test_a_second_run_leaves_the_file_byte_identical(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["A"], rank_by="conviction"))
        _commit(repo, _board("2026-06-16", ["B"], rank_by="confluence"))
        ledger = tmp_path / "snap.jsonl"

        n1 = bf.write_backfill(bf.plan_backfill(repo, BOARD, ledger), ledger, None)
        first = ledger.read_bytes()
        n2 = bf.write_backfill(bf.plan_backfill(repo, BOARD, ledger), ledger, None)
        assert (n1, n2) == (2, 0)
        assert ledger.read_bytes() == first, "a re-run moved the track record"

    def test_a_third_run_after_a_new_board_date_appends_only_that_date(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["A"], rank_by="conviction"))
        ledger = tmp_path / "snap.jsonl"
        bf.write_backfill(bf.plan_backfill(repo, BOARD, ledger), ledger, None)
        before = ledger.read_bytes()

        _commit(repo, _board("2026-06-16", ["B"], rank_by="confluence"))
        n = bf.write_backfill(bf.plan_backfill(repo, BOARD, ledger), ledger, None)
        assert n == 1
        assert ledger.read_bytes().startswith(before), \
            "append-only: existing lines must not be rewritten or reordered"
        assert [e["as_of"] for e in _entries(ledger)] == ["2026-06-15", "2026-06-16"]

    def test_existing_native_lines_are_preserved_byte_for_byte(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["A"], rank_by="conviction"))
        ledger = tmp_path / "snap.jsonl"
        native_line = '{"as_of":"2026-06-14","rank_by":"legacy","buy":[{"ticker":"NAT"}]}'
        ledger.write_text(native_line + "\n")

        bf.write_backfill(bf.plan_backfill(repo, BOARD, ledger), ledger, None)
        assert ledger.read_text().splitlines()[0] == native_line

    def test_MUTATION_an_append_that_ignores_the_ledger_is_caught(self, tmp_path,
                                                                  monkeypatch):
        """Mutation check: blind the tool to what the ledger already holds — the exact
        shape of a duplicate-on-re-run bug — and require the byte-identity assertion
        to fail."""
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["A"], rank_by="conviction"))
        ledger = tmp_path / "snap.jsonl"
        bf.write_backfill(bf.plan_backfill(repo, BOARD, ledger), ledger, None)
        first = ledger.read_bytes()

        monkeypatch.setattr(bf, "read_ledger", lambda *_a, **_k: {}, raising=True)
        bf.write_backfill(bf.plan_backfill(repo, BOARD, ledger), ledger, None)
        assert ledger.read_bytes() != first, \
            "mutation did not take — the idempotency check above is vacuous"


# --------------------------------------------------------------------------- #
# 4 — native wins on collision
# --------------------------------------------------------------------------- #
class TestNativeWinsOnCollision:
    def test_a_native_entry_is_never_overwritten_and_the_clash_is_recorded(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["RECOVERED"], rank_by="conviction"))
        ledger = tmp_path / "snap.jsonl"
        ledger.write_text(json.dumps(
            {"as_of": "2026-06-15", "rank_by": "conviction",
             "buy": [{"ticker": "NATIVE"}]}) + "\n")

        plan = bf.plan_backfill(repo, BOARD, ledger)
        assert plan["n_to_append"] == 0
        assert plan["n_collisions"] == 1
        c = plan["collisions"][0]
        assert c["resolution"] == "kept_native"
        assert c["agrees"] is False, "a real disagreement must not read as agreement"
        assert c["native_lane_counts"]["buy"] == 1

        bf.write_backfill(plan, ledger, None)
        rows = _entries(ledger)
        assert len(rows) == 1
        assert [r["ticker"] for r in rows[0]["buy"]] == ["NATIVE"]

    def test_an_agreeing_collision_is_recorded_as_agreeing(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["SAME"], rank_by="conviction"))
        ledger = tmp_path / "snap.jsonl"
        ledger.write_text(json.dumps(
            {"as_of": "2026-06-15", "rank_by": "conviction",
             "buy": [{"ticker": "SAME"}],
             "laggards": [{"ticker": "ZZZ"}]}) + "\n")

        plan = bf.plan_backfill(repo, BOARD, ledger)
        assert plan["n_collisions"] == 1
        assert plan["n_collisions_disagreeing"] == 0
        assert plan["selection_fidelity"]["n_reproduced_exactly"] == 1
        assert plan["selection_fidelity"]["rate"] == 1.0

    def test_selection_fidelity_falls_when_the_wrong_revision_is_chosen(self, tmp_path,
                                                                        monkeypatch):
        """The fidelity number must be able to go DOWN — a self-check pinned at 1.0 by
        construction measures nothing."""
        repo = _repo(tmp_path)
        _commit(repo, _board("2026-06-15", ["PUBLISHED"]), subject=ENGINE)
        _commit(repo, _board("2026-06-15", ["LATER"]), subject="render: site re-render")
        ledger = tmp_path / "snap.jsonl"
        ledger.write_text(json.dumps(
            {"as_of": "2026-06-15", "buy": [{"ticker": "PUBLISHED"}],
             "laggards": [{"ticker": "ZZZ"}]}) + "\n")

        assert bf.plan_backfill(repo, BOARD, ledger)["selection_fidelity"]["rate"] == 1.0
        monkeypatch.setattr(bf, "select_revision",
                            lambda revs: (len(revs) - 1, bf.SELECT_ENGINE, 1), raising=True)
        assert bf.plan_backfill(repo, BOARD, ledger)["selection_fidelity"]["rate"] == 0.0


# --------------------------------------------------------------------------- #
# 5 — the grader reads the LEDGER; a shallow checkout is disclosed either way
# --------------------------------------------------------------------------- #
class TestGraderReadsTheLedgerNotGit:
    def _ledger(self, tmp_path: Path, recovered: bool) -> Path:
        p = tmp_path / "snap.jsonl"
        rows = [{"as_of": "2026-06-15", "rank_by": "conviction",
                 "buy": [{"ticker": "AAA"}]},
                {"as_of": "2026-06-16", "rank_by": "conviction",
                 "buy": [{"ticker": "BBB"}]}]
        if recovered:
            rows[0]["recovery"] = {"source": bf.RECOVERY_SOURCE, "commit": "deadbeef",
                                   "era_key": "rank_by:conviction"}
        p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        return p

    def test_a_recovered_ledger_does_not_shell_out_to_git(self, tmp_path, monkeypatch):
        """The nightly cannot read git history. After the recovery it must not try."""
        monkeypatch.setattr(g, "SNAPSHOTS_JSONL", self._ledger(tmp_path, True))

        def _boom():
            raise AssertionError("archaeology ran on a recovered ledger")
        monkeypatch.setattr(g, "_git_revisions", _boom, raising=True)

        receipt: dict = {}
        boards = g.collect_boards(receipt)
        assert [b["as_of"] for b in boards] == ["2026-06-15", "2026-06-16"]
        assert receipt["git_fallback_used"] is False
        assert receipt["n_from_ledger_recovered"] == 1
        assert receipt["n_from_ledger_live"] == 1
        assert "recovered" in receipt["git_fallback_reason"]

    def test_an_unrecovered_ledger_still_uses_the_fallback(self, tmp_path, monkeypatch):
        """Self-disarming: before the recovery lands (or if it were reverted) the
        archaeology leg behaves exactly as it did."""
        monkeypatch.setattr(g, "SNAPSHOTS_JSONL", self._ledger(tmp_path, False))
        called: list[int] = []

        def _revs():
            called.append(1)
            return []
        monkeypatch.setattr(g, "_git_revisions", _revs, raising=True)

        receipt: dict = {}
        g.collect_boards(receipt)
        assert called, "the fallback must still seed a ledger with no recovered history"
        assert receipt["git_fallback_used"] is True
        assert receipt["n_from_ledger_recovered"] == 0

    def test_the_fallback_can_be_forced_on_for_an_audit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(g, "SNAPSHOTS_JSONL", self._ledger(tmp_path, True))
        monkeypatch.setattr(g, "_git_revisions", lambda: [], raising=True)
        receipt: dict = {}
        g.collect_boards(receipt, git_fallback=True)
        assert receipt["git_fallback_used"] is True
        assert "forced" in receipt["git_fallback_reason"]

    def test_a_recovered_entry_grades_through_the_same_path_as_a_native_one(self, tmp_path,
                                                                            monkeypatch):
        """The recovery must not create a second schema: _board_to_record has to read a
        recovered line exactly as it reads a live one, extra keys and all."""
        monkeypatch.setattr(g, "SNAPSHOTS_JSONL", self._ledger(tmp_path, True))
        monkeypatch.setattr(g, "_git_revisions", lambda: [], raising=True)
        boards = g.collect_boards()
        assert [r["ticker"] for r in boards[0]["rows"]] == ["AAA"]
        assert boards[0]["rows"][0]["lane"] == "buy"
        assert boards[0]["rank_by"] == "conviction"


class TestShallowCheckoutIsDisclosedEitherWay:
    def _lines(self, capsys, title):
        return [ln for ln in capsys.readouterr().out.splitlines() if title in ln]

    def test_before_the_recovery_it_is_an_OUTAGE_warning(self, capsys):
        assert g.warn_if_history_truncated(
            {"n_git_revisions": 1, "n_boards": 17, "n_from_git": 0,
             "n_from_ledger_recovered": 0, "n_from_ledger_live": 17}) is True
        hits = self._lines(capsys, "us-board-ledger-history-truncated")
        assert hits and hits[0].startswith("::warning")
        assert "fetch-depth" in hits[0]

    def test_after_the_recovery_it_is_a_NOTICE_that_names_the_numbers(self, capsys):
        assert g.warn_if_history_truncated(
            {"n_git_revisions": 1, "n_boards": 32, "n_from_git": 0,
             "n_from_ledger_recovered": 15, "n_from_ledger_live": 17}) is True
        out = capsys.readouterr().out
        hits = [ln for ln in out.splitlines()
                if "us-board-ledger-history-from-recovery" in ln]
        assert hits, "a shallow checkout must never be a silent zero"
        assert hits[0].startswith("::notice"), "annotation must start the line"
        assert "15" in hits[0] and "32" in hits[0]
        assert not [ln for ln in out.splitlines() if ln.startswith("::warning")], \
            "an expected steady state must not fire the outage alarm every night"

    def test_a_full_checkout_stays_silent(self, capsys):
        assert g.warn_if_history_truncated(
            {"n_git_revisions": 524, "n_boards": 32, "n_from_git": 15,
             "n_from_ledger_recovered": 0, "n_from_ledger_live": 17}) is False
        assert not [ln for ln in capsys.readouterr().out.splitlines()
                    if ln.startswith("::")]


# --------------------------------------------------------------------------- #
# 6 — the recovery run is ADDITIVE: it may not restate a published row
# --------------------------------------------------------------------------- #
class TestRecoveryGradeIsAdditiveOnly:
    def _frames(self):
        import pandas as pd
        stored = pd.DataFrame([
            # a published row, carrying a column the local re-grade cannot reproduce
            {"as_of": "2026-06-15", "ticker": "AAA", "lane": "buy", "horizon": 5,
             "ret": 0.10, "position": 3, "opt_root_class": "weekly"},
        ])
        fresh = pd.DataFrame([
            # same key, DIFFERENT values, and no opt_root_class at all
            {"as_of": "2026-06-15", "ticker": "AAA", "lane": "buy", "horizon": 5,
             "ret": 0.99, "position": 41},
            # genuinely new key — the recovered history
            {"as_of": "2026-06-15", "ticker": "AAA", "lane": "buy", "horizon": 10,
             "ret": 0.22, "position": 41},
        ])
        return stored, fresh

    def test_a_key_the_store_already_holds_is_dropped(self):
        stored, fresh = self._frames()
        kept, n = g._drop_keys_already_stored(fresh, stored)
        assert n == 1
        assert len(kept) == 1
        assert kept.iloc[0]["horizon"] == 10, "the NEW horizon must survive"

    def test_the_published_values_survive_the_merge(self, tmp_path, monkeypatch):
        import pandas as pd
        stored, fresh = self._frames()
        parquet = tmp_path / "retro.parquet"
        stored.to_parquet(parquet, index=False)
        monkeypatch.setattr(g, "RETRO_PARQUET", parquet, raising=True)
        monkeypatch.setattr(g, "LEDGER_DIR", tmp_path, raising=True)

        kept, _ = g._drop_keys_already_stored(fresh, stored)
        merged = g._merge_into_store(kept)
        row = merged[(merged["horizon"] == 5)].iloc[0]
        assert row["ret"] == 0.10, "a published return was restated"
        assert row["position"] == 3, "a published rank was restated"
        assert row["opt_root_class"] == "weekly", \
            "a runner-stamped column was wiped by a local re-grade"
        assert len(merged) == 2, "the recovered horizon must still accrue"

    def test_MUTATION_without_the_filter_the_published_row_moves(self, tmp_path,
                                                                 monkeypatch):
        """Mutation check: skip the filter — the ordinary keep-fresh merge — and require
        the restatement to become visible. Without this, the test above would pass on a
        no-op filter."""
        import pandas as pd
        stored, fresh = self._frames()
        parquet = tmp_path / "retro.parquet"
        stored.to_parquet(parquet, index=False)
        monkeypatch.setattr(g, "RETRO_PARQUET", parquet, raising=True)
        monkeypatch.setattr(g, "LEDGER_DIR", tmp_path, raising=True)

        merged = g._merge_into_store(fresh)   # no filter
        row = merged[(merged["horizon"] == 5)].iloc[0]
        assert row["ret"] == 0.99 and pd.isna(row["opt_root_class"]), \
            "mutation did not take — the additive-only checks above are vacuous"

    def test_an_empty_store_is_left_alone(self):
        import pandas as pd
        _stored, fresh = self._frames()
        kept, n = g._drop_keys_already_stored(fresh, pd.DataFrame())
        assert n == 0 and len(kept) == len(fresh)
        kept, n = g._drop_keys_already_stored(fresh, None)
        assert n == 0 and len(kept) == len(fresh)

    def test_the_flag_is_off_by_default_so_the_nightly_is_unchanged(self):
        """The nightly must keep its keep-fresh merge — a grade is a deterministic
        recomputation and the freshest price cache should win there."""
        import argparse
        import inspect
        src = inspect.getsource(g.main)
        assert '"--additive-only"' in src or "'--additive-only'" in src
        ap = argparse.ArgumentParser()
        ap.add_argument("--additive-only", action="store_true")
        assert ap.parse_args([]).additive_only is False


# --------------------------------------------------------------------------- #
# 7 — the recovered history must not pool a broad screen into the live record
# --------------------------------------------------------------------------- #
class TestBroadScreenNeverEntersTheEpisodeLedger:
    def _boards(self, buy_n: int) -> list[dict]:
        return [{"as_of": g.LEDGER_HISTORY_FROM, "rank_by": "bottoming-alignment",
                 "rows": [{"ticker": f"T{i}", "lane": "buy", "position": i,
                           "sector": "Materials"} for i in range(buy_n)]}]

    def _names(self, buy_n: int):
        import pandas as pd
        idx = pd.bdate_range(start=g.LEDGER_HISTORY_FROM, periods=30)
        return pd.DataFrame(
            {f"T{i}": [100.0 + j * 0.1 for j in range(len(idx))] for i in range(buy_n)},
            index=idx)

    def test_a_120_name_board_inside_the_date_window_is_excluded_by_width(self):
        """Measured: the 2026-06-25 board AS PUBLISHED still carried 120 buy names, and
        `rank_by` reads the same on both sides of the narrowing. Date alone lets it in."""
        n = g.LEDGER_BROAD_SCREEN_BUY_MIN + 20
        led = g.emit_ledger(self._boards(n), self._names(n), None)
        hist = led["meta"]["history"]
        assert hist["n_boards"] == 0, "a broad screen must not enter the live record"
        assert not led["rows"], "120 excluded names must not produce a single episode"
        assert led["summary"]["n_matured"] == 0
        assert hist["n_boards_before_current_definition"] == 1
        assert hist["broad_screen_boards_in_window"] == [g.LEDGER_HISTORY_FROM]

    def test_a_selection_width_board_on_the_same_date_is_kept(self):
        """The guard must be about WIDTH, not about the date — otherwise it would delete
        the era it is meant to protect."""
        led = g.emit_ledger(self._boards(30), self._names(30), None)
        hist = led["meta"]["history"]
        assert hist["n_boards"] == 1
        assert hist["broad_screen_boards_in_window"] == []
        assert hist["n_boards_before_current_definition"] == 0
