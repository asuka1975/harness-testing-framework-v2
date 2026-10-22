# adopting.md — ハーネス側が満たすべきこと（完成版、v1.0）

harness-testing-framework（以下 htf）の上に新しいワークフロー型ハーネスを作る人のための手引き。契約の意味は `src/htf/contract/CONTRACT.md`、型は `htf.contract` にある。実例は二つ: `examples/toy-minimal/`（最小。契約と全遷移種別）と `examples/software-factory/`（ソフトウェア開発のワークフロー。実ツールを走らせる指標、子ワークフロー、ペルソナ、分布テストと E2E まで一通り。この文書と雛形だけを読んだ別セッションが作り、その往復で足りなかったことを直した）。手順は第 3 節、実例の一巡は第 8 節、落とし穴は第 9 節。計画書の雛形は `docs/harness-plan-template.md`、運用は `docs/maintenance.md`。

この文書だけで判断できなかったことは、ハーネス側の `docs/adopting-gaps.md` に書く。htf 本体を直したり、ハーネスの中で回避したりしない（software factory の記録: `examples/software-factory/docs/adopting-gaps.md`。23 件すべて htf 側で処置した）。

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
- 親子でステージ id を重ねない（検査器 `unique_ids`。分布の集計と expectations の鍵はステージ id なので混ざる）。親子で `workflow.name` も重ねない
- memory の鍵は一つのステージだけが `memory_out` に書くのが素直。複数が書くことは禁じていないが、後に走ったものが上書きする
- **最初のステージは unknown 以外の end_state を持てない**（戻り先は自ステージより前）。自分の goal 指標の不成立をそのステージで準正常にはできないので、直させたい失敗は後ろの「検出するステージ」で判定し、そこから「直すステージ」へ戻す（検出と修正を分ける）
- **二段続けて戻ると最初の carry は消える**。復元は戻り先の**直近の**開始時スナップショット（memory の全体を含む）を戻し、carry の鍵だけを重ねる。鍵 x を受け取ったステージ T の開始時 memory には x が入っているので、後で T へ戻っても x は残る。消えるのは T より前のステージ S へ戻る時（S の開始時には x が無い）。機械的な規則は閉包: **辺 src → S の carry = 自分の鍵 ∪ 戻り先が S より後ろにある全ての辺の carry の鍵**（検査器の約束どおり、通過用の鍵も src の `memory_out` と S の `memory_in` に並べる。実例: `examples/software-factory/workflow.yaml`）。または戻り先を一段にする。また戻り先が前回書いた成果物は消えて作り直しになるので、carry に前の成果物の id を入れても作り直した成果物と対応する保証は無い。再計画で id が変わりうるなら、id を維持する約束か、分割・統合の対応を成果物に残す約束を記述に書く
- `rollback.max` は **run 全体での辺ごとの上限**。別の原因で同じ辺を使っても消費する（例: 一度 review → design を使った後、release から戻った周回でもう一度 review の design_flaw が出ると max 1 を超えて escalate）。頻度を見て値を決める
- ステージ定義の例（計画書付録 B の要点。実例は `examples/toy-minimal/workflow.yaml` と、検出と修正の分離・carry の閉包・優先の文言を備えた `examples/software-factory/workflow.yaml`（版 0.2））:

```yaml
- id: verify
  name: Verify
  description: draft.md の主張を検証し、結果を report.json に書く
  artifacts:
    reads: [draft.md]
    writes: [report.json]
    memory_in: [review_findings]
    memory_out: [failing_checks, missing_inputs]
  goal:
    qualitative: draft.md の全ての主張が report.json で検証済みとして記録されている
    quantitative:
      report_exists: { description: report.json が存在する, equals: true }
      verified_ratio: { description: 主張のうち検証済みの割合, min: 0.8 }
  end_state:
    - id: checks_failed
      description: 一つ以上の主張が検証に失敗している。失敗した検査の一覧が report.json にある。この状態は inputs_missing に優先する。
    - id: inputs_missing
      description: 検証に必要な入力が draft.md にも作業ディレクトリにも無い。
    - id: unknown
      description: 上記に当てはまらない、または分類の確信度が低い。人間に差し戻す。
  rollback:
    - { state: checks_failed, stage: draft, carry: [failing_checks], max: 2 }
    - { state: inputs_missing, stage: collect, carry: [missing_inputs], max: 1 }
```

