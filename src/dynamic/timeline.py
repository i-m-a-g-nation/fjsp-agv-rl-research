from __future__ import annotations

from collections.abc import Iterable

from src.dynamic.events import DynamicEvent
from src.dynamic.state import DynamicFJSPState


def apply_events(
    state: DynamicFJSPState,
    events: Iterable[DynamicEvent],
) -> DynamicFJSPState:
    """Apply a time-ordered event sequence to a dynamic FJSP state."""

    current_state = state
    previous_time = state.current_time
    for event in events:
        if event.time < previous_time:
            raise ValueError("dynamic events must be sorted by non-decreasing time")
        current_state = current_state.apply_event(event)
        previous_time = event.time
    return current_state
