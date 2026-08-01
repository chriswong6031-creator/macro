"""tests/test_ai_costs.py — unit tests for lib/ai_costs.py.

Coverage:
  - record_usage happy path (row fields, file created)
  - cost computation for metered + subscription + cache tokens
  - prefix-model matching in estimate_cost_usd
  - corrupt-line tolerance in read_usage
  - summarize aggregates (today / d7 / d30 / by_lane / by_model)
  - NEVER-RAISE on unwritable root (record_usage returns False, no exception)
  - key_pool_probe._PROBE_ENVS contains all 7 numbered keys + legacy
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


# ── helpers ───────────────────────────────────────────────────────────────────

def _write_pricing(tmp_path: Path) -> Path:
    """Write a minimal ai_pricing.yml under tmp_path and return its path."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    pricing_path = cfg_dir / "ai_pricing.yml"
    pricing_path.write_text(
        "schema: ai_pricing.v1\n"
        "per_mtok:\n"
        "  claude-sonnet-4-6:\n"
        "    input: 3.00\n"
        "    output: 15.00\n"
        "  claude-haiku-4-5:\n"
        "    input: 1.00\n"
        "    output: 5.00\n"
        "cache:\n"
        "  read_multiplier: 0.10\n"
        "  write_5m_multiplier: 1.25\n",
        encoding="utf-8",
    )
    return pricing_path


# ── cost computation ──────────────────────────────────────────────────────────

class TestEstimateCostUsd:
    def test_basic_metered(self, tmp_path: Path) -> None:
        _write_pricing(tmp_path)
        from lib.ai_costs import estimate_cost_usd  # type: ignore[import]

        # 1M input + 1M output for claude-sonnet-4-6 = 3.00 + 15.00 = 18.00
        cost = estimate_cost_usd(
            "claude-sonnet-4-6", 1_000_000, 1_000_000, root=tmp_path
        )
        assert cost is not None
        assert abs(cost - 18.00) < 1e-6

    def test_prefix_match_versioned_model(self, tmp_path: Path) -> None:
        """A versioned model id like claude-haiku-4-5-20251001 must match claude-haiku-4-5."""
        _write_pricing(tmp_path)
        from lib.ai_costs import estimate_cost_usd

        cost = estimate_cost_usd(
            "claude-haiku-4-5-20251001", 1_000_000, 0, root=tmp_path
        )
        assert cost is not None
        assert abs(cost - 1.00) < 1e-6

    def test_cache_tokens(self, tmp_path: Path) -> None:
        """Cache read + creation tokens contribute to cost."""
        _write_pricing(tmp_path)
        from lib.ai_costs import estimate_cost_usd

        # 1M cache_read at in_rate*0.10 = 3.00 * 0.10 = 0.30
        # 1M cache_creation at in_rate*1.25 = 3.00 * 1.25 = 3.75
        cost = estimate_cost_usd(
            "claude-sonnet-4-6",
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=1_000_000,
            cache_creation_tokens=1_000_000,
            root=tmp_path,
        )
        assert cost is not None
        assert abs(cost - 4.05) < 1e-5

    def test_unknown_model_returns_none(self, tmp_path: Path) -> None:
        _write_pricing(tmp_path)
        from lib.ai_costs import estimate_cost_usd

        cost = estimate_cost_usd("gpt-99-turbo", 1000, 1000, root=tmp_path)
        assert cost is None

    def test_missing_pricing_file_returns_none(self, tmp_path: Path) -> None:
        """If the pricing file doesn't exist, returns None without raising."""
        from lib.ai_costs import estimate_cost_usd

        # tmp_path has no config/ai_pricing.yml
        cost = estimate_cost_usd("claude-sonnet-4-6", 100, 100, root=tmp_path)
        assert cost is None


# ── record_usage ──────────────────────────────────────────────────────────────

