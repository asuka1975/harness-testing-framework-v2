# 探針（probe）の実行ログ（2026-10-22T00:58:34+09:00）

各 probe は schema/examples/positive の正例を一箇所だけ変えたもの（生成: probes/make_probes.py）。
コマンド（リポジトリのルートで）: `uv run python -m htf.testing.spec reports/verification/f1-contract-and-spec/<probe> --metrics schema/examples/metrics.json`
diff は元にした正例との差分（with_subworkflow 系は ref の相対パスの書き換え行を除く）。

## probes/p1_phase_metric_unregistered.yaml（元: positive/minimal.yaml）
```
<           draft_exists: { description: draft.md がある, equals: true }
---
>           no_such_phase_metric: { description: 未登録の指標, equals: true }
--- checker ---
reports/verification/f1-contract-and-spec/probes/p1_phase_metric_unregistered.yaml:/workflow/phases/0/goal/quantitative/no_such_phase_metric [metric_registered] 指標 'no_such_phase_metric' がレジストリに無い
1 finding(s)
EXIT=1
```

## probes/p2_rollback_to_later_stage.yaml（元: positive/with_subworkflow.yaml）
```
<             - { state: checks_failed, stage: draft, carry: [failing_checks], max: 2 }
---
>             - { state: checks_failed, stage: elaborate, carry: [failing_checks], max: 2 }
---
--- checker ---
reports/verification/f1-contract-and-spec/probes/p2_rollback_to_later_stage.yaml:/workflow/phases/0/stages/1/artifacts/memory_in [memory_in_source] memory_in 'failing_checks' を供給するものが無い（前方の memory_out、このステージへの carry、workflow.inputs のいずれにも無い）
reports/verification/f1-contract-and-spec/probes/p2_rollback_to_later_stage.yaml:/workflow/phases/1/stages/0/rollback/0/stage [rollback_forward] 戻り先 'elaborate' は 'verify' より前でなければならない
reports/verification/f1-contract-and-spec/probes/p2_rollback_to_later_stage.yaml:/workflow/phases/1/stages/0/rollback/0/carry [carry_declared] carry 'failing_checks' が戻り先 'elaborate' の memory_in に無い
3 finding(s)
EXIT=1
```

## probes/p3_memory_in_from_later_stage.yaml（元: positive/with_subworkflow.yaml）
```
<           artifacts: { reads: [inputs.json], writes: [draft.md], memory_in: [failing_checks] }
---
>           artifacts: { reads: [inputs.json], writes: [draft.md], memory_in: [failing_checks, claims] }
---
--- checker ---
reports/verification/f1-contract-and-spec/probes/p3_memory_in_from_later_stage.yaml:/workflow/phases/0/stages/1/artifacts/memory_in [memory_in_source] memory_in 'claims' を供給するものが無い（前方の memory_out、このステージへの carry、workflow.inputs のいずれにも無い）
1 finding(s)
EXIT=1
```

## probes/p4_pass_not_in_memory_in.yaml（元: positive/with_subworkflow.yaml）
```
---
77a78
>             pass: [extra_key]
--- checker ---
reports/verification/f1-contract-and-spec/probes/p4_pass_not_in_memory_in.yaml:/workflow/phases/1/stages/1/subworkflow/pass [subworkflow_inputs] pass 'extra_key' が memory_in に無い
1 finding(s)
EXIT=1
```

## probes/p5_max_not_integer.yaml（元: positive/minimal.yaml）
```
<             - { state: checks_failed, stage: draft, carry: [failing_checks], max: 2 }
---
>             - { state: checks_failed, stage: draft, carry: [failing_checks], max: 1.5 }
--- checker ---
reports/verification/f1-contract-and-spec/probes/p5_max_not_integer.yaml:/workflow/phases/1/stages/0/rollback/0/max [rollback_max] 1.5 is not of type 'integer'
1 finding(s)
EXIT=1
```

