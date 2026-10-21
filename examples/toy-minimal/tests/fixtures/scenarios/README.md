# 台本の規則

- `outcomes`: ステージ id → n 回目の進入の結果。足りなければ**最後を繰り返す**。無いステージは goal。単発の end_state を書くつもりなら `[x, goal]` と書く（`[x]` は max を超えるまで x が続く）
- `child_runs`: 子 run の開始順に、各ステージの n 回目の結果（同じ規則）。尽きたら全て goal。子 run の始まりは「carry（inconsistencies）の無い write_section の進入」で判定する。子 run には人間の解決（Rerun、carry 無しの RollbackTo）が届かないので、この判定は v1.0 では誤らない
- `empty_grounds_first`: 初回の collect で根拠ファイルを空で書く主張（draft が inputs_insufficient になる）
- `user`: `simulator`（ペルソナが即答）| `deferring`（常に中断。`answers` を resume で与える）
- `human`: escalate のたびに返す解決。`abort` | `rerun` | `continue_as_goal` | `rollback_to:<stage>`
- `expect`: `status`、`transitions`（遷移種の列）、任意で `gates`（`phase:event` の列）
- verify の結果に使える値: `goal` | `goal_assumed`（一部の主張を仮定として理由つきで記録。印は goal）| `checks_failed` | `inputs_missing` | `unknown` | `low_confidence`（印が閾値未満 → unknown）

## 確率的な構成（profiles/*.yaml）

- `distributions`: ステージ → `first` | `reentry` → クラス → 確率。再進入は供給元が (stage, claim) ごとに数える（runtime の進入回数と同じ規則）
- `split`: `stage` の分布を主張の偶奇で差し替える（`odd_claims` / `even_claims` に `first` / `reentry` の分布）。クラス内で代表ごとに下流が分かれる構成を作るためのもの
- `human`: escalate のたびに返す解決（最後を繰り返す）
- 親側のクラス（verify の checks_failed など）の代表: 失敗した主張は供給元の `pick` で選ぶ（決定論的な台本では先頭、確率的構成では種つきで一様）
