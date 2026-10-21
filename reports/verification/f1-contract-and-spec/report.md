# F1「契約と仕様」検証報告（検証役、動的ワークフロー `f1-contract-and-spec`）

- 検証日: 2026-10-22
- 検証役: 実装を見ていない general-purpose サブエージェント（docs/progress.md 末尾の宣言に従う）
- 対象コミット: `ea27337 F1 本体: 拡張スキーマ、正例・負例、整合性検査器、ハーネス契約、toy-minimal`
- 根拠はすべて本報告に記した実行コマンドと出力の要旨。付属ログ: `probe-log.md`（探針）、`schema-validation-log.txt`（スキーマ単体の検証）、`probes/`（探針ファイルと生成スクリプト）

## 総合判定: **一部判定不能**

- 計画書第6節 F1 の完了条件のうち機械的に検査できる項目（1 メタスキーマ適合、2 正例が通り負例が落ちる、3 各性質に負例がある、4 toy-minimal が検査を通る、5 契約が文書化されている）は**すべて満たす**。自作の探針 10 件も全件検査器が落とし、負例が「通ってしまう」隙は見つからなかった
- 項目 6「完了条件を実装より先に書いた」は、テストが完了条件を直接表している（構造）ことは**満たす**が、実装より先に書かれたこと（時系列）は証拠不足で**判定不能**（単一コミット、progress.md に F1 本体の実行記録が無い）
- 完了条件末尾の「人間が承認」は未（ADR-011 の決定欄が未記入）。検証役の判定対象外
- toy-minimal の MECE 事前レビューで見つけた問題: ワークフロー定義の問題 4 件、分類体系の変更の提案 4 件、フレームワーク本体の不足 4 件（第 2.4 節）

---

## 1. F1 完了条件の判定

### 1.1 スキーマが Draft 2020-12 メタスキーマに適合する — **満たす**

```text
$ uv run python -c "import json, jsonschema; s=json.load(open('schema/workflow.schema.json')); \
    jsonschema.Draft202012Validator.check_schema(s); print(s['$schema'])"
https://json-schema.org/draft/2020-12/schema
metaschema check: OK（check_schema は例外を投げない。jsonschema 4.26.0）
$ uv run pytest -q -k test_schema_conforms_to_metaschema   → 1 passed
```

### 1.2 正例が通り、負例が落ちる — **満たす**

- 正例 2 件（`schema/examples/positive/minimal.yaml`, `with_subworkflow.yaml`）: スキーマ単体で誤り 0、検査器 CLI も `0 finding(s)`、終了コード 0
- 負例 25 件（`schema/examples/negative/*.yaml`）: 検査器 CLI は全件 終了コード 1 で、ファイル名の `<code>__` が報告に現れる（1.3 の表）
- スキーマ単体では、`schema__*` 2 件と `rollback_max__*` 2 件の計 4 件だけが落ち、残り 21 件はスキーマを通る。つまり 21 件は検査器が捕まえている（`schema-validation-log.txt`）。これは ADR-011 11.15（`rollback.max` のスキーマ違反だけ `rollback_max` に対応づける）と整合する

```text
$ uv run python -m htf.testing.spec schema/examples/positive/minimal.yaml --metrics schema/examples/metrics.json
0 finding(s)   EXIT=0          （with_subworkflow.yaml も同じ）
$ for f in schema/examples/negative/*.yaml; do uv run python -m htf.testing.spec $f --metrics schema/examples/metrics.json; done
  → 25 件すべて EXIT=1（各件の報告行は 1.3 の表）
$ uv run pytest -q   → 63 passed（test_positive_validates ×2、test_schema_negative_is_rejected ×2、
                        test_positive_has_no_findings ×2、test_negative_reports_expected_code ×25 を含む）
```

### 1.3 検査器の各性質に負例がある — **満たす**

検査器のコードカタログは 14 件（`htf.testing.spec.CODES`）。計画書が列挙する 7 性質、ADR-009 (b) と ADR-011 で足された性質のすべてに負例があり、各 code は CLI の報告に実際に現れた。`test_every_code_has_a_negative_and_vice_versa` も通る（カタログと負例集合の一致）。

