"""探針 P5: オラクル検証。混同行列を変えた時の κ の追従、ECE のビン数依存、較正済み確信度の離散性。

実行: uv run python reports/verification/f3-test-runners/probe_oracle.py
"""

from __future__ import annotations

import random

from htf.testing.oracle import ConfusionClassifier, CorpusItem, expected_kappa, verify_oracle

OPTIONS = [
    {"id": "goal", "description": "正常"},
    {"id": "checks_failed", "description": "検査に失敗"},
    {"id": "unknown", "description": "不明"},
]
PRIORS = {"goal": 0.6, "checks_failed": 0.3, "unknown": 0.1}
BASE = {
    "goal": {"goal": 0.9, "checks_failed": 0.05, "unknown": 0.05},
    "checks_failed": {"goal": 0.2, "checks_failed": 0.7, "unknown": 0.1},
    "unknown": {"goal": 0.3, "checks_failed": 0.2, "unknown": 0.5},
}


def corpus(n: int, seed: int) -> list[CorpusItem]:
    rng = random.Random(seed)
    labels = list(PRIORS)
    items = []
    for i in range(n):
        label = rng.choices(labels, [PRIORS[k] for k in labels])[0]
        items.append(
            CorpusItem(
                id=f"item-{i}",
                workflow="synthetic",
                stage="verify",
                document=f"# stage: verify\ntruth: {label}\n## writes\n### report.json\n{{\"n\": {i}}}\n",
                options=OPTIONS,
                label=label,
            )
        )
    return items


def diag(p: float):
    """対角を p、残りを均等に配る混同行列。"""
    out = {}
    for k in PRIORS:
        others = [o for o in PRIORS if o != k]
        out[k] = {k: p, **{o: (1 - p) / 2 for o in others}}
    return out


C = corpus(6000, seed=3)
print("[P5-a] κ の追従: 対角 p を変えた混同行列（N=6000, seed 11）")
for p in (0.4, 0.6, 0.8, 0.9, 0.95, 1.0):
    conf = diag(p)
    rep = verify_oracle(ConfusionClassifier(conf, seed=11, confidence="calibrated", priors=PRIORS), C, reruns=1)
    exp = expected_kappa(conf, PRIORS)
    print(f"  p={p:.2f} 観測 κ={rep.kappa:.4f} 期待 κ={exp:.4f} 差={rep.kappa - exp:+.4f} acc={rep.accuracy:.3f}")

print("\n[P5-b] κ の分類器の種依存（BASE、N=6000, 種 10 本）: 許容差 0.03 に対する揺れ")
exp = expected_kappa(BASE, PRIORS)
ks = []
for sd in range(1, 11):
    rep = verify_oracle(ConfusionClassifier(BASE, seed=sd, confidence="calibrated", priors=PRIORS), C, reruns=1)
    ks.append(rep.kappa - exp)
print(f"  期待 κ={exp:.4f} 差: min={min(ks):+.4f} max={max(ks):+.4f}")
print("  N を減らすと（N=500、種 10 本）:")
C500 = corpus(500, seed=3)
ks = [
    verify_oracle(ConfusionClassifier(BASE, seed=sd, confidence="calibrated", priors=PRIORS), C500, reruns=1).kappa - exp
    for sd in range(1, 11)
]
print(f"  差: min={min(ks):+.4f} max={max(ks):+.4f}  → 0.03 を超える本数: {sum(abs(k) > 0.03 for k in ks)}/10")

print("\n[P5-c] ECE のビン数依存")
cal = ConfusionClassifier(BASE, seed=11, confidence="calibrated", priors=PRIORS)
over = ConfusionClassifier(BASE, seed=11, confidence=0.95)
acc = sum(PRIORS[k] * BASE[k][k] for k in PRIORS)
for bins in (1, 2, 5, 10, 20, 50, 100):
    r1 = verify_oracle(cal, C, bins=bins, reruns=1)
    r2 = verify_oracle(over, C, bins=bins, reruns=1)
    print(f"  bins={bins:3d} calibrated ECE={r1.ece:.4f}  overconfident(0.95) ECE={r2.ece:.4f}（0.95-acc={0.95 - acc:.4f}）")
confs = sorted({p.confidence for p in verify_oracle(cal, C, reruns=1).predictions})
print("  calibrated の確信度の取りうる値:", [round(c, 4) for c in confs], "（クラス数と同じ 3 値だけ → ビン内は均質）")

print("\n[P5-d] 較正ずれを連続的に入れた時（確信度 = 精度 + δ）の ECE: 許容差 0.03 の検出限界")


class Shifted(ConfusionClassifier):
    def __init__(self, delta: float, **kw):
        super().__init__(**kw)
        self.delta = delta

    def classify(self, document, options):
        c = super().classify(document, options)
        from htf.contract import Classification

        return Classification(c.option_id, min(1.0, max(0.0, c.confidence + self.delta)))


for d in (0.0, 0.01, 0.02, 0.03, 0.05, 0.1):
    r = verify_oracle(Shifted(d, confusion=BASE, seed=11, confidence="calibrated", priors=PRIORS), C, reruns=1)
    print(f"  δ={d:.2f} ECE={r.ece:.4f}")

print("\n[P5-e] 違う κ の棄却: 期待 κ との差が 0.1 を切るほど近い『間違った』行列は見分けられない")
for p in (0.85, 0.80, 0.75):
    wrong = diag(p)
    rep = verify_oracle(ConfusionClassifier(BASE, seed=2, confidence="calibrated", priors=PRIORS), corpus(3000, 5), reruns=1)
    print(f"  wrong=diag({p}) 期待 κ={expected_kappa(wrong, PRIORS):.3f} 観測 κ(BASE)={rep.kappa:.3f} 差={abs(rep.kappa - expected_kappa(wrong, PRIORS)):.3f} {'棄却' if abs(rep.kappa - expected_kappa(wrong, PRIORS)) > 0.1 else '見分けられない'}")
