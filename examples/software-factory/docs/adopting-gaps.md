# adopting-gaps.md — adopting.md と雛形だけでは判断できなかったこと

software-factory を htf の上に作る時に、`docs/adopting.md`、`docs/harness-plan-template.md`、`examples/toy-minimal/`、公開 API の文書（`CONTRACT.md`、`schema/workflow.schema.json`、公開モジュールの docstring とシグネチャ）だけでは決められなかったこと、足りなかったこと、回避したくなったことの記録。htf 本体は直していない。ハーネスの中で htf の不足を埋める回避策も入れていない（入れたくなったものは「回避したくなったこと」として書き、取った設計を併記する）。

各項目: **何が起きたか / どこで判断に困ったか** → **取った対応**（ハーネス側の設計判断。htf への提案があれば併記）。分類: [文書] 手引き・雛形の不足や不整合、[機能] htf に無い・合わない機能、[回避] 回避したくなったこと。

## 処置の状況（htf の計画エージェントが記入。htf の `docs/decisions.md` ADR-014、2026-10-22 人間が承認）

全項目処置済み。内訳は ADR-014 の「処置の一覧」。要約:

| 処置 | 項目 |
| --- | --- |
| htf 本体を直した（toy-minimal の再現テストを先に） | G-04（`pass` の鍵が無ければ渡さず起動）、G-05（即答した回答も累積）、G-06（親子のステージ id の重複を検査）、G-08（`max_file_chars`）、G-16（計画の `overrides`） |
| 設定 / CI | G-07（ruff の fixtures 除外）、G-03（CI に software-factory のテスト）、G-15（ガードのテストを外した） |
| 文書（adopting.md と雛形） | G-01、G-02、G-09、G-10、G-12、G-13、G-17、G-20、G-21、G-22、G-23 |
| 文書 + 契約への提案（承認済み。実装済み） | G-11（14.2 `StageContext.entry` / `reentry`）、G-18（14.3 `child_outcomes`）、G-19（14.4 `ask(..., context=)`）、G-04 の文言（14.1） |
| 解消しない（理由を記録） | G-14（`--metrics-module` はパッケージ用。ハイフン名のディレクトリではマニフェスト） |

## G-01 [文書] 読めない文書への参照

- adopting.md 3.1 は workflow.yaml の書き方の例として「計画書付録 B」を挙げ、3.6・6 節は ADR-006 / 012 / 013 を根拠として挙げる。これらは `docs/plan.md` と `docs/decisions.md` にあり、利用者の読取範囲（adopting.md・雛形・toy-minimal・公開 API）の外。閾値（分類器 0.5、分布の区間、p 値、許容差）が「仮置き」である根拠や、どこまで変えてよいかが分からない
- 対応: 書き方は toy-minimal とスキーマから推した。閾値は htf の既定を使い、ハーネス側で決めた値（カバレッジ基準など）は理由をハーネスの計画書に書いた
- 提案: 利用者が読む範囲に、付録 B の要点と、仮置きの閾値の一覧（値・意味・変えてよいか）を移す

## G-02 [文書] toy-minimal のテストが例の中に無い

- adopting.md 3.7 は「toy-minimal の `tests/conftest.py`」、3.9 は「`tests/test_runtime_*.py` が実例」と書くが、`examples/toy-minimal/tests/` には conftest もテストコードも無い（台本・計画・expectations の YAML だけ）。テストコードはリポジトリ直下の `tests/` にあり、これはフレームワーク本体側で読取範囲の外
- 困ったこと: `load_example_package` を conftest でどう使うか、分布テスト・E2E・オラクル・トリアージのランナーをどう組み合わせるか（`run_many` の工場、`run_plan` の工場の引数、`TriageQueue` の一周）を、docstring と YAML から推すしかなかった
- 対応: docstring とシグネチャから書いた（`examples/software-factory/tests/`）
- 提案: toy-minimal のテストを `examples/toy-minimal/tests/` に移すか、各ランナーの最小の呼び出し例を adopting.md に載せる

## G-03 [文書] ハーネスのテストの置き場所と CI への組み込み

