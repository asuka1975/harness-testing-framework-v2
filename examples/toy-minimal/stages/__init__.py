"""toy-minimal の決定論的な偽ステージ本体。LLM を使わない。

各本体は workflow.yaml / elaborate-claim.yaml の artifacts 宣言どおりにだけ読み書きする。
「LLM が決めるはずの結果」は台本（ScriptCursor）から取り、成果物の中に印（outcome）として残す。
分類器の偽物（MarkerClassifier）はその印を読む。指標は成果物から本物の値を計算する。
"""

from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Mapping, Sequence

from htf.contract import LLMRequest, StageContext

GOAL = "goal"


class ScriptCursor:
    """ステージ id → n 回目の進入の結果。足りなければ最後を繰り返し、無ければ goal。"""

    def __init__(self, outcomes: Mapping[str, Sequence[str]]) -> None:
        self._outcomes = {k: list(v) for k, v in outcomes.items()}
        self._entries: Counter[str] = Counter()

    def pick(self, stage_id: str, items: Sequence[str]) -> list[str]:
        """台本では先頭を選ぶ（決定論）。"""
        return list(items[:1])

    def next(self, stage_id: str, **_: object) -> str:
        seq = self._outcomes.get(stage_id) or [GOAL]
        i = self._entries[stage_id]
        self._entries[stage_id] += 1
        return seq[min(i, len(seq) - 1)]


class ChildScriptCursor:
    """子 run ごとの台本。begin_run() で次の run の台本に進む（尽きたら全て goal）。"""

    def __init__(self, runs: Sequence[Mapping[str, Sequence[str]]]) -> None:
        self._runs = [dict(r) for r in runs]
        self._started = 0
        self._current = ScriptCursor({})

    def begin_run(self) -> None:
        script = self._runs[self._started] if self._started < len(self._runs) else {}
        self._started += 1
        self._current = ScriptCursor(script)

    def next(self, stage_id: str, *, run_start: bool = False, **_: object) -> str:
        if run_start:
            self.begin_run()
        return self._current.next(stage_id)


class StochasticSource:
    """台本の代わりに、種つきの既知の分布から結果を引く（F3 の確率的偽本体）。

    進入回数（first / reentry）はこの供給元が (stage, claim) ごとに数える。規則は runtime の進入回数と同じ
    （中断からの再開は数えない。子 run の始まり run_start でその主張の計数を消す）。
    split があれば、split.stage の再進入で奇数番目の主張の分布を差し替える（クラス内で代表ごとに下流が分かれる）。
    """

    def __init__(
        self,
        distributions: Mapping[str, Mapping[str, Mapping[str, float]]],
        claims: Sequence[str],
        *,
        seed: int,
        split: Mapping[str, object] | None = None,
    ) -> None:
        self.distributions = {
            s: {k: dict(d) for k, d in kinds.items()} for s, kinds in distributions.items()
        }
        self.claims = list(claims)
        self.split = dict(split) if split else None
        self.rng = random.Random(seed)
        self._entries: Counter[tuple[str, str | None]] = Counter()

    def next(
        self, stage_id: str, *, claim: str | None = None, run_start: bool = False, **_: object
    ) -> str:
        if run_start:
            for key in [k for k in self._entries if k[1] == claim]:
                del self._entries[key]
        key = (stage_id, claim)
        self._entries[key] += 1
        kind = "first" if self._entries[key] == 1 else "reentry"
        kinds = self.distributions[stage_id]
        dist = kinds.get(kind) or kinds["first"]
        if self.split and stage_id == self.split["stage"] and claim is not None:
            parity = "odd_claims" if self.claims.index(claim) % 2 == 1 else "even_claims"
            override = (self.split.get(parity) or {}).get(kind)  # type: ignore[union-attr]
            if override:
                dist = dict(override)
        classes = list(dist)
        return self.rng.choices(classes, [dist[c] for c in classes])[0]

    def pick(self, stage_id: str, items: Sequence[str]) -> list[str]:
        """失敗した主張などを種つきで一つ選ぶ（親側のクラスの代表を主張ごとに分けるため）。"""
        return [self.rng.choice(list(items))] if items else []


# --- 親 workflow.yaml ---


