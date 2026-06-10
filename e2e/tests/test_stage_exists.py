"""M0.1 no-op: proves the workspace wiring (e2e depends on interfaces) before
any real code exists. Replaced in spirit by the lifecycle tests at M0.3."""

import a2a_interfaces
import e2e


def test_stage_can_see_the_treaty():
    assert a2a_interfaces.V == 0
    assert e2e.__doc__ is not None
