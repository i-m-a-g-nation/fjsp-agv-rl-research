"""Continue the original main-scope ledger without changing frozen materials.

This helper controls time only. Approval, evidence, and execution policy remain
the caller's responsibility; neither reader nor runner calls a model or solver.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable

from src.ai_workflow import graduation_main_scope as scope
from src.ai_workflow.research_controller import _exclusive_lock
from src.ai_workflow.runtime_budget import BudgetExceeded, BudgetLimits, RunBudget
from src.graduation.reference_protocol import encoded


LIMITS = BudgetLimits(600, 0, 0)
FINALIZATION_ALLOWANCE = 5.0


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _ledger(folder):
    """Read a closed DELETE ledger without allowing SQLite to create files."""
    path = folder / 'budget.sqlite'
    if not path.is_file() or path.is_symlink():
        raise ValueError('Missing original main budget; never recreate or replace it')
    if any((folder / ('budget.sqlite' + suffix)).exists()
           for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('Main budget has an interrupted journal or WAL sidecar')
    with path.open('rb') as handle:
        header = handle.read(100)
    if header[:16] != b'SQLite format 3\x00' or header[18:20] != b'\x01\x01':
        raise ValueError('Main budget must use the closed DELETE journal format')
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    try:
        records = db.execute('SELECT id,limits_json,active_seconds,provider_calls,'
                             'output_tokens_reserved FROM workflow_budget ORDER BY id').fetchall()
        segments = db.execute('SELECT id,reserved_seconds,finished_seconds '
                              'FROM workflow_segments ORDER BY id').fetchall()
    finally:
        db.close()
    return records, segments


def read_main_budget(scope_dir) -> dict:
    """Validate frozen preparation plus every cumulative reservation, read only.

    A valid unfinished tail reserves all remaining time. A terminal overrun is
    reported as exhausted as well; neither case may be resumed by the runner.
    Malformed histories, changes to the frozen prefix, or refunds are errors.
    """
    folder = Path(scope_dir).resolve()
    try:
        scope._check_materials(folder)
        frozen = json.loads((folder / 'budget_snapshot.json').read_text(encoding='utf-8'))
        records, rows = _ledger(folder)
        if len(records) != 1 or records[0][0] != 1 or len(rows) < 2:
            raise ValueError('Main budget was reset or its preparation prefix is missing')
        _, limits_json, active, calls, tokens = records[0]
        expected_limits = asdict(LIMITS)
        if (limits_json != json.dumps(expected_limits, sort_keys=True)
                or not _number(active) or active < 0
                or type(calls) is not int or calls != 0
                or type(tokens) is not int or tokens != 0):
            raise ValueError('Main budget limits or accumulated charges changed')
        finished_total = 0.0
        reserved_total = 0.0
        segments = []
        prefix_active = None
        for index, (identifier, reserved, finished) in enumerate(rows, start=1):
            if (type(identifier) is not int or identifier != index
                    or not _number(reserved) or not 0 < reserved <= 600
                    or reserved != 600 - finished_total):
                raise ValueError('Main budget reservation or segment sequence changed')
            if finished is None:
                if index != len(rows) or index <= 2:
                    raise ValueError('A segment follows an unsettled main budget reservation')
                reserved_total = reserved
            else:
                if not _number(finished) or finished < 0:
                    raise ValueError('Main budget has an invalid or refunded duration')
                if finished > reserved and index != len(rows):
                    raise ValueError('A segment follows an exhausted main budget')
                finished_total += finished
                if not math.isfinite(finished_total):
                    raise ValueError('Main budget duration overflow')
            segments.append({'id': identifier, 'reserved_seconds': reserved,
                             'finished_seconds': finished})
            if index == 2:
                prefix_active = finished_total
        if active != finished_total:
            raise ValueError('Main budget charge differs from the sum of finished segments')
        if (not 0 < segments[0]['finished_seconds'] <= 600
                or segments[1]['finished_seconds'] != FINALIZATION_ALLOWANCE
                or segments[1]['reserved_seconds'] < FINALIZATION_ALLOWANCE):
            raise ValueError('Main preparation or prepaid finalization prefix changed')
        prefix = {'limits': expected_limits, 'active_seconds': prefix_active,
                  'active_seconds_charged': prefix_active, 'active_seconds_reserved': 0,
                  'provider_calls': 0, 'output_tokens_reserved': 0,
                  'segments': segments[:2], 'finalization_prepaid_seconds': FINALIZATION_ALLOWANCE}
        if encoded(prefix) != encoded(frozen):
            raise ValueError('Main preparation ledger differs from its frozen budget receipt')
        charged = active + reserved_total
        return {'limits': expected_limits, 'active_seconds': active,
                'active_seconds_charged': charged, 'active_seconds_reserved': reserved_total,
                'provider_calls': calls, 'output_tokens_reserved': tokens, 'segments': segments,
                'finalization_prepaid_seconds': FINALIZATION_ALLOWANCE,
                'remaining_active_seconds': max(0.0, 600 - charged)}
    except (sqlite3.Error, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid original main budget or frozen scope materials') from exc


@dataclass(frozen=True)
class MainBudgetHandle:
    """Cheap cooperative work checkpoints against one fixed monotonic deadline."""
    _scope_dir: Path
    _work_deadline: float

    def remaining(self) -> float:
        """Return work time left, excluding the prepaid finalization allowance."""
        remaining = self._work_deadline - time.monotonic()
        if remaining <= 0:
            raise BudgetExceeded('Main phase work deadline exhausted')
        return remaining

    def check(self) -> float:
        """Check time without reading scope files or opening the ledger."""
        return self.remaining()

    def snapshot(self) -> dict:
        """Optionally validate the ledger; its read time counts as work time."""
        self.check()
        result = read_main_budget(self._scope_dir)
        self.check()
        return result


def _exhaust_unmeasured_finalization(budget):
    # An unsuccessful receipt cannot establish a bounded finalization duration.
    # Leave any remaining time reserved, so another invocation cannot retry it.
    try:
        budget.reserve_active_segment()
    except BudgetExceeded:
        pass


def run_main_phase(scope_dir, control_dir, work: Callable[[MainBudgetHandle], Any],
                   finalize: Callable[[Any, dict, Callable[[], float]], Any], *,
                   started_at: float | None = None):
    """Run work and persist its receipt under the original cumulative budget.

    ``work(handle)`` returns the value passed to ``finalize(value, snapshot,
    check_final)``. The runner returns the finalizer's value. Both callbacks must
    cooperate with deadlines; a callback returning late is rejected afterward.
    Work exceptions are settled at actual elapsed time and skip finalization.
    Successful finalization prepays five seconds, including settlement, receipt
    validation, reservation, and callback persistence, with no unused refund.
    ``started_at`` may carry a caller's earlier monotonic entry time so its
    authorized preflight is charged too. It must be finite and not in the future.
    """
    entered = time.monotonic()
    folder, control = Path(scope_dir).resolve(), Path(control_dir).resolve()
    if control == folder or folder in control.parents:
        raise ValueError('Main control directory must be outside immutable scope materials')
    control.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(control):
        if started_at is not None:
            if not _number(started_at) or started_at > time.monotonic():
                raise ValueError('Main budget start must be a finite past monotonic time')
            entered = started_at
        # RunBudget initializes missing tables: validate before allowing it near
        # the original ledger, and never initialize an exhausted/crashed run.
        previous = read_main_budget(folder)
        remaining = previous['remaining_active_seconds']
        if remaining <= 0:
            raise BudgetExceeded('Original main budget is exhausted or interrupted')
        deadline = entered + remaining
        handle = MainBudgetHandle(folder, deadline - FINALIZATION_ALLOWANCE)
        budget = RunBudget(folder / 'budget.sqlite', LIMITS)
        segment, _ = budget.reserve_active_segment()
        budget.start_segment(segment)
        try:
            handle.check()
            value = work(handle)
            handle.check()
        except BaseException:
            budget.finish_active_segment(segment, time.monotonic() - entered)
            raise

        # Capture this before settlement: every subsequent step consumes the
        # same bounded allowance, including the original segment's settlement.
        final_started = time.monotonic()

        def check_final():
            now = time.monotonic()
            available = min(final_started + FINALIZATION_ALLOWANCE, deadline) - now
            if available <= 0:
                raise BudgetExceeded('Main phase finalization deadline exhausted')
            return available

        try:
            budget.finish_active_segment(segment, final_started - entered)
            extra, available = budget.reserve_active_segment()
            if available < FINALIZATION_ALLOWANCE:
                raise BudgetExceeded('Insufficient original budget for finalization receipts')
            budget.finish_active_segment(extra, FINALIZATION_ALLOWANCE)
            check_final()
            snapshot = read_main_budget(folder)
            check_final()
            result = finalize(value, snapshot, check_final)
            check_final()
            return result
        except BaseException as exc:
            _exhaust_unmeasured_finalization(budget)
            try:
                check_final()
            except BudgetExceeded as expired:
                raise expired from exc
            raise
