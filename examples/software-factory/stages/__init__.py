"""software-factory の偽ステージ本体。LLM を使わない。

各本体は workflow.yaml / implement-task.yaml の artifacts 宣言どおりにだけ読み書きする。

- 決定論的な本体（intake / analyze / implement / release）は、入力と fixtures/ の成果物から結果が決まる
  （ペルソナの回答、要件の目録、コンポーネントの目録を写す）
- 確率的な本体（design / plan / review / code）は、供給元（sources.py: 台本か種つきの分布）から変種を取り、
  その変種の fixtures/ の成果物を写す。code は fixtures/codebase の変更を当てる
- 実ツールの本体（code / unit_test / verify）は、fixtures のコードベースに対して実際にビルド・lint・テスト・
  カバレッジを走らせ（toolchain.py）、結果を成果物に書く

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
    "Code",
    "Design",
    "INTAKE_QUESTIONS",
    "Implement",
    "Intake",
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
    "properties": {"approved": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["approved"],
}
OVERRIDES = ("unknown", "low_confidence")  # 成果物は goal の形のまま、印だけ変える値


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
    """依頼者に決まった順で質問し、carry された質問（open_questions）も続けて尋ねる。"""

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
    - carry された rejection_feedback: 組の on_feedback の要件の見送りに合意したと記録する
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
        if feedback:
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

    実在する衝突が無い時は、供給元の変種に従う（requirements_conflict なら fixtures の drawn を主張する）。
    """

    def __init__(self, source: Script | StochasticSource) -> None:
        self.source = source

    def run(self, ctx: StageContext) -> None:
        reqs = _read(ctx.workspace / "requirements.json")
        drawn = self.source.next("design")
        active = [r["id"] for r in _active(reqs["requirements"])]
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
        else:
            outcome = drawn
        revisions = [
            {"from": "review", "issue": issue} for issue in ctx.memory.get("design_issues") or []
        ]
        revisions += [
            {"from": "plan", "uncovered_component": cid}
            for cid in ctx.memory.get("uncovered_components") or []
        ]
        doc = {
            "requirements": active,
            "components": components,
            "conflicts": conflicts,
            "revisions": revisions,
            "outcome": outcome,
        }
        _write(ctx.workspace / "design.json", doc)
        if conflicts:
            ctx.emit("conflicts", conflicts)


class Plan:
    """design.json のコンポーネントを、変種（fixtures/artifacts/plan/groupings.yaml）の分け方でタスクにする。"""

    def __init__(self, source: Script | StochasticSource) -> None:
        self.source = source

    def run(self, ctx: StageContext) -> None:
        design = _read(ctx.workspace / "design.json")
        drawn = self.source.next("plan")
        groupings = _yaml("artifacts/plan/groupings.yaml")
        catalog = _yaml("artifacts/design/components.yaml")
        design_ids = [c["id"] for c in design["components"]]
        uncovered: list[str] = []
        if drawn == "design_gap":
            groups = [[cid] for cid in design_ids[:-1]]
            uncovered = design_ids[-1:]
        else:
            fixture = groupings["two_tasks" if drawn == "two_tasks" else "goal"]
            groups = [g for g in ([c for c in g if c in design_ids] for g in fixture) if g]
        tasks = [_task(i, group, catalog) for i, group in enumerate(groups, 1)]
        _attach_notes(tasks, ctx.memory)
        doc = {
            "design_components": design_ids,
            "variant": drawn,
            "tasks": tasks,
            "uncovered_components": uncovered,
            "outcome": "goal" if drawn == "two_tasks" else drawn,
        }
        _write(ctx.workspace / "tasks.json", doc)
        ctx.emit("tasks", tasks)
        if uncovered:
            ctx.emit("uncovered_components", uncovered)


