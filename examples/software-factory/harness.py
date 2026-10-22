"""software-factory を参照ランタイムに組み込む（adopting.md 3.7 の手順）。

- 台本（fixtures/scenarios/*.yaml）を Scenario に、確率的な構成（fixtures/profiles/*.yaml）を Profile に読む
- 本体・指標・分類器・ユーザー入出力・人間を Bindings に束ねる。LLM は束縛しない（本体は LLM を呼ばない）
- Runner / ReferenceRuntime の組み立てはここに一つだけ置き、契約適合テスト・決定論テスト・分布テスト・
  E2E 計画が同じ組み込み方を使う
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from htf.contract import (
    Abort,
    Classifier,
    ContinueAsGoal,
    Escalation,
    HumanDecider,
    MetricRegistry,
    Rerun,
    Resolution,
    RollbackTo,
    StageBody,
    UserIO,
    Verdict,
)
from htf.runtime import (
    DEFAULT_THRESHOLD,
    Bindings,
    DictMetricRegistry,
    Recorder,
    ReferenceRuntime,
    Runner,
    Workflow,
    load_workflow,
)
from htf.testing.harness import DeferringUserIO, MarkerClassifier, QueueUserIO, ScriptedHuman

from . import metrics as _metrics
from .stages import (
    Analyze,
    Code,
    Design,
    Implement,
    Intake,
    Plan,
    Release,
    Review,
    Script,
    StochasticSource,
    UnitTest,
    Verify,
)
from .user import PersonaUserIO

ROOT = Path(__file__).parent
WORKFLOW_PATH = ROOT / "workflow.yaml"
CHILD_PATH = ROOT / "implement-task.yaml"
MANIFEST_PATH = _metrics.MANIFEST_PATH
WORKFLOW_NAME = "software-factory"
CHILD_NAME = "implement-task"
SCENARIO_DIR = ROOT / "fixtures" / "scenarios"
PROFILE_DIR = ROOT / "fixtures" / "profiles"
# 分類器の確信度の閾値。htf の既定（0.5、較正前の仮置き）をそのまま使う。偽の分類器は 1.0 か 0.1 しか返さない
THRESHOLD = DEFAULT_THRESHOLD

Source = Script | StochasticSource


def registry() -> DictMetricRegistry:
    return _metrics.registry()


def load() -> Workflow:
    """検査を通った定義（親と子）を読む。"""
    return load_workflow(WORKFLOW_PATH, metric_names=registry().names())


def unit_coverage_min(workflow: Workflow) -> float:
    """子 unit_test の unit_coverage の基準（定義が唯一の情報源。本体の印もこの値で決める）。"""
    child = workflow.stage("implement").subworkflow.child  # type: ignore[union-attr]
    criterion = child.stage("unit_test").goal.quantitative["unit_coverage"]
    assert criterion.min is not None
    return float(criterion.min)


def make_bodies(source: Source, workflow: Workflow) -> dict[tuple[str, str], StageBody]:
    return {
        (WORKFLOW_NAME, "intake"): Intake(source),
        (WORKFLOW_NAME, "analyze"): Analyze(source),
        (WORKFLOW_NAME, "design"): Design(source),
        (WORKFLOW_NAME, "plan"): Plan(source),
        (WORKFLOW_NAME, "implement"): Implement(),
        (WORKFLOW_NAME, "verify"): Verify(source),
        (WORKFLOW_NAME, "review"): Review(source),
        (WORKFLOW_NAME, "release"): Release(source),
        (CHILD_NAME, "code"): Code(source),
        (CHILD_NAME, "unit_test"): UnitTest(source, unit_coverage_min(workflow)),
    }


# --- 組み込み方（一か所） ---


def reference_runtime(
    workflow: Workflow, bindings: Bindings, *, workspace: Path, recorder: Recorder | None = None
) -> ReferenceRuntime:
    return ReferenceRuntime(
        workflow, bindings, workspace=workspace, threshold=THRESHOLD, recorder=recorder
    )


def runner(
    workflow: Workflow,
    bindings: Bindings,
    *,
    workspace: Path,
    recorder: Recorder | None = None,
    inject: Mapping[tuple[str, str, int], Verdict] | None = None,
) -> Runner:
    return Runner(
        workflow,
        bindings,
        workspace=workspace,
        threshold=THRESHOLD,
        recorder=recorder,
        inject=inject,
    )


def conformance_runtime(
    workflow_path: Path,
    bodies: Mapping[tuple[str, str], StageBody],
    registry: MetricRegistry,
    classifier: Classifier,
    user: UserIO | None,
    *,
    workspace: Path,
) -> ReferenceRuntime:
    """契約適合テストの工場（htf.contract.conformance.RuntimeFactory）。ハーネスと同じ組み込み方を使う。"""
    workflow = load_workflow(workflow_path, metric_names=registry.names())
    bindings = Bindings(bodies=bodies, registry=registry, classifier=classifier, user=user)
    return reference_runtime(workflow, bindings, workspace=workspace)


# --- 台本（決定論テスト・E2E 計画） ---


@dataclass(frozen=True)
class Scenario:
    name: str
    persona: str = "product_owner"
    user: str = (
        "simulator"  # simulator（ペルソナ）| deferring（常に中断。answers を resume で与える）
    )
    answers: list = field(default_factory=list)
    outcomes: dict[str, list[str]] = field(default_factory=dict)
    child_runs: list[dict[str, list[str]]] = field(default_factory=list)
    human: list[str] = field(default_factory=list)
    expect: dict = field(default_factory=dict)

    @property
    def resolutions(self) -> list[Resolution]:
        return [parse_resolution(h) for h in self.human]

    def with_outcomes(self, **outcomes: list[str]) -> Scenario:
        return dataclasses.replace(self, outcomes={**self.outcomes, **outcomes})


def parse_resolution(text: str) -> Resolution:
    if text == "abort":
        return Abort(note="台本")
    if text == "rerun":
        return Rerun(note="台本")
    if text == "continue_as_goal":
        return ContinueAsGoal(note="台本: goal 扱いで続行")
    if text.startswith("rollback_to:"):
        return RollbackTo(stage=text.split(":", 1)[1], note="台本")
    raise ValueError(f"未知の解決 {text!r}")


def scenario_names() -> list[str]:
    return sorted(p.stem for p in SCENARIO_DIR.glob("*.yaml"))


def load_scenario(name_or_path: str | Path) -> Scenario:
    path = Path(name_or_path)
    if not path.suffix:
        path = SCENARIO_DIR / f"{name_or_path}.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    unknown = set(doc) - {f.name for f in dataclasses.fields(Scenario)}
    if unknown:
        raise ValueError(f"台本 {path.name} に未知の項目 {sorted(unknown)}")
    return Scenario(**doc)


def scenario_user(scenario: Scenario) -> UserIO:
    if scenario.user == "simulator":
        return PersonaUserIO(scenario.persona)
    if scenario.user == "deferring":
        return DeferringUserIO()
    if scenario.user == "queue":
        return QueueUserIO(scenario.answers)
    raise ValueError(f"未知の user {scenario.user!r}")


def make_bindings(
    scenario: Scenario,
    workflow: Workflow,
    *,
    human: HumanDecider | None = None,
    replay: bool = False,
) -> Bindings:
    """台本から束縛を組み立てる。replay=True なら分類器・ユーザーを外す（recorder が再生する）。"""
    bodies = make_bodies(Script(scenario.outcomes, scenario.child_runs), workflow)
    human = human if human is not None else ScriptedHuman(scenario.resolutions)
    if replay:
        return Bindings(bodies=bodies, registry=registry(), classifier=None, human=human)
    return Bindings(
        bodies=bodies,
        registry=registry(),
        classifier=MarkerClassifier(),
        user=scenario_user(scenario),
        human=human,
    )


def make_plan_runner(
    scenario_name: str,
    outcomes: Mapping[str, list[str]],
    human: list[str] | None,
    inject: Mapping[tuple[str, str, int], Verdict],
    workspace: Path,
) -> Runner:
    """E2E 計画の一項目から Runner を作る（htf.testing.e2e.run_plan の工場）。

    中断する台本（user: deferring）は、E2E では中断させずにペルソナに答えさせる。
    """
    scenario = load_scenario(scenario_name)
    if outcomes:
        scenario = scenario.with_outcomes(**{k: list(v) for k, v in outcomes.items()})
    if human is not None:
        scenario = dataclasses.replace(scenario, human=list(human))
    if scenario.user != "simulator":
        scenario = dataclasses.replace(scenario, user="simulator")
    workflow = load()
    return runner(workflow, make_bindings(scenario, workflow), workspace=workspace, inject=inject)


# --- 確率的な構成（分布テスト・独立性・マルコフ合成） ---


@dataclass(frozen=True)
class Profile:
    """確率的偽本体の構成。distributions はステージ → first | reentry → 値 → 確率。split は任意。"""

    name: str
    persona: str
    human: list[str]
    distributions: dict[str, dict[str, dict[str, float]]]
    split: dict | None = None


def load_profile(name: str) -> Profile:
    doc = yaml.safe_load((PROFILE_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    return Profile(
        name=doc["name"],
        persona=doc.get("persona", "product_owner"),
        human=list(doc.get("human") or ["abort"]),
        distributions={
            s: {k: dict(d) for k, d in kinds.items()} for s, kinds in doc["distributions"].items()
        },
        split=doc.get("split"),
    )


class RepeatingHuman:
    """escalate のたびに同じ解決の列を繰り返す（分布テストでは run を止めるだけ）。"""

    def __init__(self, resolutions: list[Resolution]) -> None:
        self._resolutions = list(resolutions)
        self._i = 0

    def resolve(self, escalation: Escalation) -> Resolution:
        r = self._resolutions[min(self._i, len(self._resolutions) - 1)]
        self._i += 1
        return r


def make_stochastic_runner(profile: Profile, *, seed: int, workspace: Path) -> Runner:
    """profile の分布から変種を引く偽本体で Runner を作る。成果物を書くコードは台本の時と同じ。"""
    workflow = load()
    source = StochasticSource(profile.distributions, seed=seed, split=profile.split)
    bindings = Bindings(
        bodies=make_bodies(source, workflow),
        registry=registry(),
        classifier=MarkerClassifier(),
        user=PersonaUserIO(profile.persona),
        human=RepeatingHuman([parse_resolution(h) for h in profile.human]),
    )
    return runner(workflow, bindings, workspace=workspace)
