"""参照ランタイム（決定 #8 (b)）。loader / checkpoint / context / oracle / recorder / runner。

公開 API:
  load_workflow(path, *, metric_names) -> Workflow      検査を通った定義だけを読む
  Runner(workflow, bindings, *, workspace, ...)         制御ループ。run() / resume(answer)
  ReferenceRuntime(...)                                  三操作 + start。契約適合テストの対象
  Bindings                                               ハーネスが提供するものの束
  Recorder(path, mode)                                   記録再生
  DictMetricRegistry                                     指標レジストリの簡易実装
"""

from .checkpoint import META_DIR, SnapshotStore, snapshot_digest
from .context import RunContext
from .loader import WorkflowDefinitionError, load_workflow
from .model import (
    AggregateRule,
    Artifacts,
    Criterion,
    EndState,
    Goal,
    MetricError,
    Phase,
    Rollback,
    Stage,
    Subworkflow,
    Workflow,
)
from .oracle import (
    DictMetricRegistry,
    class_options,
    evaluate_metrics,
    evaluate_stage,
    evaluate_stage_detailed,
    project,
)
from .recorder import RecordedClassifier, RecordedLLM, RecordedUserIO, Recorder, ReplayMismatch
from .runner import (
    DEFAULT_THRESHOLD,
    Bindings,
    EvaluationRecord,
    GateEvent,
    PendingQuestion,
    ReferenceRuntime,
    Runner,
    RunResult,
    RunStatus,
    TransitionRecord,
)

__all__ = [
    "DEFAULT_THRESHOLD",
    "META_DIR",
    "AggregateRule",
    "Artifacts",
    "Bindings",
    "Criterion",
    "DictMetricRegistry",
    "EndState",
    "EvaluationRecord",
    "GateEvent",
    "Goal",
    "MetricError",
    "PendingQuestion",
    "Phase",
    "RecordedClassifier",
    "RecordedLLM",
    "RecordedUserIO",
    "Recorder",
    "ReferenceRuntime",
    "ReplayMismatch",
    "Rollback",
    "RunContext",
    "RunResult",
    "RunStatus",
    "Runner",
    "SnapshotStore",
    "Stage",
    "Subworkflow",
    "TransitionRecord",
    "Workflow",
    "WorkflowDefinitionError",
    "class_options",
    "evaluate_metrics",
    "evaluate_stage",
    "evaluate_stage_detailed",
    "load_workflow",
    "project",
    "snapshot_digest",
]