def _task(i: int, group: list[str], catalog: dict) -> dict:
    comps = [catalog[c] for c in group]
    return {
        "id": f"T{i}",
        "title": " と ".join(c["title"] for c in comps),
        "components": list(group),
        "features": [c["feature"] for c in comps],
        "scope": sorted({p for c in comps for p in c["scope"]}),
        "tests": sorted({p for c in comps for p in c["tests"]}),
        "notes": [],
    }


def _attach_notes(tasks: list[dict], memory: dict) -> None:
    """carry された差し戻しを、関係するタスクの notes に書く（子 run は task の中身として受け取る）。"""

    def owners(pred) -> list[dict]:  # noqa: ANN001
        hit = [t for t in tasks if pred(t)]
        return hit or tasks[:1]

    for item in memory.get("unfinished_tasks") or []:
        for t in owners(lambda t, item=item: set(t["features"]) & set(item["features"])):
            t["notes"].append(f"前回の単体テストが通らなかった: {item['summary']}")
    for nodeid in memory.get("regressions") or []:
        module = "src/textkit/" + Path(nodeid.split("::")[0]).stem.removeprefix("test_") + ".py"
        for t in owners(lambda t, module=module: module in t["scope"]):
            t["notes"].append(f"既存のテスト {nodeid} を壊さない")
    for c in memory.get("unmet_criteria") or []:
        test_file = c["test"].split("::")[0]
        for t in owners(lambda t, test_file=test_file: test_file in t["tests"]):
            t["notes"].append(f"受け入れ基準 {c['id']} を確かめるテスト {c['test']} を書く")
    for c in memory.get("review_comments") or []:
        for t in owners(lambda t, c=c: c["target"] in t["scope"]):
            t["notes"].append(f"レビューの指摘（{c['target']}）: {c['text']}")


# --- build（親 implement と子 implement-task） ---


class Implement:
    """子 run が終わった後に走る。単体テストを通ったタスクの変更を base に統合して codebase/ に置く。"""

    def run(self, ctx: StageContext) -> None:
        ws = ctx.workspace
        codebase = ws / "codebase"
        if codebase.exists():
            shutil.rmtree(codebase)
        shutil.copytree(toolchain.BASE, codebase)
        merged, unfinished, conflicts, owner = [], [], [], {}
        for i, task in enumerate(ctx.memory["tasks"]):
            child = ws / "tasks" / str(i)
            code = _read(child / "code.json") if (child / "code.json").is_file() else None
            unit = (
                _read(child / "unit" / "report.json")
                if (child / "unit" / "report.json").is_file()
                else None
            )
            status = _task_status(code, unit)
            if status != "done":
                unfinished.append(
                    {
                        "task": task["id"],
                        "features": task["features"],
                        "status": status,
                        "summary": _summary(status, unit),
                    }
                )
                continue
            for rel in code["changed_paths"]:
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
        doc = {
            "merged": merged,
            "unfinished": unfinished,
            "conflicts": conflicts,
            "changed_paths": toolchain.changed_paths(codebase),
        }
        _write(ws / "merge.json", doc)
        if unfinished:
            ctx.emit("unfinished_tasks", unfinished)


def _task_status(code: dict | None, unit: dict | None) -> str:
    if code is None or not (code["build"]["passed"] and code["lint"]["passed"]):
        return "not_built"
    if code["out_of_scope"]:
        return "out_of_scope"
    if unit is None:
        return "not_tested"
    if unit["failed"]:
        return "tests_failing"
    if unit["coverage_gaps"]:
        return "coverage_low"
    return "done"


def _summary(status: str, unit: dict | None) -> str:
    if status == "tests_failing" and unit:
        return "失敗したテスト " + ", ".join(unit["failed"])
    if status == "coverage_low" and unit:
        return f"カバレッジ {unit['coverage']}（基準 {unit['coverage_min']}）"
    return status


