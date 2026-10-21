"""P1: 台本を変えると遷移列が期待どおりに変わるか（happy.yaml を起点に outcomes を差し替える）。"""

from _common import SCENARIOS, run_toy, show, toy
from htf.contract import Abort

base = toy.harness.load_scenario(SCENARIOS / "happy.yaml")

_, r = run_toy(base)
show("A happy（基準）", r)

_, r = run_toy(base.with_outcomes(verify=["checks_failed", "goal"]))
show("B1 verify=[checks_failed, goal] → draft へ境界越え 1 回", r)
draft_starts = [s for s in r.start_snapshots if s.stage_id == "draft"]
print("  draft 2 回目の開始時 memory:", draft_starts[1].memory)

_, r = run_toy(base.with_outcomes(verify=["checks_failed"]), resolutions=[Abort(note="探針")])
show("B2 verify=[checks_failed]（台本は最後を繰り返す）→ max 2 超過で escalate", r)

_, r = run_toy(base.with_outcomes(draft=["unknown"]), resolutions=[Abort(note="探針")])
show("C draft=[unknown] → escalate_unknown", r)

_, r = run_toy(base.with_outcomes(verify=["inputs_missing", "goal"]))
show("D verify=[inputs_missing, goal] → collect へ境界越え（carry: missing_inputs, max 1）", r)
collect_starts = [s for s in r.start_snapshots if s.stage_id == "collect"]
print("  collect 2 回目の開始時 memory:", collect_starts[1].memory)

_, r = run_toy(
    base.with_outcomes(verify=["inputs_missing", "inputs_missing"]), resolutions=[Abort(note="探針")]
)
show("E verify=[inputs_missing×2] → max 1 超過で escalate", r)
print("  escalation.edge:", r.escalations[0].edge, "cause:", r.escalations[0].cause)

import dataclasses

sc = dataclasses.replace(base, child_runs=[{"check_section": ["inconsistent"]}])
_, r = run_toy(sc)
show("F 子 check_section=[inconsistent] 1 回 → 子内でロールバックして goal（親からは見えない）", r)
print("  child_outcomes:", {k: [[o.kind for o in run] for run in v] for k, v in r.child_outcomes.items()})
