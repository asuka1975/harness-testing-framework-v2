# 台本の規則

台本は「LLM が決めるはずの結果」だけを決める。成果物から結果が決まるもの（実ツールの結果、ペルソナの回答、要件の中身）は台本では変えられない。印（`outcome`）は本体が本物の結果から書く。

## 項目

- `persona`: intake / release に答えるペルソナ（`fixtures/personas/`）。既定は `product_owner`
  - `product_owner`: 過不足なく答え、常に承認する
  - `end_user`: 切り詰めの仕方を曖昧に言う → analyze が `ambiguous`。Q1 には具体的に答える
  - `domain_expert`: R4（かな・漢字を残す slug）を持ち込む → design が `requirements_conflict`。合意なしの見送りがあるとリリースを承認しない
  - `busy_sponsor`: 要求には即答するが、リリースの承認はその場で答えない（release で中断）
- `user`: `simulator`（ペルソナ）| `deferring`（常に中断）。中断した run には `answers` を順に `resume` で与える
- `outcomes`: 親のステージ id → n 回目の進入の値。足りなければ**最後を繰り返す**。無いステージは `goal`。単発のつもりなら `[x, goal]` と書く
- `child_runs`: 子 run の**開始順**に、子のステージ（`code` / `unit_test`）の n 回目の進入の値（同じ規則）。尽きた子 run は全て既定。子 run の始まりは「carry（`test_failures` / `coverage_gaps`）の無い code の進入」で判定する。implement に入るたびに子 run は tasks の順（T1, T2, ...）に起動する
- `human`: escalate のたびに返す解決。`abort` | `rerun` | `continue_as_goal` | `rollback_to:<stage>`
- `expect`: `status`、`transitions`（親の遷移種の列）、任意で `child_runs`（implement の進入ごとの子 run の数）、`child_transitions`（最初の進入の子 run ごとの遷移種の列）

## 値

本体は進入のたびに一度だけ値を取る。成果物から結果が決まる時は、取った値を使わない（数だけ進む）。

| ステージ | 値 | 成果物から決まる結果（台本の値より強い） |
| --- | --- | --- |
| intake | `goal` / `unknown` / `low_confidence` | 回答が欠けていれば指標が不成立 |
| analyze | `goal` / `unknown` / `low_confidence` | 回答の無い質問があれば `ambiguous` |
| design | `goal` / `requirements_conflict` / `unknown` / `low_confidence` | 実在する衝突（R1 と R4）があれば `requirements_conflict` |
| plan | `goal`（3 タスク）/ `two_tasks`（2 タスク、goal）/ `design_gap` / `unknown` / `low_confidence` | なし |
| code | `correct` / `failing` / `failing_edge` / `low_coverage` / `regression` / `missing_test` / `lint` / `broken` / `out_of_scope` / `unknown` / `low_confidence` | ビルド・lint・変更パスのどれかが不成立なら `unknown` |
| unit_test | `goal` / `unknown` / `low_confidence` | テストの失敗 → `tests_failing`、カバレッジ不足 → `coverage_low` |
| verify | `goal` / `unknown` / `low_confidence` | スイートの失敗 → `regression`、受け入れ基準のテストの不在 → `criteria_unmet` |
| review | `goal` / `changes_requested` / `design_flaw` / `unknown` / `low_confidence` | なし |
| release | `goal` / `unknown` / `low_confidence` | 依頼者が承認しなければ `rejected` |

- `low_confidence` は印が閾値未満の goal（→ unknown の経路）、`unknown` は分類器が unknown を選ぶ印
- code の変種は fixtures/codebase/changes/<機能>/<変種>/ にある（correct の上に重ねる）。`regression` は slug にしか無く、他の機能では correct になる
  - `failing`: 主要な振る舞いの誤り（slug: 小文字にしない）。`failing_edge`: 端の場合の誤り（slug: 空文字を untitled にする）
  - `low_coverage`: テストの無い分岐を足す。`missing_test`: 受け入れ基準のテストを一つ書かない（カバレッジは保つ）
  - `regression`: normalize_whitespace を小文字化に変える（slug の単体テストは通り、既存の test_normalize が落ちる）
  - `lint`: 未使用の import / 変数。`broken`: 構文エラー。`out_of_scope`: task.scope の外の `src/textkit/__init__.py` を変える

## 確率的な構成（../profiles/*.yaml）

- `distributions`: ステージ → `first` | `reentry` → 値 → 確率。値は上の表と同じ。再進入は供給元が (ステージ, タスク) ごとに数える（runtime の進入回数と同じ規則。子 run の始まりでそのタスクの計数を消す）
- `split`: `stage` の `unit`（タスク id）だけ分布を差し替える。そのタスクの振る舞いは子 run をやり直しても持続する（クラス内で代表ごとに下流が分かれる構成）
- `persona`、`human`（escalate のたびに返す解決。最後を繰り返す）
