"""E2E カバレッジとマルコフ合成（雛形第 8 節）。

- E2E 計画（tests/e2e/plan.yaml）が親子の全 (stage, class) を誘発か注入で踏む（カバレッジ 100%）
- マルコフ合成: markov 構成では遷移行列からの合成と実測の run 全体の結果が許容差内。split 構成では外れる
"""

from __future__ import annotations

import pytest
from sf_support import PLAN_PATH, H

from htf.testing.e2e import (
    child_run_counts,
    compare_outcomes,
    enumerate_targets,
    load_plan,
    run_plan,
    synthesize_outcomes,
)
from htf.testing.stages import tally, transition_matrix

pytestmark = pytest.mark.e2e

TOLERANCE = 0.1  # 仮置き: 実測（N = 200）の標準誤差 0.035 の約 3 倍


def test_plan_names_every_target(workflow):
    planned = {e.target.key for e in load_plan(PLAN_PATH).entries}
    assert planned == {t.key for t in enumerate_targets(workflow)}


def test_plan_reaches_every_target(workflow, tmp_path):
    report = run_plan(load_plan(PLAN_PATH), workflow, H.make_plan_runner, workspace=tmp_path)
    assert report.uncovered == []
    assert report.coverage == 1.0
    # 注入 4: release / unknown と、このフィクスチャでは起きない integrate / merge_failed、verify / coverage_short、
    # verify / lint_dirty（ADR-014 14.6.8。本体の論理は test_sf_v02.py）。unit_test / unknown は台本で誘発する
    assert len(report.injected) == 4
    assert len(report.induced) == len(report.targets) - 4


def test_child_run_counts_vary_with_the_plan(markov_samples):
    counts = child_run_counts(markov_samples)["implement"]
    assert set(counts) == {2, 3}  # plan の two_tasks（2 タスク）と goal（3 タスク）


def test_markov_synthesis_matches_observation(workflow, markov_samples):
    predicted = synthesize_outcomes(
        workflow, transition_matrix(markov_samples), runs=2000, seed=1, samples=markov_samples
    )
    comparison = compare_outcomes(predicted, tally(markov_samples).outcomes, tolerance=TOLERANCE)
    assert comparison.ok, (comparison.predicted, comparison.observed, comparison.deviations)


def test_markov_synthesis_misses_the_split(workflow, split_samples):
    predicted = synthesize_outcomes(
        workflow, transition_matrix(split_samples), runs=2000, seed=1, samples=split_samples
    )
    comparison = compare_outcomes(predicted, tally(split_samples).outcomes, tolerance=TOLERANCE)
    assert not comparison.ok
    assert max(comparison.deviations.values()) > 0.2
