"""Scheduling research platform.

* ``fjsp_lab.fjsp``: Phase 1 static flexible job shop (data, rules, CP-SAT, checker).
* ``fjsp_lab.dynamic``: Phase 2A dynamic events and rescheduling on top of it.
* ``fjsp_lab.maintenance``: graduation model, identical parallel machines with
  one mandatory maintenance per machine, minimizing total tardiness.

Every algorithm returns a ``ScheduleResult`` that has passed the matching
feasibility checker; an infeasible plan raises instead of being returned.
"""
