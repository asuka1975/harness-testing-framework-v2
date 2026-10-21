# adopting.md — ハーネス側が満たすべきこと（初版、F2）

harness-testing-framework（以下 htf）の上に新しいワークフロー型ハーネスを作る人のための手引き。F5 で software factory を実例に加えた完成版にする。契約の意味は `src/htf/contract/CONTRACT.md`、型は `htf.contract` にある。実例は `examples/toy-minimal/`。

この文書だけで判断できなかったことは、ハーネス側の `docs/adopting-gaps.md` に書く。htf 本体を直したり、ハーネスの中で回避したりしない。

## 1. 役割分担

| htf が定めるもの | ハーネスが提供するもの |
| --- | --- |
| ワークフロースキーマ（`schema/workflow.schema.json`） | ワークフロー定義（`workflow.yaml`。子があれば子の定義） |
| 契約（三操作 run / evaluate / restore + overlay、スナップショット形式、インターフェース） | ステージ本体（`StageBody`）、指標レジストリ（`MetricRegistry`）、ユーザー入出力（`UserIO`）、LLM クライアント（`LLMClient`）、分類器（`Classifier`） |
| 整合性検査器（`htf.testing.spec`） | 指標名のマニフェスト、またはレジストリの `names()` |
| 参照ランタイム（`htf.runtime`: loader / checkpoint / runner / oracle / recorder） | 束縛（`Bindings`）と実行の起動 |
| 契約適合テスト（`htf.contract.conformance`） | テストでの継承（自前ランタイムでも同じ） |
| テストランナー群（`htf.testing.*`） | 台本、フィクスチャ、expectations（F3）、コーパス（F3） |

ハーネス固有の名前や前提（特定のツール、特定のステージ名、特定の LLM）は htf に入らない。入れたくなったら、それは htf の不足として adopting-gaps.md に書く。

## 2. 三層と評価順序（要点）

ステージの結果は必ず三層のどれかに落ちる。

- **goal**（正常系）: `quantitative` は決定論的な指標の基準、`qualitative` は自然言語
- **end_state**（準正常系）: 自然言語で互いに排他に書き、各クラスに戻り先（`rollback`）が一意にある
- **unknown**（例外系）: 必ず含める。人間に差し戻す

評価は毎回この順序: goal 指標 → goal 定性（分類器）→ end_state（分類器）→ unknown。指標が値を返せなければ unknown。指標が不成立なのに分類器が goal を選んだら unknown（不一致として記録）。分類器には goal と end_state の記述がそのまま選択肢として渡る。分類ロジックをコードに書かない。記述が分類の全て。

## 3. 手順

### 3.1 ワークフロー定義を書く

`workflow.yaml` を `schema/workflow.schema.json` に合わせて書く。書き方の例は計画書付録 B と `examples/toy-minimal/workflow.yaml`。

- `artifacts` を各ステージに宣言する: `reads` / `writes`（作業ディレクトリ相対。末尾 `/` はディレクトリ全体）、`memory_in` / `memory_out`（memory の鍵）。本体はこの範囲でだけ読み書きできる
- `memory` は成果物ファイルとは別に、ステージ間を前方に流れる鍵と値。`memory_in` の鍵は、前方のステージの `memory_out`、このステージへの `carry`、または（子なら）`workflow.inputs` のどれかから来る
- `end_state` の記述は、成果物（reads / writes / memory_in）から観測できる条件として書く。goal の言い換えや実行の途中状態を書かない。複数に当てはまりうる時は記述文中に「この状態は X に優先する」と書く
- `rollback` は unknown を除く end_state と一対一。戻り先はそのステージより前。`carry` の各鍵は元ステージの `memory_out` と戻り先の `memory_in` の両方にある。`max` は 1 以上
- ユーザーに質問するステージには `user_input: true`。宣言の無いステージではユーザー入出力を使えない
- 実行時に数が決まる下位作業は `subworkflow`（第 4 節）

### 3.2 整合性検査を通す

```text
uv run python -m htf.testing.spec path/to/workflow.yaml --metrics path/to/manifest.json
uv run python -m htf.testing.spec path/to/workflow.yaml --metrics-module your_pkg.metrics:registry
```

