"""Immutable inputs of the L1 logistics model: FJSP + AGV transport + input buffers.

Locations are the machines 0..m-1 and the load/unload (L/U) station m.
``travel[a][b]`` is the travel time between locations, used for empty and
loaded trips alike; ``handling_time`` is added to every loaded trip. Machine
i holds at most 1 + ``buffer_capacity[i]`` jobs (the machine itself plus its
input buffer; ``None`` = unlimited). With ``blocking`` a finished job stays on
its machine until a vehicle picks it up; without it the job moves at once to
an unlimited output buffer (the FJSPT benchmark convention). With
``return_to_lu`` every finished job is carried back to L/U. The model is
specified in docs/models/logistics_model_zh.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from fjsp_lab.fjsp.instance import FJSPInstance, validate_instance


def _integer(value: object, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}; booleans are not accepted')


@dataclass(frozen=True)
class LogisticsInstance:
    production: FJSPInstance
    travel: tuple[tuple[int, ...], ...]
    num_vehicles: int
    buffer_capacity: tuple[int | None, ...]
    handling_time: int = 0
    return_to_lu: bool = True
    blocking: bool = True

    def __post_init__(self) -> None:
        validate_instance(self.production)
        m = self.production.num_machines
        try:
            travel = tuple(tuple(row) for row in self.travel)
            capacity = tuple(self.buffer_capacity)
        except TypeError as exc:
            raise ValueError('travel and buffer_capacity must be sequences') from exc
        if len(travel) != m + 1 or any(len(row) != m + 1 for row in travel):
            raise ValueError(f'travel must be a {m + 1} x {m + 1} matrix (machines plus the L/U station)')
        for a, row in enumerate(travel):
            for b, value in enumerate(row):
                _integer(value, f'travel[{a}][{b}]')
            if row[a] != 0:
                raise ValueError('travel time from a location to itself must be 0')
        _integer(self.num_vehicles, 'num_vehicles', 1)
        if len(capacity) != m:
            raise ValueError('buffer_capacity needs one entry per machine')
        for i, value in enumerate(capacity):
            if value is not None:
                _integer(value, f'buffer_capacity[{i}]')
        _integer(self.handling_time, 'handling_time')
        if type(self.return_to_lu) is not bool or type(self.blocking) is not bool:
            raise ValueError('return_to_lu and blocking must be bools')
        object.__setattr__(self, 'travel', travel)
        object.__setattr__(self, 'buffer_capacity', capacity)

    @classmethod
    def create(cls, production: FJSPInstance, travel: Sequence[Sequence[int]], *, num_vehicles: int,
               buffer_capacity: int | None | Sequence[int | None] = None, handling_time: int = 0,
               return_to_lu: bool = True, blocking: bool = True) -> LogisticsInstance:
        """Build an instance; a single buffer capacity (or None) applies to every machine."""
        if buffer_capacity is None or type(buffer_capacity) is int:
            buffer_capacity = (buffer_capacity,) * production.num_machines
        return cls(production, travel, num_vehicles, buffer_capacity, handling_time, return_to_lu, blocking)

    @property
    def num_machines(self) -> int:
        return self.production.num_machines

    @property
    def num_jobs(self) -> int:
        return self.production.num_jobs

    @property
    def lu(self) -> int:
        """Location index of the load/unload station."""
        return self.production.num_machines

    def loaded_time(self, origin: int, destination: int) -> int:
        """Duration of a loaded trip, handling included."""
        return self.travel[origin][destination] + self.handling_time

    def station_capacity(self, machine: int) -> int | None:
        """Jobs machine ``machine`` may hold at once (machine + input buffer); None = unlimited."""
        capacity = self.buffer_capacity[machine]
        return None if capacity is None else 1 + capacity


def parse_layout(layout_text: str, machines: int) -> list[list[int]]:
    """Travel matrix in our location order from a layout file whose location 0 is the L/U station.

    The file is a (machines + 1) square matrix; its location f >= 1 is machine
    f - 1 (the convention of the FJSPT benchmark layouts).
    """
    rows = [[int(value) for value in line.split()] for line in layout_text.splitlines() if line.strip()]
    if len(rows) != machines + 1 or any(len(row) != machines + 1 for row in rows):
        raise ValueError(f'layout must have {machines + 1} rows for {machines} machines plus L/U')
    file_index = [f + 1 for f in range(machines)] + [0]          # our location -> file location
    return [[rows[file_index[a]][file_index[b]] for b in range(machines + 1)] for a in range(machines + 1)]


def parse_fjspt(instance_text: str, layout_text: str, *, buffer_capacity: int | None = None,
                return_to_lu: bool = False, blocking: bool = False, handling_time: int = 0,
                num_vehicles: int | None = None) -> LogisticsInstance:
    """Parse a Deroussi & Norre style FJSPT instance and its layout matrix.

    Instance: header ``jobs machines vehicles``; one line per job with the
    number of operations, then per operation ``k m_1 .. m_k p`` (1-based
    machines sharing one processing time). Layout: a (machines + 1) square
    matrix whose location 0 is the L/U station and location f >= 1 is machine
    f - 1. The defaults (no return to L/U, unlimited buffers, no blocking, no
    extra handling time) are the benchmark's conventions; they reproduce the
    published reference makespans of Deroussi & Norre's instances exactly.
    """
    tokens = [int(token) for token in instance_text.split()]
    if len(tokens) < 3:
        raise ValueError('FJSPT instance needs a header: jobs machines vehicles')
    jobs_count, machines, vehicles = tokens[:3]
    position, jobs = 3, []
    for job in range(jobs_count):
        operations = []
        count = tokens[position]
        position += 1
        for _ in range(count):
            k = tokens[position]
            eligible, p = tokens[position + 1:position + 1 + k], tokens[position + 1 + k]
            position += k + 2
            if not eligible or min(eligible) < 1 or max(eligible) > machines:
                raise ValueError(f'job {job}: machine ids must be in 1..{machines}')
            operations.append([(machine - 1, p) for machine in eligible])
        jobs.append(operations)
    if position != len(tokens):
        raise ValueError('FJSPT instance has trailing data')
    travel = parse_layout(layout_text, machines)
    production = FJSPInstance.from_jobs_array(jobs, num_machines=machines)
    return LogisticsInstance.create(production, travel, num_vehicles=num_vehicles or vehicles,
                                    buffer_capacity=buffer_capacity, handling_time=handling_time,
                                    return_to_lu=return_to_lu, blocking=blocking)


def load_fjspt(instance_path: str | Path, layout_path: str | Path, **options: object) -> LogisticsInstance:
    """Read an FJSPT instance file and layout file (UTF-8); options as in ``parse_fjspt``."""
    return parse_fjspt(Path(instance_path).read_text(encoding='utf-8'),
                       Path(layout_path).read_text(encoding='utf-8'), **options)
