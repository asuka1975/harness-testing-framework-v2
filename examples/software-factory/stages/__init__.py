"""software-factory の偽ステージ本体（版 0.2）。LLM を使わない。

各本体は workflow.yaml / implement-task.yaml の artifacts 宣言どおりにだけ読み書きする。

- 決定論的な本体（intake / analyze / implement / integrate / release）は、入力と fixtures/ の成果物から結果が決まる
  （ペルソナの回答、要件の目録、コンポーネントの目録を写す）
- 確率的な本体（design / plan / review / code）は、供給元（sources.py: 台本か種つきの分布）から変種を取り、
  その変種の fixtures/ の成果物を写す。code は fixtures/codebase の変更を当てる
- 実ツールの本体（check / unit_test / verify）は、fixtures のコードベースに対して実際にビルド・lint・テスト・
  カバレッジを走らせ（toolchain.py）、要旨を report に、正規化した出力の全体を results に書く

結果は成果物の中の印（"outcome": "<id>"）に残し、偽の分類器（MarkerClassifier）がそれを読む。印は本物の結果から
決める（実ツールの結果や、入力から決まる状態）。供給元の値を印にするのは、成果物から結果が決まらない時だけ。
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import yaml

from htf.contract import StageContext

from .. import toolchain
from .sources import Script, ScriptCursor, StochasticSource, default_for

__all__ = [
    "Analyze",
    "Check",
    "Code",
    "Design",
    "INTAKE_QUESTIONS",
    "Implement",
    "Intake",
    "Integrate",
    "Plan",
    "RELEASE_PREFIX",
    "Release",
    "Review",
    "Script",
    "ScriptCursor",
    "StochasticSource",
    "UNAGREED_MARK",
    "UnitTest",
    "Verify",
    "default_for",
]

FIXTURES = Path(__file__).parents[1] / "fixtures"

# intake は毎回この順で尋ねる（中断からの再開では、累積回答が ask の順で返る。adopting.md 3.5）
INTAKE_QUESTIONS = [
    ("role", "あなたの役割は何ですか？"),
    ("summary", "作りたいものを一文で教えてください。"),
    ("features", "欲しい機能を挙げてください。"),
    ("constraints", "守るべき制約はありますか？"),
    ("acceptance", "できあがったことを、どう確かめますか？"),
]
RELEASE_PREFIX = "[release]"
UNAGREED_MARK = "見送り（合意なし）"
RELEASE_VERSION = "0.2.0"
APPROVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "kind": {"type": "string", "enum": ["requirements", "quality"]},
        "reason": {"type": "string"},
    },
    "required": ["approved"],
}
OVERRIDES = ("unknown", "low_confidence")  # 成果物は goal の形のまま、印だけ変える値
CHILD_CARRY_KEYS = ("check_failures", "test_failures", "coverage_gaps")  # 子の code への carry


def _yaml(rel: str) -> dict:
    return yaml.safe_load((FIXTURES / rel).read_text(encoding="utf-8"))


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, doc: object) -> None:
    """JSON で書く。印（outcome）は先頭に置く: 状態文書は 1 ファイル 4000 文字で切られる（adopting-gaps.md G-08）。"""
    if isinstance(doc, dict) and "outcome" in doc:
        doc = {"outcome": doc["outcome"], **{k: v for k, v in doc.items() if k != "outcome"}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _active(requirements: list[dict]) -> list[dict]:
    return [r for r in requirements if not r.get("deferred")]


# --- discovery ---


class Intake:
    """依頼者に決まった順で質問し、carry された質問（open_questions）も続けて尋ねる。memory_in の他の鍵は読まない。"""

    def __init__(self, source: Script | StochasticSource) -> None:
        self.source = source

    def run(self, ctx: StageContext) -> None:
        answers = {key: ctx.user.ask(question) for key, question in INTAKE_QUESTIONS}
        open_questions = ctx.memory.get("open_questions") or []
        clarifications = {q["id"]: ctx.user.ask(q["question"]) for q in open_questions}
        outcome = self.source.next("intake")
        doc = {
            **answers,
            "asked": [q["id"] for q in open_questions],
            "clarifications": clarifications,
            "outcome": outcome,
        }
        _write(ctx.workspace / "intake" / "answers.json", doc)
        lines = [
            f"# 依頼（{answers['role']}）",
            "",
            str(answers["summary"]),
            "",
            "## 欲しい機能",
            "",
        ]
        lines += [f"- {f}" for f in answers["features"] or []] + ["", "## 制約", ""]
        lines += [f"- {c}" for c in answers["constraints"] or []] + [
            "",
            "## 受け入れの確かめ方",
            "",
        ]
        lines += [str(answers["acceptance"]), ""]
        for q in open_questions:
            lines += [f"## {q['question']}", "", str(clarifications[q["id"]]), ""]
        (ctx.workspace / "intake" / "request.md").write_text("\n".join(lines), encoding="utf-8")


class Analyze:
    """依頼者の役割から要件の組（fixtures/artifacts/requirements/）を写し、回答と carry を反映する。

    - 回答の無い open_questions が妨げる要件は、受け入れ基準を空にする（→ ambiguous）
    - carry された conflicts: 組の on_conflict にあれば片方を見送り、無ければ「両立する」と記録する
    - carry された rejection_feedback（kind が requirements）: 組の on_feedback の要件の見送りに合意したと記録する。
      kind が quality の feedback は plan が扱うので、ここでは読まない
    """

    def __init__(self, source: Script | StochasticSource) -> None:
        self.source = source

    def run(self, ctx: StageContext) -> None:
        answers = _read(ctx.workspace / "intake" / "answers.json")
        drawn = self.source.next("analyze")
        catalog = _yaml("artifacts/requirements/catalog.yaml")
        group = catalog["roles"].get(answers.get("role"))
        if group is None:  # 知らない依頼者: 要件を作れない
            doc = {"source": None, "requirements": [], "open_questions": [], "decisions": []}
            _write(ctx.workspace / "requirements.json", {**doc, "outcome": "unknown"})
            return
        spec = _yaml(f"artifacts/requirements/{group}.yaml")
        reqs = [
            {"id": rid, **copy.deepcopy(catalog["requirements"][rid]), "deferred": False}
            for rid in spec["requirements"]
        ]
        by_id = {r["id"]: r for r in reqs}
        clarifications = answers.get("clarifications") or {}
        open_questions = [q for q in spec["open_questions"] if not clarifications.get(q["id"])]
        for q in open_questions:
            for rid in q["blocks"]:
                by_id[rid]["criteria"] = []
        decisions = []
        for conflict in ctx.memory.get("conflicts") or []:
            pair = "+".join(sorted(conflict["between"]))
            rule = spec["on_conflict"].get(pair)
            if rule:
                by_id[rule["defer"]].update(deferred=True, agreed=False, note=rule["note"])
                decision = f"{rule['defer']} を見送る"
            else:
                decision = "確認した結果、両立する。要件は変えない"
            decisions.append({"conflict": conflict["between"], "decision": decision})
        feedback = ctx.memory.get("rejection_feedback")
        if feedback and feedback.get("kind") == "requirements":
            rule = spec["on_feedback"]
            for rid in rule.get("agree", []):
                by_id[rid].update(agreed=True, note=rule["note"])
            decisions.append({"feedback": feedback["reason"], "decision": rule.get("note", "")})
        outcome = "ambiguous" if open_questions else drawn
        doc = {
            "source": group,
            "requirements": reqs,
            "open_questions": open_questions,
            "decisions": decisions,
            "outcome": outcome,
        }
        _write(ctx.workspace / "requirements.json", doc)
        if open_questions:
            ctx.emit("open_questions", open_questions)


# --- design ---


class Design:
    """見送りでない要件をコンポーネントの目録から割り当てる。実在する衝突（fixtures の real）は必ず見つける。

    実在する衝突が無い時は、供給元の変種に従う（requirements_conflict なら fixtures の drawn を主張する。
    drops_requirement なら最後の要件を自分の写し（requirements）からも割当てからも落として goal を主張する。
    plan がそれを design_incomplete として見つけ、unassigned_requirements を carry して戻す）。
    """

    def __init__(self, source: Script | StochasticSource) -> None:
        self.source = source

    def run(self, ctx: StageContext) -> None:
        reqs = _read(ctx.workspace / "requirements.json")
        drawn = self.source.next("design")
        active = [r["id"] for r in _active(reqs["requirements"])]
        dropped: list[str] = []
        if drawn == "drops_requirement" and len(active) > 1:
            dropped, active = active[-1:], active[:-1]
        components = []
        for cid, c in _yaml("artifacts/design/components.yaml").items():
            satisfies = [r for r in c["satisfies"] if r in active]
            if satisfies:
                components.append(
                    {"id": cid, "title": c["title"], "module": c["module"], "satisfies": satisfies}
                )
        known = _yaml("artifacts/design/conflicts.yaml")
        resolved = {frozenset(d["conflict"]) for d in reqs.get("decisions", []) if "conflict" in d}
        conflicts = [
            dict(c)
            for c in known["real"]
            if set(c["between"]) <= set(active) and frozenset(c["between"]) not in resolved
        ]
        if conflicts:
            outcome = "requirements_conflict"
        elif drawn == "requirements_conflict":
            conflicts, outcome = [dict(known["drawn"])], drawn
        elif drawn == "drops_requirement":
            outcome = "goal"
        else:
            outcome = drawn
        revisions = [
            {"from": "review", "issue": issue} for issue in ctx.memory.get("design_issues") or []
        ]
        revisions += [
            {"from": "plan", "uncovered_component": cid}
            for cid in ctx.memory.get("uncovered_components") or []
        ]
        revisions += [
            {"from": "plan", "unassigned_requirement": rid}
            for rid in ctx.memory.get("unassigned_requirements") or []
        ]
        doc = {
            "requirements": active,
            "components": components,
            "conflicts": conflicts,
            "revisions": revisions,
            "variant": drawn,
            "dropped": dropped,
            "outcome": outcome,
        }
        _write(ctx.workspace / "design.json", doc)
        if conflicts:
            ctx.emit("conflicts", conflicts)


class Plan:
    """design.json のコンポーネントを、変種（fixtures/artifacts/plan/groupings.yaml）の分け方でタスクにする。

    requirements.json の見送りでない要件と design.json の割当てを照らし、どのコンポーネントにも満たされない要件を
    unassigned_requirements に書く（→ design_incomplete。design_gap に優先）。
    """

    def __init__(self, source: Script | StochasticSource) -> None:
        self.source = source

    def run(self, ctx: StageContext) -> None:
        design = _read(ctx.workspace / "design.json")
        reqs = _read(ctx.workspace / "requirements.json")
        drawn = self.source.next("plan")
        groupings = _yaml("artifacts/plan/groupings.yaml")
        catalog = _yaml("artifacts/design/components.yaml")
        design_ids = [c["id"] for c in design["components"]]
        requirement_ids = [r["id"] for r in _active(reqs["requirements"])]
        assigned = sorted({r for c in design["components"] for r in c["satisfies"]})
        unassigned = [r for r in requirement_ids if r not in assigned]
        uncovered: list[str] = []
        if drawn == "design_gap":
            groups = [[cid] for cid in design_ids[:-1]]
            uncovered = design_ids[-1:]
        else:
            fixture = groupings["two_tasks" if drawn == "two_tasks" else "goal"]
            groups = [g for g in ([c for c in g if c in design_ids] for g in fixture) if g]
        tasks = [_task(i, group, catalog) for i, group in enumerate(groups, 1)]
        _attach_notes(tasks, ctx.memory)
        if unassigned:
            outcome = "design_incomplete"
        elif uncovered:
            outcome = "design_gap"
        else:
            outcome = "goal" if drawn == "two_tasks" else drawn
        doc = {
            "design_components": design_ids,
            "requirement_ids": requirement_ids,
            "assigned_requirement_ids": assigned,
            "variant": drawn,
            "tasks": tasks,
            "uncovered_components": uncovered,
            "unassigned_requirements": unassigned,
            "outcome": outcome,
        }
        _write(ctx.workspace / "tasks.json", doc)
        ctx.emit("tasks", tasks)
        if uncovered:
            ctx.emit("uncovered_components", uncovered)
        if unassigned:
            ctx.emit("unassigned_requirements", unassigned)


def _task(i: int, group: list[str], catalog: dict) -> dict:
    comps = [catalog[c] for c in group]
    return {
        "id": f"T{i}",  # 分け方が同じなら再計画でも同じ id（分割・統合した時は notes に旧 id を書く約束）
        "title": " と ".join(c["title"] for c in comps),
        "components": list(group),
        "features": [c["feature"] for c in comps],
        "scope": sorted({p for c in comps for p in c["scope"]}),
        "tests": sorted({p for c in comps for p in c["tests"]}),
        "notes": [],
    }


UNFINISHED_LABELS = {
    "tests_failing": "前回の単体テストが通らなかった",
    "coverage_low": "前回のカバレッジが足りなかった",
    "build_failed": "前回のビルドが通らなかった",
    "lint_failed": "前回の lint 違反が残った",
    "out_of_scope": "前回に scope 外を変えた",
}


def _attach_notes(tasks: list[dict], memory: dict) -> None:
    """carry された差し戻しを、関係するタスクの notes に書く（子 run は task の中身として受け取る）。"""

    def owners(pred) -> list[dict]:  # noqa: ANN001
        hit = [t for t in tasks if pred(t)]
        return hit or tasks[:1]

    def module_of(nodeid: str) -> str:
        return "src/textkit/" + Path(nodeid.split("::")[0]).stem.removeprefix("test_") + ".py"

    for item in memory.get("unfinished_tasks") or []:
        label = UNFINISHED_LABELS.get(item["status"], f"前回のタスクが未完了（{item['status']}）")
        for t in owners(lambda t, item=item: set(t["features"]) & set(item["features"])):
            t["notes"].append(f"{label}: {item['summary']}")
    for item in (memory.get("merge_failures") or {}).get("conflicts", []):
        for t in owners(lambda t, item=item: item["path"] in t["scope"]):
            t["notes"].append(
                f"前回の統合で {item['path']} が衝突した（{', '.join(item['tasks'])}）"
            )
    for item in (memory.get("merge_failures") or {}).get("failures", []):
        for t in owners(lambda t, item=item: item.get("path") in t["scope"]):
            t["notes"].append(f"前回の統合の失敗: {item['message']}")
    for nodeid in memory.get("regressions") or []:
        module = module_of(nodeid)
        for t in owners(lambda t, module=module: module in t["scope"]):
            t["notes"].append(f"既存のテスト {nodeid} を壊さない")
    for c in memory.get("unmet_criteria") or []:
        test_file = c["test"].split("::")[0]
        for t in owners(lambda t, test_file=test_file: test_file in t["tests"]):
            t["notes"].append(f"受け入れ基準 {c['id']} を確かめるテスト {c['test']} を書く")
    for path, lines in (memory.get("suite_coverage_gaps") or {}).items():
        for t in owners(lambda t, path=path: path in t["scope"]):
            t["notes"].append(f"{path} の行 {lines} をテストで覆う")
    for v in memory.get("suite_lint_violations") or []:
        for t in owners(lambda t, v=v: v["path"] in t["scope"]):
            t["notes"].append(f"lint 違反 {v['code']}（{v['path']}:{v['line']}）を直す")
    for c in memory.get("review_comments") or []:
        for t in owners(lambda t, c=c: c["target"] in t["scope"]):
            t["notes"].append(f"レビューの指摘（{c['target']}）: {c['text']}")
    feedback = memory.get("rejection_feedback")
    if feedback and feedback.get("kind") == "quality":
        for t in tasks[:1]:
            t["notes"].append(f"依頼者の指摘（品質）: {feedback['reason']}")


# --- build（親 implement / integrate と子 implement-task） ---


class Implement:
    """子 run が終わった後に走る。各タスクの終わり方を check.json と unit/report.json の事実から tasks/summary.json に書く。

    check か unit_test で止まったタスク（ビルド失敗、scope 外、lint 違反、テストの失敗、カバレッジ不足）を
    unfinished_tasks に出す。統合は integrate が行う。
    """

    def run(self, ctx: StageContext) -> None:
        ws = ctx.workspace
        entries, unfinished = [], []
        for i, task in enumerate(ctx.memory["tasks"]):
            child = ws / "tasks" / str(i)
            check = _read(child / "check.json") if (child / "check.json").is_file() else None
            unit = (
                _read(child / "unit" / "report.json")
                if (child / "unit" / "report.json").is_file()
                else None
            )
            status = _task_status(check, unit)
            entry = {
                "id": task["id"],
                "index": i,
                "status": status,
                "summary": _summary(status, check, unit),
            }
            entries.append(entry)
            if status != "done":
                unfinished.append({"task": task["id"], "features": task["features"], **entry})
        _write(
            ws / "tasks" / "summary.json",
            {
                "outcome": "goal" if not unfinished else "tasks_unfinished",
                "tasks": entries,
                "unfinished": unfinished,
            },
        )
        if unfinished:
            ctx.emit("unfinished_tasks", unfinished)


def _task_status(check: dict | None, unit: dict | None) -> str:
    if check is None:
        return "not_checked"
    if check["build"]["errors"] or check["build"]["files"] == 0:
        return "build_failed"
    if check["out_of_scope"]:
        return "out_of_scope"
    if check["lint"]["violations"]:
        return "lint_failed"
    if unit is None:
        return "not_tested"
    if unit["failed"] or unit.get("test_count") == 0:
        return "tests_failing"
    if unit["coverage_gaps"]:
        return "coverage_low"
    return "done"


def _summary(status: str, check: dict | None, unit: dict | None) -> str:
    if status == "build_failed" and check:
        return "ビルドのエラー " + ", ".join(
            f"{e['path']}:{e['line']} {e['message']}" for e in check["build"]["errors"]
        )
    if status == "out_of_scope" and check:
        return "scope 外のパス " + ", ".join(check["out_of_scope"])
    if status == "lint_failed" and check:
        return "lint 違反 " + ", ".join(
            f"{v['code']} {v['path']}:{v['line']}" for v in check["lint"]["violations"]
        )
    if status == "tests_failing" and unit:
        return (
            "失敗したテスト " + ", ".join(unit["failed"])
            if unit["failed"]
            else "テストが集まらない"
        )
    if status == "coverage_low" and unit:
        return f"カバレッジ {unit['coverage']}（基準 {unit['coverage_min']}）"
    return status


class Integrate:
    """tasks/summary.json で done のタスクの変更を base に統合して codebase/ に置き、記録を merge.json に書く。

    同じパスを二つ以上のタスクが変えていれば conflicts に、統合後のビルドの失敗や scope 外のパスは failures に書き、
    merge_failed。このフィクスチャの世界では起きない（scope は重ならず、scope 外は check が止める）ので、E2E では
    注入で踏む（htf の ADR-014 14.6.8）。印の上書き（unknown / low_confidence）は供給元から。
    """

    def __init__(self, source: Script | StochasticSource) -> None:
        self.source = source

    def run(self, ctx: StageContext) -> None:
        ws = ctx.workspace
        drawn = self.source.next("integrate")
        summary = _read(ws / "tasks" / "summary.json")
        status_of = {t["id"]: t for t in summary["tasks"]}
        codebase = ws / "codebase"
        if codebase.exists():
            shutil.rmtree(codebase)
        shutil.copytree(toolchain.BASE, codebase)
        merged, skipped, conflicts, owner = [], [], [], {}
        for i, task in enumerate(ctx.memory["tasks"]):
            entry = status_of.get(task["id"]) or {"status": "not_checked"}
            if entry["status"] != "done":
                skipped.append({"task": task["id"], "status": entry["status"]})
                continue
            child = ws / "tasks" / str(i)
            changed = _read(child / "check.json")["changed_paths"]
            for rel in changed:
                if rel in owner:
                    conflicts.append({"path": rel, "tasks": [owner[rel], task["id"]]})
                owner[rel] = task["id"]
                src, dest = child / "repo" / rel, codebase / rel
                if src.is_file():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dest)
                elif dest.exists():
                    dest.unlink()
            merged.append(task["id"])
        build = toolchain.build(codebase)
        allowed = {p for task in ctx.memory["tasks"] for p in task["scope"]}
        changed_paths = toolchain.changed_paths(codebase)
        failures = [
            {
                "kind": "build",
                "path": e["path"],
                "message": f"{e['path']}:{e['line']} {e['message']}",
            }
            for e in build["errors"]
        ]
        failures += [
            {"kind": "scope", "path": p, "message": f"{p} はどのタスクの scope にも無い"}
            for p in changed_paths
            if p not in allowed
        ]
        failed = bool(conflicts or failures)
        doc = {
            "merged": merged,
            "skipped": skipped,
            "conflicts": conflicts,
            "failures": failures,
            "changed_paths": changed_paths,
            "outcome": "merge_failed" if failed else drawn,
        }
        _write(ws / "merge.json", doc)
        if failed:
            ctx.emit("merge_failures", {"conflicts": conflicts, "failures": failures})


class Code:
    """fixtures のコードベースにタスクの変更（変種）を当て、変わったパスを code.json に書く。

    carry（check_failures / test_failures / coverage_gaps）の無い進入が子 run の始まり。carry つきの再進入では、
    供給元の reentry の分布（直した変更が出やすい）から変種を引く。ビルド・lint・scope の検査は次の check。
    """

    def __init__(self, source: Script | StochasticSource) -> None:
        self.source = source

    def run(self, ctx: StageContext) -> None:
        task = ctx.memory["task"]
        fixing = {k: ctx.memory[k] for k in CHILD_CARRY_KEYS if k in ctx.memory}
        variant = self.source.next("code", unit=task["id"], run_start=not fixing)
        override = variant if variant in OVERRIDES else None
        repo = ctx.workspace / "repo"
        applied = toolchain.materialize(repo, task["features"], "correct" if override else variant)
        changed = toolchain.changed_paths(repo)
        doc = {
            "task": task["id"],
            "variant": variant,
            "applied": applied,
            "fixing": fixing,
            "notes": task.get("notes", []),
            "changed_paths": changed,
            "outcome": override or ("goal" if changed else "unknown"),
        }
        _write(ctx.workspace / "code.json", doc)


class Check:
    """repo/ でビルドと lint を走らせ、変わったパスと task.scope を照合して check.json に書く。印は結果から決める。"""

    def __init__(self, source: Script | StochasticSource) -> None:
        self.source = source

    def run(self, ctx: StageContext) -> None:
        task = ctx.memory["task"]
        drawn = self.source.next("check", unit=task["id"])
        check = toolchain.check(ctx.workspace / "repo", task["scope"])
        if check["build"]["errors"] or check["build"]["files"] == 0:
            outcome, failure = "build_failed", {"kind": "build", "items": check["build"]["errors"]}
        elif check["out_of_scope"]:
            outcome, failure = "out_of_scope", {"kind": "scope", "items": check["out_of_scope"]}
        elif check["lint"]["violations"]:
            outcome, failure = "lint_failed", {"kind": "lint", "items": check["lint"]["violations"]}
        else:
            outcome, failure = drawn, None
        _write(ctx.workspace / "check.json", {"task": task["id"], **check, "outcome": outcome})
        if failure is not None:
            ctx.emit("check_failures", failure)


class UnitTest:
    """repo/ でタスクのテストファイルだけを pytest とカバレッジで走らせる。要旨を report.json、全体を results.json に。"""

    def __init__(self, source: Script | StochasticSource, coverage_min: float) -> None:
        self.source = source
        self.coverage_min = (
            coverage_min  # implement-task.yaml の unit_coverage の基準（harness が定義から渡す）
        )

    def run(self, ctx: StageContext) -> None:
        task = ctx.memory["task"]
        drawn = self.source.next("unit_test", unit=task["id"])
        result = toolchain.run_tests(ctx.workspace / "repo", task["tests"])
        failed = toolchain.failed_tests(result)
        scope_src = [p for p in task["scope"] if p.startswith("src/")]
        try:
            coverage: float | None = round(
                toolchain.line_coverage(result["coverage"], scope_src), 4
            )
        except ValueError:
            coverage = None
        gaps = {}
        if coverage is not None and coverage < self.coverage_min:
            gaps = {
                p: result["coverage"][p]["missing"]
                for p in scope_src
                if result["coverage"].get(p, {}).get("missing")
            }
        if failed or not result["tests"]:
            outcome = "tests_failing"  # 失敗があるか、一件も集まらない
        elif not toolchain.tests_passed(result) or coverage is None:
            outcome = "unknown"
        elif gaps:
            outcome = "coverage_low"
        else:
            outcome = drawn
        report = {
            "task": task["id"],
            "test_count": len(result["tests"]),
            "failed": failed,
            "coverage": coverage,
            "coverage_min": self.coverage_min,
            "coverage_gaps": gaps,
            "outcome": outcome,
        }
        _write(ctx.workspace / "unit" / "report.json", report)
        _write(ctx.workspace / "unit" / "results.json", {"result": result})
        if outcome == "tests_failing":
            ctx.emit("test_failures", failed)
        if gaps:
            ctx.emit("coverage_gaps", gaps)


# --- assure ---


class Verify:
    """codebase/ でビルド・lint・テストスイート全体を走らせ、受け入れ基準をテストの結果と照合する。

    優先順位: regression > criteria_unmet > coverage_short > lint_dirty（ADR-014 14.6.4）。coverage_short と
    lint_dirty はこのフィクスチャの世界では起きない（子の check と unit_test が先に止める）が、本体の論理は持つ。
    """

    def __init__(self, source: Script | StochasticSource, coverage_min: float = 0.85) -> None:
        self.source = source
        self.coverage_min = (
            coverage_min  # workflow.yaml の suite_coverage の基準（harness が定義から渡す）
        )

    def run(self, ctx: StageContext) -> None:
        ws = ctx.workspace
        drawn = self.source.next("verify")
        repo = ws / "codebase"
        reqs = _read(ws / "requirements.json")
        build, lint = toolchain.build(repo), toolchain.lint(repo)
        result = toolchain.run_tests(repo, [])
        statuses = {t["nodeid"]: t["status"] for t in result["tests"]}
        criteria = [
            {
                "requirement": r["id"],
                "id": c["id"],
                "test": c["test"],
                "status": statuses.get(c["test"], "missing"),
            }
            for r in _active(reqs["requirements"])
            for c in r["criteria"]
        ]
        failed = toolchain.failed_tests(result)
        unmet = [c for c in criteria if c["status"] != "passed"]
        try:
            coverage: float | None = round(toolchain.line_coverage(result["coverage"]), 4)
        except ValueError:
            coverage = None
        gaps = {}
        if coverage is not None and coverage < self.coverage_min:
            gaps = {p: info["missing"] for p, info in result["coverage"].items() if info["missing"]}
        violations = lint["violations"]
        if failed:
            outcome = "regression"
        elif not (build["passed"] and toolchain.tests_passed(result)) or coverage is None:
            outcome = "unknown"
        elif unmet:
            outcome = "criteria_unmet"
        elif gaps:
            outcome = "coverage_short"
        elif violations:
            outcome = "lint_dirty"
        else:
            outcome = drawn
        report = {
            "build_passed": build["passed"],
            "lint_passed": lint["passed"],
            "lint_violation_count": len(violations),
            "lint_violations": violations,
            "test_count": len(result["tests"]),
            "failed": failed,
            "coverage": coverage,
            "coverage_min": self.coverage_min,
            "coverage_gaps": gaps,
            "criteria": criteria,
            "unmet": unmet,
            "outcome": outcome,
        }
        _write(ws / "verification" / "report.json", report)
        _write(
            ws / "verification" / "results.json", {"result": result, "build": build, "lint": lint}
        )
        if failed:
            ctx.emit("regressions", failed)
        if outcome == "criteria_unmet":
            ctx.emit("unmet_criteria", unmet)
        if outcome == "coverage_short":
            ctx.emit("suite_coverage_gaps", gaps)
        if outcome == "lint_dirty":
            ctx.emit("suite_lint_violations", violations)


class Review:
    """変種（fixtures/artifacts/review/）のレビューを写す。blocking の指摘を carry 用に memory に出す。"""

    def __init__(self, source: Script | StochasticSource) -> None:
        self.source = source

    def run(self, ctx: StageContext) -> None:
        drawn = self.source.next("review")
        variant = drawn if drawn in ("changes_requested", "design_flaw") else "goal"
        comments = _yaml(f"artifacts/review/{variant}.yaml")["comments"]
        _write(
            ctx.workspace / "review.json",
            {"variant": variant, "comments": comments, "outcome": drawn},
        )
        blocking = [c for c in comments if c["severity"] == "blocking"]
        if variant == "changes_requested":
            ctx.emit("review_comments", [c for c in blocking if c["kind"] == "code"])
        if variant == "design_flaw":
            ctx.emit("design_issues", [c for c in blocking if c["kind"] == "design"])


# --- release ---


class Release:
    """リリースの記録を作り、依頼者に承認を尋ねる。承認されなければ kind で rejected_requirements / rejected_quality。"""

    def __init__(self, source: Script | StochasticSource) -> None:
        self.source = source

    def run(self, ctx: StageContext) -> None:
        ws = ctx.workspace
        reqs = _read(ws / "requirements.json")["requirements"]
        entries = [
            {
                "id": r["id"],
                "title": r["title"],
                "status": "deferred" if r.get("deferred") else "released",
                "agreed": bool(r.get("agreed")),
                "note": r.get("note", ""),
            }
            for r in reqs
        ]
        released = [e["id"] for e in entries if e["status"] == "released"]
        unagreed = [e["id"] for e in entries if e["status"] == "deferred" and not e["agreed"]]
        agreed = [e["id"] for e in entries if e["status"] == "deferred" and e["agreed"]]
        question = (
            f"{RELEASE_PREFIX} textkit {RELEASE_VERSION} をリリースしてよいですか？ "
            f"含む要件: {', '.join(released)}。"
        )
        if unagreed:
            question += f" {UNAGREED_MARK}: {', '.join(unagreed)}。"
        if agreed:
            question += f" 見送り（合意済み）: {', '.join(agreed)}。"
        answer = ctx.user.ask(question, schema=APPROVAL_SCHEMA)
        drawn = self.source.next("release")
        approved = isinstance(answer, dict) and answer.get("approved") is True
        reason = str(answer.get("reason", "")) if isinstance(answer, dict) else str(answer)
        kind = answer.get("kind") if isinstance(answer, dict) and not approved else None
        files = toolchain.file_digests(ws / "codebase")
        manifest = {
            "name": "textkit",
            "version": RELEASE_VERSION,
            "base_version": toolchain.base_version(),
            "files": files,
            "digest": toolchain.manifest_digest(files),
            "requirements": entries,
        }
        _write(ws / "release" / "manifest.json", manifest)
        lines = [f"# textkit {RELEASE_VERSION}", "", "## 追加", ""]
        lines += [f"- {e['id']}: {e['title']}" for e in entries if e["status"] == "released"]
        deferred = [e for e in entries if e["status"] == "deferred"]
        if deferred:
            lines += ["", "## 見送り（既知の制限）", ""]
            lines += [
                f"- {e['id']}: {e['title']}（{'合意済み' if e['agreed'] else '合意なし'}。{e['note']}）"
                for e in deferred
            ]
        (ws / "release" / "CHANGELOG.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if approved:
            outcome = drawn
        elif kind == "requirements":
            outcome = "rejected_requirements"
        elif kind == "quality":
            outcome = "rejected_quality"
        else:
            outcome = "unknown"  # 種類の無い拒否は分類できない
        _write(
            ws / "release" / "approval.json",
            {
                "question": question,
                "approved": approved,
                "kind": kind,
                "reason": reason,
                "outcome": outcome,
            },
        )
        if not approved:
            ctx.emit("rejection_feedback", {"kind": kind, "reason": reason, "unagreed": unagreed})
