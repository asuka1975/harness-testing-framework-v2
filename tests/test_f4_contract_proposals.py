"""契約への提案 14.2〜14.5（ADR-014。F4 ゲートで承認）の完了条件。実装より先に書く。

14.2 StageContext.entry / reentry: 本体が runtime と同じ規則で進入回数を知る
14.3 StageContext.child_outcomes: 子を持つステージの本体が子 run の終わり方を読み取り専用で受け取る
14.4 UserIO.ask(question, *, schema=None, context=None): 質問の根拠を構造で渡す（累積列と recorder を通る）
14.5 状態文書: (a) 文書全体の上限 Runner(max_document_chars=)、(b) `## writes` を `## reads` より前に置く。
     MarkerClassifier は writes 節だけを見る
"""

from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType

import pytest

from htf.contract import (
    Abort,
    ChildOutcome,
    JsonValue,
    StageContext,
    Verdict,
    VerdictKind,
    WaitingForUser,
)
from htf.runtime import (
    Bindings,
    DictMetricRegistry,
    Recorder,
    Runner,
    RunStatus,
    load_workflow,
    project,
)
from htf.testing.harness import (
    ClassOption,
    DeferringUserIO,
    MarkerClassifier,
    QueueUserIO,
    ScriptedHuman,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
TOY = ROOT / "examples" / "toy-minimal"
SCENARIOS = TOY / "tests" / "fixtures" / "scenarios"


# --- 14.2 / 14.3: pass_carry（seed → fan[子 work] → check。check が一度 bad で fan へ戻る） ---


class _Log:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, bool, tuple[ChildOutcome, ...]]] = []

    def note(self, ctx: StageContext) -> None:
        self.calls.append((ctx.stage_id, ctx.entry, ctx.reentry, tuple(ctx.child_outcomes)))

    def of(self, stage_id: str) -> list[tuple[int, bool]]:
        return [(e, r) for s, e, r, _ in self.calls if s == stage_id]


class _Seed:
    def __init__(self, log: _Log) -> None:
        self.log = log

    def run(self, ctx: StageContext) -> None:
        self.log.note(ctx)
        (ctx.workspace / "seed.json").write_text(json.dumps({"outcome": "goal"}))
        ctx.emit("items", ["a"])


class _Fan:
    def __init__(self, log: _Log) -> None:
        self.log = log

    def run(self, ctx: StageContext) -> None:
        self.log.note(ctx)


class _Child:
    def __init__(self, log: _Log) -> None:
        self.log = log

    def run(self, ctx: StageContext) -> None:
        self.log.note(ctx)
        (ctx.workspace / "out.json").write_text(json.dumps({"outcome": "goal"}))


class _Check:
    def __init__(self, log: _Log) -> None:
        self.log = log
        self.calls = 0

    def run(self, ctx: StageContext) -> None:
        self.log.note(ctx)
        self.calls += 1
        outcome = "bad" if self.calls == 1 else "goal"
        (ctx.workspace / "check.json").write_text(json.dumps({"outcome": outcome}))
        if outcome == "bad":
            ctx.emit("hint", "二回目")


def _pass_carry(tmp_path: Path, *, inject=None, human=None):  # noqa: ANN001, ANN202
    log = _Log()
    registry = DictMetricRegistry({"seed_exists": lambda s: (s.files / "seed.json").is_file()})
    workflow = load_workflow(
        FIXTURES / "workflows" / "pass_carry.yaml", metric_names=registry.names()
    )
    bindings = Bindings(
        bodies={
            ("pass_carry", "seed"): _Seed(log),
            ("pass_carry", "fan"): _Fan(log),
            ("pass_carry", "check"): _Check(log),
            ("pass_child", "work"): _Child(log),
        },
        registry=registry,
        classifier=MarkerClassifier(),
        human=human or ScriptedHuman([]),
    )
    result = Runner(workflow, bindings, workspace=tmp_path / "ws", inject=inject).run()
    return result, log


def test_14_2_entry_and_reentry_follow_the_runtime_rule(tmp_path: Path) -> None:
    result, log = _pass_carry(tmp_path)
    assert result.status is RunStatus.COMPLETED
    assert log.of("seed") == [(1, False)]
    assert log.of("fan") == [(1, False), (2, True)]  # check の bad で戻された再進入
    assert log.of("check") == [(1, False), (2, True)]
    assert log.of("work") == [(1, False), (1, False)]  # 子 run は run ごとに数え直す


def test_14_3_child_outcomes_are_visible_to_the_parent_body(tmp_path: Path) -> None:
    result, log = _pass_carry(tmp_path)
    assert result.status is RunStatus.COMPLETED
    fan = [outs for s, _, _, outs in log.calls if s == "fan"]
    assert fan == [(ChildOutcome(index=0, kind="goal"),)] * 2
    assert all(outs == () for s, _, _, outs in log.calls if s != "fan")  # 子を持たないステージは空


