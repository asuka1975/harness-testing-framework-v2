"""整合性検査器（計画書 testing/spec）。

公開 API:
  check_workflow(path, *, metric_names=None) -> Report
  index_workflow(doc) -> WorkflowIndex
  CODES: 検査する性質のコード集合
CLI: python -m htf.testing.spec <workflow.yaml> [--metrics manifest.json | --metrics-module pkg.mod:attr]
"""

from .checker import (
    CODES,
    MAX_SUBWORKFLOW_DEPTH,
    UNKNOWN,
    Finding,
    Report,
    StageRef,
    WorkflowIndex,
    check_workflow,
    index_workflow,
    load_yaml,
)

__all__ = [
    "CODES",
    "MAX_SUBWORKFLOW_DEPTH",
    "UNKNOWN",
    "Finding",
    "Report",
    "StageRef",
    "WorkflowIndex",
    "check_workflow",
    "index_workflow",
    "load_yaml",
]