終了コード 0 で通る。所見のコードと意味は `htf.testing.spec.checker` の冒頭にある。`--metrics` は `{"metrics": ["name", ...]}` の JSON。参照ランタイムの `load_workflow` は検査を通らない定義を拒否する（`WorkflowDefinitionError`）。

### 3.3 指標を実装する

`MetricRegistry`（`names()` と `resolve(name)`）を実装する。簡単には `htf.runtime.DictMetricRegistry({"name": fn, ...})`。

- 指標は `Snapshot` を受け取り JSON 値を返す。見えるのは `snapshot.files`（そのステージ、またはフェーズゲートならそのフェーズの全ステージの `writes` の範囲の複製）と `snapshot.memory`。作業ディレクトリ全体は見えない。必要な情報は成果物に書く
- 値を返せない時は例外を投げる。runtime はそれを unknown（評価不能）にする。goal 不成立とは区別される
- 外部ツール（ビルド、テスト、lint）を呼ぶ指標はハーネス側に閉じる。ステージ本体がツールを走らせて結果を成果物に書き、指標はそれを読むのが素直

### 3.4 ステージ本体を実装する

`StageBody.run(ctx)` を実装する。`ctx` は `StageContext`。

```python
class Draft:
    def run(self, ctx: StageContext) -> None:
        inputs = json.loads((ctx.workspace / "inputs.json").read_text())      # reads
        text = ctx.llm.complete(LLMRequest(messages=[...])).text              # recorder 経由
        (ctx.workspace / "draft.md").write_text(...)                          # writes
        ctx.emit("missing_inputs", [...])                                     # memory_out
```

- 読めるのは `ctx.memory`（`memory_in` の鍵だけ）と作業ディレクトリ。書けるのは `writes` の範囲と `memory_out` の鍵だけ。範囲外は `ContractViolation`（参照ランタイムは本体の前後で作業ディレクトリを比較する。`.htf/` は対象外）
- 本体は途中状態を持たない。中断からの再開は開始時スナップショットからの再実行で行われる
- 再進入（ロールバックで戻ってきた）は carry の鍵が `ctx.memory` にあるかで分かる。初回は無い
- `subworkflow` を持つステージの本体は任意。束縛すれば子 run が全て終わった後に走る（子の成果物をまとめる等）

### 3.5 ユーザー入出力

`UserIO.ask(question, schema=None)` を実装する。その場で答えられない実装は `WaitingForUser(question, schema)` を投げる。runner は中断状態で `RunResult(status=SUSPENDED, pending=...)` を返し、`runner.resume(answer)` で回答を累積して開始時スナップショットから再実行する。同じ質問には累積した回答が順に返る。

テストでは `htf.testing.harness.DeferringUserIO`（常に中断）、`QueueUserIO`（回答列）、またはハーネス自身のシミュレータ（`examples/toy-minimal/user/`）を束縛する。

### 3.6 LLM クライアントと分類器

- `LLMClient.complete(request)`。本体は `ctx.llm` 経由でしか呼ばない。recorder を付けると記録され、再生で LLM 無しに同じ実行が得られる
- `Classifier.classify(document, options)`。`document` は reads ∪ writes ∪ memory_in からの投影、`options` は goal と end_state の記述。実 LLM の分類器は ADR-006 の後で用意する。htf のテストは LLM を呼ばず、`htf.testing.harness.MarkerClassifier`（成果物の `outcome` の印を読む）を使う

### 3.7 束縛して実行する

```python
from htf.runtime import Bindings, Runner, load_workflow

workflow = load_workflow("workflow.yaml", metric_names=registry.names())
bindings = Bindings(
    bodies={("my-workflow", "draft"): Draft(), ("my-child", "write"): Write(), ...},  # (workflow 名, stage id)
    registry=registry, classifier=classifier, user=user_io, llm=llm_client, human=decider,
)
result = Runner(workflow, bindings, workspace=Path("ws")).run()
result.status      # completed | aborted | suspended
result.trace       # TransitionRecord の列（7 種の遷移）
result.gates       # フェーズゲートの passed / failed / invalidated
```

