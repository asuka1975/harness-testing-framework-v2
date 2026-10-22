# F5（v1.0 公開と維持）の第三者検証報告

- 検証役: 実装に関わっていないサブエージェント（Claude Code）。リポジトリに書いたのは本ファイルのみ。探針のスクリプトは `/tmp/claude-1000/.../scratchpad/probe{1..4}_*.py`（リポジトリには残していない）
- 対象: コミット `9abaa55`（F5 の実装）。作業ツリーは本報告のディレクトリ以外に差分なし（`git status --short` は本報告を書く前は 0 件、書いた後は `?? reports/verification/f5-release/` のみ）。タグは `v0.1.0` のみ、`v1.0.0` は未作成
- 日付: 2026-10-22
- 判定の根拠は実行結果。実装（`src/htf/`）は探針を書くために読んだが、読んだ印象で判定していない

## 要旨

| 項目 | 判定 |
| --- | --- |
| (a) 二つの玩具で全ランナーが通る | **満たす**（htf 170 passed / 69.9 s、software factory 120 passed / 149.5 s。マーカーで分けた常時・ナイトリー・手動の各段も収集で確認。常時の段の sf は CI 原文のコマンドで 105 passed / 41.8 s） |
| (b) adopting-gaps.md が全て処理済み | **満たす**（G-01〜G-23 が ADR-014 の処置の一覧と一対一で対応。解消しない G-14 は理由が記録されている。要約の時制が古い箇所 1 件、低） |
| (c) 雛形が書かれ、software factory を雛形に当てはめて矛盾が無い | **満たす**（節立て・数値・完了条件の答えは全て一致。残るずれは 2 件とも低: 第 9 節の「ハーネス固有の担当と頻度」を sf が実 LLM 導入時へ先送りしている（雛形第 2 節が第 4・5 節に認めている読み替えと同じ形で、その旨を書いている。雛形第 9 節にその読み替えの条項が無いのは雛形側の不足）、「ハーネスの版」の所在が sf に無い。いずれも雛形か adopting.md に一文足せば消える。第 3 節） |
| (d) CI に段階が設定されている | **満たす**（三 job の起動条件とマーカー選択を確認。常時の段の収集は htf 154 / sf 105 件で、分布・E2E・オラクル・独立性のファイルからの漏れ 0 件。三段の和が全体と一致。runtime カバレッジ 92.84% ≥ 90%） |
| (e) v1.0 として公開できる状態か | **公開できる状態（人間ゲート待ち）**。版 1.0.0（pyproject と `htf.__version__` が一致）、wheel が作れて別 venv で同梱スキーマから検査器が動く、ruff・`uv lock --check` 通過。「公開」自体（タグ・Release・push）は人間の承認後で未実施、ADR-014 14.6 と ADR-015 の決定欄は未記入（設計どおり v1.0 ゲートで記入） |
| 先送りされていた第三者判定（探針） | **固定されている**。探針 4 本・判定 40 項目中、製品の不具合 0 件（探針側のバグ 1 件を直して再実行、情報項目 1 件）。重要な事実: 検査器は carry の閉包を見ない（設計どおり）。閉包を落とすのは `test_sf_v02.py::test_carry_closure` だけ |
| 重大度「高」の問題 | **無し** |

## 1. F5 の完了条件

### (a) 二つの玩具で全ランナーが通る → 満たす

```
uv run pytest -o addopts="" -q tests                              → 170 passed in 69.90s（EXIT 0）
uv run pytest -o addopts="" -q examples/software-factory/tests    → 120 passed in 149.54s（EXIT 0）
uv run pytest -q -m "not distribution and not e2e and not oracle" --cov=htf.runtime --cov-fail-under=90
                                                                  → Required test coverage of 90% reached. Total coverage: 92.84%（EXIT 0）
uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics examples/toy-minimal/metrics/manifest.json → 0 finding(s)
uv run python -m htf.testing.spec examples/software-factory/workflow.yaml --metrics examples/software-factory/metrics/manifest.json → 0 finding(s)
uv run pytest examples/software-factory/tests -m "not distribution and not e2e and not oracle"（CI 原文）→ 105 passed, 15 deselected in 41.78s
```