def test_14_3_child_unknown_reaches_the_parent_body_before_escalation(tmp_path: Path) -> None:
    inject = {("pass_child", "work", 1): Verdict(kind=VerdictKind.UNKNOWN, reason="注入")}
    result, log = _pass_carry(tmp_path, inject=inject, human=ScriptedHuman([Abort()]))
    assert result.status is RunStatus.ABORTED
    fan = [outs for s, _, _, outs in log.calls if s == "fan"]
    assert fan == [(ChildOutcome(index=0, kind="unknown", stage="work", state="unknown"),)]


def test_14_2_entry_counts_human_rerun_and_rollback_to(tmp_path: Path) -> None:
    """人間の Rerun と carry 無しの RollbackTo でも進入回数は増える（検証役 f5-release の探針を退行テストに）。"""
    from htf.contract import Rerun, RollbackTo

    inject = {("pass_carry", "check", 1): Verdict(kind=VerdictKind.UNKNOWN, reason="注入")}
    result, log = _pass_carry(tmp_path / "rerun", inject=inject, human=ScriptedHuman([Rerun()]))
    assert result.status is RunStatus.COMPLETED
    assert log.of("check") == [
        (1, False),
        (2, True),
    ]  # Rerun: 同じ開始時スナップショットから 2 回目
    assert dict(result.edge_counts) == {}  # 辺の max は消費しない

    result, log = _pass_carry(
        tmp_path / "rollback", inject=inject, human=ScriptedHuman([RollbackTo(stage="seed")])
    )
    assert result.status is RunStatus.COMPLETED
    assert log.of("seed") == [(1, False), (2, True)]
    assert log.of("fan") == [(1, False), (2, True)]
    assert log.of("check") == [(1, False), (2, True)]
    assert dict(result.edge_counts) == {}


# --- 14.4: ask(..., context=) ---

CONTEXT: dict[str, JsonValue] = {"reason": "見送られた要件 R4", "options": ["合意", "再検討"]}


class _AskWithContext:
    def run(self, ctx: StageContext) -> None:
        answer = ctx.user.ask("見送りに合意しますか?", schema={"type": "string"}, context=CONTEXT)
        (ctx.workspace / "answer.json").write_text(
            json.dumps({"outcome": "goal", "answer": answer}, ensure_ascii=False)
        )


class _ContextRecordingUser:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, object]] = []

    def ask(
        self,
        question: str,
        *,
        schema: dict[str, JsonValue] | None = None,
        context: dict[str, JsonValue] | None = None,
    ) -> JsonValue:
        self.calls.append((question, schema, context))
        return "合意"


def _ask_context(tmp_path: Path, user, recorder: Recorder | None = None):  # noqa: ANN001, ANN202
    registry = DictMetricRegistry({"answer_exists": lambda s: (s.files / "answer.json").is_file()})
    workflow = load_workflow(
        FIXTURES / "workflows" / "ask_context.yaml", metric_names=registry.names()
    )
    bindings = Bindings(
        bodies={("ask_context", "ask"): _AskWithContext()},
        registry=registry,
        classifier=MarkerClassifier(),
        user=user,
        human=ScriptedHuman([]),
    )
    return Runner(workflow, bindings, workspace=tmp_path / "ws", recorder=recorder).run()


def test_14_4_context_reaches_the_bound_user_io(tmp_path: Path) -> None:
    user = _ContextRecordingUser()
    result = _ask_context(tmp_path, user)
    assert result.status is RunStatus.COMPLETED
    assert user.calls == [("見送りに合意しますか?", {"type": "string"}, CONTEXT)]
    assert json.loads((tmp_path / "ws" / "answer.json").read_text())["answer"] == "合意"


def test_14_4_context_is_recorded_and_replayed(tmp_path: Path) -> None:
    log = tmp_path / "run.jsonl"
    recorded = _ask_context(tmp_path / "rec", _ContextRecordingUser(), Recorder(log, mode="record"))
    assert recorded.status is RunStatus.COMPLETED
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    user_entries = [e for e in entries if e["kind"] == "user"]
    assert user_entries and user_entries[0]["request"]["context"] == CONTEXT
    replayed = _ask_context(tmp_path / "rep", None, Recorder(log, mode="replay"))
    assert replayed.status is RunStatus.COMPLETED


