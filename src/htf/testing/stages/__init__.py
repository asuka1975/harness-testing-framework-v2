"""分布テストランナー、expectations 形式、独立性検証、遷移行列の推定（計画書 testing/stages）。

- run_many: 種を変えて N 回実行する
- tally: 評価記録（親と子 run）を (stage, first | reentry) ごとのクラス頻度と run 全体の結果に集計する
- expectations: 頻度の区間（第2節「分布基準の置き場」）。N と種もここに書く
- independence: クラス内の代表ごとに下流のクラス分布が揃うかを、種つきの並べ替え検定で比べる
- transition_matrix: P(class | stage, entry_kind) の推定

閾値（区間、p 値、並べ替えの回数）はすべて仮置きで、expectations や引数に置く（ADR-013）。
依存を増やさない: 分布関数は使わず並べ替え検定で p 値を出す。
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from htf.runtime import EvaluationRecord, Runner, RunResult, RunStatus

# --- 実行と集計 ---


@dataclass(frozen=True)
class RunSample:
    seed: int
    result: RunResult


def run_many(make_runner: Callable[[int], Runner], *, runs: int, seed: int = 0) -> list[RunSample]:
    """種 seed, seed+1, … で runs 回実行する。中断した run は分布テストでは扱わない（例外）。"""
    samples: list[RunSample] = []
    for i in range(runs):
        s = seed + i
        result = make_runner(s).run()
        if result.status is RunStatus.SUSPENDED:
            raise RuntimeError(
                f"run {s} が中断した。分布テストではユーザー入出力にシミュレータを束縛する"
            )
        samples.append(RunSample(s, result))
    return samples


def evaluation_units(result: RunResult) -> list[list[EvaluationRecord]]:
    """親 run と各子 run の評価記録の列（run 単位）。子は親の記録と別の単位にする。"""
    return [unit for unit, _status in evaluation_units_with_status(result)]


def evaluation_units_with_status(result: RunResult) -> list[tuple[list[EvaluationRecord], str]]:
    """run 単位の評価記録と、その run 単位の終わり方（completed / aborted / escalated / suspended）。"""
    units: list[tuple[list[EvaluationRecord], str]] = [
        (list(result.evaluations), result.status.value)
    ]
    for entries in result.child_results.values():
        for child_runs in entries:
            for child in child_runs:
                units.extend(evaluation_units_with_status(child))
    return units


@dataclass
class ClassCounts:
    counts: Counter[str] = field(default_factory=Counter)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def freq(self, cls: str) -> float:
        return self.counts[cls] / self.total if self.total else 0.0


@dataclass
class Tally:
    by_stage: dict[tuple[str, str], ClassCounts]
    outcomes: Counter[str]
    runs: int
    # 最上位のワークフローの版（スナップショットから。expectations の workflow_version と照合する。F5）
    workflow_version: str | None = None


def tally(samples: Iterable[RunSample]) -> Tally:
    by_stage: dict[tuple[str, str], ClassCounts] = defaultdict(ClassCounts)
    outcomes: Counter[str] = Counter()
    n = 0
    version: str | None = None
    for sample in samples:
        n += 1
        outcomes[sample.result.status.value] += 1
        if version is None and sample.result.end_snapshots:
            version = sample.result.end_snapshots[0].version
        for unit in evaluation_units(sample.result):
            for rec in unit:
                by_stage[(rec.stage_id, rec.entry_kind)].counts[rec.cls] += 1
    return Tally(dict(by_stage), outcomes, n, version)


def transition_matrix(samples: Iterable[RunSample]) -> dict[tuple[str, str], dict[str, float]]:
    t = tally(samples)
    return {
        key: {cls: c / cc.total for cls, c in sorted(cc.counts.items())}
        for key, cc in t.by_stage.items()
        if cc.total
    }


# --- expectations ---


@dataclass(frozen=True)
class Interval:
    min: float | None = None
    max: float | None = None

    def contains(self, value: float) -> bool:
        return (self.min is None or value >= self.min) and (self.max is None or value <= self.max)


@dataclass(frozen=True)
class Expectations:
    name: str
    origin: dict
    runs: int
    seed: int
    stages: dict[str, dict[str, dict[str, Interval]]]  # stage → first|reentry → class → 区間
    outcomes: dict[str, Interval]
    # この基準を較正した分類体系の版（workflow.version）。None なら照合しない（F5。docs/maintenance.md 第 3 節）
    workflow_version: str | None = None

    @property
    def origin_kind(self) -> str:
        return str(self.origin.get("kind", "workflow_start"))


def load_expectations(path: Path) -> Expectations:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    origin = doc.get("origin") or {"kind": "workflow_start"}
    if origin.get("kind") != "workflow_start":
        raise NotImplementedError("起点は workflow_start だけに対応している（v0.1）")
    stages = {
        stage: {
            kind: {cls: Interval(**iv) for cls, iv in (classes or {}).items()}
            for kind, classes in (kinds or {}).items()
        }
        for stage, kinds in (doc.get("stages") or {}).items()
    }
    outcomes = {k: Interval(**v) for k, v in (doc.get("outcomes") or {}).items()}
    return Expectations(
        name=doc["name"],
        origin=origin,
        runs=int(doc["runs"]),
        seed=int(doc.get("seed", 0)),
        stages=stages,
        outcomes=outcomes,
        workflow_version=(
            str(doc["workflow_version"]) if doc.get("workflow_version") is not None else None
        ),
    )


@dataclass(frozen=True)
class Violation:
    stage_id: str | None
    entry_kind: str | None
    cls: str
    observed: float
    interval: Interval
    n: int

    def __str__(self) -> str:
        where = f"{self.stage_id}/{self.entry_kind}" if self.stage_id else "outcomes"
        return (
            f"{where} {self.cls}: 観測 {self.observed:.3f} (n={self.n}) が区間 {self.interval} の外"
        )


@dataclass
class ExpectationReport:
    violations: list[Violation]

    @property
    def ok(self) -> bool:
        return not self.violations


def check_expectations(t: Tally, expectations: Expectations) -> ExpectationReport:
    """区間の検査。expectations が workflow_version を持ち、集計の版と違えば ValueError（版の同期。F5）。"""
    if (
        expectations.workflow_version is not None
        and t.workflow_version is not None
        and expectations.workflow_version != t.workflow_version
    ):
        raise ValueError(
            f"expectations {expectations.name!r} の workflow_version {expectations.workflow_version!r} が"
            f"実行した定義の版 {t.workflow_version!r} と違う。定義を変えたら expectations を較正し直す"
        )
    violations: list[Violation] = []
    for stage_id, kinds in expectations.stages.items():
        for kind, classes in kinds.items():
            counts = t.by_stage.get((stage_id, kind), ClassCounts())
            for cls, interval in classes.items():
                observed = counts.freq(cls)
                if not interval.contains(observed):
                    violations.append(
                        Violation(stage_id, kind, cls, observed, interval, counts.total)
                    )
    for outcome, interval in expectations.outcomes.items():
        observed = t.outcomes[outcome] / t.runs if t.runs else 0.0
        if not interval.contains(observed):
            violations.append(Violation(None, None, outcome, observed, interval, t.runs))
    return ExpectationReport(violations)


# --- 独立性検証 ---


def representative_key_default(record: EvaluationRecord) -> str:
    """代表の鍵の既定: 戻り先へ運ぶ carry の中身のハッシュ（carry が無ければ "-"）。"""
    if not record.carry_out:
        return "-"
    payload = json.dumps(record.carry_out, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _downstream(unit: Sequence[EvaluationRecord], index: int, mode: str, status: str) -> str:
    """下流のクラス。終端は run 単位の終わり方で区別する（end:completed / end:aborted / end:escalated）。"""
    rec = unit[index]
    if mode == "same_stage":
        for later in unit[index + 1 :]:
            if later.stage_id == rec.stage_id:
                return later.cls
        return f"end:{status}"
    if mode == "next":
        return unit[index + 1].cls if index + 1 < len(unit) else f"end:{status}"
    raise ValueError(mode)


def _g_statistic(table: dict[str, Counter[str]]) -> float:
    """独立性の G 統計量（分布関数は使わない。並べ替えで p 値を出す）。"""
    import math

    rows = {g: sum(c.values()) for g, c in table.items()}
    cols: Counter[str] = Counter()
    for c in table.values():
        cols.update(c)
    n = sum(rows.values())
    g = 0.0
    for grp, c in table.items():
        for cls, observed in c.items():
            expected = rows[grp] * cols[cls] / n
            if observed and expected:
                g += 2 * observed * math.log(observed / expected)
    return g


@dataclass
class IndependenceReport:
    stage_id: str
    cls: str
    groups: dict[str, Counter[str]]  # 代表の鍵 → 下流クラスの度数
    statistic: float
    p_value: float
    permutations: int
    alpha: float
    verifiable: bool = (
        True  # 群が二つ以上あり検定できたか。False は「検証不能」であって「未検出」ではない
    )

    @property
    def flagged(self) -> bool:
        return self.verifiable and self.p_value < self.alpha

    def __str__(self) -> str:
        return (
            f"independence({self.stage_id}, {self.cls}): G={self.statistic:.3f} p={self.p_value:.4f} "
            f"groups={ {k: dict(v) for k, v in self.groups.items()} }"
        )


def independence(
    samples: Iterable[RunSample],
    *,
    stage_id: str,
    cls: str,
    key: Callable[[EvaluationRecord], str] = representative_key_default,
    downstream: str = "same_stage",
    permutations: int = 200,
    seed: int = 0,
    alpha: float = 0.05,
) -> IndependenceReport:
    """クラス (stage_id, cls) の記録を代表の鍵で群に分け、下流のクラス分布が群で揃うかを調べる。

    統計量は G、p 値は群のラベルを種つきで並べ替えた分布での右側確率。
    """
    pairs: list[tuple[str, str]] = []
    for sample in samples:
        for unit, status in evaluation_units_with_status(sample.result):
            for i, rec in enumerate(unit):
                if rec.stage_id == stage_id and rec.cls == cls:
                    pairs.append((key(rec), _downstream(unit, i, downstream, status)))
    groups: dict[str, Counter[str]] = defaultdict(Counter)
    for g, d in pairs:
        groups[g][d] += 1
    if len(groups) < 2 or len(pairs) < 2:
        return IndependenceReport(stage_id, cls, dict(groups), 0.0, 1.0, 0, alpha, verifiable=False)
    observed = _g_statistic(groups)
    rng = random.Random(seed)
    labels = [g for g, _ in pairs]
    downs = [d for _, d in pairs]
    at_least = 0
    for _ in range(permutations):
        rng.shuffle(labels)
        table: dict[str, Counter[str]] = defaultdict(Counter)
        for g, d in zip(labels, downs, strict=True):
            table[g][d] += 1
        if _g_statistic(table) >= observed - 1e-12:
            at_least += 1
    p_value = (at_least + 1) / (permutations + 1)
    return IndependenceReport(stage_id, cls, dict(groups), observed, p_value, permutations, alpha)


__all__ = [
    "ClassCounts",
    "ExpectationReport",
    "Expectations",
    "IndependenceReport",
    "Interval",
    "RunSample",
    "Tally",
    "Violation",
    "check_expectations",
    "evaluation_units",
    "evaluation_units_with_status",
    "independence",
    "load_expectations",
    "representative_key_default",
    "run_many",
    "tally",
    "transition_matrix",
]
