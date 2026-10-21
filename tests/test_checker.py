"""整合性検査器の完了条件（F1）。

- 検査器の各性質（コード）に負例があり、その負例を検査器が当該コードで報告する
- 正例には所見が無い
- コードカタログ CODES と負例ディレクトリに現れるコードの集合が一致する
  （コードを足して負例を忘れると落ちる）
- 指標レジストリを渡さない時は metric_registered を「スキップ」として明示する
- CLI の終了コード: 0 = 所見なし、1 = 所見あり、2 = 読み込み失敗
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from htf.testing.spec import CODES, check_workflow
from htf.testing.spec.cli import main

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "schema" / "examples"
POSITIVE_DIR = EXAMPLES / "positive"
NEGATIVE_DIR = EXAMPLES / "negative"
METRICS = EXAMPLES / "metrics.json"


def _metric_names() -> list[str]:
    return json.loads(METRICS.read_text(encoding="utf-8"))["metrics"]


def _positives() -> list[Path]:
    return sorted(POSITIVE_DIR.glob("*.yaml"))


def _negatives() -> list[Path]:
    return sorted(NEGATIVE_DIR.glob("*.yaml"))


def _expected_code(path: Path) -> str:
    return path.name.split("__", 1)[0]


@pytest.mark.parametrize("path", _positives(), ids=lambda p: p.name)
def test_positive_has_no_findings(path: Path) -> None:
    report = check_workflow(path, metric_names=_metric_names())
    assert report.findings == [], [f"{f.code} {f.path}: {f.message}" for f in report.findings]
    assert report.skipped == []


@pytest.mark.parametrize("path", _negatives(), ids=lambda p: p.name)
def test_negative_reports_expected_code(path: Path) -> None:
    report = check_workflow(path, metric_names=_metric_names())
    codes = {f.code for f in report.findings}
    assert _expected_code(path) in codes, (
        f"{path.name}: 期待コード {_expected_code(path)} が無い。報告: "
        + ", ".join(f"{f.code}@{f.path}" for f in report.findings)
    )


def test_every_code_has_a_negative_and_vice_versa() -> None:
    in_examples = {_expected_code(p) for p in _negatives()}
    assert in_examples == set(CODES), {
        "負例の無いコード": set(CODES) - in_examples,
        "カタログに無いコード": in_examples - set(CODES),
    }


def test_metric_check_is_skipped_without_registry() -> None:
    report = check_workflow(_positives()[0], metric_names=None)
    assert report.skipped == ["metric_registered"]
    assert report.findings == []


def test_cli_exit_codes(tmp_path: Path) -> None:
    positive = _positives()[0]
    assert main([str(positive), "--metrics", str(METRICS)]) == 0
    assert main([str(_negatives()[0]), "--metrics", str(METRICS)]) == 1
    assert main([str(tmp_path / "missing.yaml"), "--metrics", str(METRICS)]) == 2
    # レジストリ無しでも所見が無ければ 0 だが、スキップを標準出力に出す
    assert main([str(positive)]) == 0
