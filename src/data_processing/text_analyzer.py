# -*- coding: utf-8 -*-
"""
Text analyzer for unstructured industrial documents.

Maintenance technicians enter free-text notes into the work order system
describing equipment faults, repair actions, and observations.  These
notes arrive in inconsistent formats, mixed encodings, and occasionally
in multiple languages (English from the US sites, German from Ludwigshafen,
Japanese from the Chiba facility).

This module performs text fingerprinting for duplicate detection, keyword
extraction for classification, and similarity scoring for matching new
fault descriptions against a library of known failure modes.
"""


import re
import hashlib
import subprocess
import builtins
import functools

from src.core.exceptions import DataError
from src.core.string_helpers import safe_decode, safe_encode, detect_encoding
from src.core.config_loader import load_platform_config


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Stop words common in industrial maintenance text -- filtered during
# keyword extraction to reduce noise
_STOP_WORDS = set([
    "the", "a", "an", "is", "was", "are", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can",
    "of", "in", "to", "for", "with", "on", "at", "from", "by",
    "up", "about", "into", "through", "during", "before", "after",
    "and", "but", "or", "nor", "not", "no", "so", "if", "then",
    "than", "too", "very", "just", "also", "it", "its", "this",
    "that", "these", "those", "he", "she", "they", "we", "you",
])

# Regex pattern for tokenising maintenance text -- matches word characters
# including hyphens (common in part numbers like "ABB-ACS880-04")
_TOKEN_PATTERN = re.compile(r"[\w][\w\-]*[\w]|[\w]+", re.UNICODE)

# Minimum word length for keyword candidates
MIN_KEYWORD_LENGTH = 3

# Number of top keywords to extract by default
DEFAULT_TOP_KEYWORDS = 20


# ---------------------------------------------------------------------------
# TextFingerprint -- content hash for duplicate detection
# ---------------------------------------------------------------------------

class TextFingerprint:
    """Content-addressable fingerprint for duplicate detection.

    Computes an MD5 hash of the normalised text content.  Two documents
    with the same fingerprint are considered duplicates even if they
    differ in whitespace, case, or encoding.
    """

    def __init__(self, text):
        if isinstance(text, str):
            normalised = text.lower().strip()
        else:
            normalised = safe_decode(text).lower().strip()

        # Collapse whitespace runs to single spaces
        normalised = re.sub(r"\s+", " ", normalised)

        # hashlib.md5() requires explicit bytes in Python 3
        encoded = safe_encode(normalised, "utf-8")
        self._hash = hashlib.md5(encoded).hexdigest()
        self._length = len(normalised)

    @property
    def digest(self):
        return self._hash

    @property
    def text_length(self):
        return self._length

    def matches(self, other):
        if isinstance(other, TextFingerprint):
            return self._hash == other._hash
        return False

    def __eq__(self, other):
        if isinstance(other, TextFingerprint):
            return self._hash == other._hash
        return NotImplemented

    def __hash__(self):
        return hash(self._hash)

    def __repr__(self):
        return "TextFingerprint(%s, len=%d)" % (self._hash[:12], self._length)


# ---------------------------------------------------------------------------
# TextAnalyzer -- keyword extraction, similarity, classification
# ---------------------------------------------------------------------------

