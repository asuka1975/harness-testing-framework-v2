"""整合性検査器の CLI。

終了コード: 0 = 所見なし、1 = 所見あり、2 = 定義やレジストリが読めない。
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

from .checker import check_workflow


def _load_metric_names(manifest: str | None, module: str | None) -> list[str] | None:
    """--metrics（{"metrics": [...]} の JSON）または --metrics-module（pkg.mod:attr、attr は
    names() を持つ）から指標名を読む。どちらも無ければ None（metric_registered をスキップ）。"""
    names: list[str] = []
    if manifest:
        data = json.loads(Path(manifest).read_text(encoding="utf-8"))
        names.extend(data["metrics"])
    if module:
        mod_name, _, attr = module.partition(":")
        if not attr:
            raise ValueError("--metrics-module は pkg.mod:attr の形で書く")
        registry = getattr(importlib.import_module(mod_name), attr)
        names.extend(registry.names())
    if manifest or module:
        return names
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="htf.testing.spec", description="ワークフロー定義の整合性検査"
    )
    parser.add_argument("workflow", help="workflow.yaml")
    parser.add_argument("--metrics", help='指標名のマニフェスト JSON（{"metrics": [...]}）')
    parser.add_argument("--metrics-module", help="指標レジストリ pkg.mod:attr（attr.names()）")
    args = parser.parse_args(argv)

    try:
        metric_names = _load_metric_names(args.metrics, args.metrics_module)
        report = check_workflow(args.workflow, metric_names=metric_names)
    except (OSError, ValueError, KeyError, ImportError, AttributeError, yaml.YAMLError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    for f in report.findings:
        print(f"{f.file}:{f.path} [{f.code}] {f.message}")
    for code in report.skipped:
        print(f"skipped: {code}（レジストリが渡されていない）")
    print(f"{len(report.findings)} finding(s)")
    return 1 if report.findings else 0
