"""整合性検査（雛形第 1 節の完了条件）と、定義・フィクスチャの対応。"""

from __future__ import annotations

import json
import subprocess
import sys

import yaml
from sf_support import ROOT, SF, H

from htf.testing.e2e import enumerate_targets
from htf.testing.spec import check_workflow


def test_workflow_passes_integrity_check_with_registry_names():
    report = check_workflow(H.WORKFLOW_PATH, metric_names=H.registry().names())
    assert report.ok, [f"{f.code} {f.path}: {f.message}" for f in report.findings]
    assert report.findings == []
    assert report.skipped == []


def test_cli_with_manifest_exits_zero():
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "htf.testing.spec",
            str(H.WORKFLOW_PATH),
            "--metrics",
            str(H.MANIFEST_PATH),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "0 finding(s)" in proc.stdout


def test_manifest_matches_registry():
    manifest = json.loads(H.MANIFEST_PATH.read_text(encoding="utf-8"))["metrics"]
    assert sorted(manifest) == H.registry().names()


def test_shape_meets_the_brief(workflow):
    """4 フェーズ以上 8 ステージ以上、境界越えロールバック・carry・ユーザー待ちが一つ以上、unknown は全ステージ。"""
    assert len(workflow.phases) >= 4
    assert len(workflow.stages) >= 8
    child = workflow.stage("implement").subworkflow.child
    across, carried = [], []
    for stage in [*workflow.stages, *child.stages]:
        doc = child if stage in child.stages else workflow
        assert "unknown" in stage.end_state_ids()
        assert {r.state for r in stage.rollback} == set(stage.end_state_ids()) - {"unknown"}
        for r in stage.rollback:
            if doc.phase_of(r.stage) != doc.phase_of(stage.id):
                across.append((stage.id, r.stage))
            if r.carry:
                carried.append((stage.id, r.stage))
    assert across and carried
    assert [s.id for s in workflow.stages if s.user_input] == ["intake", "release"]


def test_stage_ids_are_unique_across_parent_and_child(workflow):
    """tally / transition_matrix / expectations はステージ id で数えるので、親子で id を重ねない（G-06）。"""
    child = workflow.stage("implement").subworkflow.child
    assert not {s.id for s in workflow.stages} & {s.id for s in child.stages}


def test_every_class_has_a_coverage_target(workflow):
    targets = {(t.workflow, t.stage_id, t.state) for t in enumerate_targets(workflow)}
    assert (
        len(targets) == 43
    )  # 版 0.2: integrate と check を加え、verify / release / plan のクラスを増やした
    assert ("implement-task", "unit_test", "coverage_low") in targets
    assert ("implement-task", "check", "build_failed") in targets


def test_three_or_more_personas():
    personas = SF.user.persona_names()
    assert len(personas) >= 3
    for name in personas:
        persona = SF.user.load_persona(name)
        assert persona["id"] == name
        assert (
            persona["answers"]["role"]
            in yaml.safe_load(
                (ROOT / "fixtures/artifacts/requirements/catalog.yaml").read_text(encoding="utf-8")
            )["roles"]
        )


def test_all_scenarios_load():
    for name in H.scenario_names():
        scenario = H.load_scenario(name)
        assert scenario.expect["status"] in ("completed", "aborted")
        for resolution in scenario.human:
            H.parse_resolution(resolution)
