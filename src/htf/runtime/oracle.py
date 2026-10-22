"""oracle 基盤: 指標レジストリ、投影、評価順序（CONTRACT 第 4 節）、子 run の集約（第 7 節）。

分類ロジックはコードに書かない。分類器には goal と end_state の記述をそのまま選択肢として渡す。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from htf.contract import (
    ChildOutcome,
    Classification,
    Classifier,
    ClassOption,
    JsonValue,
    Metric,
    MetricRegistry,
    Snapshot,
    Verdict,
    VerdictKind,
)

from .checkpoint import META_DIR
from .model import UNKNOWN, Goal, MetricError, Stage

GOAL_OPTION = "goal"
MAX_FILE_CHARS = 4000


class DictMetricRegistry:
    """名前 → 指標関数の辞書によるレジストリ。"""

    def __init__(self, metrics: Mapping[str, Metric]) -> None:
        self._metrics = dict(metrics)

    def names(self) -> list[str]:
        return sorted(self._metrics)

    def resolve(self, name: str) -> Metric:
        try:
            return self._metrics[name]
        except KeyError as e:
            raise MetricError(f"指標 {name!r} がレジストリに無い") from e


def evaluate_metrics(
    goal: Goal, snapshot: Snapshot, registry: MetricRegistry
) -> tuple[bool, dict[str, JsonValue], list[str]]:
    """(すべて成立したか, 指標の値, 不成立の指標名)。値を返せない指標があれば MetricError。"""
    values: dict[str, JsonValue] = {}
    failed: list[str] = []
    for name, criterion in goal.quantitative.items():
        try:
            value = registry.resolve(name)(snapshot)
        except MetricError:
            raise
        except Exception as e:  # noqa: BLE001 — 指標の失敗は評価不能として unknown に落とす
            raise MetricError(f"指標 {name!r} が値を返せない: {e!r}") from e
        values[name] = value
        if not criterion.satisfied(value):
            failed.append(name)
    return (not failed), values, failed


def _render_file(root: Path, rel: str, max_chars: int = MAX_FILE_CHARS) -> str:
    path = root / rel
    if rel.endswith("/"):
        if not path.is_dir():
            return f"### {rel}\n（無い）\n"
        parts = [f"### {rel}\n"]
        for p in sorted(path.rglob("*")):
            if p.is_file() and META_DIR not in p.relative_to(path).parts:
                parts.append(_render_file(root, p.relative_to(root).as_posix(), max_chars))
        return "".join(parts)
    if not path.is_file():
        return f"### {rel}\n（無い）\n"
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return f"### {rel}\n（バイナリ {len(data)} bytes）\n"
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n…（{len(text) - max_chars} 文字省略）"
    return f"### {rel}\n```\n{text}\n```\n"


def project(
    stage: Stage,
    snapshot: Snapshot,
    workspace: Path,
    *,
    max_file_chars: int = MAX_FILE_CHARS,
    max_document_chars: int | None = None,
) -> str:
    """分類器に渡す状態文書。memory_in ∪ writes ∪ reads の順に組み立てる（CONTRACT 第 5.4 節）。

    writes（このステージの成果物。判定の根拠）を reads（前方のステージの成果物。参照）より前に置く（ADR-014 14.5 (b)）。
    reads は作業ディレクトリから、writes はスナップショットから読む。1 ファイルは max_file_chars で切る
    （既定 4000。adopting-gaps G-08）。文書全体は max_document_chars で切る（None は無制限。14.5 (a)）。
    切り詰めは明示の印で示す。要旨は成果物の先頭に置く。
    """
    import json

    parts = [f"# stage: {stage.id}\n", "## memory_in\n"]
    for key in stage.artifacts.memory_in:
        if key in snapshot.memory:
            parts.append(
                f"- {key}: {json.dumps(snapshot.memory[key], ensure_ascii=False, sort_keys=True)}\n"
            )
    parts.append("## writes\n")
    for rel in stage.artifacts.writes:
        parts.append(_render_file(snapshot.files, rel, max_file_chars))
    parts.append("## reads\n")
    for rel in stage.artifacts.reads:
        parts.append(_render_file(workspace, rel, max_file_chars))
    document = "".join(parts)
    if max_document_chars is not None and len(document) > max_document_chars:
        omitted = len(document) - max_document_chars
        document = document[:max_document_chars] + f"\n…（文書全体 {omitted} 文字省略）\n"
    return document


def class_options(stage: Stage) -> list[ClassOption]:
    return [ClassOption(GOAL_OPTION, stage.goal.qualitative)] + [
        ClassOption(e.id, e.description) for e in stage.end_state
    ]


def evaluate_stage_detailed(
    stage: Stage,
    snapshot: Snapshot,
    *,
    workspace: Path,
    registry: MetricRegistry,
    classifier: Classifier,
    threshold: float,
    max_file_chars: int = MAX_FILE_CHARS,
    max_document_chars: int | None = None,
) -> tuple[Verdict, str | None, Classification | None]:
    """CONTRACT 第 4 節の順序: goal 指標 → goal 定性 → end_state → unknown。

    判定に加えて、分類器に渡した状態文書と分類結果を返す（評価ログ・トリアージ・コーパスの元）。
    """
    try:
        metrics_ok, _values, failed = evaluate_metrics(stage.goal, snapshot, registry)
    except MetricError as e:
        return (
            Verdict(VerdictKind.UNKNOWN, decided_by="quantitative", reason=f"評価不能: {e}"),
            None,
            None,
        )

    document = project(
        stage,
        snapshot,
        workspace,
        max_file_chars=max_file_chars,
        max_document_chars=max_document_chars,
    )
    result = classifier.classify(document, class_options(stage))
    confident = result.confidence >= threshold

    if result.option_id == GOAL_OPTION and confident:
        if metrics_ok:
            verdict = Verdict(
                VerdictKind.GOAL, confidence=result.confidence, decided_by="qualitative", reason=""
            )
        else:
            verdict = Verdict(
                VerdictKind.UNKNOWN,
                confidence=result.confidence,
                decided_by="quantitative",
                reason=f"指標 {failed} が不成立だが分類器は goal を選んだ（不一致）",
            )
    elif result.option_id != UNKNOWN and result.option_id in stage.end_state_ids() and confident:
        verdict = Verdict(
            VerdictKind.END_STATE,
            state=result.option_id,
            confidence=result.confidence,
            decided_by="classifier",
        )
    else:
        verdict = Verdict(
            VerdictKind.UNKNOWN,
            confidence=result.confidence,
            decided_by="threshold",
            reason=f"分類器の選択 {result.option_id!r}（確信度 {result.confidence}）",
        )
    return verdict, document, result


def evaluate_stage(
    stage: Stage,
    snapshot: Snapshot,
    *,
    workspace: Path,
    registry: MetricRegistry,
    classifier: Classifier,
    threshold: float,
) -> Verdict:
    verdict, _document, _result = evaluate_stage_detailed(
        stage,
        snapshot,
        workspace=workspace,
        registry=registry,
        classifier=classifier,
        threshold=threshold,
    )
    return verdict


def aggregate_children(
    stage: Stage, outcomes: Sequence[ChildOutcome], snapshot: Snapshot, registry: MetricRegistry
) -> Verdict:
    """子を持つステージの判定（CONTRACT 第 7 節 4）。分類器は呼ばない。"""
    assert stage.subworkflow is not None
    try:
        metrics_ok, _values, failed = evaluate_metrics(stage.goal, snapshot, registry)
    except MetricError as e:
        return Verdict(VerdictKind.UNKNOWN, decided_by="quantitative", reason=f"評価不能: {e}")

    if all(o.kind == "goal" for o in outcomes):
        if metrics_ok:
            return Verdict(VerdictKind.GOAL, decided_by="aggregate", reason="全ての子 run が goal")
        return Verdict(
            VerdictKind.UNKNOWN,
            decided_by="quantitative",
            reason=f"全ての子 run が goal だが指標 {failed} が不成立",
        )

    for rule in stage.subworkflow.aggregate:
        matched = [
            o
            for o in outcomes
            if o.kind != "goal" and o.stage == rule.outcome.stage and o.state == rule.outcome.state
        ]
        hit = (
            bool(matched)
            if rule.quantifier == "any"
            else (bool(outcomes) and len(matched) == len(outcomes))
        )
        if not hit:
            continue
        reason = f"規則 {rule.quantifier} ({rule.outcome.stage}, {rule.outcome.state}) が成立"
        if rule.state == UNKNOWN:
            return Verdict(VerdictKind.UNKNOWN, decided_by="aggregate", reason=reason)
        return Verdict(
            VerdictKind.END_STATE, state=rule.state, decided_by="aggregate", reason=reason
        )
    return Verdict(
        VerdictKind.UNKNOWN, decided_by="aggregate", reason="集約規則に該当する終わり方が無い"
    )
