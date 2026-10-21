"""F3 完了条件: 既知の混同行列を持つ偽の分類器に対して、オラクル検証が既知の κ と ECE を再現する。

コーパスは合成（ラベルの事前分布は既知）。期待 κ は混同行列と事前分布から解析的に出す。
"""

from __future__ import annotations

from pathlib import Path

from htf.testing.oracle import (
    ConfusionClassifier,
    CorpusItem,
    expected_kappa,
    load_corpus,
    verify_oracle,
    write_corpus,
)

OPTIONS = [
    {"id": "goal", "description": "正常"},
    {"id": "checks_failed", "description": "検査に失敗"},
    {"id": "unknown", "description": "不明"},
]
PRIORS = {"goal": 0.6, "checks_failed": 0.3, "unknown": 0.1}
CONFUSION = {
    "goal": {"goal": 0.9, "checks_failed": 0.05, "unknown": 0.05},
    "checks_failed": {"goal": 0.2, "checks_failed": 0.7, "unknown": 0.1},
    "unknown": {"goal": 0.3, "checks_failed": 0.2, "unknown": 0.5},
}


def _corpus(n: int, seed: int) -> list[CorpusItem]:
    import random

    rng = random.Random(seed)
    labels = list(PRIORS)
    weights = [PRIORS[k] for k in labels]
    items = []
    for i in range(n):
        label = rng.choices(labels, weights)[0]
        items.append(
            CorpusItem(
                id=f"item-{i}",
                workflow="synthetic",
                stage="verify",
                document=(
                    f'# stage: verify\ntruth: {label}\n## writes\n### report.json\n{{"n": {i}}}\n'
                ),
                options=OPTIONS,
                label=label,
            )
        )
    return items


def test_reproduces_known_kappa_and_ece(tmp_path: Path) -> None:
    corpus = _corpus(6000, seed=3)
    path = tmp_path / "corpus.jsonl"
    write_corpus(path, corpus)
    assert [c.label for c in load_corpus(path)] == [c.label for c in corpus]

    # 確信度は予測クラスの実際の正答率（較正済み）→ ECE ≈ 0
    calibrated = ConfusionClassifier(CONFUSION, seed=11, confidence="calibrated", priors=PRIORS)
    report = verify_oracle(calibrated, corpus, bins=10, reruns=2)
    kappa = expected_kappa(CONFUSION, PRIORS)
    assert abs(report.kappa - kappa) < 0.03, (report.kappa, kappa)
    assert report.ece < 0.03, report.ece
    assert report.rerun_agreement == 1.0  # 種が同じなら同じ答え
    assert report.n == 6000

    # 確信度を常に 0.95 にすると、正答率（≈ 0.79）との差が ECE に出る
    overconfident = ConfusionClassifier(CONFUSION, seed=11, confidence=0.95)
    report2 = verify_oracle(overconfident, corpus, bins=10, reruns=1)
    accuracy = sum(PRIORS[k] * CONFUSION[k][k] for k in PRIORS)
    assert abs(report2.ece - (0.95 - accuracy)) < 0.03, (report2.ece, accuracy)


def test_wrong_expected_kappa_is_rejected() -> None:
    corpus = _corpus(3000, seed=5)
    classifier = ConfusionClassifier(CONFUSION, seed=2, confidence="calibrated", priors=PRIORS)
    report = verify_oracle(classifier, corpus, bins=10, reruns=1)
    wrong = {
        "goal": {"goal": 0.6, "checks_failed": 0.3, "unknown": 0.1},
        "checks_failed": {"goal": 0.5, "checks_failed": 0.4, "unknown": 0.1},
        "unknown": {"goal": 0.4, "checks_failed": 0.4, "unknown": 0.2},
    }
    assert abs(report.kappa - expected_kappa(wrong, PRIORS)) > 0.1


def test_unstable_classifier_has_low_rerun_agreement() -> None:
    corpus = _corpus(500, seed=9)
    unstable = ConfusionClassifier(
        CONFUSION, seed=None, confidence=0.9
    )  # 種なし = 呼ぶたびに引き直す
    report = verify_oracle(unstable, corpus, bins=5, reruns=3)
    assert report.rerun_agreement < 0.95
