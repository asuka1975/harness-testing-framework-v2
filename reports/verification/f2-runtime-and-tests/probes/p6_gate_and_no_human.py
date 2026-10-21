"""P6: フェーズゲート不成立の escalate に ContinueAsGoal を返すとどうなるか（gate.yaml）。
最上位の Runner に human を束縛せずに unknown になると何が返るか。"""

import json

from _common import ROOT, SCENARIOS, run_toy, show, tmp_ws, toy
from htf.contract import Abort, ContinueAsGoal, Rerun
from htf.runtime import Bindings, DictMetricRegistry, Runner, load_workflow
from htf.testing.harness import MarkerClassifier, ScriptedHuman

WF = ROOT / "tests" / "fixtures" / "workflows" / "gate.yaml"


class Seed:
    def __init__(self, values):
        self.values, self.calls = values, 0

    def run(self, ctx):
        v = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        (ctx.workspace / "a.json").write_text(json.dumps({"gate_ok": v, "outcome": "goal"}))


class Probe:
    def run(self, ctx):
        (ctx.workspace / "b.json").write_text(json.dumps({"outcome": "goal"}))


def reg():
    return DictMetricRegistry(
        {
            "a_exists": lambda s: (s.files / "a.json").exists(),
            "gate_ok": lambda s: json.loads((s.files / "a.json").read_text())["gate_ok"],
            "b_exists": lambda s: (s.files / "b.json").exists(),
        }
    )


def run(values, resolutions):
    wf = load_workflow(WF, metric_names=reg().names())
    b = Bindings(bodies={("gate", "seed"): Seed(values), ("gate", "probe"): Probe()}, registry=reg(), classifier=MarkerClassifier(), human=ScriptedHuman(resolutions))
    try:
        return Runner(wf, b, workspace=tmp_ws()).run()
    except AssertionError as e:
        print("  ScriptedHuman の台本が尽きた:", e)
        return None


r = run([False], [ContinueAsGoal(note="1"), ContinueAsGoal(note="2"), Abort(note="諦め")])
show("ゲート不成立 → ContinueAsGoal ×2 → Abort", r)
print("  escalations:", [(e.cause, e.verdict.decided_by) for e in r.escalations])

r = run([False, True], [Rerun(note="再実行")])
show("ゲート不成立 → Rerun（本体が 2 回目は gate_ok=true を書く）", r)

sc = toy.harness.load_scenario(SCENARIOS / "verify_unknown.yaml")
_, r = run_toy(sc, human=None)
show("最上位 Runner に human=None で verify が unknown", r)
print("  child_outcome:", r.child_outcome, " escalations:", len(r.escalations))