class TestRecordUsage:
    def test_happy_path_creates_ledger(self, tmp_path: Path) -> None:
        _write_pricing(tmp_path)
        from lib.ai_costs import record_usage, SCHEMA

        ok = record_usage(
            lane="test_lane",
            provider="claude_api",
            model="claude-sonnet-4-6",
            key_id=None,
            input_tokens=500,
            output_tokens=200,
            cost_basis="metered",
            root=tmp_path,
        )
        assert ok is True

        ledger = tmp_path / "data" / "ai_costs" / "usage.jsonl"
        assert ledger.exists()
        row = json.loads(ledger.read_text())
        assert row["schema"] == SCHEMA
        assert row["lane"] == "test_lane"
        assert row["provider"] == "claude_api"
        assert row["model"] == "claude-sonnet-4-6"
        assert row["input_tokens"] == 500
        assert row["output_tokens"] == 200
        assert row["cost_basis"] == "metered"
        # est_cost_usd should have been auto-computed
        assert row["est_cost_usd"] is not None
        assert row["est_cost_usd"] > 0

    def test_subscription_provider_no_billed_dollars(self, tmp_path: Path) -> None:
        """subscription cost_basis records API-equivalent value, not 0."""
        _write_pricing(tmp_path)
        from lib.ai_costs import record_usage

        ok = record_usage(
            lane="nightly",
            provider="claude_oauth",
            model="claude-haiku-4-5",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cost_basis="subscription",
            root=tmp_path,
        )
        assert ok is True
        ledger = tmp_path / "data" / "ai_costs" / "usage.jsonl"
        row = json.loads(ledger.read_text())
        # API-equivalent: 1 + 5 = 6.00
        assert row["est_cost_usd"] is not None
        assert abs(row["est_cost_usd"] - 6.00) < 1e-4

    def test_explicit_est_cost_not_overridden(self, tmp_path: Path) -> None:
        """When est_cost_usd is supplied explicitly it is stored as-is."""
        _write_pricing(tmp_path)
        from lib.ai_costs import record_usage

        ok = record_usage(
            lane="lane_x",
            provider="deepseek",
            model=None,
            input_tokens=100,
            output_tokens=50,
            est_cost_usd=0.001234,
            root=tmp_path,
        )
        assert ok is True
        row = json.loads(
            (tmp_path / "data" / "ai_costs" / "usage.jsonl").read_text()
        )
        assert abs(row["est_cost_usd"] - 0.001234) < 1e-9

    def test_all_fields_present(self, tmp_path: Path) -> None:
        """Every schema field is present in the emitted row."""
        _write_pricing(tmp_path)
        from lib.ai_costs import record_usage, SCHEMA

        record_usage(
            lane="l", provider="p", model="claude-sonnet-4-6",
            key_id="cap_1",
            input_tokens=10, output_tokens=5,
            cache_read_tokens=2, cache_creation_tokens=3,
            cost_basis="metered",
            cycle_id="cyc42", stage="build", note="hello",
            root=tmp_path,
        )
        row = json.loads(
            (tmp_path / "data" / "ai_costs" / "usage.jsonl").read_text()
        )
        required_keys = [
            "schema", "ts", "lane", "provider", "model", "key_id",
            "input_tokens", "output_tokens", "cache_read_tokens",
            "cache_creation_tokens", "est_cost_usd", "cost_basis",
            "cycle_id", "stage", "note",
        ]
        for k in required_keys:
            assert k in row, f"missing field: {k}"
        assert row["schema"] == SCHEMA
        assert row["cycle_id"] == "cyc42"
        assert row["stage"] == "build"
        assert row["note"] == "hello"
        assert row["cache_read_tokens"] == 2
        assert row["cache_creation_tokens"] == 3

    def test_never_raise_unwritable_root(self, tmp_path: Path) -> None:
        """record_usage returns False (not raises) when the ledger dir is unwritable."""
        from lib.ai_costs import record_usage

        # Point root at a path that is an existing FILE (cannot mkdir inside it)
        fake_root = tmp_path / "not_a_dir.txt"
        fake_root.write_text("x")

        ok = record_usage(
            lane="l", provider="p", root=Path(str(fake_root))
        )
        assert ok is False

    def test_appends_multiple_rows(self, tmp_path: Path) -> None:
        _write_pricing(tmp_path)
        from lib.ai_costs import record_usage

        for i in range(3):
            record_usage(lane=f"lane_{i}", provider="claude_api", root=tmp_path)

        ledger = tmp_path / "data" / "ai_costs" / "usage.jsonl"
        lines = [l for l in ledger.read_text().splitlines() if l.strip()]
        assert len(lines) == 3


