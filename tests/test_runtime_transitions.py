"""F2 の主完了条件: toy-minimal で 7 種の遷移を全て通す。

台本は examples/toy-minimal/tests/fixtures/scenarios/*.yaml。各台本に期待する遷移列と終了状態が
書いてあり、全台本で観測された遷移種の和集合が TransitionKind の 7 種と一致する。
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from htf.contract import TransitionKind
from htf.runtime import Runner, RunStatus, load_workflow
from htf.testing.harness import ScriptedHuman, observed_kinds

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "examples" / "toy-minimal" / "tests" / "fixtures" / "scenarios"
SCENARIOS = sorted(SCENARIO_DIR.glob("*.yaml"))


def run_scenario(toy: ModuleType, path: Path, workspace: Path):
    scenario = toy.harness.load_scenario(path)
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    bindings = toy.harness.make_bindings(scenario, human=ScriptedHuman(scenario.resolutions))
    runner = Runner(workflow, bindings, workspace=workspace)
    result = runner.run()
    answers = list(scenario.answers)
    while result.status is RunStatus.SUSPENDED and answers:
        result = runner.resume(answers.pop(0))
    return scenario, result


def test_scenarios_exist() -> None:
    assert len(SCENARIOS) >= 7


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_scenario_follows_expected_transitions(toy: ModuleType, tmp_path: Path, path: Path) -> None:
    scenario, result = run_scenario(toy, path, tmp_path / "ws")
    assert result.status.value == scenario.expect["status"]
    assert [t.kind.value for t in result.trace] == scenario.expect["transitions"]
    if "gates" in scenario.expect:
        assert [f"{g.phase_id}:{g.event}" for g in result.gates] == scenario.expect["gates"]


def test_all_seven_transition_kinds_observed(toy: ModuleType, tmp_path: Path) -> None:
    seen: set[TransitionKind] = set()
    for path in SCENARIOS:
        _, result = run_scenario(toy, path, tmp_path / path.stem)
        seen |= observed_kinds(result.trace)
    assert seen == set(TransitionKind), {"未観測": set(TransitionKind) - seen}


def test_rollback_restores_start_snapshot_and_overlays_carry(toy: ModuleType, tmp_path: Path) -> None:
    """verify → draft のロールバック後、draft の再進入時の memory は開始時のもの + carry だけ。"""
    scenario, result = run_scenario(toy, SCENARIO_DIR / "checks_failed_once.yaml", tmp_path / "ws")
    reentry = [s for s in result.start_snapshots if s.stage_id == "draft"]
    assert len(reentry) == 2
    first, second = reentry
    assert "failing_checks" not in first.memory
    assert second.memory["failing_checks"]  # carry で重ねられた
    # carry 以外の鍵は開始時のまま（verify が出した claims は draft には流れない）
    assert set(second.memory) - {"failing_checks"} == set(first.memory)
