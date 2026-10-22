"""実ツールの指標（ビルド通過・テスト通過・カバレッジ・lint・変更パスの範囲）が、変更の変種ごとに本物の値を返す。

指標はスナップショット（files と memory）だけを見るので、ここでは本体と同じ方法で作った成果物を Snapshot に包んで渡す。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sf_support import SF

from htf.contract import Snapshot

tc = SF.toolchain
m = SF.metrics

SLUG_TASK = {
    "id": "T1",
    "features": ["slug"],
    "scope": ["src/textkit/normalize.py", "src/textkit/slug.py", "tests/test_slug.py"],
    "tests": ["tests/test_slug.py"],
}

# 変種 → (build_passed, lint_clean, changed_paths_in_scope, unit_tests_passed, unit_coverage >= 0.9, スイート全体が通る)
EXPECTED = {
    "correct": (True, True, True, True, True, True),
    "failing": (True, True, True, False, True, False),
    "failing_edge": (True, True, True, False, True, False),
    "low_coverage": (True, True, True, True, False, True),
    "regression": (True, True, True, True, True, False),
    "missing_test": (True, True, True, True, True, True),
    "lint": (True, False, True, True, True, True),
    "broken": (False, False, True, False, None, False),
    "out_of_scope": (True, True, False, True, True, True),
}


def _snapshot(files: Path, memory: dict, stage: str) -> Snapshot:
    return Snapshot(
        workflow="implement-task",
        version="0.2",
        stage_id=stage,
        moment="end",
        ordinal=1,
        files=files,
        memory=memory,
    )


@pytest.mark.parametrize("variant", sorted(EXPECTED))
def test_code_check_and_unit_test_metrics_per_variant(variant, tmp_path):
    """版 0.2: code の指標は repo/ の差分、check の指標は check.json の記録、unit_test の指標は unit/results.json。"""
    build, lint, scope, unit_ok, cov_ok, suite_ok = EXPECTED[variant]
    repo = tmp_path / "repo"
    tc.materialize(repo, SLUG_TASK["features"], variant)
    before = tc.files_of(repo)
    assert m.changed_paths_nonempty(_snapshot(tmp_path, {"task": SLUG_TASK}, "code")) is True
    (tmp_path / "check.json").write_text(
        json.dumps(tc.check(repo, SLUG_TASK["scope"]), ensure_ascii=False), encoding="utf-8"
    )
    snap = _snapshot(tmp_path, {"task": SLUG_TASK}, "check")
    assert m.build_passed(snap) is build
    assert m.lint_clean(snap) is lint
    assert m.changed_paths_in_scope(snap) is scope

    result = tc.run_tests(repo, SLUG_TASK["tests"])
    results = tmp_path / "unit" / "results.json"
    results.parent.mkdir()
    results.write_text(json.dumps({"result": result}), encoding="utf-8")
    snap = _snapshot(tmp_path, {"task": SLUG_TASK}, "unit_test")
    assert m.unit_tests_passed(snap) is unit_ok
    if cov_ok is None:
        with pytest.raises(ValueError):  # 対象の文が無い → 評価不能（unknown）
            m.unit_coverage(snap)
    else:
        assert (m.unit_coverage(snap) >= 0.9) is cov_ok

    assert tc.tests_passed(tc.run_tests(repo, [])) is suite_ok
    assert tc.files_of(repo) == before, "ツールが作業ディレクトリに書き込んだ"


def test_regression_is_only_visible_to_the_full_suite(tmp_path):
    repo = tmp_path / "repo"
    tc.materialize(repo, ["slug"], "regression")
    assert tc.failed_tests(tc.run_tests(repo, ["tests/test_slug.py"])) == []
    assert tc.failed_tests(tc.run_tests(repo, [])) == ["tests/test_normalize.py::test_keeps_case"]


def test_failing_variants_name_different_tests(tmp_path):
    """split の代表（carry の test_failures）が区別できること。"""
    failures = {}
    for variant in ("failing", "failing_edge"):
        repo = tmp_path / variant
        tc.materialize(repo, ["slug"], variant)
        failures[variant] = tc.failed_tests(tc.run_tests(repo, ["tests/test_slug.py"]))
    assert failures == {
        "failing": ["tests/test_slug.py::test_basic", "tests/test_slug.py::test_symbols"],
        "failing_edge": ["tests/test_slug.py::test_empty"],
    }


def test_tool_results_are_memoized_by_content(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    tc.materialize(a, ["stats"], "correct")
    tc.materialize(b, ["stats"], "correct")
    assert tc.run_tests(a, ["tests/test_stats.py"]) == tc.run_tests(b, ["tests/test_stats.py"])
    tc.set_cache(False)
    try:
        assert tc.run_tests(a, ["tests/test_stats.py"]) == tc.run_tests(b, ["tests/test_stats.py"])
    finally:
        tc.set_cache(True)


def test_merged_metrics_use_the_union_of_task_scopes(tmp_path):
    codebase = tmp_path / "codebase"
    tc.materialize(codebase, ["slug", "stats", "truncate"], "correct")
    tasks = [
        {"scope": ["src/textkit/normalize.py", "src/textkit/slug.py", "tests/test_slug.py"]},
        {"scope": ["src/textkit/stats.py", "tests/test_stats.py"]},
    ]
    snap = _snapshot(tmp_path, {"tasks": tasks}, "implement")
    assert m.merged_build_passed(snap) is True
    assert m.merged_paths_in_scope(snap) is False  # truncate はどのタスクの scope にも無い
    tasks.append({"scope": ["src/textkit/truncate.py", "tests/test_truncate.py"]})
    assert m.merged_paths_in_scope(snap) is True


def test_metric_raises_when_artifact_is_missing(tmp_path):
    snap = _snapshot(tmp_path, {"task": SLUG_TASK}, "code")
    with pytest.raises(FileNotFoundError):
        m.build_passed(snap)
