# software-factory 計画書

`docs/harness-plan-template.md`（最低限版）の節に沿って埋めたもの。各節の「完了条件」は実行できる検査で書き、結果を併記する。雛形と adopting.md で判断できなかったことは `adopting-gaps.md`（G-xx）。

## 0. 前提

- ハーネス名: software-factory（`examples/software-factory/`）
- 目的: htf の上に、ソフトウェア開発のワークフロー型ハーネスを作る実例。ステージ本体は全て偽物で LLM を使わない。実装と単体テストのステージだけは、fixtures の小さなコードベース（textkit）に対して実際にビルド・lint・テスト・カバレッジを走らせ、指標は本物の値を返す
- ワークフローの概要（`workflow.yaml` 5 フェーズ 8 ステージ + 子 `implement-task.yaml` 2 ステージ）

| フェーズ | ステージ | 成果物（writes） | end_state → 戻り先（carry） |
| --- | --- | --- | --- |
| discovery | intake（ユーザー待ち） | intake/ | — |
| | analyze | requirements.json | ambiguous → intake（open_questions） |
| design | design | design.json | requirements_conflict → analyze（conflicts）※境界越え |
| | plan（タスク分割） | tasks.json | design_gap → design（uncovered_components） |
| build | implement（子をタスクごとに起動） | tasks/、codebase/、merge.json | tasks_unfinished → plan（unfinished_tasks）※境界越え |
| （子） | code | repo/、code.json | — |
| （子） | unit_test | unit/ | tests_failing → code（test_failures）、coverage_low → code（coverage_gaps） |
| assure | verify | verification/ | regression → plan（regressions）※、criteria_unmet → plan（unmet_criteria）※ |
| | review | review.json | design_flaw → design（design_issues）※、changes_requested → plan（review_comments）※ |
| release | release（ユーザー待ち） | release/ | rejected → analyze（rejection_feedback）※ |

  全ステージに unknown（人間へ）。※はフェーズ境界を越えるロールバック。
- ユーザー待ち: intake（要求の聞き取り 5 問と、analyze から carry された質問）、release（リリースの承認）
- 動的に数が決まる下位作業: implement が tasks（plan の変種で 2 か 3）の要素ごとに子 run を起動する。子の集約は「子の unknown → 親 unknown（上に置く）」「unit_test の tests_failing / coverage_low で stuck → tasks_unfinished」
- 固定の設計判断（adopting.md 第 1・2 節）: 三層（goal / end_state / unknown）、評価順序（goal 指標 → goal 定性 → end_state → unknown）、記述が分類の全て（偽の分類器 MarkerClassifier は成果物の印を読むだけ。印は本体が本物の結果から書く）、ロールバックは restore + overlay（carry）、定義が唯一の情報源（本体が使う基準値も定義から読む: unit_test のカバレッジ基準 0.9 は `harness.unit_coverage_min`）
- 完了条件: ディレクトリ骨格がある → **済**（`workflow.yaml`、`implement-task.yaml`、`stages/`、`metrics/`、`user/`、`fixtures/`、`tests/`、`docs/`。実ツールと組み立ては `toolchain.py`、束縛は `harness.py`）

## 1. ワークフロー定義

- 成果物の形（本体と指標の取り決め）
  - `intake/answers.json`: role / summary / features / constraints / acceptance、asked（carry された質問の id）、clarifications
  - `requirements.json`: requirements（id、title、criteria[{id, text, test（nodeid）}]、deferred、agreed、note）、open_questions[{id, question, blocks}]、decisions
  - `design.json`: requirements（見送りでない要件の id）、components[{id, title, module, satisfies}]、conflicts[{between, reason}]、revisions
  - `tasks.json`: design_components、tasks[{id, title, components, features, scope, tests, notes}]、uncovered_components
  - 子 `code.json`: variant、changed_paths、out_of_scope、build、lint。`unit/report.json`: result（正規化した pytest とカバレッジの出力）、failed、coverage、coverage_gaps
  - `merge.json`: merged、unfinished、conflicts、changed_paths。`verification/report.json`: build、lint、result、coverage、criteria[{id, test, status}]、failed、unmet
  - `review.json`: comments[{target, severity, kind, text}]。`release/manifest.json`（version、files のダイジェスト、digest、requirements）、`CHANGELOG.md`、`approval.json`
  - どの JSON も先頭に印 `outcome`（状態文書は 1 ファイル 4000 文字で切られる。G-08）
