"""探針 P4b: マルコフ合成の子 run 数。テストは samples / child_counts を渡さない（子 run 数の既定 = 1）。
観測された子 run 数（toy は主張 2 つ → 2）を渡した時と比べ、split が「外れる」理由がどちらにあるかを見る。

実行: uv run python reports/verification/f3-test-runners/probe_markov_children.py
"""

from __future__ import annotations

import tempfile
from collections import Counter
from pathlib import Path

from htf.runtime import load_workflow
from htf.testing.e2e import child_run_counts, compare_outcomes, synthesize_outcomes
from htf.testing.harness import load_example_package
from htf.testing.stages import load_expectations, run_many, tally, transition_matrix

ROOT = Path(__file__).resolve().parents[3]
TOY = ROOT / "examples" / "toy-minimal"
PROFILES = TOY / "tests" / "fixtures" / "profiles"
EXP = TOY / "tests" / "expectations"
toy = load_example_package(TOY, "toy_minimal")
TMP = Path(tempfile.mkdtemp(prefix="htf-probe-mc-"))
workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())


def samples_for(name: str):
    profile = toy.harness.load_profile(PROFILES / f"{name}.yaml")
    exp = load_expectations(EXP / f"{name}.yaml")
    root = TMP / name
    return run_many(
        lambda sd: toy.harness.make_stochastic_runner(profile, seed=sd, workspace=root / str(sd)),
        runs=exp.runs,
        seed=exp.seed,
    )


for name in ("markov", "split"):
    smp = samples_for(name)
    t = tally(smp)
    tm = transition_matrix(smp)
    obs = {k: round(v / t.runs, 3) for k, v in t.outcomes.items()}
    print(f"\n[{name}] observed={obs}  子 run 数の観測: {dict(Counter(child_run_counts(smp).get('elaborate', [])))}")
    for label, kw in (
        ("テストどおり（samples なし → 子 run 数 1）", {}),
        ("観測した子 run 数を渡す（samples=）", {"samples": smp}),
        ("child_counts=[2] を明示", {"child_counts": {"elaborate": [2]}}),
    ):
        devs = []
        preds = []
        for sd in (5, 1, 2, 3, 4):
            pred = synthesize_outcomes(workflow, tm, runs=4000, seed=sd, **kw)
            cmp_ = compare_outcomes(pred, t.outcomes, tolerance=0.1)
            devs.append(max(cmp_.deviations.values()))
            preds.append(round(pred["completed"] / 4000, 3))
        print(
            f"  {label:40s} predicted completed(seed5)={preds[0]} dev(seed5)={devs[0]:.3f} "
            f"ok={devs[0] <= 0.1}  dev 範囲(5 種)={min(devs):.3f}..{max(devs):.3f}"
        )
    # 解析: 主張ごとの「stuck」確率と、プールした行列での予測
    first_inc = tm[("check_section", "first")].get("inconsistent", 0.0)
    re_inc = tm[("check_section", "reentry")].get("inconsistent", 0.0)
    print(
        f"  遷移行列: P(inc|first)={first_inc:.3f} P(inc|reentry, pooled)={re_inc:.3f} "
        f"→ 子 1 つが stuck する確率(pooled)={first_inc * re_inc:.3f}"
    )
