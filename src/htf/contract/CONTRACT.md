# ハーネス契約（v0.1 草案、F1 の人間ゲート対象）

フレームワークとハーネスの境界を定める。フレームワークは契約を定め、ハーネスは契約を満たすもの（ワークフロー定義、ステージ本体、指標の実装、ユーザー入出力、LLM クライアント）を提供する。型は `types.py`、インターフェースは `interfaces.py`。この文書は意味を書く。

ここに書くのは契約であって実装ではない。参照ランタイム（`htf.runtime`、F2）はこの契約を満たす一実装で、ハーネスが自前のランタイムを持つ場合も同じ契約適合テスト（F2）で判定する。

## 1. 用語

- **ワークフロー定義**: `schema/workflow.schema.json` に適合する YAML。実行時の遷移とゲートはすべてここから駆動され、コードにステージ順や遷移を書かない
- **作業ディレクトリ**: ステージ本体が成果物を読み書きする場所。`artifacts.reads` / `writes` は作業ディレクトリ相対。末尾 `/` はディレクトリ全体
- **memory**: 鍵と JSON 値の集まり。成果物ファイルと別に、ステージ間で前方に流れる。`memory_out` に宣言した鍵だけが生成され、`memory_in` に宣言した鍵だけが見える
- **スナップショット**: あるステージの開始時または終了時の状態。`writes` の範囲の成果物の複製と、memory の全体
- **carry**: ロールバック時に、戻り先の開始時スナップショットに重ねる memory の項目。辺ごとに `rollback.carry` で宣言する
- **三層**: goal（正常系）、end_state（準正常系。各クラスに戻り先が一意）、unknown（例外系。人間に差し戻す）

## 2. 三操作

| 操作 | 入力 → 出力 | 意味 |
| --- | --- | --- |
| `run(stage, snapshot)` | 開始時スナップショット → 終了時スナップショット | 作業ディレクトリを開始時の状態にし、ステージ本体を実行し、終了時の状態を取る。`subworkflow` を持つステージでは子 run の起動と集約を含む（第 7 節） |
| `evaluate(stage, snapshot)` | 終了時スナップショット → Verdict | 第 4 節の順序で三層に落とす |
| `restore(snapshot)` | 開始時スナップショット → 同じ内容のスナップショット | 作業ディレクトリをその開始時の状態に戻す。`writes` の範囲外には触れない |
| `overlay(snapshot, carry)` | 復元したスナップショット × carry → スナップショット | carry の項目だけを memory に重ねる。戻り先の `memory_in` に無い鍵は `ContractViolation` |

ロールバックは `restore` と `overlay` の二操作の合成で、それ以外の操作を持たない。戻り先の開始時スナップショットは、その戻り先のステージを最後に開始した時のもの。

## 3. スナップショット形式

```text
<store>/<ordinal>/
  meta.json      workflow, version, stage_id, moment（start | end）, ordinal, taken_at
  memory.json    memory の全体（JSON オブジェクト）
  files/         そのステージの artifacts.writes の範囲の成果物の複製（相対パスを保つ）
```

- `moment: start` は本体実行前、`end` は実行後に取る。`ordinal` は run 内の通し番号
- 保存するのは `writes` の範囲だけ。`reads` は前方のステージの `writes` に含まれる前提で、保存しない（復元時には戻り先より前のステージの終了時 files が作業ディレクトリに残っている）
- memory は `writes` と独立に全体を保存する。`restore` は memory も開始時のものに戻し、`overlay` で carry を重ねる
- 子 run のスナップショットは子の作業ディレクトリ配下の独立した store に取る（第 7 節）

## 4. 評価順序と Verdict

`evaluate` は一回の実行ごとに、この順で判定する。順序は固定で変えない（第2節「評価順序」）。

1. **goal 指標（quantitative）**: `goal.quantitative` の各指標をレジストリから解決し、終了時スナップショットで計算して基準（`equals` / `min` / `max`）と比べる。
   - 指標が値を返せない（例外）→ `UNKNOWN`（`decided_by: quantitative`）。goal 不成立とは区別する
   - すべて成立 → 2 へ。一つでも不成立 → 3 へ（分類器には同じ呼び出しで聞くが、goal の選択肢は採らない）
