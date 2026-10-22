# 作業ログ

形式は計画書第4節末尾で固定。先頭に「次にやること」、続いて日付ごとに「完了したこと」「未完了と理由」「発見した問題（ワークフロー定義 / フレームワーク本体）」「実行した検証とその結果の要旨」。

## 次にやること

**F4 の利用者セッションの成果（software factory）を取り込み、adopting-gaps G-01〜G-23 の往復を一周した。F4 の人間ゲートで止まっている。** 143 passed（htf）、92 passed（software factory、変更なしで再検証）、整合性検査 0 件。未 push のコミットあり（F4 取り込み以降。push は人間の指示で）。

1. **人間ゲート（F4）**: 三つ
   - `examples/software-factory/workflow.yaml` と `implement-task.yaml` のレビュー（goal・end_state・unknown のクラス集合が MECE か、記述が成果物から観測可能か、各 end_state に戻り先があるか）。実ハーネスのレビューの予行演習。**Codex（GPT-6-Astra、effort max）の独立レビュー済み**（人間の指示）: 判定「直してから出す」。既存の 11 件と矛盾なし、重大度の引き上げ 5 件、新規 9 件。報告 `reports/verification/f4-sf-definition-review/report.md`、突き合わせ `reports/dynamic/f4-sf-definition-review/record.md`
   - 第三者レビューの指摘 11 件（`examples/software-factory/docs/plan.md` 第 1.1 節。高 1: 子 code の失敗が全て unknown → 確認ステージを足す提案。中 7、低 3）**と Codex の新規 9 件**の採否。推奨は ADR-014（Codex の突き合わせで更新: 既存 11 件は 採る 10 / 頻度を見てから 1、新規 9 件は 採る 5 / 見送る 1 / 頻度を見てから 2 / htf 側 1）。採る場合は分類体系の変更なので `workflow.version` を上げ、台本・E2E 計画・expectations を合わせる
   - `docs/decisions.md` ADR-014 の決定欄: 処置の一覧の承認、契約への提案 14.1〜14.5 の採否（14.5 は状態文書の総量の上限 / 順序 / 投影から外す印。Codex 20）
2. **承認後（通常セッション）**: 採用された指摘を software factory の定義に反映（版 0.2）、台本・計画・expectations の更新、再検証。承認された契約の提案を実装（toy-minimal で検証 → software factory で再検証）。adopting-gaps.md の各項目に「処置済み（ADR-014）」の印を付ける
3. **F5**: v1.0（adopting.md の完成版（software factory を実例に）、harness-plan-template.md の完成版、CI のコスト段階（常時 / ナイトリー / 手動）、分類体系とハーネスの同期バージョン管理の方式、docs/maintenance.md）。完了条件: 二つの玩具で全ランナーが通る、adopting-gaps.md が全て処理済み、雛形に software factory を当てはめて矛盾が無い、CI に段階がある、v1.0 として公開（人間ゲート。決定 #6 もここ）
4. **F5 の検証役**: F4 の往復で入れた本体の修正（G-04 / 05 / 06 / 08 / 16）は toy-minimal のテストで固定したが、第三者判定は F5 の検証役でまとめて行う

運用規則: 完了条件のテストは実装より先に別コミット。テストの変更も別コミット。検証役の予算は探針を含むなら 25 万トークン。push は人間の指示があった時だけ。software factory（利用者の成果物）の本体コードは、htf の API 変更で必要になった時だけ通常セッションが直し、理由を本ファイルに残す（今回は不要だった）。

`reports/` の構造: `reports/verification/<task-id>/report.md`、`reports/dynamic/<id>/record.md`、`reports/triage/`。

## 2026-10-22

### 完了したこと

- `git init`（リモート未設定。push はしない）
- 第4節のディレクトリ骨格（言語に依存しない範囲）を `.gitkeep` で作成: `schema/examples`、`contract`、`runtime`、`testing/{spec,harness,oracle,stages,e2e,triage}`、`examples/toy-minimal/{stages,tests}`、`reports`
- `schema/workflow.schema.json` に付録 A の基底スキーマを**そのまま**配置（plan.md の JSON ブロックを機械的に抽出。バイト一致を検証で確認）。拡張（carry / max / artifacts / 指標の形）は ADR 決定後の F1 本体で行う
- `docs/decisions.md`: ADR-001〜ADR-010 の下書き（文脈、選択肢ごとの帰結、推奨、強制点、付随する小決定、空欄の決定）。推奨は計画書第3節の推奨欄をそのまま採用し、独自に変えていない。ADR-010 には環境の確認結果（Python 3.12.3、uv あり、jsonschema 4.10.3 / PyYAML 6.0.1 あり、ruff / pytest 無し）と、パッケージ配置の小決定（P1 / P2 / P3）を加えた
- `docs/progress.md`（本ファイル）
- 初期コミット

**F1 本体（同日、人間の決定後）**

- 決定の記録: ADR-001〜005、007〜010 の「決定」節（ADR-009 は推奨 (a) に対し人間が (b) を選択。計画エージェントが確認し「b で確定、v1.0 に含める」の回答を得た）。ADR-010 は推奨構成 + P2
- ツールチェーン: pyproject.toml（uv、hatchling、ruff、pytest-cov）、uv.lock、.gitignore、`.github/workflows/ci.yml`（常時段のみ）。P2 配置（`src/htf/{contract,runtime,testing}`）。`tests/test_repo_layout.py` に初期化の完了条件を移植し、付録 A の構造保存の検査を追加
- 完了条件のテストを先に作成: `tests/test_schema_examples.py`、`tests/test_checker.py`（`CODES` と負例集合の一致を含む）、`tests/test_toy_minimal.py`。実装前に `uv run pytest --collect-only` が収集エラー（`ImportError: cannot import name 'check_workflow'`）で止まることを確認（下記「検証」）
- 拡張スキーマ `schema/workflow.schema.json`: artifacts（ADR-001）、指標の形（ADR-002）、carry / max、`user_input`（ADR-004）、`subworkflow` と `workflow.inputs`（ADR-009 (b)）、`version`、`additionalProperties: false`、`$defs`。付録 A の構造（properties / required / type / items）は保存
- 正例 2、負例 29（検査コード 14 種すべてに 1 件以上。検証役の探針 4 件を昇格）、子 3（`schema/examples/`）、指標マニフェスト
- 整合性検査器 `src/htf/testing/spec/`: `check_workflow` / `CODES` / `index_workflow` / CLI（終了コード 0 / 1 / 2、`--metrics` と `--metrics-module`）。子ワークフローの再帰検査、循環、深さ
- ハーネス契約 `src/htf/contract/`: `CONTRACT.md`（三操作、スナップショット形式、評価順序、7 種の遷移、escalate の 4 解決、子ワークフロー、契約適合テストの項目）、`types.py`、`interfaces.py`、`tests/test_contract.py`
- toy-minimal: `workflow.yaml`（2 フェーズ 4 ステージ。ユーザー待ち、carry、フェーズ内 / 境界越えロールバック、子ワークフロー呼び出し）、`elaborate-claim.yaml`（子 2 ステージ）、`metrics/manifest.json`。検証役の報告 W2〜W4 を反映
- 検証役（動的ワークフロー `f1-contract-and-spec`）: 宣言 → 起動 → 報告の受け入れ。記録は `reports/dynamic/f1-contract-and-spec/record.md`、報告は `reports/verification/f1-contract-and-spec/report.md`。報告の処理は record.md の表
- `docs/decisions.md` ADR-011: F1 で確定した小決定 11.1〜11.21 と、ゲートで決めてほしい事項 G1〜G7

