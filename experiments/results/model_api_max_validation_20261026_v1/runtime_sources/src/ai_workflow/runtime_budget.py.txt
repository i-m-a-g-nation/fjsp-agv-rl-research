"""Persistent, conservative reservations; waiting for humans is not execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from contextlib import contextmanager
import json
import math
from pathlib import Path
import sqlite3
import time


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class BudgetLimits:
    max_active_seconds: float = 120.0
    max_provider_calls: int = 8
    max_output_tokens: int = 16384

    def __post_init__(self):
        if (type(self.max_active_seconds) not in {int, float} or not math.isfinite(self.max_active_seconds)
                or not 0.1 <= self.max_active_seconds <= 600
                or type(self.max_provider_calls) is not int or not 0 <= self.max_provider_calls <= 20
                or type(self.max_output_tokens) is not int or not 0 <= self.max_output_tokens <= 131072):
            raise ValueError("Invalid execution budget limits")


class RunBudget:
    def __init__(self, path: Path, limits: BudgetLimits):
        self.path, self.limits = Path(path), limits
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.segment_started: float | None = None
        self.segment_id: int | None = None
        encoded = json.dumps(asdict(limits), sort_keys=True)
        with self._connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS workflow_budget (id INTEGER PRIMARY KEY, limits_json TEXT NOT NULL, active_seconds REAL NOT NULL, provider_calls INTEGER NOT NULL, output_tokens_reserved INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS workflow_segments (id INTEGER PRIMARY KEY, reserved_seconds REAL NOT NULL, started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_seconds REAL)")
            db.execute("INSERT OR IGNORE INTO workflow_budget VALUES (1, ?, 0, 0, 0)", (encoded,))
            if db.execute("SELECT limits_json FROM workflow_budget WHERE id=1").fetchone()[0] != encoded:
                raise ValueError("Cannot change budget limits on resume")

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def start_segment(self, segment_id: int | None = None):
        self.segment_id = segment_id
        self.segment_started = time.monotonic()

    def snapshot(self) -> dict:
        return self.read_snapshot(self.path)

    @staticmethod
    def read_snapshot(path: Path) -> dict:
        db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
        try:
            limits, active, calls, tokens = db.execute("SELECT limits_json, active_seconds, provider_calls, output_tokens_reserved FROM workflow_budget WHERE id=1").fetchone()
            reserved = db.execute("SELECT COALESCE(SUM(reserved_seconds),0) FROM workflow_segments WHERE finished_seconds IS NULL").fetchone()[0]
            return {"limits": json.loads(limits), "active_seconds": active, "active_seconds_charged": active + reserved,
                    "active_seconds_reserved": reserved, "provider_calls": calls, "output_tokens_reserved": tokens}
        finally:
            db.close()

    def remaining_seconds(self) -> float:
        elapsed = 0.0 if self.segment_started is None else time.monotonic() - self.segment_started
        own_reservation = 0.0
        if self.segment_id is not None:
            with self._connection() as db:
                row = db.execute("SELECT reserved_seconds FROM workflow_segments WHERE id=? AND finished_seconds IS NULL", (self.segment_id,)).fetchone()
                if row is None:
                    raise BudgetExceeded("Active execution segment is no longer reserved")
                own_reservation = row[0]
        remaining = self.limits.max_active_seconds - self.snapshot()["active_seconds_charged"] + own_reservation - elapsed
        if remaining <= 0:
            raise BudgetExceeded("Active execution time budget exhausted")
        return remaining

    def reserve_active_segment(self) -> tuple[int, float]:
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("SELECT active_seconds FROM workflow_budget WHERE id=1").fetchone()[0]
            reserved = db.execute("SELECT COALESCE(SUM(reserved_seconds),0) FROM workflow_segments WHERE finished_seconds IS NULL").fetchone()[0]
            remaining = self.limits.max_active_seconds - active - reserved
            if remaining <= 0:
                raise BudgetExceeded("Active execution time budget exhausted")
            identifier = db.execute("INSERT INTO workflow_segments(reserved_seconds) VALUES (?)", (remaining,)).lastrowid
            return identifier, remaining

    def finish_active_segment(self, segment_id: int, seconds: float):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Invalid active execution duration")
        with self._connection() as db:
            changed = db.execute("UPDATE workflow_segments SET finished_seconds=? WHERE id=? AND finished_seconds IS NULL", (seconds, segment_id)).rowcount
            if changed != 1:
                raise ValueError("Active segment already settled or missing")
            db.execute("UPDATE workflow_budget SET active_seconds=active_seconds+? WHERE id=1", (seconds,))

    def reserve_provider_call(self, *, output_tokens: int = 0, attempts: int = 1):
        if type(output_tokens) is not int or output_tokens < 0 or type(attempts) is not int or attempts < 1:
            raise ValueError("Invalid provider reservation")
        self.remaining_seconds()
        with self._connection() as db:
            changed = db.execute(
                "UPDATE workflow_budget SET provider_calls=provider_calls+?, output_tokens_reserved=output_tokens_reserved+? WHERE id=1 AND provider_calls+?<=? AND output_tokens_reserved+?<=?",
                (attempts, output_tokens * attempts, attempts, self.limits.max_provider_calls,
                 output_tokens * attempts, self.limits.max_output_tokens),
            ).rowcount
            if changed != 1:
                raise BudgetExceeded("Provider call or output token reservation budget exhausted")

    def record_active_seconds(self, seconds: float):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Invalid active execution duration")
        with self._connection() as db:
            db.execute("UPDATE workflow_budget SET active_seconds=active_seconds+? WHERE id=1", (seconds,))
