"""探針 P3: 注入（Runner(inject=...)）が評価記録・トレース・carry にどう残るか。E2E 計画の到達表も出す。

実行: uv run python reports/verification/f3-test-runners/probe_inject.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from htf.contract import Verdict, VerdictKind
from htf.runtime import Runner, load_workflow
from htf.testing.e2e import enumerate_targets, load_plan, run_plan
from htf.testing.harness import ScriptedHuman, load_example_package
from htf.testing.stages import evaluation_units
from htf.testing.triage import TriageQueue

ROOT = Path(__file__).resolve().parents[3]
TOY = ROOT / "examples" / "toy-minimal"
toy = load_example_package(TOY, "toy_minimal")
TMP = Path(tempfile.mkdtemp(prefix="htf-probe-inject-"))
workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())


def show(result, title: str) -> None:
    print(f"\n--- {title}: status={result.status.value}")
    print("  trace:", [(t.kind.value, t.stage_id, t.to_stage) for t in result.trace])
    for unit_i, unit in enumerate(evaluation_units(result)):
        for rec in unit:
            print(
                f"  [{unit_i}] {rec.workflow}/{rec.stage_id}#{rec.entry} cls={rec.cls:14s} "
                f"injected={rec.injected} decided_by={rec.verdict.decided_by} carry_out={rec.carry_out} "
                f"reason={rec.verdict.reason[:60]!r}"
            )


def run(name: str, inject, human=("abort",), outcomes=None, scenario: str = "happy"):
    runner = toy.harness.make_plan_runner(scenario, outcomes or {}, list(human), inject, TMP / name)
    return runner.run()


# (a) happy に verify#1 = checks_failed を注入。本体は failing_checks を emit していない → carry はどうなるか
res_a = run(
    "a-checks_failed",
    {("verify", 1): Verdict(VerdictKind.END_STATE, state="checks_failed", decided_by="classifier")},
    human=("abort",),
)
show(res_a, "(a) verify#1 に checks_failed を注入（happy）")

# (b) happy に draft#1 = unknown を注入 → escalate → abort。トリアージに乗るか
res_b = run("b-unknown", {("draft", 1): Verdict(VerdictKind.UNKNOWN, decided_by="threshold")})
show(res_b, "(b) draft#1 に unknown を注入（happy, human=abort）")
q = TriageQueue(TMP / "triage.jsonl")
added = q.enqueue(res_b, workflow=workflow.name, run_id="probe-b")
print("  triage に積まれた件数:", len(added), [(i.stage, i.reason, i.verdict) for i in added])

# (c) 子ステージ check_section#1 に unknown を注入 → 全ての子 run に効くか
res_c = run(
    "c-child-unknown",
    {("check_section", 1): Verdict(VerdictKind.UNKNOWN, decided_by="threshold")},
    human=("continue_as_goal",),
)
show(res_c, "(c) check_section#1 に unknown を注入（happy, human=continue_as_goal）")

# (d) 注入の鍵が存在しないステージ / 進入回数の時に黙って無視されるか
res_d = run("d-noop", {("nonexistent", 1): Verdict(VerdictKind.UNKNOWN), ("verify", 5): Verdict(VerdictKind.UNKNOWN)})
print(f"\n--- (d) 存在しない鍵の注入: status={res_d.status.value} injected={[e.injected for e in res_d.evaluations]}")

# (e) 子を持つステージ elaborate に sections_inconsistent を注入 → rollback が起きるか
res_e = run(
    "e-elaborate",
    {("elaborate", 1): Verdict(VerdictKind.END_STATE, state="sections_inconsistent", decided_by="classifier")},
)
show(res_e, "(e) elaborate#1 に sections_inconsistent を注入")

# (f) E2E 計画の到達表（誘発 / 注入の内訳）
plan = load_plan(TOY / "tests" / "e2e" / "plan.yaml")
report = run_plan(plan, workflow, toy.harness.make_plan_runner, workspace=TMP / "plan")
print("\n--- (f) E2E 計画")
print("  対象数:", len(enumerate_targets(workflow)), "到達:", len(report.hits), "未到達:", report.uncovered)
print("  誘発:", len(report.induced), "注入:", len(report.injected), report.injected)
print("  計画項目数:", len(plan.entries), "run の status:", [r.status.value for r in report.results])
# 計画の各項目が「自分の対象」を自分の run で踏んでいるか（他の run が偶然踏んだ分で満たされていないか）
for i, (entry, result) in enumerate(zip(plan.entries, report.results, strict=True)):
    keys = {(r.workflow, r.stage_id, r.cls, r.injected) for u in evaluation_units(result) for r in u}
    own = any(k[:3] == entry.target.key for k in keys)
    how = {k[3] for k in keys if k[:3] == entry.target.key}
    print(f"  plan-{i:2d} {entry.method:6s} {entry.target.key} 自分の run で到達={own} injected={how}")