- `human` は `HumanDecider`（escalate を受けて `Rerun` / `RollbackTo` / `ContinueAsGoal` / `Abort` のどれかを返す）。テストでは `ScriptedHuman`
- 記録再生: `Runner(..., recorder=Recorder("run.jsonl", mode="record"))` で記録し、`mode="replay"` で再生する。再生時は `llm` / `classifier` / `user` を `None` にしてよい
- 作業ディレクトリ配下の `.htf/` は runner のメタデータ（スナップショットの store）で、本体が触ってはいけない

### 3.8 契約適合テストを通す

```python
import pytest
from htf.contract.conformance import ConformanceRuntime, ConformanceSuite

class TestMyRuntime(ConformanceSuite):
    @pytest.fixture
    def make_runtime(self, tmp_path):
        def factory(workflow_path, bodies, registry, classifier, user) -> ConformanceRuntime:
            ...  # 参照ランタイムなら ReferenceRuntime(load_workflow(...), Bindings(...), workspace=tmp_path / "ws")
        return factory
```

参照ランタイムを組み込むだけでも継承して通す（組み込み方が契約を壊していないことの確認）。自前のランタイムを持つなら、契約を満たすかはこのテストでのみ判定する。

### 3.9 決定論テストを書く

- 偽ステージ本体を台本で制御し、各ステージの各 end_state と、7 種の遷移（next、フェーズ内 / 境界越えロールバック、unknown / max 超過の escalate、中断と再開、子の集約）を少なくとも一度は踏む。台本は本体コードに埋めず、フィクスチャ（YAML）に置く
- `htf.testing.harness.observed_kinds(result.trace)` で観測された遷移種を集める
- escalate の 4 つの解決を `ScriptedHuman` で踏む
- 記録 → 再生で `snapshot_digest` が一致することを確かめる

`examples/toy-minimal/tests/fixtures/scenarios/` と `tests/test_runtime_*.py` が実例。

## 4. 子ワークフロー

```yaml
subworkflow:
  ref: child.yaml        # 同じスキーマの別ファイル。子は更に子を持てない（深さ 1）
  each: items            # memory_in の鍵。値はリスト。要素ごとに子 run を一つ
  item_as: item          # 子に渡す鍵。pass の鍵と合わせて子の workflow.inputs と一致させる
  pass: [shared]
  workspace: items/      # writes のディレクトリ項目の配下。子 run i は items/<i>/ で動く（開始時に空にされる）
  aggregate:             # 上から順に評価。最初に成立した規則の state。どれも無ければ unknown
    - state: unknown                                   # 子の unknown を人間に届けるなら上に置く
      when: { any: { stage: check, state: unknown } }
    - state: items_failed
      when: { any: { stage: check, state: failed } }
```

- 子の escalate（unknown、max 超過）は人間へ行かず、子 run の終わり方として親の集約へ渡る
- 全ての子 run が goal なら親の goal 指標を評価して goal（親では分類器を呼ばない）。そうでなければ規則で end_state か unknown
- 子のステージはユーザー入出力を使えない（v1.0 では未対応）

## 5. ランタイムの規則（参照ランタイム）

- スナップショットはステージの開始時と終了時に `writes` の範囲と memory を保存する。ロールバックは戻り先の開始時スナップショットを復元し、carry の鍵だけを重ねる。復元は戻り先の `writes` の範囲外に触れない（後段の成果物は残る。次に上書きされる）
- 辺 (ステージ, end_state) の通過回数は run 全体で数え、`max` を超えたら escalate。人間の `RollbackTo` は数えない
- フェーズの最終ステージが goal になった時だけフェーズの `quantitative` を評価する（フェーズの全ステージの `writes` の和を一つのスナップショットにする）。不成立なら unknown。前のフェーズへ戻ると通過記録は無効化され、再通過時に再評価する
- `writes` 外への書き込み検出は `Runner(..., strict_writes=False)` で切れる（既定は有効）。`reads` は検査しない

## 6. 迷ったら

- この文書と `CONTRACT.md` で決まらないこと、htf に無い機能、回避したくなったこと → ハーネスの `docs/adopting-gaps.md` に書いて続行する。htf の修正は htf 側の通常のセッションが行う
- end_state の記述の良し悪し（観測可能か、排他か）は検査器では見ない。人間のレビューに出す前に、実装していない第三者に読ませる
