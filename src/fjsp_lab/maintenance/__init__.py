"""Graduation model: identical parallel machines with mandatory maintenance windows.

Modules, from data to methods:

* ``instance``, ``schedule``: immutable inputs and the plan type;
* ``feasibility``: the checker every plan must pass;
* ``generator``: deterministic G3A instances and learning splits;
* ``cpsat``, ``enumeration``: exact reference (CP-SAT) and tiny brute-force oracle;
* ``env``, ``rules``: construction MDP and EDD/MDD/ATC dispatching;
* ``metaheuristics``: GA, SA and improved GA on a token-sequence decoder;
* ``features``, ``scoring_policy``, ``attention_policy``: learned constructive
  policies (NumPy MLP; PyTorch Transformer, imported separately).
"""

from fjsp_lab.maintenance.feasibility import (
    InfeasiblePlanError,
    MaintenanceViolation,
    calculate_total_tardiness,
    check_parallel_maintenance_feasibility,
)
from fjsp_lab.maintenance.instance import (
    MaintenanceRequirement,
    ParallelMaintenanceInstance,
    ProductionTask,
    to_fjsp_instance,
)
from fjsp_lab.maintenance.schedule import MaintenanceRecord, MaintenanceScheduleResult

__all__ = [
    "ProductionTask", "MaintenanceRequirement", "ParallelMaintenanceInstance", "to_fjsp_instance",
    "MaintenanceRecord", "MaintenanceScheduleResult",
    "MaintenanceViolation", "InfeasiblePlanError", "calculate_total_tardiness",
    "check_parallel_maintenance_feasibility",
]