- リポジトリの `pyproject.toml` は `testpaths = ["tests"]`、CI は `uv run pytest`。ハーネスの `tests/` は CI で走らない。雛形は骨格に `tests/` を挙げるが、どう走らせるか（testpaths への追加、別 job、マーカー）は書いていない。pyproject と CI はフレームワーク側のファイルなので触っていない
- 対応: `uv run pytest examples/software-factory/tests` で明示的に走らせる。マーカー `distribution` / `e2e` はルートの pyproject に登録済みのものを使う
- 提案: 例のハーネスのテストを CI に載せる方針（雛形第 9 節の CI の段階）を adopting.md に書く

## G-04 [機能][回避] `subworkflow.pass` に carry でしか来ない鍵を書けない

- 検証の結果を子ワークフローへ渡したかった（verify → implement に carry `regressions` を戻し、`pass: [regressions]` で各子 run に渡す）。整合性検査は通る（`memory_in_source` は carry を出所として認める）が、初回進入では鍵が memory に無いので、参照ランタイムが子 run の起動時に `ContractViolation: subworkflow.pass の鍵 'regressions' が memory に無い` を投げる（黒箱のプローブで確認）
- adopting.md 第 4 節も CONTRACT 第 7 節も「`pass` の鍵は memory に必ずある」と書いていない。検査器と runtime で受け入れる定義が食い違っている
- 回避したくなったこと: 前段のステージ（plan）に空の `regressions` を emit させて、初回でも鍵がある状態にする
- 取った対応: 回避はしない。regression と criteria_unmet の戻り先を implement ではなく plan にし、plan が carry の内容を該当タスクの `notes` に書く（子は `task` の中身として受け取る）。フェーズ境界越え（assure → design）のロールバックとしては成立している
- 提案: (a) 検査器で「`pass` の鍵は前方の `memory_out` か `inputs` から来る」を検査する、または (b) runtime が無い鍵を子の memory に入れない（子の `memory_in` の任意の鍵として扱う）。どちらにするかを契約に書く

## G-05 [文書][機能] 一部だけ即答して残りで中断する UserIO は、再開で回答がずれる

- adopting.md 3.5 は「累積した回答は ask の順序で返る（質問文は照合しない）」と書く。黒箱で確かめると、再開時の再実行では、そのステージの**最初の ask から**累積回答を順に返し、尽きたら束縛した UserIO に尋ねる。束縛した UserIO が自分で即答した回答は累積列に入らない
- 結果: 1 問目にペルソナが即答し 2 問目で中断した場合、`resume(a2)` の後の再実行で 1 問目に a2 が返り、2 問目で再び中断する（回答が一つずつずれ、終わらない）
- 困ったこと: ペルソナのシミュレータ（雛形第 3 節）を「知っていることには答え、知らないことで中断する」形で書くのが自然だが、それは使えない
- 取った対応: 中断するペルソナは、そのステージの最初の質問から答えない形にした（busy_sponsor: 要求の聞き取りには即答し、リリースの承認だけを保留する。release の質問は一つ）。要求の聞き取りでの中断は `DeferringUserIO` で踏む
- 提案: 累積列に「束縛した UserIO が即答した回答」も入れる（記録再生と同じ扱い）か、adopting.md に「中断する UserIO はそのステージの全ての質問を保留する」と制約として書く

## G-06 [文書][機能] 分布・遷移行列の鍵がステージ id だけ（親子で id を重ねられない）

- `Tally.by_stage` と `transition_matrix` の鍵は (stage, first | reentry)、expectations も `stages.<stage>` で、workflow 名を含まない。親と子に同じ id のステージがあると数が混ざる（子の実装ステージを `implement` と名付けかけた。親のステージも `implement`）。adopting.md と検査器が求めるのは親子の `workflow.name` の重複禁止だけ
- 取った対応: 親は `implement`、子は `code` / `unit_test` と、id を親子で重ねない（`test_sf_spec.py::test_stage_ids_are_unique_across_parent_and_child` で固定）
- 提案: 鍵に workflow 名を入れるか、検査器で「子を持つ定義では親子のステージ id が重ならない」を検査する

## G-07 [文書][回避] リポジトリ全体の ruff と、意図的に壊れたフィクスチャ

