"""ハーネス契約の型。

スナップショット、判定（三層）、遷移の種類、escalate の解決、子 run の結果。
意味は同じディレクトリの CONTRACT.md にある。ここは形だけ。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


class VerdictKind(StrEnum):
    """三層。goal = 正常系、end_state = 準正常系、unknown = 例外系。"""

    GOAL = "goal"
    END_STATE = "end_state"
    UNKNOWN = "unknown"


type DecidedBy = Literal[
    "quantitative",  # goal 指標が評価不能、または不成立なのに分類器が goal を選んだ（不一致）
    "qualitative",  # 分類器が goal の記述を選んだ
    "classifier",  # 分類器が end_state の記述を選んだ
    "aggregate",  # 子 run の集約規則
    "threshold",  # 分類器の確信度が閾値未満
    "human",  # escalate 後の人間の上書き（continue_as_goal）
]


@dataclass(frozen=True)
class Verdict:
    """evaluate(stage, snapshot) の結果。"""

    kind: VerdictKind
    state: str | None = None  # END_STATE の時の end_state id
    confidence: float | None = None  # 分類器を使った時の確信度
    decided_by: DecidedBy | None = None
    reason: str = ""


@dataclass(frozen=True)
class Snapshot:
    """ステージの開始時または終了時の状態。

    files は、そのステージの artifacts.writes の範囲の成果物を複製したディレクトリ。
    memory は memory の鍵と JSON 値の全体（前方に流れる）。
    """

    workflow: str
    version: str | None
    stage_id: str
    moment: Literal["start", "end"]
    ordinal: int  # run 内の通し番号。0 から
    files: Path
    memory: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class Carry:
    """ロールバック時に戻り先の開始時スナップショットへ重ねる memory の項目。"""

    items: dict[str, JsonValue]


class TransitionKind(StrEnum):
    """runner が起こしうる遷移。計画書の「6種の遷移」に、決定 #9 (b) の集約を加えた 7 種。"""

    NEXT = "next"
    ROLLBACK_WITHIN_PHASE = "rollback_within_phase"
    ROLLBACK_ACROSS_PHASE = "rollback_across_phase"
    ESCALATE_UNKNOWN = "escalate_unknown"
    ESCALATE_MAX_EXCEEDED = "escalate_max_exceeded"
    SUSPEND_RESUME = "suspend_resume"
    SUBWORKFLOW_AGGREGATE = "subworkflow_aggregate"


# --- escalate 後の人間の選択肢（決定 #3）---


@dataclass(frozen=True)
class Rerun:
    note: str = ""


@dataclass(frozen=True)
class RollbackTo:
    stage: str
    carry: dict[str, JsonValue] = field(default_factory=dict)
    note: str = ""


@dataclass(frozen=True)
class ContinueAsGoal:
    note: str  # 必須。実行記録に人間の上書きとして残る


@dataclass(frozen=True)
class Abort:
    note: str = ""


type Resolution = Rerun | RollbackTo | ContinueAsGoal | Abort


@dataclass(frozen=True)
class Escalation:
    """人間へ差し戻す時に渡す情報。"""

    stage_id: str
    verdict: Verdict
    cause: Literal["unknown", "max_exceeded", "child_unresolved", "phase_gate_failed"]
    snapshot: Snapshot
    edge: tuple[str, str] | None = None  # max 超過の時の (state, 戻り先)


# --- 子ワークフロー（決定 #9 (b)）---


@dataclass(frozen=True)
class ChildOutcome:
    """子 run 一つの終わり方。goal 到達か、子の中で解決できなかった (stage, state)。"""

    index: int
    kind: Literal["goal", "stuck", "unknown"]
    stage: str | None = None  # stuck / unknown の時
    state: str | None = None  # stuck の時は end_state id、unknown の時は "unknown"


# --- 分類器と LLM ---


@dataclass(frozen=True)
class ClassOption:
    id: str  # "goal" または end_state id（unknown を含む）
    description: str


@dataclass(frozen=True)
class Classification:
    option_id: str
    confidence: float  # 0.0〜1.0


@dataclass(frozen=True)
class LLMRequest:
    messages: list[dict[str, JsonValue]]
    model: str | None = None
    params: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    raw: JsonValue = None


# --- 例外 ---


class ContractViolation(Exception):
    """契約に反する操作（未宣言の鍵への emit、未宣言のステージでのユーザー入出力、など）。"""


class WaitingForUser(Exception):
    """UserIO がその場で答えられない。runner はこれを捕まえて中断する（決定 #4）。"""

    def __init__(self, question: str, schema: dict[str, JsonValue] | None = None) -> None:
        super().__init__(question)
        self.question = question
        self.schema = schema
