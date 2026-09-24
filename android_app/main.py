#!/usr/bin/env python3
"""JammerDetector Android application.

This application is intentionally isolated from the repository's existing
root-level monitoring backend.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

import requests
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

try:
    from jnius import autoclass
except ImportError:
    autoclass = None


LOGGER = logging.getLogger("JammerDetectorAndroid")

# Replace the hostname with the deployed backend when it is available.
BACKEND_BASE_URL = "https://YOUR_USERNAME.pythonanywhere.com"
CONFIG_ENDPOINT = f"{BACKEND_BASE_URL}/api/config"
TELEMETRY_ENDPOINT = f"{BACKEND_BASE_URL}/api/telemetry"

DEFAULT_INTERVAL_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 15


class CellularSignalReader:
    """Read cellular RSSI from Android TelephonyManager."""

    def __init__(self) -> None:
        self.telephony_manager = None

        if autoclass is None:
            LOGGER.warning("pyjnius is not available.")
            return

        try:
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Context = autoclass("android.content.Context")
            activity = PythonActivity.mActivity
            self.telephony_manager = activity.getSystemService(
                Context.TELEPHONY_SERVICE
            )
        except Exception:
            LOGGER.exception("Unable to initialize TelephonyManager.")

    def read_rssi(self) -> Optional[int]:
        """Return cellular RSSI in dBm when Android exposes it."""
        if self.telephony_manager is None:
            return None

        try:
            signal_strength = self.telephony_manager.getSignalStrength()
            if signal_strength is None:
                return None

            # getDbm() is available on modern Android APIs.
            return int(signal_strength.getDbm())
        except Exception:
            LOGGER.exception("Failed to read cellular RSSI.")
            return None


class RemoteConfiguration:
    """Retrieve runtime configuration from the backend."""

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    def fetch(self) -> dict[str, Any]:
        response = requests.get(
            self.endpoint,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict):
            raise ValueError("Configuration response must be a JSON object.")

        return data


class TelemetryClient:
    """Send Android telemetry to the backend."""

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            self.endpoint,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        try:
            data = response.json()
            return data if isinstance(data, dict) else {"status": "ok"}
        except ValueError:
            return {"status": "ok", "http_status": response.status_code}


class TelemetryWorker(threading.Thread):
    """Collect and transmit telemetry without blocking the Kivy UI thread."""

    def __init__(
        self,
        signal_reader: CellularSignalReader,
        telemetry_client: TelemetryClient,
        config_client: RemoteConfiguration,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        super().__init__(daemon=True)
        self.signal_reader = signal_reader
        self.telemetry_client = telemetry_client
        self.config_client = config_client
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self.last_rssi: Optional[int] = None
        self.last_error: Optional[str] = None
        self.runtime_config: dict[str, Any] = {}

    def stop(self) -> None:
        self._stop_event.set()

    def collect_cycle(self) -> None:
        try:
            self.runtime_config = self.config_client.fetch()
        except Exception as exc:
            LOGGER.warning("Remote configuration unavailable: %s", exc)

        rssi = self.signal_reader.read_rssi()
        self.last_rssi = rssi

        payload = {
            "device": "android",
            "timestamp": int(time.time()),
            "rssi_dbm": rssi,
            "telemetry_type": "cellular_signal",
            "config": self.runtime_config,
        }

        LOGGER.info("Cellular telemetry: RSSI=%s dBm", rssi)
        self.telemetry_client.send(payload)

    def run(self) -> None:
        LOGGER.info("Telemetry worker started.")

        while not self._stop_event.is_set():
            try:
                self.collect_cycle()
                self.last_error = None
            except Exception as exc:
                self.last_error = str(exc)
                LOGGER.exception("Telemetry cycle failed.")

            self._stop_event.wait(self.interval_seconds)

        LOGGER.info("Telemetry worker stopped.")


class JammerDetectorApp(App):
    """Minimal Kivy UI for starting and stopping telemetry collection."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.signal_reader = CellularSignalReader()
        self.config_client = RemoteConfiguration(CONFIG_ENDPOINT)
        self.telemetry_client = TelemetryClient(TELEMETRY_ENDPOINT)
        self.worker: Optional[TelemetryWorker] = None
        self.status_label: Optional[Label] = None

    def build(self) -> BoxLayout:
        layout = BoxLayout(
            orientation="vertical",
            padding=20,
            spacing=15,
        )

        layout.add_widget(
            Label(text="JammerDetector", font_size="28sp")
        )

        self.status_label = Label(
            text="Monitoring stopped",
            font_size="18sp",
        )
        layout.add_widget(self.status_label)

        start_button = Button(
            text="Start Monitoring",
            size_hint_y=None,
            height=60,
        )
        stop_button = Button(
            text="Stop Monitoring",
            size_hint_y=None,
            height=60,
        )

        start_button.bind(on_press=lambda *_: self.start_monitoring())
        stop_button.bind(on_press=lambda *_: self.stop_monitoring())

        layout.add_widget(start_button)
        layout.add_widget(stop_button)

        Clock.schedule_interval(self.update_status, 2)
        return layout

    def start_monitoring(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return

        self.worker = TelemetryWorker(
            signal_reader=self.signal_reader,
            telemetry_client=self.telemetry_client,
            config_client=self.config_client,
        )
        self.worker.start()
        self.set_status("Monitoring started")

    def stop_monitoring(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.worker.join(timeout=2)
            self.worker = None

        self.set_status("Monitoring stopped")

    def update_status(self, _dt: float) -> None:
        if self.worker is None:
            return

        if self.worker.last_rssi is None:
            message = "Monitoring...\nRSSI: unavailable"
        else:
            message = f"Monitoring...\nRSSI: {self.worker.last_rssi} dBm"

        if self.worker.last_error:
            message += f"\nLast error: {self.worker.last_error}"

        self.set_status(message)

    def set_status(self, message: str) -> None:
        if self.status_label is not None:
            self.status_label.text = message

    def on_stop(self) -> None:
        self.stop_monitoring()


if __name__ == "__main__":
    JammerDetectorApp().run()
