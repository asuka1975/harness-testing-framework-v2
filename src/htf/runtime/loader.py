"""loader: 整合性検査を通った定義だけを読む。仕様は唯一の情報源（第2節）。"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from htf.testing.spec import Finding, Report, check_workflow, load_yaml

from .model import Workflow, build_workflow


class WorkflowDefinitionError(Exception):
    """定義が整合性検査を通らない。findings に所見。"""

    def __init__(self, report: Report) -> None:
        lines = [f"{f.file}:{f.path} [{f.code}] {f.message}" for f in report.findings]
        super().__init__("ワークフロー定義が整合性検査を通らない:\n" + "\n".join(lines))
        self.report = report
        self.findings: list[Finding] = list(report.findings)


def load_workflow(path: str | Path, *, metric_names: Iterable[str] | None = None) -> Workflow:
    """定義を検査してモデルにする。子も再帰的に読む（子は親の検査で一緒に検査済み）。"""
    path = Path(path).resolve()
    report = check_workflow(path, metric_names=metric_names)
    if report.findings:
        raise WorkflowDefinitionError(report)
    return _build(path)


def _build(path: Path) -> Workflow:
    doc = load_yaml(path)
    assert isinstance(doc, dict)
    return build_workflow(doc, path, child_loader=_build)
