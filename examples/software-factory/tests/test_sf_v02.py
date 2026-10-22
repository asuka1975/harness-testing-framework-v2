"""版 0.2 の完了条件（htf の ADR-014 の決定「全て推奨で」と小決定 14.6）。実装より先に書く。

- 定義: 親 9 ステージ（integrate を追加）、子 3 ステージ（check を追加）、end_state の集合と戻り先、優先の文言
- carry の閉包（14.6.7）: 辺 src → S の carry ⊇ 「戻り先が S より後ろにある全ての辺の carry の鍵」
- E2E の対象 43、新しい台本、指標、要旨と全結果の分離（14.6.9）
- 誘発できないクラス（14.6.8）の本体の論理: integrate の merge_failed、verify の coverage_short / lint_dirty
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from sf_support import ROOT, SF, H, run_scenario

from htf.contract import JsonValue, Snapshot
from htf.testing.e2e import enumerate_targets

tc = SF.toolchain
m = SF.metrics

PARENT_STAGES = [
    "intake",
    "analyze",
    "design",
    "plan",
    "implement",
    "integrate",
    "verify",
    "review",
    "release",
]
CHILD_STAGES = ["code", "check", "unit_test"]
END_STATES = {
    "intake": {"unknown"},
    "analyze": {"ambiguous", "unknown"},
    "design": {"requirements_conflict", "unknown"},
    "plan": {"design_gap", "design_incomplete", "unknown"},
    "implement": {"tasks_unfinished", "unknown"},
    "integrate": {"merge_failed", "unknown"},
    "verify": {"regression", "criteria_unmet", "coverage_short", "lint_dirty", "unknown"},
    "review": {"design_flaw", "changes_requested", "unknown"},
    "release": {"rejected_requirements", "rejected_quality", "unknown"},
    "code": {"unknown"},
    "check": {"build_failed", "out_of_scope", "lint_failed", "unknown"},
    "unit_test": {"tests_failing", "coverage_low", "unknown"},
}
# (ステージ, end_state) → (戻り先, その辺が自分で運ぶ鍵)
ROLLBACK = {
    ("analyze", "ambiguous"): ("intake", "open_questions"),
    ("design", "requirements_conflict"): ("analyze", "conflicts"),
    ("plan", "design_gap"): ("design", "uncovered_components"),
    ("plan", "design_incomplete"): ("design", "unassigned_requirements"),
    ("implement", "tasks_unfinished"): ("plan", "unfinished_tasks"),
    ("integrate", "merge_failed"): ("plan", "merge_failures"),
    ("verify", "regression"): ("plan", "regressions"),
    ("verify", "criteria_unmet"): ("plan", "unmet_criteria"),
    ("verify", "coverage_short"): ("plan", "suite_coverage_gaps"),
    ("verify", "lint_dirty"): ("plan", "suite_lint_violations"),
    ("review", "design_flaw"): ("design", "design_issues"),
    ("review", "changes_requested"): ("plan", "review_comments"),
    ("release", "rejected_requirements"): ("analyze", "rejection_feedback"),
    ("release", "rejected_quality"): ("plan", "rejection_feedback"),
    ("check", "build_failed"): ("code", "check_failures"),
    ("check", "out_of_scope"): ("code", "check_failures"),
    ("check", "lint_failed"): ("code", "check_failures"),
    ("unit_test", "tests_failing"): ("code", "test_failures"),
    ("unit_test", "coverage_low"): ("code", "coverage_gaps"),
}
# 「この状態は X に優先する」を記述に持つ end_state（14.6.1 / 14.6.4 / 14.6.6）
PRIORITY = {
    ("verify", "regression"),
    ("verify", "criteria_unmet"),
    ("verify", "coverage_short"),
    ("review", "design_flaw"),
    ("plan", "design_incomplete"),
    ("check", "build_failed"),
    ("check", "out_of_scope"),
    ("unit_test", "tests_failing"),
}
NEW_SCENARIOS = [
    "check_build_failed_fixed",
    "check_lint_failed_fixed",
    "check_out_of_scope_fixed",
    "check_max_exceeded",
    "check_unknown_continue",
    "code_unknown_rerun",
    "plan_design_incomplete",
    "release_rejected_quality",
]
REMOVED_SCENARIOS = ["code_broken_abort", "code_out_of_scope_rerun", "lint_unknown_continue"]
NEW_METRICS = [
    "changed_paths_nonempty",
    "tasks_summary_complete",
    "merge_conflict_count",
    "unassigned_requirement_count",
]


def _child(workflow):  # noqa: ANN001, ANN202
    return workflow.stage("implement").subworkflow.child


# --- 定義 ---


def test_versions_are_0_2(workflow):
    assert workflow.version == "0.2"
    assert _child(workflow).version == "0.2"


def test_stage_order(workflow):
    assert [s.id for s in workflow.stages] == PARENT_STAGES
    assert [s.id for s in _child(workflow).stages] == CHILD_STAGES
    assert [s.id for s in workflow.stages if s.user_input] == ["intake", "release"]
    assert workflow.stage("implement").subworkflow is not None
    assert workflow.stage("integrate").subworkflow is None


def test_end_states_and_rollback_targets(workflow):
    child = _child(workflow)
    for stage in [*workflow.stages, *child.stages]:
        assert set(stage.end_state_ids()) == END_STATES[stage.id], stage.id
        for state in END_STATES[stage.id] - {"unknown"}:
            target, own = ROLLBACK[(stage.id, state)]
            rb = stage.rollback_for(state)
            assert rb is not None and rb.stage == target, (stage.id, state)
            assert own in rb.carry, (stage.id, state, rb.carry)
            assert rb.max >= 1


def test_priority_sentences_are_in_the_descriptions(workflow):
    child = _child(workflow)
    for stage in [*workflow.stages, *child.stages]:
        for es in stage.end_state:
            has = "優先" in es.description
            assert has == ((stage.id, es.id) in PRIORITY), (stage.id, es.id, es.description)


def test_carry_closure(workflow):
    """14.6.7: 辺 src → S の carry は、自分の鍵 ∪ 戻り先が S より後ろにある全ての辺の carry の鍵を含む。"""
    for doc in (workflow, _child(workflow)):
        edges = [
            (doc.index_of(s.id), doc.index_of(rb.stage), rb, s)
            for s in doc.stages
            for rb in s.rollback
        ]
        for _src, target, rb, stage in edges:
            later = {k for _s2, t2, rb2, _st2 in edges if t2 > target for k in rb2.carry}
            missing = sorted(later - set(rb.carry))
            assert not missing, (
                f"{doc.name}: {stage.id}/{rb.state} → {rb.stage} に {missing} が無い"
            )
            target_stage = doc.stage(rb.stage)
            assert set(rb.carry) <= set(stage.artifacts.memory_out)
            assert set(rb.carry) <= set(target_stage.artifacts.memory_in)


def test_aggregate_covers_every_child_failure(workflow):
    rules = workflow.stage("implement").subworkflow.aggregate
    pairs = [(r.state, r.quantifier, r.outcome.stage, r.outcome.state) for r in rules]
    unknown_first = [p for p in pairs if p[0] == "unknown"]
    assert pairs[: len(unknown_first)] == unknown_first  # 明示の escalate は上に置く
    assert {(p[2], p[3]) for p in unknown_first} == {
        ("code", "unknown"),
        ("check", "unknown"),
        ("unit_test", "unknown"),
    }
    assert {(p[2], p[3]) for p in pairs if p[0] == "tasks_unfinished"} == {
        ("check", "build_failed"),
        ("check", "out_of_scope"),
        ("check", "lint_failed"),
        ("unit_test", "tests_failing"),
        ("unit_test", "coverage_low"),
    }


def test_forty_three_targets(workflow):
    targets = {(t.workflow, t.stage_id, t.state) for t in enumerate_targets(workflow)}
    assert len(targets) == 43
    assert {
        ("implement-task", "check", "build_failed"),
        ("software-factory", "integrate", "merge_failed"),
        ("software-factory", "plan", "design_incomplete"),
        ("software-factory", "release", "rejected_quality"),
        ("software-factory", "verify", "lint_dirty"),
    } <= targets


def test_new_scenarios_exist_and_old_ones_are_gone():
    names = set(H.scenario_names())
    assert set(NEW_SCENARIOS) <= names
    assert not set(REMOVED_SCENARIOS) & names
    for name in NEW_SCENARIOS:
        H.load_scenario(name)


def test_manifest_has_the_new_metrics():
    manifest = json.loads(H.MANIFEST_PATH.read_text(encoding="utf-8"))["metrics"]
    assert set(NEW_METRICS) <= set(manifest)
    assert sorted(manifest) == H.registry().names()


def test_quality_lead_persona_rejects_for_quality_then_approves():
    persona = SF.user.load_persona("quality_lead")
    roles = yaml.safe_load(
        (ROOT / "fixtures/artifacts/requirements/catalog.yaml").read_text(encoding="utf-8")
    )["roles"]
    assert persona["answers"]["role"] in roles
    user = SF.user.PersonaUserIO("quality_lead")
    question = f"{SF.stages.RELEASE_PREFIX} textkit 0.2.0 をリリースしてよいですか？ 含む要件: R1, R2, R3。"
    first = user.ask(question)
    assert first["approved"] is False and first["kind"] == "quality" and first["reason"]
    second = user.ask(question)
    assert second["approved"] is True


# --- 指標（14.6.2: check の指標は check.json の正規化した記録から） ---

SLUG_TASK = {
    "id": "T1",
    "features": ["slug"],
    "scope": ["src/textkit/normalize.py", "src/textkit/slug.py", "tests/test_slug.py"],
    "tests": ["tests/test_slug.py"],
}


def _snapshot(files: Path, memory: dict, stage: str, workflow: str = "implement-task") -> Snapshot:
    return Snapshot(
        workflow=workflow,
        version="0.2",
        stage_id=stage,
        moment="end",
        ordinal=1,
        files=files,
        memory=memory,
    )


@pytest.mark.parametrize(
    ("variant", "build", "lint", "scope"),
    [
        ("correct", True, True, True),
        ("broken", False, False, True),
        ("lint", True, False, True),
        ("out_of_scope", True, True, False),
    ],
)
def test_check_metrics_read_check_json(variant, build, lint, scope, tmp_path):
    repo = tmp_path / "repo"
    tc.materialize(repo, SLUG_TASK["features"], variant)
    (tmp_path / "check.json").write_text(
        json.dumps(tc.check(repo, SLUG_TASK["scope"]), ensure_ascii=False), encoding="utf-8"
    )
    snap = _snapshot(tmp_path, {"task": SLUG_TASK}, "check")
    assert m.build_passed(snap) is build
    assert m.lint_clean(snap) is lint
    assert m.changed_paths_in_scope(snap) is scope
    assert m.changed_paths_nonempty(_snapshot(tmp_path, {"task": SLUG_TASK}, "code")) is True


def test_changed_paths_nonempty_is_false_without_a_change(tmp_path):
    tc.materialize(tmp_path / "repo", [], "correct")
    assert m.changed_paths_nonempty(_snapshot(tmp_path, {"task": SLUG_TASK}, "code")) is False


def test_unit_metrics_read_results_json(tmp_path):
    repo = tmp_path / "repo"
    tc.materialize(repo, SLUG_TASK["features"], "correct")
    results = tmp_path / "unit" / "results.json"
    results.parent.mkdir()
    results.write_text(
        json.dumps({"result": tc.run_tests(repo, SLUG_TASK["tests"])}), encoding="utf-8"
    )
    snap = _snapshot(tmp_path, {"task": SLUG_TASK}, "unit_test")
    assert m.unit_tests_passed(snap) is True
    assert m.unit_coverage(snap) >= 0.9


# --- 誘発できないクラスの本体の論理（14.6.8） ---


class FakeContext:
    def __init__(self, workspace: Path, memory: dict | None = None) -> None:
        self.workspace = workspace
        self.memory = dict(memory or {})
        self.emitted: dict[str, JsonValue] = {}

    def emit(self, key: str, value: JsonValue) -> None:
        self.emitted[key] = value


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, doc: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _done_task(ws: Path, i: int, task: dict, repo_edit) -> None:  # noqa: ANN001
    """check と unit_test を通ったタスクの作業ディレクトリを手で作る。"""
    repo = ws / "tasks" / str(i) / "repo"
    tc.materialize(repo, task["features"], "correct")
    repo_edit(repo)
    check = tc.check(repo, task["scope"])
    _write(ws / "tasks" / str(i) / "check.json", {"outcome": "goal", **check})
    _write(
        ws / "tasks" / str(i) / "unit" / "report.json",
        {"outcome": "goal", "task": task["id"], "failed": [], "coverage_gaps": {}},
    )


def test_integrate_reports_merge_failed_on_conflicting_paths(tmp_path):
    """二つのタスクが同じパスを違う内容に変えると、統合は衝突を merge.json に記録して merge_failed。"""
    ws = tmp_path / "ws"
    t1 = {
        "id": "T1",
        "features": ["slug"],
        "scope": ["src/textkit/normalize.py", "src/textkit/slug.py", "tests/test_slug.py"],
    }
    t2 = {
        "id": "T2",
        "features": ["stats"],
        "scope": ["src/textkit/normalize.py", "src/textkit/stats.py", "tests/test_stats.py"],
    }

    def edit_a(repo: Path) -> None:
        (repo / "src/textkit/normalize.py").write_text(
            '"""A"""\n\n\ndef normalize_whitespace(text: str) -> str:\n    return " ".join(text.split())\n',
            encoding="utf-8",
        )

    def edit_b(repo: Path) -> None:
        (repo / "src/textkit/normalize.py").write_text(
            '"""B"""\n\n\ndef normalize_whitespace(text: str) -> str:\n    return " ".join(text.split())\n',
            encoding="utf-8",
        )

    _done_task(ws, 0, t1, edit_a)
    _done_task(ws, 1, t2, edit_b)
    _write(
        ws / "tasks" / "summary.json",
        {
            "outcome": "goal",
            "tasks": [{"id": "T1", "status": "done"}, {"id": "T2", "status": "done"}],
            "unfinished": [],
        },
    )
    ctx = FakeContext(ws, {"tasks": [t1, t2]})
    SF.stages.Integrate(SF.stages.Script({})).run(ctx)
    merge = _json(ws / "merge.json")
    assert merge["outcome"] == "merge_failed"
    assert [c["path"] for c in merge["conflicts"]] == ["src/textkit/normalize.py"]
    assert ctx.emitted["merge_failures"]
    assert (ws / "codebase" / "src" / "textkit" / "slug.py").is_file()


def _requirements(ws: Path) -> None:
    catalog = yaml.safe_load(
        (ROOT / "fixtures/artifacts/requirements/catalog.yaml").read_text(encoding="utf-8")
    )
    reqs = [
        {"id": rid, **catalog["requirements"][rid], "deferred": False} for rid in ("R1", "R2", "R3")
    ]
    _write(
        ws / "requirements.json", {"outcome": "goal", "requirements": reqs, "open_questions": []}
    )


def _full_codebase(ws: Path) -> Path:
    repo = ws / "codebase"
    tc.materialize(repo, ["slug", "stats", "truncate"], "correct")
    return repo


def test_verify_reports_lint_dirty_when_only_lint_fails(tmp_path):
    ws = tmp_path / "ws"
    _requirements(ws)
    repo = _full_codebase(ws)
    init = repo / "src" / "textkit" / "__init__.py"
    init.write_text("import os\n" + init.read_text(encoding="utf-8"), encoding="utf-8")  # F401
    ctx = FakeContext(ws)
    SF.stages.Verify(SF.stages.Script({})).run(ctx)
    report = _json(ws / "verification" / "report.json")
    assert report["outcome"] == "lint_dirty"
    assert ctx.emitted["suite_lint_violations"][0]["code"] == "F401"
    assert (ws / "verification" / "results.json").is_file()
    assert len(json.dumps(report, ensure_ascii=False)) < 4000  # 要旨は切り詰めに掛からない


def test_verify_reports_coverage_short_when_only_coverage_is_low(tmp_path):
    ws = tmp_path / "ws"
    _requirements(ws)
    repo = _full_codebase(ws)
    lines = ["def f{i}(x):\n    return x + {i}\n\n\n".replace("{i}", str(i)) for i in range(40)]
    (repo / "src" / "textkit" / "extra.py").write_text(
        '"""未テストの補助。"""\n\n\n' + "".join(lines), encoding="utf-8"
    )
    ctx = FakeContext(ws)
    SF.stages.Verify(SF.stages.Script({})).run(ctx)
    report = _json(ws / "verification" / "report.json")
    assert report["outcome"] == "coverage_short"
    assert report["coverage"] < 0.85
    assert "src/textkit/extra.py" in ctx.emitted["suite_coverage_gaps"]


def test_verify_priority_regression_over_the_rest(tmp_path):
    """既存のテストが落ち、lint 違反もある → regression（優先 1）。"""
    ws = tmp_path / "ws"
    _requirements(ws)
    repo = ws / "codebase"
    tc.materialize(repo, ["slug", "stats", "truncate"], "regression")
    init = repo / "src" / "textkit" / "__init__.py"
    init.write_text("import os\n" + init.read_text(encoding="utf-8"), encoding="utf-8")
    ctx = FakeContext(ws)
    SF.stages.Verify(SF.stages.Script({})).run(ctx)
    assert _json(ws / "verification" / "report.json")["outcome"] == "regression"


# --- 要旨と全結果の分離（14.6.9）、承認の種類（14.6.5） ---


def test_summaries_are_small_and_results_are_separate(workflow, tmp_path):
    run_scenario(H.load_scenario("happy"), workflow, tmp_path / "ws")
    ws = tmp_path / "ws"
    for rel in ("verification/report.json", "tasks/0/unit/report.json", "tasks/0/check.json"):
        text = (ws / rel).read_text(encoding="utf-8")
        assert len(text) < 4000, rel
        assert text.lstrip().startswith('{\n  "outcome"'), rel
    assert (ws / "verification" / "results.json").is_file()
    assert (ws / "tasks" / "0" / "unit" / "results.json").is_file()
    approval = _json(ws / "release" / "approval.json")
    assert approval["approved"] is True and approval["kind"] is None
    manifest = _json(ws / "release" / "manifest.json")
    assert manifest["base_version"] == "0.1.0"
    summary = _json(ws / "tasks" / "summary.json")
    assert [t["status"] for t in summary["tasks"]] == ["done", "done", "done"]
