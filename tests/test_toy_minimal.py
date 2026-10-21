"""toy-minimal の定義が F1 の完了条件を満たすこと。

- 整合性検査を通る（子ワークフローを含めて）
- 計画書 F1 の要求する形を静的に含む: 3〜4 ステージ、ロールバック（フェーズ内とフェーズ境界越え）、
  carry、ユーザー待ち、子ワークフロー（ADR-009 (b)）
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from htf.testing.spec import check_workflow, index_workflow

ROOT = Path(__file__).resolve().parent.parent
TOY = ROOT / "examples" / "toy-minimal"
WORKFLOW = TOY / "workflow.yaml"
MANIFEST = TOY / "metrics" / "manifest.json"


def _metric_names() -> list[str]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["metrics"]


def test_toy_minimal_passes_spec_check() -> None:
    report = check_workflow(WORKFLOW, metric_names=_metric_names())
    assert report.findings == [], [
        f"{f.file}:{f.path} {f.code}: {f.message}" for f in report.findings
    ]
    assert report.skipped == []


def test_toy_minimal_has_required_shapes() -> None:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    idx = index_workflow(doc)
    assert len(doc["workflow"]["phases"]) >= 2
    assert 3 <= len(idx.stages) <= 4

    within = cross = carried = 0
    for s in idx.stages:
        for rb in s.stage["rollback"]:
            if idx.phase_of(rb["stage"]) == s.phase_id:
                within += 1
            else:
                cross += 1
            if rb.get("carry"):
                carried += 1
    assert within >= 1, "フェーズ内ロールバックが無い"
    assert cross >= 1, "フェーズ境界を越えるロールバックが無い"
    assert carried >= 1, "carry 付きロールバックが無い"
    assert any(s.stage.get("user_input") for s in idx.stages), "ユーザー待ちのステージが無い"
    assert any("subworkflow" in s.stage for s in idx.stages), "子ワークフローを呼ぶステージが無い"


def test_toy_minimal_child_declares_inputs_supplied_by_parent() -> None:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    idx = index_workflow(doc)
    parents = [s for s in idx.stages if "subworkflow" in s.stage]
    for s in parents:
        sub = s.stage["subworkflow"]
        child = yaml.safe_load((WORKFLOW.parent / sub["ref"]).read_text(encoding="utf-8"))
        supplied = {sub["item_as"], *sub.get("pass", [])}
        assert supplied == set(child["workflow"].get("inputs", []))
