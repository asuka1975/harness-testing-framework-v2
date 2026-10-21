"""検証役の報告（reports/verification/f2-runtime-and-tests/report.md）の B1〜B4、B6 を再現して固定する。

B1 中断再開を含む run の記録再生、B2 再進入時の子 run 作業ディレクトリの残骸、
B3 フェーズゲート不成立の escalate に ContinueAsGoal が効かない、B4 最上位で human 無しの escalate、
B6 再生で未消費の記録が検出されない。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType

import pytest

from htf.contract import Abort, ContinueAsGoal, ContractViolation, StageContext
from htf.runtime import (
    Bindings,
    DictMetricRegistry,
    Recorder,
    ReplayMismatch,
    Runner,
    RunStatus,
    load_workflow,
    snapshot_digest,
)
from htf.testing.harness import MarkerClassifier, ScriptedHuman

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "examples" / "toy-minimal" / "tests" / "fixtures" / "scenarios"
FIXTURES = ROOT / "tests" / "fixtures" / "workflows"


# --- B1 ---


def test_b1_replay_reproduces_run_with_suspend_resume(toy: ModuleType, tmp_path: Path) -> None:
    scenario = toy.harness.load_scenario(SCENARIOS / "suspend_resume.yaml")
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    log = tmp_path / "rec.jsonl"

    recorder = Recorder(log, mode="record")
    runner = Runner(
        workflow,
        toy.harness.make_bindings(scenario, human=ScriptedHuman([])),
        workspace=tmp_path / "ws1",
        recorder=recorder,
    )
    result = runner.run()
    answers = list(scenario.answers)
    while result.status is RunStatus.SUSPENDED:
        result = runner.resume(answers.pop(0))
    assert result.status is RunStatus.COMPLETED

    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    questions = [e["request"]["question"] for e in entries if e["kind"] == "user"]
    assert questions == ["題目は?", "主張の一覧は?", "根拠の所在は?"], "回答が一度ずつ記録される"

    replayed = Runner(
        workflow,
        toy.harness.make_bindings(scenario, human=ScriptedHuman([]), replay=True),
        workspace=tmp_path / "ws2",
        recorder=Recorder(log, mode="replay"),
    ).run()
    assert replayed.status is RunStatus.COMPLETED, "回答は記録から来るので再生は中断しない"
    assert [snapshot_digest(s) for s in replayed.end_snapshots] == [
        snapshot_digest(s) for s in result.end_snapshots
    ]


# --- B2 ---


class _Seed:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, ctx: StageContext) -> None:
        self.calls += 1
        (ctx.workspace / "seed.json").write_text(json.dumps({"outcome": "goal"}))
        ctx.emit("items", ["a", "b"] if self.calls == 1 else ["a"])


class _Fan:
    def run(self, ctx: StageContext) -> None:
        ctx.emit("back", "again")


class _W:
    def run(self, ctx: StageContext) -> None:
        (ctx.workspace / "w.txt").write_text(str(ctx.memory["item"]))


class _Check:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, ctx: StageContext) -> None:
        self.calls += 1
        outcome = "bad" if self.calls <= 2 else "goal"
        (ctx.workspace / "c.json").write_text(json.dumps({"outcome": outcome}))
        if outcome == "bad":
            ctx.emit("fix", ["直す"])


def test_b2_child_workspace_is_cleared_on_reentry(tmp_path: Path) -> None:
    registry = DictMetricRegistry(
        {
            "seed_exists": lambda s: (s.files / "seed.json").is_file(),
            "run_dirs": lambda s: len([p for p in (s.files / "runs").iterdir() if p.is_dir()]),
        }
    )
    workflow = load_workflow(FIXTURES / "shrink.yaml", metric_names=registry.names())
    bindings = Bindings(
        bodies={
            ("shrink", "seed"): _Seed(),
            ("shrink", "fan"): _Fan(),
            ("shrink_child", "w"): _W(),
            ("shrink_child", "check"): _Check(),
        },
        registry=registry,
        classifier=MarkerClassifier(),
        human=ScriptedHuman([]),
    )
    result = Runner(workflow, bindings, workspace=tmp_path / "ws").run()
    assert result.status is RunStatus.COMPLETED
    fan_ends = [s for s in result.end_snapshots if s.stage_id == "fan"]
    assert len(fan_ends) == 2
    assert sorted(p.name for p in (fan_ends[1].files / "runs").iterdir()) == ["0"], (
        "2 回目の進入では items=[a] なので前回の runs/1 は残らない"
    )
    assert [[o.kind for o in outs] for outs in result.child_outcomes["fan"]] == [
        ["stuck", "goal"],
        ["goal"],
    ]


# --- B3 ---


def test_b3_continue_as_goal_passes_a_failed_gate(tmp_path: Path) -> None:
    from test_runtime_phase_gate import _run  # pytest が tests/ を sys.path に入れる

    result = _run(
        tmp_path,
        gate_values=[False],
        probe=["goal"],
        resolutions=[ContinueAsGoal(note="人間がゲートを通す")],
    )
    assert result.status is RunStatus.COMPLETED
    assert [f"{g.phase_id}:{g.event}" for g in result.gates] == [
        "first:failed",
        "first:passed",
        "second:passed",
    ]
    assert result.gates[1].note == "human"


# --- B4 ---


def test_b4_top_level_runner_without_human_raises_on_escalate(
    toy: ModuleType, tmp_path: Path
) -> None:
    scenario = toy.harness.load_scenario(SCENARIOS / "verify_unknown.yaml")
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    runner = Runner(
        workflow, toy.harness.make_bindings(scenario, human=None), workspace=tmp_path / "ws"
    )
    with pytest.raises(ContractViolation, match="HumanDecider"):
        runner.run()


# --- B6 ---


def test_b6_unconsumed_replay_entries_are_detected(toy: ModuleType, tmp_path: Path) -> None:
    scenario = toy.harness.load_scenario(SCENARIOS / "happy.yaml")
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    log = tmp_path / "rec.jsonl"
    Runner(
        workflow,
        toy.harness.make_bindings(scenario, human=ScriptedHuman([])),
        workspace=tmp_path / "ws1",
        recorder=Recorder(log, mode="record"),
    ).run()
    with log.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps({"kind": "llm", "request": {"messages": []}, "response": {"text": "余り"}})
            + "\n"
        )
    with pytest.raises(ReplayMismatch, match="未消費"):
        Runner(
            workflow,
            toy.harness.make_bindings(scenario, human=ScriptedHuman([Abort()]), replay=True),
            workspace=tmp_path / "ws2",
            recorder=Recorder(log, mode="replay"),
        ).run()
