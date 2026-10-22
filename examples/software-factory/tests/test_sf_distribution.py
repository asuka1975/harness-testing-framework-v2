"""分布テスト（雛形第 6 節）と独立性検証（第 7 節）。確率的偽本体（fixtures/profiles/）を種つきで N 回走らせる。

- markov 構成: expectations が通り、ずらした expectations が落ちる。carry つき再進入で分布が変わる（code / unit_test）
- 独立性: markov 構成の unit_test / tests_failing は代表（carry の test_failures）ごとに下流が揃う。split 構成では
  T1 の失敗だけが持続するので検出される
"""

from __future__ import annotations

import pytest
from sf_support import EXPECTATIONS

from htf.testing.stages import check_expectations, independence, load_expectations, tally

pytestmark = pytest.mark.distribution


def _violations(report) -> list[str]:  # noqa: ANN001
    return [
        f"{v.stage_id}/{v.entry_kind}/{v.cls}: {v.observed:.3f} not in "
        f"[{v.interval.min}, {v.interval.max}] (n={v.n})"
        for v in report.violations
    ]


def test_markov_expectations_hold(markov_samples):
    report = check_expectations(
        tally(markov_samples), load_expectations(EXPECTATIONS / "markov.yaml")
    )
    assert report.ok, _violations(report)


def test_shifted_expectations_fail(markov_samples):
    report = check_expectations(
        tally(markov_samples), load_expectations(EXPECTATIONS / "markov_shifted.yaml")
    )
    assert not report.ok
    failed = {(v.stage_id, v.entry_kind, v.cls) for v in report.violations}
    assert ("unit_test", "first", "goal") in failed
    assert (None, None, "completed") in failed


def test_carry_reentry_changes_the_distribution(markov_samples):
    """code は carry（check_failures / test_failures / coverage_gaps）を受けた再進入で直した変更を書きやすい
    （構成の reentry 分布）。それは code の次の check と unit_test の再進入の分布に現れる。"""
    t = tally(markov_samples)
    check_first, check_re = t.by_stage[("check", "first")], t.by_stage[("check", "reentry")]
    unit_first, unit_re = t.by_stage[("unit_test", "first")], t.by_stage[("unit_test", "reentry")]
    assert check_re.total >= 50 and unit_re.total >= 50
    assert check_re.freq("goal") - check_first.freq("goal") >= 0.03
    assert unit_re.freq("goal") - unit_first.freq("goal") >= 0.05
    assert unit_re.freq("tests_failing") < unit_first.freq("tests_failing")


def test_split_expectations_hold(split_samples):
    report = check_expectations(
        tally(split_samples), load_expectations(EXPECTATIONS / "split.yaml")
    )
    assert report.ok, _violations(report)


def test_independence_holds_in_markov(markov_samples):
    report = independence(markov_samples, stage_id="unit_test", cls="tests_failing", seed=7)
    assert report.verifiable
    assert len(report.groups) >= 3
    assert not report.flagged, (report.p_value, report.groups)


def test_independence_detects_split(split_samples):
    report = independence(split_samples, stage_id="unit_test", cls="tests_failing", seed=7)
    assert report.verifiable
    assert report.flagged, (report.p_value, report.groups)


def test_class_whose_carry_does_not_identify_a_representative_is_not_verifiable(markov_samples):
    """review / changes_requested の carry はいつも同じ指摘（fixtures の一変種）なので群が一つ → 検証不能。

    検出されなかったのではなく、検証できない（docs/plan.md 第 7 節に記録）。
    """
    report = independence(markov_samples, stage_id="review", cls="changes_requested", seed=7)
    assert not report.verifiable
