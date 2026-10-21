"""F2 の完了条件: 記録再生で同一スナップショットが得られる。

record モードで一周（LLM・分類器・ユーザー回答を JSONL に記録）し、replay モードで
内側の実装を外して一周する。end スナップショットのハッシュ列（files の内容 + memory）が一致する。
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from htf.runtime import Recorder, ReplayMismatch, Runner, RunStatus, load_workflow, snapshot_digest
from htf.testing.harness import ScriptedHuman

ROOT = Path(__file__).resolve().parent.parent
SCENARIO = ROOT / "examples" / "toy-minimal" / "tests" / "fixtures" / "scenarios" / "happy.yaml"


def _run(toy: ModuleType, workspace: Path, recorder: Recorder, *, replay: bool):
    scenario = toy.harness.load_scenario(SCENARIO)
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    bindings = toy.harness.make_bindings(scenario, human=ScriptedHuman([]), replay=replay)
    runner = Runner(workflow, bindings, workspace=workspace, recorder=recorder)
    return runner.run()


def test_replay_reproduces_end_snapshots(toy: ModuleType, tmp_path: Path) -> None:
    log = tmp_path / "record.jsonl"
    recorded = _run(toy, tmp_path / "ws1", Recorder(log, mode="record"), replay=False)
    assert recorded.status is RunStatus.COMPLETED
    assert log.exists() and log.stat().st_size > 0

    replayed = _run(toy, tmp_path / "ws2", Recorder(log, mode="replay"), replay=True)
    assert replayed.status is RunStatus.COMPLETED
    assert [snapshot_digest(s) for s in replayed.end_snapshots] == [
        snapshot_digest(s) for s in recorded.end_snapshots
    ]
    assert [t.kind for t in replayed.trace] == [t.kind for t in recorded.trace]


def test_replay_detects_mismatch(toy: ModuleType, tmp_path: Path) -> None:
    log = tmp_path / "record.jsonl"
    _run(toy, tmp_path / "ws1", Recorder(log, mode="record"), replay=False)
    # 記録と違う台本（別の主張）で再生すると、呼び出しの照合が外れる
    scenario = toy.harness.load_scenario(SCENARIO).with_claims(["別の主張"])
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    bindings = toy.harness.make_bindings(scenario, human=ScriptedHuman([]), replay=True)
    runner = Runner(workflow, bindings, workspace=tmp_path / "ws3", recorder=Recorder(log, mode="replay"))
    with pytest.raises(ReplayMismatch):
        runner.run()
