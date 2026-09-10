"""SMTP email with TradingView list attachment."""

from __future__ import annotations

import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

from app.config import (
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USER,
)
from app.services.schedule_helpers import parse_email_list

logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_FROM)


def send_tv_list_email(
    *,
    to_address: str,
    subject: str,
    body_text: str,
    tv_list_text: str,
    filename: str = "tradingview_list.txt",
) -> None:
    if not smtp_configured():
        raise RuntimeError(
            "E-posta yapılandırılmamış. .env dosyasına SMTP_HOST, SMTP_FROM ve gerekirse "
            "SMTP_USER / SMTP_PASSWORD ekleyin."
        )

    recipients = parse_email_list(to_address)
    if not recipients:
        raise ValueError("En az bir geçerli e-posta adresi gerekli.")

    msg = MIMEMultipart()
    msg["From"] = SMTP_FROM
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    attachment = MIMEApplication(tv_list_text.encode("utf-8"), Name=filename)
    attachment["Content-Disposition"] = f'attachment; filename="{filename}"'
    msg.attach(attachment)

    if SMTP_USE_TLS:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=60) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, recipients, msg.as_string())
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=60) as server:
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, recipients, msg.as_string())

    logger.info("TV list email sent to %s", ", ".join(recipients))
