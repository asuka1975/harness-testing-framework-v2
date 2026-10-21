"""F3 完了条件: トリアージ待ち行列にサンプル一件を流せる（unknown の評価記録 → 待ち行列 → ラベル → コーパス）。"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

from htf.runtime import Runner, RunStatus, load_workflow
from htf.testing.harness import ScriptedHuman
from htf.testing.oracle import load_corpus
from htf.testing.triage import TriageQueue

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "examples" / "toy-minimal" / "tests" / "fixtures" / "scenarios"


def test_one_unknown_flows_through_triage(toy: ModuleType, tmp_path: Path) -> None:
    from htf.contract import Abort

    scenario = toy.harness.load_scenario(SCENARIOS / "verify_unknown.yaml")
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    result = Runner(
        workflow,
        toy.harness.make_bindings(scenario, human=ScriptedHuman([Abort()])),
        workspace=tmp_path / "ws",
    ).run()
    assert result.status is RunStatus.ABORTED
    assert any(e.verdict.kind.value == "unknown" for e in result.evaluations)

    queue = TriageQueue(tmp_path / "triage.jsonl")
    added = queue.enqueue(result, workflow=workflow.name, run_id="run-1")
    assert len(added) == 1
    item = added[0]
    assert item.stage == "verify" and item.status == "open"
    assert "## writes" in item.document and "report.json" in item.document
    assert [o["id"] for o in item.options] == ["goal", "checks_failed", "inputs_missing", "unknown"]

    assert [i.id for i in queue.list(status="open")] == [item.id]
    queue.label(item.id, label="checks_failed", note="失敗した検査の一覧がある")
    assert queue.list(status="open") == []
    assert queue.list(status="labeled")[0].label == "checks_failed"

    corpus_path = tmp_path / "corpus.jsonl"
    exported = queue.export_corpus(corpus_path)
    assert len(exported) == 1
    assert load_corpus(corpus_path)[0].label == "checks_failed"