### 3.2 整合性検査を通す

```text
uv run python -m htf.testing.spec path/to/workflow.yaml --metrics path/to/manifest.json
uv run python -m htf.testing.spec path/to/workflow.yaml --metrics-module your_pkg.metrics:registry
```

終了コード 0 で通る。所見のコードと意味は `htf.testing.spec.checker` の冒頭にある。`--metrics-module` は import できる名前のパッケージ用で、`examples/` のようなハイフン名のディレクトリのハーネスでは使えない。その場合はマニフェスト（`--metrics`）を使い、レジストリの `names()` との一致をテストで確かめる。`--metrics` は `{"metrics": ["name", ...]}` の JSON。参照ランタイムの `load_workflow` は検査を通らない定義を拒否する（`WorkflowDefinitionError`）。

### 3.3 指標を実装する

`MetricRegistry`（`names()` と `resolve(name)`）を実装する。簡単には `htf.runtime.DictMetricRegistry({"name": fn, ...})`。

- 指標は `Snapshot` を受け取り JSON 値を返す。見えるのは `snapshot.files`（そのステージ、またはフェーズゲートならそのフェーズの全ステージの `writes` の範囲の複製）と `snapshot.memory`。作業ディレクトリ全体は見えない。必要な情報は成果物に書く
- 値を返せない時は例外を投げる。runtime はそれを unknown（評価不能）にする。goal 不成立とは区別される
- 指標が読んでよいもの: `snapshot.files`、`snapshot.memory`、ハーネスの静的な資産（fixtures のコードベースなど。決定論は崩れない）。他のステージの成果物は読めないので、必要な情報は本体が自分の成果物に写す
- 外部ツール（ビルド、テスト、lint）を呼ぶ指標はハーネス側に閉じる。ステージ本体がツールを走らせて結果を成果物に書き、指標はそれを読むのが素直
- 本体の中で実ツールを走らせる時: ツールの副産物（`__pycache__`、`.pytest_cache`、`.coverage`、lint のキャッシュ）が `writes` 外に出ると `ContractViolation` になる。バイトコードとキャッシュを作業ディレクトリの外に向け、外側の pytest の環境変数を子プロセスに持ち込まない。出力から時刻・所要時間・絶対パスを落とす（記録 → 再生の digest 一致のため）
- 分布テスト（N = 数百）で実ツールを走らせると時間がかかる。同じ入力には同じ出力なので、ハーネス側で結果をメモ化するか、記録した結果を使う（実例: `examples/software-factory/toolchain.py`）

### 3.4 ステージ本体を実装する

`StageBody.run(ctx)` を実装する。`ctx` は `StageContext`。

```python
from htf.contract import LLMRequest, StageContext

class Draft:
    def run(self, ctx: StageContext) -> None:
        inputs = json.loads((ctx.workspace / "inputs.json").read_text())      # reads
        text = ctx.llm.complete(LLMRequest(messages=[...])).text              # recorder 経由
        (ctx.workspace / "draft.md").write_text(...)                          # writes
        ctx.emit("missing_inputs", [...])                                     # memory_out
```

