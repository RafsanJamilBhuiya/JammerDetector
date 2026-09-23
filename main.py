#!/usr/bin/env python3
"""
JammerDetector - headless network health monitor.

This service is designed for GitHub Actions and other cloud/headless runners.
A GitHub-hosted runner cannot directly read the physical modem/cellular radio
attached to a user's device. Therefore, the default mode is deterministic
simulation. Set SIGNAL_SOURCE=system and provide your own platform-specific
sensor integration if real radio telemetry is available.

Telemetry is sent to ThingSpeak. Severe signal loss/anomalies trigger a
high-priority Telegram notification.

Important: an RSSI collapse alone cannot prove that a signal loss was caused
by an intentional jammer. Alerts therefore use the wording "possible jammer /
severe signal anomaly" unless a trusted external detector confirms jamming.
"""

from __future__ import annotations

import logging
import os
import random
import socket
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

THINGSPEAK_UPDATE_URL = "https://api.thingspeak.com/update"
TELEGRAM_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"

# ThingSpeak accepts one update per channel per 15 seconds on the free tier.
# GitHub Actions runs this application only every 10 minutes.
HTTP_TIMEOUT_SECONDS = 15

# Thresholds. Adjust these to match the actual radio/modem being monitored.
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


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Signal collection
# ---------------------------------------------------------------------------

def collect_signal_metrics() -> SignalMetrics:
    """
    Collect signal metrics.

    Default behavior is safe simulation because GitHub-hosted runners do not
    expose a user's cellular modem/RSSI. Set:
        SIGNAL_SOURCE=mock
        MOCK_SIGNAL_DROP=true
    to simulate a blackout at -140 dBm.

    For real hardware, replace/extend this function with a platform-specific
    modem integration and return the same SignalMetrics structure.
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
        # Normal mock range for CI/cloud testing.
        rssi_dbm = round(random.uniform(-95.0, -65.0), 1)
        degradation_percent = round(random.uniform(0.0, 20.0), 1)
        cellular_status = "CONNECTED"

    anomaly_detected = (
        rssi_dbm <= SEVERE_RSSI_DBM
        or degradation_percent >= SEVERE_DEGRADATION_PERCENT
        or cellular_status in {"BLACKOUT", "NO_SERVICE"}
    )

    # This is intentionally a "possible jammer" indicator, not proof of
    # intentional interference. A real detector should combine multiple
    # measurements and/or RF-specific evidence before making that claim.
    possible_jammer = anomaly_detected and (
        rssi_dbm <= BLACKOUT_RSSI_DBM
        or degradation_percent >= SEVERE_DEGRADATION_PERCENT
    )

    measured_at = datetime.now(timezone.utc).isoformat()

    return SignalMetrics(
        rssi_dbm=rssi_dbm,
        degradation_percent=degradation_percent,
        cellular_status=cellular_status,
        anomaly_detected=anomaly_detected,
        possible_jammer=possible_jammer,
        source=source,
        measured_at=measured_at,
        hostname=socket.gethostname(),
    )


# ---------------------------------------------------------------------------
# ThingSpeak
# ---------------------------------------------------------------------------

def send_to_thingspeak(
    channel_id: str,
    write_api_key: str,
    metrics: SignalMetrics,
) -> str:
    """
    Publish telemetry to ThingSpeak.

    ThingSpeak's update endpoint authenticates with the channel Write API Key.
    Channel ID is retained for validation/logging and operational traceability.
    """
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

    # ThingSpeak normally returns the new entry ID as plain text.
    entry_id = response.text.strip()

    if not entry_id or entry_id == "0":
        raise RuntimeError(
            f"ThingSpeak rejected the telemetry update for channel {channel_id}."
        )

    LOGGER.info("ThingSpeak update accepted. Entry ID: %s", entry_id)
    return entry_id


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def send_telegram_alert(token: str, chat_id: str, metrics: SignalMetrics) -> None:
    """Send a high-priority emergency alert to Telegram."""
    alert_level = "CRITICAL" if metrics.rssi_dbm <= BLACKOUT_RSSI_DBM else "HIGH"

    message = (
        f"🚨 JAMMERDETECTOR — {alert_level} ALERT\n\n"
        f"Possible jammer / severe signal anomaly detected.\n"
        f"RSSI: {metrics.rssi_dbm:.1f} dBm\n"
        f"Signal degradation: {metrics.degradation_percent:.1f}%\n"
        f"Cellular status: {metrics.cellular_status}\n"
        f"Possible jammer indicator: "
        f"{'YES' if metrics.possible_jammer else 'NO'}\n"
        f"Source: {metrics.source}\n"
        f"Host: {metrics.hostname}\n"
        f"UTC: {metrics.measured_at}\n\n"
        f"Note: RSSI loss alone does not prove intentional jamming."
    )

    url = TELEGRAM_SEND_URL.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True,
    }

    response = requests.post(
        url,
        data=payload,
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    result = response.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API rejected the alert: {result}")

    LOGGER.info("Emergency Telegram alert delivered successfully.")


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------

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

        send_to_thingspeak(channel_id, write_api_key, metrics)

        if metrics.anomaly_detected:
            try:
                send_telegram_alert(
                    telegram_token,
                    telegram_chat_id,
                    metrics,
                )
            except Exception:
                # Telemetry was already recorded. Do not hide the alert failure.
                LOGGER.exception("Failed to deliver Telegram emergency alert.")
                return 2

        return 0

    except requests.RequestException:
        LOGGER.exception("HTTP request failed.")
        return 1
    except Exception:
        LOGGER.exception("Monitoring cycle failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