**F2 参照ランタイムと決定論テスト（同日、人間不在で自律進行）**

- F1 ゲートの承認を記録し、G1 / G3 / G5 の記述変更と G4 (b)（集約規則の `state: unknown`）を実装。plan.md を承認どおり改訂（reports/、ステージ数の数え方、7 種の遷移）。toy-minimal の版を 0.2 に
- 完了条件のテストを先に別コミット（3e79996）: 7 種の遷移（台本 8 本）、4 解決、記録再生、フェーズゲート、loader、契約適合テストの継承。実装前の収集エラーを記録
- `htf.runtime`: model / loader / checkpoint / context / oracle / recorder / runner（ReferenceRuntime = 三操作 + start、Runner = 制御ループ）
- `htf.contract.conformance`: 継承可能な `ConformanceSuite`（Runtime の 4 操作 + start だけを対象）と `conformance.yaml`。参照ランタイムが `tests/test_conformance_reference.py` で通す
- `htf.testing.harness`: `load_example_package`、`ScriptedHuman`、`DeferringUserIO`、`QueueUserIO`、`MarkerClassifier`、`EchoLLM`、`observed_kinds`
- toy-minimal: 偽ステージ本体（`stages/`、台本で制御、宣言どおりにだけ読み書き）、指標レジストリ（`metrics/`、本物の値）、ユーザーシミュレータ（`user/`）、`harness.py`。collect の writes に `grounds/` を追加（根拠ファイルの置き場。G1 の「指す先が空」を成果物で作るため）
- `docs/adopting.md` 初版、CI に runtime カバレッジ 90% の独立ステップ、ADR-012（F2 の小決定 12.1〜12.12 と契約への提案 12.13〜12.16）

**F2 の完了（検証役の報告の処理）**

- 検証役 `f2-runtime-and-tests` の報告（`reports/verification/f2-runtime-and-tests/report.md`）: 完了条件 6 項目すべて「満たす」。探針 8 件。問題 B1〜B10、W1〜W3、adopting.md の不足 17 点。予算はトークンを 7% 超過（準正常。`reports/dynamic/f2-runtime-and-tests/record.md`）
- 回帰テストを先に別コミット（b5839c4、5 件失敗）→ 修正: B1 記録は試行単位で確定し中断した試行は破棄、B2 子 run 起動前に workspace 配下を空に、B3 ゲート不成立の escalate に ContinueAsGoal → 人間がゲートを通す、B4 最上位で human 無しは ContractViolation、B6 未消費の記録を検出、B9 `RunResult.child_results`
- B5 / B7 / B8 / B10 と不足 17 点: adopting.md を実態に揃え、閾値 0.5 を仮置きとして記録。CONTRACT 第 8 節と第 7 節 1 の改訂は契約の変更なので提案（ADR-012 12.25 / 12.26）
- W1 台本の規則を README に、W2 は v1.0 では誤認が起きない理由を記載、W3 verify に `goal_assumed`（台本 goal_assumed.yaml）

**F3 テストランナー群（同日、人間不在で自律進行）**

- 完了条件のテストを先に別コミット（b03a4b1、5 ファイル収集エラー）: 分布（正しい expectations が通りずらしたものが落ちる、再進入で分布が変わる、遷移行列）、独立性（分割の検出と非検出）、オラクル検証（既知の κ と ECE、違う κ の棄却、再実行一致）、E2E（17 対象の誘発 / 注入、マルコフ合成の一致と分割構成での不一致）、トリアージ一周
- runtime: `EvaluationRecord`（評価ログ）、`Runner(inject=)`（注入。子 run にも引き継ぐ）
- `htf.testing.stages`（run_many、tally、expectations、independence、transition_matrix）、`htf.testing.oracle`（コーパス、κ、ECE、再実行一致、ConfusionClassifier）、`htf.testing.e2e`（列挙、計画、カバレッジ、マルコフ合成）、`htf.testing.triage`（待ち行列）
- toy-minimal: `StochasticSource`（成果物を書くコードは決定論的本体と共通）、profiles（markov / split）、expectations（markov / markov_shifted / split）、e2e/plan.yaml、`make_stochastic_runner` / `make_plan_runner`
- ADR-013（13.1〜13.14）、adopting.md 第 6 節（テストランナー群）、pytest マーカー distribution / e2e、版 0.1.0（tag は未）

**F3 の完了（検証役の報告の処理）**

- 検証役 `f3-test-runners`（`reports/verification/f3-test-runners/report.md`）: 完了条件 1〜3、5〜7 は満たす。4 の後半「split でマルコフ予測が外れる」は、テストが合成に子 run 数を渡さず既定 1 で合成していたための見かけ（観測どおり子 2 で合成すると差 0.010）。探針 6 件（ネットワーク禁止での全テスト、区間の余裕、p 値の種依存、注入、合成の余裕、オラクル検証、成果物との整合）。予算内（約 15.6 万トークン、14 分）
- テストと構成の変更を先に別コミット（e7ef63f、7 件失敗）→ 修正: 合成は子 run 数が無ければ ValueError（B1）、split 構成を主張ごとに持続する振る舞いに（T1。奇数番目の主張は常に stuck → run の結果に効く）、注入の鍵を (workflow, stage, 進入回数) にして定義と照合（B3 / B4）、`verifiable`（B5）、注入由来をトリアージで既定除外（B6）、下流の終端 `end:<status>`（B7）、split の expectations を使う（T3）、失敗した主張を `pick` で選ぶ（T4）
- 閾値の懸念（報告第 3 節）を ADR-013 に転記し、ゲートで人間が読む形にした。B8（テストの変更が実装コミットに混ざった）は運用規則として ADR-013 13.19 に記録

**v0.1 のゲート通過と公開（人間の決定「12. 承認。提案は推奨を選択、2. 承認。閾値は仮置き、3. GitHub に public で push。いずれもあなたの作業」）**

- decisions.md: ADR-012 / ADR-013 の決定欄に承認を記録。契約への提案 12.13〜12.16、12.25〜12.26 を推奨どおり実装（完了条件を先に別コミット 385144d、6 件失敗 → 実装 bae80b4）: 検査器に `subworkflow_ref`（親子で name 重複）と `subworkflow_user_input`、契約に `start`、`Escalation.cause` に `phase_gate_failed`、CONTRACT 第 7・8 節の改訂
- README.md を追加。tag v0.1.0、GitHub の public リポジトリ `harness-testing-framework-v2` を作成して push、Release v0.1.0（下記の検証の要旨）
- 人間の指示「最低限の雛形はおいてください」で `docs/harness-plan-template.md`（最低限版）を追加し push
- 保護ファイル（contract/、schema/examples の負例、plan.md の改訂）の編集はすべて人間の承認の後

