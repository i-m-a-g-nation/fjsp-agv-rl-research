"""Backward-compatible heuristic solver facade.

The implementations live in smaller modules:
- baselines.py: simple job-order baseline heuristics
- dispatching.py: strict ready-operation dispatching rules
"""

from __future__ import annotations

from src.solvers.baselines import (
    earliest_finish_time_solve,
    fifo_solve,
    random_solve,
    spt_solve,
)
from src.solvers.dispatching import (
    dispatch_eft_solve,
    dispatch_fifo_solve,
    dispatch_mwkr_solve,
    dispatch_random_solve,
    dispatch_spt_solve,
)

__all__ = [
    "fifo_solve",
    "spt_solve",
    "earliest_finish_time_solve",
    "random_solve",
    "dispatch_fifo_solve",
    "dispatch_spt_solve",
    "dispatch_eft_solve",
    "dispatch_mwkr_solve",
    "dispatch_random_solve",
]