## probes/p6_duplicate_phase_id.yaml（元: positive/minimal.yaml）
```
<     - id: verify
---
>     - id: prepare
--- checker ---
reports/verification/f1-contract-and-spec/probes/p6_duplicate_phase_id.yaml:/workflow/phases [unique_ids] フェーズ id 'prepare' が 2 回現れる
1 finding(s)
EXIT=1
```

## probes/p7_aggregate_state_of_other_child_stage.yaml（元: positive/with_subworkflow.yaml）
```
---
<                 when: { any: { stage: check, state: inconsistent } }
---
>                 when: { any: { stage: write, state: inconsistent } }
--- checker ---
reports/verification/f1-contract-and-spec/probes/p7_aggregate_state_of_other_child_stage.yaml:/workflow/phases/1/stages/1/subworkflow/aggregate/0/when/any/state [subworkflow_aggregate] 子のステージ 'write' に end_state 'inconsistent' が無い
1 finding(s)
EXIT=1
```

## probes/p8_child_rollback_crosses_document.yaml（元: positive/with_subworkflow.yaml）
```
---
--- checker ---
/home/asuka1975/work/ai-agent/harness-testing-framework-v2/reports/verification/f1-contract-and-spec/probes/children/leaf_crossref.yaml:/workflow/phases/0/stages/0/artifacts/memory_in [memory_in_source] memory_in 'inconsistencies' を供給するものが無い（前方の memory_out、このステージへの carry、workflow.inputs のいずれにも無い）
/home/asuka1975/work/ai-agent/harness-testing-framework-v2/reports/verification/f1-contract-and-spec/probes/children/leaf_crossref.yaml:/workflow/phases/0/stages/1/rollback/0/stage [ref_integrity] ステージ 'verify' が同一文書に無い
reports/verification/f1-contract-and-spec/probes/p8_child_rollback_crosses_document.yaml:/workflow/phases/1/stages/1/subworkflow/ref [subworkflow_ref] 子定義 'children/leaf_crossref.yaml' が検査を通らない
3 finding(s)
EXIT=1
```

## probes/p10_carry_only_in_source_memory_in.yaml（元: positive/with_subworkflow.yaml）
```
<             memory_out: [failing_checks, missing_inputs, claims]
---
>             memory_out: [missing_inputs, claims]
---
--- checker ---
reports/verification/f1-contract-and-spec/probes/p10_carry_only_in_source_memory_in.yaml:/workflow/phases/1/stages/0/rollback/0/carry [carry_declared] carry 'failing_checks' が元ステージ 'verify' の memory_out に無い
1 finding(s)
EXIT=1
```

## P9: examples/toy-minimal/workflow.yaml を probes/p9_manifest_without_child_metric.json（section_consistent を抜いたマニフェスト）で検査
```
/home/asuka1975/work/ai-agent/harness-testing-framework-v2/examples/toy-minimal/elaborate-claim.yaml:/workflow/phases/0/goal/quantitative/section_consistent [metric_registered] 指標 'section_consistent' がレジストリに無い
/home/asuka1975/work/ai-agent/harness-testing-framework-v2/examples/toy-minimal/elaborate-claim.yaml:/workflow/phases/0/stages/1/goal/quantitative/section_consistent [metric_registered] 指標 'section_consistent' がレジストリに無い
examples/toy-minimal/workflow.yaml:/workflow/phases/1/stages/1/subworkflow/ref [subworkflow_ref] 子定義 'elaborate-claim.yaml' が検査を通らない
3 finding(s)
EXIT=1
```

## 子探針（probes/children/）と children/leaf.yaml の差分
```
-- probes/children/leaf_crossref.yaml
<             - { state: inconsistent, stage: write, carry: [inconsistencies], max: 1 }
>             - { state: inconsistent, stage: verify, carry: [inconsistencies], max: 1 }
-- probes/children/leaf_pass.yaml
<   inputs: [claim]
>   inputs: [claim, extra_key]
```
