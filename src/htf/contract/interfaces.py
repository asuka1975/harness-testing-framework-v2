"""ハーネス契約のインターフェース（Protocol）。

フレームワークが定めるのは三操作（run / evaluate / restore + overlay）と、ハーネスが提供する
ステージ本体・指標・ユーザー入出力・LLM クライアント・分類器の形。意味は CONTRACT.md。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from .types import (
    Carry,
    Classification,
    ClassOption,
    Escalation,
    JsonValue,
    LLMRequest,
    LLMResponse,
    Resolution,
    Snapshot,
    Verdict,
)

# --- ハーネスが提供するもの ---


class UserIO(Protocol):
    """ユーザー入出力（決定 #4）。user_input: true のステージの本体だけが使える。"""

    def ask(self, question: str, *, schema: dict[str, JsonValue] | None = None) -> JsonValue:
        """質問して回答を返す。その場で答えられない実装は WaitingForUser を投げる。"""
        ...


class LLMClient(Protocol):
    """LLM 呼び出し。ステージ本体はこれを直接持たず、StageContext.llm（recorder 経由）で使う。"""

    def complete(self, request: LLMRequest) -> LLMResponse: ...


class Classifier(Protocol):
    """goal と end_state の記述をそのまま選択肢として渡し、状態文書を分類する（第2節「分類器」）。"""

    def classify(self, document: str, options: Sequence[ClassOption]) -> Classification: ...


class Metric(Protocol):
    """指標。スナップショットから決定論的に値を計算する。値を返せない時は例外を投げる（→ unknown）。"""

    def __call__(self, snapshot: Snapshot) -> JsonValue: ...


@runtime_checkable
class MetricRegistry(Protocol):
    """指標レジストリ（決定 #2）。names() は整合性検査の入力でもある。"""

    def names(self) -> Iterable[str]: ...

    def resolve(self, name: str) -> Metric: ...


class StageContext(Protocol):
    """ステージ本体に渡される実行文脈。宣言（artifacts）の範囲でだけ読み書きできる。"""

    @property
    def stage_id(self) -> str: ...

    @property
    def workspace(self) -> Path: ...

    @property
    def memory(self) -> Mapping[str, JsonValue]:
        """memory_in に宣言した鍵だけが見える。"""
        ...

    def emit(self, key: str, value: JsonValue) -> None:
        """memory_out に宣言した鍵だけに書ける。他は ContractViolation。"""
        ...

    @property
    def user(self) -> UserIO:
        """user_input: true のステージでだけ使える。他は ContractViolation。"""
        ...

    @property
    def llm(self) -> LLMClient:
        """recorder を経由した LLM クライアント。記録があれば再生する。"""
        ...


class StageBody(Protocol):
    """ステージ本体。作業ディレクトリに成果物を書き、memory_out を emit する。"""

    def run(self, ctx: StageContext) -> None: ...


class HumanDecider(Protocol):
    """escalate を受けて四つの選択肢のどれかを返す（決定 #3）。テストでは台本を束縛する。"""

    def resolve(self, escalation: Escalation) -> Resolution: ...


# --- フレームワーク（参照ランタイム）またはハーネス自前の実装が満たすもの ---


class Runtime(Protocol):
    """三操作。契約適合テスト（F2）はこの Protocol に対して書く。"""

    def run(self, stage_id: str, snapshot: Snapshot) -> Snapshot:
        """開始時スナップショットからステージ本体を実行し、終了時スナップショットを返す。"""
        ...

    def evaluate(self, stage_id: str, snapshot: Snapshot) -> Verdict:
        """終了時スナップショットを三層で判定する。順序は goal 指標 → goal 定性 → end_state → unknown。"""
        ...

    def restore(self, snapshot: Snapshot) -> Snapshot:
        """開始時スナップショットを作業ディレクトリに復元する。"""
        ...

    def overlay(self, snapshot: Snapshot, carry: Carry) -> Snapshot:
        """復元したスナップショットに carry の項目だけを重ねる。宣言に無い鍵は ContractViolation。"""
        ...
