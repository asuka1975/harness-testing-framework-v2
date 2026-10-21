"""P7: 再進入で each のリストが 2 → 1 に減った時、前回の子 run の作業ディレクトリ runs/1/ が親の終了時スナップショットと指標に残るか。"""

import json
from pathlib import Path

from _common import show, tmp_ws
from htf.runtime import Bindings, DictMetricRegistry, Runner, load_workflow
from htf.testing.harness import MarkerClassifier, ScriptedHuman

WF = Path(__file__).with_name("shrink") / "shrink.yaml"


class Seed:
    def __init__(self):
        self.calls = 0

    def run(self, ctx):
        items = [["a", "b"], ["a"]][min(self.calls, 1)]
        self.calls += 1
        (ctx.workspace / "seed.json").write_text(json.dumps({"outcome": "goal", "items": items}))
        ctx.emit("items", items)


class Fan:
    def __init__(self):
        self.seen = []

    def run(self, ctx):
        self.seen.append(sorted(p.name for p in (ctx.workspace / "runs").iterdir() if p.is_dir()))
        ctx.emit("why", ["やり直し"])


class W:
    def run(self, ctx):
        (ctx.workspace / "w.txt").write_text("outcome: goal\n")


class Check:
    def __init__(self, outcomes):
        self.outcomes, self.calls = outcomes, 0

    def run(self, ctx):
        o = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        (ctx.workspace / "c.json").write_text(json.dumps({"outcome": o}))
        if o == "bad":
            ctx.emit("fix", ["直す"])


def run_dirs(s):
    root = s.files / "runs"
    return len([p for p in root.iterdir() if p.is_dir()]) if root.is_dir() else 0


reg = DictMetricRegistry({"seed_exists": lambda s: (s.files / "seed.json").is_file(), "w_exists": lambda s: (s.files / "w.txt").is_file(), "run_dirs": run_dirs})
wf = load_workflow(WF, metric_names=reg.names())
fan = Fan()
# 子 run 0（item a）: bad, bad → max 1 超過で stuck。子 run 1（item b）: goal。再進入後の子 run 0: goal
b = Bindings(
    bodies={("shrink_parent", "seed"): Seed(), ("shrink_parent", "fan"): fan, ("shrink_child", "w"): W(), ("shrink_child", "check"): Check(["bad", "bad", "goal", "goal"])},
    registry=reg,
    classifier=MarkerClassifier(),
    human=ScriptedHuman([]),
)
r = Runner(wf, b, workspace=tmp_ws()).run()
show("items [a, b] → fan_bad → seed → items [a] → fan", r)
print("  fan の本体が各進入で見た runs/ 配下:", fan.seen)
print("  child_outcomes:", {k: [[(o.index, o.kind, o.stage, o.state) for o in run] for run in v] for k, v in r.child_outcomes.items()})
ends = [s for s in r.end_snapshots if s.stage_id == "fan"]
print("  fan の終了時スナップショットの runs/ 配下:", [sorted(p.name for p in (s.files / "runs").iterdir()) for s in ends])
print("  2 回目の items:", r.memory.get("items"), " run_dirs 指標の値:", run_dirs(ends[-1]))
