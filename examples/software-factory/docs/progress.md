# software-factory 進捗

雛形（`docs/harness-plan-template.md`）の形式: 先頭に「次にやること」、日付ごとに「完了したこと」「未完了と理由」「発見した問題（ワークフロー定義 / htf 本体）」「実行した検証とその結果の要旨」。

## 次にやること

- htf の契約の提案 14.2〜14.5（進入回数、子 run の終わり方、`ask` の文脈、状態文書の総量）が実装されたら、本体をそれに合わせる（`sources.py` の進入回数の数え直し、`Implement` の子の終わり方の読み取りを `child_outcomes` に、`Release` の質問の文脈）
- 頻度を見てから決める項目（ADR-014: plan の scope_overlap、release の成果物不備、reads と writes の食い違い、稀な unknown）をトリアージで集める
- 人手ラベル（plan.md 第 4 節）と実分類器の較正（第 5 節）は、LLM を入れる段で

## 2026-10-22（htf の通常セッションによる版 0.2。理由: F4 の人間ゲートで ADR-014「全て推奨で」が決まり、定義の変更に本体を追従させる必要があった）

### 完了したこと

- 定義を版 0.2 に（htf の計画エージェントが保護ファイルを編集）: 子に `check`、親に `integrate`、plan の `design_incomplete`、verify の `coverage_short` / `lint_dirty`、release の `rejected_requirements` / `rejected_quality`、carry の閉包、記述の改訂。整合性検査 0 件
- 完了条件を先に別コミット（`tests/test_sf_v02.py`、台本 26 本、E2E 計画 43 対象、既存テストの改訂。実装前: 51 failed, 54 passed, 3 errors）→ 本体の実装（`Check`、`Integrate`、要旨 report.json と全結果 results.json の分離、approval.json の kind、manifest の base_version、ペルソナ `quality_lead`、指標 28）→ 120 passed（分布・E2E を含む）
- 第三者レビュー 11 件の採否と Codex（GPT-6-Astra）のレビューの採否は htf の ADR-014。plan.md 第 1.1 節に採否を追記
- adopting-gaps.md に処置の状況（全項目処置済み。ADR-014）

### 未完了と理由

- `integrate / merge_failed`、`verify / coverage_short`、`verify / lint_dirty` はこのフィクスチャの世界では誘発できない（scope は重ならず、scope 外・lint・カバレッジ不足は子の check と unit_test が先に止める）。E2E では注入で踏み、本体の論理は `test_sf_v02.py` で手作りの成果物に対して確かめた（ADR-014 14.6.8）
- 人手ラベルと実分類器の較正は前回と同じく未着手

### 発見した問題

#### ワークフロー定義

- 種つきの `ConfusionClassifier` は文書の内容で乱数を決めるので、同じ変種の code / check の文書が台本をまたいで同一になるこのハーネスでは有効標本が一意な文書数（561 件中の一部）に縮む。オラクル検証の許容幅は一意な文書数から取るようにした（`test_sf_oracle.py`）。定義の問題ではないが、コーパスの作り方の注意として記録

#### htf 本体

- なし（14.2〜14.5 の実装待ち）

### 実行した検証とその結果の要旨

- `uv run python -m htf.testing.spec examples/software-factory/workflow.yaml --metrics examples/software-factory/metrics/manifest.json` → 0 finding(s)
- `uv run pytest -o addopts="" -q examples/software-factory/tests` → 120 passed（約 150 秒。分布 markov N = 200 / split N = 150、E2E 43 対象 誘発 39・注入 4、マルコフ合成 markov は許容差内・split は外れる、独立性 markov 検出なし・split 検出）
- 分布の実測は plan.md 第 6 節・第 8 節

## 2026-10-22

### 完了したこと

