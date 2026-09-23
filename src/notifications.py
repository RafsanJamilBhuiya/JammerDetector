"""Telegram telemetry reports and interactive inline keyboards."""
from __future__ import annotations

import json
import logging

import requests

from .config import (
    GITHUB_ACTIONS_URL,
    HTTP_TIMEOUT_SECONDS,
    TELEGRAM_SEND_URL,
    THINGSPEAK_CHANNEL_URL,
)
from .telemetry import (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
    SignalMetrics,
)

LOGGER = logging.getLogger("JammerDetector.Telegram")


class NotificationError(RuntimeError):
    """Telegram delivery failure."""


PRIORITY_PRESENTATION = {
    PRIORITY_CRITICAL: ("🚨", "CRITICAL"),
    PRIORITY_HIGH: ("⚠️", "HIGH"),
    PRIORITY_NORMAL: ("✅", "NORMAL"),
}


def build_status_message(metrics: SignalMetrics, thingspeak_entry_id: str) -> str:
    """Build a comprehensive Markdown status report."""
    emoji, priority = PRIORITY_PRESENTATION.get(
        metrics.priority, ("⚠️", metrics.priority)
    )

    return (
        f"{emoji} *JAMMERDETECTOR — {priority}*

"
        f"*Priority:* {priority}
"
        f"*RSSI:* {metrics.rssi_dbm:.1f} dBm
"
        f"*Signal degradation:* {metrics.degradation_percent:.1f}%
"
        f"*Cellular status:* {metrics.cellular_status}
"
        f"*Possible jammer:* {metrics.jammer_indicator}
"
        f"*Telemetry source:* {metrics.source}
"
        f"*ThingSpeak entry:* {thingspeak_entry_id}
"
        f"*Host:* {metrics.hostname}
"
        f"*UTC:* {metrics.measured_at}

"
        "_Note: RSSI loss alone does not prove intentional jamming._"
    )


def send_status(
    token: str,
    chat_id: str,
    channel_id: str,
    metrics: SignalMetrics,
    entry_id: str,
) -> None:
    """Send telemetry and interactive actions to the configured Telegram chat."""
    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": "📊 View ThingSpeak Dashboard",
                    "url": THINGSPEAK_CHANNEL_URL.format(channel_id=channel_id),
                }
            ],
            [
                {
                    "text": "🔄 Run Manual Check",
                    "url": GITHUB_ACTIONS_URL,
                }
            ],
        ]
    }

    payload = {
        "chat_id": chat_id,
        "text": build_status_message(metrics, entry_id),
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
        "reply_markup": json.dumps(reply_markup, ensure_ascii=False),
    }

    try:
        response = requests.post(
            TELEGRAM_SEND_URL.format(token=token),
            data=payload,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise NotificationError("Telegram HTTP/JSON request failed.") from exc

    if not result.get("ok"):
        raise NotificationError("Telegram API rejected the status report.")

    LOGGER.info(
        "Telegram status delivered: message_id=%s",
        result.get("result", {}).get("message_id", "unknown"),
    )
