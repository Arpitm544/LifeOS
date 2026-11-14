"""Web Push delivery with VAPID keys (pywebpush). Optional at import time."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class PushResult:
    sent: int
    gone_endpoints: list[str]


def notification_payload(reminder, *, summary_count: int = 0) -> dict:
    """Payload the service worker shows, with Done / Snooze actions."""
    body = reminder.message or 'You have a LifeOS reminder.'
    if summary_count > 1:
        body = f'{summary_count} reminders: {body}'
    url = f'/task/{reminder.item_id}' if reminder.item_type == 'task' else '/today'
    actions = [{'action': 'done', 'title': 'Done'}, {'action': 'snooze_15', 'title': 'Snooze 15 min'},
               {'action': 'snooze_60', 'title': 'Snooze 1 h'}] if reminder.item_type == 'task' else []
    return {'title': 'LifeOS', 'body': body, 'reminder_id': str(reminder.id), 'kind': reminder.kind,
            'url': url, 'actions': actions}


def _send_one(subscription, payload: dict, settings) -> int:
    from pywebpush import WebPushException, webpush
    try:
        webpush(subscription_info={'endpoint': subscription.endpoint,
                                   'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth}},
                data=json.dumps(payload), vapid_private_key=settings.vapid_private_key,
                vapid_claims={'sub': settings.vapid_subject}, ttl=3600)
        return 201
    except WebPushException as exc:
        return getattr(exc.response, 'status_code', 500) or 500


async def send_to_subscriptions(subscriptions, payload: dict, settings) -> PushResult:
    if not settings.vapid_private_key or not subscriptions:
        return PushResult(0, [])
    sent, gone = 0, []
    for subscription in subscriptions:
        status = await asyncio.to_thread(_send_one, subscription, payload, settings)
        if status in (404, 410):
            gone.append(subscription.endpoint)  # expired subscription: delete it
        elif status < 300:
            sent += 1
    return PushResult(sent, gone)
