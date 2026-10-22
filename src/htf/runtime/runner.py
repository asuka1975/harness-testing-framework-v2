"""参照ランタイム: 三操作（ReferenceRuntime）と制御ループ（Runner）。

Runner はワークフロー定義だけから遷移を駆動する（CONTRACT 第 6 節の 7 種）。
  next / rollback_within_phase / rollback_across_phase / escalate_unknown / escalate_max_exceeded /
  suspend_resume / subworkflow_aggregate
中断は「回答列を累積して開始時スナップショットから再実行」（決定 #4）。子 run は人間へ行かず親の集約へ
（決定 #9 (b)）。人間の操作（決定 #3）は辺の max を消費しない。
"""

from __future__ import annotations

import dataclasses
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
    Classification,
    Classifier,
    ClassOption,
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
from .oracle import aggregate_children, class_options, evaluate_metrics, evaluate_stage_detailed
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
    note: str = ""  # "human": 不成立のゲートを人間が ContinueAsGoal で通した


@dataclass(frozen=True)
class EvaluationRecord:
    """評価のたびに runtime が残す記録。トリアージ、コーパス、分布の集計はここから作る。

    document / classification は分類器を呼んだ時だけ（子を持つステージの集約や評価不能では None）。
    carry_in は進入時に受け取った carry、carry_out は end_state の時に戻り先へ運ぶ carry（代表の鍵の既定）。
    """

    workflow: str
    stage_id: str
    entry: int  # この run でのそのステージの進入回数（1 から。中断からの再開は数えない）
    verdict: Verdict
    document: str | None
    options: list[ClassOption]
    classification: Classification | None
    carry_in: dict[str, JsonValue]
    carry_out: dict[str, JsonValue]
    injected: bool = False

    @property
    def cls(self) -> str:
        """分類の名前: goal / <end_state id> / unknown。"""
        if self.verdict.kind is VerdictKind.GOAL:
            return "goal"
        if self.verdict.kind is VerdictKind.END_STATE:
            assert self.verdict.state is not None
            return self.verdict.state
        return UNKNOWN

    @property
    def entry_kind(self) -> str:
        return "first" if self.entry == 1 else "reentry"


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
    # 子を持つステージ id → 進入ごと → 子 run ごとの RunResult（子の内部の遷移とスナップショット）
    child_results: dict[str, list[list[RunResult]]] = field(default_factory=dict)
    evaluations: list[EvaluationRecord] = field(default_factory=list)


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
        else:
            self.classifier = bindings.classifier
            self.llm = bindings.llm
        self.answers: dict[str, list[JsonValue]] = defaultdict(list)
        self.child_outcomes: dict[str, list[list[ChildOutcome]]] = defaultdict(list)
        self.child_results: dict[str, list[list[RunResult]]] = defaultdict(list)
        self.evaluations: list[EvaluationRecord] = []
        self.entry_counts: Counter[str] = Counter()  # Runner が進入のたびに増やす
        self.inject: dict[
            tuple[str, str, int], Verdict
        ] = {}  # Runner から渡される。子 run にも引き継ぐ
        # ステージ id → そのステージへ carry で運ばれうる鍵（戻り先として参照する rollback の carry の和）
        self._carry_in_keys: dict[str, set[str]] = defaultdict(set)
        for s in workflow.stages:
            for rb in s.rollback:
                self._carry_in_keys[rb.stage].update(rb.carry)

    def _user_for(self, stage: Stage) -> UserIO | None:
        """累積した回答列 → 束縛された UserIO の順に答える。recorder は本体が受け取った回答を記録する
        （resume 由来の回答も含む。中断した試行の記録は破棄されるので、回答は一度ずつ残る）。"""
        if not stage.user_input:
            return None
        queued = _QueuedUserIO(self.answers[stage.id], self.bindings.user)
        if self.recorder is not None:
            return RecordedUserIO(queued, self.recorder)
        return queued

    # --- 開始時スナップショット ---

    def start(self, stage_id: str, memory: Mapping[str, JsonValue]) -> Snapshot:
        stage = self.workflow.stage(stage_id)
        return self.store.take(stage_id, "start", self.workspace, stage.artifacts.writes, memory)

    # --- 三操作 ---

    def run(self, stage_id: str, snapshot: Snapshot) -> Snapshot:
        """一回の試行。中断（WaitingForUser）や例外で終わった試行の記録は破棄する。"""
        if self.recorder is not None:
            self.recorder.begin_attempt()
        try:
            end = self._run_attempt(stage_id, snapshot)
        except BaseException:
            if self.recorder is not None:
                self.recorder.discard_attempt()
            raise
        if self.recorder is not None:
            self.recorder.commit_attempt()
        return end

    def _run_attempt(self, stage_id: str, snapshot: Snapshot) -> Snapshot:
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
                user=self._user_for(stage),
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
        document: str | None = None
        classification: Classification | None = None
        if stage.subworkflow is not None:
            outcomes = self.child_outcomes[stage_id][-1] if self.child_outcomes[stage_id] else []
            verdict = aggregate_children(stage, outcomes, snapshot, self.bindings.registry)
        else:
            if self.classifier is None:
                raise ContractViolation("Classifier が束縛されていない")
            verdict, document, classification = evaluate_stage_detailed(
                stage,
                snapshot,
                workspace=self.workspace,
                registry=self.bindings.registry,
                classifier=self.classifier,
                threshold=self.threshold,
            )
        self.evaluations.append(self._record(stage, snapshot, verdict, document, classification))
        return verdict

    def _record(
        self,
        stage: Stage,
        snapshot: Snapshot,
        verdict: Verdict,
        document: str | None,
        classification: Classification | None,
        *,
        injected: bool = False,
    ) -> EvaluationRecord:
        carry_in = {
            k: snapshot.memory[k]
            for k in sorted(self._carry_in_keys[stage.id])
            if k in snapshot.memory
        }
        carry_out: dict[str, JsonValue] = {}
        if verdict.kind is VerdictKind.END_STATE and verdict.state is not None:
            rb = stage.rollback_for(verdict.state)
            if rb is not None:
                carry_out = {k: snapshot.memory[k] for k in rb.carry if k in snapshot.memory}
        return EvaluationRecord(
            workflow=self.workflow.name,
            stage_id=stage.id,
            entry=max(1, self.entry_counts[stage.id]),
            verdict=verdict,
            document=document,
            options=class_options(stage),
            classification=classification,
            carry_in=carry_in,
            carry_out=carry_out,
            injected=injected,
        )

    def replace_last_evaluation(self, stage: Stage, snapshot: Snapshot, verdict: Verdict) -> None:
        """注入: 直前の評価記録の Verdict を差し替える（記録には注入と残る）。"""
        last = self.evaluations[-1]
        self.evaluations[-1] = self._record(
            stage, snapshot, verdict, last.document, last.classification, injected=True
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
        # 前回の進入の子 run の作業ディレクトリを残さない（each のリストが短くなっても残骸が成果物に混ざらない）
        parent_dir = self.workspace / sub.workspace
        if parent_dir.exists():
            shutil.rmtree(parent_dir)
        parent_dir.mkdir(parents=True)
        outcomes: list[ChildOutcome] = []
        results: list[RunResult] = []
        for i, item in enumerate(items):
            child_ws = parent_dir / str(i)
            initial = {sub.item_as: item, **{k: memory[k] for k in sub.pass_}}
            child = Runner(
                sub.child,
                child_bindings,
                workspace=child_ws,
                threshold=self.threshold,
                recorder=self.recorder,
                strict_writes=self.strict_writes,
                initial_memory=initial,
                child=True,
                inject=self.inject,
            )
            try:
                result = child.run()
            except WaitingForUser as w:
                raise ContractViolation(
                    f"子ワークフロー {sub.child.name!r} のユーザー入出力は v1.0 では未対応（質問: {w.question!r}）"
                ) from w
            results.append(result)
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
            elif result.status is RunStatus.SUSPENDED and result.pending is not None:
                raise ContractViolation(
                    f"子ワークフロー {sub.child.name!r} のユーザー入出力は v1.0 では未対応"
                    f"（質問: {result.pending.question!r}）"
                )
            else:
                raise ContractViolation(f"子 run {i} が想定外の状態で終わった: {result.status}")
        self.child_results[stage.id].append(results)
        return outcomes


def _validate_inject(workflow: Workflow, inject: Mapping[tuple[str, str, int], Verdict]) -> None:
    known: set[tuple[str, str]] = set()
    stack = [workflow]
    while stack:
        wf = stack.pop()
        for s in wf.stages:
            known.add((wf.name, s.id))
            if s.subworkflow is not None:
                stack.append(s.subworkflow.child)
    for key, verdict in inject.items():
        if len(key) != 3 or (key[0], key[1]) not in known:
            raise ValueError(
                f"注入の鍵 {key!r} が定義に無い（(workflow 名, stage id, 進入回数) で指定する）"
            )
        if key[2] < 1:
            raise ValueError(f"注入の進入回数は 1 以上: {key!r}")
        if verdict.kind is VerdictKind.END_STATE:
            stage = next(
                s
                for wf in _descendants(workflow)
                for s in wf.stages
                if (wf.name, s.id) == (key[0], key[1])
            )
            if verdict.state not in stage.end_state_ids():
                raise ValueError(f"注入の end_state {verdict.state!r} はステージ {key[1]!r} に無い")


def _descendants(workflow: Workflow) -> list[Workflow]:
    out = [workflow]
    for s in workflow.stages:
        if s.subworkflow is not None:
            out.extend(_descendants(s.subworkflow.child))
    return out


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
        child: bool = False,
        inject: Mapping[tuple[str, str, int], Verdict] | None = None,
    ) -> None:
        self.workflow = workflow
        self._child = child  # 子 run: escalate は人間へ行かず ChildOutcome になる
        # 注入: (workflow 名, stage id, 進入回数) → その進入の評価結果を差し替える（E2E の「注入」。記録に残る。
        # Verdict だけを差し替え、成果物と memory は本体のまま。子 run にも同じ表が渡る）
        self.inject: dict[tuple[str, str, int], Verdict] = dict(inject or {})
        if not child:
            _validate_inject(workflow, self.inject)
        self.rt = ReferenceRuntime(
            workflow,
            bindings,
            workspace=workspace,
            threshold=threshold,
            recorder=recorder,
            strict_writes=strict_writes,
        )
        self.rt.inject = self.inject
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
            else:
                self.rt.entry_counts[stage.id] += 1
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
            injected = self.inject.get(
                (self.workflow.name, stage.id, self.rt.entry_counts[stage.id])
            )
            if injected is not None:
                verdict = dataclasses.replace(
                    injected, reason=f"注入（元の判定: {verdict.kind.value}）{injected.reason}"
                )
                self.rt.replace_last_evaluation(stage, end, verdict)
            if stage.subworkflow is not None:
                self.trace.append(
                    TransitionRecord(TransitionKind.SUBWORKFLOW_AGGREGATE, stage.id, None, verdict)
                )
            self._transition(stage, end, verdict)
        if self._status is None:
            self._status = RunStatus.COMPLETED
        if (
            not self._child
            and self.rt.recorder is not None
            and self._status in (RunStatus.COMPLETED, RunStatus.ABORTED)
        ):
            self.rt.recorder.finish()
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
                    self._escalate(
                        stage, end, gate_verdict, cause="phase_gate_failed", gate_phase=phase
                    )
                    return
            self._advance(stage, verdict)
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

    def _advance(self, stage: Stage, verdict: Verdict) -> None:
        next_id = (
            self.workflow.stages[self.pos + 1].id
            if self.pos + 1 < len(self.workflow.stages)
            else None
        )
        self.trace.append(TransitionRecord(TransitionKind.NEXT, stage.id, next_id, verdict))
        self.pos += 1

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
        gate_phase: Phase | None = None,
    ) -> None:
        escalation = Escalation(stage.id, verdict, cause, end, edge)  # type: ignore[arg-type]
        self.escalations.append(escalation)
        if self._child:
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
        if self.human is None:
            raise ContractViolation(
                f"ステージ {stage.id!r} で escalate（{cause}）が起きたが HumanDecider が束縛されていない"
            )
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
                human_verdict = Verdict(VerdictKind.GOAL, decided_by="human", reason=note)
                if gate_phase is not None:
                    # ゲート不成立由来の escalate: 人間がゲートを通したものとして次へ（再評価しない）
                    self.gates.append(GateEvent(gate_phase.id, "passed", note="human"))
                    if gate_phase.id not in self.gates_passed:
                        self.gates_passed.append(gate_phase.id)
                    self._advance(stage, human_verdict)
                else:
                    self._transition(stage, end, human_verdict)
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
            child_results={k: list(v) for k, v in self.rt.child_results.items()},
            evaluations=list(self.rt.evaluations),
        )
