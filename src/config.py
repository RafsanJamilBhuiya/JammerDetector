"""Centralized runtime configuration with non-fatal optional integrations."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

HTTP_TIMEOUT_SECONDS = 15
THINGSPEAK_UPDATE_URL = "https://api.thingspeak.com/update"
TELEGRAM_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"
THINGSPEAK_CHANNEL_URL = "https://thingspeak.com/channels/{channel_id}"
GITHUB_ACTIONS_URL = "https://github.com/RafsanJamilBhuiya/JammerDetector/actions"
LOGGER = logging.getLogger("JammerDetector.Configuration")


class ConfigurationError(RuntimeError):
    """Invalid configuration for an explicitly enabled integration."""


def _optional(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        LOGGER.warning(
            "Optional environment variable is missing: %s; related integration "
            "will be disabled for this run.",
            name,
        )
    return value


@dataclass(frozen=True)
class Settings:
    thingspeak_channel_id: str
    thingspeak_write_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    signal_source: str = "mock"
    mock_signal_drop: bool = False
    log_level: str = "INFO"

    @property
    def thingspeak_enabled(self) -> bool:
        return bool(self.thingspeak_channel_id and self.thingspeak_write_api_key)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @classmethod
    def from_env(cls) -> "Settings":
        raw_drop = os.environ.get("MOCK_SIGNAL_DROP", "false").strip().lower()
        return cls(
            thingspeak_channel_id=_optional("THINGSPEAK_CHANNEL_ID"),
            thingspeak_write_api_key=_optional("THINGSPEAK_WRITE_API_KEY"),
            telegram_bot_token=_optional("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=_optional("TELEGRAM_CHAT_ID"),
            signal_source=os.environ.get("SIGNAL_SOURCE", "mock").strip().lower(),
            mock_signal_drop=raw_drop in {"1", "true", "yes", "on"},
            log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        )

    def validate(self) -> None:
        if self.thingspeak_channel_id and not self.thingspeak_channel_id.isdigit():
            raise ConfigurationError("THINGSPEAK_CHANNEL_ID must contain only digits.")
        if self.signal_source != "mock":
            raise ConfigurationError(
                "Only SIGNAL_SOURCE=mock is supported by the current cloud runner adapter."
            )
