import numpy as np
import pytest


@pytest.fixture
def rng_vec():
    v = np.random.default_rng(1).normal(size=384)
    return v / np.linalg.norm(v)
