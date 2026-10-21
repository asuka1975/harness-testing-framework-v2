"""探針の共通部。toy-minimal を読み、一時作業ディレクトリで Runner を回す。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from htf.runtime import Runner, RunStatus, load_workflow
from htf.testing.harness import ScriptedHuman, load_example_package

ROOT = Path(__file__).resolve().parents[4]
TOY_ROOT = ROOT / "examples" / "toy-minimal"
SCENARIOS = TOY_ROOT / "tests" / "fixtures" / "scenarios"
toy = load_example_package(TOY_ROOT, "toy_minimal")


def tmp_ws() -> Path:
    return Path(tempfile.mkdtemp(prefix="htf-probe-")) / "ws"


def run_toy(scenario, *, resolutions=None, workflow_path=None, bodies_override=None, human="scripted"):
    workflow = load_workflow(
        workflow_path or toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names()
    )
    decider = (
        ScriptedHuman(resolutions if resolutions is not None else scenario.resolutions)
        if human == "scripted"
        else None
    )
    bindings = toy.harness.make_bindings(scenario, human=decider)
    if bodies_override:
        bindings.bodies = {**bindings.bodies, **bodies_override}
    runner = Runner(workflow, bindings, workspace=tmp_ws())
    result = runner.run()
    answers = list(scenario.answers)
    while result.status is RunStatus.SUSPENDED and answers:
        result = runner.resume(answers.pop(0))
    return runner, result


def show(label: str, result) -> None:
    print(f"--- {label}")
    print("  status     :", result.status.value)
    print("  transitions:", [t.kind.value for t in result.trace])
    print("  gates      :", [f"{g.phase_id}:{g.event}" for g in result.gates])
    print("  edge_counts:", dict(result.edge_counts))
    print("  resolutions:", [type(r).__name__ for r in result.resolutions])
