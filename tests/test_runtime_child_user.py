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


def test_child_user_io_is_rejected(tmp_path: Path) -> None:
    registry = DictMetricRegistry({"seed_exists": lambda s: (s.files / "seed.json").is_file()})
    workflow = load_workflow(WORKFLOW, metric_names=registry.names())
    bindings = Bindings(
        bodies={("parent_user", "seed"): Seed(), ("child_user", "ask"): Ask()},
        registry=registry,
        classifier=MarkerClassifier(),
        user=DeferringUserIO(),
        human=ScriptedHuman([]),
    )
    with pytest.raises(ContractViolation, match="未対応"):
        Runner(workflow, bindings, workspace=tmp_path / "ws").run()