- 読めるのは `ctx.memory`（`memory_in` の鍵だけ）と作業ディレクトリ。書けるのは `writes` の範囲と `memory_out` の鍵だけ。範囲外は `ContractViolation`（参照ランタイムは本体の前後で作業ディレクトリを比較する。`.htf/` は対象外）
- 本体は途中状態を持たない。中断からの再開は開始時スナップショットからの再実行で行われる
- 再進入は `ctx.entry`（この run での進入回数。1 始まり）と `ctx.reentry`（`entry > 1`）で分かる（ADR-014 14.2）。carry の鍵が `ctx.memory` にあるかでも分かるが、人間の `Rerun` や carry 無しの `RollbackTo` による再実行は carry では区別できず、`entry` では区別できる
- 分布の集計（第 6 節）の first / reentry は runtime の進入回数で決まる（その run でそのステージに 2 回目以降に入ったら reentry。carry の有無によらず、前のステージへのロールバックの後に通り直しただけでも reentry。中断からの再開は数えない。子 run は run ごとに 1 から）。`ctx.entry` は同じ規則なので、確率的偽本体は first / reentry の分布を `ctx.reentry` で使い分けられる（toy-minimal の `StochasticSource` は本体の側で数えているが、同じ値になる）
- 状態文書は 1 ファイル 4000 文字で切られる（`Runner(max_file_chars=)` で変えられる）。文書全体の上限は既定で無く、`Runner(max_document_chars=)` で付けられる（`reads` にコードベースのようなディレクトリを宣言するステージでは付ける。分類器が実 LLM なら文脈長に直撃する）。切り詰めは明示の印で示す。大きな成果物は要旨（印、失敗の一覧、要約）を先頭に置き、詳細は別ファイルにする（ADR-014 14.5）
- 復元は戻り先の `writes` の範囲外に触れないので、再進入した本体から後段の成果物（前回の実行が残したもの）が見える。`reads` は検査されない。後段の成果物に依存する本体を書かない
- `subworkflow` を持つステージの本体は任意。束縛すれば子 run が全て終わった後に走る。子の成果物（`workspace` 配下）をまとめて `memory_out` に出す（carry に使う）のは本体の役目。子 run の作業ディレクトリはステージに入るたびに空にされる
- 作業ディレクトリ配下の `.htf/` は runner のメタデータ。本体が読み書きしても検出されず、結果は未定義

### 3.5 ユーザー入出力

`UserIO.ask(question, schema=None)` を実装する。その場で答えられない実装は `WaitingForUser(question, schema)` を投げる。runner は中断状態で `RunResult(status=SUSPENDED, pending=...)` を返し、`runner.resume(answer)` で回答を累積して開始時スナップショットから再実行する。累積した回答は **ask の順序**で返る（質問文は照合しない）ので、本体は毎回同じ順で質問する。束縛した UserIO が即答した回答も累積列に入るので、「知っている質問には即答し、知らない質問で中断する」シミュレータが書ける。累積列はそのステージに入り直した時（ロールバック、Rerun）に消える。`ask` に文脈を渡す欄は無い（質問文に構造を埋める）。再開できるのは `Runner` オブジェクトが生きている間だけ（中断状態の永続化は未定。CONTRACT 第 9 節）。

```python
result = runner.run()
while result.status is RunStatus.SUSPENDED:
    answer = ask_the_human(result.pending.question)   # 別のプロセスや UI で
    result = runner.resume(answer)
```

テストでは `htf.testing.harness.DeferringUserIO`（常に中断）、`QueueUserIO`（回答列）、またはハーネス自身のシミュレータ（`examples/toy-minimal/user/`）を束縛する。

質問の根拠（見送られた要件、失敗の一覧など）を構造で渡したい時は `ctx.user.ask(question, schema=..., context={...})`（ADR-014 14.4）。シミュレータや実 UI は `context` を表示や判断に使ってよいが、質問文は `context` 無しでも答えられる形にする。`context` は recorder に要求の一部として記録される。自作の `UserIO` は `context=None` の引数を受け取る（runtime は None の時は渡さないので、受け取らない実装も当面は動く）。

### 3.6 LLM クライアントと分類器

