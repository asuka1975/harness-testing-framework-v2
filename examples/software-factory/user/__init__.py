"""software-factory のユーザーシミュレータ（ペルソナ）。intake と release の質問にペルソナの知識で答える。

ペルソナは fixtures/personas/*.yaml。答えられない質問では WaitingForUser を投げる（runner が中断する）。
中断するペルソナは、そのステージの最初の質問から答えない形にする（adopting-gaps.md G-05: 一部だけ即答して
残りで中断すると、再開時に累積回答が最初の質問から順に当てられてずれる）。busy_sponsor は release の質問
（一つだけ）を保留する。quality_lead は最初のリリースを品質を理由に承認しない（kind: quality）。
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from htf.contract import JsonValue, WaitingForUser

from ..stages import INTAKE_QUESTIONS, RELEASE_PREFIX, UNAGREED_MARK

PERSONA_DIR = Path(__file__).parents[1] / "fixtures" / "personas"


def persona_names() -> list[str]:
    return sorted(p.stem for p in PERSONA_DIR.glob("*.yaml"))


def load_persona(name: str) -> dict:
    return yaml.safe_load((PERSONA_DIR / f"{name}.yaml").read_text(encoding="utf-8"))


class PersonaUserIO:
    """一つのペルソナとして答える UserIO。尋ねられた質問は asked に残る。"""

    def __init__(self, persona: str | dict) -> None:
        self.persona = load_persona(persona) if isinstance(persona, str) else dict(persona)
        self.asked: list[str] = []
        self._release_asked = 0  # reject_quality_once: 一度目は拒否、二度目は承認

    @property
    def name(self) -> str:
        return self.persona["id"]

    def ask(
        self,
        question: str,
        *,
        schema: dict[str, JsonValue] | None = None,
        context: dict[str, JsonValue] | None = None,
    ) -> JsonValue:
        self.asked.append(question)
        for key, text in INTAKE_QUESTIONS:
            if question == text and key in self.persona["answers"]:
                return copy.deepcopy(self.persona["answers"][key])
        if question.startswith("[Q") and "]" in question:
            answer = self.persona.get("clarifications", {}).get(question[1 : question.index("]")])
            if answer:
                return answer
        if question.startswith(RELEASE_PREFIX):
            return self._release(question, schema)
        raise WaitingForUser(question, schema)  # ペルソナの知識に無い質問

    def _release(self, question: str, schema: dict[str, JsonValue] | None) -> JsonValue:
        """承認の回答。承認しない時は kind（requirements / quality）と reason を添える（版 0.2）。"""
        policy = self.persona["release"]
        if policy == "always":
            return {"approved": True, "reason": "要求どおり"}
        if policy == "no_unagreed_deferral":
            if UNAGREED_MARK in question:
                return {
                    "approved": False,
                    "kind": "requirements",
                    "reason": self.persona["rejection_reason"],
                }
            return {"approved": True, "reason": "見送りに合意済み"}
        if policy == "reject_quality_once":
            self._release_asked += 1
            if self._release_asked == 1:
                return {
                    "approved": False,
                    "kind": "quality",
                    "reason": self.persona["rejection_reason"],
                }
            return {"approved": True, "reason": "指摘が反映された"}
        raise WaitingForUser(question, schema)  # later: 会議の後で答える