# ── read_usage ────────────────────────────────────────────────────────────────

class TestReadUsage:
    def test_empty_ledger_returns_empty_list(self, tmp_path: Path) -> None:
        from lib.ai_costs import read_usage

        rows = read_usage(root=tmp_path)
        assert rows == []

    def test_corrupt_lines_skipped(self, tmp_path: Path) -> None:
        """Corrupt JSONL lines are skipped; valid lines are returned."""
        ledger = tmp_path / "data" / "ai_costs" / "usage.jsonl"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            '{"schema":"ai_costs.usage.v1","ts":"2026-01-01T00:00:00Z","lane":"a"}\n'
            "NOT_JSON_AT_ALL\n"
            '{"schema":"ai_costs.usage.v1","ts":"2026-01-02T00:00:00Z","lane":"b"}\n',
            encoding="utf-8",
        )
        from lib.ai_costs import read_usage

        rows = read_usage(root=tmp_path)
        assert len(rows) == 2
        assert rows[0]["lane"] == "a"
        assert rows[1]["lane"] == "b"

    def test_days_filter(self, tmp_path: Path) -> None:
        """days= parameter filters out old rows."""
        from lib.ai_costs import record_usage, read_usage

        _write_pricing(tmp_path)
        # Write a row that is fresh
        record_usage(lane="fresh", provider="p", root=tmp_path)

        # Manually inject an old row
        ledger = tmp_path / "data" / "ai_costs" / "usage.jsonl"
        old_row = json.dumps({
            "schema": "ai_costs.usage.v1",
            "ts": "2020-01-01T00:00:00Z",
            "lane": "old",
            "provider": "p",
        })
        with open(ledger, "a") as fh:
            fh.write(old_row + "\n")

        rows = read_usage(root=tmp_path, days=30)
        lanes = [r["lane"] for r in rows]
        assert "fresh" in lanes
        assert "old" not in lanes


# ── summarize ─────────────────────────────────────────────────────────────────

