"""検証役の探針（probe）生成。正例を一箇所だけ壊した YAML を probes/ に書く。schema/examples には置かない。
実行: uv run python reports/verification/f1-contract-and-spec/probes/make_probes.py（リポジトリのルートで）
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
POS = ROOT / "schema/examples/positive"
OUT = Path(__file__).resolve().parent
MIN = (POS / "minimal.yaml").read_text(encoding="utf-8")
SUB = (POS / "with_subworkflow.yaml").read_text(encoding="utf-8")
LEAF = (ROOT / "schema/examples/children/leaf.yaml").read_text(encoding="utf-8")
# probes/ から見た children/leaf.yaml の相対パスに直す（正例の ../children/ は probes/ からは解決できない）
SUB = SUB.replace("ref: ../children/leaf.yaml", "ref: ../../../../schema/examples/children/leaf.yaml")


def sub1(text: str, old: str, new: str) -> str:
    assert text.count(old) >= 1, old
    return text.replace(old, new, 1)


probes = {
    # P1 フェーズの goal.quantitative に未登録の指標（ADR-005: フェーズ指標の存在検査）
    "p1_phase_metric_unregistered.yaml": sub1(
        MIN, "draft_exists: { description: draft.md がある, equals: true }",
        "no_such_phase_metric: { description: 未登録の指標, equals: true }"),
    # P2 戻り先が自分より後ろのステージ（self ではなく真の前方参照）
    "p2_rollback_to_later_stage.yaml": sub1(
        SUB, "{ state: checks_failed, stage: draft, carry: [failing_checks], max: 2 }",
        "{ state: checks_failed, stage: elaborate, carry: [failing_checks], max: 2 }"),
    # P3 memory_in の供給元が後ろのステージの memory_out だけ（carry 無し）
    "p3_memory_in_from_later_stage.yaml": sub1(
        SUB, "memory_in: [failing_checks] }", "memory_in: [failing_checks, claims] }"),
    # P4 subworkflow.pass の鍵が親の memory_in に無い（既存負例は each のみ）
    "p4_pass_not_in_memory_in.yaml": sub1(
        sub1(SUB, "ref: ../../../../schema/examples/children/leaf.yaml", "ref: children/leaf_pass.yaml"),
        "item_as: claim\n", "item_as: claim\n            pass: [extra_key]\n"),
    # P5 max が整数でない
    "p5_max_not_integer.yaml": sub1(MIN, "max: 2 }", "max: 1.5 }"),
    # P6 フェーズ id の重複（unique_ids はステージと end_state だけか）
    "p6_duplicate_phase_id.yaml": sub1(MIN, "- id: verify\n      name: Verify\n      description: 下書きを検証する",
                                      "- id: prepare\n      name: Verify\n      description: 下書きを検証する"),
    # P7 集約規則の state が別の子ステージのもの（(stage, state) の組の整合）
    "p7_aggregate_state_of_other_child_stage.yaml": sub1(
        SUB, "when: { any: { stage: check, state: inconsistent } }",
        "when: { any: { stage: write, state: inconsistent } }"),
    # P8 子の rollback が親のステージを指す（文書を跨ぐ参照）
    "p8_child_rollback_crosses_document.yaml": sub1(
        SUB, "ref: ../../../../schema/examples/children/leaf.yaml", "ref: children/leaf_crossref.yaml"),
    # P10 rollback の carry が戻り先の memory_in にはあるが、元ステージでは memory_in にしか無い（素通し）
    "p10_carry_only_in_source_memory_in.yaml": sub1(
        sub1(SUB, "memory_in: [section_findings]\n            memory_out: [failing_checks, missing_inputs, claims]",
             "memory_in: [section_findings]\n            memory_out: [missing_inputs, claims]"),
        "memory_in: [failing_checks] }", "memory_in: [failing_checks] }"),
}
children = {
    "leaf_pass.yaml": sub1(LEAF, "inputs: [claim]", "inputs: [claim, extra_key]"),
    "leaf_crossref.yaml": sub1(LEAF, "{ state: inconsistent, stage: write, carry: [inconsistencies], max: 1 }",
                               "{ state: inconsistent, stage: verify, carry: [inconsistencies], max: 1 }"),
}
for name, text in probes.items():
    (OUT / name).write_text(text, encoding="utf-8")
for name, text in children.items():
    (OUT / "children" / name).write_text(text, encoding="utf-8")
# P9 子の指標が無いマニフェスト（toy-minimal の workflow.yaml に対して使う）
(OUT / "p9_manifest_without_child_metric.json").write_text(
    '{"metrics": ["inputs_complete", "draft_exists", "claim_count", "report_exists", "verified_ratio", "sections_count", "section_exists"]}\n',
    encoding="utf-8")
print("wrote", len(probes), "probes,", len(children), "children, 1 manifest")
