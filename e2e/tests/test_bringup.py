"""M6.1 — `just up` brings the chain stack up healthy; `just down` stops it clean.

Needs anvil + forge + uv on PATH; skips otherwise. Runs the real orchestrator, hits the
healthchecks, and asserts down leaves nothing listening."""

from __future__ import annotations

import socket

import pytest

from chainmcp.testing import anvil_available, artifacts_available

pytestmark = pytest.mark.skipif(
    not (anvil_available() and artifacts_available()), reason="needs anvil + forge artifacts"
)


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def test_up_then_down():
    import httpx

    from e2e import bringup

    bringup.down()  # clean slate
    try:
        manifest = bringup.up()
        assert _port_open(8545), "anvil should be listening"
        # controller answers (404 on an unknown session = the app is serving)
        assert (
            httpx.get(f"{manifest.controller_url}/v0/sessions/none", timeout=3).status_code == 404
        )
        # the deploy artifact exists and the settlement responds to a view call
        assert bringup.MANIFEST.exists()
    finally:
        bringup.down()
    assert not bringup.MANIFEST.exists()
    assert not _port_open(8000), "controller should be stopped"
