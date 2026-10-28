import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope='session')
def untraced_wall_clock():
    """Measure real controller deadlines without coverage instrumentation overhead.

    Only the two complete bounded-controller integrations use this context.
    Numerical verification, tampering and budget-expiry tests remain traced;
    no clock, production limit, or budget accounting is changed.
    """
    @contextmanager
    def measured():
        module = sys.modules.get('coverage')
        active = module.Coverage.current() if module is not None else None
        if active is not None:
            active.stop()
        try:
            yield
        finally:
            if active is not None:
                active.start()
    return measured
