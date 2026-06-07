from experiments.exp_017_phase2a_dynamic_report import (
    build_markdown_report,
    load_event_audit_rows,
    load_schedule_rows,
    write_markdown_report,
)


def test_phase2a_dynamic_report_summarizes_all_gates(tmp_path):
    smoke = tmp_path / "smoke.csv"
    smoke.write_text(
        "experiment_id,instance_name,algorithm,makespan,feasible,runtime_s,note\n"
        "exp_014,s1,DynamicEFT(a),8,PASS,0.1,DYNAMIC_PASS\n",
        encoding="utf-8",
    )
    audit = tmp_path / "audit.csv"
    audit.write_text(
        "file_name,event_count,first_time,last_time,nondecreasing_time,status,note\n"
        "dynamic_events_a.json,2,1,3,PASS,PASS,EVENT_FILE_OK\n",
        encoding="utf-8",
    )
    replay = tmp_path / "replay.csv"
    replay.write_text(
        "experiment_id,instance_name,algorithm,makespan,feasible,runtime_s,note\n"
        "exp_016,r1,DynamicEFT(dynamic_events_a.json),10,PASS,0.1,EVENT_FILE_DYNAMIC_PASS\n",
        encoding="utf-8",
    )

    report = build_markdown_report(
        load_schedule_rows(smoke),
        load_event_audit_rows(audit),
        load_schedule_rows(replay),
    )

    assert "Overall status: PASS." in report
    assert "| dynamic smoke reschedules | 1 | 1 |" in report
    assert "| event-file audits | 1 | 1 |" in report
    assert "| event-file replay reschedules | 1 | 1 |" in report
    assert "dynamic_events_a.json" in report
    assert "EVENT_FILE_DYNAMIC_PASS" in report


def test_phase2a_dynamic_report_marks_failed_gate(tmp_path):
    smoke = tmp_path / "smoke.csv"
    smoke.write_text(
        "experiment_id,instance_name,algorithm,makespan,feasible,runtime_s,note\n"
        "exp_014,s1,DynamicEFT(a),8,FAIL,0.1,ERROR\n",
        encoding="utf-8",
    )
    audit = tmp_path / "audit.csv"
    audit.write_text(
        "file_name,event_count,first_time,last_time,nondecreasing_time,status,note\n"
        "dynamic_events_a.json,2,1,3,PASS,PASS,EVENT_FILE_OK\n",
        encoding="utf-8",
    )
    replay = tmp_path / "replay.csv"
    replay.write_text(
        "experiment_id,instance_name,algorithm,makespan,feasible,runtime_s,note\n"
        "exp_016,r1,DynamicEFT(dynamic_events_a.json),10,PASS,0.1,EVENT_FILE_DYNAMIC_PASS\n",
        encoding="utf-8",
    )

    report = build_markdown_report(
        load_schedule_rows(smoke),
        load_event_audit_rows(audit),
        load_schedule_rows(replay),
    )

    assert "Overall status: FAIL." in report
    assert "| dynamic smoke reschedules | 0 | 1 |" in report


def test_phase2a_dynamic_report_rejects_missing_fields(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("instance_name\ns1\n", encoding="utf-8")

    try:
        load_schedule_rows(bad)
    except ValueError as exc:
        assert "missing required fields" in str(exc)
    else:
        raise AssertionError("expected missing-field rejection")


def test_write_phase2a_dynamic_report_creates_parent_directory(tmp_path):
    output = tmp_path / "nested" / "report.md"

    write_markdown_report(output, "# Report\n")

    assert output.read_text(encoding="utf-8") == "# Report\n"
