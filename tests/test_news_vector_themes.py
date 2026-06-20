"""Small extension: news_vector theme classification — additional cases.
No network. Complements tests/test_news_vector.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import news_vector as nv  # noqa: E402


def test_classify_theme_ai_tech_openai():
    # "OpenAI data center" -> "ai_tech" (openai and data center are ai_tech keywords)
    assert nv.classify_theme("OpenAI data center expansion announced") == "ai_tech"


def test_classify_theme_energy_opec():
    # "OPEC crude oil output" -> "energy"
    assert nv.classify_theme("OPEC crude oil output cut extended") == "energy"


def test_classify_theme_ai_tech_gpu():
    assert nv.classify_theme("Nvidia GPU shortage delays data center buildout") == "ai_tech"


def test_classify_theme_energy_natural_gas():
    assert nv.classify_theme("Natural gas prices surge on cold weather") == "energy"


def test_classify_theme_trade():
    assert nv.classify_theme("White House weighs new tariffs on China steel") == "trade"


def test_classify_theme_monetary():
    assert nv.classify_theme("Federal Reserve holds interest rates steady at FOMC meeting") == "monetary"


def test_classify_theme_inflation():
    assert nv.classify_theme("CPI data shows consumer price inflation easing") == "inflation"


def test_classify_theme_geopolitics():
    assert nv.classify_theme("US and Iran reach ceasefire deal in Gulf") == "geopolitics"


def test_classify_theme_industrial_policy():
    assert nv.classify_theme("Government takes a stake in Intel semiconductor plant") == "industrial_policy"


def test_classify_theme_none_offnarrative():
    # Off-narrative -> None (dropped)
    assert nv.classify_theme("Local sports team wins championship game") is None
    assert nv.classify_theme("") is None
    assert nv.classify_theme("Celebrity gossip roundup weekend edition") is None


def test_classify_theme_markets():
    assert nv.classify_theme("S&P 500 hits record high on Wall Street") == "markets"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