- `LLMClient.complete(request)`。本体は `ctx.llm` 経由でしか呼ばない。recorder を付けると記録され、再生で LLM 無しに同じ実行が得られる
- `Classifier.classify(document, options)`。`document` は memory_in ∪ writes ∪ reads からの投影、`options` は goal と end_state の記述（`id` は `goal` と各 end_state id。unknown を含む）。確信度が閾値未満なら unknown。閾値は `Runner(threshold=...)` で、既定の 0.5 は仮置き（較正で決める。ADR-012 12.23）。実 LLM の分類器は ADR-006 の後で用意する
- 投影（状態文書）の形式: `# stage: <id>` / `## memory_in`（鍵ごとに JSON）/ `## writes`（このステージの成果物。判定の根拠）/ `## reads`（前方の成果物。参照）の順（パスごとに `### <path>` と内容。ディレクトリは配下の全ファイル。1 ファイル 4000 文字で切る。文書全体の上限は `max_document_chars`）。`htf.runtime.project(stage, snapshot, workspace)` で同じ文書が得られる。印を読む偽の分類器（`MarkerClassifier`）は `## writes` 節だけを見る
- htf のテストは LLM を呼ばない。偽ステージ本体が成果物に印（`"outcome": "<id>"` か行 `outcome: <id>`）を書き、`htf.testing.harness.MarkerClassifier` が状態文書の `## writes` 節からその印を読んで選択肢として返す。`low_confidence` の印は閾値未満（unknown の経路）、選択肢に無い印は unknown

### 3.7 束縛して実行する

```python
from htf.runtime import Bindings, Runner, load_workflow

workflow = load_workflow("workflow.yaml", metric_names=registry.names())
bindings = Bindings(
    bodies={("my-workflow", "draft"): Draft(), ("my-child", "write"): Write(), ...},  # (workflow 名, stage id)
    registry=registry, classifier=classifier, user=user_io, llm=llm_client, human=decider,
)
result = Runner(workflow, bindings, workspace=Path("ws")).run()
result.status         # completed | aborted | suspended
result.trace          # TransitionRecord の列（7 種の遷移）
result.gates          # フェーズゲートの passed / failed / invalidated
result.child_results  # 子を持つステージ id → 進入ごと → 子 run ごとの RunResult
```

- `bodies` の鍵は (workflow 名, stage id)。親子で `workflow.name` が同じだと衝突する（検査器は未対応。ADR-012 12.13）
- `human` は `HumanDecider`（escalate を受けて `Rerun` / `RollbackTo` / `ContinueAsGoal` / `Abort` のどれかを返す）。最上位の Runner で escalate が起きたのに `human` が無ければ `ContractViolation`。テストでは `ScriptedHuman`
- 記録再生: `Runner(..., recorder=Recorder("run.jsonl", mode="record"))` で記録し、`mode="replay"` で再生する。再生時は `llm` / `classifier` / `user` を `None` にしてよい。中断再開を含む run も記録再生できる（回答は本体が受け取った時点で一度ずつ記録され、再生では記録から来るので中断しない）。再生の終わりに未消費の記録が残っていれば `ReplayMismatch`
- `registry.names()` が指標名の正本。整合性検査を CI で import 無しに回すためにマニフェスト（`{"metrics": [...]}`）を置く場合は、両者の一致をテストで確かめる（toy-minimal の `metrics/__init__.py`）
- ハーネスを `examples/` のようなハイフン名のディレクトリに置く場合、テストからは `htf.testing.harness.load_example_package(root, "pkg_name")` でパッケージとして読む（htf リポジトリでは `tests/conftest.py`）
- ハーネスのテストはハーネスの `tests/` に置き、CI では明示的に走らせる（htf リポジトリの CI は `uv run pytest examples/software-factory/tests` を別のステップにしている。本体の `testpaths` には入れない）
- 人間の `RollbackTo` も遷移の記録では `rollback_within_phase` / `rollback_across_phase`（`note="human"`）になる。台本の期待はそのつもりで書く

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

参照ランタイムを組み込むだけでも継承して通す（組み込み方が契約を壊していないことの確認）。スイートが判定するのは契約の `start` と三操作（run / evaluate / restore + overlay。CONTRACT 第 2 節）で、定義は同梱の `conformance.yaml`。制御ループの振る舞い（7 種の遷移、escalate の 4 解決、記録再生、子の集約）は参照ランタイムのもので、自前のランタイムを持つなら 3.9 の決定論テストを自前のランタイムに対しても書く。

### 3.9 決定論テストを書く

