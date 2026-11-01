"""L1 instance data, benchmark reader and the logistics feasibility checker."""

from dataclasses import replace

import pytest

from fjsp_lab.fjsp import FJSPInstance, ScheduleRecord, ScheduleResult
from fjsp_lab.logistics import (
    LogisticsInstance, LogisticsSchedule, TransportRecord, check_logistics_feasibility, parse_fjspt,
    required_transports,
)

# Locations: machine 0, machine 1, L/U = 2.
TRAVEL = [[0, 1, 2], [1, 0, 3], [2, 3, 0]]
# Job 0: M0 (3) then M1 (2). Job 1: M1 (2) then M1 again (1) - no trip between them.
PRODUCTION = FJSPInstance.from_jobs_array([[[(0, 3)], [(1, 2)]], [[(1, 2)], [(1, 1)]]], num_machines=2)


def instance(buffer=None, back=True, vehicles=1):
    return LogisticsInstance.create(PRODUCTION, TRAVEL, num_vehicles=vehicles, buffer_capacity=buffer, return_to_lu=back)


def valid_schedule():
    """Hand-built plan for one vehicle (worked out in the comments)."""
    records = [ScheduleRecord.placed(0, 0, 0, 2, 3),    # job 0 on M0 [2, 5)
               ScheduleRecord.placed(1, 0, 1, 7, 2),    # job 1 on M1 [7, 9)
               ScheduleRecord.placed(1, 1, 1, 9, 1),    # job 1 stays on M1 [9, 10)
               ScheduleRecord.placed(0, 1, 1, 10, 2)]   # job 0 on M1 [10, 12) once job 1 has left
    transports = [TransportRecord(0, 0, 0, 2, 0, 0, 0, 2),     # L/U -> M0, vehicle already at L/U
                  TransportRecord(1, 0, 0, 2, 1, 2, 4, 7),     # empty M0 -> L/U (2), loaded L/U -> M1 (3)
                  TransportRecord(0, 1, 0, 0, 1, 7, 8, 9),     # empty M1 -> M0 (1), job 0 waits in M1's buffer
                  TransportRecord(1, 2, 0, 1, 2, 9, 10, 13),   # job 1 home; frees M1 at 10
                  TransportRecord(0, 2, 0, 1, 2, 13, 16, 19)]  # empty L/U -> M1 (3), job 0 home at 19
    return LogisticsSchedule(ScheduleResult.from_records(records, instance=PRODUCTION), tuple(transports), 19)


def codes(schedule, data):
    accepted, issues = check_logistics_feasibility(schedule, data)
    assert not accepted
    return {issue.code for issue in issues}


def with_trip(schedule, index, **changes):
    trips = list(schedule.transports)
    trips[index] = replace(trips[index], **changes)
    return replace(schedule, transports=tuple(trips))


def test_required_transports_skip_same_machine_operations():
    assert required_transports([0, 1], 2, True) == [(0, 2, 0), (1, 0, 1), (2, 1, 2)]
    assert required_transports([1, 1], 2, False) == [(0, 2, 1)]


@pytest.mark.parametrize('kwargs, message', [
    ({'travel': [[0, 1], [1, 0]]}, '3 x 3'),
    ({'travel': [[0, 1, 2], [1, 1, 3], [2, 3, 0]]}, 'itself'),
    ({'travel': [[0, -1, 2], [1, 0, 3], [2, 3, 0]]}, 'integer'),
    ({'num_vehicles': 0}, 'num_vehicles'),
    ({'buffer_capacity': (1,)}, 'one entry per machine'),
    ({'buffer_capacity': (True, None)}, 'integer'),
])
def test_instance_validation(kwargs, message):
    fields = dict(production=PRODUCTION, travel=TRAVEL, num_vehicles=1, buffer_capacity=(None, None))
    fields.update(kwargs)
    with pytest.raises(ValueError, match=message):
        LogisticsInstance(**fields)


def test_station_capacity_counts_the_machine_itself():
    assert instance(buffer=0).station_capacity(0) == 1
    assert instance(buffer=None).station_capacity(1) is None


def test_fjspt_reader_maps_location_zero_to_the_lu_station():
    text = '2 2 1\n 2 1 1 3 2 1 2 2\n 1 2 1 2 4\n'
    layout = '0 5 6\n7 0 8\n9 10 0\n'
    data = parse_fjspt(text, layout)
    assert data.num_vehicles == 1 and data.return_to_lu is False and data.buffer_capacity == (None, None)
    assert data.production.get_op_options(0, 1) == ((0, 2), (1, 2))
    lu = data.lu
    assert data.travel[lu][0] == 5 and data.travel[0][lu] == 7 and data.travel[0][1] == 8 and data.travel[1][lu] == 9
    with pytest.raises(ValueError, match='rows'):
        parse_fjspt(text, '0 1\n1 0\n')


