"""F4 の adopting-gaps.md（software factory）で見つかった htf 本体の不足を、toy-minimal で再現して固定する。

第5.8節: 本体の修正は toy-minimal のテストで検証してから、software factory で再検証する。
  G-04 subworkflow.pass の鍵が初回進入で memory に無い（carry でしか来ない）→ 子に渡さず起動する
  G-05 一部だけ即答して残りで中断する UserIO → 再開で回答がずれない
  G-06 親子でステージ id が重なる定義を検査器が落とす
  G-08 状態文書の切り詰めの長さを変えられる
  G-16 E2E 計画の一項目で台本の任意の欄を上書きできる
"""

from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType

import pytest

from htf.contract import Abort, JsonValue, StageContext, WaitingForUser
from htf.runtime import Bindings, DictMetricRegistry, Runner, RunStatus, load_workflow
from htf.testing.harness import MarkerClassifier, ScriptedHuman

ROOT = Path(__file__).resolve().parent.parent
TOY = ROOT / "examples" / "toy-minimal"
SCENARIOS = TOY / "tests" / "fixtures" / "scenarios"
FIXTURES = ROOT / "tests" / "fixtures"


# --- G-05 ---


class PartialPersona:
    """知っている質問には即答し、知らない質問で中断する UserIO（自然なシミュレータの形）。"""

    def __init__(self) -> None:
        self.known = {"題目は?": "題目X", "主張の一覧は?": ["主張A"]}
        self.asked: list[str] = []

    def ask(self, question: str, *, schema: dict[str, JsonValue] | None = None) -> JsonValue:
        self.asked.append(question)
        if question in self.known:
            return self.known[question]
        raise WaitingForUser(question, schema)


def test_g05_partial_answers_are_accumulated_in_order(toy: ModuleType, tmp_path: Path) -> None:
    scenario = toy.harness.load_scenario(SCENARIOS / "happy.yaml")
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    bindings = toy.harness.make_bindings(scenario, human=ScriptedHuman([]))
    bindings.user = PartialPersona()
    runner = Runner(workflow, bindings, workspace=tmp_path / "ws")
    result = runner.run()
    assert result.status is RunStatus.SUSPENDED
    assert result.pending is not None and result.pending.question == "根拠の所在は?"
    result = runner.resume({"主張A": "grounds/0.txt"})
    assert result.status is RunStatus.COMPLETED, result.pending
    inputs = json.loads((tmp_path / "ws" / "inputs.json").read_text(encoding="utf-8"))
    assert inputs["title"] == "題目X" and inputs["claims"] == ["主張A"]
    assert inputs["grounds"] == {"主張A": "grounds/0.txt"}


# --- G-04 ---


class _Seed:
    def run(self, ctx: StageContext) -> None:
        (ctx.workspace / "seed.json").write_text(json.dumps({"outcome": "goal"}))
        ctx.emit("items", ["a"])


class _Fan:
    def run(self, ctx: StageContext) -> None:
        pass


class _Child:
    def run(self, ctx: StageContext) -> None:
        (ctx.workspace / "out.json").write_text(
            json.dumps({"outcome": "goal", "hint": ctx.memory.get("hint")}, ensure_ascii=False)
        )


class _Check:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, ctx: StageContext) -> None:
        self.calls += 1
        outcome = "bad" if self.calls == 1 else "goal"
        (ctx.workspace / "check.json").write_text(json.dumps({"outcome": outcome}))
        if outcome == "bad":
            ctx.emit("hint", "二回目のヒント")


def test_g04_pass_key_that_only_arrives_by_carry_is_optional_on_first_entry(tmp_path: Path) -> None:
    registry = DictMetricRegistry({"seed_exists": lambda s: (s.files / "seed.json").is_file()})
    workflow = load_workflow(
        FIXTURES / "workflows" / "pass_carry.yaml", metric_names=registry.names()
    )
    bindings = Bindings(
        bodies={
            ("pass_carry", "seed"): _Seed(),
            ("pass_carry", "fan"): _Fan(),
            ("pass_carry", "check"): _Check(),
            ("pass_child", "work"): _Child(),
        },
        registry=registry,
        classifier=MarkerClassifier(),
        human=ScriptedHuman([]),
    )
    result = Runner(workflow, bindings, workspace=tmp_path / "ws").run()
    assert result.status is RunStatus.COMPLETED
    fan_ends = [s for s in result.end_snapshots if s.stage_id == "fan"]
    assert len(fan_ends) == 2
    first = json.loads((fan_ends[0].files / "runs" / "0" / "out.json").read_text(encoding="utf-8"))
    second = json.loads((fan_ends[1].files / "runs" / "0" / "out.json").read_text(encoding="utf-8"))
    assert first["hint"] is None, "初回進入: carry でしか来ない鍵は子に渡らない（落ちない）"
    assert second["hint"] == "二回目のヒント", "再進入: carry で来た鍵は子に渡る"


# --- G-06 ---


def test_g06_checker_rejects_stage_id_shared_between_parent_and_child() -> None:
    from htf.testing.spec import check_workflow

    report = check_workflow(
        ROOT / "schema" / "examples" / "negative" / "unique_ids__stage_shared_with_child.yaml",
        metric_names=json.loads((ROOT / "schema" / "examples" / "metrics.json").read_text())[
            "metrics"
        ],
    )
    assert "unique_ids" in {f.code for f in report.findings}


# --- G-08 ---


def test_g08_projection_truncation_is_configurable(toy: ModuleType, tmp_path: Path) -> None:
    from htf.runtime import project

    scenario = toy.harness.load_scenario(SCENARIOS / "happy.yaml")
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    # 既定（4000 文字）では完走する
    ok = Runner(
        workflow,
        toy.harness.make_bindings(scenario, human=ScriptedHuman([])),
        workspace=tmp_path / "a",
    ).run()
    assert ok.status is RunStatus.COMPLETED
    # 40 文字で切ると inputs.json の末尾の印が落ち、collect が unknown になる
    short = Runner(
        workflow,
        toy.harness.make_bindings(scenario, human=ScriptedHuman([Abort()])),
        workspace=tmp_path / "b",
        max_file_chars=40,
    ).run()
    assert short.status is RunStatus.ABORTED
    assert short.trace[0].stage_id == "collect"
    # project 単体でも長さを指定できる
    end = ok.end_snapshots[0]
    doc = project(workflow.stage("collect"), end, tmp_path / "a", max_file_chars=40)
    assert "文字省略" in doc


# --- G-16 ---


def test_g16_plan_entry_can_override_any_scenario_field(toy: ModuleType, tmp_path: Path) -> None:
    from htf.testing.e2e import load_plan, run_plan

    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    plan = load_plan(FIXTURES / "e2e" / "overrides_plan.yaml")
    assert plan.entries[0].overrides == {"claims": ["主張X", "主張Y", "主張Z"]}
    report = run_plan(plan, workflow, toy.harness.make_plan_runner, workspace=tmp_path)
    result = report.results[0]
    assert len(result.child_results["elaborate"][0]) == 3, (
        "上書きした claims で子 run が 3 つ起動する"
    )
