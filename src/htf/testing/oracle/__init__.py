"""オラクル検証（計画書 testing/oracle）: コーパス形式、ラベル形式、一致率（Cohen の κ）、較正（ECE）、再実行一致。

コーパスは JSONL。一行が一項目: id, workflow, stage, document（状態文書）, options（選択肢）, label（人手ラベル）。
分類器の検証は人手ラベルとの κ、確信度の較正（ECE）、同じ入力を繰り返した時の一致率で測る（第2節「分類器の検証」）。
閾値（許容差）はここに置かず、呼ぶ側が決める（ADR-013）。

ConfusionClassifier は既知の混同行列を持つ偽の分類器（テスト専用）。状態文書の `truth: <label>` 行から真のラベルを読む。
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from htf.contract import Classification, Classifier, ClassOption, JsonValue


@dataclass(frozen=True)
class CorpusItem:
    id: str
    workflow: str
    stage: str
    document: str
    options: list[dict[str, str]]  # [{"id", "description"}]
    label: str
    note: str = ""
    # ラベルを付けた時の分類体系の版（workflow.version）。版が変わった記述のラベルは再ラベルの候補（F5）
    workflow_version: str | None = None


@dataclass(frozen=True)
class Prediction:
    id: str
    option_id: str
    confidence: float


def write_corpus(path: Path, items: Sequence[CorpusItem]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(asdict(item), ensure_ascii=False, sort_keys=True) + "\n")


def load_corpus(path: Path) -> list[CorpusItem]:
    items = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            items.append(CorpusItem(**json.loads(line)))
    return items


def classify_corpus(classifier: Classifier, items: Sequence[CorpusItem]) -> list[Prediction]:
    out = []
    for item in items:
        options = [ClassOption(o["id"], o["description"]) for o in item.options]
        c = classifier.classify(item.document, options)
        out.append(Prediction(item.id, c.option_id, c.confidence))
    return out


# --- 指標 ---


def cohen_kappa(labels: Sequence[str], predictions: Sequence[str]) -> float:
    n = len(labels)
    if n == 0:
        return 0.0
    po = sum(1 for a, b in zip(labels, predictions, strict=True) if a == b) / n
    la, lb = Counter(labels), Counter(predictions)
    pe = sum(la[k] * lb[k] for k in set(la) | set(lb)) / (n * n)
    return 1.0 if pe == 1.0 else (po - pe) / (1 - pe)


def expected_kappa(
    confusion: Mapping[str, Mapping[str, float]], priors: Mapping[str, float]
) -> float:
    """混同行列 C[label][pred] とラベルの事前分布から、理論上の κ。"""
    classes = list(priors)
    po = sum(priors[k] * confusion[k].get(k, 0.0) for k in classes)
    pred_marginal = {
        k: sum(priors[lab] * confusion[lab].get(k, 0.0) for lab in classes) for k in classes
    }
    pe = sum(priors[k] * pred_marginal[k] for k in classes)
    return (po - pe) / (1 - pe)


def expected_calibration_error(
    confidences: Sequence[float], correct: Sequence[bool], *, bins: int = 10
) -> float:
    n = len(confidences)
    if n == 0:
        return 0.0
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for c, ok in zip(confidences, correct, strict=True):
        idx = min(bins - 1, max(0, int(c * bins)))
        buckets[idx].append((c, ok))
    ece = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        acc = sum(1 for _, ok in bucket if ok) / len(bucket)
        conf = sum(c for c, _ in bucket) / len(bucket)
        ece += len(bucket) / n * abs(acc - conf)
    return ece


@dataclass
class OracleReport:
    n: int
    kappa: float
    ece: float
    rerun_agreement: float
    accuracy: float
    confusion: dict[str, Counter[str]] = field(default_factory=dict)  # label → pred → count
    predictions: list[Prediction] = field(default_factory=list)


def verify_oracle(
    classifier: Classifier, corpus: Sequence[CorpusItem], *, bins: int = 10, reruns: int = 2
) -> OracleReport:
    """κ、ECE、再実行一致を一度に出す。reruns 回分類し、全回で同じ答えだった項目の割合が再実行一致。"""
    runs = [classify_corpus(classifier, corpus) for _ in range(max(1, reruns))]
    first = runs[0]
    labels = [c.label for c in corpus]
    preds = [p.option_id for p in first]
    correct = [a == b for a, b in zip(labels, preds, strict=True)]
    confusion: dict[str, Counter[str]] = {}
    for label, pred in zip(labels, preds, strict=True):
        confusion.setdefault(label, Counter())[pred] += 1
    agreement = (
        sum(
            1
            for i in range(len(corpus))
            if all(run[i].option_id == first[i].option_id for run in runs[1:])
        )
        / len(corpus)
        if corpus
        else 1.0
    )
    return OracleReport(
        n=len(corpus),
        kappa=cohen_kappa(labels, preds),
        ece=expected_calibration_error([p.confidence for p in first], correct, bins=bins),
        rerun_agreement=agreement,
        accuracy=sum(correct) / len(corpus) if corpus else 0.0,
        confusion=confusion,
        predictions=first,
    )


# --- 偽の分類器 ---


class ConfusionClassifier(Classifier):
    """既知の混同行列 C[label][pred] で予測を引く偽の分類器。真のラベルは文書の `truth: <label>` 行から読む。

    confidence: 数値なら常にその値。"calibrated" なら予測クラスの精度 P(label = k | pred = k)（priors が要る）。
    seed を与えると (seed, 文書) で決まる乱数列を使い、同じ入力に同じ答えを返す。None なら呼ぶたびに引き直す。
    """

    _TRUTH = re.compile(r"^truth:\s*(?P<label>[a-z_]+)\s*$", re.M)

    def __init__(
        self,
        confusion: Mapping[str, Mapping[str, float]],
        *,
        seed: int | None,
        confidence: float | str = 0.9,
        priors: Mapping[str, float] | None = None,
    ) -> None:
        self.confusion = {k: dict(v) for k, v in confusion.items()}
        self.seed = seed
        self.confidence = confidence
        self.priors = dict(priors or {})
        self._rng = random.Random(seed)
        if confidence == "calibrated" and not self.priors:
            raise ValueError("calibrated には priors が要る")

    def _precision(self, pred: str) -> float:
        num = self.priors.get(pred, 0.0) * self.confusion.get(pred, {}).get(pred, 0.0)
        den = sum(self.priors[lab] * self.confusion[lab].get(pred, 0.0) for lab in self.priors)
        return num / den if den else 0.0

    def classify(self, document: str, options: Sequence[ClassOption]) -> Classification:
        m = self._TRUTH.search(document)
        if m is None:
            raise ValueError("文書に truth: 行が無い")
        label = m.group("label")
        row = self.confusion[label]
        if self.seed is None:
            rng = self._rng
        else:
            digest = hashlib.sha256(f"{self.seed}:{document}".encode()).hexdigest()
            rng = random.Random(int(digest[:16], 16))
        preds = list(row)
        pred = rng.choices(preds, [row[p] for p in preds])[0]
        conf = self._precision(pred) if self.confidence == "calibrated" else float(self.confidence)
        return Classification(pred, conf)


def corpus_item_from_record(
    *,
    item_id: str,
    workflow: str,
    stage: str,
    document: str,
    options: Sequence[ClassOption],
    label: str,
    note: str = "",
    workflow_version: str | None = None,
) -> CorpusItem:
    return CorpusItem(
        id=item_id,
        workflow=workflow,
        stage=stage,
        document=document,
        options=[{"id": o.id, "description": o.description} for o in options],
        label=label,
        note=note,
        workflow_version=workflow_version,
    )


JsonDoc = dict[str, JsonValue]

__all__ = [
    "ConfusionClassifier",
    "CorpusItem",
    "OracleReport",
    "Prediction",
    "classify_corpus",
    "cohen_kappa",
    "corpus_item_from_record",
    "expected_calibration_error",
    "expected_kappa",
    "load_corpus",
    "verify_oracle",
    "write_corpus",
]
