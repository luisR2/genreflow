"""Shared pytest configuration for the backend test suite."""

import os

# Every TestClient fixture runs the app's full lifespan, which includes the
# startup warm-up. That warm-up exists solely to pre-compile librosa's numba
# kernels ahead of real traffic; tests gain nothing from it and would pay for it
# on the first fixture. test_warmup.py turns it back on explicitly where it is
# the thing under test.
os.environ.setdefault("GENREFLOW_WARMUP", "0")
