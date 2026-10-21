"""参照ランタイム: 三操作（ReferenceRuntime）と制御ループ（Runner）。

Runner はワークフロー定義だけから遷移を駆動する（CONTRACT 第 6 節の 7 種）。
  next / rollback_within_phase / rollback_across_phase / escalate_unknown / escalate_max_exceeded /
  suspend_resume / subworkflow_aggregate
中断は「回答列を累積して開始時スナップショットから再実行」（決定 #4）。子 run は人間へ行かず親の集約へ
（決定 #9 (b)）。人間の操作（決定 #3）は辺の max を消費しない。
"""

from __future__ import annotations

import shutil
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from htf.contract import (
    Abort,
    Carry,
    ChildOutcome,
    Classifier,
    ContinueAsGoal,
    ContractViolation,
    Escalation,
    HumanDecider,
    JsonValue,
    LLMClient,
    MetricRegistry,
    Rerun,
    Resolution,
    RollbackTo,
    Snapshot,
    StageBody,
    TransitionKind,
    UserIO,
    Verdict,
    VerdictKind,
    WaitingForUser,
)

from .checkpoint import META_DIR, SnapshotStore, fingerprint, out_of_scope_changes
from .context import RunContext
from .model import UNKNOWN, MetricError, Phase, Stage, Workflow
from .oracle import aggregate_children, evaluate_metrics, evaluate_stage
from .recorder import RecordedClassifier, RecordedLLM, RecordedUserIO, Recorder

DEFAULT_THRESHOLD = 0.5


@dataclass
class Bindings:
    """ハーネスが提供するもの。bodies の鍵は (workflow 名, stage id)。"""

    bodies: Mapping[tuple[str, str], StageBody]
    registry: MetricRegistry
    classifier: Classifier | None
    user: UserIO | None = None
    llm: LLMClient | None = None
    human: HumanDecider | None = None


class RunStatus(StrEnum):
    COMPLETED = "completed"
    ABORTED = "aborted"
    SUSPENDED = "suspended"
    ESCALATED = "escalated"  # 子 run だけ: 人間へ行かず親の集約へ渡す


@dataclass(frozen=True)
class TransitionRecord:
    kind: TransitionKind
    stage_id: str
    to_stage: str | None
    verdict: Verdict | None
    note: str = ""


@dataclass(frozen=True)
class GateEvent:
    phase_id: str
    event: str  # passed | failed | invalidated


@dataclass(frozen=True)
class PendingQuestion:
    stage_id: str
    question: str
    schema: dict[str, JsonValue] | None


@dataclass
class RunResult:
    status: RunStatus
    trace: list[TransitionRecord]
    gates: list[GateEvent]
    pending: PendingQuestion | None
    memory: dict[str, JsonValue]
    start_snapshots: list[Snapshot]
    end_snapshots: list[Snapshot]
    escalations: list[Escalation]
    resolutions: list[Resolution]
    edge_counts: dict[tuple[str, str], int]
    child_outcomes: dict[str, list[list[ChildOutcome]]] = field(default_factory=dict)
    child_outcome: ChildOutcome | None = None  # 子 run として終わった時の、この run の終わり方


class _QueuedUserIO(UserIO):
    """累積した回答列を先に返し、尽きたら束縛された UserIO に聞く（無ければ中断）。"""

    def __init__(self, answers: Sequence[JsonValue], fallback: UserIO | None) -> None:
        self._answers = list(answers)
        self._fallback = fallback

    def ask(self, question: str, *, schema: dict[str, JsonValue] | None = None) -> JsonValue:
        if self._answers:
            return self._answers.pop(0)
        if self._fallback is None:
            raise WaitingForUser(question, schema)
        return self._fallback.ask(question, schema=schema)


