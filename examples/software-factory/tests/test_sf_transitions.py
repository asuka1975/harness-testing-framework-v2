"""遷移の決定論テスト（adopting.md 3.9）。台本（fixtures/scenarios/）で偽本体を制御し、期待した遷移列を確かめる。

- 各台本の終了状態・遷移列・ゲート・子 run の数と子の遷移列
- 7 種の遷移、escalate の 4 つの解決（abort / rerun / continue_as_goal / rollback_to）
- 記録 → 再生でスナップショットの digest が一致する
- carry の中身が戻り先に届き、成果物に反映される（ペルソナの回答、要件の見送り、タスクの notes）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sf_support import SCENARIOS, H, run_scenario

from htf.contract import (
    Abort,
    ContinueAsGoal,
    Rerun,
    RollbackTo,
    TransitionKind,
    Verdict,
    VerdictKind,
)
from htf.runtime import Recorder, snapshot_digest
from htf.testing.harness import ScriptedHuman, observed_kinds

_results: dict[str, object] = {}


def _run(name: str, workflow, tmp_path: Path):  # noqa: ANN001, ANN202
    result = run_scenario(H.load_scenario(name), workflow, tmp_path / name)
    _results[name] = result
    return result


def _kinds(trace) -> list[str]:  # noqa: ANN001
    return [t.kind.value for t in trace]


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenario(name, workflow, tmp_path):
    scenario = H.load_scenario(name)
    result = _run(name, workflow, tmp_path)
    expect = scenario.expect
    assert result.status.value == expect["status"]
    assert _kinds(result.trace) == expect["transitions"]
    if "gates" in expect:
        assert [f"{g.phase_id}:{g.event}" for g in result.gates] == expect["gates"]
    if "child_runs" in expect:
        assert [len(entry) for entry in result.child_results["implement"]] == expect["child_runs"]
    if "child_transitions" in expect:
        first_entry = result.child_results["implement"][0]
        assert [_kinds(r.trace) for r in first_entry] == expect["child_transitions"]


def test_all_seven_transition_kinds_are_observed(workflow, tmp_path):
    kinds: set[TransitionKind] = set()
    for name in SCENARIOS:
        result = _results.get(name) or _run(name, workflow, tmp_path)
        kinds |= observed_kinds(result.trace)
        for entries in result.child_results.values():
            for entry in entries:
                for child in entry:
                    kinds |= observed_kinds(child.trace)
    assert kinds == set(TransitionKind)


def test_all_four_resolutions_are_exercised(workflow, tmp_path):
    seen = set()
    for name in ("code_broken_abort", "code_out_of_scope_rerun", "verify_low_confidence",
                 "review_unknown_rollback"):  # fmt: skip
        result = _results.get(name) or _run(name, workflow, tmp_path)
        seen |= {type(r) for r in result.resolutions}
    assert seen == {Abort, Rerun, ContinueAsGoal, RollbackTo}


def test_child_escalations_stay_in_the_child(workflow, tmp_path):
    """子の unknown / max 超過は人間へ行かず、子 run の終わり方として親の集約に渡る（adopting.md 第 4 節）。"""
    result = _results.get("tasks_unfinished") or _run("tasks_unfinished", workflow, tmp_path)
    first = result.child_results["implement"][0]
    assert _kinds(first[0].trace) == [
        "next",
        "rollback_within_phase",
        "next",
        "escalate_max_exceeded",
    ]
    assert result.child_outcomes["implement"][0][0].kind == "stuck"
    assert result.escalations == []  # 親では escalate していない


@pytest.mark.parametrize(
    "name",
    ["happy", "domain_expert_conflict", "tasks_unfinished", "suspend_resume", "busy_sponsor"],
)
def test_record_then_replay_gives_identical_snapshots(name, workflow, tmp_path):
    scenario = H.load_scenario(name)
    log = tmp_path / "run.jsonl"
    recorded = run_scenario(
        scenario, workflow, tmp_path / "record", recorder=Recorder(log, mode="record")
    )
    assert recorded.status.value == "completed"
    bindings = H.make_bindings(
        scenario, workflow, human=ScriptedHuman(scenario.resolutions), replay=True
    )
    replayed = H.runner(
        workflow, bindings, workspace=tmp_path / "replay", recorder=Recorder(log, mode="replay")
    ).run()
    assert replayed.status.value == "completed"  # 再生では回答が記録から来るので中断しない
    assert [snapshot_digest(s) for s in replayed.end_snapshots] == [
        snapshot_digest(s) for s in recorded.end_snapshots
    ]
    assert _kinds(replayed.trace) == [k for k in _kinds(recorded.trace) if k != "suspend_resume"]


def test_phase_gate_failure_escalates_and_human_can_pass_it(workflow, tmp_path):
    """plan の判定を goal に差し替える（注入）と、design のゲート（tasks_cover_design）が成果物で落ちる。"""
    scenario = H.load_scenario("happy").with_outcomes(plan=["design_gap", "goal"])
    inject = {(H.WORKFLOW_NAME, "plan", 1): Verdict(kind=VerdictKind.GOAL, reason="注入")}
    aborted = run_scenario(
        scenario, workflow, tmp_path / "abort", human=ScriptedHuman([Abort()]), inject=inject
    )
    assert aborted.status.value == "aborted"
    assert aborted.escalations[-1].cause == "phase_gate_failed"
    assert [f"{g.phase_id}:{g.event}" for g in aborted.gates] == [
        "discovery:passed",
        "design:failed",
    ]

    passed = run_scenario(
        scenario,
        workflow,
        tmp_path / "continue",
        human=ScriptedHuman([ContinueAsGoal(note="2 コンポーネントで出す")]),
        inject=inject,
    )
    assert passed.status.value == "completed"
    design_gate = [(g.event, g.note) for g in passed.gates if g.phase_id == "design"]
    assert design_gate[:2] == [("failed", ""), ("passed", "human")]


# --- carry と成果物 ---


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_end_user_answers_the_carried_question(workflow, tmp_path):
    scenario = H.load_scenario("end_user_clarify")
    bindings = H.make_bindings(scenario, workflow)
    result = H.runner(workflow, bindings, workspace=tmp_path / "ws").run()
    assert result.status.value == "completed"
    asked = bindings.user.asked
    assert asked.count("あなたの役割は何ですか？") == 2  # 再進入でも同じ順で尋ねる
    assert asked[-2].startswith("[Q1]") and asked[-1].startswith("[release]")
    answers = _json(tmp_path / "ws" / "intake" / "answers.json")
    assert answers["asked"] == ["Q1"] and answers["clarifications"]["Q1"]
    reqs = _json(tmp_path / "ws" / "requirements.json")
    assert reqs["open_questions"] == []
    assert all(r["criteria"] for r in reqs["requirements"])


def test_domain_expert_deferral_is_agreed_after_rejection(workflow, tmp_path):
    result = run_scenario(H.load_scenario("domain_expert_conflict"), workflow, tmp_path / "ws")
    assert result.status.value == "completed"
    reqs = _json(tmp_path / "ws" / "requirements.json")
    r4 = next(r for r in reqs["requirements"] if r["id"] == "R4")
    assert r4["deferred"] and r4["agreed"]
    assert [d.get("conflict") for d in reqs["decisions"] if "conflict" in d] == [["R1", "R4"]]
    changelog = (tmp_path / "ws" / "release" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "R4" in changelog and "合意済み" in changelog
    rejected = [e for e in result.evaluations if e.stage_id == "release" and e.cls == "rejected"]
    assert rejected and rejected[0].carry_out["rejection_feedback"]["unagreed"] == ["R4"]


@pytest.mark.parametrize(
    ("name", "needle"),
    [
        ("regression", "既存のテスト tests/test_normalize.py::test_keeps_case を壊さない"),
        ("criteria_unmet", "受け入れ基準 R3-2 を確かめるテスト"),
        ("review_changes", "レビューの指摘（src/textkit/slug.py）"),
        (
            "tasks_unfinished",
            "前回の単体テストが通らなかった: 失敗したテスト tests/test_slug.py::test_basic",
        ),
    ],
)
def test_carry_reaches_the_plan_as_task_notes(name, needle, workflow, tmp_path):
    result = run_scenario(H.load_scenario(name), workflow, tmp_path / "ws")
    assert result.status.value == "completed"
    tasks = _json(tmp_path / "ws" / "tasks.json")["tasks"]
    notes = [n for t in tasks for n in t["notes"]]
    assert any(needle in n for n in notes), notes


def test_happy_artifacts_carry_real_tool_results(workflow, tmp_path):
    run_scenario(H.load_scenario("happy"), workflow, tmp_path / "ws")
    report = _json(tmp_path / "ws" / "verification" / "report.json")
    statuses = {t["status"] for t in report["result"]["tests"]}
    assert len(report["result"]["tests"]) == 14 and statuses == {"passed"}
    assert report["coverage"] == 1.0 and report["lint"]["violations"] == []
    assert {c["status"] for c in report["criteria"]} == {"passed"}
    merge = _json(tmp_path / "ws" / "merge.json")
    assert merge["merged"] == ["T1", "T2", "T3"] and merge["conflicts"] == []
    manifest = _json(tmp_path / "ws" / "release" / "manifest.json")
    assert manifest["files"]["src/textkit/slug.py"]
