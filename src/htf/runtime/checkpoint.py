"""checkpoint: スナップショットの保存・復元・overlay（CONTRACT 第 2・3 節）。

store のレイアウト:
  <root>/<ordinal:04d>/meta.json, memory.json, files/...
files/ は、そのステージの artifacts.writes の範囲の成果物の複製（相対パスを保つ）。
作業ディレクトリ配下の META_DIR（.htf）は runner のメタデータで、保存・復元・writes 外検出の対象外。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from htf.contract import Carry, ContractViolation, JsonValue, Snapshot

META_DIR = ".htf"


def _is_meta(path: Path) -> bool:
    return META_DIR in path.parts


def _iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for p in sorted(root.rglob("*")):
        if p.is_file() and not _is_meta(p.relative_to(root)):
            yield p


def _in_scope(rel: str, writes: Iterable[str]) -> bool:
    for w in writes:
        if w.endswith("/"):
            if rel.startswith(w):
                return True
        elif rel == w:
            return True
    return False


def fingerprint(workspace: Path) -> dict[str, str]:
    """作業ディレクトリ内の全ファイル（META_DIR を除く）の相対パス → 内容のハッシュ。"""
    out: dict[str, str] = {}
    for p in _iter_files(workspace):
        out[p.relative_to(workspace).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def out_of_scope_changes(
    before: Mapping[str, str], after: Mapping[str, str], writes: Iterable[str]
) -> list[str]:
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    return sorted(k for k in changed if not _in_scope(k, writes))


def _copy_scope(src_root: Path, dst_root: Path, writes: Iterable[str]) -> None:
    for w in writes:
        src = src_root / w
        if w.endswith("/"):
            if src.is_dir():
                shutil.copytree(
                    src, dst_root / w, ignore=shutil.ignore_patterns(META_DIR), dirs_exist_ok=True
                )
        elif src.is_file():
            (dst_root / w).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst_root / w)


def _clear_scope(root: Path, writes: Iterable[str]) -> None:
    for w in writes:
        target = root / w
        if w.endswith("/"):
            if target.is_dir():
                shutil.rmtree(target)
        elif target.exists():
            target.unlink()


class SnapshotStore:
    def __init__(self, root: Path, *, workflow: str, version: str | None) -> None:
        self.root = root
        self.workflow = workflow
        self.version = version
        self.root.mkdir(parents=True, exist_ok=True)
        self._ordinal = len([p for p in self.root.iterdir() if p.is_dir()])

    def take(
        self,
        stage_id: str,
        moment: Literal["start", "end"],
        workspace: Path,
        writes: Iterable[str],
        memory: Mapping[str, JsonValue],
    ) -> Snapshot:
        writes = list(writes)
        ordinal = self._ordinal
        self._ordinal += 1
        d = self.root / f"{ordinal:04d}"
        files = d / "files"
        files.mkdir(parents=True)
        _copy_scope(workspace, files, writes)
        (d / "memory.json").write_text(
            json.dumps(memory, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        (d / "meta.json").write_text(
            json.dumps(
                {
                    "workflow": self.workflow,
                    "version": self.version,
                    "stage_id": stage_id,
                    "moment": moment,
                    "ordinal": ordinal,
                    "writes": writes,
                    "taken_at": datetime.now(UTC).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return Snapshot(
            workflow=self.workflow,
            version=self.version,
            stage_id=stage_id,
            moment=moment,
            ordinal=ordinal,
            files=files,
            memory=dict(memory),
        )

    @staticmethod
    def restore(snapshot: Snapshot, workspace: Path, writes: Iterable[str]) -> None:
        """writes の範囲を作業ディレクトリから消し、スナップショットの files を戻す。範囲外には触れない。"""
        writes = list(writes)
        _clear_scope(workspace, writes)
        _copy_scope(snapshot.files, workspace, writes)

    @staticmethod
    def overlay(snapshot: Snapshot, carry: Carry, allowed: Iterable[str]) -> Snapshot:
        allowed = set(allowed)
        undeclared = sorted(set(carry.items) - allowed)
        if undeclared:
            raise ContractViolation(
                f"overlay: 戻り先 {snapshot.stage_id!r} の memory_in に無い鍵 {undeclared}"
            )
        memory = dict(snapshot.memory)
        memory.update(carry.items)
        return Snapshot(
            workflow=snapshot.workflow,
            version=snapshot.version,
            stage_id=snapshot.stage_id,
            moment=snapshot.moment,
            ordinal=snapshot.ordinal,
            files=snapshot.files,
            memory=memory,
        )


def snapshot_digest(snapshot: Snapshot) -> str:
    """files の内容と memory だけのハッシュ。store のパス、ordinal、taken_at は含めない。"""
    h = hashlib.sha256()
    for p in _iter_files(snapshot.files):
        h.update(p.relative_to(snapshot.files).as_posix().encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    h.update(json.dumps(snapshot.memory, ensure_ascii=False, sort_keys=True).encode())
    return h.hexdigest()
