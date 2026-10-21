"""トリアージ待ち行列（計画書 testing/triage）: unknown と低確信度の評価記録を人間のラベル付けに回す。

待ち行列は JSONL（一行一項目、状態の更新は全行の書き直し）。項目は評価記録そのもの（状態文書、選択肢、
判定、分類結果）で、ラベルが付いたらコーパス形式（htf.testing.oracle）に書き出せる。
記述改訂の提案は人間の承認が要るので、ここでは作らない（第5.4節）。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from htf.contract import JsonValue, VerdictKind
from htf.runtime import EvaluationRecord, RunResult
from htf.testing.oracle import CorpusItem, write_corpus


@dataclass
class TriageItem:
    id: str
    run_id: str
    workflow: str
    stage: str
    entry: int
    document: str
    options: list[dict[str, str]]
    verdict: dict[str, JsonValue]
    classification: dict[str, JsonValue] | None
    reason: str
    status: str = "open"  # open | labeled | dismissed
    label: str | None = None
    note: str = ""
    carry_in: dict[str, JsonValue] = field(default_factory=dict)


def _verdict_dict(rec: EvaluationRecord) -> dict[str, JsonValue]:
    v = rec.verdict
    return {
        "kind": v.kind.value,
        "state": v.state,
        "confidence": v.confidence,
        "decided_by": v.decided_by,
        "reason": v.reason,
    }


class TriageQueue:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.items: list[TriageItem] = []
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.items.append(TriageItem(**json.loads(line)))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            for item in self.items:
                f.write(json.dumps(asdict(item), ensure_ascii=False, sort_keys=True) + "\n")

    def enqueue(
        self,
        result: RunResult,
        *,
        workflow: str,
        run_id: str,
        low_confidence: float | None = None,
    ) -> list[TriageItem]:
        """unknown の評価記録（と、与えれば確信度が low_confidence 未満の記録）を積む。子 run も辿る。"""
        added: list[TriageItem] = []
        self._collect(result, workflow, run_id, low_confidence, added, prefix="")
        self.items.extend(added)
        self._save()
        return added

    def _collect(
        self,
        result: RunResult,
        workflow: str,
        run_id: str,
        low_confidence: float | None,
        added: list[TriageItem],
        *,
        prefix: str,
    ) -> None:
        for i, rec in enumerate(result.evaluations):
            if rec.document is None:
                continue  # 集約や評価不能は分類器の問題ではない
            is_unknown = rec.verdict.kind is VerdictKind.UNKNOWN
            is_low = (
                low_confidence is not None
                and rec.classification is not None
                and rec.classification.confidence < low_confidence
            )
            if not (is_unknown or is_low):
                continue
            item_id = f"{run_id}:{prefix}{rec.workflow}/{rec.stage_id}#{rec.entry}/{i}"
            added.append(
                TriageItem(
                    id=item_id,
                    run_id=run_id,
                    workflow=rec.workflow,
                    stage=rec.stage_id,
                    entry=rec.entry,
                    document=rec.document,
                    options=[{"id": o.id, "description": o.description} for o in rec.options],
                    verdict=_verdict_dict(rec),
                    classification=(
                        {
                            "option_id": rec.classification.option_id,
                            "confidence": rec.classification.confidence,
                        }
                        if rec.classification
                        else None
                    ),
                    reason="unknown" if is_unknown else "low_confidence",
                    carry_in=dict(rec.carry_in),
                )
            )
        for stage_id, entries in result.child_results.items():
            for e, child_runs in enumerate(entries):
                for c, child in enumerate(child_runs):
                    self._collect(
                        child,
                        workflow,
                        run_id,
                        low_confidence,
                        added,
                        prefix=f"{prefix}{stage_id}[{e}][{c}]/",
                    )

    def list(self, *, status: str | None = None) -> list[TriageItem]:
        return [i for i in self.items if status is None or i.status == status]

    def get(self, item_id: str) -> TriageItem:
        for item in self.items:
            if item.id == item_id:
                return item
        raise KeyError(item_id)

    def label(self, item_id: str, *, label: str, note: str = "") -> TriageItem:
        item = self.get(item_id)
        if label not in {o["id"] for o in item.options}:
            raise ValueError(f"ラベル {label!r} は選択肢に無い: {[o['id'] for o in item.options]}")
        item.label = label
        item.note = note
        item.status = "labeled"
        self._save()
        return item

    def dismiss(self, item_id: str, *, note: str = "") -> TriageItem:
        item = self.get(item_id)
        item.status = "dismissed"
        item.note = note
        self._save()
        return item

    def export_corpus(self, path: Path) -> list[CorpusItem]:
        items = [
            CorpusItem(
                id=i.id,
                workflow=i.workflow,
                stage=i.stage,
                document=i.document,
                options=i.options,
                label=i.label or "",
                note=i.note,
            )
            for i in self.items
            if i.status == "labeled" and i.label
        ]
        write_corpus(path, items)
        return items


__all__ = ["TriageItem", "TriageQueue"]