- 指標 24 個（`metrics/manifest.json`）。code の build_passed / lint_clean / changed_paths_in_scope はスナップショットの repo/ に自分でツールを走らせる。unit_test / verify の指標は本体が走らせた pytest とカバレッジの正規化した出力から計算する
- 分類体系の版: `workflow.version: "0.1"`（v0、仮説）
- 完了条件:
  - `uv run python -m htf.testing.spec examples/software-factory/workflow.yaml --metrics examples/software-factory/metrics/manifest.json` → **0 finding(s)**（`tests/test_sf_spec.py`）
  - 実装していない第三者のレビュー: 同じ読取制限（adopting.md・雛形・CONTRACT・スキーマ・toy-minimal の定義と、レビュー対象の 2 ファイルだけ）を課したサブエージェントに読ませた。結果と対応は第 1.1 節
- 止まる条件: end_state の追加・分割・統合・意味変更は人間の承認。第三者レビューの指摘のうちこれに当たるものは提案として残し、定義は変えていない

### 1.1 第三者レビューの結果と対応

レビュアー: 同じ読取制限を課したサブエージェント（定義 2 ファイルと htf の利用者向け文書だけを読み、実装は読んでいない。記録の tool_use を grep で確かめた: Read 16 回、全て許可した範囲、書き込みなし）。指摘は全て、記述か構造の変更（分類体系の変更）を伴うので、**定義は変えず提案として残す**（人間の承認待ち）。変えたのは分類器に渡らない YAML のコメント一か所（implement では end_state の記述も分類器に渡らない旨）だけ。「評価」はハーネス作者（この作業）の見立て。

