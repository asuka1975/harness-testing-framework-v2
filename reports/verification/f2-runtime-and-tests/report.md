# F2 検証報告: 参照ランタイムと決定論テスト（動的ワークフロー `f2-runtime-and-tests`）

- 検証役: 実装したエージェントとは別の general-purpose サブエージェント（2026-10-22）
- 対象コミット: 3e79996（テスト先行）→ 4fbb2df（実装）→ 39e84fb（adopting.md 初版、ADR-012）
- 書いたもの: このディレクトリのみ（`report.md`、`probes/`、`*.log`）。`git status --short` は `?? reports/verification/f2-runtime-and-tests/` だけ（`.coverage` は許可されたコマンドの副産物で、元から未追跡）
- 守ったこと: サブエージェント起動なし、外部 LLM 呼び出しなし、本体・テスト・toy-minimal・docs の変更なし

## 総合判定: **F2 完了条件を満たす**（6 項目すべて「満たす」。副問「契約適合スイートが CONTRACT.md 第 8 節を覆うか」は部分的で、問題 B5 として記録）

発見した問題: ワークフロー定義の yaml（workflow.yaml / elaborate-claim.yaml）0 件、toy-minimal の台本・偽本体 3 件、フレームワーク本体 10 件（うち重要 5 件: B1 中断再開を含む run は再生不能、B2 子の作業ディレクトリの残骸、B3 ゲート不成立で ContinueAsGoal が効かない、B5 適合スイートの範囲、B9 子内の遷移が観測できない）。いずれも計画書第 6 節 F2 の完了条件の文言そのものを落とすものではないが、B1 は「記録再生で同一スナップショット」が 7 種の遷移のうち suspend_resume を含む run に成り立たないことを意味するので、受け入れ時に人間が読むべき。

---

## 1. F2 完了条件の判定

| # | 完了条件 | 判定 | 根拠（要旨） |
| --- | --- | --- | --- |
| 1 | toy-minimal で 7 種の遷移を全て通す。台本の期待遷移列が実行と一致し、和集合が 7 種 | **満たす** | `uv run pytest -q` → 107 passed。`tests/test_runtime_transitions.py` の台本 8 本（happy、checks_failed_once、checks_failed_max、child_unknown、inputs_insufficient、sections_inconsistent、suspend_resume、verify_unknown）がすべて PASSED（`pytest_verbose.log`）。各台本の `expect.transitions` と実行の `result.trace` の一致はテストが assert し、`test_all_seven_transition_kinds_observed` が和集合 == `set(TransitionKind)`（7 種）を assert する。探針 P1 で台本を差し替えた時の遷移列も期待どおり（第 2 節） |
| 2 | escalate の 4 つの選択肢（Rerun / RollbackTo / ContinueAsGoal / Abort）が動く | **満たす** | `tests/test_runtime_escalation.py` 5 件 PASSED（Rerun は同じ開始時スナップショットから再実行、RollbackTo は辺の計数を消費せず carry を重ねる、未宣言 carry は ContractViolation、ContinueAsGoal は decided_by=human の GOAL で次へ、Abort は aborted）。探針 P4 で max 超過後の Rerun / RollbackTo も完走を確認。ただしフェーズゲート不成立の escalate では ContinueAsGoal が効かない（探針 P6、問題 B3） |
| 3a | 参照ランタイムが契約適合テストを通す | **満たす** | `tests/test_conformance_reference.py::TestReferenceRuntime` 15 件 PASSED（run 6、evaluate 6、restore/overlay 3） |
| 3b | スイートが CONTRACT.md 第 8 節の項目を覆っているか | **部分的（3 / 6 項目）** | 覆う: 「restore + overlay 後の作業ディレクトリと memory」「writes 外・未宣言 emit・未宣言 ctx.user の ContractViolation」「指標の例外 → UNKNOWN(quantitative)」。覆わない: 「7 種の遷移と 4 解決」「記録再生の同一性」「子 run の集約」。これらは参照ランタイム専用のテスト（`tests/test_runtime_*.py`）にあり、継承可能なスイートには無い。また第 8 節は「toy-minimal の定義と偽本体で」と書くがスイートは `conformance.yaml` を使う。スイートの docstring は制御ループを対象外と明記しており、意図的な範囲限定。計画書 F2 の完了条件は「通す」なので F2 の判定は変えず、契約文書との不整合を問題 B5 とする |
| 4 | 記録再生で同一スナップショットが得られる | **満たす**（条件つき） | `tests/test_runtime_recorder.py` 2 件 PASSED（happy の end スナップショット digest 列の一致、本体を変えた再生の ReplayMismatch）。探針 P3 でロールバックとゲート無効化を含む checks_failed_once でも end digest 6 件・trace・gates が一致。**ただし中断再開（suspend_resume）を含む run は記録も再生もできない**（P3-R3、問題 B1） |
| 5 | runtime の行カバレッジ 90% 以上 | **満たす** | `uv run pytest -q --cov=htf.runtime --cov-fail-under=90` → `Required test coverage of 90% reached. Total coverage: 93.14%`（`coverage.log`）。pyproject は `branch = true` なので 93.14% は行+分岐の合算。行だけなら (774−37)/774 = 95.2%。どちらの読みでも 90% 以上 |
| 6 | 完了条件のテストが実装より先に書かれている | **満たす** | `git show --stat 3e79996`: テストファイル 7 件（テストモジュール 6 + conftest.py）・台本 8 本・gate.yaml を追加し、progress.md に収集エラーの出力を残している（実装ファイルは含まない）。`git diff 3e79996 4fbb2df -- tests/ examples/toy-minimal/tests/` で確かめた変更は、(a) 台本の入力形式 `child_outcomes` → `child_runs`、(b) inputs_insufficient を台本駆動から成果物駆動（`empty_grounds_first`）へ、(c) workflow.yaml の `grounds/` を collect.writes / draft.reads に追加、(d) ruff の整形、(e) `test_replay_detects_mismatch` の不一致の作り方を「別の主張」から「別の outcome」へ。**8 本の台本の `expect`（遷移列・gates・status）とテストの assert は一切変わっていない**。(e) は、再生ではユーザー回答が記録から来るので主張を変えても要求が変わらないという実装後の気づきによる前提の修正で、assert の緩和ではない（ReplayMismatch を期待する点は同じ） |

