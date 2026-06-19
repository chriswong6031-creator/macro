"""Tests for the backward-compatible regionalization of engine.group_flow._setup."""
import pytest

from engine import group_flow


def test_region_aliases():
    a = group_flow._REGION_ALIASES
    assert a["us"] == "us" and a["usa"] == "us"
    assert a["china"] == "cn" and a["cn"] == "cn"
    assert a["hongkong"] == "hk" and a["hk"] == "hk"
    assert a["canada"] == "ca" and a["ca"] == "ca"


def test_setup_default_is_us():
    """No-arg _setup() stays US (backward compatible) and carries the expected contract."""
    s = group_flow._setup()
    if s is None:
        pytest.skip("no US baskets cache present")
    assert set(["mem", "closes", "rets", "idx", "bench", "region"]).issubset(s.keys())
    assert s["region"] == "us"
    assert not s["closes"].empty
    assert s["bench"].dropna().shape[0] > 0


def test_unknown_region_falls_back_to_us():
    s = group_flow._setup("atlantis")
    if s is None:
        pytest.skip("no US baskets cache present")
    assert s["region"] == "us"


@pytest.mark.parametrize("region", ["cn", "hk", "ca"])
def test_setup_regional(region):
    s = group_flow._setup(region)
    if s is None:
        pytest.skip(f"no {region} baskets cache present")
    assert s["region"] == region
    assert not s["closes"].empty
    assert s["mem"].get("baskets")
    assert s["bench"].dropna().shape[0] > 0
