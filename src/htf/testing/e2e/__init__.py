"""E2E カバレッジ計画（誘発と注入）とマルコフ合成（計画書 testing/e2e）。

- enumerate_targets: 定義（親と子）から (workflow, stage, class) を列挙する。class は goal、各 end_state、unknown
- 計画（YAML）: 各対象を、台本で誘発するか、n 回目の進入の Verdict を注入して踏む
- run_plan: 計画を実行し、評価記録から到達を数える（誘発と注入を区別）
- synthesize_outcomes: 遷移行列 P(class | stage, entry_kind) から run 全体の結果を合成する（マルコフ性の仮定）。
  escalate は中止（aborted）とみなす。子を持つステージは、観測された子 run 数の分布から子の数を引き、
  子の定義を同じ仮定で合成して集約規則にかける
- compare_outcomes: 合成と実測の頻度を許容差で比べる（許容差は仮置き。ADR-013）
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from htf.contract import Verdict, VerdictKind
from htf.runtime import Runner, RunResult, Workflow
from htf.runtime.model import UNKNOWN, Stage
from htf.testing.stages import RunSample, evaluation_units

# --- 対象の列挙 ---


@dataclass(frozen=True)
class CoverageTarget:
    workflow: str
    stage_id: str
    state: str  # goal | <end_state id> | unknown

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.workflow, self.stage_id, self.state)


def enumerate_targets(workflow: Workflow) -> list[CoverageTarget]:
    targets: list[CoverageTarget] = []
    for stage in workflow.stages:
        targets.append(CoverageTarget(workflow.name, stage.id, "goal"))
        for es in stage.end_state:
            targets.append(CoverageTarget(workflow.name, stage.id, es.id))
        if stage.subworkflow is not None:
            targets.extend(enumerate_targets(stage.subworkflow.child))
    return targets


# --- 計画 ---


@dataclass(frozen=True)
class PlanEntry:
    target: CoverageTarget
    method: str  # induce | inject
    scenario: str
    outcomes: dict[str, list[str]] = field(default_factory=dict)
    human: list[str] | None = None
    inject_entry: int = 1


@dataclass(frozen=True)
class Plan:
    entries: list[PlanEntry]


def load_plan(path: Path) -> Plan:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    entries = []
    for e in doc["targets"]:
        target = CoverageTarget(e["workflow"], e["stage"], e["state"])
        if "inject" in e:
            entries.append(
                PlanEntry(
                    target,
                    "inject",
                    e["inject"]["scenario"],
                    dict(e.get("outcomes") or {}),
                    e.get("human"),
                    int(e["inject"].get("entry", 1)),
                )
            )
        else:
            entries.append(
                PlanEntry(
                    target, "induce", e["induce"], dict(e.get("outcomes") or {}), e.get("human")
                )
            )
    return Plan(entries)


def verdict_for(target: CoverageTarget) -> Verdict:
    if target.state == "goal":
        return Verdict(VerdictKind.GOAL, decided_by="qualitative")
    if target.state == UNKNOWN:
        return Verdict(VerdictKind.UNKNOWN, decided_by="threshold")
    return Verdict(VerdictKind.END_STATE, state=target.state, decided_by="classifier")


# 計画の一項目から Runner を作る。(scenario 名, outcomes の上書き, human の上書き, inject, workspace) → Runner
PlanRunnerFactory = Callable[
    [str, Mapping[str, list[str]], list[str] | None, Mapping[tuple[str, int], Verdict], Path],
    Runner,
]


@dataclass
class CoverageReport:
    targets: list[CoverageTarget]
    hits: dict[tuple[str, str, str], str]  # key → induced | injected
    results: list[RunResult]

    @property
    def uncovered(self) -> list[CoverageTarget]:
        return [t for t in self.targets if t.key not in self.hits]

    @property
    def coverage(self) -> float:
        return (
            (len(self.targets) - len(self.uncovered)) / len(self.targets) if self.targets else 1.0
        )

    @property
    def induced(self) -> list[tuple[str, str, str]]:
        return [k for k, v in self.hits.items() if v == "induced"]

    @property
    def injected(self) -> list[tuple[str, str, str]]:
        return [k for k, v in self.hits.items() if v == "injected"]


def coverage_of(results: Iterable[RunResult], targets: list[CoverageTarget]) -> CoverageReport:
    hits: dict[tuple[str, str, str], str] = {}
    results = list(results)
    for result in results:
        for unit in evaluation_units(result):
            for rec in unit:
                key = (rec.workflow, rec.stage_id, rec.cls)
                how = "injected" if rec.injected else "induced"
                if key not in hits or (hits[key] == "injected" and how == "induced"):
                    hits[key] = how
    wanted = {t.key for t in targets}
    return CoverageReport(targets, {k: v for k, v in hits.items() if k in wanted}, results)


def run_plan(
    plan: Plan, workflow: Workflow, make_runner: PlanRunnerFactory, *, workspace: Path
) -> CoverageReport:
    results: list[RunResult] = []
    for i, entry in enumerate(plan.entries):
        inject: dict[tuple[str, int], Verdict] = {}
        if entry.method == "inject":
            inject[(entry.target.stage_id, entry.inject_entry)] = verdict_for(entry.target)
        runner = make_runner(
            entry.scenario, entry.outcomes, entry.human, inject, workspace / f"plan-{i}"
        )
        result = runner.run()
        results.append(result)
    return coverage_of(results, enumerate_targets(workflow))


# --- マルコフ合成 ---

Matrix = Mapping[tuple[str, str], Mapping[str, float]]


def child_run_counts(samples: Iterable[RunSample]) -> dict[str, list[int]]:
    """子を持つステージ id → 観測された子 run 数の列（親の進入ごと）。"""
    counts: dict[str, list[int]] = {}
    for sample in samples:
        for stage_id, entries in sample.result.child_results.items():
            counts.setdefault(stage_id, []).extend(len(runs) for runs in entries)
    return counts


def _sample_class(matrix: Matrix, stage_id: str, entry: int, rng: random.Random) -> str:
    kind = "first" if entry == 1 else "reentry"
    row = matrix.get((stage_id, kind)) or matrix.get((stage_id, "first"))
    if not row:
        return "goal"
    classes = list(row)
    return rng.choices(classes, [row[c] for c in classes])[0]


def _simulate(
    workflow: Workflow,
    matrix: Matrix,
    rng: random.Random,
    counts: Mapping[str, list[int]],
    *,
    child: bool = False,
) -> tuple[str, Stage | None, str | None]:
    """一回の run を合成する。戻り値: (結果, escalate したステージ, そのクラス)。

    結果は completed / aborted（最上位）、または escalated（子 run）。
    """
    stages = workflow.stages
    pos = 0
    entries: Counter[str] = Counter()
    edge_counts: Counter[tuple[str, str]] = Counter()
    while pos < len(stages):
        stage = stages[pos]
        entries[stage.id] += 1
        if stage.subworkflow is not None:
            cls = _aggregate_simulated(stage, matrix, rng, counts)
        else:
            cls = _sample_class(matrix, stage.id, entries[stage.id], rng)
        if cls == "goal":
            pos += 1
            continue
        if cls == UNKNOWN:
            return ("escalated" if child else "aborted"), stage, UNKNOWN
        rb = stage.rollback_for(cls)
        if rb is None:
            return ("escalated" if child else "aborted"), stage, cls
        edge_counts[(stage.id, cls)] += 1
        if edge_counts[(stage.id, cls)] > rb.max:
            return ("escalated" if child else "aborted"), stage, cls
        pos = workflow.index_of(rb.stage)
    return "completed", None, None


def _aggregate_simulated(
    stage: Stage, matrix: Matrix, rng: random.Random, counts: Mapping[str, list[int]]
) -> str:
    sub = stage.subworkflow
    assert sub is not None
    observed = counts.get(stage.id) or [1]
    n = rng.choice(observed)
    outcomes: list[tuple[str, str | None, str | None]] = []
    for _ in range(n):
        outcomes.append(_simulate(sub.child, matrix, rng, counts, child=True))
    if all(o[0] == "completed" for o in outcomes):
        return "goal"
    for rule in sub.aggregate:
        matched = [
            o
            for o in outcomes
            if o[0] == "escalated"
            and o[1] is not None
            and o[1].id == rule.outcome.stage
            and o[2] == rule.outcome.state
        ]
        hit = (
            bool(matched)
            if rule.quantifier == "any"
            else (bool(outcomes) and len(matched) == len(outcomes))
        )
        if hit:
            return rule.state
    return UNKNOWN


def synthesize_outcomes(
    workflow: Workflow,
    matrix: Matrix,
    *,
    runs: int,
    seed: int = 0,
    child_counts: Mapping[str, list[int]] | None = None,
    samples: Iterable[RunSample] | None = None,
) -> Counter[str]:
    """遷移行列から run 全体の結果（completed / aborted）の度数を合成する。"""
    rng = random.Random(seed)
    counts = dict(child_counts or {})
    if not counts and samples is not None:
        counts = child_run_counts(samples)
    out: Counter[str] = Counter()
    for _ in range(runs):
        status, _stage, _cls = _simulate(workflow, matrix, rng, counts)
        out[status] += 1
    return out


@dataclass
class OutcomeComparison:
    predicted: dict[str, float]
    observed: dict[str, float]
    tolerance: float

    @property
    def deviations(self) -> dict[str, float]:
        keys = set(self.predicted) | set(self.observed)
        return {
            k: abs(self.predicted.get(k, 0.0) - self.observed.get(k, 0.0)) for k in sorted(keys)
        }

    @property
    def ok(self) -> bool:
        return all(d <= self.tolerance for d in self.deviations.values())

    def __str__(self) -> str:
        return f"predicted={self.predicted} observed={self.observed} deviations={self.deviations} tol={self.tolerance}"


def compare_outcomes(
    predicted: Counter[str], observed: Counter[str], *, tolerance: float
) -> OutcomeComparison:
    pn = sum(predicted.values()) or 1
    on = sum(observed.values()) or 1
    return OutcomeComparison(
        {k: v / pn for k, v in predicted.items()},
        {k: v / on for k, v in observed.items()},
        tolerance,
    )


__all__ = [
    "CoverageReport",
    "CoverageTarget",
    "OutcomeComparison",
    "Plan",
    "PlanEntry",
    "child_run_counts",
    "compare_outcomes",
    "coverage_of",
    "enumerate_targets",
    "load_plan",
    "run_plan",
    "synthesize_outcomes",
    "verdict_for",
]