class TestSummarize:
    def test_structure_keys(self, tmp_path: Path) -> None:
        from lib.ai_costs import summarize

        result = summarize(root=tmp_path)
        assert set(result.keys()) >= {
            "today", "d7", "d30", "by_lane", "by_provider",
            "by_key", "by_model", "recent",
        }
        for period in ("today", "d7", "d30"):
            b = result[period]
            assert set(b.keys()) >= {"usd", "input_tokens", "output_tokens", "calls"}

    def test_aggregates_count_correctly(self, tmp_path: Path) -> None:
        _write_pricing(tmp_path)
        from lib.ai_costs import record_usage, summarize

        for i in range(4):
            record_usage(
                lane="test_lane",
                provider="claude_api",
                model="claude-sonnet-4-6",
                input_tokens=1000,
                output_tokens=500,
                root=tmp_path,
            )

        result = summarize(root=tmp_path)
        # All 4 rows were written just now → counted in today, d7, d30
        assert result["today"]["calls"] == 4
        assert result["d7"]["calls"] == 4
        assert result["d30"]["calls"] == 4
        assert result["today"]["input_tokens"] == 4000
        assert result["today"]["output_tokens"] == 2000

    def test_by_lane_aggregate(self, tmp_path: Path) -> None:
        _write_pricing(tmp_path)
        from lib.ai_costs import record_usage, summarize

        record_usage(lane="lane_a", provider="p", root=tmp_path)
        record_usage(lane="lane_a", provider="p", root=tmp_path)
        record_usage(lane="lane_b", provider="p", root=tmp_path)

        result = summarize(root=tmp_path)
        assert result["by_lane"]["lane_a"]["calls"] == 2
        assert result["by_lane"]["lane_b"]["calls"] == 1

    def test_by_model_aggregate(self, tmp_path: Path) -> None:
        _write_pricing(tmp_path)
        from lib.ai_costs import record_usage, summarize

        record_usage(lane="l", provider="p", model="claude-sonnet-4-6", root=tmp_path)
        record_usage(lane="l", provider="p", model="claude-haiku-4-5", root=tmp_path)
        record_usage(lane="l", provider="p", model="claude-sonnet-4-6", root=tmp_path)

        result = summarize(root=tmp_path)
        assert result["by_model"]["claude-sonnet-4-6"]["calls"] == 2
        assert result["by_model"]["claude-haiku-4-5"]["calls"] == 1

    def test_recent_newest_first_max_50(self, tmp_path: Path) -> None:
        _write_pricing(tmp_path)
        from lib.ai_costs import record_usage, summarize

        for i in range(55):
            record_usage(lane=f"l{i}", provider="p", root=tmp_path)

        result = summarize(root=tmp_path)
        assert len(result["recent"]) == 50
        # newest first: last written lane is l54
        assert result["recent"][0]["lane"] == "l54"

    def test_never_raise_empty_root(self, tmp_path: Path) -> None:
        """summarize on a root with no ledger returns zero-bucket structure."""
        from lib.ai_costs import summarize

        result = summarize(root=tmp_path)
        assert result["today"]["calls"] == 0
        assert result["recent"] == []

    def test_never_raise_unreadable_root(self, tmp_path: Path) -> None:
        """summarize with a root pointing at a file returns empty without raising."""
        fake_root = tmp_path / "file.txt"
        fake_root.write_text("x")
        from lib.ai_costs import summarize

        result = summarize(root=fake_root)
        assert result["today"]["calls"] == 0


# ── key_pool_probe._PROBE_ENVS ─────────────────────────────────────────────────

class TestKeyPoolProbeEnvs:
    def test_all_seven_keys_present(self) -> None:
        """_PROBE_ENVS must cover keys _1 through _7 to match the workflow."""
        from scripts.key_pool_probe import _PROBE_ENVS  # type: ignore[import]

        numbered = [e for e in _PROBE_ENVS if e.startswith("CLAUDE_CODE_OAUTH_TOKEN_")]
        nums = {e.split("_")[-1] for e in numbered}
        expected = {"1", "2", "3", "4", "5", "6", "7"}
        assert expected == nums, f"Missing keys: {expected - nums}"

    def test_legacy_key_present(self) -> None:
        from scripts.key_pool_probe import _PROBE_ENVS

        assert "CLAUDE_CODE_OAUTH_TOKEN" in _PROBE_ENVS


# ── lobe taxonomy (lane → lobe) ────────────────────────────────────────────────

class TestLobeForLane:
    def test_exact_matches(self) -> None:
        from lib.ai_costs import lobe_for_lane
        assert lobe_for_lane("master-brain") == "Master Brain"
        assert lobe_for_lane("ask-brain") == "Mastermind"
        assert lobe_for_lane("cortex") == "Mastermind"
        assert lobe_for_lane("catalyst-tone") == "News"
        assert lobe_for_lane("qual-extraction") == "Qual"
        assert lobe_for_lane("whitehouse") == "Whitehouse"

    def test_prefix_matches(self) -> None:
        from lib.ai_costs import lobe_for_lane
        assert lobe_for_lane("metabolism-propose") == "Metabolism"
        assert lobe_for_lane("metabolism-build") == "Metabolism"
        assert lobe_for_lane("marketing-copywriter") == "Marketing"
        assert lobe_for_lane("marketing-breaking") == "Marketing"
        assert lobe_for_lane("brain-pro") == "Mastermind"
        assert lobe_for_lane("risk-radar-review") == "Risk"

    def test_unknown_and_empty(self) -> None:
        from lib.ai_costs import lobe_for_lane
        assert lobe_for_lane("totally-new-lane") == "Other"
        assert lobe_for_lane("") == "Other"
        assert lobe_for_lane(None) == "Other"

    def test_case_insensitive(self) -> None:
        from lib.ai_costs import lobe_for_lane
        assert lobe_for_lane("Metabolism-Propose") == "Metabolism"


