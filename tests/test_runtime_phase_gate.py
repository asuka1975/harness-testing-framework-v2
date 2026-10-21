"""決定 #5 のフェーズゲート: 最終ステージが goal でも集約述語が不成立なら unknown。
境界を越えるロールバックは通過済みゲートを無効化し、再通過時に再評価する。

tests/fixtures/workflows/gate.yaml を使う（toy-minimal ではゲート不成立を決定論的に作れないため）。
"""

from __future__ import annotations

import json
from pathlib import Path

from htf.contract import Abort, JsonValue, Snapshot, StageContext, TransitionKind
from htf.runtime import Bindings, DictMetricRegistry, Runner, RunStatus, load_workflow
from htf.testing.harness import MarkerClassifier, ScriptedHuman

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "tests" / "fixtures" / "workflows" / "gate.yaml"


class Seed:
    """a.json を書く。gate_ok の値は台本で決める。"""

    def __init__(self, gate_values: list[bool]) -> None:
        self.gate_values = gate_values
        self.calls = 0

    def run(self, ctx: StageContext) -> None:
        value = self.gate_values[min(self.calls, len(self.gate_values) - 1)]
        self.calls += 1
        (ctx.workspace / "a.json").write_text(json.dumps({"gate_ok": value, "outcome": "goal"}))


class Probe:
    def __init__(self, outcomes: list[str]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def run(self, ctx: StageContext) -> None:
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        (ctx.workspace / "b.json").write_text(json.dumps({"outcome": outcome}))
        if outcome == "back":
            ctx.emit("reason", "やり直し")


def _metric(name: str, key: str):
    def read(snapshot: Snapshot) -> JsonValue:
        return json.loads((snapshot.files / name).read_text())[key]

    return read


def _registry() -> DictMetricRegistry:
    return DictMetricRegistry(
        {
            "a_exists": lambda s: (s.files / "a.json").exists(),
            "gate_ok": _metric("a.json", "gate_ok"),
            "b_exists": lambda s: (s.files / "b.json").exists(),
        }
    )


def _run(workspace: Path, *, gate_values: list[bool], probe: list[str], resolutions: list):
    workflow = load_workflow(WORKFLOW, metric_names=_registry().names())
    bindings = Bindings(
        bodies={("gate", "seed"): Seed(gate_values), ("gate", "probe"): Probe(probe)},
        registry=_registry(),
        classifier=MarkerClassifier(),
        human=ScriptedHuman(resolutions),
    )
    return Runner(workflow, bindings, workspace=workspace).run()


def test_gate_failure_escalates_as_unknown(tmp_path: Path) -> None:
    result = _run(tmp_path, gate_values=[False], probe=["goal"], resolutions=[Abort()])
    assert result.status is RunStatus.ABORTED
    assert [t.kind for t in result.trace] == [TransitionKind.ESCALATE_UNKNOWN]
    assert [f"{g.phase_id}:{g.event}" for g in result.gates] == ["first:failed"]
    assert result.trace[0].verdict is not None and result.trace[0].verdict.kind.value == "unknown"


def test_cross_phase_rollback_invalidates_and_reevaluates_gate(tmp_path: Path) -> None:
    result = _run(tmp_path, gate_values=[True], probe=["back", "goal"], resolutions=[])
    assert result.status is RunStatus.COMPLETED
    assert [t.kind for t in result.trace] == [
        TransitionKind.NEXT,
        TransitionKind.ROLLBACK_ACROSS_PHASE,
        TransitionKind.NEXT,
        TransitionKind.NEXT,
    ]
    assert [f"{g.phase_id}:{g.event}" for g in result.gates] == [
        "first:passed",
        "first:invalidated",
        "first:passed",
        "second:passed",
    ]
