"""tests/test_prophet_lifecycle_state.py — §J.9(c) lifecycle projection (PR-0(c)).

Pins the deliverable of research/PROPHET_RULING_J9C_J10_LIFECYCLE_CELLS.md §6/§9:
`lifecycle_state` is a DERIVED, display-tier, total projection over fields the
builder already publishes (`phase`, `closed`, the bridge's union watch receipt).

WHY THIS FILE IS ADVERSARIAL ABOUT PRODUCERS
--------------------------------------------
The defect this whole ruling exists to close is a vocabulary value with NO producer:
the shipped 4-dot rail renders `stage=2` (Turning) and `stage=4` (Trend), and no code
path has ever assigned either — 828 buy-row observations across 18 ledger snapshots
carry zero of them, so half the journey users were shown could not light (§1.1). Two
classes of test here exist purely to stop that recurring:

  * NO-DEAD-CELL (§9.6b) — every phase a cell claims must be a phase the management
    engine actually produces. If a phase is ever dropped from `_VALID_PHASES`, the
    cell census goes RED rather than silently zeroing a cell.
  * KEY-ABSENCE vs ZERO (§9.6c) — "the watch tier did not publish" and "the watch
    tier published and nothing fired" are different facts. Collapsing them to a silent
    0 is the same defect wearing a different hat, which is exactly what happened while
    the intake exporter's closed whitelist dropped `early_turn_watch` entirely.

And the count law (§6) is mutation-checked rather than recomputed: a receipt derived
from the same variable it checks cannot fail, so the partition tests FLIP an input and
assert the published block MOVES.

Run:
    .venv/bin/python -m pytest tests/test_prophet_lifecycle_state.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ── repo path ─────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import scripts.build_prophet as bp  # noqa: E402
from engine.prophet_management import _VALID_PHASES  # noqa: E402  (repo path first)


# ── fixtures ──────────────────────────────────────────────────────────────────

def _row(plan_id: str, asset: str, phase: str, *, closed: bool = False,
         recorded_at: str = "2026-08-10T00:00:00Z") -> dict:
    """One index plan row, carrying only the fields the projection reads."""
    return {"id": plan_id, "asset": asset, "phase": phase,
            "closed": closed, "recorded_at": recorded_at}


def _book() -> list[dict]:
    """A book touching every plan-row cell at least once.

    `overtime` and `at_t2` are zero on the live payload but have real producers in
    the management engine — a producing cell at zero is honest inventory, so they are
    exercised here rather than assumed dead.
    """
    return [
        _row("p-ready-1", "AAA", "pre_trigger"),
        _row("p-ready-2", "BBB", "pre_trigger"),
        _row("p-entered", "CCC", "triggered_pre_t1"),
        _row("p-deliv-1", "DDD", "at_t1"),
        _row("p-deliv-2", "EEE", "between_t1_t2"),
        _row("p-deliv-3", "FFF", "at_t2"),
        _row("p-overtime", "GGG", "overtime"),
        _row("p-invalid", "HHH", "invalidated"),
        # A closed row whose frozen phase is a LIVE one: `closed` outranks phase.
        _row("p-resolved", "III", "between_t1_t2", closed=True),
    ]


# ── §6 derivation: precedence, disjointness, totality ─────────────────────────

class TestPrecedence:
    """§6's derivation, implemented literally: first match wins, terminal else-arm."""

    @pytest.mark.parametrize("phase,cell", [
        ("pre_trigger",      "ready"),
        ("triggered_pre_t1", "entered"),
        ("at_t1",            "delivering"),
        ("between_t1_t2",    "delivering"),
        ("at_t2",            "delivering"),
        ("overtime",         "overtime"),
        ("invalidated",      "invalidated"),
    ])
    def test_open_row_maps_by_phase(self, phase, cell):
        assert bp.lifecycle_state(_row("x", "AAA", phase)) == cell

    @pytest.mark.parametrize("phase", sorted(_VALID_PHASES))
    def test_closed_outranks_every_phase(self, phase):
        """Rule 1 fires before any phase rule — a closed plan is resolved whatever
        phase it froze at.  Ordering this the other way would file a closed,
        graded-out `invalidated` plan as live inventory."""
        assert bp.lifecycle_state(_row("x", "AAA", phase, closed=True)) == "resolved"

    def test_every_valid_phase_maps_without_warning(self, capsys):
        """Totality over the engine's real domain: no `_VALID_PHASES` value falls to
        the unknown arm."""
        for phase in sorted(_VALID_PHASES):
            bp.lifecycle_state(_row("x", "AAA", phase))
        assert "::warning" not in capsys.readouterr().out

    @pytest.mark.parametrize("phase", ["", None, "post_t2", "confirming", "banana"])
    def test_unknown_phase_degrades_to_ready_and_discloses(self, phase, capsys):
        """An unknown state is never advertised as further along than it can be proven
        to be — and it announces itself rather than sitting in `ready` silently."""
        assert bp.lifecycle_state(_row("p-1", "AAA", phase)) == "ready"
        out = capsys.readouterr().out
        line = next(ln for ln in out.splitlines() if "prophet-lifecycle-unknown-phase" in ln)
        # House annotation law: the marker must START the line, or GitHub drops it.
        assert line.startswith("::warning"), f"annotation not at line start: {line!r}"
        assert "p-1" in line and "AAA" in line

    def test_internal_superset_phases_are_not_silently_live(self, capsys):
        """`post_t1_failed_hold` / `post_t2` are INTERNAL detection phases that the
        management engine maps to schema phases before publishing.  If one ever leaks
        onto a published row, it must land in the disclosed unknown arm — never be
        quietly absorbed into `delivering`."""
        for phase in ("post_t1_failed_hold", "post_t2"):
            assert phase not in _VALID_PHASES
            assert bp.lifecycle_state(_row("x", "AAA", phase)) == "ready"
        assert capsys.readouterr().out.count("prophet-lifecycle-unknown-phase") == 2