補助: `uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics examples/toy-minimal/metrics/manifest.json` → `0 finding(s)` exit 0。`elaborate-claim.yaml` も `0 finding(s)`。

---

## 2. 自作の探針（8 件。スクリプトと出力は `probes/*.py` と `probes/*.log`）

すべて `uv run python reports/verification/f2-runtime-and-tests/probes/<name>.py` で実行。作業ディレクトリは `tempfile.mkdtemp()`。

### P1 台本を変えると遷移列が変わるか（`p1_script_variation.py`）

happy.yaml を起点に `Scenario.with_outcomes` で差し替えた。

| 変更 | 観測した遷移列 | 期待どおりか |
| --- | --- | --- |
| 基準（happy） | `[next, next, next, subworkflow_aggregate, next]`、gates `[prepare:passed, verify:passed]` | はい |
| verify = [checks_failed, goal] | `[next, next, rollback_across_phase, next, next, subworkflow_aggregate, next]`、gates `[prepare:passed, prepare:invalidated, prepare:passed, verify:passed]`、draft 2 回目の開始時 memory `{'failing_checks': ['主張A']}` | はい（境界越え + ゲート無効化 + carry） |
| verify = [checks_failed]（台本は最後を繰り返す） | `[…, rollback_across_phase, next, rollback_across_phase, next, escalate_max_exceeded]`、edge_counts `{(verify, checks_failed): 3}` | はい（max 2 → 3 回目で escalate） |
| draft = [unknown] | `[next, escalate_unknown]` → aborted | はい |
| verify = [inputs_missing, goal] | `[next, next, rollback_across_phase, next, next, next, subworkflow_aggregate, next]`、collect 2 回目の memory `{'missing_inputs': ['主張A の外部データ']}` | はい（collect への境界越え。この辺はどの台本にも無い） |
| verify = [inputs_missing, inputs_missing] | `[…, rollback_across_phase, next, next, escalate_max_exceeded]`、escalation.edge `('inputs_missing', 'collect')`、cause `max_exceeded` | はい（max 1） |
| 子 check_section = [inconsistent] | 親: `[…, subworkflow_aggregate, rollback_within_phase, next, subworkflow_aggregate, next]`、child_outcomes `[['stuck', 'goal'], ['goal', 'goal']]` | **期待と違った**。1 回だけ inconsistent のつもりが、台本が最後を繰り返すため 2 回目も inconsistent → max 1 超過で stuck（問題 W1） |

