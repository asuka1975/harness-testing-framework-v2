from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOY_ROOT = ROOT / "examples" / "toy-minimal"


@pytest.fixture(scope="session")
def toy() -> ModuleType:
    """toy-minimal を Python パッケージ toy_minimal として読む（htf.testing.harness の読み込み口）。"""
    from htf.testing.harness import load_example_package

    return load_example_package(TOY_ROOT, "toy_minimal")
