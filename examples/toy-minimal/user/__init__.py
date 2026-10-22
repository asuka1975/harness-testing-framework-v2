"""toy-minimal のユーザーシミュレータ。collect の 3 つの質問にペルソナの知識で答える。"""

from __future__ import annotations

from collections.abc import Sequence

from htf.contract import JsonValue, WaitingForUser


class PersonaUserIO:
    def __init__(self, title: str, claims: Sequence[str]) -> None:
        self.title = title
        self.claims = list(claims)
        self.asked: list[str] = []

    def ask(
        self,
        question: str,
        *,
        schema: dict[str, JsonValue] | None = None,
        context: dict[str, JsonValue] | None = None,
    ) -> JsonValue:
        self.asked.append(question)
        if question == "題目は?":
            return self.title
        if question == "主張の一覧は?":
            return list(self.claims)
        if question == "根拠の所在は?":
            return {c: f"grounds/{i}.txt" for i, c in enumerate(self.claims)}
        raise WaitingForUser(question, schema)  # ペルソナの知識に無い質問
