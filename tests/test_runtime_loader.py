"""loader: 検査器を通った定義だけを型付きモデルにする。子も再帰的に読む。"""

from __future__ import annotations

from pathlib import Path

import pytest

from htf.runtime import WorkflowDefinitionError, load_workflow

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "schema" / "examples"
METRICS = [
    "inputs_complete",
    "draft_exists",
    "verified_ratio",
    "section_exists",
    "section_consistent",
]


def test_loads_positive_with_children() -> None:
    wf = load_workflow(EXAMPLES / "positive" / "with_subworkflow.yaml", metric_names=METRICS)
    assert wf.name == "minimal"
    assert [s.id for s in wf.stages] == ["collect", "draft", "verify", "elaborate"]
    elaborate = wf.stage("elaborate")
    assert elaborate.subworkflow is not None
    assert elaborate.subworkflow.child.name == "leaf"
    assert [s.id for s in elaborate.subworkflow.child.stages] == ["write", "check"]
    assert wf.phase_of("verify") == "verify" and wf.phase_of("collect") == "prepare"
    assert wf.stage("verify").rollback[0].carry == ["failing_checks"]
    assert wf.stage("verify").goal.quantitative["verified_ratio"].min == 0.8


def test_rejects_definition_with_findings() -> None:
    with pytest.raises(WorkflowDefinitionError) as info:
        load_workflow(EXAMPLES / "negative" / "rollback_forward__self.yaml", metric_names=METRICS)
    assert any(f.code == "rollback_forward" for f in info.value.findings)


def test_rejects_unregistered_metric() -> None:
    with pytest.raises(WorkflowDefinitionError) as info:
        load_workflow(EXAMPLES / "positive" / "minimal.yaml", metric_names=["draft_exists"])
    assert {f.code for f in info.value.findings} == {"metric_registered"}
