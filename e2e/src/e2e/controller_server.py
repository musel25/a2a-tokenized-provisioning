"""The controller as a real uvicorn server (M6.1) — what `just up` starts.

Wires a read-only ChainReader + a recording MockProvisioner (the network leg is the
lab's, added via the chain+net path) into the M4.4 app and serves it. Deliberately thin:
the composition already lives in controller.wiring; this is just the ASGI entry point.
"""

from __future__ import annotations

import argparse

import uvicorn

from chainmcp import ChainReader
from controller.app import build_app
from controller.auth import AuthStore
from controller.resource_map import load_resource_map
from controller.service import ControllerService
from netctl.mock import MockProvisioner


def build() -> object:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc-url", default="http://127.0.0.1:8545")
    parser.add_argument("--port", type=int, default=8000)
    args, _ = parser.parse_known_args()

    reader = ChainReader(args.rpc_url)
    service = ControllerService(
        reader, MockProvisioner(), AuthStore("bw-ctrl-1"), load_resource_map()
    )
    return build_app(service), args.port


if __name__ == "__main__":
    app, port = build()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
