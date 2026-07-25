"""Offline tests for collectors/edgar_geo_revenue.parse_instance — the pure XBRL
instance parser. No network: every case renders a minimal synthetic XBRL instance
(contexts + units + facts) and asserts the emitted geo_revenue block or skip reason.

Covers the §5 cases: us_member / foreign_agg / member_sum happy paths, no_geo_axis,
crossed dims, quarterly exclusion, legacy us-gaap axis namespace, duplicate dedupe,
EUR-unit ignore, negative-member no_denominator / eliminations_no_total, tainted
typedMember exclusion, classification spot checks, and the emitted-block contract.
"""
from __future__ import annotations

import collectors.edgar_geo_revenue as geo

# Namespace URIs used by the fixtures.
NS = {
    "xbrli": "http://www.xbrl.org/2003/instance",
    "xbrldi": "http://xbrl.org/2006/xbrldi",
    "us-gaap": "http://fasb.org/us-gaap/2023",
    "srt": "http://fasb.org/srt/2023",              # current geographic axis home
    "country": "http://xbrl.sec.gov/country/2023",
    "dei": "http://xbrl.sec.gov/dei/2023",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "iso4217": "http://www.xbrl.org/2003/iso4217",
}

FY_START, FY_END = "2023-10-01", "2024-09-28"     # ~363 days (full fiscal year)
Q_START, Q_END = "2024-06-30", "2024-09-28"       # ~90 days (a quarter)


def _ctx(cid: str, *, start=FY_START, end=FY_END, dims=None, typed=False,
         axis_prefix="srt", axis="StatementGeographicalAxis"):
    """Render a <context> with a period and optional explicit-member dims.

    dims: list of (member_prefix, member_local) on the given geographic axis, OR
    list of (dim_prefix, dim_local, member_prefix, member_local) for arbitrary axes
    (used for the crossed-dimension case).
    """
    seg = ""
    if dims:
        parts = []
        for d in dims:
            if len(d) == 2:
                mp, ml = d
                dp, dl = axis_prefix, axis
            else:
                dp, dl, mp, ml = d
            parts.append(
                f'<xbrldi:explicitMember dimension="{dp}:{dl}">{mp}:{ml}</xbrldi:explicitMember>'
            )
        if typed:
            parts.append('<xbrldi:typedMember dimension="us-gaap:ProductOrServiceAxis">'
                         '<us-gaap:Product>X</us-gaap:Product></xbrldi:typedMember>')
        seg = "<xbrli:segment>" + "".join(parts) + "</xbrli:segment>"
    elif typed:
        seg = ('<xbrli:segment><xbrldi:typedMember dimension="us-gaap:ProductOrServiceAxis">'
               '<us-gaap:Product>X</us-gaap:Product></xbrldi:typedMember></xbrli:segment>')
    return (f'<xbrli:context id="{cid}"><xbrli:entity>'
            f'<xbrli:identifier scheme="http://www.sec.gov/CIK">0000320193</xbrli:identifier>'
            f'{seg}</xbrli:entity>'
            f'<xbrli:period><xbrli:startDate>{start}</xbrli:startDate>'
            f'<xbrli:endDate>{end}</xbrli:endDate></xbrli:period></xbrli:context>')


def _fact(concept, cid, val, *, unit="usd", concept_prefix="us-gaap", nil=False):
    if nil:
        return (f'<{concept_prefix}:{concept} contextRef="{cid}" unitRef="{unit}" '
                f'xsi:nil="true"/>')
    return (f'<{concept_prefix}:{concept} contextRef="{cid}" unitRef="{unit}" '
            f'decimals="-6">{val}</{concept_prefix}:{concept}>')