# ── §9.6b no-dead-cell law ────────────────────────────────────────────────────

class TestNoDeadCell:
    """Every cell must have a producer that is live TODAY.  This is the stage=4
    defect's tripwire: a cell whose phase the engine no longer emits goes red here
    instead of shipping as a step users can never reach."""

    def test_every_claimed_phase_is_a_phase_the_engine_produces(self):
        claimed = set().union(*bp.LIFECYCLE_PHASE_CELLS.values())
        orphans = claimed - set(_VALID_PHASES)
        assert not orphans, (
            f"lifecycle cells claim phase(s) the management engine does not produce: "
            f"{sorted(orphans)} — a cell with no producer is the stage=4 defect reborn"
        )

    def test_every_engine_phase_is_claimed_by_exactly_one_cell(self):
        """The other direction: no published phase may fall through to the unknown
        arm, and no phase may be claimed twice (disjointness at the map level)."""
        seen: dict[str, str] = {}
        for cell, phases in bp.LIFECYCLE_PHASE_CELLS.items():
            for phase in phases:
                assert phase not in seen, (
                    f"phase {phase!r} claimed by both {seen[phase]!r} and {cell!r}"
                )
                seen[phase] = cell
        assert set(seen) == set(_VALID_PHASES), (
            f"phase coverage gap: unclaimed={sorted(set(_VALID_PHASES) - set(seen))}"
        )

    def test_cell_set_is_exactly_the_ruling_seven(self):
        assert bp.LIFECYCLE_CELLS == (
            "watch", "ready", "entered", "delivering", "overtime", "invalidated",
            "resolved",
        )

    def test_live_cells_exclude_resolved_only(self):
        """`resolved` sits OUTSIDE the headline total deliberately: a headline that
        counts graded-out plans as inventory sells non-actionable states."""
        assert set(bp.LIFECYCLE_CELLS) - set(bp.LIFECYCLE_LIVE_CELLS) == {"resolved"}

    def test_precedence_covers_every_phase_keyed_cell(self):
        assert set(bp.LIFECYCLE_PRECEDENCE) == set(bp.LIFECYCLE_PHASE_CELLS)


