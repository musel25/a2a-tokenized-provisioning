"""The authorization predicate, in isolation (M0.3 → hardened at M4.1).

The predicate is a *pure function*: no chain, no network, no clock of its own — it
decides over data the controller already fetched. That purity is the whole point
(CLAUDE.md rule 4): the same function the skeleton tests here lifts unchanged into
controller/domain.py later. A creative bouncer is a security hole, so every branch is
boring arithmetic and every deny path has a name.
"""

from __future__ import annotations

import pytest

from a2a_interfaces import ErrorCode
from a2a_interfaces.fixtures import ADA, BELL, CANONICAL_ENTITLEMENT_VIEW, WINDOW
from e2e.skeleton.stub_controller import predicate

VIEW = CANONICAL_ENTITLEMENT_VIEW  # #7: owner ADA, bandwidth, window [start, end)
MID = WINDOW.start + 1  # a chain time safely inside the window


@pytest.mark.parametrize(
    "view, owner, requester, now, active_ids, expected",
    [
        (VIEW, ADA, ADA, MID, set(), None),  # the one accept path
        (VIEW, ADA, BELL, MID, set(), ErrorCode.E_NOT_OWNER),
        (VIEW, ADA, ADA, WINDOW.start - 1, set(), ErrorCode.E_NOT_STARTED),
        (VIEW, ADA, ADA, WINDOW.end, set(), ErrorCode.E_EXPIRED),
        (
            VIEW.model_copy(update={"revoked": True}),
            ADA,
            ADA,
            MID,
            set(),
            ErrorCode.E_REVOKED,
        ),
        (
            VIEW.model_copy(update={"service_type": 9}),  # not a service we honor
            ADA,
            ADA,
            MID,
            set(),
            ErrorCode.E_SCOPE,
        ),
        (VIEW, ADA, ADA, MID, {VIEW.id}, ErrorCode.E_CONFLICT),
    ],
    ids=["accept", "not_owner", "not_started", "expired", "revoked", "scope", "conflict"],
)
def test_predicate(view, owner, requester, now, active_ids, expected):
    assert predicate(view, owner, requester, now, active_ids) == expected
