"""toy-minimal の指標レジストリ。manifest.json の名前を、成果物から本物の値を計算する関数で実装する。

指標はスナップショットの files（そのステージ / フェーズの writes の範囲）だけを見る。
"""

from __future__ import annotations

import json
from pathlib import Path

from htf.contract import JsonValue, Snapshot
from htf.runtime import DictMetricRegistry

MANIFEST_PATH = Path(__file__).parent / "manifest.json"


def _json(snapshot: Snapshot, name: str) -> dict:
    return json.loads((snapshot.files / name).read_text(encoding="utf-8"))


def inputs_complete(s: Snapshot) -> JsonValue:
    d = _json(s, "inputs.json")
    return (
        bool(d["title"])
        and bool(d["claims"])
        and all(bool(d["grounds"].get(c)) for c in d["claims"])
    )


def draft_exists(s: Snapshot) -> JsonValue:
    return (s.files / "draft.md").is_file()


def claim_count(s: Snapshot) -> JsonValue:
    text = (s.files / "draft.md").read_text(encoding="utf-8")
    return sum(1 for line in text.splitlines() if line.startswith("## "))


def report_exists(s: Snapshot) -> JsonValue:
    path = s.files / "report.json"
    return path.is_file() and {"claims", "verified_ratio"} <= set(_json(s, "report.json"))


def verified_ratio(s: Snapshot) -> JsonValue:
    return _json(s, "report.json")["verified_ratio"]


def sections_count(s: Snapshot) -> JsonValue:
    return len(list((s.files / "sections").glob("*/section.md")))


def section_exists(s: Snapshot) -> JsonValue:
    return (s.files / "section.md").is_file()


def section_consistent(s: Snapshot) -> JsonValue:
    return _json(s, "section-check.json")["consistent"]


def registry() -> DictMetricRegistry:
    reg = DictMetricRegistry(
        {
            "inputs_complete": inputs_complete,
            "draft_exists": draft_exists,
            "claim_count": claim_count,
            "report_exists": report_exists,
            "verified_ratio": verified_ratio,
            "sections_count": sections_count,
            "section_exists": section_exists,
            "section_consistent": section_consistent,
        }
    )
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["metrics"]
    assert sorted(manifest) == reg.names(), "manifest.json とレジストリの名前が一致しない"
    return reg
