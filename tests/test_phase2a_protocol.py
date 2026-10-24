import json

import pytest

from src.data.instance import FJSPInstance


def protocol_payload():
    return {"schema_version": 1, "protocol_id": "test-v1", "phase": "Phase 2A",
            "instances": [{"id": "tiny", "path": "instances/tiny.fjs"}],
            "event_types": ["machine_breakdown", "job_arrival", "processing_time_change"],
            "rules": ["fifo", "spt", "eft"], "seeds": [42], "timing_repetitions": 2}


def write_protocol(tmp_path, payload=None):
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload or protocol_payload()), encoding="utf-8")
    return path


@pytest.mark.parametrize("field,value", [
    ("phase", "RL"), ("rules", ["ppo"]), ("event_types", ["agv"]),
    ("seeds", [True]), ("seeds", [42, 42]), ("timing_repetitions", 0),
    ("rules", ["eft", "eft"]), ("unexpected", "ignored"),
])
def test_protocol_refuses_out_of_scope_or_ambiguous_configuration(tmp_path, field, value):
    from src.research.protocol import load_protocol
    payload = protocol_payload()
    payload[field] = value
    with pytest.raises(ValueError):
        load_protocol(write_protocol(tmp_path, payload), tmp_path)


@pytest.mark.parametrize("instance_path", ["../outside.fjs", "C:/outside.fjs", "/outside.fjs"])
def test_protocol_refuses_instance_paths_outside_the_project(tmp_path, instance_path):
    from src.research.protocol import load_protocol
    payload = protocol_payload()
    payload["instances"][0]["path"] = instance_path
    with pytest.raises(ValueError):
        load_protocol(write_protocol(tmp_path, payload), tmp_path)


def test_duplicate_instance_identity_is_rejected(tmp_path):
    from src.research.protocol import load_protocol
    payload = protocol_payload()
    payload["instances"].append({"id": "other", "path": "instances/tiny.fjs"})
    with pytest.raises(ValueError):
        load_protocol(write_protocol(tmp_path, payload), tmp_path)


def test_breakdown_waits_for_running_operation_and_preserves_frozen_prefix():
    from src.research.protocol import build_case
    from src.dynamic import reschedule_from_state
    instance = FJSPInstance.from_jobs_array([[[(0, 3)], [(0, 2)]]])
    case = build_case(instance, "machine_breakdown", 42)
    assert case.event_spec == {"type": "machine_breakdown", "time": 3, "machine_id": 0, "repair_time": 4}
    assert [(r.op_id, r.start, r.end) for r in case.frozen] == [(0, 0, 3)]
    assert reschedule_from_state(case.state, case.frozen, rule="eft").makespan == 6


def test_processing_change_targets_unstarted_operation_and_keeps_original_data():
    from src.research.protocol import build_case
    instance = FJSPInstance.from_jobs_array([[[(0, 3)], [(0, 2)]]])
    case = build_case(instance, "processing_time_change", 42)
    assert case.event_spec == {"type": "processing_time_change", "time": 1, "job_id": 0, "op_id": 1,
                               "machine_id": 0, "new_processing_time": 3}
    assert case.state.instance.get_processing_time(0, 1, 0) == 3
    assert instance.get_processing_time(0, 1, 0) == 2
    assert [(r.op_id, r.end) for r in case.frozen] == [(0, 3)]


def test_arrival_releases_a_complete_cloned_route_at_the_event_time():
    from src.research.protocol import build_case
    instance = FJSPInstance.from_jobs_array([[[(0, 3)], [(0, 2)]]])
    case = build_case(instance, "job_arrival", 42)
    assert case.state.instance.num_jobs == 2
    assert case.state.job_release_times == (0, 1)
    assert case.event_spec["operations"] == [[[0, 3]], [[0, 2]]]
    assert case.state.instance.jobs[1].num_ops == 2