`p1b_child_internal_rollback.py`: 子 check_section = [inconsistent, goal] にすると親のトレースは happy と同一 `[next, next, next, subworkflow_aggregate, next]`、child_outcomes は `[(0, goal), (1, goal)]`。子 run 0 の section.md には carry の痕跡（「修正: …」）があるので子内のロールバックは起きているが、親の `RunResult` からは一切観測できない（問題 B9）。

### P2 契約違反が Runner 経由で ContractViolation になるか（`p2_contract_violation.py`、定義 `wf_violation.yaml`）

自作の 2 ステージ定義（seed → probe、probe は reads [a.txt]、writes [b.txt, out/]、memory_in [k]、user_input 無し）。

| 本体の振る舞い | 結果 |
| --- | --- |
| 宣言どおり | completed `[next, next]` |
| writes 外 `stray.txt` に書く | `ContractViolation: ステージ 'probe' が writes 外に書いた: ['stray.txt']` |
| 未宣言の鍵に emit | `ContractViolation: … memory_out に無い鍵 'not_declared' への emit` |
| user_input 無しで ctx.user | `ContractViolation: … user_input を宣言していないのでユーザー入出力を使えない` |
| reads の a.txt を書き換える | `ContractViolation: … writes 外に書いた: ['a.txt']` |
| writes 外の a.txt を削除 | `ContractViolation: … writes 外に書いた: ['a.txt']` |
| `.htf/note.txt` に書く | **検出されない**（completed）。ADR-012 12.2 どおり対象外だが、adopting.md は「本体が触ってはいけない」と書く（問題 B7） |
| ctx.memory の鍵 | `['k']` のみ（memory_in に限定されている） |
| writes 外に書く + `strict_writes=False` | completed（スイッチが効く） |

### P3 記録 → 再生（`p3_record_replay.py`）

| 項目 | 結果 |
| --- | --- |
| R1 checks_failed_once を record → replay（llm / classifier / user = None） | 記録の内訳 `{user: 3, classifier: 9, llm: 2}`。end digest 6 件一致、trace 一致、gates 一致 |
| R2 本体の台本を verify=[goal] に変えて replay | `ReplayMismatch: 記録 #6 と不一致: 期待 classifier {document: '# stage: verify …'}` |
| R3 suspend_resume を record（resume を 3 回） | **記録の内訳 `{classifier: 5, llm: 1}`。ユーザー回答の記録が 0 件**。`resume()` で与えた回答は `_QueuedUserIO` が先に返すので recorder を通らない。中断（WaitingForUser）の経路は記録に何も残らない |
| R3 その記録を resume 無しで replay | `ReplayMismatch: 記録 #0 と不一致: 期待 classifier …, 実際 user {'question': '題目は?'}`（WaitingForUser を再現できず、再生が最初の質問で壊れる） |
| R3 同じ resume 列を与えて replay | 同じ `ReplayMismatch`。**中断再開を含む run は再生できない**（問題 B1） |
| R4 happy の記録に余りの行を足して replay | completed。**未消費の記録は検出されない**（問題 B6） |
| R4 happy の記録の末尾 1 行を削って replay | `ReplayMismatch: 記録の終わりを越えた要求: classifier …`（欠落は検出される） |

### P4 辺の max と escalate までの回数（`p4_max_count.py`、定義のコピーは `probes/max_1/`、`probes/max_3/`）

workflow.yaml の `verify → draft (checks_failed)` の `max: 2` だけを 1 と 3 に書き換えたコピー（子定義も同じディレクトリに複製）。verify が常に checks_failed、人間は Abort。

| max | escalate_max_exceeded 前の rollback_across_phase の回数 | edge_counts |
| --- | --- | --- |
| 1 | 1 | 2 |
| 3 | 3 | 4 |

→ max 回のロールバックを許し、max+1 回目で escalate。宣言と一致。max=1 で超過後に人間が Rerun（verify 3 回目は goal）→ completed、edge_counts は 2 のまま。RollbackTo(draft, carry={failing_checks: [人間]}) → `rollback_across_phase`（note "human"）→ completed、edge_counts は 2 のまま（人間の操作は計数を消費しない）。

