"""ワークフロースキーマの所在と読み込み。

正本はリポジトリ直下の schema/workflow.schema.json（保護ファイル）。配布物（wheel）には
htf/schema/workflow.schema.json として同梱する（pyproject の force-include）。編集可能
インストールでは同梱ファイルが無いので、パッケージ位置からリポジトリ直下へ辿る。
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from pathlib import Path

_PACKAGED = "schema/workflow.schema.json"


def schema_path() -> Path:
    """スキーマファイルのパス。同梱されていればそれ、無ければリポジトリ直下のもの。"""
    packaged = resources.files("htf").joinpath(_PACKAGED)
    if packaged.is_file():
        return Path(str(packaged))
    repo = Path(__file__).resolve().parents[2] / "schema" / "workflow.schema.json"
    if repo.is_file():
        return repo
    raise FileNotFoundError("workflow.schema.json が同梱にもリポジトリにも無い")


@cache
def load_schema() -> dict:
    """スキーマを読み込む（プロセス内で一度だけ）。"""
    return json.loads(schema_path().read_text(encoding="utf-8"))