# ── §9.6d lexicon pairing ─────────────────────────────────────────────────────

class TestLexiconPairing:
    """Both languages, all-or-nothing.  A cell shipping EN with no ZH is a half-built
    ladder on a bilingual estate."""

    def test_en_and_zh_cover_exactly_the_cells(self):
        assert set(bp.LIFECYCLE_LABELS_EN) == set(bp.LIFECYCLE_CELLS)
        assert set(bp.LIFECYCLE_LABELS_ZH) == set(bp.LIFECYCLE_CELLS)

    @pytest.mark.parametrize("cell", ["watch", "ready", "entered", "delivering",
                                      "overtime", "invalidated", "resolved"])
    def test_both_labels_non_empty(self, cell):
        assert bp.LIFECYCLE_LABELS_EN[cell].strip()
        assert bp.LIFECYCLE_LABELS_ZH[cell].strip()

    def test_zh_labels_are_the_ruling_arc_verbatim(self):
        """The ZH arc is native two-character vocabulary that converges with words the
        card already ships (失效价 · 已结 · 超时 · 入场), not translated English — and
        入场 is the estate's majority form, so the ladder must not mint 进场."""
        assert bp.LIFECYCLE_LABELS_ZH == {
            "watch": "观察", "ready": "就绪", "entered": "入场", "delivering": "达标",
            "overtime": "超时", "invalidated": "失效", "resolved": "已结",
        }

    def test_no_label_leaks_a_phase_slug_or_the_retired_word(self):
        """Glance-tier word law: raw slugs never render, and §7 retires "stage" from
        all user-facing Prophet vocabulary."""
        for label in (*bp.LIFECYCLE_LABELS_EN.values(), *bp.LIFECYCLE_LABELS_ZH.values()):
            assert "_" not in label
            assert "stage" not in label.lower()
            assert "阶段" not in label

    def test_labels_carry_no_falsifier_language(self):
        """Operator 2026-07-27 (#3821): falsifier/refutation vocabulary is never
        front-facing.  "Invalidated / 失效" is compliant — it names the plan's own
        stated invalidation level being hit — but "falsifier fired / 证伪" stays banned."""
        for label in (*bp.LIFECYCLE_LABELS_EN.values(), *bp.LIFECYCLE_LABELS_ZH.values()):
            low = label.lower()
            assert "falsif" not in low and "refut" not in low
            assert "证伪" not in label


# ── §9.6a partition law + the count law, mutation-checked ─────────────────────

