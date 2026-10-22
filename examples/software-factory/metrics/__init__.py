"""software-factory の指標レジストリ。manifest.json の名前を、成果物から本物の値を計算する関数で実装する。

指標が見るのはスナップショットの files（そのステージ / フェーズの writes の範囲）と memory だけ。

- code の指標（changed_paths_nonempty）は、スナップショットの repo/ と fixtures の base の差分を自分で取る
- check の指標（build_passed / lint_clean / changed_paths_in_scope）は、本体が実ツールを走らせて check.json に記録した
  正規化済みの出力（build のエラー、lint の違反、out_of_scope）から計算する。repo/ は code の writes なので check の
  スナップショットには無い（版 0.2。htf の ADR-014 14.6.2）
- unit_test / verify の指標は、本体が実際に走らせた pytest とカバレッジの正規化した出力（results.json）から値を
  計算する。合否やカバレッジ率を本体が書いた要旨（report.json）の値として読まない
- 値を返せない時（成果物が無い、対象が空）は例外を投げる。runtime はそれを unknown（評価不能）にする
"""

from __future__ import annotations

import json
from pathlib import Path

from htf.contract import JsonValue, Snapshot
from htf.runtime import DictMetricRegistry

from .. import toolchain

MANIFEST_PATH = Path(__file__).parent / "manifest.json"


def _json(snapshot: Snapshot, name: str) -> dict:
    return json.loads((snapshot.files / name).read_text(encoding="utf-8"))


def _active(requirements: list[dict]) -> list[dict]:
    return [r for r in requirements if not r.get("deferred")]


# --- discovery ---


def intake_complete(s: Snapshot) -> JsonValue:
    d = _json(s, "intake/answers.json")
    required = all(bool(d.get(k)) for k in ("role", "summary", "features", "acceptance"))
    clarified = all(bool(d.get("clarifications", {}).get(q)) for q in d.get("asked", []))
    return required and isinstance(d["features"], list) and clarified


def active_requirement_count(s: Snapshot) -> JsonValue:
    return len(_active(_json(s, "requirements.json")["requirements"]))


def criteria_per_requirement(s: Snapshot) -> JsonValue:
    active = _active(_json(s, "requirements.json")["requirements"])
    if not active:
        raise ValueError("見送りでない要件が無い")
    return min(sum(1 for c in r.get("criteria", []) if c.get("test")) for r in active)


def open_question_count(s: Snapshot) -> JsonValue:
    return len(_json(s, "requirements.json")["open_questions"])


# --- design ---


def design_covers_requirements(s: Snapshot) -> JsonValue:
    d = _json(s, "design.json")
    satisfied = {r for c in d["components"] for r in c["satisfies"]}
    return bool(d["requirements"]) and set(d["requirements"]) <= satisfied


def design_conflict_count(s: Snapshot) -> JsonValue:
    return len(_json(s, "design.json")["conflicts"])


def task_count(s: Snapshot) -> JsonValue:
    return len(_json(s, "tasks.json")["tasks"])


def tasks_cover_design(s: Snapshot) -> JsonValue:
    d = _json(s, "tasks.json")
    covered = {c for t in d["tasks"] for c in t["components"]}
    return bool(d["design_components"]) and set(d["design_components"]) <= covered


def task_scopes_disjoint(s: Snapshot) -> JsonValue:
    seen: set[str] = set()
    for task in _json(s, "tasks.json")["tasks"]:
        scope = set(task["scope"])
        if scope & seen:
            return False
        seen |= scope
    return True


def unassigned_requirement_count(s: Snapshot) -> JsonValue:
    return len(_json(s, "tasks.json")["unassigned_requirements"])


# --- build（親 implement / integrate と子 implement-task） ---


def _dir(s: Snapshot, name: str) -> Path:
    path = s.files / name
    if not path.is_dir():
        raise FileNotFoundError(f"{name}/ がスナップショットに無い")
    return path


def tasks_summary_complete(s: Snapshot) -> JsonValue:
    summary = _json(s, "tasks/summary.json")
    expected = [t["id"] for t in s.memory["tasks"]]
    return [t["id"] for t in summary["tasks"]] == expected and all(
        t.get("status") for t in summary["tasks"]
    )


def merged_build_passed(s: Snapshot) -> JsonValue:
    return toolchain.build(_dir(s, "codebase"))["passed"]


def merged_paths_in_scope(s: Snapshot) -> JsonValue:
    allowed = {p for task in s.memory["tasks"] for p in task["scope"]}
    return all(p in allowed for p in toolchain.changed_paths(_dir(s, "codebase")))


