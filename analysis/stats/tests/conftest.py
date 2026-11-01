import pytest

from analysis.stats import dsl
from analysis.stats.simulate import SimConfig, simulate


@pytest.fixture(scope="session")
def corpus():
    return simulate(SimConfig(n_works=3000, passages_per_work=12, seed=11, audit_n=600))


@pytest.fixture(scope="session")
def oracle_wd(corpus):
    return dsl.prepare(corpus.labels, method="oracle", truth=corpus.truth)


@pytest.fixture(scope="session")
def dsl_wd(corpus):
    return dsl.prepare(corpus.labels, corpus.human, corpus.frame, g="calib")
