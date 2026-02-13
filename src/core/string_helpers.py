# -*- coding: utf-8 -*-
"""
String and encoding helpers for the Legacy Industrial Data Platform.

Industrial systems routinely mix byte strings from serial protocols,
unicode text from operator interfaces, and legacy encodings like
Latin-1 or Shift-JIS from international sensor labels.  This module
centralises the messy encode/decode logic so that every other module
does not have to reinvent it.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from StringIO import StringIO
from cStringIO import StringIO as FastStringIO

# ---------------------------------------------------------------------------
# Encoding detection heuristics
# ---------------------------------------------------------------------------

# Common encodings encountered across our installed base, ordered by
# probability.  We try each one in sequence until decode succeeds.
_ENCODING_CANDIDATES = [
    u"utf-8",
    u"latin-1",
    u"cp1252",
    u"shift_jis",
    u"iso-8859-15",
    u"ascii",
]


def detect_encoding(raw_bytes):
    """Attempt to determine the encoding of *raw_bytes* by trial decoding.

    Returns the first encoding from ``_ENCODING_CANDIDATES`` that
    decodes without error, or ``'latin-1'`` as the ultimate fallback
    (latin-1 never raises because every byte 0x00-0xFF is a valid
    codepoint).
    """
    if not isinstance(raw_bytes, str):
        # Already unicode -- nothing to detect
        return u"utf-8"

    for enc in _ENCODING_CANDIDATES:
        try:
            raw_bytes.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return u"latin-1"


# ---------------------------------------------------------------------------
# Safe conversion functions
# ---------------------------------------------------------------------------

def safe_decode(value, encoding=u"utf-8", errors=u"replace"):
    """Decode a byte string to unicode, replacing unencodable bytes
    rather than raising."""
    if isinstance(value, unicode):
        return value
    if isinstance(value, basestring):
        return value.decode(encoding, errors)
    return unicode(value)


def safe_encode(value, encoding=u"utf-8", errors=u"replace"):
    """Encode a unicode string to bytes.  Byte strings pass through
    unchanged."""
    if isinstance(value, str) and not isinstance(value, unicode):
        return value
    if isinstance(value, unicode):
        return value.encode(encoding, errors)
    return str(value)


def to_platform_string(value, encoding=u"utf-8"):
    """Normalise *value* to the platform's native string type (``str``
    in Python 2, which is bytes).  Used at I/O boundaries where the
    rest of the stack expects plain ``str``."""
    if isinstance(value, unicode):
        return value.encode(encoding)
    if isinstance(value, basestring):
        return value
    return str(value)


# ---------------------------------------------------------------------------
# Unicode normalisation
# ---------------------------------------------------------------------------

def normalise_sensor_label(label):
    """Normalise a sensor label to NFC unicode form and strip control
    characters.  Sensor labels from different integrators arrive in
    inconsistent normalization forms -- the Japanese labels in particular
    caused duplicate-key bugs until we added this step."""
    import unicodedata
    if not isinstance(label, unicode):
        label = label.decode(u"utf-8", u"replace")
    label = unicodedata.normalize(u"NFC", label)
    # Strip C0/C1 control characters except tab and newline
    cleaned = u""
    for ch in label:
        if unicodedata.category(ch).startswith(u"C") and ch not in u"\t\n":
            continue
        cleaned += ch
    return cleaned.strip()


# ---------------------------------------------------------------------------
# String concatenation helpers
# ---------------------------------------------------------------------------

def safe_concat(*parts):
    """Concatenate strings that may be a mix of str and unicode.

    In Python 2, concatenating ``str + unicode`` triggers an implicit
    decode of the ``str`` using ASCII, which blows up on non-ASCII
    bytes.  This helper decodes every part to unicode first.
    """
    decoded = []
    for part in parts:
        if isinstance(part, unicode):
            decoded.append(part)
        elif isinstance(part, basestring):
            decoded.append(part.decode(u"utf-8", u"replace"))
        else:
            decoded.append(unicode(part))
    return u"".join(decoded)


def build_csv_line(fields, separator=u","):
    """Join fields into a single CSV line, ensuring consistent encoding."""
    encoded_fields = []
    for f in fields:
        text = safe_decode(f) if isinstance(f, basestring) else unicode(f)
        if separator in text or u'"' in text or u"\n" in text:
            text = u'"' + text.replace(u'"', u'""') + u'"'
        encoded_fields.append(text)
    return separator.join(encoded_fields)


# ---------------------------------------------------------------------------
# StringIO helpers for in-memory text assembly
# ---------------------------------------------------------------------------

def make_text_buffer(initial=u""):
    """Return a StringIO buffer pre-loaded with *initial* text."""
    buf = StringIO()
    if initial:
        buf.write(safe_encode(initial))
    return buf


def make_binary_buffer(initial=""):
    """Return a fast C-based StringIO buffer for binary data assembly."""
    buf = FastStringIO()
    if initial:
        buf.write(initial)
    return buf


# ---------------------------------------------------------------------------
# Encoding round-trip validation
# ---------------------------------------------------------------------------

def validate_roundtrip(text, encoding=u"utf-8"):
    """Return True if *text* survives an encode-then-decode round trip
    without data loss.  Used as a pre-flight check before writing to
    systems that only support a specific encoding (e.g. the reporting
    subsystem's email sender defaults to Latin-1)."""
    if not isinstance(text, unicode):
        text = text.decode(u"utf-8", u"replace")
    try:
        encoded = text.encode(encoding)
        decoded = encoded.decode(encoding)
        return decoded == text
    except (UnicodeDecodeError, UnicodeEncodeError):
        return False
