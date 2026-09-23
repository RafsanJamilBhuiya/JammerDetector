#!/usr/bin/env python3
"""JammerDetector application entry point."""
from __future__ import annotations

import logging
import sys

from src.config import ConfigurationError, Settings
from src.notifications import NotificationError, send_status
from src.telemetry import TelemetryError, collect_signal_metrics
from src.thingspeak import ThingSpeakError, send_telemetry

LOGGER = logging.getLogger("JammerDetector")


def main() -> int:
    try:
        settings = Settings.from_env()
        logging.basicConfig(
            level=settings.log_level,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
        settings.validate()
        LOGGER.info("Starting JammerDetector monitoring cycle.")
        metrics = collect_signal_metrics(settings.signal_source, settings.mock_signal_drop)
        LOGGER.info(
            "Telemetry: RSSI=%s dBm degradation=%s%% status=%s anomaly=%s possible_jammer=%s",
            metrics.rssi_dbm, metrics.degradation_percent, metrics.cellular_status,
            metrics.anomaly_detected, metrics.possible_jammer,
        )
        entry_id = send_telemetry(
            settings.thingspeak_channel_id,
            settings.thingspeak_write_api_key,
            metrics,
        )
        send_status(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            settings.thingspeak_channel_id,
            metrics,
            entry_id,
        )
        LOGGER.info("Monitoring cycle completed successfully.")
        return 0
    except ConfigurationError as exc:
        LOGGER.error("Configuration error: %s", exc)
        return 1
    except TelemetryError as exc:
        LOGGER.exception("Telemetry error: %s", exc)
        return 1
    except ThingSpeakError as exc:
        LOGGER.exception("ThingSpeak error: %s", exc)
        return 1
    except NotificationError as exc:
        LOGGER.exception("Telegram notification error: %s", exc)
        return 2
    except Exception as exc:
        LOGGER.exception("Unexpected fatal error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
