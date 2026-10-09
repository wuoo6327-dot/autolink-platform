"""Central Resend transport for AUTOLINK security and business emails."""

import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class MailUnavailable(Exception):
    pass


def send_verification(email: str, code: str, purpose: str, language='en'):
    from mail_templates import verification_message
    subject, plain, content = verification_message(code, purpose, language)
    return send_message(email, subject, plain, content)


def configured():
    return os.environ.get("MAIL_PROVIDER", "").lower() in ("resend", "resend_smtp") and bool(os.environ.get("RESEND_API_KEY") and os.environ.get("MAIL_FROM"))


def send_message(email: str, subject: str, plain: str, content: str, idempotency_key=None):
    provider = os.environ.get("MAIL_PROVIDER", "").lower()
    if provider not in ("resend", "resend_smtp"):
        raise MailUnavailable("Resend is not configured.")
    key = os.environ.get("RESEND_API_KEY", "")
    sender = os.environ.get("MAIL_FROM", "")
    if not key or not sender:
        raise MailUnavailable("Resend is not configured.")
    if provider == "resend_smtp":
        message = EmailMessage()
        message["From"] = sender
        message["To"] = email
        message["Subject"] = subject
        if idempotency_key:
            message["Resend-Idempotency-Key"] = idempotency_key
        message.set_content(plain)
        message.add_alternative(content, subtype="html")
        try:
            with smtplib.SMTP_SSL("smtp.resend.com", 465, timeout=12, context=ssl.create_default_context()) as client:
                client.login("resend", key)
                client.send_message(message, from_addr=parseaddr(sender)[1], to_addrs=[email])
        except (smtplib.SMTPException, OSError, ValueError) as exc:
            raise MailUnavailable("Resend SMTP delivery failed.") from exc
        return "smtp-accepted"
    payload = json.dumps({"from": sender, "to": [email], "subject": subject, "html": content, "text": plain}).encode()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    request = Request("https://api.resend.com/emails", data=payload, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=12) as response:
            result = json.load(response)
            if not result.get("id"):
                raise MailUnavailable("Resend did not confirm delivery.")
    except (HTTPError, URLError, OSError, ValueError) as exc:
        # Never include request headers or bodies in logs or public errors.
        raise MailUnavailable("Resend delivery failed.") from exc
    return result["id"]
