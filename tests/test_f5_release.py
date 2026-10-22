"""F5（v1.0 公開と維持）の完了条件。実装より先に書く（計画書第 6 節 F5）。

- 版 1.0.0、CI のコスト段階（常時 / ナイトリー / 手動）と `oracle` マーカー
- 分類体系とハーネスの同期バージョン管理: expectations と E2E 計画の `workflow_version` を runner が照合する。
  コーパスとトリアージの項目も版を持つ
- 文書: docs/maintenance.md、雛形の完成版と software factory の計画書の見出しの一致（矛盾が無い）、
  adopting-gaps.md が全て処置済み、adopting.md の完成版、README
「二つの玩具で全ランナーが通る」は tests/ と examples/software-factory/tests のスイートそのもの。
"""

from __future__ import annotations

import dataclasses
import json
import re
import tomllib
from collections import Counter
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from htf.contract import Abort
from htf.runtime import Runner, RunStatus, load_workflow
from htf.testing.harness import ScriptedHuman
from htf.testing.oracle import corpus_item_from_record, load_corpus, write_corpus
from htf.testing.stages import Tally, check_expectations, load_expectations
from htf.testing.triage import TriageQueue

ROOT = Path(__file__).resolve().parent.parent
TOY = ROOT / "examples" / "toy-minimal"
SF = ROOT / "examples" / "software-factory"
CI = ROOT / ".github" / "workflows" / "ci.yml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- 版と CI ---


def test_package_version_is_1_x() -> None:
    """v1.0 系（パッチ版は上がる。htf.__version__ との一致は test_repo_layout）。"""
    project = tomllib.loads(_read(ROOT / "pyproject.toml"))
    assert project["project"]["version"].split(".")[0] == "1"
    markers = project["tool"]["pytest"]["ini_options"]["markers"]
    assert any(m.startswith("oracle:") for m in markers)


def test_oracle_tests_carry_the_marker() -> None:
    for path in (ROOT / "tests" / "test_f3_oracle.py", SF / "tests" / "test_sf_oracle.py"):
        assert "pytestmark = pytest.mark.oracle" in _read(path), path


def test_ci_has_three_cost_tiers() -> None:
    doc = yaml.safe_load(_read(CI))
    triggers = doc[True] if True in doc else doc["on"]  # YAML は on を True に読む
    assert {"push", "pull_request", "schedule", "workflow_dispatch"} <= set(triggers)
    jobs = doc["jobs"]
    assert {"always", "nightly", "manual"} <= set(jobs)

    def commands(job: str) -> str:
        return "\n".join(str(s.get("run", "")) for s in jobs[job]["steps"])

    always = commands("always")
    assert "not distribution and not e2e and not oracle" in always
    assert "examples/software-factory/tests" in always
    assert "-m oracle" in commands("nightly") or '-m "oracle"' in commands("nightly")
    assert "distribution or e2e" in commands("manual")
    assert jobs["nightly"].get("if", "").startswith("github.event_name")
    assert jobs["manual"].get("if", "").startswith("github.event_name")


# --- 同期バージョン管理 ---


def _toy_workflow(toy: ModuleType):  # noqa: ANN202
    return load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())


@pytest.mark.parametrize(
    ("example", "workflow_path", "manifest"),
    [
        (TOY, TOY / "workflow.yaml", TOY / "metrics" / "manifest.json"),
        (SF, SF / "workflow.yaml", SF / "metrics" / "manifest.json"),
    ],
)
def test_expectations_and_plans_declare_the_workflow_version(
    example: Path, workflow_path: Path, manifest: Path
) -> None:
    names = json.loads(_read(manifest))["metrics"]
    version = load_workflow(workflow_path, metric_names=names).version
    files = sorted((example / "tests" / "expectations").glob("*.yaml"))
    plans = sorted((example / "tests" / "e2e").glob("*.yaml"))
    assert files and plans
    for path in files:
        assert load_expectations(path).workflow_version == version, path
    from htf.testing.e2e import load_plan

    for path in plans:
        assert load_plan(path).workflow_version == version, path


def test_expectations_version_mismatch_fails(toy: ModuleType) -> None:
    exp = load_expectations(TOY / "tests" / "expectations" / "markov.yaml")
    assert exp.workflow_version == "0.2"
    ok = Tally({}, Counter(), 0, workflow_version="0.2")
    check_expectations(ok, exp)  # 一致: 区間の検査に進む
    stale = Tally({}, Counter(), 0, workflow_version="0.1")
    with pytest.raises(ValueError, match="workflow_version"):
        check_expectations(stale, exp)
    unknown = Tally({}, Counter(), 0)  # 版の分からない集計は照合しない（古い呼び出し方）
    check_expectations(unknown, exp)


def test_tally_records_the_top_level_workflow_version(toy: ModuleType, tmp_path: Path) -> None:
    from htf.testing.stages import run_many, tally

    workflow = _toy_workflow(toy)
    scenario = toy.harness.load_scenario(TOY / "tests" / "fixtures" / "scenarios" / "happy.yaml")

    def make(seed: int) -> Runner:
        return Runner(
            workflow,
            toy.harness.make_bindings(scenario, human=ScriptedHuman([])),
            workspace=tmp_path / str(seed),
        )

    assert tally(run_many(make, runs=1, seed=1)).workflow_version == workflow.version


def test_plan_version_mismatch_fails(toy: ModuleType, tmp_path: Path) -> None:
    from htf.testing.e2e import load_plan, run_plan

    workflow = _toy_workflow(toy)
    plan = load_plan(TOY / "tests" / "e2e" / "plan.yaml")
    assert plan.workflow_version == workflow.version
    stale = dataclasses.replace(workflow, version="9.9")
    with pytest.raises(ValueError, match="workflow_version"):
        run_plan(plan, stale, toy.harness.make_plan_runner, workspace=tmp_path)