| 重大度 | 対象 | 指摘 | 評価 | 提案 |
| --- | --- | --- | --- | --- |
| 高 | 子 code | build・lint・scope の失敗が全て unknown → 子 unknown → 集約で人間へ。code は子の最初のステージで戻り先を持てない | 同意。作者も把握していたが計画書に書いていなかった（構造上の制約は G-23） | code の後に確認ステージ（例: check）を置き、build_failed / lint_failed / out_of_scope → code（carry: 違反の一覧）を作る。指標 build_passed / lint_clean / changed_paths_in_scope は check に移す |
| 中 | verify | 全テスト通過でもカバレッジ不足・lint 違反・受け入れテストの skip / xfail は unknown | 同意（現在のフィクスチャでは起きない: 子が scope のカバレッジ 0.9 と lint を見ており、skip は無い） | coverage_short（→ plan）を足すか、goal の基準と子の基準を揃える。criteria_unmet を「受け入れテストが無いか passed でない」に広げる |
| 中 | plan | scope の重なり・テストファイルの無いタスクは unknown。4 本の carry の反映が goal に無い | 同意 | end_state scope_overlap（→ design か自分の前段）を検討。goal 定性に「carry された差し戻しが該当タスクの notes にある」を足す（指標は memory と tasks.json で計算できる） |
| 中 | review | パスを挙げられない code の指摘、design.json に無いコンポーネントの欠落、kind の値が未定義 | 同意 | kind の取りうる値を記述に書く。「未実装の機能」の指摘を changes_requested に含める記述にする |
| 中 | design / analyze | 要件・機能が落ちても goal が成立する（design は自分の写しの requirements を見る） | 同意。指標が他のステージの成果物を見られない（G-12）ための写しが、定性まで写しに依っている | 定性は reads（requirements.json、intake/answers.json）を基準に書く。指標は写しのまま、写しと元の一致を定性で問う |
| 中 | 横断 | ロールバックで戻り先の前回の成果物が消え、二段続けて戻ると最初の carry が memory から消える（release → analyze → intake → analyze で rejection_feedback など） | 同意。runtime の規則どおりの振る舞いだが、この定義では起きうる（台本では踏んでいない） | 二段目の戻り先にも同じ鍵を carry する、または戻り先を一段にする。htf への文書の提案は G-22 |
| 中 | release | rejected → analyze は「見送りへの合意」しか扱わない | 同意（ペルソナの拒否理由が見送りだけなので台本では足りている） | 拒否理由の種類（見送り / 品質 / 機能の追加）を approval.json に書かせ、戻り先を分ける（品質なら review か plan） |
| 中 | verify ほか | report.json が大きく、4000 文字の切り詰めで failed / unmet が状態文書から落ちうる | 同意（印は先頭に置いたが、要旨は後ろ。G-08） | 要旨（failed、unmet、カバレッジ）を先頭に置き、全テストの結果は別ファイルにする |
| 低 | 子 unit_test | goal 定性の「基準以上」に数値が無い。テストが一件も集まらない時に coverage_low の記述が当たりうる | 同意（偽本体はテスト 0 件を unknown にしている） | 定性に 0.9 を書く。tests_failing の記述に「テストが一件も集まらない」を含める |
| 低 | 子 code / release | 「変更を含む」・版・ダイジェストが分類器から判定できない | 一部同意（code.json に changed_paths はある） | code の goal に「changed_paths が空でない」の指標を足す。release は base の版を manifest に書く |
| 低 | design / analyze / implement | 単独の要件の実現不能、design_gap の理由、要件 id を持てない質問、統合の指標だけ不成立の時の unknown | 同意（いずれも稀） | 頻度を見てから（トリアージで集める） |

この表の提案を採るかどうかは人間のレビューで決める。採る場合は `workflow.version` を上げ、台本・E2E 計画・expectations を合わせて直す。

## 2. 最初の実ステージの選択

- 選択: 子の code と unit_test（このハーネスでは LLM を使わないので、「本物」は実ツールを走らせることを指す。雛形の想定（LLM で本物にする）とは違う。G-13）
- 理由: 成果物（repo/ とテストの結果）が観測しやすく、指標（ビルド通過・テスト通過・カバレッジ・lint・変更パスの範囲）が決定論的に実装でき、end_state が少ない（unit_test の 2 つ）
- 実ツールの扱い（`toolchain.py`）: ビルド = 全 .py の compile()、lint = ruff（設定ファイルを読まない固定の規則 E,F,W,I,B）、テスト = coverage run -m pytest（子プロセス）。作業ディレクトリには書かない（バイトコード・キャッシュ・カバレッジのデータは一時ディレクトリ）。出力は時刻と絶対パスを落として正規化。内容のハッシュでメモ化（G-09、G-10）
- 完了条件:
  - 指標がレジストリにある → **済**。変種ごとに本物の値を返すことを `tests/test_sf_metrics.py` で確かめる（9 変種 × 6 指標、ツールが作業ディレクトリに書かないこと）
  - 偽本体の台本で 7 種の遷移が通る → **済**（`tests/test_sf_transitions.py::test_all_seven_transition_kinds_are_observed`）
  - LLM 呼び出しの記録: 本体は LLM を呼ばない。recorder は分類器とユーザー回答を記録し、記録 → 再生でスナップショットの digest が一致する（5 台本。中断再開を含む）

## 3. フィクスチャとコーパス

