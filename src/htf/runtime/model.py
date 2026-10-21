"""ワークフロー定義の型付きモデル。loader が検査器を通した文書から組み立てる。

実行時の遷移とゲートはすべてこのモデル（= YAML）から駆動され、ステージ順や遷移をコードに書かない。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from htf.contract import JsonValue

UNKNOWN = "unknown"


class MetricError(Exception):
    """指標が値を返せない、または基準と比べられない（→ unknown。CONTRACT 第 4 節 1）。"""


@dataclass(frozen=True)
class Criterion:
    description: str
    kind: Literal["equals", "range"]
    equals: JsonValue = None
    min: float | None = None
    max: float | None = None

    def satisfied(self, value: JsonValue) -> bool:
        if self.kind == "equals":
            return value == self.equals
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise MetricError(f"数値基準に対して数値でない値 {value!r}")
        if self.min is not None and value < self.min:
            return False
        return not (self.max is not None and value > self.max)

    @staticmethod
    def from_doc(doc: dict) -> Criterion:
        if "equals" in doc:
            return Criterion(doc["description"], "equals", equals=doc["equals"])
        return Criterion(doc["description"], "range", min=doc.get("min"), max=doc.get("max"))


@dataclass(frozen=True)
class Goal:
    qualitative: str
    quantitative: dict[str, Criterion]

    @staticmethod
    def from_doc(doc: dict) -> Goal:
        return Goal(
            doc["qualitative"],
            {name: Criterion.from_doc(c) for name, c in doc["quantitative"].items()},
        )


@dataclass(frozen=True)
class EndState:
    id: str
    description: str


@dataclass(frozen=True)
class Rollback:
    state: str
    stage: str
    carry: list[str]
    max: int


@dataclass(frozen=True)
class Artifacts:
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    memory_in: list[str] = field(default_factory=list)
    memory_out: list[str] = field(default_factory=list)

    @staticmethod
    def from_doc(doc: dict | None) -> Artifacts:
        doc = doc or {}
        return Artifacts(
            list(doc.get("reads") or []),
            list(doc.get("writes") or []),
            list(doc.get("memory_in") or []),
            list(doc.get("memory_out") or []),
        )


@dataclass(frozen=True)
class ChildOutcomeRef:
    stage: str
    state: str


@dataclass(frozen=True)
class AggregateRule:
    state: str
    quantifier: Literal["any", "all"]
    outcome: ChildOutcomeRef


@dataclass(frozen=True)
class Subworkflow:
    ref: str
    child: Workflow
    each: str
    item_as: str
    pass_: list[str]
    workspace: str
    aggregate: list[AggregateRule]


@dataclass(frozen=True)
class Stage:
    id: str
    name: str
    description: str
    artifacts: Artifacts
    user_input: bool
    subworkflow: Subworkflow | None
    goal: Goal
    end_state: list[EndState]
    rollback: list[Rollback]

    def end_state_ids(self) -> list[str]:
        return [e.id for e in self.end_state]

    def rollback_for(self, state: str) -> Rollback | None:
        return next((r for r in self.rollback if r.state == state), None)


@dataclass(frozen=True)
class Phase:
    id: str
    name: str
    description: str
    goal: Goal
    stages: list[Stage]


@dataclass(frozen=True)
class Workflow:
    name: str
    description: str
    version: str | None
    inputs: list[str]
    phases: list[Phase]
    path: Path

    @property
    def stages(self) -> list[Stage]:
        return [s for p in self.phases for s in p.stages]

    def stage(self, stage_id: str) -> Stage:
        for s in self.stages:
            if s.id == stage_id:
                return s
        raise KeyError(stage_id)

    def index_of(self, stage_id: str) -> int:
        return [s.id for s in self.stages].index(stage_id)

    def phase(self, stage_id: str) -> Phase:
        for p in self.phases:
            if any(s.id == stage_id for s in p.stages):
                return p
        raise KeyError(stage_id)

    def phase_of(self, stage_id: str) -> str:
        return self.phase(stage_id).id

    def phase_index_of(self, stage_id: str) -> int:
        return [p.id for p in self.phases].index(self.phase_of(stage_id))

    def is_last_in_phase(self, stage_id: str) -> bool:
        return self.phase(stage_id).stages[-1].id == stage_id


def build_workflow(doc: dict, path: Path, *, child_loader) -> Workflow:
    """検査済みの文書からモデルを組み立てる。child_loader(path) は子の Workflow を返す。"""
    w = doc["workflow"]
    phases = []
    for p in w["phases"]:
        stages = []
        for s in p["stages"]:
            sub = None
            if "subworkflow" in s:
                sd = s["subworkflow"]
                child_path = (path.parent / sd["ref"]).resolve()
                sub = Subworkflow(
                    ref=sd["ref"],
                    child=child_loader(child_path),
                    each=sd["each"],
                    item_as=sd["item_as"],
                    pass_=list(sd.get("pass") or []),
                    workspace=sd["workspace"],
                    aggregate=[
                        AggregateRule(
                            r["state"],
                            next(iter(r["when"])),
                            ChildOutcomeRef(**next(iter(r["when"].values()))),
                        )
                        for r in sd["aggregate"]
                    ],
                )
            stages.append(
                Stage(
                    id=s["id"],
                    name=s["name"],
                    description=s["description"],
                    artifacts=Artifacts.from_doc(s.get("artifacts")),
                    user_input=bool(s.get("user_input", False)),
                    subworkflow=sub,
                    goal=Goal.from_doc(s["goal"]),
                    end_state=[EndState(e["id"], e["description"]) for e in s["end_state"]],
                    rollback=[
                        Rollback(r["state"], r["stage"], list(r.get("carry") or []), int(r["max"]))
                        for r in s["rollback"]
                    ],
                )
            )
        phases.append(Phase(p["id"], p["name"], p["description"], Goal.from_doc(p["goal"]), stages))
    return Workflow(
        name=w["name"],
        description=w["description"],
        version=w.get("version"),
        inputs=list(w.get("inputs") or []),
        phases=phases,
        path=path,
    )