def test_plan_without_version_is_not_checked() -> None:
    from htf.testing.e2e import load_plan

    plan = load_plan(ROOT / "tests" / "fixtures" / "e2e" / "overrides_plan.yaml")
    assert plan.workflow_version is None


def test_corpus_items_round_trip_the_workflow_version(tmp_path: Path) -> None:
    from htf.contract import ClassOption

    item = corpus_item_from_record(
        item_id="x",
        workflow="toy-minimal",
        stage="collect",
        document="doc",
        options=[ClassOption("goal", "g")],
        label="goal",
        workflow_version="0.2",
    )
    assert item.workflow_version == "0.2"
    path = tmp_path / "corpus.jsonl"
    write_corpus(path, [item])
    assert load_corpus(path)[0].workflow_version == "0.2"
    # 版の欄が無い古い JSONL も読める
    path.write_text(
        json.dumps(
            {
                "id": "y",
                "workflow": "toy-minimal",
                "stage": "collect",
                "document": "d",
                "options": [{"id": "goal", "description": "g"}],
                "label": "goal",
                "note": "",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    assert load_corpus(path)[0].workflow_version is None


def test_triage_items_carry_the_version_of_their_workflow(toy: ModuleType, tmp_path: Path) -> None:
    """親と子のステージの項目は、それぞれの定義の版を持つ。"""
    workflow = _toy_workflow(toy)
    scenario = toy.harness.load_scenario(TOY / "tests" / "fixtures" / "scenarios" / "happy.yaml")
    child_name = workflow.stage("elaborate").subworkflow.child.name
    child_version = workflow.stage("elaborate").subworkflow.child.version
    from htf.contract import Verdict, VerdictKind

    # 子の check_section を unknown にする（子 run の記録が待ち行列に入る）。親の記録は low_confidence=1.1 で全て積む
    inject = {
        (child_name, "check_section", 1): Verdict(kind=VerdictKind.UNKNOWN, reason="注入"),
    }
    result = Runner(
        workflow,
        toy.harness.make_bindings(scenario, human=ScriptedHuman([Abort()])),
        workspace=tmp_path / "ws",
        inject=inject,
    ).run()
    assert result.status is RunStatus.ABORTED
    queue = TriageQueue(tmp_path / "triage.jsonl")
    items = queue.enqueue(
        result, workflow=workflow.name, run_id="r", low_confidence=1.1, include_injected=True
    )
    versions = {(i.workflow, i.workflow_version) for i in items}
    assert (workflow.name, workflow.version) in versions
    assert (child_name, child_version) in versions
    for item in items:
        queue.label(item.id, label="goal", note="")
    exported = queue.export_corpus(tmp_path / "corpus.jsonl")
    assert {(c.workflow, c.workflow_version) for c in exported} == versions


# --- 文書 ---

TEMPLATE_SECTIONS = [
    "## 0.",
    "## 1.",
    "## 2.",
    "## 3.",
    "## 4.",
    "## 5.",
    "## 6.",
    "## 7.",
    "## 8.",
    "## 9.",
    "## 付録",
]


def _section_keys(text: str) -> list[str]:
    """`## N. 題名（補足）` → `## N. 題名`（括弧の前まで。章の対応だけを比べる）。付録は種別だけ。"""
    keys = []
    for line in text.splitlines():
        if line.startswith("## 付録"):
            keys.append("## 付録")
        elif line.startswith("## "):
            keys.append(re.split(r"[（(]", line)[0].strip())
    return keys


def test_template_sections_match_the_software_factory_plan() -> None:
    template = _section_keys(_read(ROOT / "docs" / "harness-plan-template.md"))
    plan = _section_keys(_read(SF / "docs" / "plan.md"))
    assert [k for k in template if k[:5] in {s[:5] for s in TEMPLATE_SECTIONS}][
        : len(TEMPLATE_SECTIONS)
    ]
    template_main = [k for k in template if any(k.startswith(s) for s in TEMPLATE_SECTIONS)]
    plan_main = [k for k in plan if any(k.startswith(s) for s in TEMPLATE_SECTIONS)]
    assert plan_main == template_main, (plan_main, template_main)
    text = _read(ROOT / "docs" / "harness-plan-template.md")
    assert "最低限版" not in text.splitlines()[2]
    assert "software-factory" in text or "software factory" in text


def test_maintenance_doc_has_the_required_sections() -> None:
    text = _read(ROOT / "docs" / "maintenance.md")
    for needle in (
        "トリアージ",
        "記述の改訂",
        "workflow_version",
        "常時",
        "ナイトリー",
        "手動",
        "公開",
        "保護ファイル",
    ):
        assert needle in text, needle


def test_adopting_gaps_are_all_processed() -> None:
    text = _read(SF / "docs" / "adopting-gaps.md")
    status = text.split("## 処置の状況", 1)[1].split("## G-01", 1)[0]
    for i in range(1, 24):
        assert f"G-{i:02d}" in status, f"G-{i:02d}"


def test_adopting_guide_is_the_final_version() -> None:
    text = _read(ROOT / "docs" / "adopting.md")
    assert "初版" not in text.splitlines()[0]
    assert text.count("software-factory") + text.count("software factory") >= 10
    assert "落とし穴" in text
    assert "maintenance.md" in text


def test_readme_describes_v1() -> None:
    text = _read(ROOT / "README.md")
    assert "v1.0" in text and "software-factory" in text
