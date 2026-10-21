"""P1b: 子 check_section=[inconsistent, goal] → 子の中でロールバックして goal。親のトレースには子内の遷移が現れないことの確認。"""

import dataclasses

from _common import SCENARIOS, run_toy, show, toy

base = toy.harness.load_scenario(SCENARIOS / "happy.yaml")
sc = dataclasses.replace(base, child_runs=[{"check_section": ["inconsistent", "goal"]}])
_, r = run_toy(sc)
show("子 check_section=[inconsistent, goal]", r)
print("  child_outcomes:", {k: [[(o.index, o.kind) for o in run] for run in v] for k, v in r.child_outcomes.items()})
end = [s for s in r.end_snapshots if s.stage_id == "elaborate"][-1]
sec = (end.files / "sections" / "0" / "section.md").read_text(encoding="utf-8")
print("  子 run 0 の section.md に carry の痕跡（修正: …）がある:", "修正:" in sec)