| 性質（出典） | code | 負例ファイル（`<code>__<name>.yaml`） | CLI の報告行の要旨（`[code]` が現れたもの） |
| --- | --- | --- | --- |
| 参照整合（計画書） | `ref_integrity` | `rollback_stage_missing`, `rollback_state_missing` | `[ref_integrity] ステージ 'nowhere' が同一文書に無い` / `end_state 'no_such_state' が無い` |
| unknown を除く end_state と rollback の全単射（計画書） | `end_state_rollback_bijection` | `missing_rollback`, `duplicate_rollback`, `unknown_has_rollback` | `end_state 'inputs_missing' に rollback が無い` / `… rollback が 2 件ある` / `unknown に rollback を付けてはいけない` |
| 戻り先の前方性（計画書） | `rollback_forward` | `self` | `戻り先 'verify' は 'verify' より前でなければならない` |
| max の存在と有界性（計画書） | `rollback_max` | `missing`, `zero` | `'max' is a required property` / `0 is less than the minimum of 1` |
| carry の生成と消費（計画書） | `carry_declared` | `not_in_memory_out`, `not_in_memory_in` | `carry 'failing_checks' が元ステージ 'verify' の memory_out に無い` / `… 戻り先 'draft' の memory_in に無い` |
| 指標の存在（計画書、ADR-002） | `metric_registered` | `unregistered` | `指標 'no_such_metric' がレジストリに無い` |
| unknown の存在（計画書） | `unknown_present` | `missing` | `id が unknown の end_state が無い` |
| memory_in の供給元（ADR-011 11.1/11.2） | `memory_in_source` | `unsourced` | `memory_in 'review_notes' を供給するものが無い（前方の memory_out、carry、workflow.inputs のいずれにも無い）` |
| 子定義の存在・適合・循環（ADR-009 (b)） | `subworkflow_ref` | `missing_file`, `cycle` | `子定義 '../children/does-not-exist.yaml' が無い` / `循環参照: '../negative/subworkflow_ref__cycle.yaml'` |
| 子の深さ 1（ADR-011 11.10） | `subworkflow_depth` | `nested` | `子ワークフローは更に子を持てない（深さ 1 まで）` |
| 親子の inputs / each / workspace（ADR-009 (b)、ADR-011 11.3/11.6） | `subworkflow_inputs` | `child_inputs_mismatch`, `each_not_in_memory_in`, `workspace_outside_writes` | `親が供給する鍵 ['task'] と子の inputs ['claim'] が一致しない` / `each 'findings' が memory_in に無い` / `workspace 'elsewhere/' が writes のディレクトリ項目の配下に無い` |
| 集約規則の参照整合（ADR-009 (b)） | `subworkflow_aggregate` | `child_state_missing`, `parent_state_unknown` | `子のステージ 'check' に end_state 'nope' が無い` / `'unknown' は親の unknown 以外の end_state ではない` |
| id の一意性（検査器の追加） | `unique_ids` | `duplicate_stage`, `duplicate_end_state` | `ステージ id 'collect' が 2 回現れる` / `end_state id 'checks_failed' が 2 回現れる` |
| スキーマ違反（検査器の追加） | `schema` | `additional_property`, `metric_equals_and_min` | `Additional properties are not allowed ('extra' was unexpected)` / `… is not valid under any of the given schemas` |

所見（判定には影響しない）:

- 負例の一部は単一欠陥でない。例: `end_state_rollback_bijection__missing_rollback` は `memory_in_source` も同時に報告する（rollback を消すと carry の供給元も消えるため）。`subworkflow_depth__nested` と `subworkflow_ref__cycle` は 3〜4 件の所見を出す。期待 code は含まれているので完了条件は満たすが、負例ごとに「期待 code だけが出る」ことまでは保証していない
- `rollback_forward` の負例は自己参照だけ。真に後ろのステージを指す負例は無い（探針 P2 で検査器が落とすことは確認した。下記）

#### 探針（負例が「通ってしまう」隙の自作検査）