- CI は `uv run ruff check .` と `ruff format --check .` をリポジトリ全体にかける。実装ステージのフィクスチャには、lint 違反（未使用の import）や構文エラーの変更が要る（それを本物の指標が見つけることが目的）。`.py` で置くと CI が落ちる
- 回避したくなったこと: ルートの pyproject の `extend-exclude` に fixtures を足す（フレームワーク側のファイル）
- 取った対応: 変更のフィクスチャを `.py.txt` で置き、適用時に `.txt` を外す（`toolchain.materialize`）。base のコードベースは正しいコードなので `.py` のまま（ルートの ruff を通る）
- 提案: adopting.md に「ハーネスのフィクスチャのうちツールの入力になる壊れたコードの置き方」を書くか、`examples/*/fixtures` を ruff の対象から外す方針を決める

## G-08 [文書] 状態文書の 4000 文字の切り詰めと大きな成果物

- 状態文書は 1 ファイル 4000 文字で切られる（adopting.md 3.6）。テストの結果のような大きな成果物では、末尾に置いた情報（印や要旨）が分類器に届かない。偽の分類器では印が切れると unknown になり、実 LLM でも結論が読めなくなる
- 取った対応: JSON の成果物は印（outcome）を先頭に置く（`stages._write`）。テストの結果は正規化して小さくする
- 提案: 切り詰めの長さを変えられるか、成果物の設計の指針（要旨を先頭に、詳細は別ファイル）を adopting.md に書く

## G-09 [文書] 本体の中で実ツールを走らせる時の書き込み検出

- adopting.md 3.3 は「外部ツールを呼ぶ指標はハーネス側に閉じる。本体がツールを走らせて結果を成果物に書く」と書くが、参照ランタイムは writes 外の変更を検出するので、ツールの副産物（`__pycache__`、`.pytest_cache`、`.coverage`、ruff のキャッシュ）が `ContractViolation` になりうる。unit_test は repo/ を reads にしか持たないので、repo/ の中でテストを走らせると副産物が writes 外になる
- 取った対応: 子プロセスの環境で `PYTHONDONTWRITEBYTECODE`、`PYTHONPYCACHEPREFIX`、`-p no:cacheprovider`、カバレッジのデータファイル、`ruff --no-cache` を作業ディレクトリの外に向ける。外側の pytest / pytest-cov の環境変数（`COV_CORE_*`、`PYTEST_*`）を子に持ち込まない（`toolchain._env`）。ツールの出力から時刻・所要時間・絶対パスを落とす（記録→再生の digest 一致のため）
- 提案: 実ツールを本体で走らせる時の注意（副産物、決定論）を adopting.md に一段落

## G-10 [文書] 高コストな実ステージと分布テスト（N = 数百）の両立

- toy-minimal の分布テストは N = 300。実ツール（pytest 1 回 0.7 秒）を run ごとに数回走らせると、そのままでは数十分になる。指針が無い
- 取った対応: 同じ入力（コードベースの内容のハッシュ、テストの選択）には同じ出力なので、ハーネス内でツールの結果をメモ化する（`toolchain._memo`。結果は変わらない。`set_cache(False)` で切れ、`test_sf_metrics.py` で切った時と同じ結果になることを確かめる）。N は 200 / 150 に下げ、区間の根拠を expectations に書いた。分布と E2E の段で約 75 秒
- 提案: 「分布テストでは実ツールをメモ化するか、記録した結果を使う」を指針として書く

## G-11 [文書] 進入回数（first / reentry）の数え方と、本体から見えないこと

- adopting.md 3.4 は「再進入は carry の鍵が `ctx.memory` にあるかで分かる」と書くが、分布テストの first / reentry は runtime の進入回数（2 回目以降は carry の有無によらず reentry。前のステージへのロールバックの後で通り直すだけでも reentry）で数える（黒箱で確認）。`StageContext` に進入回数は無い
- 困ったこと: 確率的偽本体が first / reentry の分布を使い分けるには、本体の側で runtime と同じ規則で数え直すしかない。成果物から結果が決まる時に供給元を呼ばないと、数がずれる
- 取った対応: 本体は進入のたびに必ず一度供給元を呼ぶ（結果が成果物から決まる時も呼んで値を捨てる）。供給元は (ステージ, タスク) ごとに数え、子 run の始まりで消す（toy-minimal の StochasticSource と同じ考え方）
- 提案: `StageContext` に進入回数（と、carry で戻ってきたか）を持たせるか、adopting.md 第 6 節に first / reentry の定義を書く

## G-12 [文書] 指標がスナップショットの外を読んでよいか