skipped / xfail は無し（両方とも `passed` のみ）。F4 の完了条件に挙がる各ランナー（7 種の遷移、分布、独立性、カバレッジ 1.0、マルコフ合成、オラクル、トリアージ）は sf の `test_sf_transitions / distribution / e2e / oracle / triage` が全て含み、通っている。

### (b) adopting-gaps.md が全て処理済み → 満たす

`examples/software-factory/docs/adopting-gaps.md` の「処置の状況」節と ADR-014「処置の一覧」を G-01〜G-23 で突き合わせた。

| 分類（adopting-gaps の要約） | 項目 | ADR-014 の処置 | 一致 |
| --- | --- | --- | --- |
| htf 本体を直した | G-04, 05, 06, 08, 16 | 解消（runtime / 検査器 / 設定）。`tests/test_f4_gaps.py` で固定 | 一致（第 2 節の探針でも確認） |
| 設定 / CI | G-03, 07, 15 | 解消 | 一致（ruff の `extend-exclude` と ci.yml のステップを実物で確認） |
| 文書 | G-01, 02, 09, 10, 12, 13, 17, 20, 21, 22, 23 | 解消（adopting.md / 雛形） | 一致（adopting.md 3.1 に閉包と「検出と修正を分ける」、第 9 節「落とし穴」を確認） |
| 文書 + 契約への提案 | G-04 の文言 (14.1), G-11 (14.2), G-18 (14.3), G-19 (14.4) | 実装済み（`tests/test_f4_contract_proposals.py`、CONTRACT 5.1 / 5.3 / 5.4 / 7） | 一致。ただし adopting-gaps の要約は「承認済み。F5 の v1.0 前に実装」と未来形のまま（低。第 4 節 文書-1） |
| 解消しない（理由） | G-14 | 理由を ADR-014 に記録 | 一致 |

`tests/test_f5_release.py::test_adopting_gaps_are_all_processed` は「処置の状況」節に G-01〜G-23 の文字列があることしか見ないので、この突き合わせは手で行った。

### (c) 雛形と software factory → 満たす（第 3 節に表）

- `docs/harness-plan-template.md` は第 0〜9 節 + 付録で、各節に「書くこと / 守ること / 完了条件 / 実例」がある。`tests/test_f5_release.py::test_template_sections_match_the_software_factory_plan` が見出しの一致を固定している（通過）
- 雛形が実例として引く数値（5 フェーズ 9 ステージ + 子 3、ユーザー待ち 2、台本 26、ペルソナ 5、43 対象 誘発 39・注入 4、誘発できない 3 クラス、指標 28）を実物で数えた: フェーズ 5、親ステージ 9、子 3、`fixtures/scenarios/*.yaml` 26、`fixtures/personas/` 5、`metrics/manifest.json` 28、`tests/e2e/plan.yaml` 43 項目で `inject:` 4 件（integrate/merge_failed、verify/coverage_short、verify/lint_dirty、release/unknown）。全て一致
- 矛盾と断じるものは無い。ずれ 2 件（第 9 節の担当と頻度の先送り、ハーネスの版の所在。いずれも低）と文言のずれ 3 件は第 3 節。判定を「満たす」とした理由: 第 9 節の先送りは、雛形第 2 節が LLM を使わないハーネスに第 4・5 節で認めている読み替え（偽の正解・偽の分類器に留めてその旨を書く）と同じ形で、sf はその旨を書いている。雛形第 9 節に同じ条項が無いのは雛形側の不足（F5 の戻る条件「雛形か adopting.md」）

### (d) CI に段階が設定されている → 満たす

`.github/workflows/ci.yml` の三 job:

| job | `if` | 内容 |
| --- | --- | --- |
| `always` | `push \|\| pull_request` | ruff check / format、`pytest -m "not distribution and not e2e and not oracle" --cov=htf`、同じ選択で `--cov=htf.runtime --cov-fail-under=90`、`pytest examples/software-factory/tests -m "not distribution and not e2e and not oracle"` |
| `nightly` | `schedule \|\| (workflow_dispatch && inputs.tier == 'nightly')` | `pytest -m oracle`（htf と sf） |
| `manual` | `workflow_dispatch && inputs.tier == 'manual'` | `pytest -m "distribution or e2e"`（htf と sf） |

`--collect-only -q` で数えた（`-o addopts=""`）:

| 選択 | tests/ | examples/software-factory/tests |
| --- | --- | --- |
| 全体 | 170 | 120 |
| 常時 `not distribution and not e2e and not oracle` | 154 | 105 |
| ナイトリー `oracle` | 3 | 3 |
| 手動 `distribution or e2e` | 13 | 12 |

154 + 3 + 13 = 170、105 + 3 + 12 = 120 で三段は全体を漏れなく分割している。常時の段の node id を `f3_distribution|f3_e2e|f3_oracle|f3_independence|sf_distribution|sf_e2e|sf_oracle` で grep して 0 件（マーカー漏れ無し。`test_f3_independence.py` は `pytestmark = pytest.mark.distribution` を持ち手動の段に入ることを grep で確認）。ruff（`check .` All checks passed、`format --check .` 71 files already formatted）と `uv lock --check`（成功）も CI の最初のステップとして通る。所要時間の目安（maintenance.md 第 4 節: sf 常時 約 1 分）は実測 42 秒で合う。

### (e) v1.0 として公開できる状態か → 公開できる（人間ゲート待ち）

- 版: `pyproject.toml` 1.0.0、`src/htf/__init__.py` `__version__ = "1.0.0"`。一致
- 配布物: `uv build`（出力はスクラッチパッド）で sdist と wheel が作れる。wheel に `htf/schema/workflow.schema.json`、`htf/contract/CONTRACT.md`、`htf/contract/conformance/conformance.yaml` が入っている。別の venv に入れて cwd=/tmp から `python -m htf.testing.spec <sf の workflow.yaml> --metrics ...` → `0 finding(s)`（同梱スキーマで動く。リポジトリへは何も書かれない）
- README: v1.0 の状態、三段の CI、使い方のコマンドが書かれ、所要時間の記載（htf 約 1 分強、sf 約 2.5 分）は実測（70 s、150 s）と合う
- 未解決の懸念: ADR-015「決定」欄と ADR-014 14.6 の承認が未記入（v1.0 ゲートで人間が記入する設計）。タグ・Release・push は人間の指示待ち。maintenance.md 第 6 節の手順 (1) 常時の段と手動の段を両方通す → 三段とも CI のコマンドどおり単独で通した（常時: htf 154 件はカバレッジ付きの実行で通過、sf 105 passed / 42 s。ナイトリー: `-m oracle` htf 3 passed / 0.3 s、sf 3 passed / 15 s。手動: `-m "distribution or e2e"` htf 13 passed / 66 s、sf 12 passed / 112 s）。(2) progress.md への検証の要旨 → 本報告の後に計画エージェントが書く
- 判定: 技術的には公開できる状態。「公開」そのものは人間ゲートなので本検証では満たす / 満たさないを付けない

## 2. 先送りされていた第三者判定（探針）

探針は `tests/test_f4_contract_proposals.py` の `_pass_carry` / `_ask_context` を importlib で読み、既存テストが見ていない経路を足した。全て `uv run python` で実行。

### 探針 1: `ctx.entry` の規則（CONTRACT 5.1 / 14.2）— 16 / 16 PASS

