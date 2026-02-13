# -*- coding: utf-8 -*-
"""
Reporting subsystem for the Legacy Industrial Data Platform.

This package provides report generation, email alerting, and a basic
web dashboard for plant operators and engineers.  Reports can be
rendered to plain text or HTML via configurable templates, emailed
to distribution lists on alarm conditions, and viewed in a browser
through the built-in dashboard server.
"""


from .report_generator import ReportGenerator, ReportTemplate, ReportSection
from .email_sender import EmailSender, EmailAlert, AlertThreshold
from .web_dashboard import DashboardServer, DashboardHandler, SessionManager