正例を一箇所だけ変えた探針 10 件を `probes/` に置き（`schema/examples` には置いていない）、検査器 CLI にかけた。**全件が終了コード 1 で、狙った code を報告した。隙は見つからなかった。** 詳細は `probe-log.md`。

| 探針 | 変更（正例との差分） | 狙い | 報告された code |
| --- | --- | --- | --- |
| P1 | フェーズ `prepare` の goal.quantitative を未登録の `no_such_phase_metric` に | ADR-005「phase.goal.quantitative の指標名の存在を検査」 | `metric_registered`（`/workflow/phases/0/goal/quantitative/…`） |
| P2 | `verify.checks_failed` の戻り先を後ろの `elaborate` に | 自己参照でない前方違反 | `rollback_forward`（他に `memory_in_source`, `carry_declared`） |
| P3 | `draft.memory_in` に後ろのステージの memory_out `claims` を追加（carry 無し） | memory が前方にしか流れないこと | `memory_in_source` |
| P4 | `subworkflow.pass: [extra_key]`（親 memory_in に無い。子 inputs は合わせた） | 既存負例は each のみ | `subworkflow_inputs`（`pass 'extra_key' が memory_in に無い`） |
| P5 | `max: 1.5` | max が整数であること | `rollback_max`（`1.5 is not of type 'integer'`） |
| P6 | フェーズ id を重複させる | unique_ids がフェーズにも及ぶか | `unique_ids`（`フェーズ id 'prepare' が 2 回現れる`） |
| P7 | 集約規則の state を別の子ステージの end_state に（`stage: write, state: inconsistent`） | (stage, state) の組での参照整合 | `subworkflow_aggregate` |
| P8 | 子の rollback が親のステージ `verify` を指す | 文書を跨ぐ参照の禁止 | 子側で `ref_integrity`、親側で `subworkflow_ref` |
| P9 | toy-minimal を、子の指標 `section_consistent` を抜いたマニフェストで検査 | 子ファイルの指標もレジストリで検査されるか | 子ファイルで `metric_registered` ×2、親で `subworkflow_ref` |
| P10 | carry の鍵を元ステージの memory_out から外す（with_subworkflow 版） | carry ⊆ memory_out | `carry_declared` |

### 1.4 toy-minimal が検査を通る（子を含む） — **満たす**

```text
$ uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics examples/toy-minimal/metrics/manifest.json
0 finding(s)   EXIT=0
$ uv run python -m htf.testing.spec examples/toy-minimal/elaborate-claim.yaml --metrics examples/toy-minimal/metrics/manifest.json
0 finding(s)   EXIT=0          （子を単体で検査しても通る。inputs: [claim] が memory_in の供給元になる）
$ uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml      （レジストリ無し）
skipped: metric_registered（レジストリが渡されていない）  0 finding(s)  EXIT=0
$ uv run pytest -q -k test_toy_minimal   → 3 passed
```

子が実際に再帰検査されていることは探針 P9 で確認した（マニフェストから `section_consistent` を抜くと `elaborate-claim.yaml` 側に所見が出る）。

F1 が要求する形（YAML を読んで確認。`test_toy_minimal_has_required_shapes` も同じことを検査している）:

| 要求 | toy-minimal での所在 |
| --- | --- |
| 3〜4 ステージ | 親は 2 フェーズ 4 ステージ（collect, draft, verify, elaborate）。子 elaborate-claim.yaml に 2 ステージ（write_section, check_section）。テストは親だけを 3〜4 で数えている（3 節に注記） |
| ロールバック（フェーズ内） | elaborate → verify（carry: section_findings, max 1） |
| フェーズ境界越え | verify → draft（max 2）、verify → collect（max 1）、draft → collect（max 1） |
| carry | 4 辺すべてに carry。memory_out / memory_in の宣言は検査器が通している |
| ユーザー待ち | collect に `user_input: true`（ADR-004 (b)、ADR-011 11.4） |
| max 超過で escalate | verify → draft の max 2 |
| 子ワークフロー呼び出し（ADR-009 (b)） | elaborate の `subworkflow`（ref: elaborate-claim.yaml, each: claims, item_as: claim, workspace: sections/, aggregate 1 規則） |
| unknown | 親子の全 6 ステージに `unknown` がある |

