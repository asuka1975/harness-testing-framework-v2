# harness-testing-framework

ワークフロー型エージェントハーネスのための汎用テスティングフレームワーク。

ハーネスの仕様（ワークフロー定義 YAML）を唯一の情報源とし、ステージの結果を三層（goal / end_state / unknown）で判定する実行機構と、それを LLM なしで検査するランナー群を提供する。特定のハーネスに依存しない。

- **スキーマと整合性検査器**: `schema/workflow.schema.json`、`htf.testing.spec`（`python -m htf.testing.spec workflow.yaml --metrics manifest.json`）
- **契約**: `src/htf/contract/CONTRACT.md`（三操作 run / evaluate / restore + overlay、スナップショット形式、インターフェース）と契約適合テスト `htf.contract.conformance`
- **参照ランタイム**: `htf.runtime`（loader / checkpoint / runner / oracle / recorder）
- **テストランナー群**: `htf.testing.{harness,stages,oracle,e2e,triage}`（決定論テストの道具、分布テスト、独立性検証、オラクル検証、E2E とマルコフ合成、トリアージ）
- **玩具ワークフロー**: `examples/toy-minimal/`（契約と全遷移種別を最小構成で覆う）

## 使い方

ハーネス側が満たすべきことと組み込み方は `docs/adopting.md`。設計判断は `docs/decisions.md`（ADR）、計画は `docs/plan.md`、作業ログは `docs/progress.md`。

```text
uv sync
uv run pytest                       # すべて LLM なし（分布 / E2E を含め約 1 分）
uv run pytest -m "not distribution and not e2e"
uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics examples/toy-minimal/metrics/manifest.json
```

Python 3.12 以上、依存は jsonschema と PyYAML。

## 状態

v0.1: 玩具 1（toy-minimal）に対して全ランナーが LLM なしで通り、参照ランタイムが契約適合テストを通る。玩具 2（software factory）と適用の手引きの完成版は次の段階。
