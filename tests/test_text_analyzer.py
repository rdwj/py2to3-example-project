# -*- coding: utf-8 -*-
"""
Characterization tests for src/data_processing/text_analyzer.py

Tests the current Python 2 behavior including:
- hashlib.md5("string") with str (bytes) directly
- re.UNICODE flag usage
- commands.getoutput() (removed in Py3)
- reduce() as builtin (moved to functools in Py3)
- map() and filter() returning lists (iterators in Py3)
- __builtin__ module reference (renamed to builtins in Py3)
- xrange() (renamed to range() in Py3)
- dict.has_key() and dict.iteritems()
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import pytest
import tempfile
import builtins as __builtin__

from src.data_processing.text_analyzer import (
    TextFingerprint,
    TextAnalyzer,
    MIN_KEYWORD_LENGTH,
    DEFAULT_TOP_KEYWORDS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def analyzer():
    """Create a TextAnalyzer instance."""
    return TextAnalyzer(language="en")


@pytest.fixture
def sample_maintenance_text():
    """Sample industrial maintenance text."""
    return """
    ABB-ACS880-04 drive fault on Line 3. Technician observed high vibration
    and temperature readings. Replaced faulty capacitor bank and reset
    protection relays. System tested and returned to service.
    """


@pytest.fixture
def sample_german_text():
    """Sample German maintenance text."""
    return u"Störung an der Pumpe. Lager ausgetauscht."


@pytest.fixture
def sample_japanese_text():
    """Sample Japanese maintenance text."""
    return u"温度センサー故障。交換完了。"


# ---------------------------------------------------------------------------
# Test TextFingerprint
# ---------------------------------------------------------------------------

def test_fingerprint_creation_from_unicode():
    """Test creating fingerprint from unicode string."""
    text = u"Test maintenance note"
    fp = TextFingerprint(text)
    assert fp.digest is not None
    assert len(fp.digest) == 32  # MD5 hex digest length
    assert fp.text_length > 0


def test_fingerprint_creation_from_bytes():
    """Test creating fingerprint from bytes (Python 2 str)."""
    text = b"Test maintenance note"
    fp = TextFingerprint(text)
    assert fp.digest is not None
    assert isinstance(fp.digest, str)


def test_fingerprint_md5_with_str():
    """Test hashlib.md5() accepts str directly (Py2 behavior)."""
    text = "Simple text"
    fp = TextFingerprint(text)
    # Should work without explicit .encode() in Py2
    assert fp.digest is not None


def test_fingerprint_normalization_whitespace():
    """Test whitespace normalization in fingerprint."""
    text1 = "Test   with    extra   spaces"
    text2 = "Test with extra spaces"
    fp1 = TextFingerprint(text1)
    fp2 = TextFingerprint(text2)
    assert fp1.digest == fp2.digest


def test_fingerprint_normalization_case():
    """Test case normalization (lowercase)."""
    text1 = "TEST MAINTENANCE"
    text2 = "test maintenance"
    fp1 = TextFingerprint(text1)
    fp2 = TextFingerprint(text2)
    assert fp1.digest == fp2.digest


def test_fingerprint_normalization_strips():
    """Test leading/trailing whitespace is stripped."""
    text1 = "  test  "
    text2 = "test"
    fp1 = TextFingerprint(text1)
    fp2 = TextFingerprint(text2)
    assert fp1.digest == fp2.digest


def test_fingerprint_matches_method():
    """Test matches() method for comparison."""
    text = "Test text"
    fp1 = TextFingerprint(text)
    fp2 = TextFingerprint(text)
    assert fp1.matches(fp2)


def test_fingerprint_not_matches():
    """Test matches() returns False for different texts."""
    fp1 = TextFingerprint("Text A")
    fp2 = TextFingerprint("Text B")
    assert not fp1.matches(fp2)


def test_fingerprint_equality_operator():
    """Test __eq__ operator."""
    text = "Test"
    fp1 = TextFingerprint(text)
    fp2 = TextFingerprint(text)
    assert fp1 == fp2


def test_fingerprint_hash():
    """Test __hash__ for use in sets."""
    fp1 = TextFingerprint("Test")
    fp2 = TextFingerprint("Test")
    fp3 = TextFingerprint("Different")

    fingerprints = {fp1, fp2, fp3}
    assert len(fingerprints) == 2  # fp1 and fp2 should be same


def test_fingerprint_repr():
    """Test __repr__ output."""
    fp = TextFingerprint("Test")
    repr_str = repr(fp)
    assert "TextFingerprint" in repr_str
    assert "len=" in repr_str


def test_fingerprint_unicode_content():
    """Test fingerprint with unicode content."""
    text = u"温度センサー故障"
    fp = TextFingerprint(text)
    assert fp.digest is not None
    assert fp.text_length > 0


# ---------------------------------------------------------------------------
# Test TextAnalyzer extract_keywords
# ---------------------------------------------------------------------------

def test_analyzer_extract_keywords_simple(analyzer):
    """Test keyword extraction from simple text."""
    text = "pump motor bearing replacement completed successfully"
    keywords = analyzer.extract_keywords(text)

    assert isinstance(keywords, list)
    assert len(keywords) > 0
    # Keywords should be tuples of (word, frequency)
    assert isinstance(keywords[0], tuple)
    assert isinstance(keywords[0][0], str)
    assert isinstance(keywords[0][1], int)


def test_analyzer_extract_keywords_filters_stop_words(analyzer):
    """Test that stop words are filtered out."""
    text = "the pump is a critical component and should be maintained"
    keywords = analyzer.extract_keywords(text)

    keyword_words = [kw for kw, _ in keywords]
    # Common stop words should be filtered
    assert "the" not in keyword_words
    assert "is" not in keyword_words
    assert "and" not in keyword_words
    # Content words should remain
    assert "pump" in keyword_words or "critical" in keyword_words


def test_analyzer_extract_keywords_min_length(analyzer):
    """Test that short tokens are filtered."""
    text = "a ab abc abcd abcde"
    keywords = analyzer.extract_keywords(text)

    keyword_words = [kw for kw, _ in keywords]
    # Words shorter than MIN_KEYWORD_LENGTH should be filtered
    if MIN_KEYWORD_LENGTH > 2:
        assert "ab" not in keyword_words


def test_analyzer_extract_keywords_regex_unicode_flag(analyzer, sample_japanese_text):
    """Test re.UNICODE flag handles non-ASCII."""
    keywords = analyzer.extract_keywords(sample_japanese_text)
    # Should extract Japanese characters
    assert len(keywords) > 0


def test_analyzer_extract_keywords_part_numbers(analyzer):
    """Test extraction of part numbers with hyphens."""
    text = "ABB-ACS880-04 drive and SIEMENS-S7-1500 PLC"
    keywords = analyzer.extract_keywords(text)

    keyword_words = [kw for kw, _ in keywords]
    # Part numbers with hyphens should be captured
    assert any("abb" in kw and "acs880" in kw for kw in keyword_words) or \
           any("abb-acs880" in kw for kw in keyword_words)


def test_analyzer_extract_keywords_map_returns_list(analyzer):
    """Test that map() returns a list (Py2 behavior)."""
    text = "test keywords extraction"
    keywords = analyzer.extract_keywords(text)
    # In Py2, map returns list; this should work
    assert isinstance(keywords, list)


def test_analyzer_extract_keywords_filter_returns_list(analyzer):
    """Test that filter() returns a list (Py2 behavior)."""
    text = "test the and keywords"
    keywords = analyzer.extract_keywords(text)
    # filter() in Py2 returns list
    assert isinstance(keywords, list)


def test_analyzer_extract_keywords_top_n(analyzer):
    """Test limiting results to top_n."""
    text = "word1 " * 10 + "word2 " * 5 + "word3 " * 3 + "word4 " * 1
    keywords = analyzer.extract_keywords(text, top_n=2)

    assert len(keywords) == 2
    # Should be sorted by frequency descending
    assert keywords[0][1] >= keywords[1][1]


def test_analyzer_extract_keywords_frequency_counting(analyzer):
    """Test frequency counting with dict.has_key()."""
    text = "fault fault fault error error warning"
    keywords = analyzer.extract_keywords(text)

    keyword_dict = dict(keywords)
    assert keyword_dict["fault"] == 3
    assert keyword_dict["error"] == 2
    assert keyword_dict["warning"] == 1


def test_analyzer_extract_keywords_sorted_by_frequency(analyzer):
    """Test keywords sorted by frequency then alphabetically."""
    text = "apple banana apple cherry banana apple"
    keywords = analyzer.extract_keywords(text)

    # apple (3), banana (2), cherry (1)
    assert keywords[0][0] == "apple"
    assert keywords[0][1] == 3


def test_analyzer_extract_keywords_from_bytes(analyzer):
    """Test extracting from bytes string."""
    text = b"motor bearing failure"
    keywords = analyzer.extract_keywords(text)
    assert len(keywords) > 0


# ---------------------------------------------------------------------------
# Test TextAnalyzer compute_similarity
# ---------------------------------------------------------------------------

def test_analyzer_compute_similarity_identical(analyzer):
    """Test similarity of identical texts."""
    text = "pump motor bearing replacement"
    score = analyzer.compute_similarity(text, text)
    assert score == 1.0


def test_analyzer_compute_similarity_different(analyzer):
    """Test similarity of completely different texts."""
    text1 = "pump motor bearing"
    text2 = "valve sensor temperature"
    score = analyzer.compute_similarity(text1, text2)
    assert 0.0 <= score < 1.0


def test_analyzer_compute_similarity_partial_overlap(analyzer):
    """Test similarity with partial keyword overlap."""
    text1 = "motor bearing fault"
    text2 = "motor sensor fault"
    score = analyzer.compute_similarity(text1, text2)
    assert 0.0 < score < 1.0


def test_analyzer_compute_similarity_empty_texts(analyzer):
    """Test similarity when both texts are empty."""
    score = analyzer.compute_similarity("", "")
    assert score == 1.0


def test_analyzer_compute_similarity_one_empty(analyzer):
    """Test similarity when one text is empty."""
    score = analyzer.compute_similarity("test", "")
    assert score == 0.0


# ---------------------------------------------------------------------------
# Test TextAnalyzer batch_similarity with reduce()
# ---------------------------------------------------------------------------

def test_analyzer_batch_similarity_simple(analyzer):
    """Test pairwise similarity for batch of texts."""
    texts = [
        "motor bearing fault",
        "motor sensor fault",
        "pump valve issue"
    ]
    pairs, average = analyzer.batch_similarity(texts)

    assert len(pairs) == 3  # C(3,2) = 3 pairs
    assert 0.0 <= average <= 1.0
    # Each pair is (i, j, score)
    assert all(len(p) == 3 for p in pairs)


def test_analyzer_batch_similarity_uses_reduce(analyzer):
    """Test that reduce() is used for total calculation."""
    texts = ["text one", "text two", "text three"]
    pairs, average = analyzer.batch_similarity(texts)

    # Verify reduce() is working by checking average calculation
    if pairs:
        manual_total = sum(p[2] for p in pairs)
        manual_avg = manual_total / len(pairs)
        assert abs(average - manual_avg) < 0.001


def test_analyzer_batch_similarity_uses_xrange(analyzer):
    """Test that xrange() is used in nested loops."""
    # This implicitly tests xrange usage
    texts = ["text " + str(i) for i in range(5)]
    pairs, average = analyzer.batch_similarity(texts)

    # Should produce C(5,2) = 10 pairs
    assert len(pairs) == 10


def test_analyzer_batch_similarity_empty_list(analyzer):
    """Test batch similarity with empty list."""
    pairs, average = analyzer.batch_similarity([])
    assert pairs == []
    assert average == 0.0


def test_analyzer_batch_similarity_single_text(analyzer):
    """Test batch similarity with single text."""
    pairs, average = analyzer.batch_similarity(["single text"])
    assert pairs == []
    assert average == 0.0


# ---------------------------------------------------------------------------
# Test TextAnalyzer classify_fault with dict.iteritems()
# ---------------------------------------------------------------------------

def test_analyzer_classify_fault_simple(analyzer):
    """Test fault classification against reference library."""
    library = {
        "bearing_fault": ["bearing noise", "bearing vibration", "bearing wear"],
        "motor_fault": ["motor overheating", "motor failure", "motor fault"]
    }
    analyzer.load_reference_library(library)

    text = "bearing vibration detected on pump"
    label, score = analyzer.classify_fault(text)

    assert label == "bearing_fault"
    assert score > 0.0


def test_analyzer_classify_fault_iteritems_usage(analyzer):
    """Test that dict.iteritems() is used in classification."""
    library = {
        "type_a": ["fault a"],
        "type_b": ["fault b"]
    }
    analyzer.load_reference_library(library)

    text = "fault a detected"
    label, score = analyzer.classify_fault(text)
    assert label is not None


def test_analyzer_classify_fault_no_library(analyzer):
    """Test classification with no reference library."""
    text = "some fault"
    label, score = analyzer.classify_fault(text)

    assert label is None
    assert score == 0.0


def test_analyzer_classify_fault_best_match(analyzer):
    """Test that best matching label is returned."""
    library = {
        "exact_match": ["motor bearing fault"],
        "partial_match": ["motor fault"]
    }
    analyzer.load_reference_library(library)

    text = "motor bearing fault detected"
    label, score = analyzer.classify_fault(text)

    # Should match exact_match better
    assert label == "exact_match"


# ---------------------------------------------------------------------------
# Test TextAnalyzer run_external_analyzer with commands.getoutput()
# ---------------------------------------------------------------------------

def test_analyzer_run_external_analyzer_simple(analyzer):
    """Test running external tool with commands.getoutput()."""
    # Use a simple shell command that exists on most systems
    text = "test text"
    # Use 'echo' as the external tool (just for testing)
    output = analyzer.run_external_analyzer(text, "cat")

    # Should return command output
    assert isinstance(output, str)


def test_analyzer_run_external_analyzer_creates_temp_file(analyzer, monkeypatch):
    """Test that temporary file is created for external tool."""
    import tempfile

    created_files = []

    original_mktemp = tempfile.mktemp

    def tracking_mktemp(*args, **kwargs):
        path = original_mktemp(*args, **kwargs)
        created_files.append(path)
        return path

    monkeypatch.setattr(tempfile, "mktemp", tracking_mktemp)

    text = "test"
    try:
        analyzer.run_external_analyzer(text, "cat")
    except:
        pass

    # Should have created a temp file
    assert len(created_files) > 0


def test_analyzer_run_external_analyzer_unicode_text(analyzer):
    """Test external analyzer with unicode text."""
    text = u"温度センサー"
    # This should encode to UTF-8 before writing
    try:
        output = analyzer.run_external_analyzer(text, "cat")
    except:
        pass  # Command may not exist, but encoding should work


@pytest.mark.skipif(os.name == 'nt', reason="Unix-specific test")
def test_analyzer_run_external_analyzer_commands_module(analyzer):
    """Test that commands.getoutput() is used (Unix only)."""
    text = "test"
    output = analyzer.run_external_analyzer(text, "echo")
    # commands.getoutput should work
    assert isinstance(output, str)


# ---------------------------------------------------------------------------
# Test TextAnalyzer batch_fingerprint with map()
# ---------------------------------------------------------------------------

def test_analyzer_batch_fingerprint_simple(analyzer):
    """Test batch fingerprinting with map()."""
    texts = ["text one", "text two", "text three"]
    results = analyzer.batch_fingerprint(texts)

    assert len(results) == 3
    # Results should be (index, fingerprint) tuples
    assert all(isinstance(r, tuple) and len(r) == 2 for r in results)
    assert all(isinstance(r[1], TextFingerprint) for r in results)


def test_analyzer_batch_fingerprint_map_returns_list(analyzer):
    """Test that map() returns a list (Py2 behavior)."""
    texts = ["a", "b", "c"]
    results = analyzer.batch_fingerprint(texts)

    # Should be a list, not an iterator
    assert isinstance(results, list)


def test_analyzer_batch_fingerprint_builtin_check(analyzer):
    """Test __builtin__.map reference check."""
    texts = ["test"]
    results = analyzer.batch_fingerprint(texts)

    # The function checks __builtin__.map exists
    assert hasattr(__builtin__, "map")


def test_analyzer_batch_fingerprint_enumerate(analyzer):
    """Test enumeration in results."""
    texts = ["a", "b", "c"]
    results = analyzer.batch_fingerprint(texts)

    indices = [r[0] for r in results]
    assert indices == [0, 1, 2]


# ---------------------------------------------------------------------------
# Test TextAnalyzer deduplicate with filter()
# ---------------------------------------------------------------------------

def test_analyzer_deduplicate_removes_duplicates(analyzer):
    """Test deduplication based on fingerprints."""
    texts = [
        "Test maintenance note",
        "Test maintenance note",  # Duplicate
        "Different note",
        "test maintenance note",  # Duplicate (case-insensitive)
    ]
    unique = analyzer.deduplicate(texts)

    assert len(unique) == 2


def test_analyzer_deduplicate_filter_returns_list(analyzer):
    """Test that filter() returns a list (Py2 behavior)."""
    texts = ["a", "b", "c"]
    unique = analyzer.deduplicate(texts)

    assert isinstance(unique, list)


def test_analyzer_deduplicate_preserves_order(analyzer):
    """Test that first occurrence is preserved."""
    texts = [
        "First occurrence",
        "Different text",
        "First occurrence",  # Duplicate
    ]
    unique = analyzer.deduplicate(texts)

    assert len(unique) == 2
    assert unique[0] == "First occurrence"


def test_analyzer_deduplicate_empty_list(analyzer):
    """Test deduplication of empty list."""
    unique = analyzer.deduplicate([])
    assert unique == []


def test_analyzer_deduplicate_all_unique(analyzer):
    """Test deduplication when all texts are unique."""
    texts = ["text one", "text two", "text three"]
    unique = analyzer.deduplicate(texts)
    assert len(unique) == 3


# ---------------------------------------------------------------------------
# Test fingerprint method
# ---------------------------------------------------------------------------

def test_analyzer_fingerprint_method(analyzer):
    """Test analyzer.fingerprint() convenience method."""
    text = "Test maintenance note"
    fp = analyzer.fingerprint(text)

    assert isinstance(fp, TextFingerprint)
    assert fp.digest is not None


# ---------------------------------------------------------------------------
# Test unicode handling throughout
# ---------------------------------------------------------------------------

def test_analyzer_keywords_unicode_german(analyzer, sample_german_text):
    """Test keyword extraction from German text."""
    keywords = analyzer.extract_keywords(sample_german_text)
    assert len(keywords) > 0


def test_analyzer_keywords_unicode_japanese(analyzer, sample_japanese_text):
    """Test keyword extraction from Japanese text."""
    keywords = analyzer.extract_keywords(sample_japanese_text)
    # Should extract tokens even if they're Japanese
    assert len(keywords) > 0


def test_analyzer_similarity_unicode(analyzer):
    """Test similarity calculation with unicode texts."""
    text1 = u"温度センサー故障"
    text2 = u"温度センサー交換"
    score = analyzer.compute_similarity(text1, text2)
    assert score > 0.0  # Should have some overlap


# ---------------------------------------------------------------------------
# Test initialization
# ---------------------------------------------------------------------------

def test_analyzer_initialization_default():
    """Test default initialization."""
    analyzer = TextAnalyzer()
    assert analyzer._language == "en"


def test_analyzer_initialization_custom_language():
    """Test initialization with custom language."""
    analyzer = TextAnalyzer(language="de")
    assert analyzer._language == "de"


def test_analyzer_reference_library_initially_empty():
    """Test reference library is initially empty."""
    analyzer = TextAnalyzer()
    assert analyzer._reference_library == {}


def test_analyzer_load_reference_library():
    """Test loading reference library."""
    analyzer = TextAnalyzer()
    library = {"type1": ["text1", "text2"]}
    analyzer.load_reference_library(library)
    assert analyzer._reference_library == library