### 1.5 契約が文書化されている — **満たす**（軽微な食い違い 3 点を 2.4 節 F2〜F4 に記す）

CONTRACT.md を types.py / interfaces.py と突き合わせた結果:

| 計画書が要求する内容 | CONTRACT.md | types.py / interfaces.py | 一致 |
| --- | --- | --- | --- |
| 三操作 run / evaluate / restore + overlay | 第 2 節の表 | `Runtime` Protocol: `run`, `evaluate`, `restore`, `overlay` | 一致 |
| スナップショット形式 | 第 3 節（meta.json / memory.json / files/） | `Snapshot(workflow, version, stage_id, moment, ordinal, files, memory)` | ほぼ一致。meta.json の `taken_at` に対応する属性が `Snapshot` に無い（F2） |
| ステージ本体のインターフェース | 第 5.1 節 | `StageBody.run(ctx)`, `StageContext`（stage_id, workspace, memory, emit, user, llm） | 一致 |
| 指標のインターフェース | 第 5.2 節 | `Metric.__call__(snapshot)`, `MetricRegistry.names()/resolve()`（runtime_checkable） | 一致 |
| ユーザー入出力 | 第 5.3 節 | `UserIO.ask(question, schema=None)`, `WaitingForUser(question, schema)` | 一致 |
| LLM クライアント / 分類器 | 第 5.4 節 | `LLMClient.complete`, `Classifier.classify(document, options)`, `ClassOption`, `Classification` | 一致 |
| 評価順序（第2節: goal 指標 → goal 定性 → end_state → unknown） | 第 4 節 1〜4 が同じ順序。加えて ADR-002（評価不能 → unknown）、ADR-005（フェーズゲート、不成立 → unknown）、ADR-009（親は集約規則）の追加規則がある | `Runtime.evaluate` の docstring に同じ順序 | 一致。ただし `DecidedBy` の注記が第 4 節と食い違う（F3） |
| 遷移の種類 | 第 6 節の 7 種 | `TransitionKind` 7 値 | 一致（`test_seven_transition_kinds`） |
| escalate の 4 つの選択肢（ADR-003） | 第 5.5 節 | `Rerun`, `RollbackTo(stage, carry)`, `ContinueAsGoal(note 必須)`, `Abort`、`Escalation.cause` | 一致 |
| 子ワークフローの扱い（ADR-009 (b)） | 第 7 節（起動、子の escalate の伝播、集約、深さ 1） | `ChildOutcome(goal / stuck / unknown)`, `Escalation.cause = child_unresolved` | 一致 |

```text
$ uv run pytest -q -k test_contract   → 5 passed（__all__ の解決、7 遷移、3 層と 4 解決、MetricRegistry の構造的判定、WaitingForUser）
```

「人間が承認」は未（ADR-011「決定」欄が未記入）。これは人間ゲートであり検証役の判定対象外。

### 1.6 テストが「完了条件を実装より先に書いた」形になっているか — **構造: 満たす / 時系列: 判定不能**

構造（tests/ が完了条件を直接表しているか）: 満たす。

- `tests/test_schema_examples.py`: 正例がスキーマを通る、`schema__*` 負例が落ちる
- `tests/test_checker.py`: 正例に所見が無い、各負例がファイル名の code を報告する、**`CODES` と負例集合の一致**（code を足して負例を忘れると落ちる）、レジストリ無しで `metric_registered` をスキップと明示する、CLI の終了コード 0/1/2
- `tests/test_toy_minimal.py`: 検査を通る（子を含む）、要求の形（3〜4 ステージ、フェーズ内/境界越えロールバック、carry、ユーザー待ち、子ワークフロー）、親の供給鍵と子の inputs の一致
- `tests/test_repo_layout.py`: メタスキーマ適合、付録 A の構造保存、ADR の固定節、progress.md の固定形式
- `tests/test_contract.py`: 契約の形（7 遷移、4 解決、3 層）

