# 作業ログ

形式は計画書第4節末尾で固定。先頭に「次にやること」、続いて日付ごとに「完了したこと」「未完了と理由」「発見した問題（ワークフロー定義 / フレームワーク本体）」「実行した検証とその結果の要旨」。

## 次にやること

F2 は完了（検証役の判定「満たす」を受け入れ、報告の B1〜B4 / B6 / B9 を修正して 113 passed、runtime 93%）。**F3（テストランナー群）に入る。** 人間は不在。止まる位置は **F3 の終わりの v0.1 公開承認**（pyproject の版は 0.1.0 に上げてよいが tag と Release は打たない）。第5.5節の条件に当たればその前でも止まる。

F3 のタスク列（第5.1節）。閾値（独立性の p 値、κ / ECE の許容差、マルコフ予測の許容差、N）はすべて仮置きで、コードでなく expectations / 設定に置き、ADR-013 に一覧にしてゲートに出す。依存は増やさない（χ² の分布関数が要る所は種を固定した並べ替え検定）。

1. **完了条件のテストを先に別コミット**: `tests/test_f3_distribution.py`（確率的偽本体に対して正しい expectations が通り、ずらした expectations が落ちる）、`tests/test_f3_independence.py`（クラス内で意図的に下流分布を分けた偽本体を検出し、分けていないものは検出しない）、`tests/test_f3_oracle.py`（既知の混同行列と較正を持つ偽分類器に対して κ と ECE を許容差内で再現。違う κ を期待すると落ちる。再実行一致）、`tests/test_f3_e2e.py`（E2E 計画が toy-minimal の親子の全 (stage, end_state) を誘発か注入で踏む。マルコフ予測と実測が許容差内。分割した本体では外れる）、`tests/test_f3_triage.py`（unknown を一件、待ち行列 → ラベル → コーパスへ流す）。実装前の失敗を記録
2. **runtime の評価ログと注入**: `RunResult.evaluations`（stage、進入回数、状態文書、選択肢、分類結果、Verdict。評価時に捕まえる）と `.htf/evaluations.jsonl`。`Runner(inject={(stage, n): Verdict})` で n 回目の進入の Verdict を差し替え、`reason` に注入と書く
3. **確率的偽本体**（`examples/toy-minimal/stages/stochastic.py`）: 結果の供給元を種つきの分布に差し替える（成果物を書くコードは決定論的本体を再利用）。再進入（carry あり）で分布が変わるもの、`check_section` の `inconsistent` にクラス内で代表（carry の中身）ごとに下流分布を分けたものを含む
4. **分布テストランナーと expectations 形式**（`htf.testing.stages`）: 起点（ワークフロー先頭。保存した開始時スナップショットは欄だけ用意）、N、種、(stage, 初回 / 再進入) ごとのクラス頻度の区間、run 全体の結果の頻度の区間。expectations は `examples/toy-minimal/tests/expectations/`
5. **独立性検証と遷移行列**（`htf.testing.stages`）: 代表の鍵 `(stage, class, 評価記録) → key` は設定項目（既定は carry のハッシュ）。クラス内の群ごとの下流クラス分布を種つき並べ替え検定で比べる。遷移行列 P(class | stage, entry) の推定
6. **オラクル検証**（`htf.testing.oracle`）: コーパス形式とラベル形式（JSONL）、κ（Cohen）、ECE、再実行一致、レポート
7. **E2E**（`htf.testing.e2e`）: 定義から (stage, end_state) を列挙、誘発（台本）と注入（2）で覆う計画、カバレッジ報告（誘発 / 注入を区別）、マルコフ合成（5 の行列から run 全体の結果の確率を予測し実測と比べる）
8. **トリアージ**（`htf.testing.triage`）: unknown と低確信度の評価記録を待ち行列（JSONL）に積む、一覧、ラベル付け、コーパスへの書き出し
9. **pytest のマーカー**: `distribution` / `e2e` を分け、CI では今は常時（偽本体）。F5 で段階分け
10. **ADR-013**: F3 で確定した小決定（閾値の仮置き、代表の鍵、並べ替え検定、形式の改訂回数）
11. **版を 0.1.0 に**、v0.1 のゲート項目（ADR-012 / 013 の決定欄）を揃えて報告し、**止まる**。検証役（F3）はゲートの前に起動する

運用規則: 完了条件のテストは実装より先に**別コミット**にし、そのコミットで `uv run pytest` が失敗する出力を progress.md に残す。expectations 形式の改訂は F3 内で 2 回まで（回数を本ファイルに残す。現在 0 回）。検証役の予算は探針を含むなら 25 万トークンを目安にする。

`reports/` の構造: `reports/verification/<task-id>/report.md`、`reports/dynamic/<id>/record.md`、`reports/triage/`（F3 から）。

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

### 発見した問題

#### ワークフロー定義の問題

なし（まだワークフロー定義が存在しない）

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
