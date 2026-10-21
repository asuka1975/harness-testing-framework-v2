"""リポジトリの骨格と固定形式の検査。

F1 初期化タスクの完了条件（docs/progress.md 2026-10-22 の check_init.py）を、
ADR-010 の決定（P2 配置）に合わせて移植したもの。

- 第4節の骨格ディレクトリ（ADR-010 の対応表どおりの実パス）が存在する
- schema/workflow.schema.json が Draft 2020-12 メタスキーマに適合する
- 拡張スキーマが付録 A の基底スキーマの構造（properties / required / type / items）を保っている
  （付録 A「既存の意味は変えない」の機械的な下限）
- docs/decisions.md に ADR-001〜010 があり、各 ADR に 推奨 / 決定 / 強制点 がある
- docs/progress.md が第4節末尾の固定形式に従う
- pyproject の version と htf.__version__ が一致する
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import jsonschema
import pytest

import htf

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "workflow.schema.json"
PLAN_PATH = ROOT / "docs" / "plan.md"


@pytest.mark.parametrize(
    "rel",
    [
        "schema/examples",
        "src/htf/contract",
        "src/htf/runtime",
        "src/htf/testing/spec",
        "src/htf/testing/harness",
        "src/htf/testing/oracle",
        "src/htf/testing/stages",
        "src/htf/testing/e2e",
        "src/htf/testing/triage",
        "examples/toy-minimal/stages",
        "examples/toy-minimal/tests",
        "docs",
        "reports",
        "tests",
    ],
)
def test_skeleton_dir_exists(rel: str) -> None:
    assert (ROOT / rel).is_dir(), rel


def test_software_factory_is_not_pre_created() -> None:
    # F4 の利用者セッションが adopting.md と雛形だけから作る成果物。骨格を先に置かない
    # F4 が始まったらこのテストは外す（progress.md に記録すること）
    assert not (ROOT / "examples" / "software-factory").exists()


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_schema_conforms_to_metaschema() -> None:
    jsonschema.Draft202012Validator.check_schema(_load_schema())


def _appendix_a() -> dict:
    plan = PLAN_PATH.read_text(encoding="utf-8")
    m = re.search(r"## 付録 A.*?```json\n(.*?)```", plan, re.S)
    assert m is not None, "plan.md に付録 A の JSON ブロックが無い"
    return json.loads(m.group(1))


def _resolve(node: dict, root: dict) -> dict:
    """同一文書内の $ref（#/...）だけを解決する。"""
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        assert ref.startswith("#/"), ref
        cur: dict = root
        for part in ref[2:].split("/"):
            cur = cur[part.replace("~1", "/").replace("~0", "~")]
        node = cur
    return node


def _assert_extends(base: dict, ext: dict, root: dict, path: str) -> None:
    ext = _resolve(ext, root)
    if "type" in base:
        assert ext.get("type") == base["type"], f"{path}: type が変わった"
    for key in base.get("required", []):
        assert key in ext.get("required", []), f"{path}: required {key} が外れた"
    for key, sub in base.get("properties", {}).items():
        assert key in ext.get("properties", {}), f"{path}: property {key} が消えた"
        _assert_extends(sub, ext["properties"][key], root, f"{path}.{key}")
    if "items" in base:
        assert "items" in ext, f"{path}: items が消えた"
        _assert_extends(base["items"], ext["items"], root, f"{path}[]")


def test_schema_preserves_appendix_a_structure() -> None:
    schema = _load_schema()
    _assert_extends(_appendix_a(), schema, schema, "$")


def test_decisions_has_ten_adrs_with_fixed_sections() -> None:
    text = (ROOT / "docs" / "decisions.md").read_text(encoding="utf-8")
    sections = re.split(r"^## ADR-", text, flags=re.M)[1:]
    ids = [s.split()[0] for s in sections]
    assert ids == [f"{i:03d}" for i in range(1, 11)], ids
    for adr_id, s in zip(ids, sections, strict=True):
        for heading in ("### 推奨", "### 決定"):
            assert re.search(rf"^{heading}", s, re.M), f"ADR-{adr_id}: {heading} が無い"
        assert re.search(r"^- 強制点:", s, re.M), f"ADR-{adr_id}: 強制点 が無い"


def test_progress_follows_fixed_format() -> None:
    text = (ROOT / "docs" / "progress.md").read_text(encoding="utf-8")
    heads = re.findall(r"^## (.+)$", text, re.M)
    assert heads and heads[0].strip() == "次にやること"
    for h in ("完了したこと", "未完了と理由", "発見した問題", "実行した検証とその結果の要旨"):
        assert re.search(rf"^### {h}", text, re.M), h
    for h in ("ワークフロー定義の問題", "フレームワーク本体の不足"):
        assert re.search(rf"^#### {h}", text, re.M), h


def test_version_matches_pyproject() -> None:
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert htf.__version__ == meta["project"]["version"]