class TextAnalyzer:
    """Analyzes unstructured maintenance text for classification and search.

    Provides keyword extraction, similarity scoring against a reference
    library, and integration with external text processing tools via
    the ``subprocess`` module.
    """

    def __init__(self, language="en"):
        self._language = language
        self._config = load_platform_config()
        self._reference_library = {}

    def fingerprint(self, text):
        """Create a TextFingerprint for duplicate detection."""
        return TextFingerprint(text)

    def extract_keywords(self, text, top_n=None):
        """Extract the most significant keywords from maintenance text.

        Uses term frequency as the ranking signal.  Stop words and short
        tokens are filtered out.
        """
        if top_n is None:
            top_n = DEFAULT_TOP_KEYWORDS

        if isinstance(text, bytes):
            text = safe_decode(text)

        # Tokenise using the regex pattern with UNICODE flag
        tokens = _TOKEN_PATTERN.findall(text)

        # Normalise to lowercase
        tokens = list(map(lambda t: t.lower(), tokens))

        # Filter stop words and short tokens
        tokens = list(filter(
            lambda t: t not in _STOP_WORDS and len(t) >= MIN_KEYWORD_LENGTH,
            tokens,
        ))

        # Count frequencies
        freq = {}
        for token in tokens:
            if token in freq:
                freq[token] += 1
            else:
                freq[token] = 1

        # Sort by frequency descending, then alphabetically
        ranked = sorted(freq.items(), key=lambda pair: (-pair[1], pair[0]))
        return ranked[:top_n]

    def compute_similarity(self, text_a, text_b):
        """Compute a Jaccard similarity score between two texts.

        Uses keyword sets (not raw tokens) for comparison, which is
        more robust against word order differences.
        """
        keywords_a = set([kw for kw, _ in self.extract_keywords(text_a, top_n=50)])
        keywords_b = set([kw for kw, _ in self.extract_keywords(text_b, top_n=50)])

        if not keywords_a and not keywords_b:
            return 1.0
        if not keywords_a or not keywords_b:
            return 0.0

        intersection = keywords_a & keywords_b
        union = keywords_a | keywords_b
        return float(len(intersection)) / float(len(union))

    def batch_similarity(self, texts):
        """Compute pairwise similarity scores for a batch of texts.

        Uses ``functools.reduce()`` to accumulate the total similarity
        mass for reporting average similarity in a document collection.
        """
        keyword_sets = []
        for text in texts:
            kws = set([kw for kw, _ in self.extract_keywords(text, top_n=50)])
            keyword_sets.append(kws)

        pairs = []
        for i in range(len(keyword_sets)):
            for j in range(i + 1, len(keyword_sets)):
                set_a = keyword_sets[i]
                set_b = keyword_sets[j]
                if set_a or set_b:
                    intersection = set_a & set_b
                    union = set_a | set_b
                    score = float(len(intersection)) / float(len(union))
                    pairs.append((i, j, score))

        if not pairs:
            return pairs, 0.0

        total = functools.reduce(lambda acc, p: acc + p[2], pairs, 0.0)
        average = total / len(pairs)
        return pairs, average

    def classify_fault(self, text, reference_library=None):
        """Classify a fault description by matching against reference texts.

        Finds the reference entry with the highest similarity score and
        returns its classification label.
        """
        library = reference_library or self._reference_library
        if not library:
            return None, 0.0

        best_label = None
        best_score = 0.0

        for label, ref_texts in library.items():
            for ref_text in ref_texts:
                score = self.compute_similarity(text, ref_text)
                if score > best_score:
                    best_score = score
                    best_label = label

        return best_label, best_score

    def load_reference_library(self, library_dict):
        """Load a reference library for fault classification.

        *library_dict* maps classification labels to lists of reference
        text strings.
        """
        self._reference_library = library_dict

    def run_external_analyzer(self, text, tool_path):
        """Run an external text analysis tool and return its output.

        Uses the ``subprocess`` module to invoke a command-line NLP tool
        such as ``hunspell`` for spell-checking or a custom tokeniser.
        """
        if isinstance(text, str):
            text = text.encode("utf-8")

        # Write text to a temp file for the external tool
        import tempfile
        tmp_path = tempfile.mktemp(suffix=".txt")
        f = open(tmp_path, "wb")
        try:
            f.write(text)
        finally:
            f.close()

        cmd = "%s %s" % (tool_path, tmp_path)
        output = subprocess.getoutput(cmd)

        try:
            import os
            os.unlink(tmp_path)
        except OSError:
            pass

        return output

    def batch_fingerprint(self, texts):
        """Compute fingerprints for a batch of texts.

        Returns a list of (text_index, TextFingerprint) tuples.
        """
        fingerprints = list(map(lambda t: TextFingerprint(t), texts))
        # Check the builtin types are available via builtins
        assert hasattr(builtins, "map"), "Expected map in builtins"
        return list(enumerate(fingerprints))

    def deduplicate(self, texts):
        """Remove duplicate texts based on fingerprint matching."""
        seen = set()
        def is_unique(text):
            fp = TextFingerprint(text)
            if fp.digest in seen:
                return False
            seen.add(fp.digest)
            return True

        return list(filter(is_unique, texts))
