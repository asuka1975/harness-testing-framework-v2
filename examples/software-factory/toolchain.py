"""実ツール（ビルド・テスト・カバレッジ・lint）と、フィクスチャのコードベースへの変更の適用。

本体（code / check / unit_test / integrate / verify / release）と指標の両方が使う。

- 作業ディレクトリには成果物以外を書かない。バイトコード、pytest のキャッシュ、カバレッジのデータ、ruff の
  キャッシュはすべて作業ディレクトリ外の一時ディレクトリへ逃がす（参照ランタイムは writes 外の変更を検出する）
- ツールの出力は時刻・所要時間・絶対パスを落として正規化する（記録→再生でスナップショットの digest が一致する）
- 同じ内容の入力には同じ出力なので、内容のハッシュで結果をメモ化する（分布テストは同じ変更を何百回も検査する）。
  メモ化は観測できる結果を変えない。`set_cache(False)` で切れる
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
BASE = FIXTURES / "codebase" / "base"
CHANGES = FIXTURES / "codebase" / "changes"
# 変更のフィクスチャは .py.txt で置く（意図的な lint 違反・構文エラーをリポジトリ全体の ruff から外すため）
FIXTURE_SUFFIX = ".txt"
LINT_RULES = "E,F,W,I,B"
TIMEOUT = 120

_cache: dict[tuple, dict] = {}
_cache_enabled = True


def set_cache(enabled: bool) -> None:
    global _cache_enabled
    _cache_enabled = enabled
    _cache.clear()


def _memo(key: tuple, compute):  # noqa: ANN001, ANN202
    if _cache_enabled and key in _cache:
        return copy.deepcopy(_cache[key])
    value = compute()
    if _cache_enabled:
        _cache[key] = copy.deepcopy(value)
    return value


# --- コードベースの組み立てと差分 ---


def variants(feature: str) -> list[str]:
    return sorted(p.name for p in (CHANGES / feature).iterdir() if p.is_dir())


def materialize(repo: Path, features: Sequence[str], variant: str) -> list[str]:
    """repo を base で作り直し、各機能に correct を、その上に variant を重ねる。

    variant を持たない機能は correct のまま（例: regression は slug にしか無い）。適用した "機能:変種" を返す。
    """
    if repo.exists():
        shutil.rmtree(repo)
    shutil.copytree(BASE, repo)
    applied = []
    for feature in features:
        _overlay(CHANGES / feature / "correct", repo)
        chosen = variant if (CHANGES / feature / variant).is_dir() else "correct"
        if chosen != "correct":
            _overlay(CHANGES / feature / chosen, repo)
        applied.append(f"{feature}:{chosen}")
    return applied


def _overlay(src: Path, repo: Path) -> None:
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src).as_posix()
        if not rel.endswith(FIXTURE_SUFFIX):
            raise ValueError(f"変更のフィクスチャは {FIXTURE_SUFFIX} で終わる: {path}")
        dest = repo / rel[: -len(FIXTURE_SUFFIX)]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)


def files_of(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        return {}
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def changed_paths(repo: Path, base: Path = BASE) -> list[str]:
    """base と比べて追加・変更・削除されたパス（repo 相対）。"""
    before, after = files_of(base), files_of(repo)
    return sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))


def content_digest(root: Path) -> str:
    h = hashlib.sha256()
    for rel, data in files_of(root).items():
        h.update(rel.encode())
        h.update(b"\0")
        h.update(hashlib.sha256(data).digest())
    return h.hexdigest()


def file_digests(root: Path) -> dict[str, str]:
    return {rel: hashlib.sha256(data).hexdigest() for rel, data in files_of(root).items()}


def manifest_digest(files: dict[str, str]) -> str:
    """ファイルごとのダイジェストから全体のダイジェストを作る（release 本体と指標が同じ計算を使う）。"""
    lines = "".join(f"{path}:{digest}\n" for path, digest in sorted(files.items()))
    return hashlib.sha256(lines.encode()).hexdigest()


# --- ツール ---


def build(repo: Path) -> dict:
    """Python のビルド = 全 .py のバイトコンパイル。compile() で行い、何も書かない。"""
    errors = []
    sources = sorted(p for p in repo.rglob("*.py") if p.is_file())
    for path in sources:
        rel = path.relative_to(repo).as_posix()
        try:
            compile(path.read_bytes(), rel, "exec", dont_inherit=True)
        except SyntaxError as e:
            errors.append({"path": rel, "line": e.lineno, "message": e.msg})
    return {"passed": not errors and bool(sources), "files": len(sources), "errors": errors}


def lint(repo: Path) -> dict:
    """ruff（設定ファイルを読まない固定の規則）。違反を正規化して返す。"""
    return _memo(("lint", LINT_RULES, content_digest(repo)), lambda: _lint(repo))


def _lint(repo: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="sf-lint-") as tmp:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--isolated",
                "--no-cache",
                "--select",
                LINT_RULES,
                "--target-version",
                "py312",
                "--output-format",
                "json",
                ".",
            ],
            cwd=repo,
            env=_env(Path(tmp), repo),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"ruff が失敗した（{proc.returncode}）: {proc.stderr.strip()}")
    violations = sorted(
        (
            {
                "path": _rel(v["filename"], repo),
                "line": v["location"]["row"],
                "code": v.get("code") or "syntax",
                "message": v["message"],
            }
            for v in json.loads(proc.stdout or "[]")
        ),
        key=lambda v: (v["path"], v["line"], v["code"]),
    )
    return {"passed": not violations, "rules": LINT_RULES, "violations": violations}


def run_tests(repo: Path, tests: Sequence[str]) -> dict:
    """pytest をカバレッジ付きで走らせる。tests は repo 相対のテストファイル（空ならスイート全体）。"""
    key = ("tests", content_digest(repo), tuple(tests))
    return _memo(key, lambda: _run_tests(repo, list(tests)))


def _run_tests(repo: Path, tests: list[str]) -> dict:
    with tempfile.TemporaryDirectory(prefix="sf-tests-") as tmp_name:
        tmp = Path(tmp_name)
        rcfile = tmp / "coveragerc"
        rcfile.write_text("[run]\nbranch = False\n", encoding="utf-8")
        data, junit, cov_json = tmp / "coverage.data", tmp / "junit.xml", tmp / "coverage.json"
        env = _env(tmp, repo)
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "coverage",
                "run",
                f"--rcfile={rcfile}",
                f"--data-file={data}",
                "--source=src",
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "-q",
                f"--junitxml={junit}",
                "-o",
                "junit_family=xunit2",
                *tests,
            ],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        if data.exists():
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "coverage",
                    "json",
                    f"--rcfile={rcfile}",
                    f"--data-file={data}",
                    "-o",
                    str(cov_json),
                ],
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
            )
        results = _parse_junit(junit) if junit.exists() else []
        coverage = _parse_coverage(cov_json, repo) if cov_json.exists() else {}
    return {
        "command": ["pytest", *tests] if tests else ["pytest"],
        "returncode": proc.returncode,
        "tests": results,
        "coverage": coverage,
    }


def _parse_junit(path: Path) -> list[dict]:
    out = []
    for case in ET.parse(path).getroot().iter("testcase"):
        classname, name = case.get("classname", ""), case.get("name", "")
        nodeid = f"{classname.replace('.', '/')}.py::{name}" if classname else name
        # 鍵は status（outcome は分類器が読む印の鍵なので使わない）
        if case.find("failure") is not None:
            status = "failed"
        elif case.find("error") is not None:
            status = "error"
        elif case.find("skipped") is not None:
            status = "skipped"
        else:
            status = "passed"
        out.append({"nodeid": nodeid, "status": status})
    return sorted(out, key=lambda r: r["nodeid"])


def _parse_coverage(path: Path, repo: Path) -> dict:
    files = json.loads(path.read_text(encoding="utf-8")).get("files", {})
    out = {}
    for name, info in files.items():
        summary = info["summary"]
        out[_rel(name, repo)] = {
            "statements": summary["num_statements"],
            "covered": summary["covered_lines"],
            "missing": sorted(info.get("missing_lines", [])),
        }
    return dict(sorted(out.items()))


def _rel(name: str, repo: Path) -> str:
    p = Path(name)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(repo.resolve()).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix()


def _env(tmp: Path, repo: Path) -> dict[str, str]:
    """子プロセスの環境。外側の pytest / カバレッジの設定を持ち込まず、書き込みを tmp に逃がす。"""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("COV_CORE_", "PYTEST_", "COVERAGE_"))
    }
    env.update(
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONPYCACHEPREFIX=str(tmp / "pycache"),
        PYTHONPATH=str(repo / "src"),
        PYTHONHASHSEED="0",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
    )
    return env


def check(repo: Path, scope: Sequence[str]) -> dict:
    """子の check が書く正規化した記録: ビルド、lint、base から変わったパスと task.scope の照合。

    指標（build_passed / lint_clean / changed_paths_in_scope）はこの記録（check.json）から計算する。
    """
    changed = changed_paths(repo)
    return {
        "build": build(repo),
        "lint": lint(repo),
        "changed_paths": changed,
        "out_of_scope": [p for p in changed if p not in scope],
        "scope": list(scope),
    }


def base_version() -> str:
    """fixtures の base の版（release の manifest の base_version と、指標の照合に使う）。"""
    import tomllib

    return tomllib.loads((BASE / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]


# --- 正規化した結果からの集計（本体の印と指標が同じ計算を使う） ---


def failed_tests(result: dict) -> list[str]:
    return [t["nodeid"] for t in result["tests"] if t["status"] in ("failed", "error")]


def tests_passed(result: dict) -> bool:
    return result["returncode"] == 0 and bool(result["tests"]) and not failed_tests(result)


def line_coverage(coverage: dict, paths: Sequence[str] | None = None) -> float:
    """paths（None なら全ファイル）の行カバレッジ。対象の文が一つも無ければ例外（評価不能）。"""
    chosen = [info for p, info in coverage.items() if paths is None or p in paths]
    statements = sum(info["statements"] for info in chosen)
    if statements == 0:
        raise ValueError("カバレッジの対象の文が無い")
    return sum(info["covered"] for info in chosen) / statements