def _instance(contexts, facts, *, doc_end=FY_END, fy="2024", with_dei=True):
    """Assemble a full instance document from context + fact fragment strings."""
    nsdecls = " ".join(f'xmlns:{k}="{v}"' for k, v in NS.items())
    units = (
        '<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>'
        '<xbrli:unit id="eur"><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unit>'
    )
    dei = ""
    if with_dei:
        # DEI facts need a context; reuse a plain FY context id "dei_ctx".
        contexts = contexts + [_ctx("dei_ctx")]
        dei = (f'<dei:DocumentType contextRef="dei_ctx">10-K</dei:DocumentType>'
               f'<dei:DocumentPeriodEndDate contextRef="dei_ctx">{doc_end}</dei:DocumentPeriodEndDate>'
               f'<dei:DocumentFiscalYearFocus contextRef="dei_ctx">{fy}</dei:DocumentFiscalYearFocus>')
    body = "".join(contexts) + units + dei + "".join(facts)
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<xbrli:xbrl {nsdecls}>{body}</xbrli:xbrl>')
    return xml.encode("utf-8")


# ------------------------------------------------------------------ happy paths ---
def test_us_member_happy_path():
    """US 60 / Europe 25 / GreaterChina 15, total 100 → foreign 40.0, em 15.0."""
    ctxs = [
        _ctx("c_us", dims=[("country", "US")]),
        _ctx("c_eu", dims=[("us-gaap", "EuropeMember")]),
        _ctx("c_cn", dims=[("us-gaap", "GreaterChinaMember")]),
        _ctx("c_tot"),
    ]
    facts = [
        _fact("Revenues", "c_us", 60e9),
        _fact("Revenues", "c_eu", 25e9),
        _fact("Revenues", "c_cn", 15e9),
        _fact("Revenues", "c_tot", 100e9),
    ]
    out = geo.parse_instance(_instance(ctxs, facts))
    assert out["ok"] is True, out
    assert out["method"] == "us_member"
    assert out["foreign_pct"] == 40.0
    assert out["em_pct"] == 15.0
    assert out["fy"] == 2024
    assert out["asof"] == FY_END
    assert out["concept"] == "Revenues"
    assert len(out["by_region"]) == 3
    keys = {r["key"] for r in out["by_region"]}
    assert keys == {"US", "Europe", "GreaterChina"}
    # by_region sorted pct desc; US (60%) first.
    assert out["by_region"][0]["key"] == "US"
    assert out["by_region"][0]["cls"] == "us"
    cls = {r["key"]: r["cls"] for r in out["by_region"]}
    assert cls["GreaterChina"] == "em"
    assert cls["Europe"] == "dm"


def test_foreign_agg_path():
    """NonUs 20, total 80 → foreign 25.0, no em_pct (no unambiguous EM member)."""
    ctxs = [_ctx("c_fa", dims=[("us-gaap", "NonUsMember")]), _ctx("c_tot")]
    facts = [_fact("Revenues", "c_fa", 20e9), _fact("Revenues", "c_tot", 80e9)]
    out = geo.parse_instance(_instance(ctxs, facts))
    assert out["ok"] is True, out
    assert out["method"] == "foreign_agg"
    assert out["foreign_pct"] == 25.0
    assert "em_pct" not in out
    fa = [r for r in out["by_region"] if r["key"] == "NonUs"][0]
    assert fa["cls"] == "foreign_total"


def test_member_sum_path():
    """No plain total; US 30 + Europe 20 → denom 50 → foreign 40.0, method member_sum."""
    ctxs = [
        _ctx("c_us", dims=[("country", "US")]),
        _ctx("c_eu", dims=[("us-gaap", "EuropeMember")]),
    ]
    facts = [_fact("Revenues", "c_us", 30e9), _fact("Revenues", "c_eu", 20e9)]
    out = geo.parse_instance(_instance(ctxs, facts))
    assert out["ok"] is True, out
    assert out["method"] == "member_sum"
    assert out["foreign_pct"] == 40.0


# ------------------------------------------------------------------ skip paths ----
def test_no_geo_axis():
    """A total but no geographic-axis contexts at all → no_geo_axis."""
    ctxs = [_ctx("c_tot")]
    facts = [_fact("Revenues", "c_tot", 100e9)]
    out = geo.parse_instance(_instance(ctxs, facts))
    assert out["ok"] is False
    assert out["reason"] == "no_geo_axis"


