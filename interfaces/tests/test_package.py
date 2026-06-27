"""M0.1 smoke test: the package imports and exposes its schema version.

A no-op like its e2e sibling (test_stage_exists.py) — it proves the workspace wiring before
any real shapes exist. Superseded in spirit by the model round-trip/reject suites at M0.2;
kept because `V` (the `"v"` every payload carries, docs/03 §0) must stay exported.
"""

import a2a_interfaces


def test_package_imports_and_declares_schema_version():
    assert a2a_interfaces.V == 0  # rule 3: shapes are versioned; v0 until a shape changes