**F4 の往復（利用者セッションの成果の取り込みと adopting-gaps の処置）**

- 利用者セッション（人間が別に起動）の成果 `examples/software-factory/` をそのまま取り込んだ（81433db）: 5 フェーズ 8 ステージ + 子 2、実ツール（compile / ruff / pytest + coverage）の指標、台本 21、E2E 31 対象、テスト 92 件、adopting-gaps G-01〜G-23、第三者レビュー 11 件（利用者セッションが同じ読取制限のサブエージェントで実施）。利用者セッションは本体・plan.md・progress.md・decisions.md を読んでいない（その progress.md に記録）
- F4 開始に伴うガード（software-factory 不在）を外した（3940915）
- G-04 / 05 / 06 / 08 / 16 を toy-minimal で再現するテストを先に別コミット（02cb2af、6 件失敗）→ 本体を修正（034c7cf）。G-07 ruff の除外、G-03 CI のステップ、文書 13 件、契約への提案 4 件（ADR-014 14.1〜14.4）、解消しない理由 1 件（G-14）
- software factory は変更せずに再検証: 92 passed、整合性検査 0 件（本体の修正が利用者の成果物に影響しない）
- 利用者セッションの読取制限を自分の目で確認（第7節「制限を破った時点で F4 の結果は無効」）: `examples/software-factory/` の import は `htf.contract`、`htf.contract.conformance`、`htf.runtime`、`htf.testing.{harness,oracle,spec,stages,triage}` の公開名だけ。`htf.runtime.runner` 等の内部モジュール、`src/htf`、htf の plan.md / decisions.md / progress.md、htf の `tests/` への参照は無い。探針の残骸（probe、log）も無い → **F4 の結果は有効**
- ADR-014 に第三者レビュー 11 件への推奨（採る 8、頻度を見てから 3）を添えた
- **人間の指示で Codex（GPT-6-Astra、reasoning effort max）に定義 2 ファイルの独立レビュー**（第5.10節の宣言 `f4-sf-definition-review`。読取制限は隔離ディレクトリで構造的に課し、既存の 11 件は渡さない）。2 ターン（独立レビュー 31 分 + 前提の訂正 13 分）、書き込み 0。最後のメッセージを `reports/verification/f4-sf-definition-review/report.md` にそのまま写し、既存 11 件との突き合わせ（矛盾なし、重大度の引き上げ 5、新規 9）を `reports/dynamic/f4-sf-definition-review/record.md` に、採否の推奨の更新と契約への提案 14.5 を ADR-014 に書いた。定義は変えていない

### 未完了と理由

- ツールチェーンの骨格（pyproject、CI、.gitignore）: ADR-010 が未決のため作っていない（計画書 F1「決定 #10 が出たらツールチェーンの骨格と CI の雛形を作る」）
- スキーマの拡張、検査器、契約、toy-minimal: ADR-001 / 002 / 005 / 007 が未決のため着手していない
- `examples/software-factory/` の骨格: 意図して作っていない。F4 の利用者セッションが adopting.md と雛形だけから作る成果物で、骨格を先に置くと adopting.md 以外のヒントを与えて F4 の検証（文書の十分性）が弱まる。人間が覆してよい
- `docs/adopting.md`、`docs/harness-plan-template.md` のプレースホルダ: 同様に F2 / F5 の成果物なので作っていない

**F1 本体**

- 人間ゲート（スキーマと契約の承認、ADR-011 の承認、G1〜G6）: 人間の決定待ち
- G4 (b) のスキーマ拡張（集約規則の unknown 優先）: 提案止まり。承認後に実装
- toy-minimal の記述 W1（意味の確定が要る）と T1〜T4（分類体系の変更）: 提案止まり（第5.4節）
- CI の実行: リモート未設定のため GitHub Actions は一度も動いていない。ローカルで同じコマンド（ruff check、ruff format --check、pytest --cov）を実行した
- `htf.runtime` は空（F2）。`src/htf/testing/{harness,oracle,stages,e2e,triage}` も空（F2〜F3）

**F2**

- 検証役による完了条件の第三者判定: 本セッションで起動する（下記の宣言）。受け入れてから F3 へ
- ADR-012 の契約への提案 12.13〜12.16: F3 ゲートで決める（契約は承認済みなので F2 では変えない）
- 子ワークフローのステージのユーザー入出力: v1.0 では未対応（`ContractViolation`。ADR-012 12.8）

**F3**

- 検証役の判定と v0.1 の公開承認: 本セッションで検証役を起動し、報告を受け入れた後に人間ゲートで止まる
- 契約への提案（ADR-012 12.13〜12.16、12.25〜12.26）: 承認待ちのため未実装
- expectations の起点「保存した開始時スナップショット」: 欄だけ（v0.1 では `workflow_start` のみ）
- トリアージの記述改訂の提案: 作らない（人間の承認が要る。第5.4節）

**F3 で見送った改善（v0.1 の後。文書化のみで未実装）**

- 注入に carry を添える（検証役 F3 の B2。今は Verdict だけを差し替え、戻り先は空の carry で動く）
- マルコフ合成の比較の粒度（13.11。completed / aborted の 2 値は粗い。ステージ別のクラス頻度や run 長の分布に広げる）
- expectations の区間を「名目 ± k·SE」か信頼区間で書ける形式（13.4。形式の改訂は F4 の基準が出てから）

**F4**

- 人間ゲート（workflow.yaml のレビュー、第三者レビュー 11 件 + Codex の新規 9 件の採否、ADR-014）: 人間の決定待ち
- 契約への提案 14.1〜14.5: 承認まで未実装（G-11 / G-18 / G-19 は文書で暫定の指針。14.5 は Codex 20）
- adopting-gaps.md への「処置済み」の印: 承認後に付ける（利用者の成果物を今は変えない）
- push: F4 取り込み以降のコミットは未 push（人間の指示で）

### 発見した問題

#### ワークフロー定義の問題

F1 時点: なし（まだワークフロー定義が存在しない）

**software factory（F4 ゲート。Codex の独立レビュー。定義は変えず、採否は ADR-014 で提案）**

- 高 10 件のうち分類体系が変わるもの 8: 子 code の失敗が全て unknown（01）、verify の品質不成立（02）、plan の scope 重複・テスト無し（03）、design の割当て漏れ（04）、統合の失敗（05）、release の拒否理由（08）、design_gap の原因の混同（09）、release の成果物不備（10）。記述のみ 1: implement の本体指示と aggregate の食い違い（06）。carry の宣言の追加 1: 二段ロールバック（07）
- 中 9 件（12〜18、20、21）・低 1 件（19）は記述の補強が中心（12、13、14、15、16、17、18、19）。20 は htf 側（提案 14.5）、21 は頻度を見てから。軽微 2（intake の constraints の必須性、`max` が run 全体の上限であること）
- 既存の 11 件（sf 計画書 第 1.1 節）との関係: すべてに対応する指摘があり矛盾なし。Codex は 5 件の重大度を引き上げた。突き合わせは `reports/dynamic/f4-sf-definition-review/record.md`

