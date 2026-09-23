"""ThingSpeak cloud API integration."""
from __future__ import annotations
import logging
from typing import Any
import requests
from .config import HTTP_TIMEOUT_SECONDS, THINGSPEAK_UPDATE_URL
from .telemetry import SignalMetrics

LOGGER = logging.getLogger("JammerDetector.ThingSpeak")

class ThingSpeakError(RuntimeError):
    """ThingSpeak submission failure."""

def send_telemetry(channel_id: str, write_api_key: str, metrics: SignalMetrics) -> str:
    if not channel_id.isdigit():
        raise ThingSpeakError("THINGSPEAK_CHANNEL_ID must contain only digits.")
    payload: dict[str, Any] = {
        "api_key": write_api_key,
        "field1": metrics.rssi_dbm,
        "field2": metrics.degradation_percent,
        "field3": int(metrics.anomaly_detected),
        "field4": int(metrics.possible_jammer),
        "status": f"{metrics.cellular_status};source={metrics.source};host={metrics.hostname}",
    }
    try:
        response = requests.post(THINGSPEAK_UPDATE_URL, data=payload, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ThingSpeakError("ThingSpeak HTTP request failed.") from exc
    entry_id = response.text.strip()
    if not entry_id or entry_id == "0":
        raise ThingSpeakError(f"ThingSpeak rejected the update for channel {channel_id}.")
    LOGGER.info("ThingSpeak update accepted: channel=%s entry=%s", channel_id, entry_id)
    return entry_id