- 偽ステージ本体を台本で制御し、各ステージの各 end_state と、7 種の遷移（next、フェーズ内 / 境界越えロールバック、unknown / max 超過の escalate、中断と再開、子の集約）を少なくとも一度は踏む。台本は本体コードに埋めず、フィクスチャ（YAML）に置く
- 偽本体の設計指針: (1) 本体は宣言どおりに成果物を書き、「LLM が決めるはずの結果」だけを台本から取る。指標は成果物から本物の値を計算する。(2) 結果は成果物の中に印（3.6）として残し、偽分類器がそれを読む。(3) 台本は「ステージ id → n 回目の進入の結果」の列で、足りなければ最後を繰り返す等の規則を台本のそばに書く（`examples/toy-minimal/tests/fixtures/scenarios/README.md`）。(4) 子 run の台本は子 run の開始順に並べ、子 run の始まりを本体が見分けられる根拠（carry の有無など）を明記する
- `htf.testing.harness.observed_kinds(result.trace)` で観測された遷移種を集める
- escalate の 4 つの解決を `ScriptedHuman` で踏む
- 記録 → 再生で `snapshot_digest` が一致することを確かめる

`examples/toy-minimal/tests/fixtures/scenarios/` と `tests/test_runtime_*.py` が実例。

## 4. 子ワークフロー

実例: software factory の `implement`（タスクごとに `implement-task.yaml` を起動し、子の check / unit_test の止まり方を集約で `tasks_unfinished` に写す。統合は次の `integrate` が行う）。

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

- `pass` の鍵が親の memory に無い時（carry でしか来ない鍵の初回進入など）は、その鍵を子に渡さずに起動する（子の `memory_in` には無いものとして見える）。子の `inputs` は「親が供給しうる鍵」の宣言で、毎回あることの保証ではない
- 子の escalate（unknown、max 超過）は人間へ行かず、子 run の終わり方として親の集約へ渡る
- 子を持つステージの本体（子 run の後に走る）は `ctx.child_outcomes` で子 run の終わり方（goal / stuck / unknown と、止まったステージと状態）を読める（ADR-014 14.3）。集約の判定は runtime が `aggregate` 規則で行うので、本体はこれを成果物の事実と併せて要旨（未完了のタスクなど）を書くのに使う。分類の記述をコードに写さない
- 全ての子 run が goal なら親の goal 指標を評価して goal（親では分類器を呼ばない）。そうでなければ規則で end_state か unknown
- 子のステージは `user_input` を宣言できない（整合性検査 `subworkflow_user_input` が落とす。v1.0 では未対応）。親子で `workflow.name` は重複しない（`subworkflow_ref`）

## 5. ランタイムの規則（参照ランタイム）

- スナップショットはステージの開始時と終了時に `writes` の範囲と memory を保存する。ロールバックは戻り先の開始時スナップショットを復元し、carry の鍵だけを重ねる。復元は戻り先の `writes` の範囲外に触れない（後段の成果物は残る。次に上書きされる）
- 辺 (ステージ, end_state) の通過回数は run 全体で数え、`max` を超えたら escalate。人間の `RollbackTo` は数えない
- フェーズの最終ステージが goal になった時だけフェーズの `quantitative` を評価する（フェーズの全ステージの `writes` の和を一つのスナップショットにする）。不成立なら unknown。前のフェーズへ戻ると通過記録は無効化され、再通過時に再評価する
- `writes` 外への書き込み検出は `Runner(..., strict_writes=False)` で切れる（既定は有効）。`reads` は検査しない。`.htf/` は検出の対象外
- 子を持つステージに入るたびに `subworkflow.workspace` 配下を空にしてから子 run を起動する。前回の進入の子 run の残骸は残らない
- フェーズゲート不成立の escalate に人間が `ContinueAsGoal` を返すと、ゲートを人間が通したものとして記録（`GateEvent(passed, note="human")`）し、再評価せずに次へ進む

## 6. テストランナー群（F3）