def test_crossed_dims_excluded():
    """Geo axis AND a product axis in the same context → that context is not a clean
    geo context; with nothing else → no_geo_axis."""
    ctxs = [
        # geo + product axis in ONE context (two dims) → excluded from geo selection.
        _ctx("c_x", dims=[
            ("srt", "StatementGeographicalAxis", "country", "US"),
            ("us-gaap", "ProductOrServiceAxis", "us-gaap", "ProductMember"),
        ]),
        _ctx("c_tot"),
    ]
    facts = [_fact("Revenues", "c_x", 60e9), _fact("Revenues", "c_tot", 100e9)]
    out = geo.parse_instance(_instance(ctxs, facts))
    assert out["ok"] is False
    assert out["reason"] == "no_geo_axis"


def test_quarterly_geo_excluded():
    """90-day geo contexts are not FY-duration → excluded → no_geo_axis."""
    ctxs = [
        _ctx("c_us_q", start=Q_START, end=Q_END, dims=[("country", "US")]),
        _ctx("c_eu_q", start=Q_START, end=Q_END, dims=[("us-gaap", "EuropeMember")]),
        _ctx("c_tot"),
    ]
    facts = [
        _fact("Revenues", "c_us_q", 15e9),
        _fact("Revenues", "c_eu_q", 6e9),
        _fact("Revenues", "c_tot", 100e9),
    ]
    out = geo.parse_instance(_instance(ctxs, facts))
    assert out["ok"] is False
    assert out["reason"] == "no_geo_axis"


def test_legacy_usgaap_axis_namespace():
    """StatementGeographicalAxis under the us-gaap prefix (legacy) parses the same —
    the axis match is namespace-agnostic on the localname."""
    ctxs = [
        _ctx("c_us", axis_prefix="us-gaap", dims=[("country", "US")]),
        _ctx("c_fa", axis_prefix="us-gaap", dims=[("us-gaap", "NonUsMember")]),
        _ctx("c_tot"),
    ]
    facts = [
        _fact("Revenues", "c_us", 70e9),
        _fact("Revenues", "c_fa", 30e9),
        _fact("Revenues", "c_tot", 100e9),
    ]
    out = geo.parse_instance(_instance(ctxs, facts))
    assert out["ok"] is True, out
    assert out["foreign_pct"] == 30.0


def test_duplicate_facts_deduped():
    """A duplicate (concept, context) fact must not double-count the member."""
    ctxs = [
        _ctx("c_us", dims=[("country", "US")]),
        _ctx("c_eu", dims=[("us-gaap", "EuropeMember")]),
        _ctx("c_tot"),
    ]
    facts = [
        _fact("Revenues", "c_us", 60e9),
        _fact("Revenues", "c_us", 60e9),   # exact duplicate — keep-first
        _fact("Revenues", "c_eu", 40e9),
        _fact("Revenues", "c_tot", 100e9),
    ]
    out = geo.parse_instance(_instance(ctxs, facts))
    assert out["ok"] is True, out
    # if the dup double-counted, US would be 120 and foreign_pct would go negative.
    assert out["foreign_pct"] == 40.0


def test_eur_unit_ignored():
    """EUR-unit geo facts are ignored (USD-only); a USD-total-less pair in EUR falls
    through to no_denominator (no USD geo facts to sum)."""
    ctxs = [
        _ctx("c_us", dims=[("country", "US")]),
        _ctx("c_eu", dims=[("us-gaap", "EuropeMember")]),
    ]
    facts = [
        _fact("Revenues", "c_us", 30e9, unit="eur"),
        _fact("Revenues", "c_eu", 20e9, unit="eur"),
    ]
    out = geo.parse_instance(_instance(ctxs, facts))
    assert out["ok"] is False
    assert out["reason"] == "no_denominator"


