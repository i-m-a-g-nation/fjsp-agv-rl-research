import pytest

from src.graduation.dispatch_rules import solve_dispatch_rule
from src.graduation.reference_main_protocol import build_main_cases
from src.graduation.reference_main_results import _data
from src.graduation.teacher_data import (
    TeacherReplayError, instance_to_record, plan_to_actions, record_to_instance,
)


def _data_for(n, m):
    return _data(next(c for c in build_main_cases()
                      if c['factors']['num_tasks'] == n and c['factors']['num_machines'] == m))


@pytest.mark.parametrize('mode', ['fixed', 'joint'])
def test_teacher_plan_replays_and_records_round_trip(mode):
    data = _data_for(24, 4)
    plan = solve_dispatch_rule(data, mode=mode, rule='MDD')
    actions = plan_to_actions(plan, data, mode)
    assert len(actions) == 24 + 4
    assert record_to_instance(instance_to_record(data)) == data


def test_tampered_teacher_plan_is_rejected():
    data = _data_for(8, 2)
    plan = solve_dispatch_rule(data, mode='joint', rule='EDD')
    plan.total_tardiness += 1
    with pytest.raises(TeacherReplayError):
        plan_to_actions(plan, data, 'joint')


def test_attention_policy_rollout_and_losses():
    torch = pytest.importorskip('torch')
    from src.graduation.attention_policy import (
        AttentionPolicy, PolicyConfig, imitation_loss, load, reinforce_loss, rollout, save,
    )
    torch.manual_seed(0)
    model = AttentionPolicy(PolicyConfig(width=32, layers=1, heads=4, feedforward=64))
    problems = [(_data_for(8, 2), 'fixed'), (_data_for(24, 4), 'joint')]
    greedy, _ = rollout(model, problems, samples=2, greedy=True)
    assert greedy[0][0] == greedy[0][1] and all(v >= 0 for g in greedy for v in g)
    teachers = [plan_to_actions(solve_dispatch_rule(d, mode=m, rule='MDD'), d, m) for d, m in problems]
    loss = imitation_loss(model, problems, teachers)
    loss.backward()
    assert loss.item() > 0
    rl, mean = reinforce_loss(model, problems, samples=4, generator=torch.Generator().manual_seed(1),
                              scale=[1.0, 1.0])
    rl.backward()
    assert mean >= 0


def test_checkpoint_round_trip_and_hash_check(tmp_path):
    torch = pytest.importorskip('torch')
    from src.graduation.attention_policy import AttentionPolicy, PolicyConfig, load, rollout, save
    model = AttentionPolicy(PolicyConfig(width=32, layers=1, heads=4, feedforward=64)).eval()
    digest = save(model, tmp_path / 'm.pt')
    again = load(tmp_path / 'm.pt', expected_sha256=digest)
    problems = [(_data_for(24, 2), 'joint')]
    assert rollout(model, problems, samples=1, greedy=True)[0] == rollout(again, problems, samples=1, greedy=True)[0]
    with pytest.raises(ValueError):
        load(tmp_path / 'm.pt', expected_sha256='0' * 64)
