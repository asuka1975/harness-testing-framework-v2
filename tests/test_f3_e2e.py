"""F3 完了条件: E2E 計画が toy-minimal の全 (stage, end_state) を踏み、マルコフ予測が実測と一致する。

- 計画は examples/toy-minimal/tests/e2e/plan.yaml。誘発（台本）と注入（n 回目の進入の Verdict の差し替え）
- マルコフ合成は分布テストの遷移行列から run 全体の結果を合成し、実測と比べる。
  クラス内で下流を分割した構成（split）では予測が外れる
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from htf.runtime import load_workflow
from htf.testing.e2e import (
    compare_outcomes,
    enumerate_targets,
    load_plan,
    run_plan,
    synthesize_outcomes,
)
from htf.testing.stages import load_expectations, run_many, tally, transition_matrix

ROOT = Path(__file__).resolve().parent.parent
TOY = ROOT / "examples" / "toy-minimal"
PLAN = TOY / "tests" / "e2e" / "plan.yaml"
PROFILES = TOY / "tests" / "fixtures" / "profiles"
EXPECTATIONS = TOY / "tests" / "expectations"

pytestmark = pytest.mark.e2e


def test_targets_enumerate_parent_and_child(toy: ModuleType) -> None:
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    targets = enumerate_targets(workflow)
    keys = {(t.workflow, t.stage_id, t.state) for t in targets}
    assert ("toy-minimal", "verify", "checks_failed") in keys
    assert ("elaborate-claim", "check_section", "inconsistent") in keys
    assert ("toy-minimal", "collect", "goal") in keys and (
        "toy-minimal",
        "collect",
        "unknown",
    ) in keys
    assert len(keys) == 17


def test_plan_covers_all_targets_with_induce_and_inject(toy: ModuleType, tmp_path: Path) -> None:
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    plan = load_plan(PLAN)
    report = run_plan(plan, workflow, toy.harness.make_plan_runner, workspace=tmp_path)
    assert report.uncovered == [], report.uncovered
    assert report.coverage == 1.0
    assert report.induced and report.injected, "誘発と注入の両方を使う"
    injected_verdicts = [e for r in report.results for e in r.evaluations if e.injected]
    assert injected_verdicts and all("注入" in e.verdict.reason for e in injected_verdicts)


def _samples(toy: ModuleType, root: Path, name: str):
    profile = toy.harness.load_profile(PROFILES / f"{name}.yaml")
    expectations = load_expectations(EXPECTATIONS / f"{name}.yaml")
    return run_many(
        lambda seed: toy.harness.make_stochastic_runner(
            profile, seed=seed, workspace=root / str(seed)
        ),
        runs=expectations.runs,
        seed=expectations.seed,
    )


def test_markov_prediction_matches_observation(toy: ModuleType, tmp_path: Path) -> None:
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    samples = _samples(toy, tmp_path, "markov")
    predicted = synthesize_outcomes(
        workflow, transition_matrix(samples), runs=4000, seed=5, samples=samples
    )
    comparison = compare_outcomes(predicted, tally(samples).outcomes, tolerance=0.1)
    assert comparison.ok, comparison


def test_markov_prediction_deviates_for_split_body(toy: ModuleType, tmp_path: Path) -> None:
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    samples = _samples(toy, tmp_path, "split")
    predicted = synthesize_outcomes(
        workflow, transition_matrix(samples), runs=4000, seed=5, samples=samples
    )
    comparison = compare_outcomes(predicted, tally(samples).outcomes, tolerance=0.1)
    assert not comparison.ok, comparison


def test_synthesize_requires_child_counts_for_subworkflows(toy: ModuleType, tmp_path: Path) -> None:
    """子を持つワークフローで子 run 数を渡さないと黙って 1 にしない（検証役の報告 B1）。"""
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    with pytest.raises(ValueError, match="子 run"):
        synthesize_outcomes(workflow, {}, runs=10, seed=1)


def test_inject_keys_are_workflow_qualified_and_validated(toy: ModuleType, tmp_path: Path) -> None:
    """注入の鍵は (workflow, stage, entry)。定義に無い鍵は ValueError（検証役の報告 B3 / B4）。"""
    from htf.contract import Verdict, VerdictKind
    from htf.runtime import Runner
    from htf.testing.harness import ScriptedHuman

    scenario = toy.harness.load_scenario(TOY / "tests" / "fixtures" / "scenarios" / "happy.yaml")
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    bindings = toy.harness.make_bindings(scenario, human=ScriptedHuman([]))
    with pytest.raises(ValueError, match="注入"):
        Runner(
            workflow,
            bindings,
            workspace=tmp_path / "ws",
            inject={("toy-minimal", "no_such_stage", 1): Verdict(VerdictKind.GOAL)},
        )
    with pytest.raises(ValueError, match="注入"):
        Runner(
            workflow,
            bindings,
            workspace=tmp_path / "ws",
            inject={("no_such_workflow", "verify", 1): Verdict(VerdictKind.GOAL)},
        )
    # 子のステージは子の workflow 名で指定する（子が unknown → 親も unknown → 中止）
    from htf.contract import Abort

    runner = Runner(
        workflow,
        toy.harness.make_bindings(scenario, human=ScriptedHuman([Abort()])),
        workspace=tmp_path / "ws2",
        inject={("elaborate-claim", "check_section", 1): Verdict(VerdictKind.UNKNOWN)},
    )
    result = runner.run()
    child_records = [
        e
        for runs in result.child_results["elaborate"]
        for child in runs
        for e in child.evaluations
        if e.stage_id == "check_section"
    ]
    assert child_records and all(e.injected for e in child_records)