| 場面 | 期待（CONTRACT 5.1） | 結果 |
| --- | --- | --- |
| check を unknown に注入 → 人間が `Rerun` | check の entry が増える | `check: [(1,F),(2,T)]`、fan は `[(1,F)]` のまま、完走、`edge_counts == {}`、遷移に rollback 無し |
| 同 → 人間が carry 無しの `RollbackTo("fan", {})` | fan と check の entry が増え、子は run ごとに 1 から、辺の max を消費しない、`rollback_within_phase` note=human | `fan: [(1,F),(2,T)]`、`check: [(1,F),(2,T)]`、`work: [(1,F),(1,F)]`、`edge_counts == {}`、遷移 `('rollback_within_phase','human')` |
| 同、check が escalate 前に `hint` を emit していた | carry 無しなので戻り先の開始時 memory に hint が無い | 2 回目の fan 開始時 memory `{'items': ['a']}`（hint 無し） |
| `ask_context` で中断する UserIO → 中断 → `resume` | 再開では entry が増えない | 本体が見た `(entry, reentry)`: `[(1,F),(1,F)]` |

既存テスト（`test_14_2_entry_and_reentry_follow_the_runtime_rule`）はロールバックによる再進入だけを見ていた。人間の Rerun / RollbackTo / 中断再開の三経路も規則どおりで、adopting.md 3.4 の「人間の Rerun や carry 無しの RollbackTo は carry では区別できず entry で区別できる」は実際にそのとおり。

### 探針 2: carry の閉包から鍵を一つ外した複製 — 事実を記録

`plan/design_gap → design` の carry から `review_comments` を外した複製（`implement-task.yaml` ごとスクラッチパッドへ複製。design の `memory_in` には他の辺からも `review_comments` が来るので検査器の `memory_in_source` は別の供給元で満たされ、閉包だけが壊れる）。

| 検査 | 結果 |
| --- | --- |
| `check_workflow(原本)` | 0 finding(s) |
| `check_workflow(複製)` | **0 finding(s)**（検査器は閉包を見ない。`src/htf/testing/spec/` に閉包の検査は無い: `grep closure\|閉包` 0 件） |
| `test_carry_closure` のループを複製に当てる | 違反 1 件 `('software-factory','plan','design_gap','design',['review_comments'])` |
| `test_sf_v02.py::test_carry_closure(複製)` を直接呼ぶ | `AssertionError: software-factory: plan/design_gap → design に ['review_comments'] が無い` |

結論: 閉包を固定しているのはハーネス側のテストだけで、検査器は設計どおり（ADR-014 G-22「検査器の警告は見送り」）閉包を見ない。雛形第 1 節「閉包をテストで固定する」と adopting.md 3.1 の指針はこの事実と整合している。新しいハーネスは自分で閉包テストを書かないと守られない（第 6 節）。

### 探針 3: `ask(..., context=)` の往復と子 unknown の `child_outcomes` — 10 / 10 PASS

| 検査 | 結果 |
| --- | --- |
| 記録モードで run → JSONL の `kind: user` の `request` | `{"context": {...CONTEXT...}, "question": ..., "schema": {...}}`。context が残る |
| 再生モード（`user=None`）で run | 完走。`answer.json` が記録と一致、終了時スナップショットの memory も一致 |
| 違う context を渡す本体で再生 | `ReplayMismatch: 記録 #0 と不一致: 期待 user {'context': {...}, ...}, 実際 user {...}`（context は要求の一部として照合される。既存テストは「再生が完走する」ことしか見ていなかった） |
| 子 `work` を unknown に注入 | 親本体の `ctx.child_outcomes == (ChildOutcome(index=0, kind='unknown', stage='work', state='unknown'),)`、親は aggregate 規則が無いので UNKNOWN → 人間 → Abort、`RunResult.child_outcomes['fan']` にも同じ列、子を持たないステージは空 |

### 探針 4: software factory の実成果物での投影と版の照合 — 12 / 12 PASS（情報 1）

`happy` 台本を本物の本体で走らせ（`sf_support.run_scenario`）、終了時スナップショットを `htf.runtime.project` で投影した。

