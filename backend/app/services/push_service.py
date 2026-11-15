"""Web Push delivery with VAPID keys (pywebpush). Optional at import time."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from urllib.parse import urlsplit

log = logging.getLogger('lifeos.push')
PUSH_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class PushResult:
    sent: int
    gone_endpoints: list[str]
    failed: int = 0
    statuses: list[int] = field(default_factory=list)


def allowed_endpoint(endpoint: str, allowed_hosts: list[str]) -> bool:
    """Only browser push services may receive requests (prevents SSRF)."""
    try:
        parts = urlsplit(endpoint)
        host = (parts.hostname or '').lower()
        port = parts.port
    except ValueError:  # malformed URL or port
        return False
    if parts.scheme != 'https' or not host or port not in (None, 443):
        return False
    return any(host == allowed or host.endswith('.' + allowed) for allowed in allowed_hosts)


def notification_payload(reminder, *, summary_count: int = 0, settings=None, api_url: str = '') -> dict:
    """Payload the service worker shows, with Done / Snooze actions.

    With settings, the payload carries a signed action token so the buttons work
    from the notification without opening the app (PRD F3.2).
    """
    from .push_tokens import sign_action_token
    body = reminder.message or 'You have a LifeOS reminder.'
    if summary_count > 1:
        body = f'{summary_count} reminders: {body}'
    url = f'/task/{reminder.item_id}' if reminder.item_type == 'task' else '/today'
    actions = [{'action': 'done', 'title': 'Done'}, {'action': 'snooze_15', 'title': 'Snooze 15 min'},
               {'action': 'snooze_60', 'title': 'Snooze 1 h'}] if reminder.item_type == 'task' else []
    payload = {'title': 'LifeOS', 'body': body, 'reminder_id': str(reminder.id), 'kind': reminder.kind,
               'url': url, 'actions': actions}
    if actions and settings is not None:
        token = sign_action_token(settings, reminder_id=str(reminder.id), user_id=str(reminder.user_id))
        if token:
            payload['action_token'] = token
            base = api_url or getattr(settings, 'public_api_url', '') or 'http://127.0.0.1:8000'
            payload['action_url'] = f"{base.rstrip('/')}/api/push-actions/{reminder.id}"
        else:
            payload['actions'] = []  # no secret configured: the buttons could not act
    return payload


def _send_one(subscription, payload: dict, settings) -> int:
    from pywebpush import WebPushException, webpush
    try:
        webpush(subscription_info={'endpoint': subscription.endpoint,
                                   'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth}},
                data=json.dumps(payload), vapid_private_key=settings.vapid_private_key,
                vapid_claims={'sub': settings.vapid_subject}, ttl=3600, timeout=PUSH_TIMEOUT_SECONDS)
        return 201
    except WebPushException as exc:
        return getattr(exc.response, 'status_code', 500) or 500
    except Exception as exc:  # network errors, timeouts: retried; config errors show in the log
        # Type only: request errors embed the endpoint URL in their message.
        log.warning('web push raised %s', type(exc).__name__)
        return 599


async def send_to_subscriptions(subscriptions, payload: dict, settings) -> PushResult:
    if not settings.vapid_private_key or not subscriptions:
        return PushResult(0, [])
    allowed = settings.push_allowed_host_list
    sent, failed, gone, statuses = 0, 0, [], []
    for subscription in subscriptions:
        if not allowed_endpoint(subscription.endpoint, allowed):
            # Never call a non-push host, but keep the row: the allowlist may differ
            # between API and worker environments or change later.
            log.warning('skipped push to a host outside PUSH_ALLOWED_HOSTS')
            continue
        status = await asyncio.to_thread(_send_one, subscription, payload, settings)
        statuses.append(status)
        if status in (404, 410):
            gone.append(subscription.endpoint)  # expired subscription: delete it
        elif status < 300:
            sent += 1
        else:
            failed += 1
            # Status code only: no endpoint, user or message text in logs.
            log.warning('web push failed with status %s', status)
    return PushResult(sent, gone, failed, statuses)
