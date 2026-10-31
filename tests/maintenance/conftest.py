import pytest

from fjsp_lab.maintenance.generator import build_instance, g3a_cases


@pytest.fixture(scope='session')
def cases():
    return g3a_cases()


@pytest.fixture(scope='session')
def small():
    """n=8, m=2 primary case (CP-SAT proves optimality within a second)."""
    return build_instance(8, 2, 30, 25, 75, 101)


@pytest.fixture(scope='session')
def large():
    """n=24, m=4: the largest size the construction environment supports."""
    return build_instance(24, 4, 30, 75, 75, 202)
