"""Ports are structural: a class satisfies a Protocol by shape, not inheritance."""

from a2a_interfaces import ApplyResult, NetworkProvisioner


class _StubProvisioner:
    """Implements NetworkProvisioner without importing or subclassing it."""

    def apply_bandwidth(self, session_id, path, capacity_bps, qos_class):
        return ApplyResult(ok=True)

    def apply_telemetry(
        self, session_id, target, sensor_paths, collector_endpoint, sample_interval_s
    ):
        return ApplyResult(ok=True)

    def teardown(self, session_id):
        return ApplyResult(ok=True)

    def health(self):
        return True


def test_conforming_class_satisfies_protocol():
    assert isinstance(_StubProvisioner(), NetworkProvisioner)


def test_nonconforming_class_does_not():
    class Empty:
        pass

    assert not isinstance(Empty(), NetworkProvisioner)