### P5 フェーズ境界を越えるロールバックの復元（`p5_cross_phase_restore.py`）

checks_failed_once の Draft 本体を包んで、進入のたびに作業ディレクトリの中身を記録した。

- draft 1 回目に見える成果物: `['grounds/0.txt', 'grounds/1.txt', 'inputs.json']`。2 回目: `[…, 'report.json']`、**draft.md は無い**（開始時スナップショットが復元された。report.json は verify の writes なので残る = 「範囲外に触れない」のとおり）
- draft の 2 つの開始時スナップショットの files だけの digest は一致。memory の差分は `{'failing_checks': ['主張A']}` のみ（carry だけが重なる）。1 回目の memory は `{}`
- store のレイアウト: `['files', 'memory.json', 'meta.json']`、meta.json の鍵 `['moment', 'ordinal', 'stage_id', 'taken_at', 'version', 'workflow', 'writes']`（CONTRACT 第 3 節の項目 + `writes`）
- store の ordinal は 15 で start+end の 12 より 3 多い（フェーズゲート評価用の仮スナップショット。RunResult からは見えない）
- 本体は `rglob` で `.htf/` 配下のファイル（1 回目 9、2 回目 25）も見える。読むことは禁じられていない

### P6 ゲート不成立での ContinueAsGoal、human 無しの最上位 Runner（`p6_gate_and_no_human.py`、`tests/fixtures/workflows/gate.yaml`）

- gate_ok=false のまま ContinueAsGoal ×2 → Abort: 遷移 `[escalate_unknown, escalate_unknown, escalate_unknown]`、gates `[first:failed ×3]`、escalations はすべて `(unknown, quantitative)`。**ContinueAsGoal はゲートを再評価して再び不成立になり、人間の「goal 扱いで続行」が効かない**（問題 B3）。台本が尽きるまで繰り返す
- gate_ok を 2 回目に true にして Rerun → `[escalate_unknown, next, next]`、gates `[first:failed, first:passed, second:passed]`（本体の出力が変わる場合は Rerun で抜けられる）
- toy の verify_unknown を `human=None` で実行: status **`escalated`**、trace `[next, next, escalate_unknown]`、`child_outcome=ChildOutcome(index=-1, kind='unknown', stage='verify', state='unknown')`。例外にならず、adopting.md 3.7 の status 一覧にも無い（問題 B4）

### P7 再進入で子の数が減った時の作業ディレクトリ（`p7_stale_child_dirs.py`、定義 `probes/shrink/`）

自作の親（seed → fan、fan は subworkflow each=items、workspace runs/、any(check, bad) → fan_bad → seed へ）と子（w → check、check: bad → w、max 1）。seed は 1 回目 items=[a, b]、2 回目 [a]。子 run 0 は bad×2 で stuck。

- 遷移 `[next, subworkflow_aggregate, rollback_within_phase, next, subworkflow_aggregate, next]`、child_outcomes 1 回目 `[(0, stuck, check, bad), (1, goal)]`、2 回目 `[(0, goal)]`
- **2 回目の fan の終了時スナップショットの runs/ 配下は `['0', '1']`**。items は `['a']` なのに `run_dirs` 指標（glob）は 2。前回の子 run 1 の作業ディレクトリが残り、親の成果物と指標に混入する（問題 B2）。toy-minimal の `Elaborate` 本体と `sections_count` 指標も glob なので同じ条件で誤る

---

## 3. adopting.md の十分性（利用者として読んで toy-minimal の harness.py と stages/ を作れるか）

結論: 契約の意味と束縛の API（3.3、3.7、3.8）は書かれており、`Bindings` と `Runner` の呼び方は文書どおりに動く。しかし「決定論的な偽ステージ本体と台本」をどう設計するかは文書に無く、toy-minimal を読んで真似るしかない。F4 の「adopting.md だけから作る」前提では、以下が不足。

### 説明できない点（文書に無い）