| 検査 | 結果 |
| --- | --- |
| release の投影で `## writes` < `## reads` | writes@30、reads@1955（文書 6632 文字） |
| `writes_block` が CHANGELOG.md の `## 追加` で切れず approval.json まで届く | writes 節 1914 文字、`## 追加` と `approval.json` を含む。実際の CHANGELOG.md に `## 追加` 見出しがある |
| `MarkerClassifier` が release の実文書で goal | `Classification('goal', 1.0)` |
| verify（`reads: [codebase/]`、15 ファイル）の投影で `## writes` < `## reads` | writes@29、reads@3607（文書 8055 文字） |
| `max_document_chars=6000` | 末尾に `…（文書全体 2055 文字省略）`、先頭 6000 文字は原文と一致、writes 節（`verification/report.json`）は残り、切り詰め後も goal |
| 情報: 1 ファイルの切り詰めの印 | verify の全文書に出ない（全ファイル 4000 文字未満。sf の要旨 / 全結果の分離 14.6.9 が効いている） |
| sf の `expectations/markov.yaml` の `workflow_version` を 0.1 に変えて `check_expectations` | `ValueError: expectations 'markov' の workflow_version '0.1' が実行した定義の版 '0.2' と違う。…` |

### 探針で確かめなかったもの（既存テストを根拠に採る）

- G-05（即答した回答の累積）: `test_g05_partial_answers_are_accumulated_in_order`（通過）。探針 1 の中断再開も同じ経路を通る
- G-06（親子のステージ id）: `test_g06_checker_rejects_stage_id_shared_between_parent_and_child`（通過）
- G-16（計画の overrides）: `test_g16_plan_entry_can_override_any_scenario_field`（通過）
- E2E 計画の版の照合（`run_plan`）: `test_plan_version_mismatch_fails`（通過）
- トリアージ・コーパスの版: `test_triage_items_carry_the_version_of_their_workflow`、`test_corpus_items_round_trip_the_workflow_version`（通過）

## 3. 雛形と software factory の計画書の突き合わせ

