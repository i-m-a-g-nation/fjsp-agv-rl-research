"""Innovation project L1: flexible job shop with AGV transport and input buffers.

Modules, from data to methods:

* ``instance``: immutable inputs (FJSP + travel matrix, vehicles, buffers) and
  the FJSPT benchmark reader;
* ``schedule``: production ScheduleResult plus transport records;
* ``feasibility``: the checker every schedule must pass (production part by
  the unchanged static FJSP checker);
* ``simulator``, ``rules``: event-driven simulation and joint / decoupled rules;
* ``sequences``: earliest schedule from machine and vehicle sequences (reference-solution replay);
* ``cpsat``: small-instance CP-SAT reference.

Depends only on ``fjsp_lab.fjsp``. Model: docs/models/logistics_model_zh.md.
"""

from fjsp_lab.logistics.feasibility import (
    InfeasibleLogisticsError,
    LogisticsViolation,
    check_logistics_feasibility,
    require_feasible,
)
from fjsp_lab.logistics.instance import LogisticsInstance, load_fjspt, parse_fjspt
from fjsp_lab.logistics.schedule import LogisticsSchedule, TransportRecord, required_transports

__all__ = [
    "LogisticsInstance", "load_fjspt", "parse_fjspt",
    "LogisticsSchedule", "TransportRecord", "required_transports",
    "LogisticsViolation", "InfeasibleLogisticsError", "check_logistics_feasibility", "require_feasible",
]