class TestPartitionAndCounts:

    def test_every_row_maps_to_exactly_one_cell(self):
        rows = _book()
        counts, _live, _grand = bp.lifecycle_projection(rows, [])
        assert all(r["lifecycle_state"] in bp.LIFECYCLE_CELLS for r in rows)
        # Exhaustive AND disjoint: the cells sum to the row count, once each.
        assert sum(v for c, v in counts.items() if c != "watch") == len(rows)

    def test_counts_block_is_the_seven_cells_in_funnel_order(self):
        counts, _l, _g = bp.lifecycle_projection(_book(), ["ZZZ"])
        assert list(counts) == list(bp.LIFECYCLE_CELLS)

    def test_live_total_equals_open_count_plus_watch(self):
        """§6 invariant 1 — the headline binder."""
        rows = _book()
        watch = ["ZZZ", "YYY"]
        counts, live, _grand = bp.lifecycle_projection(rows, watch)
        open_count = sum(1 for r in rows if not r.get("closed"))
        assert live == open_count + len(watch)
        assert counts["resolved"] not in (None,)  # resolved is excluded from `live`
        assert live == sum(counts[c] for c in bp.LIFECYCLE_LIVE_CELLS)

    def test_grand_total_equals_active_count_plus_watch(self):
        """§6 invariant 2."""
        rows = _book()
        watch = ["ZZZ"]
        _counts, live, grand = bp.lifecycle_projection(rows, watch)
        assert grand == len(rows) + len(watch)
        assert grand == live + _counts["resolved"]

    def test_flipping_closed_moves_the_block(self):
        """§6 count law, made mechanical: the published counts may not be
        derivable-but-unchecked.  Mutate ONE row and assert the block moves — a
        receipt computed from the same variable it checks cannot fail."""
        rows = _book()
        before, live_before, grand_before = bp.lifecycle_projection(rows, [])

        target = next(r for r in rows if r["id"] == "p-invalid")
        assert target["lifecycle_state"] == "invalidated"
        target["closed"] = True

        after, live_after, grand_after = bp.lifecycle_projection(rows, [])

        assert target["lifecycle_state"] == "resolved", "the row's own field must move"
        assert after["invalidated"] == before["invalidated"] - 1
        assert after["resolved"] == before["resolved"] + 1
        assert live_after == live_before - 1, "a closed plan leaves the headline total"
        assert grand_after == grand_before, "the book did not change size"

    def test_flipping_phase_moves_the_block(self):
        """The same law on the other axis — `phase` is the second input."""
        rows = _book()
        before, live_before, _g = bp.lifecycle_projection(rows, [])
        next(r for r in rows if r["id"] == "p-ready-1")["phase"] = "overtime"
        after, live_after, _g2 = bp.lifecycle_projection(rows, [])
        assert after["ready"] == before["ready"] - 1
        assert after["overtime"] == before["overtime"] + 1
        assert live_after == live_before, "overtime is still a LIVE cell"

    def test_empty_book_does_not_pass_vacuously(self):
        """An empty run must produce a real zeroed block, not an absent one — and the
        totals must still be internally consistent."""
        counts, live, grand = bp.lifecycle_projection([], [])
        assert list(counts) == list(bp.LIFECYCLE_CELLS)
        assert live == 0 and grand == 0
        assert set(counts.values()) == {0}


# ── §9.6c key-absence vs zero (the watch cell) ────────────────────────────────

class TestWatchKeyAbsenceVsZero:
    """"The watch tier did not publish" and "it published and nothing fired" are
    different facts.  A silent 0 for the first is the producer-less-cell defect."""

    def test_absent_key_yields_none_not_empty(self):
        assert bp.prophet_watch_roster({}) is None
        assert bp.prophet_watch_roster({"admitted": 3}) is None

    def test_present_empty_key_yields_empty_not_none(self):
        assert bp.prophet_watch_roster({"early_turn_watch": []}) == []

    def test_absent_roster_omits_the_watch_cell_entirely(self):
        counts, live, grand = bp.lifecycle_projection(_book(), None)
        assert "watch" not in counts, (
            "an unpublished watch tier must be a DISCLOSED ABSENCE — omitting the key "
            "— never a silent 0 that reads as 'nothing fired'"
        )
        rows = _book()
        assert live == sum(1 for r in rows if not r.get("closed"))
        assert grand == len(rows)

    def test_published_empty_roster_reports_a_real_zero(self):
        counts, _live, _grand = bp.lifecycle_projection(_book(), [])
        assert counts["watch"] == 0, (
            "a published-but-empty roster is honest inventory at zero, and must be "
            "distinguishable from the absent case"
        )

    def test_the_two_cases_are_distinguishable_downstream(self):
        absent, _l1, _g1 = bp.lifecycle_projection(_book(), None)
        empty, _l2, _g2 = bp.lifecycle_projection(_book(), [])
        assert ("watch" in absent) is not ("watch" in empty)

    def test_none_propagates_through_the_cell_helper(self):
        assert bp.lifecycle_watch_cell(None, _book()) is None


# ── §9.1a intake pass-through, and the wrong-producer guard ───────────────────

