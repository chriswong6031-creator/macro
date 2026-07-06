"""Unit tests for engine.neuralweb._law and engine.neuralweb._dates (R5 §5.2/§5.1).

Focused on the helpers in isolation; full integration coverage is in
tests/test_macro_context_authority.py.
"""
from __future__ import annotations


class TestToIso:
    """to_iso: four observed formats → ISO-8601 or None."""

    def test_iso_date(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso("2026-07-05") == "2026-07-05"

    def test_display_string_zero_padded(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso("Jul 05, 2026") == "2026-07-05"

    def test_display_string_single_digit_day(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso("Jan 1, 2026") == "2026-01-01"

    def test_iso_datetime_with_z(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso("2026-07-05T14:30:00Z") == "2026-07-05"

    def test_iso_datetime_with_space(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso("2026-07-05 06:00:00") == "2026-07-05"

    def test_none_input(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso(None) is None

    def test_empty_string(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso("") is None

    def test_unrecognised_string(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso("not-a-date") is None

    def test_integer_input(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso(20260705) is None  # type: ignore[arg-type]

    def test_all_month_abbreviations(self):
        """Verify all 12 month abbreviations round-trip correctly."""
        from engine.neuralweb._dates import to_iso
        cases = [
            ("Jan 15, 2026", "2026-01-15"),
            ("Feb 15, 2026", "2026-02-15"),
            ("Mar 15, 2026", "2026-03-15"),
            ("Apr 15, 2026", "2026-04-15"),
            ("May 15, 2026", "2026-05-15"),
            ("Jun 15, 2026", "2026-06-15"),
            ("Jul 15, 2026", "2026-07-15"),
            ("Aug 15, 2026", "2026-08-15"),
            ("Sep 15, 2026", "2026-09-15"),
            ("Oct 15, 2026", "2026-10-15"),
            ("Nov 15, 2026", "2026-11-15"),
            ("Dec 15, 2026", "2026-12-15"),
        ]
        for inp, expected in cases:
            assert to_iso(inp) == expected, f"to_iso({inp!r}) != {expected!r}"


class TestDisplayOnly:
    def test_sets_flag(self):
        from engine.neuralweb._law import display_only
        d: dict = {"key": "val"}
        result = display_only(d)
        assert result["display_only"] is True

    def test_returns_same_object(self):
        from engine.neuralweb._law import display_only
        d: dict = {}
        assert display_only(d) is d

    def test_idempotent(self):
        from engine.neuralweb._law import display_only
        d: dict = {"display_only": True}
        display_only(d)
        assert d["display_only"] is True


class TestAssertNoAuthority:
    def test_clean_dict(self):
        from engine.neuralweb._law import assert_no_authority
        assert assert_no_authority({"foo": "bar"}) == []

    def test_all_authority_booleans_false(self):
        from engine.neuralweb._law import assert_no_authority
        ok = {k: False for k in ("can_add_candidates", "can_raise_size",
                                  "can_lower_size", "can_block_entry", "can_force_exit")}
        assert assert_no_authority(ok) == []

    def test_truthy_boolean_detected(self):
        from engine.neuralweb._law import assert_no_authority
        for key in ("can_add_candidates", "can_raise_size", "can_lower_size",
                    "can_block_entry", "can_force_exit"):
            violations = assert_no_authority({key: True})
            assert violations, f"{key}=True should be a violation"

    def test_article2_key_detected(self):
        from engine.neuralweb._law import assert_no_authority
        for key in ("alert_triage", "board_ordering", "top_setups",
                    "attention_queue", "push_floor"):
            violations = assert_no_authority({key: "anything"})
            assert violations, f"Article-2 key {key!r} should be flagged"

    def test_non_empty_scored_path_surfaces(self):
        from engine.neuralweb._law import assert_no_authority
        assert assert_no_authority({"scored_path_surfaces": ["x"]}) != []

    def test_empty_scored_path_surfaces_ok(self):
        from engine.neuralweb._law import assert_no_authority
        assert assert_no_authority({"scored_path_surfaces": []}) == []

    def test_nested_violation(self):
        from engine.neuralweb._law import assert_no_authority
        nested = {"a": {"b": {"can_force_exit": True}}}
        violations = assert_no_authority(nested)
        assert any("can_force_exit" in v for v in violations)

    def test_list_traversal(self):
        from engine.neuralweb._law import assert_no_authority
        obj = [{"can_add_candidates": True}]
        violations = assert_no_authority(obj)
        assert violations

    def test_scalar_no_crash(self):
        from engine.neuralweb._law import assert_no_authority
        assert assert_no_authority(42) == []  # type: ignore[arg-type]
        assert assert_no_authority("hello") == []  # type: ignore[arg-type]
        assert assert_no_authority(None) == []  # type: ignore[arg-type]
