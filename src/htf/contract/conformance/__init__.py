"""契約適合テスト（CONTRACT 第 8 節）。任意の Runtime 実装が通すべきもの。

対象は三操作（run / evaluate / restore + overlay）と開始時スナップショットの取得（start）だけ。
制御ループ（遷移、max、フェーズゲート、中断、子 run の集約）は参照ランタイムの振る舞いで、
htf.testing.harness と各ハーネスのテストで検査する（ADR-008: 自前のランタイムでも契約の判定はこのテストだけ）。

使い方（ハーネス側の tests/）:

    import pytest
    from htf.contract.conformance import ConformanceRuntime, ConformanceSuite

    class TestMyRuntime(ConformanceSuite):
        @pytest.fixture
        def make_runtime(self, tmp_path):
            def factory(workflow_path, bodies, registry, classifier, user) -> ConformanceRuntime:
                ...  # 自前のランタイムを、この定義・本体・レジストリ・分類器・UserIO で組み立てて返す
            return factory

定義は同じディレクトリの conformance.yaml（seed → probe の 2 ステージ）。本体とレジストリはこのモジュールが
用意し、ランタイムには束縛の仕方だけを求める。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

import pytest

from htf.contract.interfaces import (
    Classifier,
    Metric,
    MetricRegistry,
    StageBody,
    StageContext,
    UserIO,
)
from htf.contract.types import (
    Carry,
    Classification,
    ClassOption,
    ContractViolation,
    JsonValue,
    Snapshot,
    Verdict,
    VerdictKind,
)

WORKFLOW_PATH = Path(__file__).parent / "conformance.yaml"
NAME = "conformance"


class ConformanceRuntime(Protocol):
    """三操作 + 開始時スナップショットの取得。"""

    def start(self, stage_id: str, memory: Mapping[str, JsonValue]) -> Snapshot: ...

    def run(self, stage_id: str, snapshot: Snapshot) -> Snapshot: ...

    def evaluate(self, stage_id: str, snapshot: Snapshot) -> Verdict: ...

    def restore(self, snapshot: Snapshot) -> Snapshot: ...

    def overlay(self, snapshot: Snapshot, carry: Carry) -> Snapshot: ...


class RuntimeFactory(Protocol):
    def __call__(
        self,
        workflow_path: Path,
        bodies: Mapping[tuple[str, str], StageBody],
        registry: MetricRegistry,
        classifier: Classifier,
        user: UserIO | None,
    ) -> ConformanceRuntime: ...


# --- このモジュールが用意する本体・レジストリ・分類器 ---


class SeedBody:
    def run(self, ctx: StageContext) -> None:
        (ctx.workspace / "in.txt").write_text("hello", encoding="utf-8")
        ctx.emit("k_in", "from seed")


class ProbeBody:
    """mode で振る舞いを変える探針。"""

    def __init__(self, mode: str = "ok", value: int = 1) -> None:
        self.mode = mode
        self.value = value

    def run(self, ctx: StageContext) -> None:
        ws = ctx.workspace
        if self.mode == "write_outside":
            (ws / "stray.txt").write_text("x", encoding="utf-8")
            return
        if self.mode == "emit_undeclared":
            ctx.emit("not_declared", 1)
            return
        if self.mode == "use_user":
            ctx.user.ask("使ってはいけない")
            return
        if self.mode == "dump_memory":
            (ws / "out.txt").write_text(
                json.dumps(dict(ctx.memory), sort_keys=True), encoding="utf-8"
            )
            return
        assert (ws / "in.txt").read_text(encoding="utf-8") == "hello"
        (ws / "out.txt").write_text(str(self.value), encoding="utf-8")
        (ws / "out").mkdir(exist_ok=True)
        (ws / "out" / "x.txt").write_text("x", encoding="utf-8")
        ctx.emit("k_out", ["probe"])


class ConformanceRegistry:
    def __init__(self, *, error: bool = False) -> None:
        self.error = error

    def names(self) -> list[str]:
        return ["in_exists", "probe_value"]

    def resolve(self, name: str) -> Metric:
        if name == "in_exists":
            return lambda s: (s.files / "in.txt").is_file()
        if name == "probe_value":
            if self.error:

                def boom(_s: Snapshot) -> JsonValue:
                    raise RuntimeError("指標が落ちた")

                return boom
            return lambda s: int((s.files / "out.txt").read_text(encoding="utf-8"))
        raise KeyError(name)


class FixedClassifier:
    def __init__(self, option_id: str, confidence: float) -> None:
        self.option_id = option_id
        self.confidence = confidence
        self.seen: list[list[ClassOption]] = []

    def classify(self, document: str, options: Sequence[ClassOption]) -> Classification:
        self.seen.append(list(options))
        return Classification(self.option_id, self.confidence)


class _AnsweringUser:
    def ask(self, question: str, *, schema: dict[str, JsonValue] | None = None) -> JsonValue:
        return "答え"


# --- スイート ---


class ConformanceSuite:
    """継承して make_runtime フィクスチャを与える。"""

    @pytest.fixture
    def make_runtime(self) -> RuntimeFactory:  # pragma: no cover - 継承側が与える
        raise NotImplementedError("make_runtime フィクスチャを継承側で定義する")

    def _rt(
        self,
        make_runtime: RuntimeFactory,
        *,
        probe: ProbeBody | None = None,
        registry: MetricRegistry | None = None,
        classifier: Classifier | None = None,
        user: UserIO | None = None,
    ) -> ConformanceRuntime:
        bodies: dict[tuple[str, str], StageBody] = {
            (NAME, "seed"): SeedBody(),
            (NAME, "probe"): probe or ProbeBody(),
        }
        return make_runtime(
            WORKFLOW_PATH,
            bodies,
            registry or ConformanceRegistry(),
            classifier or FixedClassifier("goal", 0.9),
            user,
        )

    @staticmethod
    def _seed(rt: ConformanceRuntime) -> Snapshot:
        return rt.run("seed", rt.start("seed", {}))

    def _probe(
        self, rt: ConformanceRuntime, memory: Mapping[str, JsonValue] | None = None
    ) -> tuple[Snapshot, Snapshot]:
        seed_end = self._seed(rt)
        start = rt.start("probe", memory if memory is not None else seed_end.memory)
        return start, rt.run("probe", start)

    # run

    def test_run_takes_end_snapshot_of_writes_and_emitted_memory(
        self, make_runtime: RuntimeFactory
    ) -> None:
        rt = self._rt(make_runtime)
        end = self._seed(rt)
        assert end.moment == "end" and end.stage_id == "seed"
        assert (end.files / "in.txt").read_text(encoding="utf-8") == "hello"
        assert end.memory["k_in"] == "from seed"

    def test_run_copies_only_the_writes_scope(self, make_runtime: RuntimeFactory) -> None:
        rt = self._rt(make_runtime)
        _start, end = self._probe(rt)
        assert (end.files / "out.txt").is_file()
        assert (end.files / "out" / "x.txt").is_file()
        assert not (end.files / "in.txt").exists(), (
            "reads は probe の writes ではないので複製しない"
        )
        assert end.memory["k_out"] == ["probe"] and end.memory["k_in"] == "from seed"

    def test_run_rejects_write_outside_declared_scope(self, make_runtime: RuntimeFactory) -> None:
        rt = self._rt(make_runtime, probe=ProbeBody("write_outside"))
        with pytest.raises(ContractViolation):
            self._probe(rt)

    def test_run_rejects_undeclared_emit(self, make_runtime: RuntimeFactory) -> None:
        rt = self._rt(make_runtime, probe=ProbeBody("emit_undeclared"))
        with pytest.raises(ContractViolation):
            self._probe(rt)

    def test_run_rejects_user_io_in_stage_without_declaration(
        self, make_runtime: RuntimeFactory
    ) -> None:
        rt = self._rt(make_runtime, probe=ProbeBody("use_user"), user=_AnsweringUser())
        with pytest.raises(ContractViolation):
            self._probe(rt)

    def test_memory_view_is_limited_to_memory_in(self, make_runtime: RuntimeFactory) -> None:
        rt = self._rt(make_runtime, probe=ProbeBody("dump_memory"))
        _start, end = self._probe(rt, memory={"k_in": "x", "stray": 1})
        assert json.loads((end.files / "out.txt").read_text(encoding="utf-8")) == {"k_in": "x"}

    # evaluate（CONTRACT 第 4 節の順序）

    def test_evaluate_goal_when_metrics_pass_and_classifier_goal(
        self, make_runtime: RuntimeFactory
    ) -> None:
        rt = self._rt(make_runtime)
        _start, end = self._probe(rt)
        verdict = rt.evaluate("probe", end)
        assert verdict.kind is VerdictKind.GOAL

    def test_evaluate_unknown_when_metric_raises(self, make_runtime: RuntimeFactory) -> None:
        rt = self._rt(make_runtime, registry=ConformanceRegistry(error=True))
        _start, end = self._probe(rt)
        verdict = rt.evaluate("probe", end)
        assert verdict.kind is VerdictKind.UNKNOWN and verdict.decided_by == "quantitative"

    def test_evaluate_metrics_failure_overrides_classifier_goal(
        self, make_runtime: RuntimeFactory
    ) -> None:
        rt = self._rt(
            make_runtime, probe=ProbeBody(value=2), classifier=FixedClassifier("goal", 0.9)
        )
        _start, end = self._probe(rt)
        verdict = rt.evaluate("probe", end)
        assert verdict.kind is VerdictKind.UNKNOWN and verdict.decided_by == "quantitative"

    def test_evaluate_end_state_from_classifier(self, make_runtime: RuntimeFactory) -> None:
        rt = self._rt(
            make_runtime, probe=ProbeBody(value=2), classifier=FixedClassifier("bad", 0.9)
        )
        _start, end = self._probe(rt)
        verdict = rt.evaluate("probe", end)
        assert verdict.kind is VerdictKind.END_STATE and verdict.state == "bad"

    def test_evaluate_unknown_below_threshold(self, make_runtime: RuntimeFactory) -> None:
        rt = self._rt(
            make_runtime, probe=ProbeBody(value=2), classifier=FixedClassifier("bad", 0.1)
        )
        _start, end = self._probe(rt)
        verdict = rt.evaluate("probe", end)
        assert verdict.kind is VerdictKind.UNKNOWN and verdict.decided_by == "threshold"

    def test_classifier_receives_goal_and_end_state_descriptions_verbatim(
        self, make_runtime: RuntimeFactory
    ) -> None:
        classifier = FixedClassifier("goal", 0.9)
        rt = self._rt(make_runtime, classifier=classifier)
        _start, end = self._probe(rt)
        rt.evaluate("probe", end)
        options = classifier.seen[-1]
        assert [o.id for o in options] == ["goal", "bad", "unknown"]
        assert options[0].description == "out.txt の値が 1 である"
        assert options[1].description == "out.txt の値が 1 でない"

    # restore + overlay

    def test_restore_returns_workspace_to_start(self, make_runtime: RuntimeFactory) -> None:
        rt = self._rt(make_runtime)
        start, end = self._probe(rt)
        assert (end.files / "out.txt").is_file()
        rt.restore(start)
        again = rt.start("probe", start.memory)
        assert not (again.files / "out.txt").exists()
        assert not (again.files / "out").exists()
        assert again.memory == start.memory

    def test_overlay_merges_declared_key(self, make_runtime: RuntimeFactory) -> None:
        rt = self._rt(make_runtime)
        start = rt.start("probe", {"k_in": "a"})
        overlaid = rt.overlay(start, Carry({"k_in": "b"}))
        assert overlaid.memory["k_in"] == "b" and overlaid.stage_id == "probe"

    def test_overlay_rejects_undeclared_key(self, make_runtime: RuntimeFactory) -> None:
        rt = self._rt(make_runtime)
        start = rt.start("probe", {"k_in": "a"})
        with pytest.raises(ContractViolation):
            rt.overlay(start, Carry({"nope": 1}))


__all__ = [
    "NAME",
    "WORKFLOW_PATH",
    "ConformanceRegistry",
    "ConformanceRuntime",
    "ConformanceSuite",
    "FixedClassifier",
    "ProbeBody",
    "RuntimeFactory",
    "SeedBody",
]