def test_14_4_replay_with_a_different_context_is_a_mismatch(tmp_path: Path) -> None:
    """context は記録の要求の一部。違う context で再生すると ReplayMismatch（検証役 f5-release の探針）。"""
    from htf.runtime import ReplayMismatch

    log = tmp_path / "run.jsonl"
    _ask_context(tmp_path / "rec", _ContextRecordingUser(), Recorder(log, mode="record"))

    class _OtherContext(_AskWithContext):
        def run(self, ctx: StageContext) -> None:
            answer = ctx.user.ask(
                "見送りに合意しますか?", schema={"type": "string"}, context={"reason": "別"}
            )
            (ctx.workspace / "answer.json").write_text(
                json.dumps({"outcome": "goal", "answer": answer})
            )

    registry = DictMetricRegistry({"answer_exists": lambda s: (s.files / "answer.json").is_file()})
    workflow = load_workflow(
        FIXTURES / "workflows" / "ask_context.yaml", metric_names=registry.names()
    )
    bindings = Bindings(
        bodies={("ask_context", "ask"): _OtherContext()},
        registry=registry,
        classifier=MarkerClassifier(),
        user=None,
        human=ScriptedHuman([]),
    )
    with pytest.raises(ReplayMismatch):
        Runner(
            workflow, bindings, workspace=tmp_path / "rep", recorder=Recorder(log, mode="replay")
        ).run()


def test_14_4_test_doubles_accept_context() -> None:
    assert QueueUserIO(["x"]).ask("q", context={"a": 1}) == "x"
    with pytest.raises(WaitingForUser):
        DeferringUserIO().ask("q", schema=None, context={"a": 1})


# --- 14.5: 状態文書 ---


def _toy_run(toy: ModuleType, tmp_path: Path, **runner_kwargs):  # noqa: ANN003, ANN202
    scenario = toy.harness.load_scenario(SCENARIOS / "happy.yaml")
    workflow = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    human = ScriptedHuman([Abort()]) if runner_kwargs else ScriptedHuman([])
    bindings = toy.harness.make_bindings(scenario, human=human)
    return workflow, Runner(workflow, bindings, workspace=tmp_path / "ws", **runner_kwargs).run()


def test_14_5b_writes_come_before_reads_in_the_projection(toy: ModuleType, tmp_path: Path) -> None:
    workflow, result = _toy_run(toy, tmp_path)
    assert result.status is RunStatus.COMPLETED
    draft_end = next(s for s in result.end_snapshots if s.stage_id == "draft")
    doc = project(workflow.stage("draft"), draft_end, tmp_path / "ws")
    assert doc.index("## memory_in") < doc.index("## writes") < doc.index("## reads")
    assert "### draft.md" in doc.split("## reads")[0]


def test_14_5b_marker_classifier_reads_only_the_writes_block() -> None:
    document = (
        "# stage: x\n## memory_in\n## writes\n### a.json\n```\n"
        '{"outcome": "goal"}\n```\n## reads\n### b.json\n```\n{"outcome": "bad"}\n```\n'
    )
    options = [ClassOption("goal", "g"), ClassOption("bad", "b"), ClassOption("unknown", "u")]
    assert MarkerClassifier().classify(document, options).option_id == "goal"


def test_14_5b_marker_classifier_ignores_markdown_headers_inside_written_files() -> None:
    """成果物の Markdown の見出し（`## 追加` など）で writes 節を切らない。

    software factory の release（CHANGELOG.md が approval.json より前に並ぶ）で見つけた退行の再現。
    """
    document = (
        "# stage: release\n## memory_in\n## writes\n### release/CHANGELOG.md\n```\n"
        "# textkit 0.2.0\n\n## 追加\n\n- R1\n```\n"
        '### release/approval.json\n```\n{"outcome": "goal"}\n```\n'
        '## reads\n### requirements.json\n```\n{"outcome": "bad"}\n```\n'
    )
    options = [ClassOption("goal", "g"), ClassOption("bad", "b"), ClassOption("unknown", "u")]
    assert MarkerClassifier().classify(document, options).option_id == "goal"


def test_14_5a_whole_document_cap(toy: ModuleType, tmp_path: Path) -> None:
    workflow, result = _toy_run(toy, tmp_path)
    draft_end = next(s for s in result.end_snapshots if s.stage_id == "draft")
    full = project(workflow.stage("draft"), draft_end, tmp_path / "ws")
    capped = project(workflow.stage("draft"), draft_end, tmp_path / "ws", max_document_chars=200)
    assert len(full) > 200
    assert capped.startswith(full[:200]) and "文書全体" in capped and "文字省略" in capped
    assert len(capped) < len(full)


def test_14_5a_runner_applies_the_document_cap(toy: ModuleType, tmp_path: Path) -> None:
    _workflow, result = _toy_run(toy, tmp_path, max_document_chars=60)
    assert result.status is RunStatus.ABORTED  # 印が切り落とされ collect が unknown
    record = result.evaluations[0]
    assert record.stage_id == "collect" and record.document is not None
    assert len(record.document) <= 60 + 40 and "文書全体" in record.document
