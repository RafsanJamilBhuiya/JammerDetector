"""Telegram Markdown reports and interactive inline keyboards."""
from __future__ import annotations
import json
import logging
import requests
from .config import GITHUB_ACTIONS_URL, HTTP_TIMEOUT_SECONDS, TELEGRAM_SEND_URL, THINGSPEAK_CHANNEL_URL
from .telemetry import BLACKOUT_RSSI_DBM, SignalMetrics

LOGGER = logging.getLogger("JammerDetector.Telegram")

class NotificationError(RuntimeError):
    """Telegram delivery failure."""

def build_status_message(metrics: SignalMetrics, thingspeak_entry_id: str) -> str:
    if metrics.rssi_dbm <= BLACKOUT_RSSI_DBM:
        priority, headline, state = "CRITICAL", "🚨 *JAMMERDETECTOR — CRITICAL BLACKOUT*", "BLACKOUT / possible jammer or severe signal anomaly"
    elif metrics.anomaly_detected:
        priority, headline, state = "HIGH", "⚠️ *JAMMERDETECTOR — HIGH PRIORITY ALERT*", "Severe signal anomaly detected"
    else:
        priority, headline, state = "NORMAL", "✅ *JAMMERDETECTOR — NETWORK HEALTH REPORT*", "Normal simulated network health"
    return (
        f"{headline}\n\n*Priority:* {priority}\n*Status:* {state}\n"
        f"*RSSI:* {metrics.rssi_dbm:.1f} dBm\n*Signal degradation:* {metrics.degradation_percent:.1f}%\n"
        f"*Cellular status:* {metrics.cellular_status}\n*Possible jammer indicator:* {'YES' if metrics.possible_jammer else 'NO'}\n"
        f"*Telemetry source:* {metrics.source}\n*ThingSpeak entry:* {thingspeak_entry_id}\n"
        f"*Host:* {metrics.hostname}\n*UTC:* {metrics.measured_at}\n\n"
        "_Note: RSSI loss alone does not prove intentional jamming._"
    )

def send_status(token: str, chat_id: str, channel_id: str, metrics: SignalMetrics, entry_id: str) -> None:
    reply_markup = {
        "inline_keyboard": [
            [{"text": "📊 View ThingSpeak Dashboard", "url": THINGSPEAK_CHANNEL_URL.format(channel_id=channel_id)}],
            [{"text": "🔄 Run Manual Check", "url": GITHUB_ACTIONS_URL}],
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
        response = requests.post(TELEGRAM_SEND_URL.format(token=token), data=payload, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise NotificationError("Telegram HTTP/JSON request failed.") from exc
    if not result.get("ok"):
        raise NotificationError("Telegram API rejected the status report.")
    LOGGER.info("Telegram status delivered: message_id=%s", result.get("result", {}).get("message_id", "unknown"))
