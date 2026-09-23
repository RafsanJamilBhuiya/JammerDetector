#!/usr/bin/env python3
"""
JammerDetector - headless cellular signal health monitor.

GitHub-hosted runners cannot directly read a physical cellular modem/RF sensor.
The default CI mode therefore uses mock telemetry. A real deployment should
provide a platform-specific sensor adapter that returns SignalMetrics.

Each run:
1. Validates required secrets.
2. Collects signal telemetry (mock by default in CI).
3. Writes telemetry to ThingSpeak.
4. Sends a Telegram Markdown status report on every successful telemetry write.
5. Adds inline buttons for the ThingSpeak dashboard and GitHub Actions page.
6. Marks severe anomalies / -140 dBm blackout samples as high-priority.

An RSSI collapse alone cannot prove intentional jamming; alerts use
"possible jammer / severe signal anomaly" wording unless external RF evidence
confirms intentional interference.
"""

from __future__ import annotations

import json
import logging
import os
import random
import socket
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

import requests


THINGSPEAK_UPDATE_URL = "https://api.thingspeak.com/update"
TELEGRAM_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"
THINGSPEAK_CHANNEL_URL = "https://thingspeak.com/channels/{channel_id}"
GITHUB_ACTIONS_URL = "https://github.com/RafsanJamilBhuiya/JammerDetector/actions"

HTTP_TIMEOUT_SECONDS = 15

SEVERE_RSSI_DBM = -125.0
BLACKOUT_RSSI_DBM = -140.0
SEVERE_DEGRADATION_PERCENT = 80.0

LOGGER = logging.getLogger("JammerDetector")


@dataclass(frozen=True)
class SignalMetrics:
    """Normalized network health telemetry."""

    rssi_dbm: float
    degradation_percent: float
    cellular_status: str
    anomaly_detected: bool
    possible_jammer: bool
    source: str
    measured_at: str
    hostname: str


