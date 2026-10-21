"""toy-minimal を参照ランタイムに組み込む（adopting.md の手順の実例）。

- 台本（tests/fixtures/scenarios/*.yaml）を Scenario に読む
- 本体・指標・分類器・ユーザー入出力・LLM を Bindings に束ねる
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from htf.contract import Abort, ContinueAsGoal, HumanDecider, Rerun, Resolution, RollbackTo
from htf.runtime import Bindings, DictMetricRegistry
from htf.testing.harness import DeferringUserIO, EchoLLM, MarkerClassifier

from . import metrics as _metrics
from .stages import (
    CheckSection,
    ChildScriptCursor,
    Collect,
    Draft,
    Elaborate,
    ScriptCursor,
    Verify,
    WriteSection,
)
from .user import PersonaUserIO

ROOT = Path(__file__).parent
WORKFLOW_PATH = ROOT / "workflow.yaml"
CHILD_PATH = ROOT / "elaborate-claim.yaml"
MANIFEST_PATH = _metrics.MANIFEST_PATH
WORKFLOW_NAME = "toy-minimal"
CHILD_NAME = "elaborate-claim"


@dataclass(frozen=True)
class Scenario:
    name: str
    title: str = "題目"
    claims: list[str] = field(default_factory=lambda: ["主張A"])
    empty_grounds_first: list[str] = field(default_factory=list)
    outcomes: dict[str, list[str]] = field(default_factory=dict)
    child_runs: list[dict[str, list[str]]] = field(default_factory=list)
    user: str = "simulator"  # simulator | deferring
    answers: list = field(default_factory=list)
    human: list[str] = field(default_factory=list)
    expect: dict = field(default_factory=dict)

    @property
    def resolutions(self) -> list[Resolution]:
        return [_parse_resolution(h) for h in self.human]

    def with_outcomes(self, **outcomes: list[str]) -> Scenario:
        return dataclasses.replace(self, outcomes={**self.outcomes, **outcomes})

    def with_claims(self, claims: list[str]) -> Scenario:
        return dataclasses.replace(self, claims=list(claims))


def _parse_resolution(text: str) -> Resolution:
    if text == "abort":
        return Abort(note="台本")
    if text == "rerun":
        return Rerun(note="台本")
    if text == "continue_as_goal":
        return ContinueAsGoal(note="台本: goal 扱いで続行")
    if text.startswith("rollback_to:"):
        return RollbackTo(stage=text.split(":", 1)[1], note="台本")
    raise ValueError(f"未知の解決 {text!r}")


def scenario_from_dict(doc: dict) -> Scenario:
    known = {f.name for f in dataclasses.fields(Scenario)}
    unknown = set(doc) - known
    if unknown:
        raise ValueError(f"台本に未知の項目 {sorted(unknown)}")
    return Scenario(**doc)


def load_scenario(path: Path) -> Scenario:
    return scenario_from_dict(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def registry() -> DictMetricRegistry:
    return _metrics.registry()


def make_bindings(
    scenario: Scenario, *, human: HumanDecider | None = None, replay: bool = False
) -> Bindings:
    """台本から束縛を組み立てる。replay=True なら LLM・分類器・ユーザーを外す（recorder が再生する）。"""
    cursor = ScriptCursor(scenario.outcomes)
    child_cursor = ChildScriptCursor(scenario.child_runs)
    bodies = {
        (WORKFLOW_NAME, "collect"): Collect(cursor, scenario.empty_grounds_first),
        (WORKFLOW_NAME, "draft"): Draft(cursor),
        (WORKFLOW_NAME, "verify"): Verify(cursor),
        (WORKFLOW_NAME, "elaborate"): Elaborate(),
        (CHILD_NAME, "write_section"): WriteSection(child_cursor),
        (CHILD_NAME, "check_section"): CheckSection(child_cursor),
    }
    if replay:
        return Bindings(bodies=bodies, registry=registry(), classifier=None, human=human)
    user = (
        PersonaUserIO(scenario.title, scenario.claims)
        if scenario.user == "simulator"
        else DeferringUserIO()
    )
    return Bindings(
        bodies=bodies,
        registry=registry(),
        classifier=MarkerClassifier(),
        user=user,
        llm=EchoLLM(),
        human=human,
    )
