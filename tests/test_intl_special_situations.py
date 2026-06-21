"""International special-situations classifier (engine/intl_special_situations.py, Phase 4 core).

Pins the §D3 regulator-filing -> mature-category mapping, the going-private-before-tender
ordering, country resolution (regulator + exchange suffix), and the US-rules fallback.
"""
from __future__ import annotations

from engine import intl_special_situations as isi


def test_country_resolution():
    assert isi.country_for("sedar") == "CA"
    assert isi.country_for("rns") == "GB"
    assert isi.country_for(ticker="ARX.TO") == "CA"
    assert isi.country_for(ticker="BARC.L") == "GB"
    assert isi.country_for(ticker="2551.HK") == "HK"
    assert isi.country_for(ticker="AAPL") is None       # US, no suffix
    assert isi.country_for() is None


def test_uk_rns_mapping():
    assert isi.classify_intl("Rule 2.7 Announcement: Recommended Cash Offer for Foo plc")[0] == "Tender Offers"
    assert isi.classify_intl("Form 8.3 - TR-1: Notification of major holdings")[0] == "Activist Campaigns"
    assert isi.classify_intl("Rule 2.4 - Statement re possible offer")[0] == "Strategic Reviews"
    # a scheme that cancels the listing is going-private, not a plain tender
    assert isi.classify_intl("Recommended cash acquisition by way of scheme; cancellation of listing")[0] == "Going-Private"


def test_canada_sedar_mapping():
    assert isi.classify_intl("Early Warning Report filed under NI 62-103")[0] == "Activist Campaigns"
    assert isi.classify_intl("Plan of Arrangement with Acme Corp")[0] == "Acquisitions"
    assert isi.classify_intl("Take-over bid circular for Beta Mining")[0] == "Tender Offers"
    assert isi.classify_intl("Normal course issuer bid commenced")[0] == "Capital Returns"


def test_asia_eu_mapping():
    assert isi.classify_intl("大量保有報告書 (large shareholding report)")[0] == "Activist Campaigns"
    assert isi.classify_intl("公開買付届出書 TOB launched")[0] == "Tender Offers"
    assert isi.classify_intl("吸収合併 absorption-type merger")[0] == "Acquisitions"
    assert isi.classify_intl("주식대량보유상황보고서")[0] == "Activist Campaigns"
    assert isi.classify_intl("Privatisation proposal / Rule 3.5 mandatory general offer")[0] == "Going-Private"
    assert isi.classify_intl("Substantial Holder Notice Form 604")[0] == "Activist Campaigns"


def test_falls_back_to_us_rules_then_none():
    # a US-style phrase still routes via the shared classifier
    assert isi.classify_intl("entered into an agreement and plan of merger to be acquired")[0] == "Acquisitions"
    assert isi.classify_intl("ordinary product launch, nothing to see") == (None, None)
    assert isi.classify_intl(None) == (None, None)
