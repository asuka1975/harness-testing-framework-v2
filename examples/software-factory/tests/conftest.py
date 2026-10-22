"""software-factory のテストの共通フィクスチャ。

走らせ方: uv run pytest examples/software-factory/tests
  常時の段だけ: uv run pytest examples/software-factory/tests -m "not distribution and not e2e"
"""

from __future__ import annotations

import pytest
from sf_support import SF, H


@pytest.fixture(scope="session")
def sf():  # noqa: ANN201
    return SF


@pytest.fixture(scope="session")
def workflow():  # noqa: ANN201
    return H.load()


@pytest.fixture(scope="session")
def markov_samples(tmp_path_factory):  # noqa: ANN001, ANN201
    from sf_support import sample_profile

    return sample_profile("markov", "markov", tmp_path_factory.mktemp("markov"))


@pytest.fixture(scope="session")
def split_samples(tmp_path_factory):  # noqa: ANN001, ANN201
    from sf_support import sample_profile

    return sample_profile("split", "split", tmp_path_factory.mktemp("split"))