- 読んでよい範囲（`docs/adopting.md`、`docs/harness-plan-template.md`、`examples/toy-minimal/`、公開 API の文書）を読んだ。公開 API の文書として読んだもの: `src/htf/contract/CONTRACT.md`、`schema/workflow.schema.json`、公開モジュールの docstring とシグネチャ（`inspect` で出力。関数本体は読んでいない）。フレームワーク本体の実装、`docs/plan.md`・`progress.md`・`decisions.md`、リポジトリ直下の `tests/` は開いていない（プローブとテストの失敗のトレースバックに実装のファイル名と行が出たのは付随的）
- ディレクトリ骨格（雛形第 0 節）: `workflow.yaml`、`stages/`、`metrics/`、`user/`、`fixtures/`、`tests/`、`docs/`
- 公開 API の振る舞いを黒箱で確かめるプローブ（スクラッチ領域。リポジトリには置かない）:
  - `subworkflow.pass` の鍵が子 run の起動時に memory に無いと `ContractViolation`（carry でしか来ない鍵は初回進入で落ちる。整合性検査は通る）→ G-04
  - 一部だけ即答して残りで中断する UserIO は、再開で累積回答が最初の質問から当てられてずれる → G-05
  - 進入回数はステージごとに run 全体で数え、2 回目以降は carry の有無によらず `reentry` → G-11
  - 子を持つステージの本体は、子 run が stuck でも走る。全ての子 run が goal で親の指標が不成立なら `unknown(quantitative)`
- 実ツールのスパイク（`toolchain.py`）: fixtures のコードベース（textkit）に変更の変種を当て、ビルド（compile）・lint（ruff）・テスト（pytest + coverage）を子プロセスで走らせる。3 機能 × 8〜9 変種の全てで意図どおりの結果（例: slug/regression は単体テストが通りスイート全体で test_normalize が落ちる）。作業ディレクトリへの書き込みなし。変更のフィクスチャは `.py.txt`（G-07）
- ワークフロー定義（`workflow.yaml` 5 フェーズ 8 ステージ、`implement-task.yaml` 子 2 ステージ）。整合性検査 0 件
- 指標 24 個（`metrics/`）、偽本体 10 個（`stages/`）、結果の供給元（台本 / 種つきの分布）、ペルソナ 4 つ（`user/`、`fixtures/personas/`）、成果物のフィクスチャ、束縛（`harness.py`）
- 台本 21 本（`fixtures/scenarios/`、規則は README）、確率的な構成 2 つ（`fixtures/profiles/`）、expectations 3 つ、E2E 計画（31 対象）
- テスト 92 件（`tests/`）: 整合性検査（`test_sf_spec.py`）、実ツールの指標（`test_sf_metrics.py`）、契約適合（`test_sf_conformance.py`）、遷移の決定論（`test_sf_transitions.py`）、分布と独立性（`test_sf_distribution.py`）、E2E とマルコフ合成（`test_sf_e2e.py`）、オラクル（`test_sf_oracle.py`）、トリアージの一周（`test_sf_triage.py`）
- 計画書（`docs/plan.md`）を雛形の節に沿って埋めた。adopting-gaps.md に G-01〜G-23
- 第三者レビュー: 同じ読取制限を課したサブエージェントに、定義（2 ファイル）と htf の利用者向け文書だけを読ませた。指摘 11 件（高 1・中 7・低 3）を plan.md 第 1.1 節に評価と提案つきで記録。分類体系の変更になるので定義は変えていない（YAML のコメント一か所だけ直した）。指摘から htf の文書の不足を 2 件（G-22 二段のロールバックと carry、G-23 最初のステージは unknown しか持てない）

### 未完了と理由

- 人手ラベル: 人間のラベラーがいない（雛形の止まる条件）。テストでは偽本体の印を正解の代わりに使った
- 実分類器の検証: このハーネスは LLM を使わない（課題の条件）。偽の分類器でランナーを通しただけ
- ハーネスのテストは CI で走らない: ルートの pyproject の `testpaths` と CI はフレームワーク側のファイル（G-03）
- 第三者レビューの指摘への対応: 全て記述か構造の変更を伴うので人間の承認待ち（雛形第 1 節の止まる条件）

### 発見した問題