すべて LLM なしで動く。閾値はすべて仮置き（ADR-013）。実例の規模（software factory 版 0.2）: 台本 26、E2E 43 対象（誘発 39・注入 4）、分布テスト N = 200（markov）と 150（split）、オラクル検証のコーパス 561 件（偽の正解）、トリアージの一周。呼び出し方は `examples/software-factory/tests/`（`sf_support.py` と各 `test_sf_*.py`）。

- **評価ログ**: `result.evaluations`（`EvaluationRecord`: stage、進入回数、状態文書、選択肢、分類結果、Verdict、carry）。子 run の分は `result.child_results` の各 `RunResult` にある。トリアージ・コーパス・分布の集計はここから作る
- **分布テスト**（`htf.testing.stages`）: 確率的な偽本体（種を固定し既知の分布でクラスを出す）で `run_many` → `tally` → `check_expectations`。expectations は YAML（`runs`、`seed`、`stages.<stage>.<first|reentry>.<class>: {min, max}`、`outcomes`）。実例 `examples/toy-minimal/tests/expectations/`
- **独立性検証**（`independence`）: クラス内の代表（既定: 戻り先へ運ぶ carry の中身）ごとに下流のクラス分布が揃うかを、種つきの並べ替え検定で調べる。代表の鍵は `key=` で差し替える。群が一つしか無ければ `verifiable=False`（検証不能。未検出ではない）。carry が代表を識別しないクラスは既定の鍵では検証できない
- **遷移行列とマルコフ合成**（`transition_matrix`、`htf.testing.e2e.synthesize_outcomes`）: P(class | stage, first/reentry) から run 全体の結果を合成し、`compare_outcomes` で実測と比べる。子を持つワークフローでは子 run 数の分布（`samples=` か `child_counts=`）が必須。比較は completed / aborted の頻度で粗い（ADR-013 13.11）
- **E2E カバレッジ**（`htf.testing.e2e`）: `enumerate_targets` が定義から (workflow, stage, class) を列挙する。計画 YAML で各対象を台本で誘発するか、`Runner(inject={(workflow 名, stage, n): Verdict})` で n 回目の進入の判定を注入する。注入は Verdict だけを差し替え、成果物と memory は本体のまま（戻り先が carry を受ける経路は注入では踏めない）。鍵は定義と照合される。`run_plan` が到達を数える（誘発 / 注入を区別）。実例 `examples/toy-minimal/tests/e2e/plan.yaml`
- **オラクル検証**（`htf.testing.oracle`）: コーパス（JSONL）に対して分類器を走らせ、κ・ECE・再実行一致を出す。`ConfusionClassifier` は既知の混同行列を持つ偽物（ランナーの検証用。状態文書の `truth: <label>` 行から真のラベルを読む約束で、実コーパスにこの行は無い）
- **トリアージ**（`htf.testing.triage.TriageQueue`）: run の unknown と低確信度の評価記録を待ち行列に積み、人間がラベルを付け、コーパスに書き出す。注入で作られた判定は既定で積まない。集約で unknown になった親の記録には状態文書が無いので積まれない（子の記録を積む）。記述の改訂は提案止まり（人間の承認）

最小の呼び出し例（`make_runner(seed)` はハーネスの工場。実例は htf リポジトリの `tests/test_f3_*.py`）:

```python
from htf.testing.stages import run_many, tally, load_expectations, check_expectations, independence, transition_matrix
from htf.testing.e2e import load_plan, run_plan, synthesize_outcomes, compare_outcomes
from htf.testing.oracle import verify_oracle, load_corpus
from htf.testing.triage import TriageQueue

exp = load_expectations("tests/expectations/markov.yaml")
samples = run_many(lambda seed: make_runner(seed), runs=exp.runs, seed=exp.seed)
assert check_expectations(tally(samples), exp).ok
report = independence(samples, stage_id="verify", cls="checks_failed")       # report.verifiable / report.flagged
predicted = synthesize_outcomes(workflow, transition_matrix(samples), runs=4000, seed=5, samples=samples)
assert compare_outcomes(predicted, tally(samples).outcomes, tolerance=0.1).ok
coverage = run_plan(load_plan("tests/e2e/plan.yaml"), workflow, make_plan_runner, workspace=tmp)  # coverage.uncovered
oracle = verify_oracle(classifier, load_corpus("corpus.jsonl"))              # oracle.kappa / ece / rerun_agreement
queue = TriageQueue("triage.jsonl"); queue.enqueue(result, workflow=workflow.name, run_id="run-1")
```