- コードベース: `fixtures/codebase/base/`（textkit 0.1.0: normalize_whitespace とそのテスト）と、機能（slug / stats / truncate）ごとの変更の変種 `fixtures/codebase/changes/<機能>/<変種>/`（`.py.txt`。correct の上に重ねる。G-07）。変種: correct、failing、failing_edge、low_coverage、regression（slug のみ）、missing_test、lint、broken、out_of_scope
- 成果物: `fixtures/artifacts/`（要件の目録と依頼者ごとの組、コンポーネントの目録と衝突、タスクの分け方、レビューの変種）
- ペルソナ 4 つ（`fixtures/personas/`、`user/`）: product_owner（過不足なく答える）、domain_expert（衝突する要求を持ち込み、合意なしの見送りを承認しない）、end_user（曖昧に答え、確かめる質問に具体的に答える）、busy_sponsor（リリースの承認だけ保留 → 中断）。中断するペルソナはそのステージの最初の質問から保留する（G-05）
- 台本 21 本（`fixtures/scenarios/`、規則は README）: 全 end_state、7 種の遷移、escalate の 4 解決、中断と再開（DeferringUserIO と busy_sponsor）
- 確率的偽本体の構成（`fixtures/profiles/`）: markov（再進入で分布が変わる: code は carry つき再進入で correct が 0.62 → 0.85）、split（T1 の code だけ持続して failing_edge）
- 完了条件:
  - E2E 計画が親子の全 (stage, class) を誘発か注入で踏む → **済**（31 対象、誘発 29・注入 2、カバレッジ 1.0。`tests/test_sf_e2e.py`）
  - 契約適合テストを通す → **済**（`tests/test_sf_conformance.py`。ハーネスと同じ組み込み方 `harness.conformance_runtime` で参照ランタイムを作る）

## 4. 人手ラベル

- コーパスの作り方: (a) 台本の run の評価記録（`tests/test_sf_oracle.py`、状態文書 200 件以上）、(b) トリアージ待ち行列から（`tests/test_sf_triage.py`）。形式は `htf.testing.oracle` の JSONL
- ラベラー: **人間はまだいない**。テストでは、偽本体が本物の結果から書いた印をラベラーの代わりに使う（`sf_support.marker_truth`。low_confidence は goal とみなす）。実コーパスの人手ラベルは雛形の止まる条件（人手ラベルが要る）に当たるので、ここで止まっている
- 件数の目安（提案）: ステージ × クラスごとに 20 件以上（31 対象 → 600 件程度）。トリアージで積まれたものを優先する
- 完了条件: ラベル付きコーパスがある → **一部**（偽の世界の正解で作ったものだけ）。`human_approval` に当たる指標はこのハーネスに無い（release の承認はユーザー入出力で取る）

## 5. 分類器検証

- 分類器の後ろ側: このハーネスでは偽の分類器だけ（LLM を使わない）。実分類器は htf の ADR-006 の後（読めない。G-01）
- 実施した検証（`tests/test_sf_oracle.py`）:
  - MarkerClassifier: κ = 1.0、正解率 1.0、再実行一致 1.0、ECE > 0（low_confidence の項目は正しいが確信度 0.1）
  - ConfusionClassifier（正しいクラス 0.8 / unknown 0.2 の混同行列）: κ が理論値（`expected_kappa`）の ±0.1、正解率 0.8 ± 0.08。種つきで再実行一致 1.0、種なしで 1.0 未満。`confidence="calibrated"` で ECE < 0.1
- 閾値: 確信度の閾値は htf の既定 0.5（仮置き）のまま。偽の分類器は 1.0 か 0.1 しか返さないので較正の材料にならない
- 完了条件: オラクル検証レポート → **偽の分類器についてのみ済**。実分類器の較正は未着手

## 6. 分布テストと往復