class ReferenceRuntime:
    """三操作 + 開始時スナップショットの取得。契約適合テストの対象。"""

    def __init__(
        self,
        workflow: Workflow,
        bindings: Bindings,
        *,
        workspace: Path,
        threshold: float = DEFAULT_THRESHOLD,
        recorder: Recorder | None = None,
        strict_writes: bool = True,
        store_root: Path | None = None,
    ) -> None:
        self.workflow = workflow
        self.bindings = bindings
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.threshold = threshold
        self.recorder = recorder
        self.strict_writes = strict_writes
        self.store = SnapshotStore(
            store_root or self.workspace / META_DIR / "snapshots",
            workflow=workflow.name,
            version=workflow.version,
        )
        if recorder is not None:
            self.classifier: Classifier | None = RecordedClassifier(bindings.classifier, recorder)
            self.llm: LLMClient | None = RecordedLLM(bindings.llm, recorder)
            self.user: UserIO | None = RecordedUserIO(bindings.user, recorder)
        else:
            self.classifier = bindings.classifier
            self.llm = bindings.llm
            self.user = bindings.user
        self.answers: dict[str, list[JsonValue]] = defaultdict(list)
        self.child_outcomes: dict[str, list[list[ChildOutcome]]] = defaultdict(list)

    # --- 開始時スナップショット ---

    def start(self, stage_id: str, memory: Mapping[str, JsonValue]) -> Snapshot:
        stage = self.workflow.stage(stage_id)
        return self.store.take(stage_id, "start", self.workspace, stage.artifacts.writes, memory)

    # --- 三操作 ---

    def run(self, stage_id: str, snapshot: Snapshot) -> Snapshot:
        stage = self.workflow.stage(stage_id)
        memory: dict[str, JsonValue] = dict(snapshot.memory)
        if stage.subworkflow is not None:
            self.child_outcomes[stage_id].append(self._run_children(stage, memory))
        body = self.bindings.bodies.get((self.workflow.name, stage_id))
        if body is None and stage.subworkflow is None:
            raise ContractViolation(
                f"ステージ ({self.workflow.name}, {stage_id}) に本体が束縛されていない"
            )
        if body is not None:
            before = fingerprint(self.workspace) if self.strict_writes else {}
            ctx = RunContext(
                stage,
                self.workspace,
                memory,
                user=_QueuedUserIO(self.answers[stage_id], self.user) if stage.user_input else None,
                llm=self.llm,
            )
            body.run(ctx)
            if self.strict_writes:
                stray = out_of_scope_changes(
                    before, fingerprint(self.workspace), stage.artifacts.writes
                )
                if stray:
                    raise ContractViolation(f"ステージ {stage_id!r} が writes 外に書いた: {stray}")
            memory.update(ctx.emitted)
        return self.store.take(stage_id, "end", self.workspace, stage.artifacts.writes, memory)

    def evaluate(self, stage_id: str, snapshot: Snapshot) -> Verdict:
        stage = self.workflow.stage(stage_id)
        if stage.subworkflow is not None:
            outcomes = self.child_outcomes[stage_id][-1] if self.child_outcomes[stage_id] else []
            return aggregate_children(stage, outcomes, snapshot, self.bindings.registry)
        if self.classifier is None:
            raise ContractViolation("Classifier が束縛されていない")
        return evaluate_stage(
            stage,
            snapshot,
            workspace=self.workspace,
            registry=self.bindings.registry,
            classifier=self.classifier,
            threshold=self.threshold,
        )

    def restore(self, snapshot: Snapshot) -> Snapshot:
        stage = self.workflow.stage(snapshot.stage_id)
        SnapshotStore.restore(snapshot, self.workspace, stage.artifacts.writes)
        return snapshot

    def overlay(self, snapshot: Snapshot, carry: Carry) -> Snapshot:
        stage = self.workflow.stage(snapshot.stage_id)
        return SnapshotStore.overlay(snapshot, carry, stage.artifacts.memory_in)

    # --- フェーズゲート（決定 #5）---

    def evaluate_gate(self, phase: Phase, memory: Mapping[str, JsonValue]) -> tuple[bool, str]:
        """フェーズの全ステージの writes の和をスナップショットにして集約述語を評価する。"""
        writes = [w for s in phase.stages for w in s.artifacts.writes]
        snapshot = self.store.take(phase.id, "end", self.workspace, writes, memory)
        try:
            ok, _values, failed = evaluate_metrics(phase.goal, snapshot, self.bindings.registry)
        except MetricError as e:
            return False, f"評価不能: {e}"
        return ok, ("" if ok else f"フェーズ {phase.id!r} の指標 {failed} が不成立")

    # --- 子 run（決定 #9 (b)）---

    def _run_children(self, stage: Stage, memory: Mapping[str, JsonValue]) -> list[ChildOutcome]:
        sub = stage.subworkflow
        assert sub is not None
        items = memory.get(sub.each)
        if not isinstance(items, list):
            raise ContractViolation(f"subworkflow.each {sub.each!r} の値がリストでない: {items!r}")
        for key in sub.pass_:
            if key not in memory:
                raise ContractViolation(f"subworkflow.pass の鍵 {key!r} が memory に無い")
        child_bindings = Bindings(
            bodies=self.bindings.bodies,
            registry=self.bindings.registry,
            classifier=self.bindings.classifier,
            user=self.bindings.user,
            llm=self.bindings.llm,
            human=None,
        )
        outcomes: list[ChildOutcome] = []
        for i, item in enumerate(items):
            child_ws = self.workspace / sub.workspace / str(i)
            if child_ws.exists():
                shutil.rmtree(child_ws)
            initial = {sub.item_as: item, **{k: memory[k] for k in sub.pass_}}
            child = Runner(
                sub.child,
                child_bindings,
                workspace=child_ws,
                threshold=self.threshold,
                recorder=self.recorder,
                strict_writes=self.strict_writes,
                initial_memory=initial,
            )
            result = child.run()
            if result.status is RunStatus.COMPLETED:
                outcomes.append(ChildOutcome(index=i, kind="goal"))
            elif result.status is RunStatus.ESCALATED and result.child_outcome is not None:
                outcomes.append(
                    ChildOutcome(
                        index=i,
                        kind=result.child_outcome.kind,
                        stage=result.child_outcome.stage,
                        state=result.child_outcome.state,
                    )
                )
            else:
                raise ContractViolation(f"子 run {i} が想定外の状態で終わった: {result.status}")
        return outcomes


