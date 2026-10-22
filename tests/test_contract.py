"""契約モジュールの形の検査（意味は F2 の契約適合テストで確かめる）。

- 公開名が __all__ と一致して import できる
- 遷移は 7 種（計画書の 6 種 + 決定 #9 の集約。ADR-011 11.13）
- escalate の解決は 4 種（決定 #3）
- 三層は goal / end_state / unknown
- MetricRegistry は runtime_checkable で、names / resolve を持つものを受け入れる
"""

from __future__ import annotations

import htf.contract as contract
from htf.contract import (
    Abort,
    ContinueAsGoal,
    MetricRegistry,
    Rerun,
    RollbackTo,
    TransitionKind,
    VerdictKind,
    WaitingForUser,
)


def test_all_exports_resolve() -> None:
    for name in contract.__all__:
        assert hasattr(contract, name), name
    assert sorted(contract.__all__) == list(contract.__all__)


def test_seven_transition_kinds() -> None:
    assert {k.value for k in TransitionKind} == {
        "next",
        "rollback_within_phase",
        "rollback_across_phase",
        "escalate_unknown",
        "escalate_max_exceeded",
        "suspend_resume",
        "subworkflow_aggregate",
    }


def test_three_layers_and_four_resolutions() -> None:
    assert {k.value for k in VerdictKind} == {"goal", "end_state", "unknown"}
    resolutions = (Rerun(), RollbackTo(stage="draft"), ContinueAsGoal(note="人間の上書き"), Abort())
    assert len({type(r) for r in resolutions}) == 4


def test_metric_registry_is_structural() -> None:
    class Registry:
        def names(self) -> list[str]:
            return ["draft_exists"]

        def resolve(self, name: str):  # noqa: ANN202
            return lambda snapshot: True

    assert isinstance(Registry(), MetricRegistry)


def test_runtime_protocol_includes_start_and_three_operations() -> None:
    """ADR-012 12.14: 開始時スナップショットの取得 start を契約の操作に含める。"""
    from htf.contract import Runtime

    for name in ("start", "run", "evaluate", "restore", "overlay"):
        assert callable(getattr(Runtime, name)), name


def test_escalation_cause_includes_phase_gate_failed() -> None:
    """ADR-012 12.15: フェーズゲート不成立の escalate は cause で区別できる。"""
    from htf.contract import Escalation, Snapshot, Verdict

    snapshot = Snapshot("w", None, "s", "end", 0, Path("."))
    e = Escalation("s", Verdict(VerdictKind.UNKNOWN), "phase_gate_failed", snapshot)
    assert e.cause == "phase_gate_failed"


def test_waiting_for_user_carries_question() -> None:
    e = WaitingForUser("題目は?", schema={"type": "string"})
    assert e.question == "題目は?"
    assert e.schema == {"type": "string"}
