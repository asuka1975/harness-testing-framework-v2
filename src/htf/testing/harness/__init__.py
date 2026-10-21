"""偽ステージ本体によるランナー検証のための道具（計画書 testing/harness）。

- load_example_package: examples/ 配下のハーネス（ハイフン名のディレクトリ）を Python パッケージとして読む
- ScriptedHuman / DeferringUserIO / QueueUserIO / MarkerClassifier / EchoLLM: 契約インターフェースの
  決定論的な代役（テストダブル）。特定のハーネスを知らない
- observed_kinds: トレースから観測された遷移種の集合
"""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from types import ModuleType

from htf.contract import (
    Classification,
    ClassOption,
    Escalation,
    JsonValue,
    LLMRequest,
    LLMResponse,
    Resolution,
    TransitionKind,
    WaitingForUser,
)


def load_example_package(root: Path, name: str) -> ModuleType:
    """root/__init__.py をパッケージ name として読み、直下のサブモジュールも import する。"""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, root / "__init__.py", submodule_search_locations=[str(root)]
    )
    assert spec is not None and spec.loader is not None, root
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    for info in pkgutil.iter_modules([str(root)]):
        if info.name != "tests":
            importlib.import_module(f"{name}.{info.name}")
    return module


class ScriptedHuman:
    """台本どおりに解決を返す HumanDecider。台本が尽きたら失敗する。"""

    def __init__(self, resolutions: Sequence[Resolution]) -> None:
        self._resolutions = list(resolutions)
        self.escalations: list[Escalation] = []

    def resolve(self, escalation: Escalation) -> Resolution:
        self.escalations.append(escalation)
        if not self._resolutions:
            raise AssertionError(f"台本に解決が無い: {escalation.stage_id} {escalation.cause}")
        return self._resolutions.pop(0)


class DeferringUserIO:
    """その場では答えられない UserIO。常に WaitingForUser を投げる（中断の経路を踏むため）。"""

    def ask(self, question: str, *, schema: dict[str, JsonValue] | None = None) -> JsonValue:
        raise WaitingForUser(question, schema)


class QueueUserIO:
    """回答を順に返す UserIO。尽きたら WaitingForUser。"""

    def __init__(self, answers: Iterable[JsonValue]) -> None:
        self._answers = list(answers)

    def ask(self, question: str, *, schema: dict[str, JsonValue] | None = None) -> JsonValue:
        if not self._answers:
            raise WaitingForUser(question, schema)
        return self._answers.pop(0)


class MarkerClassifier:
    """状態文書の writes 節にある印（既定: outcome）をそのまま選択肢として返す決定論的な分類器。

    印が low_confidence なら goal を低い確信度で返す（閾値未満 → unknown の経路）。
    印が選択肢に無ければ unknown を返す。LLM を使わないテスト専用。
    """

    _PATTERNS = (
        re.compile(r'"(?P<key>[a-z_]+)"\s*:\s*"(?P<val>[a-z_]+)"'),
        re.compile(r"^(?P<key>[a-z_]+):\s*(?P<val>[a-z_]+)\s*$", re.M),
    )

    def __init__(self, key: str = "outcome", *, confidence: float = 1.0, low: float = 0.1) -> None:
        self.key = key
        self.confidence = confidence
        self.low = low
        self.calls: list[str] = []

    def classify(self, document: str, options: Sequence[ClassOption]) -> Classification:
        section = document.split("## writes", 1)[-1]
        marker = None
        for pattern in self._PATTERNS:
            for m in pattern.finditer(section):
                if m.group("key") == self.key:
                    marker = m.group("val")
        self.calls.append(marker or "")
        ids = {o.id for o in options}
        if marker == "low_confidence":
            return Classification("goal", self.low)
        if marker in ids:
            return Classification(marker, self.confidence)
        return Classification("unknown", self.confidence)


class EchoLLM:
    """最後のメッセージの内容を決定論的に返す LLMClient の代役。"""

    def complete(self, request: LLMRequest) -> LLMResponse:
        last = request.messages[-1] if request.messages else {}
        content = str(last.get("content", ""))
        return LLMResponse(text=f"[echo] {content}", raw={"model": request.model})


def observed_kinds(trace: Iterable[object]) -> set[TransitionKind]:
    return {getattr(t, "kind") for t in trace}  # noqa: B009


__all__ = [
    "DeferringUserIO",
    "EchoLLM",
    "MarkerClassifier",
    "QueueUserIO",
    "ScriptedHuman",
    "load_example_package",
    "observed_kinds",
]