class Runner:
    def __init__(
        self,
        workflow: Workflow,
        bindings: Bindings,
        *,
        workspace: Path,
        threshold: float = DEFAULT_THRESHOLD,
        recorder: Recorder | None = None,
        strict_writes: bool = True,
        initial_memory: Mapping[str, JsonValue] | None = None,
    ) -> None:
        self.workflow = workflow
        self.rt = ReferenceRuntime(
            workflow,
            bindings,
            workspace=workspace,
            threshold=threshold,
            recorder=recorder,
            strict_writes=strict_writes,
        )
        self.human = bindings.human
        self.memory: dict[str, JsonValue] = dict(initial_memory or {})
        self.pos = 0
        self.counts: Counter[tuple[str, str]] = Counter()
        self.gates_passed: list[str] = []
        self.start_by_stage: dict[str, Snapshot] = {}
        self.trace: list[TransitionRecord] = []
        self.gates: list[GateEvent] = []
        self.start_snapshots: list[Snapshot] = []
        self.end_snapshots: list[Snapshot] = []
        self.escalations: list[Escalation] = []
        self.resolutions: list[Resolution] = []
        self.pending: PendingQuestion | None = None
        self._status: RunStatus | None = None
        self._child_outcome: ChildOutcome | None = None
        self._resume_from_start = False

    # --- 公開 API ---

    def run(self) -> RunResult:
        return self._loop()

    def resume(self, answer: JsonValue) -> RunResult:
        if self.pending is None:
            raise ContractViolation("中断していないので再開できない")
        stage_id = self.pending.stage_id
        self.rt.answers[stage_id].append(answer)
        self.trace.append(TransitionRecord(TransitionKind.SUSPEND_RESUME, stage_id, stage_id, None))
        self.pending = None
        self._status = None
        self._resume_from_start = True
        return self._loop()

    # --- 制御ループ ---

    def _loop(self) -> RunResult:
        stages = self.workflow.stages
        while self._status is None and self.pos < len(stages):
            stage = stages[self.pos]
            if self._resume_from_start:
                self._reset_to_start(stage)
                self._resume_from_start = False
            start = self.rt.start(stage.id, self.memory)
            self.start_by_stage[stage.id] = start
            self.start_snapshots.append(start)
            try:
                end = self.rt.run(stage.id, start)
            except WaitingForUser as w:
                self.pending = PendingQuestion(stage.id, w.question, w.schema)
                self._status = RunStatus.SUSPENDED
                break
            self.memory = dict(end.memory)
            self.end_snapshots.append(end)
            verdict = self.rt.evaluate(stage.id, end)
            if stage.subworkflow is not None:
                self.trace.append(
                    TransitionRecord(TransitionKind.SUBWORKFLOW_AGGREGATE, stage.id, None, verdict)
                )
            self._transition(stage, end, verdict)
        if self._status is None:
            self._status = RunStatus.COMPLETED
        return self._result()

    def _reset_to_start(self, stage: Stage) -> None:
        start = self.start_by_stage.get(stage.id)
        if start is not None:
            self.rt.restore(start)
            self.memory = dict(start.memory)

    def _transition(self, stage: Stage, end: Snapshot, verdict: Verdict) -> None:
        if verdict.kind is VerdictKind.GOAL:
            if self.workflow.is_last_in_phase(stage.id):
                phase = self.workflow.phase(stage.id)
                ok, reason = self.rt.evaluate_gate(phase, self.memory)
                if ok:
                    self.gates.append(GateEvent(phase.id, "passed"))
                    if phase.id not in self.gates_passed:
                        self.gates_passed.append(phase.id)
                else:
                    self.gates.append(GateEvent(phase.id, "failed"))
                    gate_verdict = Verdict(
                        VerdictKind.UNKNOWN, decided_by="quantitative", reason=reason
                    )
                    self.trace.append(
                        TransitionRecord(
                            TransitionKind.ESCALATE_UNKNOWN, stage.id, None, gate_verdict
                        )
                    )
                    self._escalate(stage, end, gate_verdict, cause="unknown")
                    return
            next_id = (
                self.workflow.stages[self.pos + 1].id
                if self.pos + 1 < len(self.workflow.stages)
                else None
            )
            self.trace.append(TransitionRecord(TransitionKind.NEXT, stage.id, next_id, verdict))
            self.pos += 1
            return

        if verdict.kind is VerdictKind.END_STATE:
            assert verdict.state is not None
            rb = stage.rollback_for(verdict.state)
            if rb is None:  # 検査器が保証するので起きない
                raise ContractViolation(f"end_state {verdict.state!r} に戻り先が無い")
            edge = (stage.id, verdict.state)
            self.counts[edge] += 1
            if self.counts[edge] > rb.max:
                self.trace.append(
                    TransitionRecord(
                        TransitionKind.ESCALATE_MAX_EXCEEDED,
                        stage.id,
                        None,
                        verdict,
                        note=f"辺 {edge} が max {rb.max} を超えた",
                    )
                )
                self._escalate(
                    stage, end, verdict, cause="max_exceeded", edge=(verdict.state, rb.stage)
                )
                return
            carry = {k: self.memory[k] for k in rb.carry if k in self.memory}
            self._rollback(stage, rb.stage, carry, verdict, note="")
            return

        self.trace.append(
            TransitionRecord(TransitionKind.ESCALATE_UNKNOWN, stage.id, None, verdict)
        )
        cause = "child_unresolved" if verdict.decided_by == "aggregate" else "unknown"
        self._escalate(stage, end, verdict, cause=cause)

    def _rollback(
        self,
        stage: Stage,
        target_id: str,
        carry: dict[str, JsonValue],
        verdict: Verdict,
        *,
        note: str,
    ) -> None:
        target_index = self.workflow.index_of(target_id)
        if target_index >= self.workflow.index_of(stage.id):
            raise ContractViolation(
                f"戻り先 {target_id!r} は {stage.id!r} より前でなければならない"
            )
        same_phase = self.workflow.phase_of(target_id) == self.workflow.phase_of(stage.id)
        kind = (
            TransitionKind.ROLLBACK_WITHIN_PHASE
            if same_phase
            else TransitionKind.ROLLBACK_ACROSS_PHASE
        )
        self.trace.append(TransitionRecord(kind, stage.id, target_id, verdict, note=note))
        if not same_phase:
            target_phase_index = self.workflow.phase_index_of(target_id)
            for phase in self.workflow.phases[target_phase_index:]:
                if phase.id in self.gates_passed:
                    self.gates_passed.remove(phase.id)
                    self.gates.append(GateEvent(phase.id, "invalidated"))
        start = self.start_by_stage[target_id]
        restored = self.rt.restore(start)
        overlaid = self.rt.overlay(restored, Carry(carry))
        self.memory = dict(overlaid.memory)
        self.pos = target_index

    def _escalate(
        self,
        stage: Stage,
        end: Snapshot,
        verdict: Verdict,
        *,
        cause: str,
        edge: tuple[str, str] | None = None,
    ) -> None:
        escalation = Escalation(stage.id, verdict, cause, end, edge)  # type: ignore[arg-type]
        self.escalations.append(escalation)
        if self.human is None:
            # 子 run: 人間へ行かず、親の集約へ（CONTRACT 第 7 節 2）
            if cause == "max_exceeded":
                self._child_outcome = ChildOutcome(
                    index=-1, kind="stuck", stage=stage.id, state=verdict.state
                )
            else:
                self._child_outcome = ChildOutcome(
                    index=-1, kind="unknown", stage=stage.id, state=UNKNOWN
                )
            self._status = RunStatus.ESCALATED
            return
        resolution = self.human.resolve(escalation)
        self.resolutions.append(resolution)
        match resolution:
            case Rerun():
                self._reset_to_start(stage)
            case RollbackTo(stage=target_id, carry=carry):
                target = self.workflow.stage(target_id)
                undeclared = sorted(set(carry) - set(target.artifacts.memory_in))
                if undeclared:
                    raise ContractViolation(
                        f"人間の rollback_to: 戻り先 {target_id!r} の memory_in に無い鍵 {undeclared}"
                    )
                self._rollback(stage, target_id, dict(carry), verdict, note="human")
            case ContinueAsGoal(note=note):
                self._transition(
                    stage, end, Verdict(VerdictKind.GOAL, decided_by="human", reason=note)
                )
            case Abort():
                self._status = RunStatus.ABORTED
            case _:
                raise ContractViolation(f"未知の解決 {resolution!r}")

    def _result(self) -> RunResult:
        assert self._status is not None
        return RunResult(
            status=self._status,
            trace=list(self.trace),
            gates=list(self.gates),
            pending=self.pending,
            memory=dict(self.memory),
            start_snapshots=list(self.start_snapshots),
            end_snapshots=list(self.end_snapshots),
            escalations=list(self.escalations),
            resolutions=list(self.resolutions),
            edge_counts={k: v for k, v in self.counts.items() if v},
            child_outcomes={k: list(v) for k, v in self.rt.child_outcomes.items()},
            child_outcome=self._child_outcome,
        )
