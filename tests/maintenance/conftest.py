import pytest

from fjsp_lab.maintenance.generator import build_instance, g3a_cases, periodic_case


@pytest.fixture(scope='session')
def cases():
    return g3a_cases()


@pytest.fixture(scope='session')
def small():
    """n=8, m=2 primary case (CP-SAT proves optimality within a second)."""
    return build_instance(8, 2, 30, 25, 75, 101)


@pytest.fixture(scope='session')
def large():
    """n=24, m=4 single-window case."""
    return build_instance(24, 4, 30, 75, 75, 202)


@pytest.fixture(scope='session')
def periodic():
    """n=50, m=4 with 1, 2, 3, 1 maintenance windows per machine."""
    return periodic_case(50, 4, 'mixed', 20, 50, 75, 7).data


@pytest.fixture(scope='session')
def periodic_big():
    """n=100, m=8, the largest grid size (two windows on every machine)."""
    return periodic_case(100, 8, 'uniform2', 10, 25, 125, 3).data