仮置きの閾値（htf の ADR-013 で決めたもの。ハーネス側で変えてよい。根拠はハーネスの計画書に書く）:

| 値 | 意味 | 置き場 |
| --- | --- | --- |
| 分類器の確信度の閾値 0.5 | 未満なら unknown。較正結果で決める | `Runner(threshold=)` |
| expectations の区間 | 観測頻度が入るべき範囲。統計的検定はしない。N と種も expectations に書く | expectations YAML |
| 並べ替え検定 200 回、有意水準 0.05 | 独立性検証。p の下限は 1/(回数+1) | `independence(permutations=, alpha=)` |
| κ / ECE の許容差 | オラクル検証。N に依存する | 呼ぶ側 |
| マルコフ合成の許容差 0.1 | completed / aborted の頻度の差 | `compare_outcomes(tolerance=)` |
| 状態文書の切り詰め 4000 文字 | 1 ファイルあたり | `Runner(max_file_chars=)` |
- 分布と E2E のテストは数十秒かかる。`uv run pytest -m "not distribution and not e2e"` で常時の段だけを回せる

## 7. 迷ったら

- この文書と `CONTRACT.md` で決まらないこと、htf に無い機能、回避したくなったこと → ハーネスの `docs/adopting-gaps.md` に書いて続行する。htf の修正は htf 側の通常のセッションが行う
- end_state の記述の良し悪し（観測可能か、排他か）は検査器では見ない。人間のレビューに出す前に、実装していない第三者に定義ファイルだけを読ませる（読取範囲は隔離ディレクトリで課し、既存の指摘は渡さない。実例: htf の `reports/dynamic/f4-sf-definition-review/record.md`）
- 運用（トリアージ、閾値、版の同期、CI の段、公開）は `docs/maintenance.md`

## 8. 実例の一巡（software factory、版 0.2）

雛形（`docs/harness-plan-template.md`）の節ごとに、software factory がどこで何をしたか。計画書は `examples/software-factory/docs/plan.md`。

| 雛形の節 | software factory で作ったもの | 場所 |
| --- | --- | --- |
| 0 前提 | 5 フェーズ 9 ステージ（intake → analyze → design → plan → implement → integrate → verify → review → release）+ 子 3（code → check → unit_test）。ユーザー待ち 2、子の集約 1 | `workflow.yaml` 冒頭、plan.md 第 0 節 |
| 1 ワークフロー定義 | 成果物の形の取り決め（要旨 report と全結果 results の分離）、指標 28 のマニフェスト、第三者レビュー 2 回（サブエージェントと Codex）の採否で版 0.1 → 0.2 | `workflow.yaml`、`implement-task.yaml`、`metrics/manifest.json`、plan.md 第 1・1.1 節 |
| 2 最初の実ステージ | 子の check と unit_test。ビルド = compile()、lint = ruff、テスト = coverage run -m pytest。作業ディレクトリに書かない、正規化、メモ化 | `toolchain.py`、`stages/`（`Check`、`UnitTest`） |
| 3 フィクスチャとコーパス | 小さなコードベース textkit と機能 × 変種の変更、要件・設計・レビューの目録、ペルソナ 5、台本 26（規則は README）、確率的な構成 2 | `fixtures/`、`fixtures/scenarios/README.md` |
| 4 人手ラベル | 偽の正解（本体が本物の結果から書いた印）で代用。人手ラベルは止まる条件 | `tests/sf_support.py`（`marker_truth`）、`tests/test_sf_oracle.py` |
| 5 分類器検証 | 偽の分類器（印を読む / 既知の混同行列）で κ・ECE・再実行一致の形を確認。許容幅は一意な文書数から | `tests/test_sf_oracle.py` |
| 6 分布テストと往復 | expectations 3（理論値 ± 約 3 標準誤差、`workflow_version`）。ずらした基準が落ちる | `tests/expectations/`、`tests/test_sf_distribution.py` |
| 7 独立性 | unit_test / tests_failing を既定の鍵で。split 構成で検出、検証不能なクラスは記録 | `tests/test_sf_distribution.py`、plan.md 第 7 節 |
| 8 残りと E2E | 43 対象を誘発 39・注入 4 で。誘発できない 3 クラスは本体の論理を手作りの成果物で確認。マルコフ合成は markov で一致、split で外れる | `tests/e2e/plan.yaml`、`tests/test_sf_e2e.py`、`tests/test_sf_v02.py` |
| 9 維持 | CI の三段（htf の ci.yml）、トリアージの一周、版の同期 | `tests/test_sf_triage.py`、`docs/maintenance.md` |

