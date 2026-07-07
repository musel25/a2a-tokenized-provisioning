"""M4.5 — compose the real controller: read-only chain + real hands + resource map,
plus the two autonomous teardown drivers (the Revoked watcher, the expiry timer).

This is the ONLY controller module that touches concrete adapters, and it depends on
their packages, never the reverse. `domain.py` stays pure; `service.py` stays on the
ports; this file is where the ports meet reality.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from .auth import AuthStore
from .resource_map import load_resource_map
from .service import ControllerService


@dataclass
class ControllerRuntime:
    """The live controller and its background drivers, bundled so callers start/stop
    them as one. `service` is the same object M4.4's httpx tests drove — only its
    dependencies changed."""

    service: ControllerService
    _reader: object
    _provisioner: object
    _expiry: "ExpiryTimer" = field(default=None)

    def start_watchers(self, expiry_poll_s: float = 2.0) -> None:
        # Revoked → teardown: the chain adapter's watcher calls straight into the
        # service (which re-reads the chain before acting — don't trust the event).
        self._reader.watch_revoked(self.service.handle_revoked)
        self._expiry = ExpiryTimer(self.service, expiry_poll_s)
        self._expiry.start()

    def close(self) -> None:
        if self._expiry is not None:
            self._expiry.stop()
        for closable in (self._reader, self._provisioner):
            close = getattr(closable, "close", None)
            if close is not None:
                close()


class ExpiryTimer:
    """ADR-004 in code: an OS timer SCHEDULES wake-ups, but every wake re-reads chain
    time before tearing anything down. A dumb poll (not a per-session alarm) because
    chain time can jump — the timer's only job is to keep asking `tick()`."""

    def __init__(self, service: ControllerService, poll_s: float) -> None:
        self._service = service
        self._poll_s = poll_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self._poll_s):
            try:
                self._service.tick()  # re-reads chain time inside
            except Exception as err:  # noqa: BLE001 — a transient RPC hiccup, retry next tick
                self.last_error = err

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._poll_s * 3)
            self._thread = None


def build_runtime(
    rpc_url: str,
    provisioner,
    controller_id: str = "bw-ctrl-1",
    deployment: dict | None = None,
    resource_map_path: Path | None = None,
    poll_interval: float = 1.0,
) -> ControllerRuntime:
    """Wire the production controller. The chain side is a READ-ONLY ChainReader —
    the controller holds no key, not even an unused one (rule 2)."""
    from chainmcp import ChainReader

    reader = ChainReader(rpc_url, deployment=deployment, poll_interval=poll_interval)
    service = ControllerService(
        reader, provisioner, AuthStore(controller_id), load_resource_map(resource_map_path)
    )
    return ControllerRuntime(service=service, _reader=reader, _provisioner=provisioner)