- ワークフロー定義: 第三者レビューの重大度「高」= 子 code のビルド・lint・範囲の失敗が全て unknown（人間へ）になる（G-23）。二段続けて戻ると最初の carry が消える経路がある（G-22。台本では踏んでいない）。当初 verify の regression を implement に戻し `pass` で子に渡す設計にしたが、runtime が初回進入で落とす（G-04）ので戻り先を plan にした。人間の RollbackTo の記録の形を読み違えた（G-17）。lint_unknown_continue は、統合が単体テストを通ったタスクだけなので verify が criteria_unmet を出す（期待を直した）
- htf 本体（提案は adopting-gaps.md）: G-04（`pass` と carry）、G-05（中断と累積回答）、G-06（ステージ id の鍵）、G-11（進入回数）、G-15（software-factory の存在で落ちるガードのテスト）、G-18（子の終わり方が本体に渡らない）、G-19（UserIO の文脈）ほか

### 実行した検証とその結果の要旨

- `uv run python -m htf.testing.spec examples/software-factory/workflow.yaml --metrics examples/software-factory/metrics/manifest.json` → `0 finding(s)`、終了コード 0
- `uv run pytest examples/software-factory/tests` → 92 passed（約 1 分 45 秒）。常時の段 `-m "not distribution and not e2e"` → 80 passed、12 deselected（約 38 秒）
  - 契約適合: `ConformanceSuite` の 15 件が通る
  - 決定論: 台本 21 本の遷移列・終了状態・ゲートが期待どおり。7 種の遷移を全て観測。escalate の 4 解決（abort / rerun / continue_as_goal / rollback_to）。記録 → 再生で digest 一致（5 台本、中断再開を含む）。フェーズゲートの不成立（注入で plan を goal にすると design のゲートが成果物で落ちる）と、人間が通した記録
  - 分布（markov、N = 200、種 100）: expectations が通る。completed 0.605。code goal first 0.920 → reentry 1.0、unit_test goal first 0.740 → reentry 0.872（carry つき再進入で分布が変わる）。ずらした expectations は unit_test first goal 0.740 < 0.9 と completed 0.605 < 0.8 で落ちる。split（N = 150、種 200）: expectations が通る（aborted 1.0）
  - 独立性（unit_test / tests_failing）: markov で群 8・p = 0.507（検出なし）、split で群 7・p = 0.005（検出）。review / changes_requested ほか 3 クラスは carry が代表を識別せず検証不能（記録）
  - E2E: 31 対象、誘発 29・注入 2、カバレッジ 1.0。マルコフ合成: markov の予測 completed 0.612 と実測 0.605（差 0.007、許容差 0.1）、split の予測 0.363 と実測 0.0（差 0.363）で外れる
  - オラクル: 状態文書 200 件以上のコーパス。MarkerClassifier κ = 1.0。ConfusionClassifier（0.8 / 0.2）の κ が理論値の ±0.1、種つきで再実行一致 1.0、種なしで 1.0 未満、calibrated で ECE < 0.1
  - トリアージ: unknown を出す 7 台本 → 積む（子 run の項目を含む）→ ラベル（intake は却下）→ コーパスに書き出し → オラクル検証 → 改訂候補（確信度が閾値未満の verify と unit_test）。定義ファイルは変わらない。注入の判定は既定で積まない
- `uv run ruff check .` → All checks passed。`uv run ruff format --check .` → 72 files already formatted
- `uv run pytest`（リポジトリ直下。CI の常時の段）→ **1 failed, 135 passed**。落ちるのは `tests/test_repo_layout.py::test_software_factory_is_not_pre_created`（`examples/software-factory` が存在しないことを確かめるガード。G-15）。この作業の前は通っていた
- 最終状態での再実行（2026-10-22 10:43、整形・コメント修正・第三者レビューの後）: `uv run pytest examples/software-factory/tests` → 92 passed（1 分 45 秒）、`ruff check .` / `ruff format --check .` → 通る、`git diff --stat` → 空（フレームワーク側の追跡ファイルに変更なし）、ハーネスの外に新規ファイルなし
- 第三者レビューのサブエージェントの読取制限の遵守: 記録（トランスクリプト）の tool_use を grep で確認。Read 16 回のみ（adopting.md、雛形、CONTRACT.md、スキーマ、toy-minimal の定義 2 つ、レビュー対象の定義 2 つ）。書き込み・シェル実行なし