組み込み方は一か所（`harness.py`）: 台本 → `Scenario`、確率的な構成 → `Profile`、本体・指標・分類器・ユーザー入出力・人間を `Bindings` に束ね、`Runner` / `ReferenceRuntime` の組み立てを契約適合・決定論・分布・E2E で共有する。

## 9. 落とし穴（software factory の往復 G-01〜G-23 と、第三者レビュー 20 件から）

定義を書く時:

- **最初のステージで失敗を準正常にしようとする**。最初のステージは unknown しか持てない。検出するステージを後ろに置き、そこから直すステージへ戻す（3.1）
- **二段続けて戻ると carry が消える**。閉包（戻り先より後ろへ運ばれうる鍵を各辺が運ぶ）をテストで固定する（3.1）
- **goal の定性が自分の写しだけを基準にする**（design.json の requirements に挙げた要件を…）。原本（reads）との一致を要求する
- **基準値・0 件の境界・kind の値域・id の維持・空の回答が記述に無い**。分類器は記述しか見ない。指標の基準値も定性に書く
- **普通の失敗が unknown にしか行けない**（カバレッジ不足、lint 違反、統合の失敗、拒否の理由の種類）。頻度の高い失敗には準正常のクラスと戻り先を用意する。稀なものは頻度を見てから
- **`max` は run 全体の上限**。別の原因で同じ辺を使っても消費する

本体と指標を書く時:

- **指標が他のステージの成果物を読む**。指標が見られるのは自ステージ（フェーズならフェーズ）の writes のスナップショットと memory だけ。必要な事実は自分の成果物に写す（check.json、tasks/summary.json）
- **実ツールが作業ディレクトリに書く**（バイトコード、キャッシュ）。writes 外の変更として検出される。一時ディレクトリへ逃がし、出力は時刻と絶対パスを落として正規化し、内容のハッシュでメモ化する（3.3）
- **状態文書の切り詰め**。1 ファイル 4000 文字、文書全体は `max_document_chars`。要旨を先頭に、全結果は別ファイルに。`reads` にコードベースを宣言するステージでは文書全体の上限を付ける
- **一部だけ即答して残りで中断する UserIO**。累積列が最初の質問から当たるので、中断するペルソナはそのステージの最初の質問から保留する（3.5）
- **進入回数を本体で数え直す**。`ctx.entry` / `ctx.reentry` を使う（3.4）
- **親子でステージ id を重ねる**。分布の集計と expectations の鍵が混ざる。検査器が落とす
- **フィクスチャの世界で起きない失敗を無理に作る**。注入で踏み、本体の論理は手作りの成果物で確かめ、計画に例外として書く

テストを書く時:

- **E2E 計画の注入は Verdict だけを差し替える**。carry は運ばれない。carry を運ぶ end_state は誘発で踏む
- **同じ文書が多いコーパスでの許容幅**。種つきの分類器は文書の内容で乱数を決めるので有効標本は一意な文書数
- **expectations の区間を観測に合わせて緩める**。理論値 ± 標準誤差から決め、根拠を書く。落ちるべき基準（ずらした expectations）も持つ
- **定義を変えたのに expectations・計画・コーパスを据え置く**。`workflow_version` を書き、runner に照合させる（maintenance.md 第 3 節）
