"""Lossless typed rows for existing R1 observations; no scheduling decisions."""
from dataclasses import dataclass
import math

from src.graduation.rl_environment import (
    ACTION_COUNT, MAX_MACHINES, MAX_TASKS, ConstructionObservation,
)

ROW_COUNT = MAX_TASKS + MAX_MACHINES
ROW_WIDTH = 13


def _boolean_tuple(values, size):
    if type(values) is not tuple or len(values) != size or any(type(value) is not bool for value in values):
        raise ValueError('Expected an immutable boolean tuple of the declared size')


def _auxiliary(value):
    if (type(value.mode) is not str or value.mode not in ('fixed', 'joint')
            or type(value.status) is not str or value.status not in ('ACTIVE', 'TERMINATED', 'TRUNCATED', 'FAILED')
            or type(value.steps) is not int or not 0 <= value.steps <= ROW_COUNT
            or type(value.scale) is not int or value.scale <= 0):
        raise ValueError('Invalid observation metadata')
    _boolean_tuple(value.action_mask, ACTION_COUNT)


def _float_grid(rows, count, width):
    if type(rows) is not tuple or len(rows) != count:
        raise ValueError('Expected the complete immutable row matrix')
    for row in rows:
        if (type(row) is not tuple or len(row) != width
                or any(type(value) is not float or not math.isfinite(value) for value in row)):
            raise ValueError('Rows require the exact width and finite built-in floats')


def _payload(row, present, *, machine):
    flags = (5, 6) if machine else (2,)
    if any(row[column] not in (0.0, 1.0) for column in flags):
        raise ValueError('Observation flags must be binary floats')
    if not present and any(value != 0.0 for value in row):
        raise ValueError('Absent object slots must have zero payloads')


def _validate_observation(observation):
    if type(observation) is not ConstructionObservation:
        raise ValueError('Expected a ConstructionObservation')
    _auxiliary(observation)
    _float_grid(observation.task_features, MAX_TASKS, 3)
    _float_grid(observation.machine_features, MAX_MACHINES, 7)
    _boolean_tuple(observation.task_presence, MAX_TASKS)
    _boolean_tuple(observation.machine_presence, MAX_MACHINES)
    for row, present in zip(observation.task_features, observation.task_presence):
        _payload(row, present, machine=False)
    for row, present in zip(observation.machine_features, observation.machine_presence):
        _payload(row, present, machine=True)


@dataclass(frozen=True)
class TypedStateEncoding:
    """Version1: 24 task slots then4 machine slots, including explicit padding."""

    mode: str
    status: str
    steps: int
    scale: int
    rows: tuple[tuple[float, ...], ...]
    action_mask: tuple[bool, ...]
    version: int = 1

    def __post_init__(self):
        _validate_encoding(self)


def _validate_encoding(encoded):
    if type(encoded) is not TypedStateEncoding or type(encoded.version) is not int or encoded.version != 1:
        raise ValueError('Expected a version1 TypedStateEncoding')
    _auxiliary(encoded)
    _float_grid(encoded.rows, ROW_COUNT, ROW_WIDTH)
    for index, row in enumerate(encoded.rows):
        machine = index >= MAX_TASKS
        if row[10:12] != ((0.0, 1.0) if machine else (1.0, 0.0)) or row[12] not in (0.0, 1.0):
            raise ValueError('Row type and presence do not match the stable slot format')
        unused = row[:3] if machine else row[3:10]
        if any(value != 0.0 for value in unused):
            raise ValueError('Cross-type payload columns must be zero')
        _payload(row[3:10] if machine else row[:3], bool(row[12]), machine=machine)


def encode_construction_observation(observation: ConstructionObservation) -> TypedStateEncoding:
    """Copy payloads exactly; never reconstruct clocks or recompute action masks."""
    _validate_observation(observation)
    rows = tuple(row + (0.0,)*7 + (1.0, 0.0, float(present))
                 for row, present in zip(observation.task_features, observation.task_presence))
    rows += tuple((0.0,)*3 + row + (0.0, 1.0, float(present))
                  for row, present in zip(observation.machine_features, observation.machine_presence))
    return TypedStateEncoding(observation.mode, observation.status, observation.steps,
                              observation.scale, rows, observation.action_mask)


def decode_construction_observation(encoded: TypedStateEncoding) -> ConstructionObservation:
    """Restore every original field, rejecting any data that would be discarded."""
    _validate_encoding(encoded)
    tasks, machines = encoded.rows[:MAX_TASKS], encoded.rows[MAX_TASKS:]
    return ConstructionObservation(encoded.mode, encoded.status, encoded.steps, encoded.scale,
        tuple(row[:3] for row in tasks), tuple(row[3:10] for row in machines),
        tuple(bool(row[12]) for row in tasks), tuple(bool(row[12]) for row in machines), encoded.action_mask)
