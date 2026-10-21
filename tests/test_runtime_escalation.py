"""F2 の完了条件: escalate の 4 つの選択肢（決定 #3）が動く。

verify を unknown にして escalate させ、台本化した HumanDecider で各 Resolution を返す。
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

from htf.contract import Abort, ContinueAsGoal, Rerun, RollbackTo, TransitionKind
from htf.runtime import Runner, RunStatus, load_workflow
from htf.testing.harness import ScriptedHuman

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "examples" / "toy-minimal" / "tests" / "fixtures" / "scenarios"


def _run(toy: ModuleType, workspace: Path, *, verify: list[str], resolutions: list):
    scenario = toy.harness.load_scenario(SCENARIO_DIR / "verify_unknown.yaml")
    scenario = scenario.with_outcomes(verify=verify)
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    runner = Runner(
        workflow, toy.harness.make_bindings(scenario, human=ScriptedHuman(resolutions)), workspace=workspace
    )
    return runner.run()


def test_rerun_reexecutes_same_stage_from_start_snapshot(toy: ModuleType, tmp_path: Path) -> None:
    result = _run(toy, tmp_path, verify=["unknown", "goal"], resolutions=[Rerun(note="もう一度")])
    kinds = [t.kind for t in result.trace]
    assert kinds[:3] == [TransitionKind.NEXT, TransitionKind.NEXT, TransitionKind.ESCALATE_UNKNOWN]
    assert result.status is RunStatus.COMPLETED
    starts = [s for s in result.start_snapshots if s.stage_id == "verify"]
    assert len(starts) == 2 and starts[0].memory == starts[1].memory
    assert result.resolutions == [Rerun(note="もう一度")]


def test_rollback_to_restores_target_without_consuming_max(toy: ModuleType, tmp_path: Path) -> None:
    result = _run(
        toy,
        tmp_path,
        verify=["unknown", "goal"],
        resolutions=[RollbackTo(stage="draft", carry={"failing_checks": ["人間が指定"]}, note="設計からやり直す")],
    )
    assert result.status is RunStatus.COMPLETED
    kinds = [t.kind for t in result.trace]
    assert TransitionKind.ROLLBACK_ACROSS_PHASE in kinds
    human_rollback = next(t for t in result.trace if t.kind is TransitionKind.ROLLBACK_ACROSS_PHASE)
    assert human_rollback.note == "human"
    assert result.edge_counts == {}  # 人間の操作は辺の max を消費しない
    draft_starts = [s for s in result.start_snapshots if s.stage_id == "draft"]
    assert draft_starts[-1].memory["failing_checks"] == ["人間が指定"]


def test_rollback_to_rejects_undeclared_carry(toy: ModuleType, tmp_path: Path) -> None:
    import pytest

    from htf.contract import ContractViolation

    with pytest.raises(ContractViolation):
        _run(
            toy,
            tmp_path,
            verify=["unknown"],
            resolutions=[RollbackTo(stage="draft", carry={"not_declared": 1})],
        )


def test_continue_as_goal_proceeds_with_human_verdict(toy: ModuleType, tmp_path: Path) -> None:
    result = _run(toy, tmp_path, verify=["unknown"], resolutions=[ContinueAsGoal(note="分類器の誤り")])
    assert result.status is RunStatus.COMPLETED
    esc = next(t for t in result.trace if t.kind is TransitionKind.ESCALATE_UNKNOWN)
    following = result.trace[result.trace.index(esc) + 1]
    assert following.kind is TransitionKind.NEXT
    assert following.verdict is not None and following.verdict.decided_by == "human"


def test_abort_stops_the_run(toy: ModuleType, tmp_path: Path) -> None:
    result = _run(toy, tmp_path, verify=["unknown"], resolutions=[Abort(note="中止")])
    assert result.status is RunStatus.ABORTED
    assert result.trace[-1].kind is TransitionKind.ESCALATE_UNKNOWN
