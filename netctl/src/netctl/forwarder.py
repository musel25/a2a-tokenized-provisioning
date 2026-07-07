"""TelemetryForwarder — the direction-flipper of ADR-007.

gNMI telemetry is dial-in (collector connects to the router); the product Ada bought
is "samples arrive at MY endpoint". This bridges the two: subscribe to the router with
the provider's own gNMI session, relay every update to the consumer's endpoint as one
`TelemetrySample` JSON line over TCP (docs/03 §5.1).

The forwarder is deliberately PROCESS state — unlike bandwidth config, which lives on
the router — so a provisioner restart stops forwarding until re-applied (ADR-007
consequences; a real deployment supervises it like any service).
"""

from __future__ import annotations

import socket
import threading

from a2a_interfaces import TelemetrySample

from .connect import GnmiTarget, connect


class TelemetryForwarder:
    """One session's stream: router → consumer collector. start() returns once the
    subscription and the collector connection are up (so apply_telemetry can report
    honestly); stop() is idempotent."""

    def __init__(
        self,
        session_id: str,
        target: GnmiTarget,
        sensor_paths: list[str],
        collector_endpoint: str,
        sample_interval_s: int,
    ) -> None:
        self._session_id = session_id
        self._target = target
        self._sensor_paths = sensor_paths
        self._collector_endpoint = collector_endpoint
        self._sample_interval_s = sample_interval_s
        self._client = None
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self.last_error: Exception | None = None

    def start(self) -> None:
        host, port = self._collector_endpoint.rsplit(":", 1)
        self._sock = socket.create_connection((host, int(port)), timeout=5)
        self._client = connect(self._target)
        self._stream = self._client.subscribe2(
            subscribe={
                "mode": "stream",
                "encoding": "json_ietf",
                "subscription": [
                    {
                        "path": path,
                        "mode": "sample",
                        "sample_interval": self._sample_interval_s * 1_000_000_000,
                    }
                    for path in self._sensor_paths
                ],
            }
        )
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        try:
            for message in self._stream:
                if self._stopping.is_set():
                    break
                update = message.get("update")
                if not update:  # sync_response etc. — control noise, not samples
                    continue
                sample = TelemetrySample(
                    session_id=self._session_id,
                    path=update.get("prefix")
                    or (self._sensor_paths[0] if self._sensor_paths else ""),
                    timestamp_ns=update.get("timestamp", 0),
                    values={u["path"]: u["val"] for u in update.get("update", [])},
                )
                self._sock.sendall(sample.model_dump_json().encode() + b"\n")
        except Exception as err:  # noqa: BLE001 — a dead stream is reported, not raised
            if not self._stopping.is_set():
                self.last_error = err

    def stop(self) -> None:
        """Idempotent: closing an already-stopped forwarder is a no-op success."""
        self._stopping.set()
        for closer in (
            lambda: self._client and self._client.close(),
            lambda: self._sock and self._sock.close(),
        ):
            try:
                closer()
            except Exception:  # noqa: BLE001 — closing is best-effort by nature
                pass
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
