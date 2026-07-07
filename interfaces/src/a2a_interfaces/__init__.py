"""Published language for a2a-tokenized-provisioning.

The only things two packages may share: shapes (pydantic models, `models.py`) and
ports (typing.Protocol, `ports.py`). Canonical example values live in `fixtures.py`.
See docs/03-interfaces.md and CLAUDE.md rules 1-4.
"""

from .models import (
    ActionPayload,
    ActivateRequest,
    ChallengeRequest,
    ChallengeResponse,
    ProofPayload,
    SessionInfo,
    TeardownRequest,
    V,
    ApplyResult,
    BandwidthNeed,
    BandwidthParams,
    DecisionOutput,
    EntitlementView,
    ErrorCode,
    Offer,
    ResolvedNode,
    ResolvedPath,
    ServiceNeed,
    SessionState,
    SignedOffer,
    TelemetryNeed,
    TelemetryParams,
    TelemetrySample,
    TimeWindow,
)
from .ports import EntitlementReader, NetworkProvisioner

__all__ = [
    "ActionPayload",
    "ActivateRequest",
    "ChallengeRequest",
    "ChallengeResponse",
    "ProofPayload",
    "SessionInfo",
    "TeardownRequest",
    "V",
    "ApplyResult",
    "BandwidthNeed",
    "BandwidthParams",
    "DecisionOutput",
    "EntitlementReader",
    "EntitlementView",
    "ErrorCode",
    "NetworkProvisioner",
    "Offer",
    "ResolvedNode",
    "ResolvedPath",
    "ServiceNeed",
    "SessionState",
    "SignedOffer",
    "TelemetryNeed",
    "TelemetryParams",
    "TelemetrySample",
    "TimeWindow",
]