class TestWatchRosterPassThrough:
    """The bridge has computed this roster since #5370; the exporter's closed
    key-by-key whitelist dropped it, so the watch cell had no published producer.
    That is the SILENT SIBLING shape — the field existed, nothing carried it."""

    def test_bridge_list_of_str_passes_through(self):
        assert bp.prophet_watch_roster(
            {"early_turn_watch": ["AAA", "BBB"]}) == ["AAA", "BBB"]

    def test_basket_score_shaped_value_is_withheld_not_coerced(self, capsys):
        """engine/basket_score.py publishes a same-named `list[dict]` (ruling §2 note
        c).  Sourcing it must NOT silently coerce to [] — that would publish "the
        watch tier fired nothing", a false fact, where the truth is "wrong producer"."""
        basket_shaped = [{"en": "early turn watch", "zh": "早期转向观察"}]
        assert bp.prophet_watch_roster({"early_turn_watch": basket_shaped}) is None
        line = next(ln for ln in capsys.readouterr().out.splitlines()
                    if "prophet-lifecycle-watch-shape" in ln)
        assert line.startswith("::warning"), f"annotation not at line start: {line!r}"

    def test_the_bridge_is_the_declared_producer_and_ships_list_of_str(self):
        """Pins the producer end of the contract: the bridge seeds a `list[str]` and
        writes it onto the caller's intake dict.  If that shape ever changes, this
        fails HERE rather than the exporter silently withholding the cell forever."""
        import inspect

        import engine.prophet_bridge as pbr
        src = inspect.getsource(pbr)
        assert "early_turn_watch: list[str] = []" in src
        assert 'intake_stats["early_turn_watch"] = sorted(early_turn_watch)' in src

    def test_watch_cell_subtracts_open_plans_but_not_closed_ones(self):
        """§6: minus OPEN rows, not minus ANY.  A fresh union fire on a name whose
        only plans are closed is a live watch state, not a resolved one."""
        rows = [
            _row("open-1", "AAA", "pre_trigger"),
            _row("closed-1", "BBB", "between_t1_t2", closed=True),
        ]
        # AAA holds an open plan → not on watch.  BBB's only plan is closed → watch.
        assert bp.lifecycle_watch_cell(["AAA", "BBB", "CCC"], rows) == ["BBB", "CCC"]

    def test_watch_cell_is_disjoint_from_the_open_book(self):
        rows = _book()
        roster = [r["asset"] for r in rows] + ["ZZZ"]
        cell = bp.lifecycle_watch_cell(roster, rows)
        open_tickers = {r["asset"] for r in rows if not r.get("closed")}
        assert not (set(cell) & open_tickers)
        assert "III" in cell, "the closed-only name stays watchable"
        assert "ZZZ" in cell


# ── §9.6e per-ticker projection (FBRT-shaped duplicate plans) ─────────────────

