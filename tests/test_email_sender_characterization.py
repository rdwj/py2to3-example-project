# -*- coding: utf-8 -*-
"""
Characterization tests for src/reporting/email_sender.py

Captures pre-migration behavior of:
- AlertThreshold sensor alarm checking with min_interval
- EmailAlert construction and MIME message composition
- EmailSender distribution lists, alert delivery (mocked SMTP)
- Py2-specific: unicode/str isinstance checks, safe_encode for MIME,
  except comma syntax, print statement
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.reporting.email_sender import (
    AlertThreshold, EmailAlert, EmailSender, EmailError,
)


# ---------------------------------------------------------------------------
# AlertThreshold
# ---------------------------------------------------------------------------

class TestAlertThreshold:
    """Characterize alarm threshold checking."""

    def test_high_limit_violation(self):
        """Captures: value exceeding high_limit + deadband triggers alarm."""
        thresh = AlertThreshold("TEMP-001", high_limit=100.0, deadband=1.0,
                                 min_interval_sec=0)
        result = thresh.check(102.0)
        assert result is not None
        assert "HIGH" in result

    def test_low_limit_violation(self):
        """Captures: value below low_limit - deadband triggers alarm."""
        thresh = AlertThreshold("FLOW-001", low_limit=10.0, deadband=0.5,
                                 min_interval_sec=0)
        result = thresh.check(9.0)
        assert result is not None
        assert "LOW" in result

    def test_within_bounds_returns_none(self):
        """Captures: value within limits returns None."""
        thresh = AlertThreshold("TEMP", high_limit=100.0, low_limit=0.0,
                                 min_interval_sec=0)
        assert thresh.check(50.0) is None

    def test_min_interval_suppression(self):
        """Captures: repeated violations within min_interval_sec are suppressed."""
        thresh = AlertThreshold("TEMP", high_limit=100.0, min_interval_sec=60)
        first = thresh.check(200.0)
        assert first is not None
        second = thresh.check(200.0)
        assert second is None  # suppressed

    def test_deadband_boundary(self):
        """Captures: value at exactly high_limit + deadband does NOT trigger.
        Only strictly greater than triggers."""
        thresh = AlertThreshold("T", high_limit=100.0, deadband=1.0,
                                 min_interval_sec=0)
        assert thresh.check(101.0) is None  # at boundary
        assert thresh.check(101.1) is not None  # above


# ---------------------------------------------------------------------------
# EmailAlert
# ---------------------------------------------------------------------------

class TestEmailAlert:
    """Characterize email alert composition."""

    def test_construction(self):
        """Captures: alert holds subject, body, recipients, sender, priority."""
        alert = EmailAlert("Test Subject", "Test Body",
                           ["user@plant.local"], priority=1)
        assert alert.subject == "Test Subject"
        assert alert.body == "Test Body"
        assert alert.recipients == ["user@plant.local"]
        assert alert.priority == 1

    def test_recipients_normalized_to_list(self):
        """Captures: single recipient string wrapped in list."""
        alert = EmailAlert("S", "B", "user@plant.local")
        assert alert.recipients == ["user@plant.local"]

    @pytest.mark.py2_behavior
    def test_to_mime_message_ascii(self):
        """Captures: MIME message construction with safe_encode.
        isinstance(body, unicode) check; Py2 encodes unicode to bytes."""
        alert = EmailAlert("Alert", "Body text", ["a@b.com"])
        msg = alert.to_mime_message()
        assert msg["Subject"] == "Alert"
        assert msg["From"] == "platform-alerts@plant.local"
        assert "a@b.com" in msg["To"]

    @pytest.mark.py2_behavior
    def test_to_mime_message_unicode_body(self):
        """Captures: unicode body encoded via safe_encode before MIME wrapping."""
        alert = EmailAlert(u"Alerte \u00e9lev\u00e9e",
                           u"Temp\u00e9rature critique",
                           ["ops@plant.local"])
        msg = alert.to_mime_message()
        assert msg is not None
        as_str = msg.as_string()
        assert len(as_str) > 0

    def test_x_priority_header(self):
        """Captures: X-Priority header set from priority field."""
        alert = EmailAlert("S", "B", ["a@b.com"], priority=2)
        msg = alert.to_mime_message()
        assert msg["X-Priority"] == "2"


# ---------------------------------------------------------------------------
# EmailSender (SMTP mocked)
# ---------------------------------------------------------------------------

class TestEmailSender:
    """Characterize email sender with distribution lists (no actual SMTP)."""

    def test_add_distribution_list(self):
        """Captures: distribution list stored by name."""
        sender = EmailSender()
        sender.add_distribution_list("ops", ["a@plant.local", "b@plant.local"])
        assert sender.get_distribution_list("ops") == ["a@plant.local", "b@plant.local"]

    def test_get_empty_distribution_list(self):
        """Captures: missing list returns empty list."""
        sender = EmailSender()
        assert sender.get_distribution_list("missing") == []

    def test_send_alert_type_check(self):
        """Captures: send_alert requires EmailAlert instance."""
        sender = EmailSender()
        with pytest.raises(EmailError, match="Expected EmailAlert"):
            sender.send_alert("not an alert")

    def test_compose_alarm_body(self):
        """Captures: alarm body formatting with safe_encode."""
        sender = EmailSender()
        body = sender.compose_alarm_body("TEMP-001", "High temp", 3, value=105.5)
        assert "TEMP-001" in body
        assert "High temp" in body
        assert "105.5" in body
        assert "ALARM NOTIFICATION" in body

    @pytest.mark.py2_behavior
    def test_compose_alarm_body_unicode_tag(self):
        """Captures: safe_encode on unicode tag/message for alarm body."""
        sender = EmailSender()
        body = sender.compose_alarm_body(u"caf\u00e9-TEMP", u"Temp\u00e9rature", 2)
        assert body is not None
        assert len(body) > 0

    def test_total_sent_initial(self):
        """Captures: send count starts at zero."""
        sender = EmailSender()
        assert sender.total_sent == 0

    def test_send_to_empty_list_skips(self):
        """Captures: sending to an empty list does nothing."""
        sender = EmailSender()
        # This should not raise since the list is empty
        sender.send_to_list("empty", "Subject", "Body")
        assert sender.total_sent == 0
