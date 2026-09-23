"""Centralized configuration and secret validation."""
from __future__ import annotations
import os
from dataclasses import dataclass

HTTP_TIMEOUT_SECONDS = 15
THINGSPEAK_UPDATE_URL = "https://api.thingspeak.com/update"
TELEGRAM_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"
THINGSPEAK_CHANNEL_URL = "https://thingspeak.com/channels/{channel_id}"
GITHUB_ACTIONS_URL = "https://github.com/RafsanJamilBhuiya/JammerDetector/actions"

class ConfigurationError(RuntimeError):
    """Invalid or incomplete runtime configuration."""

def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"Required environment variable is missing: {name}")
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

    @classmethod
    def from_env(cls) -> "Settings":
        raw_drop = os.environ.get("MOCK_SIGNAL_DROP", "false").strip().lower()
        return cls(
            thingspeak_channel_id=_required("THINGSPEAK_CHANNEL_ID"),
            thingspeak_write_api_key=_required("THINGSPEAK_WRITE_API_KEY"),
            telegram_bot_token=_required("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=_required("TELEGRAM_CHAT_ID"),
            signal_source=os.environ.get("SIGNAL_SOURCE", "mock").strip().lower(),
            mock_signal_drop=raw_drop in {"1", "true", "yes", "on"},
            log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        )

    def validate(self) -> None:
        if not self.thingspeak_channel_id.isdigit():
            raise ConfigurationError("THINGSPEAK_CHANNEL_ID must contain only digits.")
        if self.signal_source != "mock":
            raise ConfigurationError(
                "Only SIGNAL_SOURCE=mock is supported by the current cloud runner adapter."
            )