| 節 | 雛形の「書くこと / 完了条件」 | sf 計画書 | 判定 | 直すなら |
| --- | --- | --- | --- | --- |
| 冒頭 | 「実例は sf 計画書（この雛形を当てはめたもの。版 0.2）」、雛形は「完成版、v1.0」 | 冒頭「`docs/harness-plan-template.md`（**最低限版**）の節に沿って埋めたもの」 | 文言のずれ（低）。sf 計画書が古い雛形の名を引く | sf 計画書の一語（雛形・adopting.md の問題ではない） |
| 0 | ハーネス名・目的・概要（ユーザー待ち、動的な下位作業）、固定の設計判断、基準値は定義から読む / 骨格 | 全て答えている（表、ユーザー待ち 2、子の集約、`harness.unit_coverage_min`、骨格 済） | 一致 | — |
| 1 | 定義、成果物の形、守ること 4 点、完了条件（spec 0 件、第三者レビューは隔離ディレクトリで読取範囲を課す、指摘は表） | 成果物の形、指標 28、版 0.2、spec 0 件、レビュー 2 回（サブエージェント + Codex）、表、採否 | 一致。ただし 1 回目のレビューは「同じ読取制限を課した」サブエージェント（指示で課した）で、雛形の「読取範囲は指示ではなく隔離ディレクトリで課す」は Codex の回だけが満たす | 雛形は Codex の回の経験から書かれ、sf 計画書は事実を書いている。矛盾ではない（記録）。雛形の文は維持 |
| 2 | 最初の実ステージと理由、LLM 無しの読み替え、実ツールの扱い（作業ディレクトリに書かない・正規化・メモ化）、完了条件 3 つ | check と unit_test、理由、`toolchain.py` の扱い、3 条件とも済 | 一致（雛形の読み替え規定 G-13 が効いている） | — |
| 3 | フィクスチャ・ペルソナ 3 以上・台本・確率的構成、完了条件（E2E 計画が全対象を踏む、carry を運ぶ end_state は誘発、起きないクラスは注入 + 単体テストで明記、契約適合） | 変種 9、ペルソナ 5、台本 26、profiles 2、43 対象 誘発 39 注入 4、例外 3 クラスの理由、契約適合 済 | 一致（数値は実物と一致） | — |
| 4 | コーパスの作り方、ラベラー、件数（ステージ × クラス 20 以上）、形式（JSONL、**`workflow_version` を持つ**）、完了条件（偽の正解での代用を明記、human_approval） | 作り方 2 通り、ラベラー無し、43 × 20 ≈ 900、「形式は `htf.testing.oracle` の JSONL」、代用を明記、human_approval 無し | ほぼ一致。sf 第 4 節は `workflow_version` に触れない（第 9 節にはある） | sf 計画書第 4 節に一語足せば済む。雛形は維持 |
| 5 | 後ろ側、κ・ECE・再実行一致の**目標と閾値**（仮置き、根拠）、有効標本の扱い、完了条件（レポート、ナイトリーに載せる） | 偽の分類器のみ、実測値（κ=1.0 ほか）と許容幅、有効標本の注意は第 4 節、確信度 0.5 は既定、ナイトリーは第 9 節 | ほぼ一致。κ・ECE の「目標」は書かれていない（実測と許容幅だけ）。偽の分類器では較正にならないと明記 | 雛形第 5 節に「偽の分類器しか無い段階では目標は書けず、実測と許容幅を書く」と読み替えを一行足すと sf と揃う（雛形側） |
| 6 | expectations（N、種、版、区間、根拠）、往復の手順、完了条件（通る、ずらしたものが落ちる、版の一致） | markov / markov_shifted / split、実測、往復、3 条件とも済 | 一致（探針 4 で版の照合も確認） | — |
| 7 | クラスと代表の鍵、p 値、完了条件（揃う。分割検出なら提案して止まる） | tests_failing、既定の鍵、p 値 0.05、markov 済、split は検出（提案を書いて承認待ち）、検証不能 3 クラスの記録 | 一致 | — |
| 8 | 本物にする順、E2E 計画の更新、マルコフ合成（子 run 数の分布）、完了条件 2 つ | 順の提案、43 対象、samples からの子 run 数、markov 差 0.002、split で外れる | 一致 | — |
| 9 | **トリアージの頻度と担当**、承認の流れ、版の同期（**ハーネスの版**も同じ変更で）、CI の段階。完了条件「手順書がある（maintenance.md を基に**ハーネス固有の担当と頻度**を書く）」 | 頻度（週一回）はあるが担当は無し。「ハーネスの版を同じ変更で上げる」と書くが sf にはパッケージの版（`__version__` など）が無く、版は計画書の「版 0.2」だけ。完了条件は「済（担当と頻度は実 LLM を入れる段で決める）」 | **ずれ（低。雛形側の不足）**: 雛形の完了条件は「担当と頻度を書く」で、sf は実 LLM 導入時へ先送りして「済」としている。雛形第 2 節が第 4・5 節に認める読み替えと同じ形だが、第 9 節にはその条項が無い。**ずれ（低）**: 「ハーネスの版」の所在 | 雛形第 9 節の完了条件を「手順書がある。担当と頻度は実 LLM（実ユーザー）を入れる前に決める。偽本体だけの間は htf の maintenance.md の参照で可」に改めるか、sf 計画書を「一部」に改める。後者は sf 側の修正なので F5 の戻る条件からは雛形を直す方が筋。「ハーネスの版」は adopting.md / 雛形に「パッケージの版が無いハーネスでは計画書の版（と `workflow.version`）」と一言 |
| 付録 | 止まる条件・禁止事項 | 当たった止まる条件 3 件 | 一致（雛形の付録「上限」は作業の進め方の規則と明記され、G-13 が解消されている） | — |

総括: 構造と数値の矛盾は無い。第 9 節の 2 点は雛形（または adopting.md）側に読み替えを一文書けば消える種類のもので、計画書 F5 の戻る条件「雛形か adopting.md」に当たるが、v1.0 公開を止めるほどではない（判定は「満たす」）。

## 4. 発見した問題

### ワークフロー定義（software factory）

無し。整合性検査 0 件、閉包・優先の文言・aggregate の順序はテストで固定され、実成果物の投影でも分類器が正しく読める（探針 4）。

### htf 本体