#### フレームワーク本体の不足

- **第4節の木に `reports/` が無い**が、第5.9節（検証役の書き先は `reports/` のみ）と第5.10節（`reports/dynamic/<id>/`）が参照している。食い違いなので `reports/` を作成した。plan.md 本文への反映は人間の確認を待つ（plan.md は保護ファイルで計画エージェントが編集できるが、計画書本文の変更は人間の確認を経たい）
- **第4節の木にフレームワーク自身のテスト（検査器のテスト、契約適合テスト等）の置き場が無い**。`testing/` はランナーの実装であってテストではない。ADR-010 の小決定（パッケージ配置）で `tests/` の追加として扱う
- **`reports/` の内部構造が `reports/dynamic/<id>/` 以外は未定義**。検証役の報告の置き場（例: `reports/verification/<task>/`）は、F1 本体で検証役を初めて使う時に決めて記録する

**toy-minimal（検証役の報告 2.4 節）**

- 直した（意味を変えない範囲。ADR-011 11.21）: W2 `verify.inputs_missing` に不足一覧の成果物（report.json）を明記。W3 `verify.goal.qualitative` の「全て検証済み」と「検証できないものは仮定」の同居を解消。W4 `elaborate.sections_inconsistent` の「再試行の後も」（実行履歴）を成果物の条件に書き換え。子を持つステージの goal 定性が分類器に渡されない旨のコメント
- 提案止まり（人間の承認が要る。decisions.md ADR-011 G1〜G5）: W1 `draft.inputs_insufficient` の意味確定。T1 `verify` で検証済み 8 割未満が毎回 unknown になる隙間。T2 goal の「仮定」と `inputs_missing` の境界。T3 集約で stuck と unknown が混在した時に unknown が人間に届かない。T4 子 `check_section` の「整合」の意味

**F1 本体で見つかったもの**

- 計画書 F2 の「6 種の遷移」は内訳が書かれていない。契約では next / rollback_within_phase / rollback_across_phase / escalate_unknown / escalate_max_exceeded / suspend_resume と読み、ADR-009 (b) の `subworkflow_aggregate` を加えて 7 種にした（ADR-011 11.13）。計画書の改訂は人間の確認待ち
- 計画書 F1 の「3〜4 ステージ」は子ワークフローを想定していない（G6）
- 集約規則で「子の unknown を親の unknown に優先」が書けない（検証役の報告 F1 → G4）。スキーマ拡張の提案
- CONTRACT.md と types.py の食い違い 2 件（`taken_at`、`DecidedBy.quantitative`）→ 直した（ADR-011 11.18、11.19）
- 負例の薄い箇所 4 件（検証役の報告 F4）→ 探針を負例に昇格（ADR-011 11.20）
- ruff の E501 が全角文字を幅 2 で数えるため、日本語のコメントで誤検出する → `ignore = ["E501"]`（ADR-011 11.16）
- ruff format が docs/ の Markdown 内コードブロックを整形した → `extend-exclude = ["docs", "reports"]`
- スキーマの正本（`schema/`）と配布物の同梱（`htf/schema/`）の二重化 → `htf.schema.schema_path()` で解決（ADR-011 11.17）

**toy-minimal（F2）**

- collect の `writes` に `grounds/`、draft の `reads` に `grounds/` を追加した。根拠ファイルの置き場が宣言に無く、G1 の「根拠の所在が指す先が無いか空」を成果物で作れなかったため（分類体系の変更ではない。整合性検査 0 件）

**F2 で見つかったもの（ADR-012 に記載）**

- 契約の三操作に「開始時スナップショットの取得」が無く、契約適合テストが Runtime + `start` を要求した（12.14）
- 束縛の鍵 (workflow 名, stage id) は親子で同名の workflow で衝突する。検査器に性質を足す提案（12.13）
- フェーズゲート不成立の `Escalation.cause` が無い（12.15）。子のステージの `user_input` を静的に禁止したい（12.16）
- 記録再生の不一致を作るには本体の振る舞い（台本の結果）を変える必要がある。入力（回答・LLM・分類器）は記録から来るので台本の入力を変えても要求は変わらない（テストの前提を直した）

**F3 で見つかったもの**

- 分布の集計で first / reentry を分けるには runtime の進入回数が要った（carry の有無では verify → draft → verify の再進入を区別できない）→ `EvaluationRecord.entry`（ADR-013 13.2）
- 独立性検証の代表は「受け取った carry」では分けられない（check_section は carry を受けない）→ 既定を「戻り先へ運ぶ carry（carry_out）」にした（13.5）
- E2E の注入は親の Runner だけでは子ステージに届かない → inject を子 run に引き継ぐ
- マルコフ合成は子 run の数が分布から出ないので、観測された子 run 数の分布から引く（13.11）
- `ConfusionClassifier` は真のラベルが要るので、状態文書の `truth:` 行から読む（テスト専用の約束）

**F4 の往復で見つかったもの（software factory の adopting-gaps。処置は ADR-014）**

- runtime: `pass` の鍵が carry でしか来ないと初回進入で落ちる（G-04 → 無ければ渡さない）。即答と中断が混ざる UserIO で再開後の回答がずれる（G-05 → 即答も累積）。状態文書の切り詰めが固定（G-08 → `max_file_chars`）
- 検査器: 親子でステージ id が重なると分布の鍵が混ざる（G-06 → `unique_ids`）
- ランナー: E2E 計画で台本の任意の欄を上書きできない（G-16 → `overrides`）
- 契約の不足（提案）: 進入回数（G-11）、子 run の終わり方を親の本体に（G-18）、`ask` の文脈（G-19）、`pass` の文言（G-04）
- 文書の不足 13 件（adopting.md と雛形に反映）。構成: ruff がフィクスチャを見る（G-07）、ハーネスのテストが CI に無い（G-03）、ガードのテスト（G-15）
- 投影（Codex の指摘 20）: 状態文書は 1 ファイルの切り詰めだけで総量の上限が無く、`reads: [codebase/]` のようにディレクトリを読むステージでは配下の全ファイルが判定結果（writes）より前に並ぶ。`reads` が本体の読取許可と分類器への投影の二役を兼ねる → 契約への提案 14.5（総量の上限 / writes を先に / 投影から外す印）。承認まで未実装
- 計画エージェントの誤り（過程）: 検証役への指示に「`reads` は分類器に渡らない」と書いた。正しくは `reads ∪ writes ∪ memory_in`（CONTRACT 第 5.4 節、adopting.md 3.6、スキーマ、`htf.runtime.project` のすべてが一致）。検証役が資料との不一致を指摘したので第 2 ターンで訂正し、観点 (b) の差分を取った。本体・契約・文書の修正は不要。再発防止: 検証役への前提は資料の節を指す形で書き、自分の要約を前提として書かない

### 実行した検証とその結果の要旨

