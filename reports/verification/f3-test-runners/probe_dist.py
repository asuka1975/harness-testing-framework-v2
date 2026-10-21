"""探針 P1 / P2 / P4 / P6: 分布の余裕、独立性の p 値の安定性、マルコフ合成の余裕、確率的本体と成果物の整合。

実行: uv run python reports/verification/f3-test-runners/probe_dist.py  (約 2 分)
"""

from __future__ import annotations

import json
import re
import tempfile
from collections import Counter
from pathlib import Path

from htf.runtime import load_workflow
from htf.testing.e2e import compare_outcomes, synthesize_outcomes
from htf.testing.harness import load_example_package
from htf.testing.stages import (
    check_expectations,
    evaluation_units,
    independence,
    load_expectations,
    run_many,
    tally,
    transition_matrix,
)

ROOT = Path(__file__).resolve().parents[3]
TOY = ROOT / "examples" / "toy-minimal"
PROFILES = TOY / "tests" / "fixtures" / "profiles"
EXP = TOY / "tests" / "expectations"
toy = load_example_package(TOY, "toy_minimal")
TMP = Path(tempfile.mkdtemp(prefix="htf-probe-"))


def samples_for(name: str, *, runs: int | None = None, seed: int | None = None):
    profile = toy.harness.load_profile(PROFILES / f"{name}.yaml")
    exp = load_expectations(EXP / f"{name}.yaml")
    r, s = runs or exp.runs, exp.seed if seed is None else seed
    root = TMP / f"{name}-{r}-{s}"
    return run_many(
        lambda sd: toy.harness.make_stochastic_runner(profile, seed=sd, workspace=root / str(sd)),
        runs=r,
        seed=s,
    )


def margins(t, exp, label: str) -> None:
    print(f"\n[P1] {label}: 観測頻度と区間の余裕（N はそのセルの評価数）")
    for stage, kinds in exp.stages.items():
        for kind, classes in kinds.items():
            cc = t.by_stage.get((stage, kind))
            n = cc.total if cc else 0
            for cls, iv in classes.items():
                obs = cc.freq(cls) if cc else 0.0
                lo = f"{obs - iv.min:+.3f}" if iv.min is not None else "   -  "
                hi = f"{iv.max - obs:+.3f}" if iv.max is not None else "   -  "
                ok = iv.contains(obs)
                print(
                    f"  {stage:14s} {kind:7s} {cls:14s} obs={obs:.3f} N={n:4d} "
                    f"[{iv.min},{iv.max}] 余裕 min:{lo} max:{hi} {'ok' if ok else 'NG'}"
                )
    for outcome, iv in exp.outcomes.items():
        obs = t.outcomes[outcome] / t.runs
        print(f"  outcome {outcome:10s} obs={obs:.3f} N={t.runs} [{iv.min},{iv.max}] {iv.contains(obs)}")


