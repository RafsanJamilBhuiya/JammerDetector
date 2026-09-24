"""ThingSpeak cloud API integration."""
from __future__ import annotations

import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import HTTP_TIMEOUT_SECONDS, THINGSPEAK_UPDATE_URL
from .telemetry import SignalMetrics

LOGGER = logging.getLogger("JammerDetector.ThingSpeak")


class ThingSpeakError(RuntimeError):
    """ThingSpeak submission failure."""


def send_telemetry(channel_id: str, write_api_key: str, metrics: SignalMetrics) -> str:
    """Post the three primary telemetry fields in one ThingSpeak update."""
    if not channel_id.isdigit():
        raise ThingSpeakError("THINGSPEAK_CHANNEL_ID must contain only digits.")
    if not write_api_key.strip():
        raise ThingSpeakError("THINGSPEAK_WRITE_API_KEY is empty.")

    payload: dict[str, Any] = {
        "api_key": write_api_key,
        "field1": metrics.rssi_dbm,
        "field2": metrics.degradation_percent,
        "field3": int(metrics.possible_jammer),
    }

    try:
        request = Request(
            THINGSPEAK_UPDATE_URL,
            data=urlencode(payload).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            entry_id = response.read().decode("utf-8").strip()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ThingSpeakError("ThingSpeak HTTP request failed.") from exc

    if not entry_id or entry_id == "0":
        raise ThingSpeakError(
            f"ThingSpeak rejected the update for channel {channel_id}."
        )

    LOGGER.info(
        "ThingSpeak update accepted: channel=%s entry=%s",
        channel_id,
        entry_id,
    )
    return entry_id