def test_valid_schedule_is_accepted_with_enough_buffer():
    for buffer in (None, 1):
        assert check_logistics_feasibility(valid_schedule(), instance(buffer)) == (True, [])


def test_buffer_capacity_counts_reserved_places():
    # Job 0 is reserved for M1 at 7 while job 1 still occupies M1 until 10.
    assert codes(valid_schedule(), instance(buffer=0)) == {'BUFFER_OVERFLOW'}


def test_transport_structure_violations_are_named():
    plan, data = valid_schedule(), instance()
    assert 'TRANSPORT_MISSING' in codes(replace(plan, transports=plan.transports[:2] + plan.transports[3:]), data)
    assert 'TRANSPORT_DUPLICATE' in codes(replace(plan, transports=plan.transports + plan.transports[:1]), data)
    extra = TransportRecord(1, 1, 0, 1, 1, 9, 9, 9)
    assert 'TRANSPORT_UNEXPECTED' in codes(replace(plan, transports=plan.transports + (extra,)), data)
    assert 'TRANSPORT_ROUTE' in codes(with_trip(plan, 1, origin=0), data)
    assert 'TRANSPORT_MALFORMED' in codes(with_trip(plan, 0, pickup=0.0), data)
    assert 'TRANSPORT_UNEXPECTED' in codes(plan, instance(back=False))


def test_timing_and_vehicle_violations_are_named():
    plan, data = valid_schedule(), instance()
    assert 'TRANSPORT_DURATION' in codes(with_trip(plan, 0, delivery=1), data)
    assert 'DISPATCH_INVALID' in codes(with_trip(plan, 0, dispatch=1), data)
    assert 'PICKUP_BEFORE_READY' in codes(with_trip(plan, 2, dispatch=3, pickup=4, delivery=5), data)
    assert 'START_BEFORE_DELIVERY' in codes(with_trip(plan, 0, pickup=1, delivery=3), data)
    assert 'EMPTY_TRAVEL_SHORT' in codes(with_trip(plan, 1, pickup=3, delivery=6), data)
    assert 'VEHICLE_OVERLAP' in codes(with_trip(plan, 1, dispatch=1), data)
    assert 'VEHICLE_INVALID' in codes(with_trip(plan, 0, vehicle=1), data)


def test_blocking_makespan_and_production_violations_are_named():
    plan, data = valid_schedule(), instance()
    # Job 1 is picked up at 11, so job 0 cannot start on M1 at 10.
    blocked = with_trip(with_trip(plan, 3, pickup=11, delivery=14), 4, dispatch=14, pickup=17, delivery=20)
    assert codes(replace(blocked, makespan=20), data) == {'MACHINE_BLOCKED'}
    assert codes(replace(plan, makespan=18), data) == {'MAKESPAN_MISMATCH'}
    broken = replace(plan, production=replace(plan.production, records=plan.production.records[:-1]))
    assert codes(broken, data) == {'PRODUCTION_INVALID'}
    assert codes(LogisticsSchedule(ScheduleResult()), data) == {'PRODUCTION_INVALID'}


def test_blocking_switch_only_relaxes_machine_occupation():
    plan, data = valid_schedule(), instance()
    late_pickup = with_trip(with_trip(plan, 3, pickup=11, delivery=14), 4, dispatch=14, pickup=17, delivery=20)
    late_pickup = replace(late_pickup, makespan=20)
    assert codes(late_pickup, data) == {'MACHINE_BLOCKED'}
    free = LogisticsInstance.create(PRODUCTION, TRAVEL, num_vehicles=1, blocking=False)
    assert check_logistics_feasibility(late_pickup, free) == (True, [])


def test_decoder_rebuilds_the_hand_schedule_and_rejects_cycles():
    from fjsp_lab.logistics.sequences import decode_sequences
    machines = [[(0, 0)], [(1, 0), (1, 1), (0, 1)]]
    trips = [[(0, 0), (1, 0), (0, 1), (1, 2), (0, 2)]]
    decoded, hand = decode_sequences(instance(), machines, trips), valid_schedule()
    assert set(decoded.production.records) == set(hand.production.records)
    assert set(decoded.transports) == set(hand.transports) and decoded.makespan == hand.makespan
    # Job 0 first on M1, but its trip there only after job 1 has left M1: cyclic.
    with pytest.raises(ValueError, match='cyclic'):
        decode_sequences(instance(), [[(0, 0)], [(0, 1), (1, 0), (1, 1)]], [[(0, 0), (1, 0), (1, 2), (0, 1), (0, 2)]])
    with pytest.raises(ValueError, match='every required trip'):
        decode_sequences(instance(), machines, [trips[0][:-1]])
