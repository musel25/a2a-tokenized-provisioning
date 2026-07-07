"""The operator console server (M6.4+): serves the SPA and streams live pipeline events.

A single global `Console` session (one operator). Actions run in a worker thread and
push typed events to every connected browser over Server-Sent Events; the SPA renders
them as the trust relay, the event stream, and the device inspector.

  uv run --group demo python -m e2e.dashboard.server        # → http://127.0.0.1:8099
"""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from .orchestrator import Console

HERE = Path(__file__).parent
CONSOLE = Console()
_subscribers: list[queue.Queue] = []
_subs_lock = threading.Lock()
_busy = threading.Lock()  # one action at a time (a single operator, a single stack)


def _broadcast(event: dict) -> None:
    with _subs_lock:
        for q in _subscribers:
            q.put(event)


def _run(target, *args) -> None:
    """Run an action in a worker thread if free; ignore overlapping requests."""
    if not _busy.acquire(blocking=False):
        _broadcast({"kind": "busy", "domain": "controller", "title": "busy",
                    "detail": "an action is already running", "t": 0})
        return

    def wrapped():
        try:
            target(*args, _broadcast)
        finally:
            _busy.release()

    threading.Thread(target=wrapped, daemon=True).start()


def build_app() -> FastAPI:
    app = FastAPI(title="a2a operator console")

    # Warm the LLM endpoint (if configured) while the operator is still reading the page —
    # a scale-to-zero Modal container boots in ~60 s and this hides it. No-op when off.
    threading.Thread(target=CONSOLE.warm_llm, daemon=True).start()

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (HERE / "console.html").read_text()

    @app.get("/api/status")
    def status() -> dict:
        return CONSOLE.status()

    @app.get("/api/device")
    def device() -> dict:
        try:
            return CONSOLE.device_state()
        except Exception as err:  # noqa: BLE001
            return {"online": False, "error": str(err)[:200]}

    @app.post("/api/chat")
    def chat(body: dict) -> dict:
        text = (body or {}).get("text", "").strip()
        if not text:
            return {"error": "empty"}
        _run(lambda emit: CONSOLE.chat(text, emit))
        return {"started": "chat"}

    @app.post("/api/provision/{service}")
    def provision(service: str, budget: int = 15) -> dict:
        _run(CONSOLE.provision, service, budget)
        return {"started": service}

    @app.post("/api/revoke")
    def revoke() -> dict:
        _run(lambda emit: CONSOLE.revoke(emit))
        return {"started": "revoke"}

    @app.post("/api/llm/toggle")
    def llm_toggle() -> dict:
        """Operator switch: mute/unmute live judgment (contrast LLM vs deterministic
        without restarting). Only meaningful when an endpoint is configured and warm."""
        CONSOLE.llm_muted = not CONSOLE.llm_muted
        return CONSOLE.status()["llm"]

    @app.post("/api/reset")
    def reset() -> dict:
        CONSOLE.reset()
        _broadcast({"kind": "reset", "domain": "chain", "title": "reset",
                    "detail": "session cleared", "t": 0})
        return {"reset": True}

    @app.get("/api/events")
    def events() -> StreamingResponse:
        q: queue.Queue = queue.Queue()
        with _subs_lock:
            _subscribers.append(q)

        def stream():
            hello = {"kind": "hello", "domain": "controller", "title": "connected",
                     "detail": "streaming live", "t": 0}
            yield f"data: {json.dumps(hello)}\n\n"
            try:
                while True:
                    try:
                        event = q.get(timeout=15)
                        yield f"data: {json.dumps(event)}\n\n"
                    except queue.Empty:
                        yield ": keepalive\n\n"
            finally:
                with _subs_lock:
                    if q in _subscribers:
                        _subscribers.remove(q)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


def main() -> None:
    import uvicorn

    print("operator console → http://127.0.0.1:8099")
    uvicorn.run(build_app(), host="127.0.0.1", port=8099, log_level="warning")


if __name__ == "__main__":
    main()
