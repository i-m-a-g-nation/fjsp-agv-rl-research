from __future__ import annotations

from src.data.instance import FJSPInstance, validate_instance
from src.scheduling.encoding import ScheduleRecord, ScheduleResult


class Violation:
    """One feasibility violation found in a schedule."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"Violation({self.code}: {self.message})"


_MISSING = object()


def _record_has_integer_fields(rec, index: int, violations: list[Violation]) -> bool:
    """Reject malformed records before indexing, arithmetic, sorting or hashing."""

    if not isinstance(rec, ScheduleRecord):
        violations.append(Violation("INVALID_RECORD", f"Record {index} must be a ScheduleRecord"))
        return False

    valid = True
    for field, code in (
        ("job_id", "INVALID_JOB_ID"),
        ("op_id", "INVALID_OP_ID"),
        ("machine_id", "INVALID_MACHINE_ID"),
        ("start", "INVALID_TIME"),
        ("end", "INVALID_TIME"),
        ("processing_time", "INVALID_TIME"),
    ):
        value = getattr(rec, field, _MISSING)
        if value is _MISSING:
            violations.append(Violation("INVALID_RECORD", f"Record {index} is missing {field}"))
            valid = False
        elif type(value) is not int:
            # Python integers are finite; excluding floats also excludes NaN,
            # infinity and numerically equal values such as 0.0 or True.
            violations.append(Violation(code, f"Record {index}: {field} must be a Python int (not bool)"))
            valid = False
    return valid


def _record_is_ident_valid(rec, instance: FJSPInstance, violations: list[Violation]) -> bool:
    """Validate job and operation identifiers before indexed access."""

    # Return False when ids are invalid so later checks can avoid unsafe
    # instance.jobs[job_id] indexing.
    valid = True
    if rec.job_id < 0 or rec.job_id >= instance.num_jobs:
        violations.append(Violation(
            "INVALID_JOB_ID",
            f"Job ID {rec.job_id} out of range [0, {instance.num_jobs - 1}]",
        ))
        valid = False
    elif not (0 <= rec.op_id < instance.jobs[rec.job_id].num_ops):
        violations.append(Violation(
            "INVALID_OP_ID",
            f"Job {rec.job_id} Op ID {rec.op_id} out of range "
            f"[0, {instance.jobs[rec.job_id].num_ops - 1}]",
        ))
        valid = False
    return valid


def _validate_record_values(rec, violations: list[Violation]) -> None:
    """Validate schedule time fields."""

    # These checks are independent of the instance, so they can run even when
    # job or machine ids are invalid.
    if rec.start < 0:
        violations.append(Violation(
            "INVALID_TIME",
            f"Job {rec.job_id} Op {rec.op_id}: start={rec.start} is negative",
        ))
    if rec.processing_time <= 0:
        violations.append(Violation(
            "INVALID_TIME",
            f"Job {rec.job_id} Op {rec.op_id}: processing_time={rec.processing_time} <= 0",
        ))
    if rec.end < rec.start:
        violations.append(Violation(
            "INVALID_TIME",
            f"Job {rec.job_id} Op {rec.op_id}: end={rec.end} < start={rec.start}",
        ))
    if rec.end - rec.start != rec.processing_time:
        violations.append(Violation(
            "PROCESSING_TIME_MISMATCH",
            f"Job {rec.job_id} Op {rec.op_id}: end-start={rec.end - rec.start} "
            f"!= processing_time={rec.processing_time}",
        ))


def _validate_record_machine(rec, instance: FJSPInstance, violations: list[Violation]) -> None:
    """Validate machine id, eligibility, and processing time consistency."""

    # Machine range must be checked before asking the instance whether the
    # machine is eligible.
    if rec.machine_id < 0 or rec.machine_id >= instance.num_machines:
        violations.append(Violation(
            "INVALID_MACHINE_ID",
            f"Job {rec.job_id} Op {rec.op_id}: Machine {rec.machine_id}"
            f" out of range [0, {instance.num_machines - 1}]",
        ))
        return

    if not (0 <= rec.job_id < instance.num_jobs):
        return
    if not (0 <= rec.op_id < instance.jobs[rec.job_id].num_ops):
        return

    # Eligibility and processing-time checks connect the schedule back to the
    # immutable benchmark data.
    eligible = instance.is_machine_eligible(rec.job_id, rec.op_id, rec.machine_id)
    if not eligible:
        violations.append(Violation(
            "MACHINE_INELIGIBLE",
            f"Job {rec.job_id} Op {rec.op_id}: Machine {rec.machine_id} "
            f"not in eligible set",
        ))
    else:
        expected_pt = instance.get_processing_time(rec.job_id, rec.op_id, rec.machine_id)
        if rec.processing_time != expected_pt:
            violations.append(Violation(
                "PT_INSTANCE_MISMATCH",
                f"Job {rec.job_id} Op {rec.op_id} on Machine {rec.machine_id}: "
                f"recorded pt={rec.processing_time} != instance pt={expected_pt}",
            ))


def check_feasibility(
    result: ScheduleResult,
    *,
    expected_instance: FJSPInstance | None = None,
) -> tuple[bool, list[Violation]]:
    """Check integer static FJSP data and all seven schedule constraints.

    Malformed data is reported as violations, without repairing or coercing it.
    Supplying expected_instance binds the result to the caller's problem data;
    independently reconstructed but equal instances are accepted.
    """

    violations: list[Violation] = []
    if not isinstance(result, ScheduleResult):
        return False, [Violation("INVALID_RESULT", "Result must be a ScheduleResult")]

    instance = getattr(result, "instance", None)

    # A schedule without an instance cannot be validated against operation
    # counts, eligible machines, or processing times.
    if instance is None:
        violations.append(Violation("NO_INSTANCE", "ScheduleResult has no instance reference"))
        return False, violations

    try:
        validate_instance(instance)
    except (TypeError, ValueError) as exc:
        return False, [Violation("INVALID_INSTANCE", str(exc))]

    if expected_instance is not None:
        try:
            validate_instance(expected_instance)
        except (TypeError, ValueError) as exc:
            return False, [Violation("INVALID_EXPECTED_INSTANCE", str(exc))]
        if instance != expected_instance:
            violations.append(Violation("INSTANCE_MISMATCH", "Result instance differs from the expected problem"))

    records = getattr(result, "records", None)
    if not isinstance(records, (list, tuple)):
        violations.append(Violation("INVALID_RECORDS", "ScheduleResult.records must be a list or tuple"))
        return False, violations

    makespan = getattr(result, "makespan", None)
    if type(makespan) is not int or makespan < 0:
        violations.append(Violation("INVALID_MAKESPAN", "makespan must be a nonnegative Python int (not bool)"))

    if not records:
        violations.append(Violation("NO_RECORDS", "ScheduleResult has no records"))
        return False, violations

    records_well_formed = True
    for index, rec in enumerate(records):
        if not _record_has_integer_fields(rec, index, violations):
            records_well_formed = False
    if not records_well_formed:
        return False, violations

    # First pass: local record sanity. This collects as many issues as possible
    # instead of failing fast on the first bad record.
    for rec in result.records:
        _validate_record_values(rec, violations)
        _record_is_ident_valid(rec, instance, violations)
        _validate_record_machine(rec, instance, violations)

    expected_ops = instance.total_ops
    actual_ops = len(result.records)
    if actual_ops != expected_ops:
        violations.append(Violation(
            "OP_COUNT_MISMATCH",
            f"Expected {expected_ops} operations, got {actual_ops}",
        ))

    # Each operation must appear exactly once.
    ops_scheduled: set[tuple[int, int]] = set()
    for rec in result.records:
        key = (rec.job_id, rec.op_id)
        if key in ops_scheduled:
            violations.append(Violation(
                "DUPLICATE_OP",
                f"Job {rec.job_id} Op {rec.op_id} scheduled more than once",
            ))
        ops_scheduled.add(key)

    for j_id in range(instance.num_jobs):
        for o_id in range(instance.jobs[j_id].num_ops):
            if (j_id, o_id) not in ops_scheduled:
                violations.append(Violation(
                    "MISSING_OP",
                    f"Job {j_id} Op {o_id} not scheduled",
                ))

    # Precedence is checked per job after sorting by operation id, not by the
    # insertion order of records.
    job_ops: dict[int, list[ScheduleRecord]] = {}
    for rec in result.records:
        job_ops.setdefault(rec.job_id, []).append(rec)

    for j_id, ops in job_ops.items():
        ops_sorted = sorted(ops, key=lambda r: r.op_id)
        for i in range(len(ops_sorted) - 1):
            prev_op = ops_sorted[i]
            next_op = ops_sorted[i + 1]
            if prev_op.op_id + 1 != next_op.op_id:
                violations.append(Violation(
                    "OP_SEQUENCE_GAP",
                    f"Job {j_id}: Op {prev_op.op_id} -> Op {next_op.op_id} has gap in sequence",
                ))
            if prev_op.end > next_op.start:
                violations.append(Violation(
                    "PRECEDENCE_VIOLATION",
                    f"Job {j_id}: Op {prev_op.op_id} ends at {prev_op.end} "
                    f"but Op {next_op.op_id} starts at {next_op.start}",
                ))

    # Machine capacity is checked per machine after sorting by start time.
    machine_ops: dict[int, list[ScheduleRecord]] = {}
    for rec in result.records:
        machine_ops.setdefault(rec.machine_id, []).append(rec)

    for m_id, ops in machine_ops.items():
        ops_sorted = sorted(ops, key=lambda r: r.start)
        for i in range(len(ops_sorted) - 1):
            prev_op = ops_sorted[i]
            next_op = ops_sorted[i + 1]
            if prev_op.end > next_op.start:
                violations.append(Violation(
                    "MACHINE_OVERLAP",
                    f"Machine {m_id}: Op (J{prev_op.job_id} O{prev_op.op_id}) "
                    f"ends at {prev_op.end} overlaps with "
                    f"Op (J{next_op.job_id} O{next_op.op_id}) starts at {next_op.start}",
                ))

    # Keep the stored makespan honest; experiments and comparisons depend on it.
    computed_makespan = max(r.end for r in result.records) if result.records else 0
    if type(makespan) is int and makespan != computed_makespan:
        violations.append(Violation(
            "MAKESPAN_MISMATCH",
            f"Result makespan={result.makespan} != computed={computed_makespan}",
        ))

    return len(violations) == 0, violations
