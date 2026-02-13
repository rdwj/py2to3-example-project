# -*- coding: utf-8 -*-
"""
Email alert system for the Legacy Industrial Data Platform.

Sends alarm notifications and daily summary digests to plant engineers
and operations staff via the site's internal SMTP relay.  The distribution
list is managed via the platform INI file because the original operators
preferred editing a config section over using a web interface.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import sys
import time
import socket
import smtplib
from email.mime.text import MIMEText

from core.config_loader import load_platform_config
from core.exceptions import PlatformError
from core.string_helpers import safe_encode, safe_decode


class EmailError(PlatformError):
    """Raised when email composition or delivery fails."""
    pass


class AlertThreshold:
    """Defines when a sensor alarm triggers an email notification.

    Supports high/low limits, deadband, and a minimum interval between
    repeated notifications to avoid flooding operators.
    """

    def __init__(self, tag, high_limit=None, low_limit=None,
                 deadband=0.0, min_interval_sec=300):
        self.tag = tag
        self.high_limit = high_limit
        self.low_limit = low_limit
        self.deadband = deadband
        self.min_interval_sec = min_interval_sec
        self._last_triggered = 0

    def check(self, value):
        """Return a descriptive string if the value violates a limit,
        or None if within bounds."""
        now = time.time()
        if now - self._last_triggered < self.min_interval_sec:
            return None
        if self.high_limit is not None and value > self.high_limit + self.deadband:
            self._last_triggered = now
            return "HIGH: %.2f exceeds limit %.2f" % (value, self.high_limit)
        if self.low_limit is not None and value < self.low_limit - self.deadband:
            self._last_triggered = now
            return "LOW: %.2f below limit %.2f" % (value, self.low_limit)
        return None


class EmailAlert:
    """A composed email alert ready for delivery."""

    def __init__(self, subject, body, recipients, sender=None, priority=3):
        self.subject = subject
        self.body = body
        self.recipients = recipients if isinstance(recipients, list) else [recipients]
        self.sender = sender or "platform-alerts@plant.local"
        self.priority = priority
        self.created_at = time.time()

    def to_mime_message(self):
        """Build a MIMEText message from the alert fields."""
        # In Python 3, MIMEText expects str (not bytes) for the body
        body_str = self.body if isinstance(self.body, str) else safe_decode(self.body)
        msg = MIMEText(body_str, "plain", "utf-8")
        msg["Subject"] = self.subject if isinstance(self.subject, str) else safe_decode(self.subject)
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)
        msg["X-Priority"] = str(self.priority)
        return msg


class EmailSender:
    """Connects to the plant SMTP relay and delivers alert messages.

    Supports plain SMTP and STARTTLS.  Authentication is optional
    since most plant relays use IP-based whitelisting.
    """

    def __init__(self, smtp_host="mail.plant.local", smtp_port=25,
                 use_tls=False, username=None, password=None):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.use_tls = use_tls
        self.username = username
        self.password = password
        self._distribution_lists = {}
        self._send_count = 0

    def add_distribution_list(self, name, recipients):
        self._distribution_lists[name] = list(recipients)
        print("Distribution list '%s': %d recipients" % (name, len(recipients)))

    def get_distribution_list(self, name):
        return self._distribution_lists.get(name, [])

    def load_distribution_lists(self, config=None):
        """Load lists from the [email_lists] section of platform config."""
        if config is None:
            config = load_platform_config()
        for key, value in config.items("email_lists"):
            addrs = [a.strip() for a in value.split(",") if a.strip()]
            if addrs:
                self._distribution_lists[key] = addrs
        print("Loaded %d distribution lists" % len(self._distribution_lists))

    def send_alert(self, alert):
        """Deliver a single EmailAlert via SMTP."""
        if not isinstance(alert, EmailAlert):
            raise EmailError("Expected EmailAlert, got %s" % type(alert).__name__)
        msg = alert.to_mime_message()
        try:
            conn = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
            try:
                if self.use_tls:
                    conn.starttls()
                if self.username and self.password:
                    conn.login(self.username, self.password)
                conn.sendmail(alert.sender, alert.recipients, msg.as_string())
                self._send_count += 1
                print("Alert sent to %d recipients: %s" % (len(alert.recipients), alert.subject))
            finally:
                conn.quit()
        except smtplib.SMTPAuthenticationError as e:
            print("SMTP auth failed for %s: %s" % (self.smtp_host, e))
            raise EmailError("SMTP auth failed: %s" % e)
        except smtplib.SMTPRecipientsRefused as e:
            print("Recipients refused: %s" % e)
            raise EmailError("Recipients refused: %s" % e)
        except (smtplib.SMTPException, socket.error) as e:
            print("SMTP error sending to %s: %s" % (self.smtp_host, e))
            raise EmailError("Send failed: %s" % e)

    def send_to_list(self, list_name, subject, body, priority=3):
        """Compose and send an alert to a named distribution list."""
        recipients = self.get_distribution_list(list_name)
        if not recipients:
            print("No recipients in list '%s', skipping" % list_name)
            return
        alert = EmailAlert(subject, body, recipients, priority=priority)
        self.send_alert(alert)

    def compose_alarm_body(self, tag, message, severity, value=None):
        """Build a formatted alarm notification body string."""
        lines = [
            "INDUSTRIAL PLATFORM ALARM NOTIFICATION",
            "=" * 45, "",
            "Tag:       %s" % safe_decode(tag),
            "Severity:  %d" % severity,
            "Message:   %s" % safe_decode(message),
        ]
        if value is not None:
            lines.append("Value:     %.4f" % value)
        lines.append("Time:      %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
        lines.append("")
        lines.append("--- Automated alert from the Industrial Data Platform ---")
        return "\n".join(lines)

    def send_alarm_notification(self, list_name, tag, message, severity, value=None):
        """Compose and send an alarm notification."""
        body = self.compose_alarm_body(tag, message, severity, value)
        subject = "[ALARM SEV%d] %s: %s" % (severity, tag, message[:50])
        self.send_to_list(list_name, subject, body, priority=min(severity, 5))

    def send_daily_digest(self, list_name, report_content):
        """Send a daily summary report as an email digest."""
        subject = "Daily Platform Summary - %s" % time.strftime("%Y-%m-%d")
        body = report_content if isinstance(report_content, str) else safe_decode(report_content)
        self.send_to_list(list_name, subject, body, priority=5)

    @property
    def total_sent(self):
        return self._send_count