- expectations（`tests/expectations/`）: markov（N = 200、種 100）、markov_shifted（落ちるべきもの）、split（N = 150、種 200）。区間の根拠は各ファイルの冒頭（構成から計算した理論値 ± 約 3 標準誤差）
- 実測（markov、N = 200）: completed 0.605。code の goal first 0.920 → reentry 1.0、unit_test の goal first 0.740 → reentry 0.872、tests_failing 0.180 → 0.083（carry つき再進入で分布が変わる）
- 記述の改訂の往復: 改訂のたびに整合性検査（`test_sf_spec.py`）と台本（`test_sf_transitions.py`）を回す。分類体系の変更は人間の承認
- 完了条件: expectations が通る → **済**。ずらした expectations が落ちる → **済**（unit_test first goal 0.740 < 0.9、completed 0.605 < 0.8）

## 7. 独立性

- 検証するクラスと代表の鍵: unit_test / tests_failing、既定の鍵（戻り先へ運ぶ carry = 失敗したテストの nodeid の一覧のハッシュ）。代表は「どのタスクのどのテストが落ちたか」を識別する
- 結果: markov で群 8・p = 0.507（検出なし）、split で群 7・p = 0.005（検出。T1 の test_empty の群だけ再進入でも必ず落ちる）。p 値の閾値は htf の既定 0.05（仮置き）
- 既定の鍵で検証できないクラス（carry が代表を識別しない。群が一つ）: review / changes_requested、verify / regression、design / requirements_conflict（いずれも fixtures の一変種が carry になる）。検出されなかったのではなく検証不能として記録する（`test_sf_distribution.py::test_class_whose_carry_does_not_identify_a_representative_is_not_verifiable`）。検証するなら、指摘のカテゴリや失敗したテストのモジュールを代表の鍵として `key=` に与える
- 完了条件: クラス内で下流の分布が揃う → markov で**済**。split の検出はこの構成の意図どおり（クラスの粒度を変える提案: tests_failing を「主要な振る舞いの誤り」と「端の場合の誤り」に分けるか、タスクごとの持続性を carry に記録する。分類体系の変更なので人間の承認待ち）

## 8. 残りのステージと E2E

- 残りのステージは全て偽本体のまま（このハーネスの範囲）。本物にする順の提案: review（LLM。成果物が JSON で観測しやすい）→ design / plan → analyze → intake（実ユーザー）
- E2E 計画（`tests/e2e/plan.yaml`）: 誘発 29、注入 2（release / unknown、unit_test / unknown）。carry を運ぶ end_state は全て誘発
- マルコフ合成（`tests/test_sf_e2e.py`、子 run 数の分布は `samples=` から。2 タスク 71 回 / 3 タスク 160 回）: markov の予測 completed 0.612 と実測 0.605（差 0.007、許容差 0.1）。split の予測 completed 0.363 と実測 0.0（差 0.363）で外れる
- 完了条件: (stage, class) のカバレッジ 100% → **済**。マルコフ予測と実測が許容差内 → **済**（markov）

## 9. 維持ループ（提案）

- トリアージ: 実 LLM を入れたら run ごとに `TriageQueue.enqueue(low_confidence=閾値)`、週一回ラベル付け。記述の改訂候補は「選択とラベルの食い違い」と「選択は正しいが確信度が閾値未満」（`test_sf_triage.py` の一周で出している）。改訂は提案止まり
- 分類体系の版（`workflow.version`）とハーネスの版を同じ変更で上げる
- CI の段階: 整合性検査・決定論テスト・契約適合・オラクル・トリアージは常時（80 件、約 40 秒）、分布と E2E は人間の許可時（12 件、約 75 秒）。ただし現在のリポジトリの CI はハーネスのテストを走らせない（G-03）
- 完了条件: 維持の手順書 → 未（htf の `docs/maintenance.md` が F5）

## 付録: この作業で当たった止まる条件

- 人手ラベル（第 4 節）: 偽の正解で代用し、実ラベルは止めている
- フレームワーク側のテスト `tests/test_repo_layout.py::test_software_factory_is_not_pre_created` が、このディレクトリができたことで落ちる（G-15）。フレームワーク本体側のファイルなので直していない
- 分類体系の変更（第 1.1 節、第 7 節の提案）: 人間の承認待ち