class Code:
    """fixtures のコードベースにタスクの変更（変種）を当て、ビルド・lint・変更パスを確かめる。

    carry（test_failures / coverage_gaps）の無い進入が子 run の始まり。carry つきの再進入では、供給元の
    reentry の分布（直した変更が出やすい）から変種を引く。印は実ツールの結果から決める。
    """

    def __init__(self, source: Script | StochasticSource) -> None:
        self.source = source

    def run(self, ctx: StageContext) -> None:
        task = ctx.memory["task"]
        fixing = {k: ctx.memory[k] for k in ("test_failures", "coverage_gaps") if k in ctx.memory}
        variant = self.source.next("code", unit=task["id"], run_start=not fixing)
        override = variant if variant in OVERRIDES else None
        repo = ctx.workspace / "repo"
        applied = toolchain.materialize(repo, task["features"], "correct" if override else variant)
        build, lint = toolchain.build(repo), toolchain.lint(repo)
        changed = toolchain.changed_paths(repo)
        out_of_scope = [p for p in changed if p not in task["scope"]]
        ok = build["passed"] and lint["passed"] and not out_of_scope
        doc = {
            "task": task["id"],
            "variant": variant,
            "applied": applied,
            "fixing": fixing,
            "notes": task.get("notes", []),
            "changed_paths": changed,
            "out_of_scope": out_of_scope,
            "build": build,
            "lint": lint,
            "outcome": override or ("goal" if ok else "unknown"),
        }
        _write(ctx.workspace / "code.json", doc)


class UnitTest:
    """repo/ でタスクのテストファイルだけを pytest とカバレッジで走らせる。印は結果から決める。"""

    def __init__(self, source: Script | StochasticSource, coverage_min: float) -> None:
        self.source = source
        self.coverage_min = (
            coverage_min  # implement-task.yaml の unit_coverage の基準（harness が渡す）
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
        if failed:
            outcome = "tests_failing"
        elif not toolchain.tests_passed(result) or coverage is None:
            outcome = "unknown"
        elif gaps:
            outcome = "coverage_low"
        else:
            outcome = drawn
        doc = {
            "task": task["id"],
            "result": result,
            "failed": failed,
            "coverage": coverage,
            "coverage_min": self.coverage_min,
            "coverage_gaps": gaps,
            "outcome": outcome,
        }
        _write(ctx.workspace / "unit" / "report.json", doc)
        if failed:
            ctx.emit("test_failures", failed)
        if gaps:
            ctx.emit("coverage_gaps", gaps)


# --- assure ---


class Verify:
    """codebase/ でビルド・lint・テストスイート全体を走らせ、受け入れ基準をテストの結果と照合する。"""

    def __init__(self, source: Script | StochasticSource) -> None:
        self.source = source

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
        unmet = [c for c in criteria if c["status"] == "missing"]
        try:
            coverage: float | None = round(toolchain.line_coverage(result["coverage"]), 4)
        except ValueError:
            coverage = None
        if failed:
            outcome = "regression"
        elif not (build["passed"] and toolchain.tests_passed(result)):
            outcome = "unknown"
        elif unmet:
            outcome = "criteria_unmet"
        else:
            outcome = drawn
        report = {
            "build": build,
            "lint": lint,
            "result": result,
            "coverage": coverage,
            "criteria": criteria,
            "failed": failed,
            "unmet": unmet,
            "outcome": outcome,
        }
        _write(ws / "verification" / "report.json", report)
        if failed:
            ctx.emit("regressions", failed)
        if unmet:
            ctx.emit("unmet_criteria", unmet)


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
    """リリースの記録を作り、依頼者に承認を尋ねる。承認されなければ rejected（印は回答から決まる）。"""

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
        files = toolchain.file_digests(ws / "codebase")
        manifest = {
            "name": "textkit",
            "version": RELEASE_VERSION,
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
        outcome = drawn if approved else "rejected"
        _write(
            ws / "release" / "approval.json",
            {"question": question, "approved": approved, "reason": reason, "outcome": outcome},
        )
        if not approved:
            ctx.emit("rejection_feedback", {"reason": reason, "unagreed": unagreed})
