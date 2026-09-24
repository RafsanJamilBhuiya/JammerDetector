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

        metrics = collect_signal_metrics(
            settings.signal_source, settings.mock_signal_drop
        )

        entry_id = "disabled"
        if settings.thingspeak_enabled:
            try:
                entry_id = send_telemetry(
                    settings.thingspeak_channel_id,
                    settings.thingspeak_write_api_key,
                    metrics,
                )
            except ThingSpeakError as exc:
                LOGGER.error("ThingSpeak integration failed: %s", exc)
                return 1
        else:
            LOGGER.warning("ThingSpeak integration disabled: credentials not configured.")

        if settings.telegram_enabled:
            try:
                send_status(
                    settings.telegram_bot_token,
                    settings.telegram_chat_id,
                    settings.thingspeak_channel_id,
                    metrics,
                    entry_id,
                )
            except NotificationError as exc:
                LOGGER.error("Telegram notification failed: %s", exc)
                return 2
        else:
            LOGGER.warning(
                "Telegram integration disabled: TELEGRAM_BOT_TOKEN and/or "
                "TELEGRAM_CHAT_ID not configured."
            )

        LOGGER.info("Monitoring cycle completed successfully.")
        return 0
    except ConfigurationError as exc:
        LOGGER.error("Configuration error: %s", exc)
        return 1
    except TelemetryError as exc:
        LOGGER.exception("Telemetry error: %s", exc)
        return 1
    except Exception as exc:
        LOGGER.exception("Unexpected fatal error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