def merge_conflict_count(s: Snapshot) -> JsonValue:
    m = _json(s, "merge.json")
    return len(m["conflicts"]) + len(m["failures"])


def changed_paths_nonempty(s: Snapshot) -> JsonValue:
    return bool(toolchain.changed_paths(_dir(s, "repo")))


def build_passed(s: Snapshot) -> JsonValue:
    build = _json(s, "check.json")["build"]
    return not build["errors"] and build["files"] > 0


def lint_clean(s: Snapshot) -> JsonValue:
    return not _json(s, "check.json")["lint"]["violations"]


def changed_paths_in_scope(s: Snapshot) -> JsonValue:
    return not _json(s, "check.json")["out_of_scope"]


def unit_tests_passed(s: Snapshot) -> JsonValue:
    return toolchain.tests_passed(_json(s, "unit/results.json")["result"])


def unit_coverage(s: Snapshot) -> JsonValue:
    result = _json(s, "unit/results.json")["result"]
    paths = [p for p in s.memory["task"]["scope"] if p.startswith("src/")]
    return round(toolchain.line_coverage(result["coverage"], paths), 4)


# --- assure ---


def suite_passed(s: Snapshot) -> JsonValue:
    return toolchain.tests_passed(_json(s, "verification/results.json")["result"])


def suite_coverage(s: Snapshot) -> JsonValue:
    result = _json(s, "verification/results.json")["result"]
    return round(toolchain.line_coverage(result["coverage"]), 4)


def suite_lint_clean(s: Snapshot) -> JsonValue:
    return not _json(s, "verification/results.json")["lint"]["violations"]


def criteria_verified_ratio(s: Snapshot) -> JsonValue:
    criteria = _json(s, "verification/report.json")["criteria"]
    if not criteria:
        raise ValueError("受け入れ基準が無い")
    tests = _json(s, "verification/results.json")["result"]["tests"]
    statuses = {t["nodeid"]: t["status"] for t in tests}
    passed = sum(1 for c in criteria if statuses.get(c["test"]) == "passed")
    return round(passed / len(criteria), 4)


def blocking_comment_count(s: Snapshot) -> JsonValue:
    return sum(1 for c in _json(s, "review.json")["comments"] if c["severity"] == "blocking")


# --- release ---


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in text.split("."))


def release_manifest_valid(s: Snapshot) -> JsonValue:
    m = _json(s, "release/manifest.json")
    return (
        m.get("base_version") == toolchain.base_version()
        and _version(m["version"]) > _version(m["base_version"])
        and bool(m["files"])
        and toolchain.manifest_digest(m["files"]) == m["digest"]
    )


def changelog_covers_requirements(s: Snapshot) -> JsonValue:
    m = _json(s, "release/manifest.json")
    text = (s.files / "release" / "CHANGELOG.md").read_text(encoding="utf-8")
    return bool(m["requirements"]) and all(r["id"] in text for r in m["requirements"])


def release_approved(s: Snapshot) -> JsonValue:
    return _json(s, "release/approval.json")["approved"] is True


def registry() -> DictMetricRegistry:
    reg = DictMetricRegistry(
        {
            "intake_complete": intake_complete,
            "active_requirement_count": active_requirement_count,
            "criteria_per_requirement": criteria_per_requirement,
            "open_question_count": open_question_count,
            "design_covers_requirements": design_covers_requirements,
            "design_conflict_count": design_conflict_count,
            "task_count": task_count,
            "tasks_cover_design": tasks_cover_design,
            "task_scopes_disjoint": task_scopes_disjoint,
            "unassigned_requirement_count": unassigned_requirement_count,
            "tasks_summary_complete": tasks_summary_complete,
            "merged_build_passed": merged_build_passed,
            "merged_paths_in_scope": merged_paths_in_scope,
            "merge_conflict_count": merge_conflict_count,
            "changed_paths_nonempty": changed_paths_nonempty,
            "build_passed": build_passed,
            "lint_clean": lint_clean,
            "changed_paths_in_scope": changed_paths_in_scope,
            "unit_tests_passed": unit_tests_passed,
            "unit_coverage": unit_coverage,
            "suite_passed": suite_passed,
            "suite_coverage": suite_coverage,
            "suite_lint_clean": suite_lint_clean,
            "criteria_verified_ratio": criteria_verified_ratio,
            "blocking_comment_count": blocking_comment_count,
            "release_manifest_valid": release_manifest_valid,
            "changelog_covers_requirements": changelog_covers_requirements,
            "release_approved": release_approved,
        }
    )
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["metrics"]
    assert sorted(manifest) == reg.names(), "manifest.json とレジストリの名前が一致しない"
    return reg
