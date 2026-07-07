"""The HTTP surface (docs/03 §3) — parse, call the service, map codes to statuses.

Deliberately logic-free: if an `if` about entitlements appears in this file, it is in
the wrong file (docs/05 §6). The ErrorCode→status table is the only decision here,
and it is data.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from a2a_interfaces import (
    ActivateRequest,
    ChallengeRequest,
    ChallengeResponse,
    ErrorCode,
    TeardownRequest,
)

from .service import ControllerService, Denied

# 404 = no such thing · 401 = your proof failed · 403 = the ticket says no ·
# 502 = the network said no (docs/05 §6)
STATUS: dict[ErrorCode, int] = {
    ErrorCode.E_UNKNOWN_ENTITLEMENT: 404,
    ErrorCode.E_BAD_PROOF: 401,
    ErrorCode.E_NONCE_REUSED: 401,
    ErrorCode.E_NOT_OWNER: 403,
    ErrorCode.E_NOT_STARTED: 403,
    ErrorCode.E_EXPIRED: 403,
    ErrorCode.E_REVOKED: 403,
    ErrorCode.E_SCOPE: 403,
    ErrorCode.E_CONFLICT: 403,
    ErrorCode.E_NETWORK: 502,
}


def build_app(service: ControllerService) -> FastAPI:
    app = FastAPI(title="a2a-controller", version="0")

    @app.exception_handler(Denied)
    async def _denied(_request, exc: Denied):
        return JSONResponse(status_code=STATUS[exc.code], content={"error": exc.code.value})

    @app.post("/v0/challenge")
    def challenge(body: ChallengeRequest) -> ChallengeResponse:
        issued = service.challenge(body.entitlement_id)
        return ChallengeResponse(
            nonce=issued.nonce,
            controller_id=issued.controller_id,
            expires_at=issued.expires_at,
        )

    @app.post("/v0/activate")
    def activate(body: ActivateRequest):
        return service.activate(
            body.entitlement_id, body.action.kind, body.proof.nonce, body.proof.signature
        )

    @app.post("/v0/teardown")
    def teardown(body: TeardownRequest):
        return {"state": service.teardown(body.session_id).state.value}

    @app.get("/v0/sessions/{session_id}")
    def session(session_id: str):
        return service.session(session_id)

    return app