def test_negative_member_no_total():
    """A negative member without a plain total → member_sum path rejects it →
    no_denominator."""
    ctxs = [
        _ctx("c_us", dims=[("country", "US")]),
        _ctx("c_ot", dims=[("us-gaap", "EuropeMember")]),
    ]
    facts = [
        _fact("Revenues", "c_us", 30e9),
        _fact("Revenues", "c_ot", -5e9),
    ]
    out = geo.parse_instance(_instance(ctxs, facts))
    assert out["ok"] is False
    assert out["reason"] == "no_denominator"


def test_eliminations_no_total():
    """An Eliminations member present with no plain total → eliminations_no_total."""
    ctxs = [
        _ctx("c_us", dims=[("country", "US")]),
        _ctx("c_eu", dims=[("us-gaap", "EuropeMember")]),
        _ctx("c_el", dims=[("us-gaap", "EliminationsMember")]),
    ]
    facts = [
        _fact("Revenues", "c_us", 30e9),
        _fact("Revenues", "c_eu", 20e9),
        _fact("Revenues", "c_el", -3e9),
    ]
    out = geo.parse_instance(_instance(ctxs, facts))
    assert out["ok"] is False
    assert out["reason"] == "eliminations_no_total"


def test_tainted_typed_member_excluded():
    """A geo context also carrying a typedMember is tainted → excluded → with nothing
    else clean, no_geo_axis."""
    ctxs = [
        _ctx("c_us", dims=[("country", "US")], typed=True),
        _ctx("c_tot"),
    ]
    facts = [_fact("Revenues", "c_us", 60e9), _fact("Revenues", "c_tot", 100e9)]
    out = geo.parse_instance(_instance(ctxs, facts))
    assert out["ok"] is False
    assert out["reason"] == "no_geo_axis"


# ---------------------------------------------------- classification spot checks --
def test_classification_country_br_em():
    """country:BR classifies EM and counts into em_pct; JP is DM (not counted)."""
    ctxs = [
        _ctx("c_us", dims=[("country", "US")]),
        _ctx("c_br", dims=[("country", "BR")]),
        _ctx("c_jp", dims=[("country", "JP")]),
        _ctx("c_tot"),
    ]
    facts = [
        _fact("Revenues", "c_us", 50e9),
        _fact("Revenues", "c_br", 20e9),
        _fact("Revenues", "c_jp", 30e9),
        _fact("Revenues", "c_tot", 100e9),
    ]
    out = geo.parse_instance(_instance(ctxs, facts))
    assert out["ok"] is True, out
    assert out["foreign_pct"] == 50.0
    # em = BR only (20/100); JP is DM, excluded from em_pct.
    assert out["em_pct"] == 20.0
    cls = {r["key"]: r["cls"] for r in out["by_region"]}
    assert cls["BR"] == "em"
    assert cls["JP"] == "dm"


def test_classification_asiapacific_mixed_not_em():
    """AsiaPacific is a mixed region: listed in by_region, NEVER summed into em_pct.
    GreaterChina IS EM. So em_pct counts only GreaterChina."""
    ctxs = [
        _ctx("c_us", dims=[("country", "US")]),
        _ctx("c_ap", dims=[("us-gaap", "AsiaPacificMember")]),
        _ctx("c_cn", dims=[("us-gaap", "GreaterChinaMember")]),
        _ctx("c_tot"),
    ]
    facts = [
        _fact("Revenues", "c_us", 40e9),
        _fact("Revenues", "c_ap", 35e9),
        _fact("Revenues", "c_cn", 25e9),
        _fact("Revenues", "c_tot", 100e9),
    ]
    out = geo.parse_instance(_instance(ctxs, facts))
    assert out["ok"] is True, out
    assert out["foreign_pct"] == 60.0
    # em = GreaterChina (25) only; AsiaPacific (35) is mixed and NOT counted.
    assert out["em_pct"] == 25.0
    cls = {r["key"]: r["cls"] for r in out["by_region"]}
    assert cls["AsiaPacific"] == "mixed"
    assert cls["GreaterChina"] == "em"


