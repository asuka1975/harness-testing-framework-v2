"""ハーネス契約（計画書 contract/）。保護ファイル。

契約 = 三操作（run / evaluate / restore + overlay）、スナップショット形式、
ステージ本体・指標・ユーザー入出力・LLM クライアント・分類器のインターフェース。
意味は CONTRACT.md、形は types.py と interfaces.py。
"""

from .interfaces import (
    Classifier,
    HumanDecider,
    LLMClient,
    Metric,
    MetricRegistry,
    Runtime,
    StageBody,
    StageContext,
    UserIO,
)
from .types import (
    Abort,
    Carry,
    ChildOutcome,
    Classification,
    ClassOption,
    ContinueAsGoal,
    ContractViolation,
    DecidedBy,
    Escalation,
    JsonValue,
    LLMRequest,
    LLMResponse,
    Rerun,
    Resolution,
    RollbackTo,
    Snapshot,
    TransitionKind,
    Verdict,
    VerdictKind,
    WaitingForUser,
)

__all__ = [
    "Abort",
    "Carry",
    "ChildOutcome",
    "ClassOption",
    "Classification",
    "Classifier",
    "ContinueAsGoal",
    "ContractViolation",
    "DecidedBy",
    "Escalation",
    "HumanDecider",
    "JsonValue",
    "LLMClient",
    "LLMRequest",
    "LLMResponse",
    "Metric",
    "MetricRegistry",
    "Rerun",
    "Resolution",
    "RollbackTo",
    "Runtime",
    "Snapshot",
    "StageBody",
    "StageContext",
    "TransitionKind",
    "UserIO",
    "Verdict",
    "VerdictKind",
    "WaitingForUser",
]
