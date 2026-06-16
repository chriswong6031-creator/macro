"""admin read-only panels — smoke tests against the real repo state (no network)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin import ai_cost, brief, content, ga4, github_api, gitops, health


def test_health_summary_shape():
    s = health.summary()
    for k in ("healthy", "sources", "markets", "source_rows"):
        assert k in s
    assert {"ok", "stale", "dead", "total"} <= set(s["sources"])
    assert isinstance(s["markets"], list) and s["markets"]


def test_ai_cost_estimate_shape():
    c = ai_cost.estimate()
    for k in ("components", "monthly_usd", "savings_by_interval", "assumptions"):
        assert k in c
    assert len(c["savings_by_interval"]) == 7        # intervals 1..7
    assert all(s["interval"] in range(1, 8) for s in c["savings_by_interval"])
    assert c["monthly_usd"] >= 0


def test_content_inventory_finds_pages():
    inv = content.inventory()
    assert inv["total_pages"] > 0
    assert all("name" in p and "kb" in p for p in inv["pages"][:5])


def test_brief_panel_shape():
    b = brief.panel()
    assert "master_brain" in b and "ai_desk" in b
    assert 1 <= b["master_brain"]["interval_days"] <= 7
    assert isinstance(b["master_brain"]["items"], list)


def test_ga4_status_degrades_without_creds():
    st = ga4.status()
    assert st["measurement_id"] == "G-BZTZ9W1BBB"
    assert "setup_steps" in st and st["setup_steps"]
    # configured is a bool either way; without creds it must be False
    assert isinstance(st["configured"], bool)


def test_github_repo_detected():
    owner, name = github_api.repo()
    # this checkout's origin is chriswong6031-creator/macro
    assert owner and name


def test_gitops_status_shape():
    s = gitops.status()
    for k in ("branch", "config_dirty", "can_push_live"):
        assert k in s


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn(); print("PASS", fn.__name__)