# ── summarize rollups (by_lobe / percentages / cost_basis) ─────────────────────

class TestSummarizeRollups:
    def test_by_lobe_rollup(self, tmp_path: Path) -> None:
        _write_pricing(tmp_path)
        from lib.ai_costs import record_usage, summarize
        record_usage(lane="metabolism-propose", provider="claude_oauth",
                     model="claude-sonnet-4-6", input_tokens=1000, output_tokens=500,
                     cost_basis="subscription", root=tmp_path)
        record_usage(lane="metabolism-build", provider="claude_oauth",
                     model="claude-sonnet-4-6", input_tokens=2000, output_tokens=1000,
                     cost_basis="subscription", root=tmp_path)
        record_usage(lane="master-brain", provider="deepseek",
                     model="claude-haiku-4-5", input_tokens=500, output_tokens=200,
                     cost_basis="metered", root=tmp_path)
        s = summarize(root=tmp_path)
        assert "Metabolism" in s["by_lobe"]
        assert s["by_lobe"]["Metabolism"]["calls"] == 2
        assert set(s["by_lobe"]["Metabolism"]["lanes"]) == {
            "metabolism-propose", "metabolism-build"}
        assert "master-brain" not in s["by_lobe"]["Metabolism"]["lanes"]
        assert s["by_lobe"]["Master Brain"]["calls"] == 1

    def test_percentages(self, tmp_path: Path) -> None:
        _write_pricing(tmp_path)
        from lib.ai_costs import record_usage, summarize
        for _ in range(3):
            record_usage(lane="solo", provider="claude_api", model="claude-sonnet-4-6",
                         input_tokens=1000, output_tokens=100, root=tmp_path)
        s = summarize(root=tmp_path)
        # a single lane must be 100% of both cost and tokens
        assert s["by_lane"]["solo"]["pct_usd"] == 100.0
        assert s["by_lane"]["solo"]["pct_tokens"] == 100.0
        assert "tokens" in s["by_lane"]["solo"]

    def test_cost_basis_split(self, tmp_path: Path) -> None:
        _write_pricing(tmp_path)
        from lib.ai_costs import record_usage, summarize
        record_usage(lane="a", provider="claude_oauth", model="claude-sonnet-4-6",
                     input_tokens=1000, output_tokens=100, cost_basis="subscription",
                     root=tmp_path)
        record_usage(lane="b", provider="deepseek", model="claude-haiku-4-5",
                     input_tokens=1000, output_tokens=100, cost_basis="metered",
                     root=tmp_path)
        s = summarize(root=tmp_path)
        assert s["by_cost_basis"]["subscription"]["calls"] == 1
        assert s["by_cost_basis"]["metered"]["calls"] == 1

    def test_ranked_lists_present(self, tmp_path: Path) -> None:
        _write_pricing(tmp_path)
        from lib.ai_costs import record_usage, summarize
        record_usage(lane="a", provider="p", root=tmp_path)
        s = summarize(root=tmp_path)
        for k in ("lobe_ranked", "by_lane_ranked", "by_provider_ranked",
                  "by_model_ranked", "by_key_ranked"):
            assert isinstance(s[k], list)


# ── shard merge (remote-sync mechanism) ────────────────────────────────────────

