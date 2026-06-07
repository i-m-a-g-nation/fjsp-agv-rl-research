import pytest

from src.dynamic import (
    JobArrival,
    MachineBreakdown,
    MachineRepair,
    ProcessingTimeChange,
    event_from_spec,
    events_from_specs,
    load_event_specs_json,
)


def test_event_from_spec_builds_machine_breakdown():
    event = event_from_spec({
        "type": "machine_breakdown",
        "time": 3,
        "machine_id": 1,
        "repair_time": 9,
    })

    assert event == MachineBreakdown(time=3, machine_id=1, repair_time=9)


def test_event_from_spec_builds_all_supported_event_types():
    events = events_from_specs([
        {"type": "machine_repair", "time": 5, "machine_id": 0},
        {"type": "job_arrival", "time": 6, "operations": [[[0, 3], [1, 4]]]},
        {
            "type": "processing_time_change",
            "time": 7,
            "job_id": 0,
            "op_id": 1,
            "machine_id": 1,
            "new_processing_time": 8,
        },
    ])

    assert events[0] == MachineRepair(time=5, machine_id=0)
    assert events[1] == JobArrival(time=6, operations=(((0, 3), (1, 4)),))
    assert events[2] == ProcessingTimeChange(
        time=7,
        job_id=0,
        op_id=1,
        machine_id=1,
        new_processing_time=8,
    )


def test_event_from_spec_rejects_unknown_type():
    with pytest.raises(ValueError, match="unsupported"):
        event_from_spec({"type": "unknown", "time": 1})


def test_event_from_spec_rejects_bad_job_arrival_options():
    with pytest.raises(ValueError, match="machine options"):
        event_from_spec({
            "type": "job_arrival",
            "time": 1,
            "operations": [[["bad", 3]]],
        })


def test_load_event_specs_json_loads_utf8_array(tmp_path):
    path = tmp_path / "events.json"
    path.write_text(
        '[{"type": "machine_repair", "time": 2, "machine_id": 1}]',
        encoding="utf-8",
    )

    events = load_event_specs_json(path)

    assert events == [MachineRepair(time=2, machine_id=1)]


def test_load_event_specs_json_rejects_non_list_payload(tmp_path):
    path = tmp_path / "events.json"
    path.write_text('{"type": "machine_repair"}', encoding="utf-8")

    with pytest.raises(ValueError, match="list"):
        load_event_specs_json(path)
