"""Tests for SLF-031 lazy-prices feasibility spike.

Tests pure functions only — no network, no filesystem I/O.
"""
from __future__ import annotations
import math
import pytest


# Import the functions under test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.slf031_edgar_pilot import (
    cosine_tfidf,
    jaccard_3gram,
    norm_length_delta,
    extract_text,
)


# ---------------------------------------------------------------------------
# cosine_tfidf
# ---------------------------------------------------------------------------
class TestCosineTfidf:
    def test_identical_texts(self):
        t = "the quick brown fox jumps over the lazy dog " * 5
        score = cosine_tfidf(t, t)
        assert abs(score - 1.0) < 1e-6

    def test_completely_different_texts(self):
        t1 = "apple orange banana mango kiwi " * 5
        t2 = "nitrogen oxygen hydrogen helium neon " * 5
        score = cosine_tfidf(t1, t2)
        # No shared tokens → cosine = 0
        assert score < 0.01

    def test_partial_overlap(self):
        t1 = "risk factors interest rate credit market liquidity " * 10
        t2 = "risk factors interest rate operational compliance " * 10
        score = cosine_tfidf(t1, t2)
        # Should be meaningfully similar but < 1
        assert 0.3 < score < 1.0

    def test_returns_float(self):
        score = cosine_tfidf("hello world", "world hello")
        assert isinstance(score, float)

    def test_empty_strings_returns_nan(self):
        score = cosine_tfidf("", "")
        assert math.isnan(score)

    def test_one_empty_string_returns_nan(self):
        score = cosine_tfidf("hello world", "")
        assert math.isnan(score)


# ---------------------------------------------------------------------------
# jaccard_3gram
# ---------------------------------------------------------------------------
class TestJaccard3gram:
    def test_identical_texts(self):
        t = "the quick brown fox jumps over the lazy dog"
        score = jaccard_3gram(t, t)
        assert score == 1.0

    def test_no_overlap(self):
        t1 = "alpha beta gamma delta epsilon zeta"
        t2 = "one two three four five six seven"
        score = jaccard_3gram(t1, t2)
        assert score == 0.0

    def test_partial_overlap(self):
        t1 = "risk factors market risk credit risk interest rate risk"
        t2 = "risk factors market risk regulatory risk interest rate risk"
        score = jaccard_3gram(t1, t2)
        assert 0.0 < score < 1.0

    def test_too_short_returns_nan(self):
        # fewer than 3 words → can't form 3-grams → nan
        score = jaccard_3gram("hello world", "hi there")
        assert math.isnan(score)

    def test_returns_float_between_0_and_1(self):
        t1 = "the quick brown fox jumps over lazy"
        t2 = "the quick brown fox runs under lazy"
        score = jaccard_3gram(t1, t2)
        assert 0.0 <= score <= 1.0

    def test_symmetry(self):
        t1 = "a b c d e f g h i j"
        t2 = "a b c x y z g h i j"
        s1 = jaccard_3gram(t1, t2)
        s2 = jaccard_3gram(t2, t1)
        assert abs(s1 - s2) < 1e-10


# ---------------------------------------------------------------------------
# norm_length_delta
# ---------------------------------------------------------------------------
class TestNormLengthDelta:
    def test_identical_length(self):
        t1 = "hello world foo bar"
        t2 = "alpha beta gamma delta"
        score = norm_length_delta(t1, t2)
        assert score == 0.0

    def test_one_empty(self):
        score = norm_length_delta("", "hello world")
        assert abs(score - 1.0) < 1e-10

    def test_both_empty_returns_nan(self):
        score = norm_length_delta("", "")
        assert math.isnan(score)

    def test_half_size(self):
        t1 = "a b c d"       # 4 words
        t2 = "e f g h i j k l"  # 8 words
        score = norm_length_delta(t1, t2)
        assert abs(score - 0.5) < 1e-10

    def test_symmetry(self):
        t1 = "a b c"
        t2 = "a b c d e"
        s1 = norm_length_delta(t1, t2)
        s2 = norm_length_delta(t2, t1)
        assert abs(s1 - s2) < 1e-10

    def test_large_delta(self):
        t1 = ("word " * 100).strip()
        t2 = ("word " * 10).strip()
        score = norm_length_delta(t1, t2)
        # (100-10)/100 = 0.9
        assert abs(score - 0.90) < 1e-10


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------
class TestExtractText:
    def test_plain_text(self):
        content = b"Hello world this is a plain text filing with lots of words."
        text, item1a = extract_text(content, "http://example.com/filing.txt")
        assert "Hello world" in text
        assert item1a is None

    def test_html_stripping(self):
        content = b"<html><body><p>Risk <b>factors</b> here.</p></body></html>"
        text, item1a = extract_text(content, "http://example.com/filing.htm")
        assert "<p>" not in text
        assert "Risk" in text
        assert "factors" in text

    def test_html_entity_unescaping(self):
        content = b"<html><body>&amp; &lt; &gt;</body></html>"
        text, item1a = extract_text(content, "http://example.com/x.htm")
        assert "&amp;" not in text
        assert "&" in text

    def test_item1a_extraction(self):
        # Construct a minimal filing with Item 1A section
        body = (
            "ITEM 1A. RISK FACTORS "
            + "This is a risk factor about interest rates. " * 100
            + "ITEM 2 PROPERTIES"
        )
        content = body.encode("utf-8")
        text, item1a = extract_text(content, "http://example.com/x.htm")
        assert item1a is not None
        assert "interest rates" in item1a

    def test_returns_tuple(self):
        content = b"simple text"
        result = extract_text(content, "http://example.com/x.txt")
        assert isinstance(result, tuple)
        assert len(result) == 2
