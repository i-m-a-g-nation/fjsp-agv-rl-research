import csv

from experiments.exp_015_dynamic_event_file_check import (
    audit_event_file,
    run_event_file_audit,
    write_event_audit_csv,
)


def test_event_file_audit_passes_valid_ordered_file(tmp_path):
    path = tmp_path / "dynamic_events_valid.json"
    path.write_text(
        """
        [
          {"type": "machine_breakdown", "time": 2, "machine_id": 0, "repair_time": 5},
          {"type": "machine_repair", "time": 5, "machine_id": 0}
        ]
        """,
        encoding="utf-8",
    )

    audit = audit_event_file(path)

    assert audit.status == "PASS"
    assert audit.event_count == 2
    assert audit.first_time == 2
    assert audit.last_time == 5
    assert audit.nondecreasing_time


def test_event_file_audit_rejects_out_of_order_times(tmp_path):
    path = tmp_path / "dynamic_events_out_of_order.json"
    path.write_text(
        """
        [
          {"type": "machine_repair", "time": 5, "machine_id": 0},
          {"type": "machine_breakdown", "time": 2, "machine_id": 0, "repair_time": 5}
        ]
        """,
        encoding="utf-8",
    )

    audit = audit_event_file(path)

    assert audit.status == "FAIL"
    assert audit.event_count == 2
    assert not audit.nondecreasing_time
    assert audit.note == "EVENT_TIMES_NOT_NONDECREASING"


def test_event_file_audit_rejects_invalid_specs(tmp_path):
    path = tmp_path / "dynamic_events_bad.json"
    path.write_text('[{"type": "unknown", "time": 1}]', encoding="utf-8")

    audit = audit_event_file(path)

    assert audit.status == "FAIL"
    assert audit.note.startswith("LOAD_ERROR:")


def test_event_file_audit_discovers_and_writes_csv(tmp_path):
    path = tmp_path / "dynamic_events_valid.json"
    path.write_text(
        '[{"type": "job_arrival", "time": 3, "operations": [[[0, 2]]]}]',
        encoding="utf-8",
    )

    audits = run_event_file_audit(tmp_path)
    output = tmp_path / "audit.csv"
    write_event_audit_csv(output, audits)

    assert len(audits) == 1
    assert audits[0].file_name == "dynamic_events_valid.json"
    with output.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["status"] == "PASS"
    assert rows[0]["event_count"] == "1"