時系列（実装より先に書いたか）: 判定不能。

- git 履歴: テストと実装が同一コミット `ea27337` に入っており、順序を復元できない
- `docs/progress.md`: F1 本体についての「完了したこと」「実行した検証とその結果の要旨」の節が無い（同コミットの progress.md の差分は「次にやること」のタスク列と動的ワークフローの宣言だけ）。「次にやること 1」に書かれた「実装前は失敗する」ことの確認（`uv run pytest --collect-only`）の結果は記録されていない
- ファイルの更新時刻（最終書き込み時刻なので弱い証拠）: `test_schema_examples.py` 00:36:57、`test_checker.py` 00:37:12 は `workflow.schema.json` 00:39:51、`checker.py` 00:45:04 より前。一方 `test_toy_minimal.py` 00:45:04 は `checker.py` と同時刻、`test_contract.py` 00:48:43 は `types.py` 00:48:05 より後。どちらとも言えない

---

## 2. toy-minimal の MECE 事前レビュー（人間レビューの予行）

観点: (a) goal / end_state / unknown のクラス集合が互いに排他か、重なりうる場合に「〜に優先する」があるか、(b) end_state の記述が成果物（reads / writes / memory）から観測できる条件か（goal の言い換え・実行の途中状態でないか）、(c) unknown 以外の各 end_state に戻り先があり、carry が元の memory_out と戻り先の memory_in にあるか、(d) 集約規則が子の終わり方を過不足なく写しているか。

### 2.1 親 workflow.yaml

#### collect（prepare フェーズ、user_input: true）

- クラス集合: {goal, unknown}。end_state は unknown のみで排他は自明。優先順の記述は不要
- 観測可能性: goal は inputs.json の必須項目（題目、主張の一覧、根拠の所在）が埋まっていること。writes: [inputs.json] から観測できる。quantitative `inputs_complete` と同じ内容
- 戻り先: 無し（最初のステージ。失敗はすべて unknown → 人間）。設計として妥当
- carry: memory_in [missing_inputs] は draft と verify からの carry で供給される（検査器が通している）。初回はこの鍵が無いことになるが、記述上の問題は無い
- 所見: 無し

#### draft（prepare フェーズ）

- クラス集合: {goal, inputs_insufficient, unknown}。goal「全ての主張に節があり、各節が根拠の所在を参照」と inputs_insufficient「一部の主張に根拠の所在が無く、その節が空」は排他。優先順の記述は不要（unknown 以外のクラスが 1 つ）
- 観測可能性: inputs_insufficient は「draft.md のその節が空のまま」「足りない項目の一覧が draft.md の末尾」で、writes: [draft.md] と reads: [inputs.json] から観測できる。goal の言い換えではない
- 戻り先: inputs_insufficient → collect（carry: missing_inputs, max 1）。missing_inputs は draft の memory_out にあり、collect の memory_in にある
- 所見 **W1**（記述の曖昧さ）: 「inputs.json の主張の一部に根拠の所在が無く」は、collect の goal「根拠の所在がすべて埋まった形で書かれている」と読み合わせると、collect が goal で抜けた直後には起きない状態になる。意図が「所在欄が空」なのか「所在は書いてあるが指す先に根拠が無い」なのかが記述から決まらない。後者なら「根拠の所在が指す先に根拠が無く」のように書く（意味を確定させる変更なので、人間が後者と決めるなら T 側に移る）
- 所見（注記）: memory_in [failing_checks]（verify からの carry）を draft がどう使うかは goal / end_state に現れない。再進入時の期待結果が初回と同じでよいなら問題ない

#### verify（verify フェーズ）

