"""software-factory のテストが共有する部品（conftest からも使う。名前の衝突を避けて conftest とは別に置く）。

ハーネスはハイフン名のディレクトリにあるので、load_example_package でパッケージとして読む（adopting.md 3.7）。
"""

from __future__ import annotations

from pathlib import Path

from htf.testing.harness import load_example_package

ROOT = Path(__file__).resolve().parents[1]
SF = load_example_package(ROOT, "software_factory")
H = SF.harness
SCENARIOS = H.scenario_names()


def run_scenario(scenario, workflow, workspace: Path, *, recorder=None, human=None, inject=None):  # noqa: ANN001, ANN201
    """台本を最後まで走らせる。中断したら answers を順に resume で与える。"""
    bindings = H.make_bindings(scenario, workflow, human=human, replay=False)
    runner = H.runner(workflow, bindings, workspace=workspace, recorder=recorder, inject=inject)
    result = runner.run()
    answers = list(scenario.answers)
    while result.status.value == "suspended" and answers:
        result = runner.resume(answers.pop(0))
    return result


EXPECTATIONS = ROOT / "tests" / "expectations"
PLAN_PATH = ROOT / "tests" / "e2e" / "plan.yaml"


def sample_profile(profile: str, expectations: str, workspace: Path):  # noqa: ANN201
    """expectations の N と種で、確率的な構成を run_many する（分布・独立性・マルコフ合成が共有する）。"""
    from htf.testing.stages import load_expectations, run_many

    exp = load_expectations(EXPECTATIONS / f"{expectations}.yaml")
    prof = H.load_profile(profile)
    return run_many(
        lambda seed: H.make_stochastic_runner(prof, seed=seed, workspace=workspace / f"run-{seed}"),
        runs=exp.runs,
        seed=exp.seed,
    )


def marker_truth(document: str, option_ids: list[str]) -> str:
    """偽の世界の正解ラベル: 状態文書の writes 節にある印。low_confidence は goal（分類器が自信を持てなかっただけ）。

    実コーパスでは人間がラベルを付ける。ここでは偽本体が本物の結果から書いた印を、ラベラーの代わりに使う。
    """
    import re

    writes = document.split("## writes", 1)[-1]
    found = re.search(r'"outcome": "([a-z_]+)"', writes)
    label = found.group(1) if found else "unknown"
    if label == "low_confidence":
        label = "goal"
    return label if label in option_ids else "unknown"


def evaluation_records(result):  # noqa: ANN001, ANN201
    """親 run と全ての子 run の評価記録（分類器を呼んだものだけ）。"""
    from htf.testing.stages import evaluation_units

    return [r for unit in evaluation_units(result) for r in unit if r.document]
