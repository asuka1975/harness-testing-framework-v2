"""P4: 辺の max を変えた定義で、escalate_max_exceeded までのロールバック回数が max と一致するか。
max 超過後の Rerun / RollbackTo も踏む。"""

import shutil
from pathlib import Path

from _common import SCENARIOS, TOY_ROOT, run_toy, show, toy
from htf.contract import Abort, Rerun, RollbackTo, TransitionKind

HERE = Path(__file__).parent
ORIG = (TOY_ROOT / "workflow.yaml").read_text(encoding="utf-8")
NEEDLE = "carry: [failing_checks]\n              max: 2"
assert ORIG.count(NEEDLE) == 1

base = toy.harness.load_scenario(SCENARIOS / "happy.yaml")

for n in (1, 3):
    d = HERE / f"max_{n}"
    d.mkdir(exist_ok=True)
    (d / "workflow.yaml").write_text(ORIG.replace(NEEDLE, f"carry: [failing_checks]\n              max: {n}"), encoding="utf-8")
    shutil.copy(TOY_ROOT / "elaborate-claim.yaml", d / "elaborate-claim.yaml")
    sc = base.with_outcomes(verify=["checks_failed"])
    _, r = run_toy(sc, resolutions=[Abort(note="探針")], workflow_path=d / "workflow.yaml")
    rollbacks = sum(1 for t in r.trace if t.kind is TransitionKind.ROLLBACK_ACROSS_PHASE and t.stage_id == "verify")
    show(f"max={n}: verify が常に checks_failed", r)
    print(f"  escalate 前のロールバック回数 = {rollbacks}（max={n} と一致: {rollbacks == n}）, 計数 = {r.edge_counts.get(('verify', 'checks_failed'))}")

# max=1 で超過後に Rerun → verify が goal になって完走
d = HERE / "max_1"
_, r = run_toy(base.with_outcomes(verify=["checks_failed", "checks_failed", "goal"]), resolutions=[Rerun(note="探針")], workflow_path=d / "workflow.yaml")
show("max=1: 超過 → 人間 Rerun → verify 3 回目は goal", r)
# max=1 で超過後に RollbackTo(draft) → 計数を消費せず draft → verify goal
_, r = run_toy(
    base.with_outcomes(verify=["checks_failed", "checks_failed", "goal"]),
    resolutions=[RollbackTo(stage="draft", carry={"failing_checks": ["人間"]}, note="探針")],
    workflow_path=d / "workflow.yaml",
)
show("max=1: 超過 → 人間 RollbackTo(draft) → 完走", r)
print("  人間の rollback の note:", [t.note for t in r.trace if t.kind is TransitionKind.ROLLBACK_ACROSS_PHASE])
