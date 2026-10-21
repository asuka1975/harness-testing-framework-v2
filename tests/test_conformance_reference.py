"""参照ランタイムが契約適合テスト（htf.contract.conformance）を通す。

ハーネスが自前のランタイムを持つ場合も、同じ ConformanceSuite を継承して make_runtime を差し替えるだけ。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from htf.contract import Classifier, MetricRegistry, StageBody, UserIO
from htf.contract.conformance import ConformanceRuntime, ConformanceSuite
from htf.runtime import Bindings, ReferenceRuntime, load_workflow


class TestReferenceRuntime(ConformanceSuite):
    @pytest.fixture
    def make_runtime(self, tmp_path: Path):
        def factory(
            workflow_path: Path,
            bodies: Mapping[tuple[str, str], StageBody],
            registry: MetricRegistry,
            classifier: Classifier,
            user: UserIO | None,
        ) -> ConformanceRuntime:
            workflow = load_workflow(workflow_path, metric_names=registry.names())
            bindings = Bindings(bodies=bodies, registry=registry, classifier=classifier, user=user)
            return ReferenceRuntime(workflow, bindings, workspace=tmp_path / "ws")

        return factory
