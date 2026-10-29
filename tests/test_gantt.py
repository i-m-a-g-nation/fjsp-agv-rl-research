"""Drawing preserves the checked schedule and releases its own figure resources."""
import matplotlib.pyplot as plt
from PIL import Image
import pytest

from src.data.instance import FJSPInstance
from src.scheduling.encoding import ScheduleResult
from src.scheduling.feasibility import check_feasibility
from src.vis.gantt import plot_gantt


def checked_schedule():
    instance=FJSPInstance.from_jobs_array([
        [[(0,3)],[(1,2)]], [[(1,2)]],
    ],num_machines=2)
    result=ScheduleResult(instance=instance)
    result.add_record(0,0,0,0,3)
    result.add_record(0,1,1,3,2)
    result.add_record(1,0,1,0,2)
    result.compute_makespan()
    assert check_feasibility(result,expected_instance=instance)[0]
    return result


def test_saved_gantt_is_readable_png_and_leaves_no_figure(tmp_path):
    result=checked_schedule();before=set(plt.get_fignums())
    target=tmp_path/'schedule.png'
    plot_gantt(result,save_path=target)
    with Image.open(target) as picture:
        assert picture.format=='PNG' and picture.width>100 and picture.height>100
        picture.verify()
    assert set(plt.get_fignums())==before
    assert result.makespan==5 and check_feasibility(result,expected_instance=result.instance)[0]


def test_shown_gantt_preserves_machine_rows_and_operation_intervals(monkeypatch):
    result=checked_schedule();seen=[];before=set(plt.get_fignums())
    def inspect_display():
        ax=plt.gcf().axes[0]
        seen.append({'machines':[t.get_text() for t in ax.get_yticklabels()],
                     'intervals':sorted((p.get_x(),p.get_width(),p.get_y()+p.get_height()/2) for p in ax.patches),
                     'labels':sorted(t.get_text() for t in ax.texts)})
    monkeypatch.setattr(plt,'show',inspect_display)
    try:
        plot_gantt(result)
        assert seen==[{'machines':['M0','M1'],'intervals':[(0,2,1),(0,3,0),(3,2,1)],
                       'labels':['J0O0','J0O1','J1O0']}]
        assert set(plt.get_fignums())==before
    finally:
        for n in set(plt.get_fignums())-before:plt.close(n)


def test_failed_save_does_not_leak_a_figure(tmp_path):
    before=set(plt.get_fignums())
    try:
        with pytest.raises(FileNotFoundError):
            plot_gantt(checked_schedule(),save_path=tmp_path/'missing'/'schedule.png')
        assert set(plt.get_fignums())==before
    finally:
        for n in set(plt.get_fignums())-before:plt.close(n)
