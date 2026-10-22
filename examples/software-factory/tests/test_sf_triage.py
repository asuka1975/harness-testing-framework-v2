"""トリアージの一周（雛形第 4・9 節）: unknown と低確信度の評価記録を積む → 人間がラベルを付ける（一部は却下）
→ コーパスに書き出す → オラクル検証にかける → 分類器とラベルが食い違う項目を記述改訂の候補として出す
（改訂は提案止まり。定義ファイルは変えない）。
"""

from __future__ import annotations

import hashlib
from collections import Counter

from sf_support import H, evaluation_records, marker_truth, run_scenario

from htf.contract import Verdict, VerdictKind
from htf.testing.harness import MarkerClassifier, ScriptedHuman
from htf.testing.oracle import load_corpus, verify_oracle
from htf.testing.triage import TriageQueue

UNKNOWN_SCENARIOS = [
    "intake_unknown",
    "code_broken_abort",
    "code_out_of_scope_rerun",
    "lint_unknown_continue",
    "unit_test_unknown",
    "verify_low_confidence",
    "review_unknown_rollback",
]


def _digest(path) -> str:  # noqa: ANN001
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_triage_round_trip(workflow, tmp_path):
    before = (_digest(H.WORKFLOW_PATH), _digest(H.CHILD_PATH))
    queue = TriageQueue(tmp_path / "triage.jsonl")
    for name in UNKNOWN_SCENARIOS:
        result = run_scenario(H.load_scenario(name), workflow, tmp_path / name)
        queue.enqueue(result, workflow=H.WORKFLOW_NAME, run_id=name, low_confidence=0.5)

    items = queue.list(status="open")
    by_stage = Counter((i.workflow, i.stage) for i in items)
    assert by_stage[("implement-task", "code")] >= 3  # 子 run の記録も辿る
    assert by_stage[("implement-task", "unit_test")] >= 1
    assert {("software-factory", "intake"), ("software-factory", "verify")} <= set(by_stage)
    assert all(i.document and i.options for i in items)

    # 人間のラベル付け（ここではラベラーの代わりに偽の世界の正解を使う）。intake の項目は「依頼者に聞き直す」で却下
    for item in items:
        if item.stage == "intake":
            queue.dismiss(item.id, note="成果物は正常。依頼者に聞き直す運用で対処")
        else:
            label = marker_truth(item.document, [o["id"] for o in item.options])
            queue.label(item.id, label=label, note="トリアージ")
    assert queue.list(status="open") == []

    corpus_path = tmp_path / "corpus.jsonl"
    exported = queue.export_corpus(corpus_path)
    assert exported == load_corpus(corpus_path)
    assert len(exported) == len(items) - by_stage[("software-factory", "intake")]

    report = verify_oracle(MarkerClassifier(), exported)
    pairs = list(zip(report.predictions, exported, strict=True))
    # ラベラーの代わりが印なので、選択とラベルの食い違いは出ない（実コーパスではここが改訂の主な入力）
    assert [item.id for p, item in pairs if p.option_id != item.label] == []
    # 記述改訂の候補: 選択は正しいが確信度が閾値未満の項目（記述が曖昧で分類器が迷った、の兆候）
    candidates = sorted(
        {(item.workflow, item.stage, item.label) for p, item in pairs if p.confidence < H.THRESHOLD}
    )
    assert candidates == [
        ("implement-task", "unit_test", "goal"),
        ("software-factory", "verify", "goal"),
    ]
    # 記述の改訂は提案止まり（人間の承認）: 定義ファイルは変わっていない
    assert (_digest(H.WORKFLOW_PATH), _digest(H.CHILD_PATH)) == before


def test_injected_verdicts_are_not_triaged_by_default(workflow, tmp_path):
    scenario = H.load_scenario("happy")
    inject = {(H.WORKFLOW_NAME, "release", 1): Verdict(kind=VerdictKind.UNKNOWN, reason="注入")}
    from htf.contract import Abort

    result = run_scenario(
        scenario, workflow, tmp_path / "ws", human=ScriptedHuman([Abort()]), inject=inject
    )
    assert result.status.value == "aborted"
    queue = TriageQueue(tmp_path / "triage.jsonl")
    assert queue.enqueue(result, workflow=H.WORKFLOW_NAME, run_id="inject") == []
    items = queue.enqueue(result, workflow=H.WORKFLOW_NAME, run_id="inject", include_injected=True)
    assert [i.stage for i in items] == ["release"] and items[0].injected


def test_low_confidence_records_are_triaged_even_when_goal(workflow, tmp_path):
    """閾値以上でも low_confidence 未満の確信度の記録は積める（ここでは全て 1.0 なので積まれない）。"""
    result = run_scenario(H.load_scenario("happy"), workflow, tmp_path / "ws")
    assert all(r.classification.confidence == 1.0 for r in evaluation_records(result))
    queue = TriageQueue(tmp_path / "triage.jsonl")
    assert queue.enqueue(result, workflow=H.WORKFLOW_NAME, run_id="happy", low_confidence=0.5) == []