class Collect:
    """ユーザーに 3 つ質問して inputs.json と grounds/ を書く。

    empty_grounds_first の主張は、初回だけ根拠ファイルを空で書く（G1: 所在が指す先が空）。
    missing_inputs を carry で受けた再進入では全て埋める。
    """

    def __init__(self, cursor: ScriptCursor, empty_grounds_first: Sequence[str] = ()) -> None:
        self.cursor = cursor
        self.empty_first = set(empty_grounds_first)

    def run(self, ctx: StageContext) -> None:
        title = ctx.user.ask("題目は?")
        claims = ctx.user.ask("主張の一覧は?")
        grounds = ctx.user.ask("根拠の所在は?")
        assert isinstance(claims, list) and isinstance(grounds, dict)
        outcome = self.cursor.next("collect")
        reentry = "missing_inputs" in ctx.memory
        ws = ctx.workspace
        for claim in claims:
            path = ws / str(grounds[claim])
            path.parent.mkdir(parents=True, exist_ok=True)
            empty = claim in self.empty_first and not reentry
            path.write_text("" if empty else f"根拠: {claim}\n", encoding="utf-8")
        (ws / "inputs.json").write_text(
            json.dumps(
                {"title": title, "claims": claims, "grounds": grounds, "outcome": outcome},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


class Draft:
    """inputs.json から draft.md を書く。根拠が無いか空の主張があれば inputs_insufficient（成果物から決まる）。"""

    def __init__(self, cursor: ScriptCursor) -> None:
        self.cursor = cursor

    def run(self, ctx: StageContext) -> None:
        ws = ctx.workspace
        inputs = json.loads((ws / "inputs.json").read_text(encoding="utf-8"))
        missing = [
            c
            for c in inputs["claims"]
            if not (ws / inputs["grounds"][c]).is_file()
            or (ws / inputs["grounds"][c]).stat().st_size == 0
        ]
        outcome = "inputs_insufficient" if missing else self.cursor.next("draft")
        failing = ctx.memory.get("failing_checks")
        text = ctx.llm.complete(
            LLMRequest(messages=[{"role": "user", "content": f"{inputs['title']} の下書きを書く"}])
        ).text
        lines = [f"# {inputs['title']}", "", f"outcome: {outcome}", ""]
        if failing:
            lines += [f"（再提出。失敗した検査: {', '.join(map(str, failing))}）", ""]
        for claim in inputs["claims"]:
            lines += [f"## {claim}", ""]
            if claim in missing:
                lines += ["（根拠が無いため空）", ""]
            else:
                lines += [text, f"根拠: {inputs['grounds'][claim]}", ""]
        if missing:
            lines += ["---", "足りない項目: " + ", ".join(missing)]
            ctx.emit("missing_inputs", missing)
        (ws / "draft.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


class Verify:
    """draft.md の主張を「検証」して report.json を書く。結果は台本。

    G3: 仮定とは根拠はあるが検証手段が無い主張。根拠の所在が無い主張は仮定にせず inputs_missing にする。
    """

    def __init__(self, cursor: ScriptCursor) -> None:
        self.cursor = cursor

    def run(self, ctx: StageContext) -> None:
        ws = ctx.workspace
        draft = (ws / "draft.md").read_text(encoding="utf-8")
        claims = [line[3:] for line in draft.splitlines() if line.startswith("## ")]
        outcome = self.cursor.next("verify")
        verified, assumed, failed, missing = list(claims), [], [], []
        if outcome == "goal_assumed":
            # 根拠はあるが検証手段が無い主張を、理由つきで仮定として記録する（G3）。印は goal
            outcome = "goal"
            assumed = [{"claim": c, "reason": "根拠はあるが検証手段が無い"} for c in claims[:1]]
            verified = claims[1:]
        elif outcome == "checks_failed":
            failed = self.cursor.pick("verify", claims)
            verified = [c for c in claims if c not in failed]
        elif outcome == "inputs_missing":
            picked = self.cursor.pick("verify", claims)
            missing = [f"{c} の外部データ" for c in picked]
            verified = [c for c in claims if c not in picked]
        ratio = len(verified) / len(claims) if claims else 0.0
        report = {
            "outcome": outcome,
            "claims": claims,
            "verified": verified,
            "assumed": assumed,
            "failed": failed,
            "missing_inputs": missing,
            "verified_ratio": ratio,
            "notes": ctx.memory.get("section_findings"),
        }
        (ws / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if failed:
            ctx.emit("failing_checks", failed)
        if missing:
            ctx.emit("missing_inputs", missing)
        ctx.emit("claims", verified)


class Elaborate:
    """子 run が終わった後に走る。各節の検査結果をまとめて section_findings に出す。"""

    def run(self, ctx: StageContext) -> None:
        findings = []
        for check in sorted((ctx.workspace / "sections").glob("*/section-check.json")):
            data = json.loads(check.read_text(encoding="utf-8"))
            if not data.get("consistent", False):
                findings.append({"section": check.parent.name, "issues": data.get("issues", [])})
        if findings:
            ctx.emit("section_findings", findings)


# --- 子 elaborate-claim.yaml ---


class WriteSection:
    """claim から section.md を書く。carry（inconsistencies）の無い進入が子 run の始まり。"""

    def __init__(self, cursor: ChildScriptCursor) -> None:
        self.cursor = cursor

    def run(self, ctx: StageContext) -> None:
        claim = ctx.memory["claim"]
        outcome = self.cursor.next(
            "write_section", claim=claim, run_start="inconsistencies" not in ctx.memory
        )
        fixes = ctx.memory.get("inconsistencies")
        lines = [f"# {claim}", "", f"{claim} について述べる。"]
        if fixes:
            lines += ["", f"修正: {', '.join(map(str, fixes))}"]
        lines += ["", f"outcome: {outcome}", ""]
        (ctx.workspace / "section.md").write_text("\n".join(lines), encoding="utf-8")


class CheckSection:
    def __init__(self, cursor: ChildScriptCursor) -> None:
        self.cursor = cursor

    def run(self, ctx: StageContext) -> None:
        section = (ctx.workspace / "section.md").read_text(encoding="utf-8")
        outcome = self.cursor.next(
            "check_section", claim=ctx.memory["claim"], reentry="修正:" in section
        )
        consistent = outcome == GOAL
        issues = [] if consistent else [f"{ctx.memory['claim']} と整合しない文がある"]
        (ctx.workspace / "section-check.json").write_text(
            json.dumps(
                {"outcome": outcome, "consistent": consistent, "issues": issues}, ensure_ascii=False
            ),
            encoding="utf-8",
        )
        if outcome == "inconsistent":
            ctx.emit("inconsistencies", issues)
