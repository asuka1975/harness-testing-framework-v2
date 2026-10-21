"""P2: writes 外への書き込み・未宣言の emit・未宣言ステージの ctx.user などが Runner 経由で ContractViolation になるか。"""

from pathlib import Path

from _common import tmp_ws
from htf.contract import ContractViolation, StageContext
from htf.runtime import Bindings, DictMetricRegistry, Runner, load_workflow
from htf.testing.harness import MarkerClassifier, QueueUserIO, ScriptedHuman

WF = Path(__file__).with_name("wf_violation.yaml")


class Seed:
    def run(self, ctx: StageContext) -> None:
        (ctx.workspace / "a.txt").write_text("outcome: goal\n")
        ctx.emit("k", 1)


class Probe:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def run(self, ctx: StageContext) -> None:
        ws = ctx.workspace
        (ws / "b.txt").write_text("outcome: goal\n")
        if self.mode == "write_outside":
            (ws / "stray.txt").write_text("x")
        elif self.mode == "emit_undeclared":
            ctx.emit("not_declared", 1)
        elif self.mode == "use_user":
            ctx.user.ask("質問")
        elif self.mode == "modify_reads":
            (ws / "a.txt").write_text("changed")
        elif self.mode == "delete_outside":
            (ws / "a.txt").unlink()
        elif self.mode == "write_meta":
            (ws / ".htf" / "note.txt").write_text("touch meta")
        elif self.mode == "read_memory_outside":
            print("    ctx.memory keys:", sorted(ctx.memory), "(memory_in は [k] のみ)")


def registry():
    return DictMetricRegistry(
        {"a_exists": lambda s: (s.files / "a.txt").is_file(), "b_exists": lambda s: (s.files / "b.txt").is_file()}
    )


def run(mode: str, *, strict: bool = True):
    wf = load_workflow(WF, metric_names=registry().names())
    b = Bindings(
        bodies={("probe_violation", "seed"): Seed(), ("probe_violation", "probe"): Probe(mode)},
        registry=registry(),
        classifier=MarkerClassifier(),
        user=QueueUserIO(["答え"]),
        human=ScriptedHuman([]),
    )
    try:
        r = Runner(wf, b, workspace=tmp_ws(), strict_writes=strict).run()
        print(f"  {mode:22s} strict={strict}: 例外なし status={r.status.value} transitions={[t.kind.value for t in r.trace]}")
    except ContractViolation as e:
        print(f"  {mode:22s} strict={strict}: ContractViolation: {e}")


for m in ["ok", "write_outside", "emit_undeclared", "use_user", "modify_reads", "delete_outside", "write_meta", "read_memory_outside"]:
    run(m)
run("write_outside", strict=False)