2. **goal 定性判定**: 分類器に状態文書（第 5.4 節）と選択肢（`goal.qualitative`、各 `end_state.description`。unknown を含む）を渡す。goal が選ばれ、確信度が閾値以上 → `GOAL`（`decided_by: qualitative`）
3. **end_state 分類**: unknown 以外の end_state が選ばれ、確信度が閾値以上 → `END_STATE(state)`（`decided_by: classifier`）
4. **unknown**: 上記のいずれでもない（unknown が選ばれた、または確信度が閾値未満）→ `UNKNOWN`（`decided_by: threshold`）

閾値は分類器の較正結果から決め、根拠を記録する（第2節「分類器の検証」。F1 では未定）。`subworkflow` を持つステージでは 2 と 3 を集約規則で置き換える（第 7 節）。

**フェーズゲート（決定 #5）**: フェーズの最終ステージが `GOAL` になった時だけ、`phase.goal.quantitative` を同じスナップショットで評価する。成立 → ゲート通過を記録して次のフェーズへ。不成立 → フェーズに戻り先が無いので `UNKNOWN` として escalate。前のフェーズのステージへロールバックしたら、その境界以降のゲート通過記録を無効化し、再び最終ステージを `GOAL` で抜けた時に再評価する。`phase.goal.qualitative` は文書上の説明で、分類器には渡さない。

## 5. ハーネスが提供するもの

### 5.1 ステージ本体（StageBody / StageContext）

- `run(ctx)` は `ctx.workspace` に成果物を書き、`ctx.emit(key, value)` で memory を出す
- 読めるのは `ctx.memory`（`memory_in` の鍵だけ）と作業ディレクトリ。書けるのは `writes` の範囲と `memory_out` の鍵だけ。範囲外は `ContractViolation`（参照ランタイムは終了時スナップショットを取る時に `writes` 外の変更を検出する）
- `ctx.user` は `user_input: true` のステージでだけ使える。`ctx.llm` は recorder 経由で、記録があれば再生する。フレームワークのテストはこの再生だけで通る
- 本体は途中状態を持たない。中断（第 6 節）からの再開は、開始時スナップショットからの再実行で行う

### 5.2 指標（Metric / MetricRegistry、決定 #2）

- YAML には指標名と基準だけ。実装はハーネス側のレジストリにあり、`names()` と `resolve(name)` を持つ
- 指標はスナップショットから決定論的に計算する。外部ツール（ビルド、テスト、lint）を呼ぶ指標はハーネス側に閉じ、フレームワークは名前と値しか知らない
- 整合性検査器は `names()`（またはマニフェスト `{"metrics": [...]}`）で「YAML が参照する指標がすべてレジストリにある」を検査する

### 5.3 ユーザー入出力（UserIO、決定 #4）

- `ask(question, schema=None) -> JsonValue`。ステージ本体は同期的に呼ぶだけで、待ち方を知らない
- その場で答えられない実装は `WaitingForUser` を投げる。runner はこれを捕まえて中断状態に入り、保留中の質問と開始時スナップショットを保存して終了する。回答が来たら、回答列に加えて開始時スナップショットから再実行する（回答は累積し、再実行で同じ質問に同じ回答を返す）
- テストではシミュレータ（ペルソナ）を束縛する。recorder はユーザー回答も記録再生の対象にする

### 5.4 LLM クライアントと分類器（LLMClient / Classifier）

- `LLMClient.complete(request)`。ステージ本体は `ctx.llm` 経由でしか呼ばない（recorder を通す）
- `Classifier.classify(document, options)`。選択肢は goal の記述と end_state の記述をそのまま渡し、分類ロジックをコードに書かない。優先順は記述文中の「〜に優先する」で表す（決定 #7）
- 状態文書は `reads ∪ writes ∪ memory_in` から投影する。スナップショット全体や作業ディレクトリ全体を渡さない

### 5.5 人間（HumanDecider、決定 #3）

escalate を受けて四つのどれかを返す。`Rerun`（同じ開始時スナップショットから再実行。max に数えない）、`RollbackTo(stage, carry)`（前方のステージへ。辺の max を消費しない。carry は明示した項目だけで、戻り先の `memory_in` に無い鍵は拒否）、`ContinueAsGoal(note)`（goal 到達扱いで続行。note 必須。記録に人間の上書きとして残り、goal 到達率には混ぜない）、`Abort`。

