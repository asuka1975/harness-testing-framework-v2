"""子ワークフローのステージのユーザー入出力は v1.0 では未対応（ADR-012 12.8）。

子の本体が WaitingForUser を投げたら、親の中断にはせず ContractViolation にする。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from htf.contract import ContractViolation, StageContext
from htf.runtime import Bindings, DictMetricRegistry, Runner, load_workflow
from htf.testing.harness import DeferringUserIO, MarkerClassifier, ScriptedHuman

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "tests" / "fixtures" / "workflows" / "child_user.yaml"


class Seed:
    def run(self, ctx: StageContext) -> None:
        (ctx.workspace / "seed.json").write_text(json.dumps({"outcome": "goal"}))
        ctx.emit("items", ["a"])


class Ask:
    def run(self, ctx: StageContext) -> None:
        answer = ctx.user.ask("答えは?")
        (ctx.workspace / "answer.txt").write_text(str(answer))


def test_child_user_input_is_rejected_statically() -> None:
    """ADR-012 12.16: 子のステージの user_input は整合性検査で落とす（実行時より早く分かる）。"""
    from htf.runtime import WorkflowDefinitionError

    registry = DictMetricRegistry({"seed_exists": lambda s: (s.files / "seed.json").is_file()})
    with pytest.raises(WorkflowDefinitionError) as info:
        load_workflow(WORKFLOW, metric_names=registry.names())
    assert any(f.code == "subworkflow_user_input" for f in info.value.findings)


def test_child_user_io_is_rejected_at_runtime(tmp_path: Path) -> None:
    """検査を迂回して組み立てた定義でも、実行時に ContractViolation になる（防御の二重化）。"""
    from htf.runtime.model import build_workflow
    from htf.testing.spec import load_yaml

    def build(path: Path):
        doc = load_yaml(path)
        assert isinstance(doc, dict)
        return build_workflow(doc, path.resolve(), child_loader=build)

    workflow = build(WORKFLOW)
    registry = DictMetricRegistry({"seed_exists": lambda s: (s.files / "seed.json").is_file()})
    bindings = Bindings(
        bodies={("parent_user", "seed"): Seed(), ("child_user", "ask"): Ask()},
        registry=registry,
        classifier=MarkerClassifier(),
        user=DeferringUserIO(),
        human=ScriptedHuman([]),
    )
    with pytest.raises(ContractViolation, match="未対応"):
        Runner(workflow, bindings, workspace=tmp_path / "ws").run()
