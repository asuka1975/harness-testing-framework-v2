"""スキーマの正例・負例（F1 の完了条件「正例が通り負例が落ちる」）。

- schema/examples/positive/*.yaml はスキーマに適合する
- schema/examples/negative/<code>__<name>.yaml のうち code が schema のものはスキーマで落ちる
  （それ以外の code は検査器が捕まえる。tests/test_checker.py）
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "workflow.schema.json"
POSITIVE_DIR = ROOT / "schema" / "examples" / "positive"
NEGATIVE_DIR = ROOT / "schema" / "examples" / "negative"


def _validator() -> jsonschema.Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def _load(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _positives() -> list[Path]:
    return sorted(POSITIVE_DIR.glob("*.yaml"))


def _schema_negatives() -> list[Path]:
    return sorted(p for p in NEGATIVE_DIR.glob("*.yaml") if p.name.startswith("schema__"))


def test_examples_exist() -> None:
    assert _positives(), "正例が無い"
    assert _schema_negatives(), "スキーマ段階の負例が無い"


@pytest.mark.parametrize("path", _positives(), ids=lambda p: p.name)
def test_positive_validates(path: Path) -> None:
    errors = list(_validator().iter_errors(_load(path)))
    assert errors == [], [e.message for e in errors]


@pytest.mark.parametrize("path", _schema_negatives(), ids=lambda p: p.name)
def test_schema_negative_is_rejected(path: Path) -> None:
    errors = list(_validator().iter_errors(_load(path)))
    assert errors, f"{path.name} がスキーマを通ってしまう"