1. **ハイフン名のディレクトリの読み込み口**。`examples/toy-minimal/harness.py` は `from . import metrics` と相対 import で書かれ、`htf.testing.harness.load_example_package(root, "toy_minimal")`（tests/conftest.py）を経由しないと import できない。adopting.md はこの関数に触れていない
2. **台本（Scenario）の形式と偽本体の制御方式**。3.9 は「台本は本体コードに埋めずフィクスチャに置く」とだけ書く。`ScriptCursor`（ステージごとの n 回目の進入の結果、足りなければ最後を繰り返す）と `ChildScriptCursor`（子 run の境界を carry の有無で判定）は toy 固有の設計で、文書には設計指針が無い
3. **MarkerClassifier の印の規則**。3.6 は「成果物の outcome の印を読む」とだけ書く。実際は状態文書の `## writes` 節にある `"outcome": "x"`（JSON）か行 `outcome: x` を読み、`low_confidence` で閾値未満、選択肢に無い印は unknown。偽本体が成果物に印を書くという設計自体が説明されていない
4. **状態文書（投影）の形式**。`# stage:` / `## memory_in` / `## reads` / `## writes`、ディレクトリは配下の全ファイル、4000 文字で切る。自前の分類器や偽分類器を書くのに要る
5. **分類器の閾値**。`Runner(threshold=)` の既定 0.5（`DEFAULT_THRESHOLD`）はどこにも書かれていない（CONTRACT 第 9 節では未定）
6. **中断再開の書き方と永続化**。`SUSPENDED` の間 `resume(answer)` を繰り返すループは tests にしかなく、harness.py には無い。Runner オブジェクトが生きている間しか再開できない（永続化は CONTRACT 第 9 節で未定）ことも書かれていない
7. **Bindings.bodies の鍵の衝突**。親子で `workflow.name` が同じだと衝突する（ADR-012 12.1、検査器は未対応）注意が無い
8. **human を束縛しない時の振る舞い**（P6: `escalated` が返る）
9. **manifest.json とレジストリの関係**。toy は `sorted(manifest) == reg.names()` を assert するが、両方要るのか、どちらが正本かが書かれていない
10. **子を持つステージの本体の役割**。本体の束縛は任意だが、`memory_out`（toy の section_findings）を出すには本体が要ること、子の成果物を親がどう集めるか（glob）は実例にしかない

### 迷う点

11. 3.4「再進入は carry の鍵が ctx.memory にあるかで分かる」— 人間の Rerun や carry 無しの RollbackTo では初回と区別できない。toy の `ChildScriptCursor` はこの見分け方に依存しているので、Rerun で台本がずれる
12. 3.5「同じ質問には累積した回答が順に返る」— 実装は質問文を照合せず、ask の順序で返す。本体が毎回同じ順で質問する前提が明記されていない
13. 第 5 節「復元は戻り先の writes の範囲外に触れない（後段の成果物は残る）」— 再進入した本体は後段の成果物（P5 の report.json）を読めるし、`reads` は検査されない。前回の後段成果物に依存する本体を書いてしまっても検出されない旨の注意が要る

### 文書にあるのに実装と違う点

14. 3.7 `result.status  # completed | aborted | suspended` — `escalated` もある（最上位で human=None の時）
15. 3.7「再生時は llm / classifier / user を None にしてよい」— 中断再開を含む run では再生できない（P3-R3）
16. 3.8「自前のランタイムを持つなら、契約を満たすかはこのテストでのみ判定する」— スイートは三操作 + start だけで、CONTRACT 第 8 節の 7 種の遷移・4 解決・記録再生・集約は判定しない（B5）
17. 3.4 のコード例に `StageContext` / `LLMRequest` の import 元（`htf.contract`）が無い（軽微）

---

## 4. 発見した問題

### 4.1 ワークフロー定義・台本の問題（toy-minimal）

`workflow.yaml` と `elaborate-claim.yaml` 自体には所見が無い（検査器 0 finding(s)、7 種の遷移がすべて到達可能、辺の max と carry の宣言が実行と一致: P1 / P4 / P5）。以下の W1〜W3 は yaml ではなく toy 側の台本と偽ステージ本体（`stages/__init__.py`）の問題。

