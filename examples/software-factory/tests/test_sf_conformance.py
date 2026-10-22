"""契約適合テスト（adopting.md 3.8）。参照ランタイムを、ハーネスと同じ組み込み方（harness.conformance_runtime）で通す。"""

from __future__ import annotations

import pytest
from sf_support import H

from htf.contract.conformance import ConformanceSuite


class TestSoftwareFactoryRuntime(ConformanceSuite):
    @pytest.fixture
    def make_runtime(self, tmp_path):  # noqa: ANN001, ANN201
        def factory(workflow_path, bodies, registry, classifier, user):  # noqa: ANN001, ANN202
            return H.conformance_runtime(
                workflow_path, bodies, registry, classifier, user, workspace=tmp_path / "ws"
            )

        return factory