- クラス集合: {goal, checks_failed, inputs_missing, unknown}。checks_failed と inputs_missing は同時に成り立ちうるが、checks_failed に「この状態は inputs_missing に優先する」がある（ADR-007 の定型句に沿う）。優先順の記述は完備
- 観測可能性: checks_failed は「失敗した検査の一覧が report.json にある」で writes から観測できる。inputs_missing は「入力が draft.md にも作業ディレクトリにも無い」で、reads: [draft.md] と作業ディレクトリから観測できるが、**何が無いのかを記録する成果物が示されていない**（W2）
- 戻り先: checks_failed → draft（carry: failing_checks, max 2）、inputs_missing → collect（carry: missing_inputs, max 1）。両方の carry は verify の memory_out にあり、戻り先の memory_in にある。memory_in [section_findings] は elaborate からの carry で供給される
- 所見 **W2**（観測可能性）: inputs_missing の記述に、不足した入力の一覧がどの成果物にあるかが無い（memory_out の missing_inputs は carry であって成果物ではない）。「不足する入力の一覧が report.json にある」のように成果物上の条件を足す
- 所見 **W3**（goal の内部矛盾）: goal 定性「全ての主張が検証済みとして記録され、検証できないものは仮定として明示」は「全て検証済み」と「検証できないものがある」を同時に言っている。quantitative は verified_ratio ≥ 0.8。意図は「各主張が検証済みか仮定のどちらかで記録され、検証済みが 8 割以上」と読めるので、そう書く
- 所見 **T1**（クラスの隙間）: 入力はあり、検査の失敗も無いが、検証済みが 8 割未満（仮定が多い、主張が検証可能な形でない）という結果は、goal 指標で落ち、checks_failed にも inputs_missing にも当てはまらず、毎回 unknown（人間）になる。想定される頻度が高いなら「入力はあるが主張が検証可能な形でない（該当主張の一覧が report.json にある）→ draft へ」のようなクラスが要る。人間の判断
- 所見 **T2**（goal と end_state の境界）: goal の「検証できないものは仮定として明示」と inputs_missing の「入力が無く検証できていない」は、入力が無い主張を「仮定として明示」すれば goal、しなければ inputs_missing になりうる。境界は成果物でなくステージ本体の振る舞いで決まる。評価順序では goal が先に勝つが、記述上の境界（どの不足なら仮定扱いにしてよいか）を人間が決める必要がある

#### elaborate（verify フェーズ、subworkflow）

- クラス集合: {goal, sections_inconsistent, unknown}。goal「全ての検証済み主張に section.md があり、各 section-check.json が矛盾なし」と sections_inconsistent「一つ以上の節が矛盾したまま」は排他。優先順の記述は不要
- 観測可能性: sections_inconsistent は「矛盾箇所の一覧が各節の section-check.json にある」で writes: [sections/] 配下から観測できる。ただし冒頭の「再試行の後も」は実行の履歴（子の max 超過）であって成果物の状態ではない（W4）。このステージは集約規則で決まり分類器は記述を読まない（CONTRACT 第 7 節 4）ので、実害は人間の読みやすさに留まる
- 戻り先: sections_inconsistent → verify（carry: section_findings, max 1）。section_findings は elaborate の memory_out にあり、verify の memory_in にある
- 所見 **W4**（記述の形）: 「再試行の後も主張と矛盾したままである」を「section-check.json が矛盾を記録している節が一つ以上ある」のように成果物の条件で書く
- 所見（注記）: 親の goal 定性は分類器に渡されない（CONTRACT 第 7 節 4: 子がすべて goal なら親も goal）。文書上の説明として残すなら YAML のコメントでそう示すと誤解が無い
- 集約規則の過不足は 2.3 節

### 2.2 子 elaborate-claim.yaml

#### write_section

- クラス集合: {goal, unknown}。排他は自明
- 観測可能性: goal「section.md が claim を展開し、claim に無い主張を含まない」は writes: [section.md] と memory_in [claim] から観測できる
- 戻り先: 無し（子の最初のステージ）。失敗は unknown → 子 run の結果として親の集約へ
- carry: memory_in [claim] は workflow.inputs、[inconsistencies] は check_section からの carry で供給される
- 所見: 無し

#### check_section