# ------------------------------------------------------- emitted-block contract ---
def test_emitted_block_contract():
    """The emitted block key set is EXACTLY the §5 shape: required keys present with
    correct types + percent ranges; optional keys absent (not null) when not derivable.
    Fixture with an EM member so em_pct + by_region are both present."""
    ctxs = [
        _ctx("c_us", dims=[("country", "US")]),
        _ctx("c_cn", dims=[("us-gaap", "GreaterChinaMember")]),
        _ctx("c_tot"),
    ]
    facts = [
        _fact("Revenues", "c_us", 55e9),
        _fact("Revenues", "c_cn", 45e9),
        _fact("Revenues", "c_tot", 100e9),
    ]
    out = geo.parse_instance(_instance(ctxs, facts))
    # project through the store-block shaper (what actually lands in geo_revenue.json).
    out["source"] = "10-K 2024-09-28"
    out["accession"] = "0000320193-24-000123"
    block = geo._emit_block(out)

    required = {"foreign_pct", "asof", "source", "fy", "accession", "method", "concept"}
    assert required <= set(block), f"missing required keys: {required - set(block)}"
    # em_pct + by_region derivable here → present.
    assert "em_pct" in block and "by_region" in block
    # no unexpected/null-padded keys.
    allowed = required | {"em_pct", "by_region"}
    assert set(block) <= allowed, f"unexpected keys: {set(block) - allowed}"
    # types + ranges.
    assert isinstance(block["foreign_pct"], float) and 0.0 <= block["foreign_pct"] <= 100.0
    assert isinstance(block["em_pct"], float) and 0.0 <= block["em_pct"] <= block["foreign_pct"] + 0.5
    assert isinstance(block["fy"], int)
    assert isinstance(block["asof"], str) and len(block["asof"]) == 10
    assert isinstance(block["method"], str)
    assert isinstance(block["concept"], str)
    assert isinstance(block["accession"], str)
    for r in block["by_region"]:
        assert set(r) == {"key", "label", "cls", "pct"}
        assert r["cls"] in {"us", "dm", "em", "mixed", "other", "foreign_total"}
        assert isinstance(r["pct"], float)


def test_emitted_block_omits_em_when_absent():
    """foreign_agg with no unambiguous EM member → em_pct is ABSENT (not null)."""
    ctxs = [_ctx("c_fa", dims=[("us-gaap", "NonUsMember")]), _ctx("c_tot")]
    facts = [_fact("Revenues", "c_fa", 20e9), _fact("Revenues", "c_tot", 80e9)]
    out = geo.parse_instance(_instance(ctxs, facts))
    out["source"] = "10-K 2024-09-28"
    out["accession"] = "x"
    block = geo._emit_block(out)
    assert "em_pct" not in block
    assert block["foreign_pct"] == 25.0


def test_concept_priority_on_tie():
    """When two revenue concepts have equal geo-fact counts, the earlier one in
    REVENUE_CONCEPTS wins. RevenueFromContractWithCustomerExcludingAssessedTax
    outranks Revenues."""
    ctxs = [
        _ctx("c_us", dims=[("country", "US")]),
        _ctx("c_eu", dims=[("us-gaap", "EuropeMember")]),
        _ctx("c_tot"),
    ]
    facts = [
        # both concepts tagged on the same contexts (equal counts).
        _fact("Revenues", "c_us", 60e9),
        _fact("Revenues", "c_eu", 40e9),
        _fact("Revenues", "c_tot", 100e9),
        _fact("RevenueFromContractWithCustomerExcludingAssessedTax", "c_us", 70e9),
        _fact("RevenueFromContractWithCustomerExcludingAssessedTax", "c_eu", 30e9),
        _fact("RevenueFromContractWithCustomerExcludingAssessedTax", "c_tot", 100e9),
    ]
    out = geo.parse_instance(_instance(ctxs, facts))
    assert out["ok"] is True, out
    assert out["concept"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert out["foreign_pct"] == 30.0   # from the winning concept (US 70)
