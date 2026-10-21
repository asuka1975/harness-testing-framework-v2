"""recorder: LLM・分類器・ユーザー回答の記録と再生（第2節「非決定性の二層分離」）。

記録は JSONL。再生は記録と同じ順序・同じ要求であることを照合し、外れたら ReplayMismatch。
ユーザー入出力の WaitingForUser は記録しない（中断は実行機構の状態であって回答ではない）。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from htf.contract import (
    Classification,
    Classifier,
    ClassOption,
    ContractViolation,
    JsonValue,
    LLMClient,
    LLMRequest,
    LLMResponse,
    UserIO,
)


class ReplayMismatch(Exception):
    """再生中の要求が記録と一致しない。"""


class Recorder:
    def __init__(self, path: str | Path, mode: Literal["record", "replay"]) -> None:
        self.path = Path(path)
        self.mode = mode
        self._entries: list[dict] = []
        self._cursor = 0
        if mode == "replay":
            self._entries = [
                json.loads(line)
                for line in self.path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def call(self, kind: str, request: JsonValue, live: Callable[[], JsonValue]) -> JsonValue:
        if self.mode == "record":
            response = live()
            with self.path.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {"kind": kind, "request": request, "response": response},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )
            return response
        if self._cursor >= len(self._entries):
            raise ReplayMismatch(f"記録の終わりを越えた要求: {kind} {request!r}")
        entry = self._entries[self._cursor]
        self._cursor += 1
        if entry["kind"] != kind or entry["request"] != request:
            raise ReplayMismatch(
                f"記録 #{self._cursor - 1} と不一致: 期待 {entry['kind']} {entry['request']!r}, 実際 {kind} {request!r}"
            )
        return entry["response"]


def _require(inner: object, what: str) -> None:
    if inner is None:
        raise ContractViolation(f"record モードでは {what} の実装が要る")


class RecordedLLM(LLMClient):
    def __init__(self, inner: LLMClient | None, recorder: Recorder) -> None:
        self._inner = inner
        self._recorder = recorder

    def complete(self, request: LLMRequest) -> LLMResponse:
        def live() -> JsonValue:
            _require(self._inner, "LLMClient")
            assert self._inner is not None
            return asdict(self._inner.complete(request))

        data = self._recorder.call("llm", asdict(request), live)
        assert isinstance(data, dict)
        return LLMResponse(text=str(data["text"]), raw=data.get("raw"))


class RecordedUserIO(UserIO):
    def __init__(self, inner: UserIO | None, recorder: Recorder) -> None:
        self._inner = inner
        self._recorder = recorder

    def ask(self, question: str, *, schema: dict[str, JsonValue] | None = None) -> JsonValue:
        def live() -> JsonValue:
            _require(self._inner, "UserIO")
            assert self._inner is not None
            return self._inner.ask(question, schema=schema)

        return self._recorder.call("user", {"question": question, "schema": schema}, live)


class RecordedClassifier(Classifier):
    def __init__(self, inner: Classifier | None, recorder: Recorder) -> None:
        self._inner = inner
        self._recorder = recorder

    def classify(self, document: str, options: Sequence[ClassOption]) -> Classification:
        request: JsonValue = {"document": document, "options": [asdict(o) for o in options]}

        def live() -> JsonValue:
            _require(self._inner, "Classifier")
            assert self._inner is not None
            return asdict(self._inner.classify(document, options))

        data = self._recorder.call("classifier", request, live)
        assert isinstance(data, dict)
        return Classification(
            option_id=str(data["option_id"]), confidence=float(data["confidence"])
        )
