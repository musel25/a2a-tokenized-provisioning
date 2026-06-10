import a2a_interfaces


def test_package_imports_and_declares_schema_version():
    assert a2a_interfaces.V == 0
