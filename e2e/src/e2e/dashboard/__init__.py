"""Dashboard (M6.4, ADR-003): components emit DashboardEvents; Streamlit tails them."""

from .emitter import RunLog, read_events

__all__ = ["RunLog", "read_events"]
