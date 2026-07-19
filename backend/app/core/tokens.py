"""Signed, expiring tokens for one-click actions in notifications.

Unsubscribe links must work from an email or SMS with a single click —
no login, no enumerable IDs. Tokens are HMAC-SHA256 signed with the app
secret; no extra dependency needed.
"""

import base64
import hashlib
import hmac
import time
from typing import Optional

from app.core.config import Settings

UNSUBSCRIBE_MAX_AGE_SECONDS = 60 * 60 * 24 * 180  # 180 days


def _sign(settings: Settings, payload: str) -> str:
    digest = hmac.new(
        settings.secret_key.encode(), payload.encode(), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def make_unsubscribe_token(settings: Settings, subscription_id: int) -> str:
    """Create a signed unsubscribe token for a subscription"""
    payload = f"unsub.{subscription_id}.{int(time.time())}"
    signature = _sign(settings, payload)
    raw = f"{payload}.{signature}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def verify_unsubscribe_token(settings: Settings, token: str) -> Optional[int]:
    """Return the subscription id for a valid token, else None"""
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        action, sub_id, issued_at, signature = raw.rsplit(".", 3)[-4:]
        payload = f"{action}.{sub_id}.{issued_at}"
        if action != "unsub":
            return None
        if not hmac.compare_digest(signature, _sign(settings, payload)):
            return None
        if time.time() - int(issued_at) > UNSUBSCRIBE_MAX_AGE_SECONDS:
            return None
        return int(sub_id)
    except Exception:
        return None
