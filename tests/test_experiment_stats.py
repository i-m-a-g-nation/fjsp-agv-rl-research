"""Statistics helpers that decide whether pre-registered hypotheses hold (experiments/_common.py)."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experiments'))
from _common import cluster_sign_flip, holm_adjust  # noqa: E402


def test_holm_adjusts_step_down_in_input_order():
    # sorted 0.01, 0.03, 0.04 -> 3*0.01, max(.03, 2*0.03), max(.06, 1*0.04)
    assert holm_adjust([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm_adjust([0.5, 0.6]) == [1.0, 1.0]          # capped at 1


def test_sign_flip_is_exact_and_bounded_by_cluster_count():
    result = cluster_sign_flip({'a': [-1.0], 'b': [-2.0], 'c': [-3.0]})
    assert result['p_cluster'] == 1 / 8 == result['p_cluster_min']    # only the observed signs are as extreme
    assert result['clusters_favouring'] == 3 and result['clusters_against'] == 0
    assert cluster_sign_flip({'a': [1.0], 'b': [2.0], 'c': [3.0]}, 'greater')['p_cluster'] == 1 / 8
    assert cluster_sign_flip({'a': [1.0], 'b': [2.0], 'c': [3.0]})['p_cluster'] == 1.0


def test_each_cluster_counts_once_whatever_its_size():
    # Instance-weighted, four wins against one loss would look convincing; by cluster it is one each way.
    result = cluster_sign_flip({'big': [-1.0, -1.0, -1.0, -1.0], 'small': [1.0]})
    assert result['clusters'] == 2 and result['p_cluster'] == 0.75


def test_sign_flip_without_differences_supports_nothing():
    assert cluster_sign_flip({'a': [0.0], 'b': [0.0, 0.0]})['p_cluster'] == 1.0
    with pytest.raises(ValueError):
        cluster_sign_flip({'a': []})
    with pytest.raises(ValueError):
        cluster_sign_flip({'a': [1.0]}, 'two-sided')
