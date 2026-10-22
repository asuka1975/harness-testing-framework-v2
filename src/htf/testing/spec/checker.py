"""ワークフロー定義の整合性検査器。

検査する性質（コード）:

  schema                       スキーマ適合（下のどの性質にも対応づけられない違反）
  unique_ids                   フェーズ id、ステージ id（文書全体で一意。子のステージ id は親と重ならない）、
                               end_state id（ステージ内で一意）
  ref_integrity                rollback.state は自ステージの end_state、rollback.stage は同一文書のステージ
  end_state_rollback_bijection unknown を除く end_state と rollback.state が一対一
  rollback_forward             戻り先は自ステージより前
  rollback_max                 max が存在し 1 以上の整数（有界）
  carry_declared               carry の各鍵が元ステージの memory_out と戻り先の memory_in にある
  metric_registered            quantitative の指標名（ステージとフェーズ）がレジストリにある
  unknown_present              各ステージの end_state に unknown がある
  memory_in_source             memory_in の各鍵が、前方のステージの memory_out、このステージへの carry、
                               またはワークフローの inputs のいずれかにある
  subworkflow_ref              子定義が存在して読み込め、再帰的に検査を通り、循環せず、親子で
                               workflow.name が重複しない（束縛の鍵。ADR-012 12.13）
  subworkflow_user_input       子ワークフローのステージは user_input を宣言しない（v1.0 では未対応。12.16）
  subworkflow_depth            子は更に子を持たない（v1.0 は深さ 1 まで）
  subworkflow_inputs           each / pass は自ステージの memory_in、item_as ∪ pass == 子の inputs、
                               workspace は自ステージの writes のディレクトリ配下
  subworkflow_aggregate        aggregate.state は自ステージの end_state（unknown は明示の escalate）、
                               when の (stage, state) は子に存在する

end_state の記述の良し悪し（成果物から観測できるか、互いに排他か、優先順）は検査しない。
人間のレビューで見る。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema
import yaml

from htf.schema import load_schema

UNKNOWN = "unknown"
MAX_SUBWORKFLOW_DEPTH = 1

CODES: frozenset[str] = frozenset(
    {
        "schema",
        "unique_ids",
        "ref_integrity",
        "end_state_rollback_bijection",
        "rollback_forward",
        "rollback_max",
        "carry_declared",
        "metric_registered",
        "unknown_present",
        "memory_in_source",
        "subworkflow_ref",
        "subworkflow_depth",
        "subworkflow_inputs",
        "subworkflow_aggregate",
        "subworkflow_user_input",
    }
)


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    message: str
    file: str


@dataclass
class Report:
    file: str
    findings: list[Finding] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings


@dataclass(frozen=True)
class StageRef:
    order: int
    phase_index: int
    phase_id: str
    stage_index: int
    stage_id: str
    stage: dict

    @property
    def path(self) -> str:
        return f"/workflow/phases/{self.phase_index}/stages/{self.stage_index}"

    @property
    def artifacts(self) -> dict:
        return self.stage.get("artifacts") or {}

    def keys(self, name: str) -> set[str]:
        return set(self.artifacts.get(name) or [])


class WorkflowIndex:
    """ステージの大域順序と id の索引。id が重複する時は最初の出現を採る。"""

    def __init__(self, doc: dict) -> None:
        self.stages: list[StageRef] = []
        self.by_id: dict[str, StageRef] = {}
        order = 0
        for pi, phase in enumerate(doc["workflow"]["phases"]):
            for si, stage in enumerate(phase["stages"]):
                ref = StageRef(order, pi, phase["id"], si, stage["id"], stage)
                self.stages.append(ref)
                self.by_id.setdefault(stage["id"], ref)
                order += 1

    def phase_of(self, stage_id: str) -> str | None:
        ref = self.by_id.get(stage_id)
        return ref.phase_id if ref else None

    def position(self, stage_id: str) -> int | None:
        ref = self.by_id.get(stage_id)
        return ref.order if ref else None


def index_workflow(doc: dict) -> WorkflowIndex:
    return WorkflowIndex(doc)


def load_yaml(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def check_workflow(path: str | Path, *, metric_names: Iterable[str] | None = None) -> Report:
    """定義ファイルを検査する。

    metric_names を渡さない時は metric_registered を検査せず、Report.skipped に記録する。
    最上位ファイルが読めない時は例外を投げる（子が読めない時は所見）。
    """
    path = Path(path)
    registry = None if metric_names is None else set(metric_names)
    report = Report(file=str(path))
    doc = load_yaml(path)
    _Checker(report, registry).check_document(path, doc, depth=0, chain=(path.resolve(),))
    report.skipped = sorted(set(report.skipped))
    return report


class _Checker:
    def __init__(self, report: Report, registry: set[str] | None) -> None:
        self.report = report
        self.registry = registry
        self._docs: dict[Path, object] = {}  # 検査中の文書（親の name を子の検査で参照する）

    # --- 報告 ---

    def _workflow_name(self, file: Path) -> str | None:
        doc = self._docs.get(file.resolve())
        return doc["workflow"]["name"] if isinstance(doc, dict) else None

    def add(self, file: Path, code: str, path: str, message: str) -> None:
        assert code in CODES, code
        self.report.findings.append(Finding(code, path, message, str(file)))

    # --- 文書単位 ---

    def check_document(
        self, file: Path, doc: object, *, depth: int, chain: tuple[Path, ...]
    ) -> None:
        self._docs[file.resolve()] = doc
        if not self.check_schema(file, doc):
            return
        assert isinstance(doc, dict)
        idx = index_workflow(doc)
        self.check_unique_ids(file, doc, idx)
        inputs = set(doc["workflow"].get("inputs") or [])
        for pi, phase in enumerate(doc["workflow"]["phases"]):
            self.check_metrics(file, f"/workflow/phases/{pi}/goal/quantitative", phase["goal"])
        for ref in idx.stages:
            self.check_stage(file, ref, idx, inputs, depth=depth, chain=chain)

    def check_schema(self, file: Path, doc: object) -> bool:
        validator = jsonschema.Draft202012Validator(load_schema())
        ok = True
        for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
            ok = False
            path = "/" + "/".join(str(p) for p in err.absolute_path)
            self.add(file, _code_for_schema_error(err), path, err.message)
        return ok

    def check_unique_ids(self, file: Path, doc: dict, idx: WorkflowIndex) -> None:
        phase_ids = Counter(p["id"] for p in doc["workflow"]["phases"])
        for pid, n in phase_ids.items():
            if n > 1:
                self.add(
                    file, "unique_ids", "/workflow/phases", f"フェーズ id {pid!r} が {n} 回現れる"
                )
        stage_ids = Counter(s.stage_id for s in idx.stages)
        for sid, n in stage_ids.items():
            if n > 1:
                self.add(
                    file, "unique_ids", "/workflow/phases", f"ステージ id {sid!r} が {n} 回現れる"
                )
        for ref in idx.stages:
            es_ids = Counter(e["id"] for e in ref.stage["end_state"])
            for eid, n in es_ids.items():
                if n > 1:
                    self.add(
                        file,
                        "unique_ids",
                        f"{ref.path}/end_state",
                        f"end_state id {eid!r} が {n} 回現れる",
                    )

    def check_metrics(self, file: Path, path: str, goal: dict) -> None:
        if self.registry is None:
            self.report.skipped.append("metric_registered")
            return
        for name in goal["quantitative"]:
            if name not in self.registry:
                self.add(
                    file, "metric_registered", f"{path}/{name}", f"指標 {name!r} がレジストリに無い"
                )

    # --- ステージ単位 ---

    def check_stage(
        self,
        file: Path,
        ref: StageRef,
        idx: WorkflowIndex,
        inputs: set[str],
        *,
        depth: int,
        chain: tuple[Path, ...],
    ) -> None:
        stage = ref.stage
        es_ids = {e["id"] for e in stage["end_state"]}
        if UNKNOWN not in es_ids:
            self.add(
                file,
                "unknown_present",
                f"{ref.path}/end_state",
                "id が unknown の end_state が無い",
            )
        self.check_metrics(file, f"{ref.path}/goal/quantitative", stage["goal"])
        self.check_rollbacks(file, ref, idx, es_ids)
        self.check_memory_in_source(file, ref, idx, inputs)
        if "subworkflow" in stage:
            self.check_subworkflow(file, ref, idx, es_ids, depth=depth, chain=chain)

    def check_rollbacks(
        self, file: Path, ref: StageRef, idx: WorkflowIndex, es_ids: set[str]
    ) -> None:
        covered: Counter[str] = Counter()
        for ri, rb in enumerate(ref.stage["rollback"]):
            rpath = f"{ref.path}/rollback/{ri}"
            state, target_id = rb["state"], rb["stage"]
            if state not in es_ids:
                self.add(file, "ref_integrity", f"{rpath}/state", f"end_state {state!r} が無い")
            elif state == UNKNOWN:
                self.add(
                    file,
                    "end_state_rollback_bijection",
                    f"{rpath}/state",
                    "unknown に rollback を付けてはいけない（人間に差し戻す）",
                )
            else:
                covered[state] += 1
            target = idx.by_id.get(target_id)
            if target is None:
                self.add(
                    file,
                    "ref_integrity",
                    f"{rpath}/stage",
                    f"ステージ {target_id!r} が同一文書に無い",
                )
            elif target.order >= ref.order:
                self.add(
                    file,
                    "rollback_forward",
                    f"{rpath}/stage",
                    f"戻り先 {target_id!r} は {ref.stage_id!r} より前でなければならない",
                )
            for key in rb.get("carry") or []:
                if key not in ref.keys("memory_out"):
                    self.add(
                        file,
                        "carry_declared",
                        f"{rpath}/carry",
                        f"carry {key!r} が元ステージ {ref.stage_id!r} の memory_out に無い",
                    )
                if target is not None and key not in target.keys("memory_in"):
                    self.add(
                        file,
                        "carry_declared",
                        f"{rpath}/carry",
                        f"carry {key!r} が戻り先 {target_id!r} の memory_in に無い",
                    )
        for state, n in covered.items():
            if n > 1:
                self.add(
                    file,
                    "end_state_rollback_bijection",
                    f"{ref.path}/rollback",
                    f"end_state {state!r} に rollback が {n} 件ある",
                )
        for state in sorted(es_ids - {UNKNOWN} - set(covered)):
            self.add(
                file,
                "end_state_rollback_bijection",
                f"{ref.path}/rollback",
                f"end_state {state!r} に rollback が無い",
            )

    def check_memory_in_source(
        self, file: Path, ref: StageRef, idx: WorkflowIndex, inputs: set[str]
    ) -> None:
        sources = set(inputs)
        for other in idx.stages:
            if other.order < ref.order:
                sources |= other.keys("memory_out")
            for rb in other.stage["rollback"]:
                if rb["stage"] == ref.stage_id:
                    sources |= set(rb.get("carry") or [])
        for key in sorted(ref.keys("memory_in") - sources):
            self.add(
                file,
                "memory_in_source",
                f"{ref.path}/artifacts/memory_in",
                f"memory_in {key!r} を供給するものが無い"
                "（前方の memory_out、このステージへの carry、workflow.inputs のいずれにも無い）",
            )

    # --- 子ワークフロー ---

    def check_subworkflow(
        self,
        file: Path,
        ref: StageRef,
        idx: WorkflowIndex,
        es_ids: set[str],
        *,
        depth: int,
        chain: tuple[Path, ...],
    ) -> None:
        sub = ref.stage["subworkflow"]
        spath = f"{ref.path}/subworkflow"
        memory_in = ref.keys("memory_in")
        if sub["each"] not in memory_in:
            self.add(
                file,
                "subworkflow_inputs",
                f"{spath}/each",
                f"each {sub['each']!r} が memory_in に無い",
            )
        for key in sub.get("pass") or []:
            if key not in memory_in:
                self.add(
                    file, "subworkflow_inputs", f"{spath}/pass", f"pass {key!r} が memory_in に無い"
                )
        dirs = [w for w in ref.keys("writes") if w.endswith("/")]
        if not any(sub["workspace"].startswith(d) for d in dirs):
            self.add(
                file,
                "subworkflow_inputs",
                f"{spath}/workspace",
                f"workspace {sub['workspace']!r} が writes のディレクトリ項目の配下に無い",
            )

        if depth >= MAX_SUBWORKFLOW_DEPTH:
            self.add(
                file,
                "subworkflow_depth",
                spath,
                f"子ワークフローは更に子を持てない（深さ {MAX_SUBWORKFLOW_DEPTH} まで）",
            )

        child_path = (file.parent / sub["ref"]).resolve()
        if child_path in chain:
            self.add(file, "subworkflow_ref", f"{spath}/ref", f"循環参照: {sub['ref']!r}")
            return
        if depth >= MAX_SUBWORKFLOW_DEPTH:
            return
        if not child_path.is_file():
            self.add(file, "subworkflow_ref", f"{spath}/ref", f"子定義 {sub['ref']!r} が無い")
            return
        try:
            child = load_yaml(child_path)
        except yaml.YAMLError as e:
            self.add(
                file, "subworkflow_ref", f"{spath}/ref", f"子定義 {sub['ref']!r} が読めない: {e}"
            )
            return

        before = len(self.report.findings)
        self.check_document(child_path, child, depth=depth + 1, chain=(*chain, child_path))
        child_ok = len(self.report.findings) == before
        if not child_ok:
            self.add(
                file, "subworkflow_ref", f"{spath}/ref", f"子定義 {sub['ref']!r} が検査を通らない"
            )
        if not _is_schema_valid(child):
            return
        assert isinstance(child, dict)
        child_idx = index_workflow(child)

        if child["workflow"]["name"] == self._workflow_name(file):
            self.add(
                file,
                "subworkflow_ref",
                f"{spath}/ref",
                f"子の workflow.name {child['workflow']['name']!r} が親と同じ（束縛の鍵が衝突する）",
            )
        shared = sorted({s.stage_id for s in child_idx.stages} & {s.stage_id for s in idx.stages})
        if shared:
            self.add(
                file,
                "unique_ids",
                f"{spath}/ref",
                f"子のステージ id {shared} が親と重なる（分布の集計と expectations の鍵が混ざる）",
            )
        asking = [s.stage_id for s in child_idx.stages if s.stage.get("user_input")]
        if asking:
            self.add(
                file,
                "subworkflow_user_input",
                f"{spath}/ref",
                f"子のステージ {asking} が user_input を宣言している（子のユーザー入出力は未対応）",
            )

        supplied = {sub["item_as"], *(sub.get("pass") or [])}
        declared = set(child["workflow"].get("inputs") or [])
        if supplied != declared:
            self.add(
                file,
                "subworkflow_inputs",
                f"{spath}/item_as",
                f"親が供給する鍵 {sorted(supplied)} と子の inputs {sorted(declared)} が一致しない",
            )

        for ai, rule in enumerate(sub["aggregate"]):
            apath = f"{spath}/aggregate/{ai}"
            if rule["state"] not in es_ids:
                self.add(
                    file,
                    "subworkflow_aggregate",
                    f"{apath}/state",
                    f"{rule['state']!r} は親の end_state ではない",
                )
            (quant, outcome), *_ = rule["when"].items()
            cstage = child_idx.by_id.get(outcome["stage"])
            if cstage is None:
                self.add(
                    file,
                    "subworkflow_aggregate",
                    f"{apath}/when/{quant}/stage",
                    f"子にステージ {outcome['stage']!r} が無い",
                )
            elif outcome["state"] not in {e["id"] for e in cstage.stage["end_state"]}:
                self.add(
                    file,
                    "subworkflow_aggregate",
                    f"{apath}/when/{quant}/state",
                    f"子のステージ {outcome['stage']!r} に end_state {outcome['state']!r} が無い",
                )


def _is_schema_valid(doc: object) -> bool:
    return jsonschema.Draft202012Validator(load_schema()).is_valid(doc)


def _code_for_schema_error(err: jsonschema.ValidationError) -> str:
    """スキーマ違反を性質コードに対応づける。rollback の max に関するものだけ rollback_max。"""
    parts = [str(p) for p in err.absolute_path]
    in_rollback_entry = (
        len(parts) >= 2 and parts[-2] == "rollback" or (len(parts) >= 3 and parts[-3] == "rollback")
    )
    if in_rollback_entry:
        if parts[-1] == "max":
            return "rollback_max"
        if err.validator == "required" and "'max'" in err.message:
            return "rollback_max"
    return "schema"
