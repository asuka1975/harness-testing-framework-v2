"""オラクル検証（雛形第 5 節）を偽の分類器で通す。コーパスはこのハーネスの台本の run の状態文書から作る。

- 正解ラベル: 偽本体が本物の結果から書いた印（sf_support.marker_truth。実コーパスでは人手ラベル）
- MarkerClassifier: 印を読むので κ = 1。low_confidence の項目は正しいが確信度が低い → ECE に現れる
- ConfusionClassifier（既知の混同行列）: κ が理論値（expected_kappa）に近い。種つきなら再実行一致 1、種なしなら 1 未満
- コーパスの JSONL の書き出しと読み戻し
"""

from __future__ import annotations

import math
from collections import Counter

import pytest
from sf_support import SCENARIOS, H, evaluation_records, marker_truth, run_scenario

from htf.testing.harness import MarkerClassifier
from htf.testing.oracle import (
    ConfusionClassifier,
    corpus_item_from_record,
    expected_kappa,
    load_corpus,
    verify_oracle,
    write_corpus,
)

ACCURACY = 0.8  # 混同行列: 正しいクラスを 0.8、unknown を 0.2

pytestmark = pytest.mark.oracle  # オラクル検証はナイトリーの段（計画書第 5.7 節）


@pytest.fixture(scope="module")
def corpus(workflow, tmp_path_factory):  # noqa: ANN001, ANN201
    base = tmp_path_factory.mktemp("oracle")
    items = []
    for name in SCENARIOS:
        result = run_scenario(H.load_scenario(name), workflow, base / name)
        for i, record in enumerate(evaluation_records(result)):
            options = [o.id for o in record.options]
            items.append(
                corpus_item_from_record(
                    item_id=f"{name}-{i}",
                    workflow=record.workflow,
                    stage=record.stage_id,
                    document=record.document,
                    options=record.options,
                    label=marker_truth(record.document, options),
                    note=f"台本 {name}",
                )
            )
    return items


def test_corpus_round_trips_through_jsonl(corpus, tmp_path):
    path = tmp_path / "corpus.jsonl"
    write_corpus(path, corpus)
    assert load_corpus(path) == corpus
    labels = Counter(item.label for item in corpus)
    assert len(corpus) >= 200
    assert {"goal", "unknown", "ambiguous", "tests_failing", "regression"} <= set(labels)


def test_marker_classifier_agrees_with_the_labels(corpus):
    report = verify_oracle(MarkerClassifier(), corpus)
    assert report.kappa == pytest.approx(1.0)
    assert report.accuracy == pytest.approx(1.0)
    assert report.rerun_agreement == pytest.approx(1.0)
    assert report.ece > 0  # low_confidence の項目: 正しいが確信度 0.1


def _confusion(labels: set[str]) -> dict[str, dict[str, float]]:
    matrix = {lab: {lab: ACCURACY, "unknown": 1 - ACCURACY} for lab in labels if lab != "unknown"}
    matrix["unknown"] = {"unknown": ACCURACY, "goal": 1 - ACCURACY}
    return matrix


def _with_truth(corpus):  # noqa: ANN001, ANN202
    """ConfusionClassifier の約束: 状態文書の `truth: <label>` 行から真のラベルを読む（実コーパスには無い行）。"""
    import dataclasses

    return [dataclasses.replace(i, document=f"truth: {i.label}\n{i.document}") for i in corpus]


def test_confusion_classifier_reproduces_the_expected_kappa(corpus):
    labels = Counter(item.label for item in corpus)
    priors = {lab: n / len(corpus) for lab, n in labels.items()}
    confusion = _confusion(set(labels))
    truth_corpus = _with_truth(corpus)
    report = verify_oracle(ConfusionClassifier(confusion, seed=11), truth_corpus, reruns=3)
    # 種つきの分類器は文書の内容で乱数を決めるので、同じ文書は同じ答えになる。有効な標本は一意な文書の数
    # （同じ変種の code / check の文書は台本をまたいで同一）。許容幅はその数から 3 標準誤差で取る
    unique = len({item.document for item in corpus})
    tolerance = 3 * math.sqrt(ACCURACY * (1 - ACCURACY) / unique)
    assert report.kappa == pytest.approx(expected_kappa(confusion, priors), abs=max(0.1, tolerance))
    assert report.accuracy == pytest.approx(ACCURACY, abs=tolerance)
    assert report.rerun_agreement == pytest.approx(1.0)  # 種つき: 同じ入力に同じ答え

    calibrated = ConfusionClassifier(confusion, seed=11, confidence="calibrated", priors=priors)
    assert verify_oracle(calibrated, truth_corpus).ece < 0.1

    unseeded = verify_oracle(ConfusionClassifier(confusion, seed=None), truth_corpus, reruns=3)
    assert unseeded.rerun_agreement < 1.0
