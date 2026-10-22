# harness-testing-framework

ワークフロー型エージェントハーネスのための汎用テスティングフレームワーク。

ハーネスの仕様（ワークフロー定義 YAML）を唯一の情報源とし、ステージの結果を三層（goal / end_state / unknown）で判定する実行機構と、それを LLM なしで検査するランナー群を提供する。特定のハーネスに依存しない。

- **スキーマと整合性検査器**: `schema/workflow.schema.json`、`htf.testing.spec`（`python -m htf.testing.spec workflow.yaml --metrics manifest.json`）
- **契約**: `src/htf/contract/CONTRACT.md`（三操作 run / evaluate / restore + overlay、スナップショット形式、インターフェース）と契約適合テスト `htf.contract.conformance`
- **参照ランタイム**: `htf.runtime`（loader / checkpoint / runner / oracle / recorder）
- **テストランナー群**: `htf.testing.{harness,stages,oracle,e2e,triage}`（決定論テストの道具、分布テスト、独立性検証、オラクル検証、E2E とマルコフ合成、トリアージ）
- **玩具ワークフロー**: `examples/toy-minimal/`（契約と全遷移種別を最小構成で覆う）、`examples/software-factory/`（ソフトウェア開発のワークフロー。実ツールを走らせる指標、子ワークフロー、ペルソナ、分布テストと E2E まで一通り）

## 使い方

ハーネス側が満たすべきことと組み込み方は `docs/adopting.md`、実ハーネスの計画書の雛形は `docs/harness-plan-template.md`、運用は `docs/maintenance.md`。設計判断は `docs/decisions.md`（ADR）、計画は `docs/plan.md`、作業ログは `docs/progress.md`。

```text
uv sync
uv run pytest                                                   # htf のすべて（LLM なし。分布 / E2E / オラクルを含め約 1 分強）
uv run pytest -m "not distribution and not e2e and not oracle"  # CI の常時の段
uv run pytest examples/software-factory/tests                   # 例のハーネス（約 2.5 分。常時の段だけなら -m を付ける）
uv run python -m htf.testing.spec examples/software-factory/workflow.yaml --metrics examples/software-factory/metrics/manifest.json
```

CI は三段（`.github/workflows/ci.yml`）: 常時（整合性検査・決定論テスト・契約適合・トリアージ）、ナイトリー（オラクル検証）、手動（分布テストと E2E）。

Python 3.12 以上、依存は jsonschema と PyYAML。

## 状態

v1.0: 二つの玩具（toy-minimal、software-factory 版 0.2）で全ランナーが LLM なしで通り、参照ランタイムが契約適合テストを通る。adopting.md と雛形は software factory を実例にした完成版、CI は三段、分類体系とハーネスの版は expectations・E2E 計画・コーパスの `workflow_version` で同期する。実 LLM による方法検証（分類器の較正）は v1.0 の後（ADR-006）。