def main() -> None:
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    markov = samples_for("markov")
    split = samples_for("split")
    t_markov, t_split = tally(markov), tally(split)
    exp_markov = load_expectations(EXP / "markov.yaml")
    exp_shift = load_expectations(EXP / "markov_shifted.yaml")

    # ---- P1 区間の余裕 ----
    margins(t_markov, exp_markov, "markov.yaml（seed 100, 300 run）")
    print("  全セル:", {k: dict(v.counts) for k, v in sorted(t_markov.by_stage.items())})
    print("  outcomes:", dict(t_markov.outcomes))
    rep = check_expectations(t_markov, exp_shift)
    print("\n[P1] markov_shifted.yaml の違反:", [str(v) for v in rep.violations])
    obs_goal = t_markov.by_stage[("verify", "first")].freq("goal")
    print(f"  verify.first.goal 観測 {obs_goal:.3f}（名目 0.55）。shifted の要求 min 0.8 との差 {0.8 - obs_goal:.3f}")
    # 区間の下限を上げていき、どこで落ちるか
    for m in (0.55, 0.58, 0.60, 0.62, 0.65):
        print(f"  verify.first.goal min={m}: {'通る' if obs_goal >= m else '落ちる'}")

    # 別の種での揺れ（同じ N=300 で 3 種）
    print("\n[P1] 別の種（N=300）で markov.yaml / shifted が通るか、主要セルの観測値")
    alt = {}
    for s in (1, 2000, 31337):
        smp = samples_for("markov", seed=s)
        alt[s] = smp
        tt = tally(smp)
        ok_m = check_expectations(tt, exp_markov).ok
        ok_s = check_expectations(tt, exp_shift).ok
        vf = tt.by_stage[("verify", "first")]
        vr = tt.by_stage[("verify", "reentry")]
        cs = tt.by_stage[("check_section", "first")]
        print(
            f"  seed={s:5d} markov:{'通' if ok_m else '落'} shifted:{'通' if ok_s else '落'} "
            f"verify.first goal={vf.freq('goal'):.3f} cf={vf.freq('checks_failed'):.3f} (N={vf.total}) "
            f"verify.reentry goal={vr.freq('goal'):.3f} cf={vr.freq('checks_failed'):.3f} (N={vr.total}) "
            f"check_section.first inc={cs.freq('inconsistent'):.3f} (N={cs.total}) "
            f"completed={tt.outcomes['completed'] / tt.runs:.3f}"
        )

    # ---- P2 独立性の p 値 ----
    print("\n[P2] 独立性検証: 並べ替えの種 / 回数で p 値がどれだけ動くか")
    for name, smp in (("split", split), ("markov", markov)):
        for perms in (100, 300, 1000):
            ps = []
            for sd in range(1, 11):
                r = independence(smp, stage_id="check_section", cls="inconsistent", permutations=perms, seed=sd)
                ps.append(r.p_value)
            print(
                f"  {name:6s} perms={perms:4d} G={r.statistic:.2f} groups={ {k: dict(v) for k, v in r.groups.items()} } "
                f"p: min={min(ps):.4f} max={max(ps):.4f} (種 1..10)"
            )
    print("  markov の別の run 種（N=300）での p（perms=300, seed=1）: 偽陽性の起きやすさ")
    for s, smp in alt.items():
        r = independence(smp, stage_id="check_section", cls="inconsistent", permutations=300, seed=1)
        print(f"    run seed={s}: p={r.p_value:.4f} flagged={r.flagged} groups={ {k: dict(v) for k, v in r.groups.items()} }")
    print("  split の別の run 種（N=300）での p（perms=300, seed=1）")
    for s in (1, 2000):
        smp = samples_for("split", seed=s)
        r = independence(smp, stage_id="check_section", cls="inconsistent", permutations=300, seed=1)
        print(f"    run seed={s}: p={r.p_value:.4f} flagged={r.flagged} groups={ {k: dict(v) for k, v in r.groups.items()} }")
    # 下流の定義を next に変えると検出できるか
    r = independence(split, stage_id="check_section", cls="inconsistent", permutations=300, seed=1, downstream="next")
    print(f"  split downstream='next': p={r.p_value:.4f} groups={ {k: dict(v) for k, v in r.groups.items()} }")
    # 他のクラス（verify checks_failed）は carry が主張名を含まないので一群になるはず
    r = independence(markov, stage_id="verify", cls="checks_failed", permutations=100, seed=1)
    print(f"  markov verify/checks_failed: groups={len(r.groups)} p={r.p_value:.4f}（群が 1 つなら検証できない: 13.5）")

    # ---- P4 マルコフ合成の余裕 ----
    print("\n[P4] マルコフ合成: 予測と実測の差（許容差 0.1）。合成の種 1..10")
    for name, smp, tt in (("markov", markov, t_markov), ("split", split, t_split)):
        devs = []
        for sd in range(1, 11):
            pred = synthesize_outcomes(workflow, transition_matrix(smp), runs=4000, seed=sd, samples=smp)
            cmp_ = compare_outcomes(pred, tt.outcomes, tolerance=0.1)
            devs.append(max(cmp_.deviations.values()))
        print(
            f"  {name:6s} observed={ {k: round(v / tt.runs, 3) for k, v in tt.outcomes.items()} } "
            f"max deviation: min={min(devs):.3f} max={max(devs):.3f}  (test の seed=5: {devs[4]:.3f})"
        )
        pred5 = synthesize_outcomes(workflow, transition_matrix(smp), runs=4000, seed=5, samples=smp)
        print(f"         predicted(seed 5)={ {k: round(v / 4000, 3) for k, v in pred5.items()} }")
    print("  markov の別の run 種での差（seed=5 合成）")
    for s, smp in alt.items():
        tt = tally(smp)
        pred = synthesize_outcomes(workflow, transition_matrix(smp), runs=4000, seed=5, samples=smp)
        cmp_ = compare_outcomes(pred, tt.outcomes, tolerance=0.1)
        print(f"    run seed={s}: max dev={max(cmp_.deviations.values()):.3f} ok={cmp_.ok}")
    # 子 run 数の分布と、split の遷移行列（reentry 行）
    tm = transition_matrix(split)
    print("  split 遷移行列 check_section reentry:", {k: round(v, 3) for k, v in tm[("check_section", "reentry")].items()})
    tm = transition_matrix(markov)
    print("  markov 遷移行列 check_section reentry:", {k: round(v, 3) for k, v in tm[("check_section", "reentry")].items()})

    # ---- P6 確率的本体と成果物の整合 ----
    print("\n[P6] verify の評価記録: cls × decided_by × report.json の verified_ratio（状態文書から抽出）")
    tab: Counter[tuple[str, str, str]] = Counter()
    ratio_re = re.compile(r'"verified_ratio":\s*([0-9.]+)')
    for smp in markov:
        for unit in evaluation_units(smp.result):
            for rec in unit:
                if rec.stage_id != "verify":
                    continue
                m = ratio_re.search(rec.document or "")
                ratio = m.group(1) if m else "?"
                tab[(rec.cls, str(rec.verdict.decided_by), ratio)] += 1
    for k, v in sorted(tab.items()):
        print(f"  cls={k[0]:14s} decided_by={k[1]:22s} verified_ratio={k[2]:4s} n={v}")
    print("  draft の評価記録: cls × decided_by")
    tab2: Counter[tuple[str, str, str]] = Counter()
    for smp in markov:
        for unit in evaluation_units(smp.result):
            for rec in unit:
                if rec.stage_id in ("draft", "collect", "elaborate", "check_section", "write_section"):
                    tab2[(rec.stage_id, rec.cls, str(rec.verdict.decided_by))] += 1
    for k, v in sorted(tab2.items()):
        print(f"  {k[0]:14s} cls={k[1]:22s} decided_by={k[2]:22s} n={v}")
    # 中断 / 例外の有無
    print("  run の status:", dict(t_markov.outcomes), "| split:", dict(t_split.outcomes))
    # split 本体の実装どおり奇数番目の主張（主張B）の再進入が必ず inconsistent か
    stuck = Counter()
    for smp in split:
        for unit in evaluation_units(smp.result):
            for rec in unit:
                if rec.stage_id == "check_section" and rec.entry_kind == "reentry":
                    claim = rec.carry_in.get("claim") if rec.carry_in else None
                    stuck[(json.dumps(claim, ensure_ascii=False), rec.cls)] += 1
    print("  split: check_section 再進入の (carry_in claim, cls):", dict(stuck))


if __name__ == "__main__":
    main()
