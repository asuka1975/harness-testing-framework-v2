"""F3 完了条件: クラス内で意図的に下流分布を変えた偽ステージ本体を独立性検証が検出し、変えていないものは検出しない。

代表の鍵は既定（carry の中身のハッシュ）。check_section の inconsistent クラスを、代表（主張）ごとに
再進入後の振る舞いが分かれる構成（profiles/split.yaml）と分かれない構成（profiles/markov.yaml）で比べる。
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from htf.testing.stages import independence, load_expectations, run_many

ROOT = Path(__file__).resolve().parent.parent
TOY = ROOT / "examples" / "toy-minimal"
PROFILES = TOY / "tests" / "fixtures" / "profiles"
EXPECTATIONS = TOY / "tests" / "expectations"

pytestmark = pytest.mark.distribution


def _samples(toy: ModuleType, root: Path, profile_name: str):
    profile = toy.harness.load_profile(PROFILES / f"{profile_name}.yaml")
    expectations = load_expectations(EXPECTATIONS / f"{profile_name}.yaml")
    return run_many(
        lambda seed: toy.harness.make_stochastic_runner(profile, seed=seed, workspace=root / str(seed)),
        runs=expectations.runs,
        seed=expectations.seed,
    )


def test_split_class_is_detected(toy: ModuleType, tmp_path: Path) -> None:
    samples = _samples(toy, tmp_path, "split")
    report = independence(samples, stage_id="check_section", cls="inconsistent", permutations=300, seed=1)
    assert len(report.groups) >= 2
    assert report.p_value < 0.01, report


def test_unsplit_class_is_not_flagged(toy: ModuleType, tmp_path: Path) -> None:
    samples = _samples(toy, tmp_path, "markov")
    report = independence(samples, stage_id="check_section", cls="inconsistent", permutations=300, seed=1)
    assert len(report.groups) >= 2
    assert report.p_value >= 0.05, report