- 指標に見えるのはそのステージの writes の複製と memory（adopting.md 3.3）。changed_paths_in_scope は「base からの差分」なので base のコードベースが要るが、それはハーネスの fixtures（作業ディレクトリの外の静的な資産）にある。読んでよいかが書かれていない。また plan の tasks_cover_design は design.json（plan の writes の外）が要る
- 取った対応: 静的な資産（fixtures の base）は読む（決定論は崩れない）。他のステージの成果物が要る指標は、本体がその情報を自分の成果物に写す（tasks.json の design_components、manifest.json の requirements）
- 提案: 「指標が読んでよいもの」（スナップショット、memory、ハーネスの静的な資産）を明記する

## G-13 [文書] 雛形と toy-minimal の食い違い、雛形の前提と LLM を使わないハーネス

- 雛形第 0 節の骨格は `fixtures/` をハーネス直下に置くが、toy-minimal は `tests/fixtures/`。どちらに合わせるか決められない。ここでは雛形に合わせ、テストの基準（expectations、E2E 計画）だけ `tests/` に置いた
- 雛形第 2 節は「最初に本物にする（LLM や実ツールを使う）ステージ」と「LLM 呼び出しは recorder を経由し記録を残す」、第 4・5 節は人手ラベルと実分類器を前提にする。このハーネスは LLM を使わないので、第 2 節は実ツールのステージで読み替え、第 4・5 節は偽の正解と偽の分類器での実施に留めた（plan.md 第 4・5 節）
- 雛形の付録「同じ戻りの上限超過（仕様へは 3 回、それ以外は 2 回）」が、ワークフローの `max` の設計の指針なのか、作業の進め方の止まる条件なのか分からない。ここでは作業の進め方と読み、`max` は辺ごとに 1〜2 にした

## G-14 [機能] `--metrics-module` はハイフン名のディレクトリのハーネスで使えない

- adopting.md 3.2 は `--metrics-module your_pkg.metrics:registry` を挙げるが、`examples/software-factory/` は import できる名前ではない（`load_example_package` を通さないと読めない）
- 取った対応: マニフェスト（`--metrics`）を使い、レジストリとの一致をテストで確かめる（toy-minimal と同じ）

## G-15 [文書][回避] フレームワーク側のテストが software-factory の存在で落ちる

- この作業で `examples/software-factory/` を作ると、リポジトリ直下の `uv run pytest`（CI の常時の段）で `tests/test_repo_layout.py::test_software_factory_is_not_pre_created` が落ちる（`assert not (ROOT / "examples" / "software-factory").exists()`。失敗の出力だけを見た。テストのファイルは読取範囲の外なので開いていない）。他の 135 件は通る
- adopting.md にも雛形にも、このガードの存在と外し方が書かれていない
- 回避したくなったこと: ガードのテストを消すか、条件を変える
- 取った対応: 何もしない（フレームワーク本体側のファイル）。htf 側のセッションで、software-factory を作る段（F4 / F5）に合わせてガードを外す必要がある

## G-16 [機能] E2E 計画の一項目で変えられるもの

- 計画の項目が台本に重ねられるのは親の `outcomes` と `human` だけ（toy-minimal の計画と `PlanEntry` の欄から）。子 run の台本やペルソナは変えられないので、子のステージの対象には専用の台本が要る。また `run_plan` の工場の中で、中断する台本（DeferringUserIO）を即答するユーザーに差し替える必要がある（toy-minimal の `make_plan_runner` が黙ってそうしている）
- 取った対応: 子の対象ごとに台本を用意した（tasks_unfinished、coverage_low_fixed、unit_test_unknown など）。工場は toy-minimal と同じく中断する台本をペルソナに差し替える
- 提案: `PlanEntry` に任意の台本の上書き（辞書）を持たせる。中断の扱いを工場の約束として書く

## G-17 [文書] 人間の RollbackTo の遷移の記録

- 人間の `RollbackTo` は `rollback_across_phase`（または within）として遷移の記録に残る（台本の期待を書き間違えて気づいた）。adopting.md・CONTRACT 第 6 節の表は、ロールバックの遷移を「END_STATE(s) で…」とだけ書き、人間の解決による場合を書いていない
- 取った対応: 台本の期待に合わせた（`review_unknown_rollback.yaml`）

## G-18 [機能][回避] 子を持つステージの本体に子 run の終わり方が渡らない

