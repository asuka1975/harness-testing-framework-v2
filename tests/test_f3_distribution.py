"""F3 完了条件: 確率的偽ステージ本体に対して、正しい expectations が通り、ずらした expectations が落ちる。

確率的本体は examples/toy-minimal/tests/fixtures/profiles/markov.yaml（種つきの既知の分布。再進入で分布が変わる）。
expectations は examples/toy-minimal/tests/expectations/。N と種は expectations に書く。
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from htf.testing.stages import (
    check_expectations,
    load_expectations,
    run_many,
    tally,
    transition_matrix,
)

ROOT = Path(__file__).resolve().parent.parent
TOY = ROOT / "examples" / "toy-minimal"
PROFILE = TOY / "tests" / "fixtures" / "profiles" / "markov.yaml"
EXPECTATIONS = TOY / "tests" / "expectations"

pytestmark = pytest.mark.distribution


@pytest.fixture(scope="module")
def samples(toy: ModuleType, tmp_path_factory: pytest.TempPathFactory):
    profile = toy.harness.load_profile(PROFILE)
    expectations = load_expectations(EXPECTATIONS / "markov.yaml")
    root = tmp_path_factory.mktemp("dist")
    return run_many(
        lambda seed: toy.harness.make_stochastic_runner(profile, seed=seed, workspace=root / str(seed)),
        runs=expectations.runs,
        seed=expectations.seed,
    )


def test_correct_expectations_pass(samples) -> None:
    report = check_expectations(tally(samples), load_expectations(EXPECTATIONS / "markov.yaml"))
    assert report.ok, report.violations


def test_shifted_expectations_fail(samples) -> None:
    report = check_expectations(tally(samples), load_expectations(EXPECTATIONS / "markov_shifted.yaml"))
    assert not report.ok
    assert any(v.stage_id == "verify" for v in report.violations)


def test_reentry_distribution_differs_from_first_entry(samples) -> None:
    t = tally(samples)
    first = t.by_stage[("verify", "first")]
    reentry = t.by_stage[("verify", "reentry")]
    assert first.total > 50 and reentry.total > 20
    assert reentry.freq("goal") > first.freq("goal") + 0.15


def test_transition_matrix_rows_sum_to_one(samples) -> None:
    matrix = transition_matrix(samples)
    assert ("verify", "first") in matrix and ("check_section", "first") in matrix
    for row in matrix.values():
        assert abs(sum(row.values()) - 1.0) < 1e-9