- クラス集合: {goal, inconsistent, unknown}。goal「全ての文が claim と整合し、section-check.json が矛盾なし」と inconsistent「一つ以上の文が claim と矛盾する。矛盾箇所の一覧が section-check.json にある」は排他。優先順の記述は不要
- 観測可能性: inconsistent は section-check.json の内容で観測できる。goal の言い換えではない
- 戻り先: inconsistent → write_section（carry: inconsistencies, max 1）。inconsistencies は check_section の memory_out にあり、write_section の memory_in にある
- 所見 **T4**（クラスの隙間）: section.md に「claim から導けないが claim と矛盾もしない文」がある場合、「整合」を「矛盾しない」と読めば goal、「claim から導ける」と読めば goal でも inconsistent でもなく unknown になる。write_section の goal が「claim に無い主張を含まない」と言っているので後者の読みが自然で、その場合この結果は毎回人間に行く。「整合」の意味を記述で確定するか、クラス（例: 「claim に無い主張を含む。該当文の一覧が section-check.json にある」→ write_section）を足すかは人間の判断

### 2.3 集約規則の過不足（elaborate ⇐ elaborate-claim）

子 run の終わり方を列挙する（CONTRACT 第 7 節 2 の ChildOutcome）:

| 子の終わり方 | 起きる条件 | 親の集約規則での扱い |
| --- | --- | --- |
| goal | 両ステージを GOAL で抜けた | 全子 run が goal なら親 goal |
| stuck (check_section, inconsistent) | inconsistent が max 1 を超えた（2 回目） | `any` 規則で sections_inconsistent → verify へ |
| unknown (write_section, unknown) | 子の分類で unknown | 規則に無い → 親 unknown → 人間 |
| unknown (check_section, unknown) | 同上 | 規則に無い → 親 unknown → 人間 |

- 写していない終わり方は子の unknown 2 つで、親の unknown（人間）に落ちる。CONTRACT 第 7 節 4 の「子の unknown を親の end_state に写すかはハーネス側の判断」どおりで、人間に届かせる設計意図として妥当
- 所見 **T3**（混在時の優先）: 子 run が複数あるとき、一つが stuck(inconsistent) で別の一つが unknown だと、`any` 規則が先に成立して sections_inconsistent → verify へ戻り、unknown だった子は人間に届かない。これを許容するか（verify 再実行で解消を期待する）、unknown を優先して人間に出すかは人間の判断。後者を選ぶ場合、現在のスキーマでは書けない（F1）

### 2.4 問題の分類

#### ワークフロー定義の問題（workflow.yaml / elaborate-claim.yaml を直せばよい。意味を変えない範囲）

| # | 場所 | 内容 | 直し方 |
| --- | --- | --- | --- |
| W1 | draft.inputs_insufficient | 「根拠の所在が無く」が collect の goal と読み合わせると曖昧 | 意図を確定して書く（「所在が指す先に根拠が無い」なら T 側として人間承認） |
| W2 | verify.inputs_missing | 不足した入力の一覧を記録する成果物が示されていない | 「不足する入力の一覧が report.json にある」を足す |
| W3 | verify.goal.qualitative | 「全て検証済み」と「検証できないものは仮定」が同時に書かれている | 「各主張が検証済みか仮定として記録され…」に直す |
| W4 | elaborate.sections_inconsistent | 「再試行の後も」は実行履歴 | 成果物の条件（section-check.json の記録）で書く |

#### 分類体系の変更の提案（end_state の追加・分割・意味変更。人間の承認が要る）

| # | 場所 | 内容 | 選択肢 |
| --- | --- | --- | --- |
| T1 | verify | 入力あり・失敗なし・検証済み 8 割未満が毎回 unknown | クラス追加（→ draft, carry）か、unknown のままと決める |
| T2 | verify | goal「仮定として明示」と inputs_missing の境界が記述で決まらない | どの不足を仮定扱いにしてよいかを記述に書く |
| T3 | elaborate の aggregate | stuck と unknown の混在で unknown が人間に届かない | 許容するか、unknown 優先にするか（後者は F1 が要る） |
| T4 | check_section | 「claim から導けないが矛盾しない文」が unknown に落ちる | 「整合」の意味の確定か、クラス追加 |

#### フレームワーク本体の不足（スキーマ・検査器・契約で表せない / 検査できないもの）