| # | 問題 | 根拠 | 提案 |
| --- | --- | --- | --- |
| W1 | `ScriptCursor` の「足りなければ最後を繰り返す」規則で、単発の end_state を書くつもりの台本（`[inconsistent]`）が max 超過（stuck）になる。checks_failed_max.yaml はこの規則に依存する一方、読み手は 1 回と誤読しうる | P1-F | 台本の規則をファイル冒頭か harness.py の docstring に書き、単発を書く時は `[x, goal]` と明記する。または尽きたら goal にする |
| W2 | `ChildScriptCursor` は「memory に inconsistencies が無い進入 = 新しい子 run」と判定する。Rerun や carry 無しの再進入でも新しい run と誤認し、台本が一つ先に進む | stages/__init__.py の `WriteSection.run`、adopting.md 3.4 の見分け方 | 子 run の境界は memory_in の `claim`（`workflow.inputs`）の変化か、親から渡す index で判定する |
| W3 | `Verify` 本体は `assumed` を常に空にする。verify の goal 定性「仮定とした主張にはその理由が記録されている」と `inputs_missing` と goal の境界（G3）の分岐を偽本体で踏めない | stages/__init__.py の `Verify.run`（`assumed = []` 固定） | F3 で (stage, end_state) の覆いを数える前に、台本に `assumed` を出す結果を足す |

### 4.2 フレームワーク本体の不足（契約・ランタイム・ランナー・文書）

| # | 重要度 | 問題 | 根拠 | 提案 |
| --- | --- | --- | --- | --- |
| B1 | 高 | **中断再開を含む run は記録も再生もできない**。`resume()` で与えた回答は `_QueuedUserIO` が先に返すので `RecordedUserIO` を通らず記録に残らない。再生では WaitingForUser（live が例外）を表せず、resume 列を同じに与えても最初の質問で `ReplayMismatch`。CONTRACT 5.3「recorder はユーザー回答も記録再生の対象にする」と adopting.md 3.7「再生時は user を None にしてよい」に反する。完了条件「記録再生で同一スナップショット」は suspend_resume には成り立たない | P3-R3 | 記録に `user` の回答（resume 由来も）と「中断した」事象を残し、再生では記録の回答を `answers` に積んでから開始する。または再生時の UserIO 照合を「質問 → 回答」の辞書にして順序に依存しない形にする |
| B2 | 高 | **子 run の作業ディレクトリの残骸**。`each` のリストが再進入で短くなっても前回の `<workspace><i>/` は消えず、親の終了時スナップショットと glob 指標に混入する。ADR-012 12.7「run 開始時に空にする」は子 run 単位で、親の `subworkflow.workspace` 全体は空にしない | P7（items 2 → 1 で runs/ に 0, 1 が残り指標が 2） | 親ステージの子 run 起動前に `subworkflow.workspace` 配下の `<i>/` のうち今回の要素数以上のものを消す（または配下全体を空にする）。契約第 7 節 1 に明記 |
| B3 | 高 | **フェーズゲート不成立の escalate に ContinueAsGoal を返しても抜けられない**。GOAL(human) で `_transition` に戻り、ゲートを再評価して再び不成立 → escalate を繰り返す。決定 #3 の 4 選択肢のうち 1 つが機能しない状況がある。ADR-012 12.10 の帰結で、記録されていない | P6（failed ×3、escalations ×3） | ゲート不成立由来の escalate（12.15 の `phase_gate_failed`）では ContinueAsGoal をゲート通過扱い（`GateEvent(passed, by=human)`）にする。F3 ゲートの ADR-012 の議題に足す |
| B4 | 中 | 最上位の Runner に `human=None` で unknown になると例外を出さずに `RunStatus.ESCALATED` と `child_outcome(index=-1)` を返す。子 run と最上位の区別が無い | P6 | 最上位で human 無しの escalate は `ContractViolation`（または専用の例外）にする。少なくとも adopting.md の status 一覧に書く |
| B5 | 高 | 契約適合スイートが CONTRACT 第 8 節の 6 項目中 3 項目しか覆わず、`conformance.yaml` を使う（第 8 節は toy-minimal と書く）。adopting.md 3.8「契約を満たすかはこのテストでのみ判定する」と合わせると、自前ランタイムは制御ループ（7 種、4 解決、再生、集約）の適合を判定されない | 第 1 節 3b | (a) 第 8 節を「スイートは三操作 + start。制御ループは `htf.testing.harness` と各ハーネスの決定論テストで」と改訂する（ADR-012 への追加）か、(b) スイートに `Runner` 相当のプロトコル（run_all / resume / 人間の解決）を加えて 7 種と 4 解決を覆う。12.14（start の追加）と一緒に決める |
| B6 | 低 | 再生終了時に未消費の記録があっても検出されない | P3-R4 | `Recorder.finish()` で残りがあれば `ReplayMismatch`、または Runner が run 終了時に確認する |
| B7 | 低 | `.htf/` への本体の書き込みは検出されない（12.2 で対象外と明記）。adopting.md は「本体が触ってはいけない」と書く。本体は rglob で store の中身も読める | P2 write_meta、P5 | 検出するか、文書を「検出しない。触った時の結果は未定義」に揃える |
| B8 | 低 | `DEFAULT_THRESHOLD = 0.5` が CONTRACT（第 9 節で未定）にも ADR-012 にも adopting.md にも無い暗黙の決定 | runner.py | ADR-012 に「仮置き 0.5。較正で決める」と記録し、adopting.md に `threshold` を書く |
| B9 | 高 | **子 run の内部の遷移（子内のロールバック、子の start/end スナップショット）が親の RunResult から観測できない**。`child_outcomes` は終わり方だけ。F3 の E2E カバレッジ「各ステージの各 end_state を一度は踏む」で子ステージの end_state を数えられない。CONTRACT 7.2 は「recorder は子 run も記録再生する」と書くが、記録は分類器要求の列で、遷移の記録ではない | P1b（子内で inconsistent → 修正が起きたのに親は happy と同一） | `ChildOutcome` に子の trace（または `RunResult`）を持たせる。12.12 の記録規則と合わせて F3 前に決める |
| B10 | 低 | adopting.md の記述と実装の差（第 3 節 14〜17）: status 一覧、再生時の user、適合テストの範囲、import 元 | 第 3 節 | 文書の修正 |