## 6. 遷移の種類

runner が起こす遷移は次の 7 種（`TransitionKind`）。計画書 F2 の「6 種」に、決定 #9 (b) による集約を加えた。

| 種類 | 起きる条件 | 動作 |
| --- | --- | --- |
| `next` | `GOAL`（フェーズ最終ステージならゲートも通過） | 次のステージへ |
| `rollback_within_phase` | `END_STATE(s)` で戻り先が同じフェーズ | `restore` + `overlay(carry)`、辺 (stage, s) の計数を +1 |
| `rollback_across_phase` | `END_STATE(s)` で戻り先が前のフェーズ | 同上に加え、境界以降のゲート通過記録を無効化 |
| `escalate_unknown` | `UNKNOWN` | 人間へ（第 5.5 節）。子 run の中では親の集約へ |
| `escalate_max_exceeded` | 辺の計数が `max` を超える | 同上 |
| `suspend_resume` | `WaitingForUser` | 中断し、回答後に開始時スナップショットから再実行 |
| `subworkflow_aggregate` | `subworkflow` を持つステージの子 run がすべて終わった | 集約規則で親の Verdict を決める（第 7 節） |

辺の計数は (ステージ, end_state) ごとに持ち、戻り先より前へ別のロールバックで戻った時にリセットしない（上限は run 全体で有効）。計数のリセットが必要になったら契約の属性として起票する。

## 7. 子ワークフロー（決定 #9 (b)）

`subworkflow` を持つステージの `run` は次を行う。

1. `each` の鍵（`memory_in`）の値はリスト。要素 i ごとに子 run を一つ、作業ディレクトリ `<workspace><i>/` で起動する。子の memory の初期値は `{item_as: 要素, pass の各鍵: 親の値}` で、これが子の `workflow.inputs` と一致する（検査器が確かめる）
2. 子 run は独立した runner として子の定義を実行する。子のスナップショット store は子の作業ディレクトリ配下。子の中の escalate（unknown、max 超過）は人間へ行かず、その子 run の `ChildOutcome(stuck | unknown, stage, state)` になる。すべてのステージを `GOAL` で抜けた子 run は `ChildOutcome(goal)`
3. 子 run がすべて終わったら、親のステージ本体（束縛されていれば）を実行する。子の成果物は `workspace` 配下にあり、親の `writes` に含まれる
4. 親の `evaluate`: goal 指標 → すべての子 run が `goal` なら `GOAL`（goal 定性判定は子の中で済んでいるものとし、親では分類器を呼ばない）→ そうでなければ `aggregate` を上から順に評価し、最初に成立した規則の `state` に落ちる（`decided_by: aggregate`）→ どれも成立しなければ `UNKNOWN`（人間へ。`cause: child_unresolved`）
   - `any: {stage, state}`: 一つ以上の子 run がその (stage, state) で終わった。`all`: すべての子 run がその (stage, state) で終わった
   - 子の unknown を親の end_state に写すと、その unknown は人間に届かない。写すかどうかはハーネス側の判断で、写さなければ親の unknown として人間へ行く
5. 入れ子の深さは 1 まで（子は `subworkflow` を持てない）。recorder は子 run も記録再生する

## 8. 契約適合テスト（F2 で作る）

任意の `Runtime` 実装が通すべきもの。toy-minimal の定義と決定論的な偽ステージ本体で、次を確かめる。

- 7 種の遷移がすべて起きる。escalate の 4 つの解決が動く
- `restore` + `overlay` の後の作業ディレクトリと memory が、戻り先の開始時スナップショットに carry だけを重ねたものと一致する
- `writes` 外への書き込み、未宣言の鍵への `emit`、未宣言ステージでの `ctx.user` が `ContractViolation` になる
- 記録再生で同一スナップショットが得られる
- 指標が例外を投げた時に `UNKNOWN(decided_by: quantitative)` になる
- 子 run の集約が第 7 節のとおりに動く

## 9. 未定（F2 以降で決める）

- 分類器の確信度の閾値（較正結果から）
- 中断状態の永続化の形式（保留中の質問、回答列）
- 一つのステージが出せる質問数の上限
- 辺の計数のリセット規則（必要になった時）