def required_env(name: str) -> str:
    """Return a required environment variable or fail safely."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")
    return value


def optional_bool_env(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def collect_signal_metrics() -> SignalMetrics:
    """
    Collect signal metrics.

    CI/cloud mode uses mock telemetry. Set MOCK_SIGNAL_DROP=true to simulate
    a -140 dBm blackout. Real hardware support requires a platform-specific
    modem/RF adapter.
    """
    source = os.environ.get("SIGNAL_SOURCE", "mock").strip().lower()
    simulate_drop = optional_bool_env("MOCK_SIGNAL_DROP", default=False)

    if source != "mock":
        raise RuntimeError(
            "SIGNAL_SOURCE is not 'mock', but no platform-specific real sensor "
            "adapter is configured. GitHub-hosted runners cannot directly "
            "expose cellular RSSI."
        )

    if simulate_drop:
        rssi_dbm = BLACKOUT_RSSI_DBM
        degradation_percent = 100.0
        cellular_status = "BLACKOUT"
    else:
        rssi_dbm = round(random.uniform(-95.0, -65.0), 1)
        degradation_percent = round(random.uniform(0.0, 20.0), 1)
        cellular_status = "CONNECTED"

    anomaly_detected = (
        rssi_dbm <= SEVERE_RSSI_DBM
        or degradation_percent >= SEVERE_DEGRADATION_PERCENT
        or cellular_status in {"BLACKOUT", "NO_SERVICE"}
    )

    possible_jammer = anomaly_detected and (
        rssi_dbm <= BLACKOUT_RSSI_DBM
        or degradation_percent >= SEVERE_DEGRADATION_PERCENT
    )

    return SignalMetrics(
        rssi_dbm=rssi_dbm,
        degradation_percent=degradation_percent,
        cellular_status=cellular_status,
        anomaly_detected=anomaly_detected,
        possible_jammer=possible_jammer,
        source=source,
        measured_at=datetime.now(timezone.utc).isoformat(),
        hostname=socket.gethostname(),
    )


def send_to_thingspeak(
    channel_id: str,
    write_api_key: str,
    metrics: SignalMetrics,
) -> str:
    """Publish one telemetry sample to ThingSpeak and return its entry ID."""
    if not channel_id.isdigit():
        raise ValueError("THINGSPEAK_CHANNEL_ID must contain only digits.")

    payload: Dict[str, Any] = {
        "api_key": write_api_key,
        "field1": metrics.rssi_dbm,
        "field2": metrics.degradation_percent,
        "field3": 1 if metrics.anomaly_detected else 0,
        "field4": 1 if metrics.possible_jammer else 0,
        "status": (
            f"{metrics.cellular_status};source={metrics.source};"
            f"host={metrics.hostname}"
        ),
    }

    LOGGER.info(
        "Sending telemetry to ThingSpeak channel %s: RSSI=%s dBm, "
        "degradation=%s%%, status=%s",
        channel_id,
        metrics.rssi_dbm,
        metrics.degradation_percent,
        metrics.cellular_status,
    )

    response = requests.post(
        THINGSPEAK_UPDATE_URL,
        data=payload,
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    entry_id = response.text.strip()
    if not entry_id or entry_id == "0":
        raise RuntimeError(
            f"ThingSpeak rejected the telemetry update for channel {channel_id}."
        )

    LOGGER.info("ThingSpeak update accepted. Entry ID: %s", entry_id)
    return entry_id


def build_telegram_status_message(
    metrics: SignalMetrics,
    thingspeak_entry_id: str,
) -> str:
    """Build a Markdown status report for normal and anomalous runs."""
    if metrics.rssi_dbm <= BLACKOUT_RSSI_DBM:
        priority = "CRITICAL"
        headline = "🚨 *JAMMERDETECTOR — CRITICAL BLACKOUT*"
        state = "BLACKOUT / possible jammer or severe signal anomaly"
    elif metrics.anomaly_detected:
        priority = "HIGH"
        headline = "⚠️ *JAMMERDETECTOR — HIGH PRIORITY ALERT*"
        state = "Severe signal anomaly detected"
    else:
        priority = "NORMAL"
        headline = "✅ *JAMMERDETECTOR — NETWORK HEALTH REPORT*"
        state = "Normal simulated network health"

    jammer_indicator = "YES" if metrics.possible_jammer else "NO"

    return (
        f"{headline}\n\n"
        f"*Priority:* {priority}\n"
        f"*Status:* {state}\n"
        f"*RSSI:* {metrics.rssi_dbm:.1f} dBm\n"
        f"*Signal degradation:* {metrics.degradation_percent:.1f}%\n"
        f"*Cellular status:* {metrics.cellular_status}\n"
        f"*Possible jammer indicator:* {jammer_indicator}\n"
        f"*Telemetry source:* {metrics.source}\n"
        f"*ThingSpeak entry:* {thingspeak_entry_id}\n"
        f"*Host:* {metrics.hostname}\n"
        f"*UTC:* {metrics.measured_at}\n\n"
        f"_Note: RSSI loss alone does not prove intentional jamming._"
    )


def send_telegram_status(
    token: str,
    chat_id: str,
    metrics: SignalMetrics,
    thingspeak_entry_id: str,
    channel_id: str,
) -> None:
    """Send the run report with interactive Telegram inline buttons."""
    message = build_telegram_status_message(metrics, thingspeak_entry_id)

    channel_url = THINGSPEAK_CHANNEL_URL.format(channel_id=channel_id)

    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": "📊 View ThingSpeak Dashboard",
                    "url": channel_url,
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
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
        "reply_markup": json.dumps(reply_markup, ensure_ascii=False),
    }

    LOGGER.info(
        "Sending Telegram %s-priority status report with inline keyboard.",
        "high" if metrics.anomaly_detected else "normal",
    )

    response = requests.post(
        TELEGRAM_SEND_URL.format(token=token),
        data=payload,
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    result = response.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API rejected the status report: {result}")

    message_id = result.get("result", {}).get("message_id", "unknown")
    LOGGER.info(
        "Telegram status report delivered successfully. Message ID: %s",
        message_id,
    )


def main() -> int:
    """Run one monitoring cycle."""
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    try:
        channel_id = required_env("THINGSPEAK_CHANNEL_ID")
        write_api_key = required_env("THINGSPEAK_WRITE_API_KEY")
        telegram_token = required_env("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = required_env("TELEGRAM_CHAT_ID")

        metrics = collect_signal_metrics()

        LOGGER.info(
            "Signal sample: RSSI=%s dBm, degradation=%s%%, status=%s, "
            "anomaly=%s, possible_jammer=%s",
            metrics.rssi_dbm,
            metrics.degradation_percent,
            metrics.cellular_status,
            metrics.anomaly_detected,
            metrics.possible_jammer,
        )

        entry_id = send_to_thingspeak(channel_id, write_api_key, metrics)

        try:
            send_telegram_status(
                telegram_token,
                telegram_chat_id,
                metrics,
                entry_id,
                channel_id,
            )
        except Exception:
            # ThingSpeak telemetry is already recorded; report Telegram failure
            # explicitly and fail the workflow so the delivery problem is visible.
            LOGGER.exception("Failed to deliver Telegram status report.")
            return 2

        LOGGER.info(
            "Monitoring cycle completed successfully: ThingSpeak + Telegram."
        )
        return 0

    except requests.RequestException:
        LOGGER.exception("HTTP request failed.")
        return 1
    except Exception:
        LOGGER.exception("Monitoring cycle failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
