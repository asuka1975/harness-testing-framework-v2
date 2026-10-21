"""toy-minimal を参照ランタイムに組み込む（adopting.md の手順の実例）。

- 台本（tests/fixtures/scenarios/*.yaml）を Scenario に読む
- 本体・指標・分類器・ユーザー入出力・LLM を Bindings に束ねる
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from htf.contract import (
    Abort,
    ContinueAsGoal,
    Escalation,
    HumanDecider,
    Rerun,
    Resolution,
    RollbackTo,
    Verdict,
)
from htf.runtime import Bindings, DictMetricRegistry, Runner, load_workflow
from htf.testing.harness import DeferringUserIO, EchoLLM, MarkerClassifier, ScriptedHuman

from . import metrics as _metrics
from .stages import (
    CheckSection,
    ChildScriptCursor,
    Collect,
    Draft,
    Elaborate,
    ScriptCursor,
    StochasticSource,
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
SCENARIO_DIR = ROOT / "tests" / "fixtures" / "scenarios"


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


# --- F3: 確率的偽本体の構成（profile）と、分布テスト / E2E 計画のための Runner の組み立て ---


@dataclass(frozen=True)
class Profile:
    """確率的偽本体の構成。分布は stage → first | reentry → class → 確率。split は任意。"""

    name: str
    title: str
    claims: list[str]
    human: list[str]
    distributions: dict[str, dict[str, dict[str, float]]]
    split: dict | None = None


def load_profile(path: Path) -> Profile:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Profile(
        name=doc["name"],
        title=doc.get("title", "題目"),
        claims=list(doc["claims"]),
        human=list(doc.get("human") or ["abort"]),
        distributions={
            s: {k: dict(d) for k, d in kinds.items()} for s, kinds in doc["distributions"].items()
        },
        split=doc.get("split"),
    )


class _RepeatingHuman:
    """escalate のたびに同じ解決の列を繰り返す（分布テストでは run を止めるだけ）。"""

    def __init__(self, resolutions: list) -> None:
        self._resolutions = list(resolutions)
        self._i = 0

    def resolve(self, escalation: Escalation):  # noqa: ANN201
        r = self._resolutions[min(self._i, len(self._resolutions) - 1)]
        self._i += 1
        return r


def _workflow():  # noqa: ANN202
    return load_workflow(WORKFLOW_PATH, metric_names=registry().names())


def make_stochastic_runner(profile: Profile, *, seed: int, workspace: Path) -> Runner:
    """profile の分布から結果を引く偽本体で Runner を作る。本体の成果物を書くコードは決定論的本体と同じ。"""
    source = StochasticSource(profile.distributions, profile.claims, seed=seed, split=profile.split)
    bodies = {
        (WORKFLOW_NAME, "collect"): Collect(source),  # type: ignore[arg-type]
        (WORKFLOW_NAME, "draft"): Draft(source),  # type: ignore[arg-type]
        (WORKFLOW_NAME, "verify"): Verify(source),  # type: ignore[arg-type]
        (WORKFLOW_NAME, "elaborate"): Elaborate(),
        (CHILD_NAME, "write_section"): WriteSection(source),  # type: ignore[arg-type]
        (CHILD_NAME, "check_section"): CheckSection(source),  # type: ignore[arg-type]
    }
    bindings = Bindings(
        bodies=bodies,
        registry=registry(),
        classifier=MarkerClassifier(),
        user=PersonaUserIO(profile.title, profile.claims),
        llm=EchoLLM(),
        human=_RepeatingHuman([_parse_resolution(h) for h in profile.human]),
    )
    return Runner(_workflow(), bindings, workspace=workspace)


def make_plan_runner(
    scenario_name: str,
    outcomes: Mapping[str, list[str]],
    human: list[str] | None,
    inject: Mapping[tuple[str, int], Verdict],
    workspace: Path,
) -> Runner:
    """E2E 計画の一項目から Runner を作る（htf.testing.e2e.run_plan の工場）。"""
    scenario = load_scenario(SCENARIO_DIR / f"{scenario_name}.yaml")
    if outcomes:
        scenario = scenario.with_outcomes(**{k: list(v) for k, v in outcomes.items()})
    if human is not None:
        scenario = dataclasses.replace(scenario, human=list(human))
    if scenario.user == "deferring":
        scenario = dataclasses.replace(scenario, user="simulator")
    bindings = make_bindings(scenario, human=ScriptedHuman(scenario.resolutions))
    return Runner(_workflow(), bindings, workspace=workspace, inject=inject)
