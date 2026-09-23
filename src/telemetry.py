"""Signal telemetry model and mock/anomaly simulation."""
from __future__ import annotations
import random
import socket
from dataclasses import dataclass
from datetime import datetime, timezone

SEVERE_RSSI_DBM = -125.0
BLACKOUT_RSSI_DBM = -140.0
SEVERE_DEGRADATION_PERCENT = 80.0

class TelemetryError(RuntimeError):
    """Telemetry collection failure."""

@dataclass(frozen=True)
class SignalMetrics:
    rssi_dbm: float
    degradation_percent: float
    cellular_status: str
    anomaly_detected: bool
    possible_jammer: bool
    source: str
    measured_at: str
    hostname: str

def collect_signal_metrics(source: str = "mock", simulate_drop: bool = False) -> SignalMetrics:
    """Generate mock cellular telemetry; optionally force a -140 dBm blackout."""
    if source != "mock":
        raise TelemetryError(
            "No real cellular/RF adapter is configured; cloud runners use mock telemetry."
        )
    if simulate_drop:
        rssi_dbm, degradation_percent, cellular_status = BLACKOUT_RSSI_DBM, 100.0, "BLACKOUT"
    else:
        rssi_dbm = round(random.uniform(-95.0, -65.0), 1)
        degradation_percent = round(random.uniform(0.0, 20.0), 1)
        cellular_status = "CONNECTED"
    anomaly = (
        rssi_dbm <= SEVERE_RSSI_DBM
        or degradation_percent >= SEVERE_DEGRADATION_PERCENT
        or cellular_status in {"BLACKOUT", "NO_SERVICE"}
    )
    possible_jammer = anomaly and (
        rssi_dbm <= BLACKOUT_RSSI_DBM or degradation_percent >= SEVERE_DEGRADATION_PERCENT
    )
    return SignalMetrics(
        rssi_dbm=rssi_dbm,
        degradation_percent=degradation_percent,
        cellular_status=cellular_status,
        anomaly_detected=anomaly,
        possible_jammer=possible_jammer,
        source=source,
        measured_at=datetime.now(timezone.utc).isoformat(),
        hostname=socket.gethostname(),
    )