| # | 重大度 | 内容 | 根拠 |
| --- | --- | --- | --- |
| 本体-1 | 低（設計どおり。記録） | 検査器は carry の閉包を検査しない。閉包を壊した定義も `0 finding(s)`。新しいハーネスは自分で閉包テストを書かないと二段ロールバックで carry が消える不具合を検査器では捕まえられない | 探針 2。ADR-014 G-22「検査器の警告は見送り」と整合 |
| 本体-2 | 低（情報） | `test_14_4_context_is_recorded_and_replayed` は「再生が完走する」しか見ておらず、context が照合されることは固定していない（実際には照合されている。探針 3） | 探針 3 で `ReplayMismatch` を確認 |
| 本体-3 | 低（情報） | `test_14_2_entry_and_reentry_follow_the_runtime_rule` は人間の Rerun / RollbackTo / 中断再開の経路を見ていない（実際には規則どおり。探針 1） | 探針 1 |

探針 1〜4 の内容（人間の解決と entry、閉包の複製、違う context での再生、実成果物での投影）は htf か sf の退行テストとして足す価値がある（公開後でよい）。

### 文書

| # | 重大度 | 内容 | 根拠 |
| --- | --- | --- | --- |
| 文書-1 | 低 | `adopting-gaps.md` の「処置の状況」が G-11 / 18 / 19 / 04 の文言を「承認済み。F5 の v1.0 前に実装」と未来形で書いている。実装済み（ADR-014「実装の記録」、`tests/test_f4_contract_proposals.py` 通過） | 引用: 「文書 + 契約への提案（承認済み。F5 の v1.0 前に実装）」 |
| 文書-2 | 低 | sf 計画書の冒頭が雛形を「最低限版」と呼ぶ。雛形は「完成版、v1.0」 | 第 3 節 |
| 文書-3 | 低 | 雛形第 9 節の完了条件「ハーネス固有の担当と頻度を書く」を sf が実 LLM 導入時へ先送りして「済」としている。雛形第 9 節に第 2 節のような読み替えの条項が無い（雛形側の不足） | 第 3 節 |
| 文書-4 | 低 | 「ハーネスの版」の所在が sf に無い（パッケージの版が無い）。maintenance.md 第 3 節と雛形第 9 節は「ハーネスのパッケージの版も同じ変更で上げる」と書く | `grep __version__ examples/software-factory/__init__.py harness.py` 0 件 |
| 文書-5 | 低 | ADR-015「決定」欄と ADR-014 14.6 の承認が未記入。設計どおり（v1.0 ゲート）だが、公開時に記入が要る | ADR-015 末尾「（未記入。v1.0 ゲート）」 |

## 5. 判定できなかった事項

- 「v1.0 として公開」（完了条件の最後の項目）そのもの: 人間ゲート（タグ・Release・push）なので本検証では判定しない。技術的な前提は全て通っている
- CI が GitHub Actions 上で実際に走ること（`astral-sh/setup-uv@v5` の動作、`inputs.tier` の `if` 式の評価）: ローカルでは YAML の構造とコマンドの通過しか確かめられない。`nightly` の `if` が `schedule` の時に `inputs.tier` を参照するのは空文字になるだけで問題にならないはずだが、実行で確かめていない
- 分類器の閾値・κ・ECE の目標値の妥当性: 偽の分類器しか無いので判定できない（ADR-006 の後）

## 6. v1.0 公開への懸念

公開前に直すべきもの:

- 高の問題は無い。文書-1（adopting-gaps の未来形）と 文書-2（「最低限版」）は一語の修正で、公開物に残すと「未実装」と読まれるので公開前に直すのが望ましい（いずれも sf の docs 配下 = 利用者の成果物。計画エージェントが理由を progress.md に残して直す）
- ADR-015 の決定欄と ADR-014 14.6 の承認を人間ゲートで記入する（設計どおり）

公開後でよいもの:

- 文書-3 / 文書-4（F5 の戻る条件「雛形か adopting.md」に当たる）: 雛形第 9 節（または adopting.md）に「担当と頻度は実 LLM / 実ユーザーを入れる前に決める」「パッケージの版が無いハーネスでは計画書の版」の読み替えを足す
- 本体-1: 新しいハーネスのために、閉包の検査を検査器の警告（ADR-014 で見送った案）として足すか、adopting.md 3.9 に閉包テストの雛形（`test_carry_closure` のループ）を載せる
- 本体-2 / 本体-3: 探針 1〜4 を退行テストとして htf（`tests/`）か sf に取り込む
- maintenance.md 第 6 節 (2)「progress.md に検証の要旨」を本報告から書く

## 7. 予算の実績

- おおよそのトークン: 約 15 万（文書とテストの読み込み 約 6 万、探針と実行 約 3 万、報告と修正 約 3 万、その他）。上限 25 万の内側
- 時間: 約 19 分（開始からの経過 515 秒の時点で報告を書き始め、段ごとの単独実行の待ちを含めて 1119 秒で確定。上限 30 分）
- ツール呼び出し: 約 36 回（Bash 約 27、Write 5、advisor 2、その他 2）
- 外部 LLM 呼び出し: 0

読んだファイル（全文または該当節）: `docs/plan.md`（5.7〜5.10、F4、F5）、`docs/decisions.md`（ADR-014、ADR-015）、`src/htf/contract/CONTRACT.md`、`docs/adopting.md`（見出し、3.1、3.4、3.7、第 9 節）、`docs/harness-plan-template.md`、`docs/maintenance.md`、`README.md`、`pyproject.toml`、`.github/workflows/ci.yml`、`docs/progress.md`（先頭）、`tests/test_f4_gaps.py`、`tests/test_f4_contract_proposals.py`、`tests/test_f5_release.py`、`tests/fixtures/workflows/{pass_carry,ask_context}.yaml`、`examples/software-factory/docs/{plan,adopting-gaps}.md`、`examples/software-factory/workflow.yaml`（構造と plan の rollback）、`examples/software-factory/tests/{test_sf_v02.py,sf_support.py,conftest.py}`、`examples/software-factory/tests/{expectations,e2e}/*.yaml`（版の欄）、`examples/toy-minimal/tests/fixtures/scenarios/happy.yaml`、`src/htf/runtime/runner.py`（Runner・_loop・人間の解決・_rollback）、`src/htf/runtime/recorder.py`（call・RecordedUserIO）、`src/htf/testing/harness/__init__.py`（MarkerClassifier・writes_block）、`src/htf/schema.py`

実行したコマンド（全て EXIT 0）:

```
uv run pytest -o addopts="" -q tests
uv run pytest -o addopts="" -q examples/software-factory/tests
uv run pytest -q -m "not distribution and not e2e and not oracle" --cov=htf.runtime --cov-fail-under=90
uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics examples/toy-minimal/metrics/manifest.json
uv run python -m htf.testing.spec examples/software-factory/workflow.yaml --metrics examples/software-factory/metrics/manifest.json
uv run ruff check . / uv run ruff format --check . / uv lock --check
uv run pytest -o addopts="" --collect-only -q [-m ...] tests / examples/software-factory/tests（4 選択 × 2）
uv run pytest examples/software-factory/tests -m "not distribution and not e2e and not oracle"（CI 原文）
uv run pytest tests -m oracle / uv run pytest examples/software-factory/tests -m oracle（ナイトリーの段、CI 原文）
uv run pytest tests -m "distribution or e2e" / uv run pytest examples/software-factory/tests -m "distribution or e2e"（手動の段、CI 原文）
uv build --out-dir <scratchpad>/dist; uv venv <scratchpad>/venv; uv pip install <wheel>; <venv>/python -m htf.testing.spec ...（cwd=/tmp）
uv run python <scratchpad>/probe1_entry.py / probe2_closure.py / probe3_context_child.py / probe4_projection_sf.py
git status --short / git log --oneline -5 / git tag
```

副作用: 必須コマンドが `.pytest_cache` / `.coverage` を作る（gitignore 済み。`git status --short` は本報告を書く前は 0 件、書いた後は `?? reports/verification/f5-release/` のみ）。リポジトリへの書き込みは本ファイルのみ。
