# -*- coding: utf-8 -*-
"""
Characterization tests for src/reporting/email_sender.py

Tests email composition, SMTP delivery, alert thresholds, and distribution lists.
Mocks smtplib.SMTP to avoid network dependencies. Focuses on bytes/str handling,
unicode content, and except syntax patterns.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import time
import pytest
from unittest import mock

from src.reporting.email_sender import (
    EmailError, AlertThreshold, EmailAlert, EmailSender
)
from src.core.exceptions import PlatformError


# ============================================================================
# AlertThreshold Tests
# ============================================================================

def test_alert_threshold_init_defaults():
    """Test AlertThreshold initialization with minimal parameters."""
    threshold = AlertThreshold("TEMP_001")
    assert threshold.tag == "TEMP_001"
    assert threshold.high_limit is None
    assert threshold.low_limit is None
    assert threshold.deadband == 0.0
    assert threshold.min_interval_sec == 300


def test_alert_threshold_init_full():
    """Test AlertThreshold initialization with all parameters."""
    threshold = AlertThreshold(
        "PRESSURE_042",
        high_limit=150.0,
        low_limit=50.0,
        deadband=5.0,
        min_interval_sec=600
    )
    assert threshold.tag == "PRESSURE_042"
    assert threshold.high_limit == 150.0
    assert threshold.low_limit == 50.0
    assert threshold.deadband == 5.0
    assert threshold.min_interval_sec == 600


@pytest.mark.parametrize("value,expected_contains", [
    (200.0, "HIGH"),  # Exceeds high limit
    (30.0, "LOW"),    # Below low limit
])
def test_alert_threshold_check_violations(value, expected_contains):
    """Test that threshold violations return descriptive strings."""
    threshold = AlertThreshold("SENSOR_001", high_limit=180.0, low_limit=40.0)
    result = threshold.check(value)
    assert result is not None
    assert expected_contains in result
    assert str(value) in result


def test_alert_threshold_check_within_bounds():
    """Test that values within bounds return None."""
    threshold = AlertThreshold("SENSOR_002", high_limit=100.0, low_limit=20.0)
    assert threshold.check(50.0) is None
    assert threshold.check(99.0) is None
    assert threshold.check(21.0) is None


def test_alert_threshold_deadband():
    """Test deadband prevents alarms in buffer zone."""
    threshold = AlertThreshold("SENSOR_003", high_limit=100.0, deadband=5.0)
    # Within deadband, no alarm
    assert threshold.check(103.0) is None
    # Beyond deadband, alarm triggers
    result = threshold.check(106.0)
    assert result is not None
    assert "HIGH" in result


def test_alert_threshold_min_interval():
    """Test that minimum interval prevents repeated notifications."""
    threshold = AlertThreshold("SENSOR_004", high_limit=100.0, min_interval_sec=60)

    # First trigger should work
    result1 = threshold.check(120.0)
    assert result1 is not None

    # Immediate second check should be suppressed
    result2 = threshold.check(130.0)
    assert result2 is None

    # Simulate time passing
    threshold._last_triggered = time.time() - 70
    result3 = threshold.check(140.0)
    assert result3 is not None


# ============================================================================
# EmailAlert Tests
# ============================================================================

def test_email_alert_init_minimal():
    """Test EmailAlert initialization with required parameters."""
    alert = EmailAlert("Test Subject", "Test body", "engineer@plant.local")
    assert alert.subject == "Test Subject"
    assert alert.body == "Test body"
    assert alert.recipients == ["engineer@plant.local"]
    assert alert.sender == "platform-alerts@plant.local"
    assert alert.priority == 3


def test_email_alert_init_multiple_recipients():
    """Test EmailAlert with list of recipients."""
    recipients = ["eng1@plant.local", "eng2@plant.local", "ops@plant.local"]
    alert = EmailAlert("Alert", "Body", recipients)
    assert alert.recipients == recipients


def test_email_alert_init_custom_sender_priority():
    """Test EmailAlert with custom sender and priority."""
    alert = EmailAlert(
        "Critical Alert",
        "Emergency shutdown required",
        "ops@plant.local",
        sender="critical-system@plant.local",
        priority=1
    )
    assert alert.sender == "critical-system@plant.local"
    assert alert.priority == 1


def test_email_alert_to_mime_message_ascii():
    """Test MIME message generation with ASCII content."""
    alert = EmailAlert("Test Subject", "Simple body text", "user@example.com")
    msg = alert.to_mime_message()

    assert msg["Subject"] == "Test Subject"
    assert msg["From"] == "platform-alerts@plant.local"
    assert msg["To"] == "user@example.com"
    assert msg["X-Priority"] == "3"
    assert "Simple body text" in msg.as_string()


def test_email_alert_to_mime_message_unicode():
    """Test MIME message generation with unicode content (bytes/str handling)."""
    alert = EmailAlert(
        u"Alert: Température élevée",
        u"La température a atteint 85°C",
        "engineer@plant.local"
    )
    msg = alert.to_mime_message()

    # Should not raise encoding errors
    msg_str = msg.as_string()
    assert "Subject" in msg_str
    assert "utf-8" in msg_str.lower()


# ============================================================================
# EmailSender Tests
# ============================================================================

def test_email_sender_init_defaults():
    """Test EmailSender initialization with default parameters."""
    sender = EmailSender()
    assert sender.smtp_host == "mail.plant.local"
    assert sender.smtp_port == 25
    assert sender.use_tls is False
    assert sender.username is None
    assert sender.password is None
    assert sender.total_sent == 0


def test_email_sender_init_custom():
    """Test EmailSender initialization with custom SMTP settings."""
    sender = EmailSender(
        smtp_host="smtp.example.com",
        smtp_port=587,
        use_tls=True,
        username="platform",
        password="secret123"
    )
    assert sender.smtp_host == "smtp.example.com"
    assert sender.smtp_port == 587
    assert sender.use_tls is True
    assert sender.username == "platform"


def test_email_sender_add_distribution_list(capsys):
    """Test adding distribution lists."""
    sender = EmailSender()
    recipients = ["eng1@plant.local", "eng2@plant.local"]
    sender.add_distribution_list("engineers", recipients)

    assert sender.get_distribution_list("engineers") == recipients
    captured = capsys.readouterr()
    assert "engineers" in captured.out
    assert "2 recipients" in captured.out


def test_email_sender_get_distribution_list_missing():
    """Test getting non-existent distribution list returns empty list."""
    sender = EmailSender()
    assert sender.get_distribution_list("nonexistent") == []


@mock.patch("src.reporting.email_sender.load_platform_config")
def test_email_sender_load_distribution_lists(mock_config, capsys):
    """Test loading distribution lists from config."""
    mock_config.return_value.items.return_value = [
        ("engineers", "eng1@plant.local, eng2@plant.local, eng3@plant.local"),
        ("operations", "ops1@plant.local, ops2@plant.local"),
    ]

    sender = EmailSender()
    sender.load_distribution_lists()

    assert len(sender.get_distribution_list("engineers")) == 3
    assert len(sender.get_distribution_list("operations")) == 2
    captured = capsys.readouterr()
    assert "Loaded 2 distribution lists" in captured.out


@mock.patch("smtplib.SMTP")
def test_email_sender_send_alert_success(mock_smtp_class, capsys):
    """Test successful email delivery via SMTP."""
    mock_smtp = mock_smtp_class.return_value

    sender = EmailSender()
    alert = EmailAlert("Test Alert", "Test body", ["user@example.com"])

    sender.send_alert(alert)

    # Verify SMTP connection and delivery
    mock_smtp_class.assert_called_once_with("mail.plant.local", 25, timeout=30)
    mock_smtp.sendmail.assert_called_once()
    mock_smtp.quit.assert_called_once()

    assert sender.total_sent == 1
    captured = capsys.readouterr()
    assert "Alert sent" in captured.out


@mock.patch("smtplib.SMTP")
def test_email_sender_send_alert_with_tls(mock_smtp_class):
    """Test email delivery with STARTTLS."""
    mock_smtp = mock_smtp_class.return_value

    sender = EmailSender(use_tls=True, username="user", password="pass")
    alert = EmailAlert("Alert", "Body", "recipient@example.com")

    sender.send_alert(alert)

    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_once_with("user", "pass")


@mock.patch("smtplib.SMTP")
def test_email_sender_send_alert_invalid_type(mock_smtp_class):
    """Test send_alert raises EmailError for non-EmailAlert objects."""
    sender = EmailSender()

    with pytest.raises(EmailError, match="Expected EmailAlert"):
        sender.send_alert("not an alert")


@mock.patch("smtplib.SMTP")
def test_email_sender_send_alert_auth_failure(mock_smtp_class, capsys):
    """Test SMTP authentication failure (except syntax with comma)."""
    import smtplib
    mock_smtp = mock_smtp_class.return_value
    mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, "Auth failed")

    sender = EmailSender(username="user", password="wrong")
    alert = EmailAlert("Alert", "Body", "recipient@example.com")

    with pytest.raises(EmailError, match="SMTP auth failed"):
        sender.send_alert(alert)

    captured = capsys.readouterr()
    assert "SMTP auth failed" in captured.out


@mock.patch("smtplib.SMTP")
def test_email_sender_send_alert_recipients_refused(mock_smtp_class, capsys):
    """Test SMTP recipients refused error."""
    import smtplib
    mock_smtp = mock_smtp_class.return_value
    mock_smtp.sendmail.side_effect = smtplib.SMTPRecipientsRefused({
        "bad@example.com": (550, "User unknown")
    })

    sender = EmailSender()
    alert = EmailAlert("Alert", "Body", "bad@example.com")

    with pytest.raises(EmailError, match="Recipients refused"):
        sender.send_alert(alert)


@mock.patch("smtplib.SMTP")
def test_email_sender_send_alert_connection_error(mock_smtp_class, capsys):
    """Test SMTP socket error (multiple exception types in except)."""
    import socket
    mock_smtp_class.side_effect = socket.error("Connection refused")

    sender = EmailSender()
    alert = EmailAlert("Alert", "Body", "user@example.com")

    with pytest.raises(EmailError, match="Send failed"):
        sender.send_alert(alert)


@mock.patch("smtplib.SMTP")
def test_email_sender_send_to_list_success(mock_smtp_class, capsys):
    """Test sending to a distribution list."""
    sender = EmailSender()
    sender.add_distribution_list("test_list", ["user1@example.com", "user2@example.com"])

    sender.send_to_list("test_list", "Subject", "Body", priority=2)

    mock_smtp_class.return_value.sendmail.assert_called_once()


@mock.patch("smtplib.SMTP")
def test_email_sender_send_to_list_empty(mock_smtp_class, capsys):
    """Test sending to empty distribution list skips sending."""
    sender = EmailSender()
    sender.send_to_list("nonexistent", "Subject", "Body")

    # Should not attempt SMTP connection
    mock_smtp_class.assert_not_called()
    captured = capsys.readouterr()
    assert "No recipients" in captured.out


def test_email_sender_compose_alarm_body_minimal():
    """Test alarm body composition with minimal parameters."""
    sender = EmailSender()
    body = sender.compose_alarm_body("TEMP_001", "High temperature", 3)

    assert "TEMP_001" in body
    assert "High temperature" in body
    assert "Severity:  3" in body
    assert "ALARM NOTIFICATION" in body


def test_email_sender_compose_alarm_body_with_value():
    """Test alarm body composition including sensor value."""
    sender = EmailSender()
    body = sender.compose_alarm_body("PRESSURE_042", "Overpressure", 2, value=158.7)

    assert "PRESSURE_042" in body
    assert "Overpressure" in body
    assert "158.7" in body


def test_email_sender_compose_alarm_body_unicode():
    """Test alarm body with unicode tag and message."""
    sender = EmailSender()
    body = sender.compose_alarm_body(u"TEMP_élévé", u"Température critique", 4)

    # Should not raise encoding errors
    assert len(body) > 0


@mock.patch("smtplib.SMTP")
def test_email_sender_send_alarm_notification(mock_smtp_class):
    """Test sending alarm notification to distribution list."""
    sender = EmailSender()
    sender.add_distribution_list("operators", ["op1@plant.local", "op2@plant.local"])

    sender.send_alarm_notification(
        "operators",
        "PUMP_007",
        "Vibration alarm",
        severity=2,
        value=3.5
    )

    # Verify email was composed and sent
    call_args = mock_smtp_class.return_value.sendmail.call_args
    msg_str = call_args[0][2]
    assert "PUMP_007" in msg_str
    assert "Vibration alarm" in msg_str


@mock.patch("smtplib.SMTP")
def test_email_sender_send_daily_digest_ascii(mock_smtp_class):
    """Test sending daily digest with ASCII content."""
    sender = EmailSender()
    sender.add_distribution_list("daily", ["eng@plant.local"])

    report = "Daily Summary\n" + "=" * 40 + "\nAll systems normal."
    sender.send_daily_digest("daily", report)

    call_args = mock_smtp_class.return_value.sendmail.call_args
    msg_str = call_args[0][2]
    assert "Daily Platform Summary" in msg_str
    assert "All systems normal" in msg_str


@mock.patch("smtplib.SMTP")
def test_email_sender_send_daily_digest_unicode(mock_smtp_class):
    """Test sending daily digest with unicode content (bytes/str edge case)."""
    sender = EmailSender()
    sender.add_distribution_list("daily", ["eng@plant.local"])

    report = u"Résumé quotidien\n45 événements"
    sender.send_daily_digest("daily", report)

    # Should encode unicode to bytes without errors
    mock_smtp_class.return_value.sendmail.assert_called_once()


@mock.patch("smtplib.SMTP")
def test_email_sender_total_sent_counter(mock_smtp_class):
    """Test that total_sent counter increments correctly."""
    sender = EmailSender()
    sender.add_distribution_list("test", ["user@example.com"])

    assert sender.total_sent == 0

    sender.send_to_list("test", "Alert 1", "Body 1")
    assert sender.total_sent == 1

    sender.send_to_list("test", "Alert 2", "Body 2")
    assert sender.total_sent == 2
