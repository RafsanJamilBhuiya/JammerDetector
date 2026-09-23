"""Signal telemetry model and mock/anomaly simulation."""
from __future__ import annotations

import random
import socket
from dataclasses import dataclass
from datetime import datetime, timezone

SEVERE_RSSI_DBM = -125.0
BLACKOUT_RSSI_DBM = -140.0
SEVERE_DEGRADATION_PERCENT = 80.0

NORMAL = "NORMAL"
BLACKOUT = "BLACKOUT"
NO_SERVICE = "NO_SERVICE"

PRIORITY_NORMAL = "NORMAL"
PRIORITY_HIGH = "HIGH"
PRIORITY_CRITICAL = "CRITICAL"


class TelemetryError(RuntimeError):
    """Telemetry collection failure."""


@dataclass(frozen=True)
class SignalMetrics:
    rssi_dbm: float
    degradation_percent: float
    cellular_status: str
    possible_jammer: bool
    priority: str
    source: str
    measured_at: str
    hostname: str

    @property
    def jammer_indicator(self) -> str:
        return "YES" if self.possible_jammer else "NO"

    @property
    def anomaly_detected(self) -> bool:
        return self.priority != PRIORITY_NORMAL


def _priority_for(rssi_dbm: float, degradation_percent: float, cellular_status: str) -> str:
    if (
        rssi_dbm <= BLACKOUT_RSSI_DBM
        or cellular_status == BLACKOUT
    ):
        return PRIORITY_CRITICAL
    if (
        rssi_dbm <= SEVERE_RSSI_DBM
        or degradation_percent >= SEVERE_DEGRADATION_PERCENT
        or cellular_status == NO_SERVICE
    ):
        return PRIORITY_HIGH
    return PRIORITY_NORMAL


def collect_signal_metrics(
    source: str = "mock",
    simulate_drop: bool = False,
    force_blackout: bool = False,
    simulate_blackout: bool = False,
) -> SignalMetrics:
    """Collect telemetry from the configured source.

    The current cloud adapter is mock-only. Any blackout simulation forces
    RSSI to -140 dBm so critical alerting can be tested safely.
    """
    if source != "mock":
        raise TelemetryError(
            "No real cellular/RF adapter is configured; cloud runners use mock telemetry."
        )

    blackout_requested = simulate_drop or force_blackout or simulate_blackout

    if blackout_requested:
        rssi_dbm = BLACKOUT_RSSI_DBM
        degradation_percent = 100.0
        cellular_status = BLACKOUT
    else:
        rssi_dbm = round(random.uniform(-95.0, -65.0), 1)
        degradation_percent = round(random.uniform(0.0, 20.0), 1)
        cellular_status = NORMAL

    priority = _priority_for(rssi_dbm, degradation_percent, cellular_status)
    possible_jammer = priority in {PRIORITY_HIGH, PRIORITY_CRITICAL} and (
        rssi_dbm <= BLACKOUT_RSSI_DBM
        or degradation_percent >= SEVERE_DEGRADATION_PERCENT
    )

    return SignalMetrics(
        rssi_dbm=rssi_dbm,
        degradation_percent=degradation_percent,
        cellular_status=cellular_status,
        possible_jammer=possible_jammer,
        priority=priority,
        source=source,
        measured_at=datetime.now(timezone.utc).isoformat(),
        hostname=socket.gethostname(),
    )