- implement の本体（子 run の後に走る）は、単体テストを通ったタスクだけを統合したい。本体に見えるのは子の成果物（`tasks/<i>/` 配下）だけで、`ChildOutcome`（goal / stuck / unknown）は渡らない。本体は成果物から各タスクの状態を判定し直すことになり、分類（unit_test の tests_failing / coverage_low）の論理をコードに書き写すことになる
- 回避したくなったこと: runtime の内部から子 run の結果を取る
- 取った対応: 成果物の事実だけで判定する（code.json のビルド・lint・範囲外の変更、unit/report.json の failed と coverage_gaps の有無。`stages._task_status`）。分類の記述を読む判定は書いていない
- 提案: 子を持つステージの本体に、子 run の終わり方を読み取り専用で渡す（例: `ctx.memory` の予約鍵か `StageContext.child_outcomes`）

## G-19 [機能] ユーザー入出力に文脈を渡す手段が無い

- release の承認では、依頼者に「どの要件が見送られ、合意があるか」を見せて判断させたい。`UserIO.ask(question, schema)` には文脈の欄が無く、シミュレータは質問文を読んで判断するしかない（`UNAGREED_MARK` を質問文に埋め込み、ペルソナが文字列で探す）
- 提案: `ask` に任意の文脈（JSON）を渡せるようにするか、質問文に構造を埋める約束を書く

## G-20 [文書] トリアージ待ち行列と集約の unknown

- 子の unknown を集約規則で親 unknown にした時、親の評価記録には状態文書が無く（分類器を呼ばない）、`TriageQueue.enqueue` は親の項目を積まない（子の項目は積む。黒箱で確認）。adopting.md 第 6 節は「unknown の評価記録を積む」と書くだけで、状態文書の無い記録の扱いが分からない
- 取った対応: 子の項目でラベルを付ける前提にした（`test_sf_triage.py`）

## G-21 [文書] carry の鍵を複数のステージが出してよいか

- 同じ memory の鍵を二つのステージの `memory_out` に書いてよいか（例: 前段が空の値を、後段が carry の値を出す）が、スキーマにも adopting.md にも書かれていない（G-04 の回避を考えた時に困った）
- 取った対応: 使わない。memory の鍵はそれぞれ一つのステージだけが出す

## G-22 [文書] ロールバックが続く時の carry と前回の成果物

- 第三者レビュー（plan.md 第 1.1 節）で指摘された。restore は戻り先の開始時スナップショット（writes の範囲と memory の全体）を戻すので、(a) 戻り先が前回書いた成果物は消えて作り直しになり、(b) 二段続けて戻ると最初の carry が memory から消える（release → analyze（rejection_feedback）→ analyze が ambiguous で intake へ → intake の開始時の memory には rejection_feedback が無い）。逆に、一段だけ戻る時は、戻り先の最後の開始時以降に出た古い memory が残る
- adopting.md 第 5 節と CONTRACT 第 2・3 節の規則から導けるが、ワークフローを設計する側から見た帰結（どの carry がいつ消えるか、carry の id が作り直した成果物と対応する保証が無いこと）が書かれていない。定義を書く時に気づけなかった
- 取った対応: 定義は変えず、提案として plan.md 第 1.1 節に残した
- 提案: adopting.md 第 3.1 節に「二段のロールバックで carry を保つには二段目の辺にも同じ鍵を carry する」「carry に前の成果物の id を入れる時の注意」を書く。検査器で、carry の鍵を受け取ったステージが更に前へ戻す辺を持つ時に警告する

## G-23 [文書] 文書の最初のステージは unknown 以外の end_state を持てない

- 戻り先は自ステージより前（`rollback_forward`）なので、各文書の最初のステージ（親の intake、子の code）は unknown しか持てない。子の code は自分の goal 指標（ビルド・lint・変更パスの範囲）で失敗を見つけても、それを直す戻り先が無く、失敗は全て unknown（人間へ）になる。第三者レビューの重大度「高」の指摘はこれ
- toy-minimal の子（write_section）も同じ形だが、その帰結（「検出するステージ」と「直すステージ」を分けないと準正常系にできない）が adopting.md に書かれていない
- 取った対応: 定義は変えず、確認ステージを足す提案を plan.md 第 1.1 節に残した
- 提案: adopting.md 第 3.1 節に「ステージ自身の goal 指標の不成立は、そのステージでは end_state にできない（戻り先が要る）。直させたい失敗は後ろのステージで判定する」と書く
