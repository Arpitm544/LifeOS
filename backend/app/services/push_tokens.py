"""Signed tokens that let a push notification's buttons act without a Clerk session (PRD F3.2).

The service worker has no access to the user's Clerk session, so each push payload
carries a short-lived HMAC token bound to one reminder and one user. The token can
only act on that reminder (Done / Snooze), never read data.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

TOKEN_TTL_SECONDS = 7 * 24 * 3600
ALLOWED_ACTIONS = ('done', 'snooze_15', 'snooze_60')


def _secret(settings) -> Optional[bytes]:
    if getattr(settings, 'push_action_secret', ''):
        return settings.push_action_secret.encode()
    if getattr(settings, 'vapid_private_key', ''):
        # API and worker already share the VAPID key; derive a separate key from it.
        return hashlib.sha256(b'lifeos-push-action:' + settings.vapid_private_key.encode()).digest()
    return None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def sign_action_token(settings, *, reminder_id: str, user_id: str, now: Optional[float] = None) -> Optional[str]:
    secret = _secret(settings)
    if secret is None:
        return None
    exp = int((now if now is not None else time.time()) + TOKEN_TTL_SECONDS)
    body = _b64(json.dumps({'r': str(reminder_id), 'u': str(user_id), 'e': exp}, separators=(',', ':')).encode())
    signature = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    return f'{body}.{signature}'


def verify_action_token(settings, token: str, *, reminder_id: str, now: Optional[float] = None) -> Optional[str]:
    """Return the user id the token was issued for, or None if it is invalid, expired or for another reminder."""
    secret = _secret(settings)
    if secret is None or not token or token.count('.') != 1:
        return None
    body, signature = token.split('.')
    expected = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        claims = json.loads(_unb64(body))
    except ValueError:
        return None
    if not isinstance(claims, dict) or claims.get('r') != str(reminder_id):
        return None
    if not isinstance(claims.get('e'), int) or claims['e'] < (now if now is not None else time.time()):
        return None
    user = claims.get('u')
    return user if isinstance(user, str) and user else None
