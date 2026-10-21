"""pytest プラグイン（探針 P0）: ソケットの生成を禁止して全テストを走らせ、ネットワーク（LLM API）を呼んでいないことを確かめる。

実行: PYTHONPATH=reports/verification/f3-test-runners uv run pytest -o addopts="" -p blocknet -q
"""

from __future__ import annotations

import socket


class _NoNetwork(RuntimeError):
    pass


def _blocked(*_a, **_k):  # noqa: ANN002, ANN003
    raise _NoNetwork("探針 blocknet: テスト中にソケットが作られた（ネットワーク呼び出し）")


def pytest_configure(config) -> None:  # noqa: ANN001
    socket.socket = _blocked  # type: ignore[misc,assignment]
    socket.create_connection = _blocked  # type: ignore[assignment]
    socket.getaddrinfo = _blocked  # type: ignore[assignment]