class TestPerTickerProjection:
    """Ticker-keyed surfaces (landing showcase, stock-detail and dossier chips) render
    one card per NAME.  The row-granular cell cannot serve them: 13 of 127 tickers
    carried two rows on the ruling's reference payload."""

    def _fbrt(self) -> list[dict]:
        """The live exemplar, verbatim in shape: FBRT held one plan closed 07-13 in
        `resolved` and one open plan from 08-05 in `ready`, on the same night."""
        return [
            _row("FBRT-2026-07-13", "FBRT", "between_t1_t2", closed=True,
                 recorded_at="2026-07-13T00:00:00Z"),
            _row("FBRT-2026-08-05", "FBRT", "pre_trigger",
                 recorded_at="2026-08-05T00:00:00Z"),
        ]

    def test_duplicate_plan_ticker_occupies_two_cells_at_ROW_granularity(self):
        """The unit of account is the plan row, and two rows is the honest count:
        they are two separate tracked commitments."""
        rows = self._fbrt()
        counts, _live, _grand = bp.lifecycle_projection(rows, [])
        assert counts["resolved"] == 1 and counts["ready"] == 1

    def test_per_ticker_projection_is_single_valued(self):
        rows = self._fbrt()
        bp.lifecycle_projection(rows, [])
        by_ticker = bp.lifecycle_state_by_ticker(rows, [])
        assert list(by_ticker) == ["FBRT"]
        assert by_ticker["FBRT"] == "ready", "the newest OPEN row wins"

    def test_newest_open_row_wins_regardless_of_input_order(self):
        rows = [
            _row("p-old", "AAA", "pre_trigger", recorded_at="2026-07-01T00:00:00Z"),
            _row("p-new", "AAA", "overtime", recorded_at="2026-08-05T00:00:00Z"),
        ]
        assert bp.lifecycle_state_by_ticker(rows)["AAA"] == "overtime"
        assert bp.lifecycle_state_by_ticker(list(reversed(rows)))["AAA"] == "overtime"

    def test_recorded_at_tie_breaks_on_id_deterministically(self):
        rows = [
            _row("p-a", "AAA", "pre_trigger", recorded_at="2026-08-05T00:00:00Z"),
            _row("p-b", "AAA", "overtime", recorded_at="2026-08-05T00:00:00Z"),
        ]
        assert bp.lifecycle_state_by_ticker(rows)["AAA"] == "overtime"
        assert bp.lifecycle_state_by_ticker(list(reversed(rows)))["AAA"] == "overtime"

    def test_watch_outranks_a_finished_episode(self):
        """§6: a live fire outranks a finished episode."""
        rows = [_row("p-done", "AAA", "at_t2", closed=True)]
        assert bp.lifecycle_state_by_ticker(rows, ["AAA"])["AAA"] == "watch"

    def test_closed_only_ticker_with_no_watch_fire_is_resolved(self):
        rows = [_row("p-done", "AAA", "at_t2", closed=True)]
        assert bp.lifecycle_state_by_ticker(rows, [])["AAA"] == "resolved"

    def test_every_ticker_in_the_book_gets_exactly_one_cell(self):
        rows = _book() + self._fbrt()
        by_ticker = bp.lifecycle_state_by_ticker(rows, ["ZZZ"])
        assert set(by_ticker) == {r["asset"] for r in rows} | {"ZZZ"}
        assert all(v in bp.LIFECYCLE_CELLS for v in by_ticker.values())

    def test_projection_does_not_stamp_rows(self):
        """It is a READ-ONLY projection — `lifecycle_projection()` owns the stamp."""
        rows = self._fbrt()
        bp.lifecycle_state_by_ticker(rows, [])
        assert not any("lifecycle_state" in r for r in rows)


# ── §2.4 rider: the dead constants are gone ───────────────────────────────────

class TestDeadConstantsDeleted:
    """A vocabulary value with no producer is how the estate got an unlightable dot;
    we do not keep two more in stock."""

    def test_confirming_and_confirmed_are_deleted(self):
        import engine.us_early_turn as uet
        for name in ("STAGE_CONFIRMING", "STAGE_CONFIRMED"):
            assert not hasattr(uet, name), (
                f"{name} was never assigned anywhere — §2.4 deletes it rather than "
                f"leaving a producer-less vocabulary value in stock"
            )

    def test_the_one_assigned_constant_survives(self):
        """`STAGE_EARLY` is the operator-ratified admission-lane fact column."""
        import engine.us_early_turn as uet
        assert uet.STAGE_EARLY == "EARLY"


# ── the field ships DARK ──────────────────────────────────────────────────────

def test_no_prophet_surface_renders_lifecycle_state_yet():
    """§9: "Explicitly not in PR-0(c): any template/rail change... The field ships
    dark; surfaces adopt at migration."  This fails loudly if a Prophet surface starts
    reading the field before the Board migration lands its ladder + same-PR rail
    retirement (§10.1) — two lifecycle vocabularies may never co-render on one card.

    Scoped to PROPHET surfaces on purpose.  `lifecycle_state` is not a unique token in
    this estate: templates/capital_structure.js reads an unrelated
    `event.lifecycle_state` off the capital-structure event payload, a different
    program with a different contract.  Scoping by "does this file mention Prophet at
    all" separates the two namespaces without an exemption list to rot.
    """
    hits = []
    for path in sorted((_REPO / "templates").rglob("*")):
        if not path.is_file() or path.suffix not in {".j2", ".html", ".js", ".css"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "prophet" in text.lower() and "lifecycle_state" in text:
            hits.append(path.relative_to(_REPO).as_posix())
    assert not hits, (
        f"lifecycle_state is rendered by Prophet surface(s) {hits} — PR-0(c) ships the "
        f"field DARK; a surface adopting it must also retire the 4-dot rail in the "
        f"SAME PR (§10.1)"
    )