完了条件は実装より先に `check_init.py` として書いた。ツールチェーン未決のためリポジトリには置かず、全文を本節末尾に埋め込む（ADR-010 決定後に `tests/` へ移植する。再実行は全文をファイルに保存して `python3 -I check_init.py <リポジトリのルート>`）。検査内容:

1. 骨格ディレクトリの存在、`examples/software-factory` が無いこと、`.git` の存在
2. `schema/workflow.schema.json` が JSON として読め、`jsonschema.Draft202012Validator.check_schema` を通る
3. 同ファイルが plan.md 付録 A の JSON ブロックとパース後に等しく、かつバイト一致する
4. `docs/decisions.md` に `## ADR-001`〜`## ADR-010` がちょうど10件あり、各 ADR に「### 推奨」「### 決定」「- 強制点:」がある
5. `docs/progress.md` の先頭の節が「次にやること」で、固定の4小節と「発見した問題」の二分がある

実行コマンドと結果:

```text
$ python3 -I <scratchpad>/check_init.py .
ok   dir exists: schema/examples ... ok   dir exists: reports   （13 ディレクトリ）
ok   examples/software-factory is NOT pre-created (F4 の成果物)
ok   git repository initialized
ok   schema parses and conforms to Draft 2020-12 metaschema
ok   appendix A json block found in plan.md
ok   schema/workflow.schema.json equals appendix A (parsed JSON equality)
ok   schema/workflow.schema.json is byte-identical to appendix A block
ok   decisions.md has heading ADR-001 ... ADR-010 / exactly 10 ADR sections
ok   ADR-001..010 each has 決定 / 推奨 / 強制点
ok   progress.md first section is 次にやること / 4 subsections / 発見した問題 の二分
0 failure(s)
exit=0
```

負例の確認（検査が空振りでないこと）: スキーマのコピーを壊した作業コピーに対して同じ検査を実行し、メタスキーマ検査と付録 A 一致の項目が FAIL になり終了コードが 1 になることを確認した。

```text
$ # コピー negctl/ の schema の "type" を "objekt" に書き換えてから
$ python3 -I check_init.py negctl
FAIL schema metaschema check: 'objekt' is not valid under any of the given schemas
FAIL schema/workflow.schema.json equals appendix A (parsed JSON equality)
FAIL schema/workflow.schema.json is byte-identical to appendix A block
3 failure(s)
exit=1
```

`check_init.py` の全文:

```python
"""F1 初期化タスクの完了条件（実装より先に書いた検査）。

引数: リポジトリのルート。終了コードは 0 なら全条件を満たす。
条件:
  1. 第4節の骨格ディレクトリが存在する（language-agnostic な範囲）
  2. schema/workflow.schema.json が JSON として読め、Draft 2020-12 メタスキーマに適合する
  3. schema/workflow.schema.json の内容が docs/plan.md 付録 A の JSON ブロックと一致する（「そのまま置く」）
  4. docs/decisions.md に ADR-001〜ADR-010 の見出しがあり、各 ADR に「決定」節がある
  5. docs/progress.md の先頭の節が「次にやること」で、固定された4つの小節を持つ
"""

import json
import re
import sys
from pathlib import Path

import jsonschema

root = Path(sys.argv[1]).resolve()
failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)

**F1 本体（同日）**

完了条件のテストを先に書き、実装前に失敗することを確認した:

```text
$ uv run pytest --collect-only -q      （schema / checker / toy-minimal のテストを書いた直後、実装前）
tests/test_toy_minimal.py:15: in <module>
    from htf.testing.spec import check_workflow, index_workflow
E   ImportError: cannot import name 'check_workflow' from 'htf.testing.spec'
ERROR tests/test_checker.py
ERROR tests/test_toy_minimal.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
exit=2
```

実装後（コミット ea27337 の時点）:

```text
$ uv run ruff check .                  → All checks passed!
$ uv run ruff format --check .         → 21 files already formatted
$ uv run pytest --cov=htf --cov-report=term-missing
  58 passed（spec/checker.py 95%、cli.py 85%。contract/ は import する検査が無かったため 0% → tests/test_contract.py を追加して 63 passed）
$ uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics examples/toy-minimal/metrics/manifest.json
0 finding(s)   exit=0
$ uv run python -m htf.testing.spec schema/examples/negative/subworkflow_ref__cycle.yaml --metrics schema/examples/metrics.json
  … [subworkflow_depth] … [subworkflow_ref] 循環参照 … [subworkflow_ref] 子定義が検査を通らない … 4 finding(s)   exit=1
```

検証役の受け入れ（第5.10節。`reports/dynamic/f1-contract-and-spec/record.md`）:

```text
$ git status --short                    → ?? reports/verification/   のみ（保護ファイル・本体・テストに変更なし）
$ uv run pytest -q                      → 63 passed
$ uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics …  → 0 finding(s)
```

報告の処理後（W2〜W4 の修正、CONTRACT.md / types.py の修正、負例 4 件の昇格）:

```text
$ uv run ruff check . && uv run ruff format --check .   → All checks passed! / 22 files already formatted
$ uv run pytest -q                                      → 67 passed
$ for f in rollback_forward__later_stage metric_registered__phase_metric subworkflow_inputs__pass_not_in_memory_in unique_ids__duplicate_phase; do … ; done
  [carry_declared] [memory_in_source] [rollback_forward]  <- rollback_forward__later_stage
  [metric_registered]                                      <- metric_registered__phase_metric
  [subworkflow_inputs]                                     <- subworkflow_inputs__pass_not_in_memory_in
  [unique_ids]                                             <- unique_ids__duplicate_phase
$ uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics examples/toy-minimal/metrics/manifest.json
0 finding(s)   toy exit=0
```

最終レビュー後の追加（同日）:

- W3 の修正文「検証済みの主張が全体の 8 割以上ある」は quantitative の `verified_ratio: min 0.8` の言い換えで、定性に数値基準を持ち込んでいた（分類器に割合の判定を求め、指標との不一致を自分で作る）。「仮定とした主張にはその理由が記録されている」に直した（成果物の条件。ADR-011 11.21 の範囲）
- ADR-011 11.17（wheel への同梱）を実行で確認: `uv build` → `unzip -l dist/*.whl | grep schema` → `htf/schema/workflow.schema.json`（14155 bytes）が入っている

```text
$ uv run pytest -q                                      → 67 passed
$ uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics examples/toy-minimal/metrics/manifest.json
0 finding(s)
$ uv run ruff check .                                   → All checks passed!
```

**F2 実装後**

```text
$ uv run ruff format . && uv run ruff check .             → 43 files left unchanged / All checks passed!
$ uv run pytest -q                                        → 107 passed
   内訳: 遷移の台本 8 本 + 7 種の和集合 + carry の検査（test_runtime_transitions）、4 解決 + 未宣言 carry の拒否
   （test_runtime_escalation）、記録再生の同一性と不一致検出（test_runtime_recorder）、ゲート不成立 → unknown と
   無効化・再評価（test_runtime_phase_gate）、loader の拒否、契約適合テスト 15 項目（test_conformance_reference）、
   子のユーザー入出力の拒否（test_runtime_child_user）
$ uv run pytest -q --cov=htf.runtime --cov-fail-under=90  → Required test coverage of 90% reached. Total coverage: 93.14%
   runner.py 92%、oracle.py 87%、checkpoint.py 98%、context.py 90%、model.py 96%、recorder.py 95%、loader.py 100%
$ uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics examples/toy-minimal/metrics/manifest.json
0 finding(s)
```

最初の実行で落ちたのは `test_replay_detects_mismatch` 1 件のみ（テストの前提の誤り。上記「本体の不足」）。
子のユーザー入出力の拒否は、最初は子 Runner が中断状態で返すため「想定外の状態」の例外になった → 中断状態を「未対応」の `ContractViolation` に写した。

**F2 の報告処理後**

```text
$ uv run pytest -q tests/test_runtime_f2_findings.py   （修正前、コミット b5839c4）
FAILED test_b1_replay_reproduces_run_with_suspend_resume / test_b2_child_workspace_is_cleared_on_reentry /
FAILED test_b3_continue_as_goal_passes_a_failed_gate / test_b4_top_level_runner_without_human_raises_on_escalate /
FAILED test_b6_unconsumed_replay_entries_are_detected
$ uv run ruff format . && uv run ruff check .             → 45 files left unchanged / All checks passed!
$ uv run pytest -o addopts="" -q                           → 113 passed
$ uv run pytest -q --cov=htf.runtime --cov-fail-under=90  → Required test coverage of 90% reached. Total coverage: 93.55%（行+分岐）
$ uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics examples/toy-minimal/metrics/manifest.json → 0 finding(s)
```

注: pyproject の addopts が `-q` なので `pytest -q` は `-qq` 相当になり件数の行が出ない。件数を見る時は `-o addopts=""`。

**F3**

```text
$ uv run pytest --collect-only -q                         （テストを書いた直後、実装前。コミット b03a4b1）
E   ImportError: cannot import name 'ConfusionClassifier' from 'htf.testing.oracle'
E   ImportError: cannot import name 'check_expectations' from 'htf.testing.stages'
E   ImportError: cannot import name 'compare_outcomes' from 'htf.testing.e2e'
E   ImportError: cannot import name 'independence' from 'htf.testing.stages'
E   ImportError: cannot import name 'load_corpus' from 'htf.testing.oracle'
ERROR tests/test_f3_{distribution,e2e,independence,oracle,triage}.py   exit=2

実装後:
$ uv run pytest -o addopts="" -q tests/test_f3_triage.py tests/test_f3_oracle.py tests/test_f3_e2e.py::… tests/test_runtime_*
  1 failed（E2E 計画の注入が子ステージに届かない）, 22 passed → inject を子 run に引き継いで修正
$ uv run pytest -o addopts="" -q tests/test_f3_e2e.py tests/test_f3_distribution.py tests/test_f3_independence.py
  10 passed in 49.28s
$ uv run ruff format --check . && uv run ruff check .     → 50 files already formatted / All checks passed!
$ uv run pytest -o addopts="" -q                           → 127 passed in 50.06s
$ uv run pytest -q --cov=htf.runtime --cov-fail-under=90  → Required test coverage of 90% reached. Total coverage: 93.70%
$ uv run pytest -q --cov=htf                               → testing/e2e 91%、oracle 93%、stages 91%、triage 75%、TOTAL 92%
```

**F3 の報告処理後（最終）**

```text
$ uv run pytest -o addopts="" -q tests/test_f3_e2e.py tests/test_f3_triage.py tests/test_f3_independence.py   （修正前、コミット e7ef63f）
FAILED test_markov_prediction_deviates_for_split_body / test_synthesize_requires_child_counts_for_subworkflows /
FAILED test_inject_keys_are_workflow_qualified_and_validated / test_injected_unknown_is_excluded_by_default /
FAILED test_split_class_is_detected / test_unsplit_class_is_not_flagged / test_unverifiable_class_is_reported_as_such
7 failed, 4 passed
$ uv run ruff format . && uv run ruff check .             → 50 files left unchanged / All checks passed!
$ uv run pytest -o addopts="" -q                           → 131 passed in 64.84s
$ uv run pytest -q --cov=htf.runtime --cov-fail-under=90  → Required test coverage of 90% reached. Total coverage: 92.52%
$ uv run pytest -q --cov=htf                               → TOTAL 93%
$ uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics examples/toy-minimal/metrics/manifest.json → 0 finding(s)
```

**v0.1 ゲート通過後（契約への提案の実装）**

```text
$ uv run pytest -o addopts="" -q tests/test_checker.py tests/test_contract.py tests/test_runtime_child_user.py   （実装前、385144d）
FAILED test_negative_reports_expected_code[subworkflow_ref__same_name.yaml] / [subworkflow_user_input__child_asks.yaml] /
FAILED test_every_code_has_a_negative_and_vice_versa / test_runtime_protocol_includes_start_and_three_operations /
FAILED test_escalation_cause_includes_phase_gate_failed / test_child_user_input_is_rejected_statically
6 failed, 39 passed
$ uv run ruff check .                                      → All checks passed!
$ uv run pytest -o addopts="" -q                           → 136 passed in 64.55s
$ uv run pytest -q --cov=htf.runtime --cov-fail-under=90  → Required test coverage of 90% reached. Total coverage: 92.52%
$ uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics …   → 0 finding(s)
$ uv run python -m htf.testing.spec schema/examples/negative/subworkflow_ref__same_name.yaml --metrics schema/examples/metrics.json
  … [subworkflow_ref] 子の workflow.name 'minimal' が親と同じ（束縛の鍵が衝突する）   1 finding(s)
```

公開（人間の指示「GitHub に public で push」による）:

```text
$ git tag -a v0.1.0 -m "v0.1.0: …"
$ gh repo create harness-testing-framework-v2 --public --source=. --remote=origin --push
  → https://github.com/asuka1975/harness-testing-framework-v2 PUBLIC、main を push
$ git push origin v0.1.0                              → [new tag] v0.1.0
$ gh release create v0.1.0 --title "v0.1.0" --notes … → https://github.com/asuka1975/harness-testing-framework-v2/releases/tag/v0.1.0
$ gh run list（初回の GitHub Actions）                 → main: success（ruff check / format --check / pytest --cov / runtime 90% の段。https://github.com/asuka1975/harness-testing-framework-v2/actions/runs/39698988217）
```

LICENSE は置いていない（人間が決める。無ければ既定で all rights reserved）。

**F4 の往復**

```text
$ uv run python -m htf.testing.spec examples/software-factory/workflow.yaml --metrics examples/software-factory/metrics/manifest.json → 0 finding(s)
$ uv run pytest -o addopts="" -q examples/software-factory/tests          → 92 passed in 106.18s（取り込み時）
$ uv run pytest -o addopts="" -q tests/test_f4_gaps.py tests/test_checker.py   （修正前、02cb2af）
FAILED test_g05_… / test_g04_… / test_g06_… / test_g08_… / test_g16_… / test_negative_reports_expected_code[unique_ids__stage_shared_with_child.yaml]
6 failed, 36 passed
$ uv run ruff format . && uv run ruff check .             → 68 files left unchanged / All checks passed!
$ uv run pytest -o addopts="" -q                           → 143 passed in 65.84s
$ uv run pytest -q --cov=htf.runtime --cov-fail-under=90  → Required test coverage of 90% reached. Total coverage: 93.20%
$ uv run pytest -o addopts="" -q examples/software-factory/tests          → 92 passed in 104.64s（本体修正後、software factory は変更なし）
$ 整合性検査: software-factory 0 finding(s)、toy-minimal 0 finding(s)
```

**Codex の独立レビュー（`f4-sf-definition-review`、人間の指示）**: 第 1 ターン 17:36〜18:07（31 分）、入力 186,058 トークン（うちキャッシュ 153,984）、出力 30,383（うち推論 20,767）、コマンド 10（すべて隔離ディレクトリ内の読取。祖先ディレクトリの `AGENTS.md` 探索は空振り）、書き込み 0。第 2 ターン（前提の訂正）18:08〜18:22（13 分）、入力 259,519（キャッシュ 197,248）、出力 42,328、コマンド 0。判定「直してから出す」。指摘は 21 番まで（第 2 ターンで 11 を取り下げ、12・17 を改訂、20・21 を追加）。構造面は既存レビューと同じ結論（優先順位で解消されない重複なし、子の集約は網羅、11 辺の戻り先と carry は宣言と整合）。時間の合計 44 分は宣言の上限 40 分を超えた（第 2 ターンは計画エージェントの誤りの訂正。準正常として受け入れ。`record.md`）

### 動的ワークフローの宣言（第5.10節）: `f4-sf-definition-review`

- **目的**: F4 人間ゲートの項目 1（`examples/software-factory/workflow.yaml` と `implement-task.yaml` の MECE・観測可能性・戻り先のレビュー）を、人間に出す前に実装を見ていない第三者に読ませる（第5.9節「workflow.yaml の MECE レビューは必ず検証役を通す」）。人間の指示: 「1. について Codex Astra 6 Max にレビューをもらってください」
- **役割と人数**: 検証役 1（Claude のサブエージェントではなく外部 CLI: Codex CLI 0.162.1、モデル `gpt-6-astra`、reasoning effort `max`、サンドボックス read-only、非対話 `codex exec`）
- **入力**: 読取制限は指示ではなく構造で課す。隔離ディレクトリに次だけを複製して作業ルートにする: `workflow.yaml`、`implement-task.yaml`、`metrics/manifest.json`、`docs/adopting.md`、`src/htf/contract/CONTRACT.md`、`schema/workflow.schema.json`、software factory の `docs/plan.md` 第 0〜1 節（**第 1.1 節の既存の第三者レビュー 11 件は除く**。独立性のため）。stages/ や metrics/ の実装、htf 本体、plan.md、decisions.md、progress.md は渡さない
- **書いてよいパス**: 検証役は書かない（read-only）。最後のメッセージを計画エージェントが `reports/verification/f4-sf-definition-review/report.md` にそのまま写し、記録を `reports/dynamic/f4-sf-definition-review/record.md` に残す
- **完了条件**: 報告に (1) 全体の判定、(2) 指摘の表（重大度・対象・観点・引用による根拠・失敗する場面・分類体系の変更か記述のみか・提案）、(3) ステージごとの所見（問題なしも明記）、(4) 判定できなかった事項、(5) 読んだファイルの一覧。受け入れ時にイベント記録から読取範囲を確かめる
- **予算**: 1 ターン、時間 40 分、フレームワーク外の LLM 呼び出し 1 セッション（Codex）
- **反復の上限**: 1（独立レビューの後、既存の 11 件との突き合わせを同じセッションの続きで 1 ターンだけ追加してよい。これは独立性を損なわない）。**入れ子の深さ**: 0
- **受け入れ**: 報告を読み、既存の 11 件と突き合わせ（重複 / 新規 / 矛盾）て人間ゲートの材料にする。定義は変えない（指摘はすべて提案。ADR-014 の決定欄も触らない）
- **実績（起動後に追記）**: 2 ターン。追加の 1 ターンは突き合わせではなく、計画エージェントの指示の前提の誤り（`reads` の投影）の訂正に使った。突き合わせは計画エージェントが `record.md` で実施。時間 44 分（上限 40 分を超過。準正常として受け入れ。理由は `record.md`）。読取範囲は両ターンとも隔離ディレクトリの中だけ。判定: 準正常

### 動的ワークフローの宣言（第5.10節）: `f3-test-runners`

- **目的**: F3 の完了条件の第三者判定（すべて LLM なし。正しい expectations が通りずらしたものが落ちる、独立性検証が分割を検出、E2E が全 (stage, end_state) を踏みマルコフ予測が実測と一致、偽の分類器で既知の κ と ECE を再現、トリアージに一件流せる）と、閾値の仮置き（ADR-013）の妥当性の読み
- **役割と人数**: 検証役 1（general-purpose サブエージェント。新規起動）
- **入力**: docs/plan.md（第6節 F3）、docs/decisions.md（ADR-012、ADR-013）、docs/adopting.md 第 6 節、tests/test_f3_*.py、examples/toy-minimal/（profiles、expectations、e2e/plan.yaml、stages/、harness.py）、`uv run pytest` と `uv run pytest --cov` の出力。実装 src/htf/testing/ と src/htf/runtime/ は読んでよいが判定の根拠は実行結果
- **書いてよいパス**: `reports/verification/f3-test-runners/` のみ
- **完了条件**: `report.md` に (1) F3 完了条件の各項目の判定と根拠、(2) 自作の探針（例: expectations の区間を少し動かして落ちる境界、独立性検証の p 値の種依存、注入した Verdict が記録に残ること、マルコフ合成の許容差 0.1 の余裕）、(3) ADR-013 の閾値で人間に見せるべき懸念、(4) 発見した問題（toy の構成 / 本体）、(5) 判定できなかった事項
- **予算**: トークン 25 万、時間 25 分、フレームワーク外の LLM 呼び出し 0
- **反復の上限**: 1。**入れ子の深さ**: 0
- **受け入れ**: 報告を読んだ後、本セッションで `uv run pytest` を再実行して受け入れる

### 動的ワークフローの宣言（第5.10節）: `f2-runtime-and-tests`

- **目的**: F2 の完了条件の第三者判定（7 種の遷移、escalate の 4 解決、参照ランタイムの契約適合、記録再生の同一性、runtime の行カバレッジ 90%）と、adopting.md 初版の十分性の読み（利用者として読んで toy-minimal の harness.py の手順が説明できるか）
- **役割と人数**: 検証役 1（general-purpose サブエージェント。新規起動、fork は使わない）
- **入力**: docs/plan.md（第6節 F2）、`src/htf/contract/CONTRACT.md`、`docs/adopting.md`、`docs/decisions.md`（ADR-011、ADR-012）、`tests/`、`examples/toy-minimal/`、`uv run pytest` と `uv run pytest --cov=htf.runtime --cov-fail-under=90` と検査器 CLI の出力。実装 `src/htf/runtime/` は読んでよいが判定の根拠は実行結果
- **書いてよいパス**: `reports/verification/f2-runtime-and-tests/` のみ
- **完了条件**: `report.md` に (1) F2 完了条件の各項目の判定（満たす / 満たさない / 判定不能）と根拠、(2) 自作の探針（台本を変えて遷移列が変わること、writes 外に書く本体や未宣言の emit が `ContractViolation` になること、再生で LLM 無しに同じ結果になること）、(3) adopting.md だけでは判断できない点の一覧、(4) 発見した問題（ワークフロー定義 / 本体）、(5) 判定できなかった事項
- **予算**: トークン 20 万、時間 20 分、フレームワーク外の LLM 呼び出し 0
- **反復の上限**: 1。**入れ子の深さ**: 0
- **受け入れ**: 報告を読んだ後、本セッションで `uv run pytest` と CLI を再実行して受け入れる

# 1. 骨格
for d in [
    "schema/examples",
    "contract",
    "runtime",
    "testing/spec",
    "testing/harness",
    "testing/oracle",
    "testing/stages",
    "testing/e2e",
    "testing/triage",
    "examples/toy-minimal/stages",
    "examples/toy-minimal/tests",
    "docs",
    "reports",
]:
    check((root / d).is_dir(), f"dir exists: {d}")
check(
    not (root / "examples/software-factory").exists(),
    "examples/software-factory is NOT pre-created (F4 の成果物)",
)
check((root / ".git").is_dir(), "git repository initialized")

# 2. スキーマがメタスキーマに適合
schema_path = root / "schema/workflow.schema.json"
schema = None
try:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    check(True, "schema parses and conforms to Draft 2020-12 metaschema")
except Exception as e:  # noqa: BLE001
    check(False, f"schema metaschema check: {e}")

# 3. 付録 A と一致
plan = (root / "docs/plan.md").read_text(encoding="utf-8")
m = re.search(r"## 付録 A.*?```json\n(.*?)```", plan, re.S)
check(m is not None, "appendix A json block found in plan.md")
if m and schema is not None:
    check(
        json.loads(m.group(1)) == schema,
        "schema/workflow.schema.json equals appendix A (parsed JSON equality)",
    )
    check(
        schema_path.read_text(encoding="utf-8") == m.group(1),
        "schema/workflow.schema.json is byte-identical to appendix A block",
    )

# 4. decisions.md
dec = (root / "docs/decisions.md").read_text(encoding="utf-8")
for i in range(1, 11):
    check(
        re.search(rf"^## ADR-{i:03d}\b", dec, re.M) is not None,
        f"decisions.md has heading ADR-{i:03d}",
    )
sections = re.split(r"^## ADR-", dec, flags=re.M)[1:]
check(len(sections) == 10, f"decisions.md has exactly 10 ADR sections (found {len(sections)})")
for s in sections:
    adr_id = s.split()[0]
    check(re.search(r"^### 決定", s, re.M) is not None, f"ADR-{adr_id} has a 決定 section")
    check(re.search(r"^### 推奨", s, re.M) is not None, f"ADR-{adr_id} has a 推奨 section")
    check(re.search(r"^- 強制点:", s, re.M) is not None, f"ADR-{adr_id} has a 強制点 line")

# 5. progress.md
prog = (root / "docs/progress.md").read_text(encoding="utf-8")
heads = re.findall(r"^## (.+)$", prog, re.M)
check(
    bool(heads) and heads[0].strip() == "次にやること", "progress.md first section is 次にやること"
)
for h in ["完了したこと", "未完了と理由", "発見した問題", "実行した検証とその結果の要旨"]:
    check(re.search(rf"^### {h}", prog, re.M) is not None, f"progress.md has subsection {h}")
for h in ["ワークフロー定義の問題", "フレームワーク本体の不足"]:
    check(
        re.search(rf"^#### {h}", prog, re.M) is not None,
        f"progress.md splits 発見した問題 into {h}",
    )

print()
print(f"{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
```

**F2 完了条件のテスト（実装前、別コミット）**

`tests/test_runtime_{transitions,escalation,recorder,phase_gate,loader}.py`、`tests/test_conformance_reference.py`、台本 8 本（`examples/toy-minimal/tests/fixtures/scenarios/`）、`tests/fixtures/workflows/gate.yaml` を書いた時点:

```text
$ uv run pytest --collect-only -q
E   ModuleNotFoundError: No module named 'htf.contract.conformance'
E   ImportError: cannot import name 'Runner' from 'htf.runtime'
E   ImportError: cannot import name 'WorkflowDefinitionError' from 'htf.runtime'
E   ImportError: cannot import name 'Bindings' from 'htf.runtime'
E   ImportError: cannot import name 'Recorder' from 'htf.runtime'
ERROR tests/test_conformance_reference.py … ERROR tests/test_runtime_transitions.py（6 ファイル）
exit=2
```

### 動的ワークフローの宣言（第5.10節）: `f1-contract-and-spec`

- **目的**: F1 の完了条件の第三者判定（実装した本セッションに判定を任せない。第5.9節）と、toy-minimal の workflow.yaml / elaborate-claim.yaml の MECE 事前レビュー（人間に出す前の必須工程）
- **役割と人数**: 検証役 1（general-purpose サブエージェント。本セッションの文脈を継がない新規起動。fork は使わない）
- **入力**: docs/plan.md（第6節 F1、付録 A / B）、docs/decisions.md、schema/、src/htf/contract/（CONTRACT.md、types.py、interfaces.py）、examples/toy-minimal/、tests/、検査器 CLI（`uv run python -m htf.testing.spec`）と `uv run pytest` の出力。判定は実行した結果を根拠にする（コードを読んで「正しそう」で判定しない）
- **書いてよいパス**: `reports/verification/f1-contract-and-spec/` のみ。保護ファイルと本体コードは書かない
- **完了条件**: `reports/verification/f1-contract-and-spec/report.md` に (1) F1 完了条件の各項目（スキーマのメタスキーマ適合、正例が通り負例が落ちる、検査器の各性質に負例がある、toy-minimal が検査を通る、契約が文書化されている）の判定（満たす / 満たさない / 判定不能）と根拠（実行したコマンドと出力の要旨）、(2) toy-minimal と子の各ステージの end_state について、記述が成果物から観測可能か、互いに排他か、各 end_state に戻り先があるか、優先順が記述にあるかのレビュー、(3) 発見した問題（ワークフロー定義の問題と本体の不足を分ける）、(4) 検証役が判定できなかった事項
- **予算**: トークン 20 万、時間 20 分、フレームワーク外の LLM 呼び出し 0
- **反復の上限**: 1（再実行しない。不足は計画エージェントが判断する）
- **入れ子の深さ**: 0（検証役はサブエージェントを起動しない）
- **受け入れ**: 報告は第5.3節 4 の検証（本セッションでの `uv run pytest` と CLI の再実行）を通してから受け入れる。報告の中だけで成立する判断は残さない
