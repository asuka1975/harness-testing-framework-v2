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
    """記録は試行（ステージ本体の一回の実行）単位で確定する。

    begin_attempt() 〜 commit_attempt() の間の呼び出しは緩衝し、commit で確定（入れ子なら親の緩衝へ）、
    discard_attempt() で破棄する。中断（WaitingForUser）で終わった試行の記録を残さないため。
    再生では試行の区切りは無視し、確定した記録を順に照合する。
    """

    def __init__(self, path: str | Path, mode: Literal["record", "replay"]) -> None:
        self.path = Path(path)
        self.mode = mode
        self._entries: list[dict] = []
        self._cursor = 0
        self._buffers: list[list[dict]] = []
        if mode == "replay":
            self._entries = [
                json.loads(line)
                for line in self.path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    # --- 試行の区切り（record モードだけ意味を持つ）---

    def begin_attempt(self) -> None:
        if self.mode == "record":
            self._buffers.append([])

    def commit_attempt(self) -> None:
        if self.mode != "record":
            return
        entries = self._buffers.pop()
        if self._buffers:
            self._buffers[-1].extend(entries)
        else:
            self._write(entries)

    def discard_attempt(self) -> None:
        if self.mode == "record":
            self._buffers.pop()

    def finish(self) -> None:
        """再生の終わりに、未消費の記録が残っていれば不一致。"""
        if self.mode == "replay" and self._cursor < len(self._entries):
            remaining = len(self._entries) - self._cursor
            raise ReplayMismatch(f"未消費の記録が {remaining} 件残っている（#{self._cursor} から）")

    def _write(self, entries: list[dict]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    def call(self, kind: str, request: JsonValue, live: Callable[[], JsonValue]) -> JsonValue:
        if self.mode == "record":
            response = live()
            entry = {"kind": kind, "request": request, "response": response}
            if self._buffers:
                self._buffers[-1].append(entry)
            else:
                self._write([entry])
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
