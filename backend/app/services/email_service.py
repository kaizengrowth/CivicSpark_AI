"""Email delivery via the Resend HTTPS API.

Chosen over raw SMTP so the free-tier Render web service needs no SMTP
egress; no-ops gracefully when RESEND_API_KEY is unset.
"""

import logging

import requests

from app.core.config import Settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


class EmailService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.resend_api_key
        self.from_email = settings.from_email or "alerts@civicspark.local"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def send_email(self, to: str, subject: str, html: str) -> str | None:
        """Send one email; returns the provider message id or None."""
        if not self.is_configured:
            logger.info(f"Email not configured; skipping send to {to}")
            return None
        try:
            response = requests.post(
                RESEND_API_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "from": self.from_email,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json().get("id")
        except Exception as e:
            logger.error(f"Resend send failed for {to}: {e}")
            return None
