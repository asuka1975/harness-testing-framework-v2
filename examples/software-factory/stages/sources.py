"""結果の供給元: 台本（決定論）と、種つきの既知の分布（確率的）。

本体は「LLM が決めるはずの結果」だけを供給元から取る。

- code: 当てる変更の変種（correct / failing / failing_edge / low_coverage / regression / missing_test / lint /
  broken / out_of_scope。unknown / low_confidence は correct を当てて印だけ変える）
- design / plan / review: 成果物の変種（各ステージの end_state か goal。plan は two_tasks も goal の一種）
- それ以外（intake / analyze / unit_test / verify / release）: 成果物から決まる結果が goal の時だけ使う上書き
  （goal / unknown / low_confidence）

本体は進入のたびに必ず一度 next を呼ぶ（成果物から結果が決まる時も呼び、値を捨てる）。供給元が数える進入回数を
runtime の進入回数（first / reentry）と揃えるため。ユーザー入出力を使う本体は、質問の後で呼ぶ（中断した試行で
数えない）。
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Mapping, Sequence

CHILD_STAGES = frozenset({"code", "unit_test"})
DEFAULTS = {"code": "correct"}  # 他のステージの既定は goal


def default_for(stage_id: str) -> str:
    return DEFAULTS.get(stage_id, "goal")


class ScriptCursor:
    """ステージ id → n 回目の進入の値。足りなければ最後を繰り返し、無ければ既定。"""

    def __init__(self, outcomes: Mapping[str, Sequence[str]]) -> None:
        self._outcomes = {k: list(v) for k, v in outcomes.items()}
        self._entries: Counter[str] = Counter()

    def next(self, stage_id: str) -> str:
        seq = self._outcomes.get(stage_id) or [default_for(stage_id)]
        i = self._entries[stage_id]
        self._entries[stage_id] += 1
        return seq[min(i, len(seq) - 1)]


class Script:
    """親の台本と、子 run ごとの台本（子 run の開始順）。尽きた子 run は全て既定。

    子 run の始まりは「carry（test_failures / coverage_gaps）の無い code の進入」（run_start）で判定する。
    子 run には人間の解決（Rerun、carry 無しの RollbackTo）が届かないので、この判定は誤らない。
    """

    def __init__(
        self,
        outcomes: Mapping[str, Sequence[str]],
        child_runs: Sequence[Mapping[str, Sequence[str]]] = (),
    ) -> None:
        self._parent = ScriptCursor(outcomes)
        self._child_runs = [dict(r) for r in child_runs]
        self._started = 0
        self._child = ScriptCursor({})

    def next(self, stage_id: str, *, unit: str | None = None, run_start: bool = False) -> str:
        if stage_id not in CHILD_STAGES:
            return self._parent.next(stage_id)
        if run_start:
            script = (
                self._child_runs[self._started] if self._started < len(self._child_runs) else {}
            )
            self._started += 1
            self._child = ScriptCursor(script)
        return self._child.next(stage_id)


class StochasticSource:
    """台本の代わりに、種つきの既知の分布から値を引く（確率的偽本体）。

    distributions: ステージ → first | reentry → 値 → 確率。無いステージは既定（goal / correct）を返す。
    進入回数は (ステージ, 単位) ごとに数える。単位は子のステージならタスク id、親のステージなら None。
    子 run の始まり（run_start）でそのタスクの計数を消す。規則は runtime の進入回数と同じ。
    split があれば、split.stage の split.unit（タスク id）だけ分布を差し替える（クラス内で代表ごとに下流が分かれる
    構成。そのタスクの失敗は持続し、子 run をやり直しても変わらない）。
    """

    def __init__(
        self,
        distributions: Mapping[str, Mapping[str, Mapping[str, float]]],
        *,
        seed: int,
        split: Mapping[str, object] | None = None,
    ) -> None:
        self.distributions = {
            s: {k: dict(d) for k, d in kinds.items()} for s, kinds in distributions.items()
        }
        self.split = dict(split) if split else None
        self.rng = random.Random(seed)
        self._entries: Counter[tuple[str, str | None]] = Counter()

    def next(self, stage_id: str, *, unit: str | None = None, run_start: bool = False) -> str:
        if run_start:
            for key in [k for k in self._entries if k[1] == unit]:
                del self._entries[key]
        key = (stage_id, unit)
        self._entries[key] += 1
        kind = "first" if self._entries[key] == 1 else "reentry"
        kinds = self.distributions.get(stage_id)
        if not kinds:
            return default_for(stage_id)
        dist = kinds.get(kind) or kinds["first"]
        if self.split and stage_id == self.split["stage"] and unit == self.split["unit"]:
            dist = dict(self.split.get(kind) or dist)  # type: ignore[arg-type]
        values = list(dist)
        return self.rng.choices(values, [dist[v] for v in values])[0]
