"""StageContext の参照実装。宣言（artifacts）の範囲でだけ読み書きできる（CONTRACT 第 5.1 節）。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from htf.contract import ContractViolation, JsonValue, LLMClient, UserIO

from .model import Stage


class RunContext:
    def __init__(
        self,
        stage: Stage,
        workspace: Path,
        memory: Mapping[str, JsonValue],
        *,
        user: UserIO | None,
        llm: LLMClient | None,
    ) -> None:
        self._stage = stage
        self._workspace = workspace
        self._memory = MappingProxyType(
            {k: v for k, v in memory.items() if k in stage.artifacts.memory_in}
        )
        self._user = user
        self._llm = llm
        self._emitted: dict[str, JsonValue] = {}

    @property
    def stage_id(self) -> str:
        return self._stage.id

    @property
    def workspace(self) -> Path:
        return self._workspace

    @property
    def memory(self) -> Mapping[str, JsonValue]:
        return self._memory

    def emit(self, key: str, value: JsonValue) -> None:
        if key not in self._stage.artifacts.memory_out:
            raise ContractViolation(
                f"ステージ {self._stage.id!r} の memory_out に無い鍵 {key!r} への emit"
            )
        self._emitted[key] = value

    @property
    def user(self) -> UserIO:
        if not self._stage.user_input:
            raise ContractViolation(
                f"ステージ {self._stage.id!r} は user_input を宣言していないのでユーザー入出力を使えない"
            )
        if self._user is None:
            raise ContractViolation("UserIO が束縛されていない")
        return self._user

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            raise ContractViolation("LLMClient が束縛されていない")
        return self._llm

    @property
    def emitted(self) -> dict[str, JsonValue]:
        return dict(self._emitted)
