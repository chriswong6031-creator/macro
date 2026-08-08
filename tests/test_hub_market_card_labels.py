"""Landing-hub market cards keep one stable header label per market."""

from __future__ import annotations

import re

from scripts import build_vector


def test_market_cards_show_only_the_current_regime_label() -> None:
    regimes = {
        "US": ("🇺🇸", "q2", "Reflation", "再通胀", "deteriorating"),
        "CN": ("🇨🇳", "q3", "Stagflation", "滞胀", "stable"),
        "HK": ("🇭🇰", "q1", "Goldilocks", "理想增长", "improving"),
        "CA": ("🇨🇦", "q2", "Reflation", "再通胀", "deteriorating"),
    }
    blob = [
        {
            "cc": cc,
            "flag": flag,
            "quad": quad,
            "quad_name_en": label_en,
            "quad_name_zh": label_zh,
            "rdir": direction,
            "rtoward_en": "Stagflation",
            "rtoward_zh": "滞胀",
        }
        for cc, (flag, quad, label_en, label_zh, direction) in regimes.items()
    ]

    html = build_vector._g_markets(blob, 3, 3, 3)
    headers = re.findall(
        r'<div class="card-top">(.*?)</div><div class="split">', html
    )

    assert len(headers) == 4
    assert all(header.count('class="pill ') == 1 for header in headers)
    assert "regime-changed" not in html
    assert "regime-drift" not in html
    assert "changed" not in html
    assert "cooling" not in html
    assert "firming" not in html