| # | 内容 | 影響 |
| --- | --- | --- |
| F1 | 集約規則で「子の unknown を親の unknown に優先して落とす」が書けない。`state: unknown` は負例（`subworkflow_aggregate__parent_state_unknown`）で禁止され、unknown は規則が一つも成立しない時の既定にしかならない | T3 で unknown 優先を選ぶ場合に、スキーマ（規則の対象に unknown を許す、または escalate の規則種）と CONTRACT 第 7 節 4 の変更が要る。F2 の runner に影響 |
| F2 | CONTRACT 第 3 節 meta.json の `taken_at` に対応する属性が `types.Snapshot` に無い | 文書と型の食い違い。保存形式だけの項目ならその旨を CONTRACT に書く |
| F3 | `types.DecidedBy` の注記「quantitative: goal 指標が不成立、または評価不能」が CONTRACT 第 4 節 1（不成立は 3 へ進み、quantitative は評価不能にだけ使う）と食い違う。また「goal 指標が不成立だが分類器が goal を選んだ」場合の Verdict（kind と decided_by）が第 4 節に書かれていない。`DecidedBy` の `human` も第 4 節に無い（第 5.5 節の含意のみ） | F2 の runner 実装で解釈が分かれる。契約の承認前に文言を揃える |
| F4 | 負例集合の薄い箇所: `rollback_forward` は自己参照のみ、`metric_registered` はステージ指標のみ、`subworkflow_inputs` は pass 無し、`unique_ids` はフェーズ id 無し。探針 P1 / P2 / P4 / P6 は検査器が落とすので検査器の不足ではないが、負例として残っていない | 探針を `schema/examples/negative/` に昇格させるか（保護ファイルなので計画エージェントの判断） |

---

## 3. 判定できなかった事項

1. **テストを実装より先に書いたこと（時系列）**: 単一コミットで順序を復元できず、progress.md に F1 本体の「完了したこと」「実行した検証とその結果の要旨」が無い（計画書第5.7節「実行したコマンドと出力の要旨を progress.md に残す」に対して記録が欠けている）。更新時刻は弱い証拠で両方向
2. **「人間が承認」**: ADR-011 の決定欄が未記入。人間ゲート
3. **「3〜4 ステージ」の数え方**: 親 4 + 子 2 = 6 を「3〜4」と見るかは解釈。テストは親だけを数える。計画書の文言は子ワークフロー（ADR-009 (b) で後から入った）を想定していないので、人間が確定する
4. **CI の雛形**: F1「作るもの」にあるが完了条件には無く、`.github/` は検証役の読取範囲に無いので見ていない
5. **`uv run ruff check .`**: progress.md のタスク 4 の完了条件に含まれるが、検証役に許可されたコマンドに無いので実行していない
6. **end_state 記述が分類器で人間と一致して分類できるか**: 実 LLM とコーパスが要る（ADR-006、F3 以降）。本レビューは記述の静的な読みに限る
7. **契約の意味（三操作の振る舞い）**: F2 の契約適合テストの対象。F1 では形（Protocol と文書）だけを見た

## 付録: 実行したコマンドの一覧

```text
uv run pytest -q                                                   → 63 passed
uv run pytest -q -vvv                                              → テスト名の一覧（1.2〜1.6 で引用）
uv run python -c "...Draft202012Validator.check_schema(...)"       → OK（jsonschema 4.26.0）
uv run python -c "...CODES, MAX_SUBWORKFLOW_DEPTH, UNKNOWN, htf.contract.__all__"
uv run python -m htf.testing.spec <positive|negative|children|toy-minimal|probe> --metrics <manifest>
uv run python -c "...Draft202012Validator(schema).iter_errors(...) for all examples"   → schema-validation-log.txt
uv run python reports/verification/f1-contract-and-spec/probes/make_probes.py         → probes/ の生成
git log --oneline / git show --stat ea27337 / git show ea27337 -- docs/progress.md
ls -la --time-style=full-iso tests/*.py src/htf/... schema/... examples/toy-minimal/...
```