class TestShards:
    def test_shard_write_and_merge(self, tmp_path: Path, monkeypatch) -> None:
        from lib.ai_costs import record_usage, read_usage
        monkeypatch.delenv("AI_COSTS_SHARD", raising=False)
        record_usage(lane="master-brain", provider="deepseek", root=tmp_path)
        monkeypatch.setenv("AI_COSTS_SHARD", "metabolism-propose-run1-1")
        record_usage(lane="metabolism-propose", provider="claude_oauth", root=tmp_path)
        assert (tmp_path / "data/ai_costs/usage.jsonl").exists()
        assert (tmp_path / "data/ai_costs/usage.d/metabolism-propose-run1-1.jsonl").exists()
        rows = read_usage(root=tmp_path)
        assert sorted(r["lane"] for r in rows) == ["master-brain", "metabolism-propose"]

    def test_shard_name_sanitized(self, tmp_path: Path, monkeypatch) -> None:
        from lib.ai_costs import record_usage
        monkeypatch.setenv("AI_COSTS_SHARD", "weird/../name with spaces")
        record_usage(lane="x", provider="p", root=tmp_path)
        files = list((tmp_path / "data/ai_costs/usage.d").glob("*.jsonl"))
        assert len(files) == 1
        assert "/" not in files[0].name and ".." not in files[0].stem


class TestExternalStateRoot:
    def test_env_redirects_mutable_ledgers_but_not_pricing(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from lib import ai_costs

        repo = tmp_path / "repo"
        runtime = tmp_path / "runtime"
        _write_pricing(repo)
        monkeypatch.setattr(ai_costs, "_repo_root", lambda: repo)
        monkeypatch.setenv("AI_COSTS_STATE_ROOT", str(runtime))
        monkeypatch.delenv("AI_COSTS_SHARD", raising=False)

        assert ai_costs.record_usage(
            lane="earnings_qual",
            provider="deepseek",
            model="claude-haiku-4-5",
            input_tokens=1_000,
            output_tokens=100,
        ) is True

        ledger = runtime / "data" / "ai_costs" / "usage.jsonl"
        assert ledger.exists()
        assert not (repo / "data" / "ai_costs" / "usage.jsonl").exists()
        rows = ai_costs.read_usage()
        assert len(rows) == 1
        assert rows[0]["lane"] == "earnings_qual"
        assert rows[0]["est_cost_usd"] is not None

    def test_explicit_root_still_wins(self, tmp_path: Path, monkeypatch) -> None:
        from lib.ai_costs import record_usage

        runtime = tmp_path / "runtime"
        explicit = tmp_path / "explicit"
        monkeypatch.setenv("AI_COSTS_STATE_ROOT", str(runtime))
        assert record_usage(lane="x", provider="p", root=explicit) is True
        assert (explicit / "data" / "ai_costs" / "usage.jsonl").exists()
        assert not runtime.exists()


# ── direct-SDK capture helpers ─────────────────────────────────────────────────

class TestCaptureHelpers:
    def test_infer_provider(self) -> None:
        from lib.ai_costs import infer_provider
        assert infer_provider("https://api.deepseek.com/anthropic") == ("deepseek", "metered")
        assert infer_provider(None, oauth=True) == ("claude_oauth", "subscription")
        assert infer_provider(None) == ("claude_api", "metered")
        assert infer_provider("http://localhost:8000/v1") == ("openai_compat", "metered")

    def test_record_response_usage(self, tmp_path: Path) -> None:
        _write_pricing(tmp_path)
        from lib.ai_costs import record_response_usage, read_usage

        class _U:
            input_tokens = 1200
            output_tokens = 340
            cache_read_input_tokens = 0
            cache_creation_input_tokens = 0

        class _Resp:
            usage = _U()

        ok = record_response_usage(
            lane="qual-extraction", response=_Resp(), model="claude-haiku-4-5",
            provider="deepseek", cost_basis="metered", root=tmp_path)
        assert ok is True
        rows = read_usage(root=tmp_path)
        assert len(rows) == 1
        assert rows[0]["lane"] == "qual-extraction"
        assert rows[0]["input_tokens"] == 1200

    def test_record_response_usage_no_usage_object(self, tmp_path: Path) -> None:
        from lib.ai_costs import record_response_usage

        class _Resp:
            usage = None

        assert record_response_usage(lane="x", response=_Resp(), root=tmp_path) is False