補足（問題ではないが記録）: 探針 P5 で store の meta.json に契約第 3 節に無い `writes` 項目がある（復元に必要で妥当）。フェーズゲート用の仮スナップショット（stage_id = phase id）が store の ordinal を消費し、RunResult からは見えない（12.4 どおり）。

---

## 5. 判定できなかった事項

- **分類器の閾値と記述の分類可能性**: toy は MarkerClassifier（印を読む）なので、goal / end_state の記述が実 LLM で分類できるか、閾値 0.5 が妥当かは判定できない（計画書どおり F2 の範囲外）
- **記録再生の同一性の全範囲**: happy と checks_failed_once（ロールバック、ゲート無効化、子 run 2 つ）で一致を確認した。中断再開を含む run は再生不能と判明（B1）。子 run が stuck / unknown で終わる run の再生は未確認
- **「行カバレッジ」の読み**: pyproject の `branch = true` により `--cov-fail-under` が判定するのは行+分岐の合算 93.14%。行だけなら 95.2%。どちらで読むかは人間の確認事項だが、判定には影響しない
- **ADR-012 の契約への提案 12.13〜12.16**: F3 ゲートの対象で本検証では判定しない。本報告の B3（ContinueAsGoal とゲート）、B5（スイートの範囲）、B9（子の trace）は同じゲートで扱うべき追加議題
- **予算**: 宣言の「時間 20 分」は探針の作成と実行で超過した可能性がある（トークンは 20 万前後）。検証の内容には影響しない

---

## 付録: 実行したコマンドと出力の要旨

```text
$ uv run pytest -q                                              → 107 passed
$ uv run pytest -q --cov=htf.runtime --cov-fail-under=90         → Required test coverage of 90% reached. Total coverage: 93.14%（coverage.log）
$ uv run pytest -v -o addopts="" tests/test_runtime_*.py tests/test_conformance_reference.py
                                                                 → 39 passed（pytest_verbose.log。台本 8 本、適合 15 件の ID）
$ uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics examples/toy-minimal/metrics/manifest.json
                                                                 → 0 finding(s)  exit=0（elaborate-claim.yaml も 0）
$ git show --stat 3e79996 / 4fbb2df / 39e84fb、git diff 3e79996 4fbb2df -- tests/ examples/toy-minimal/tests/ examples/toy-minimal/workflow.yaml
$ uv run python reports/verification/f2-runtime-and-tests/probes/p{1,1b,2,3,4,5,6,7}_*.py   → probes/*.log
$ git status --short                                             → ?? reports/verification/f2-runtime-and-tests/
```
