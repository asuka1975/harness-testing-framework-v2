"""software-factory: 要求の取り込みからリリースまでのソフトウェア開発ワークフロー（htf の実例ハーネス）。

htf.testing.harness.load_example_package(<このディレクトリ>, "software_factory") で読む。
  workflow.yaml / implement-task.yaml    定義（親と子）
  stages/                                偽ステージ本体と結果の供給元（台本 / 種つきの分布）
  toolchain.py                           実ツール（ビルド・lint・テスト・カバレッジ）とコードベースの組み立て
  metrics/                               指標レジストリ（manifest.json の名前を実装）
  user/                                  ユーザーシミュレータ（ペルソナ）
  harness.py                             台本・構成の読み込みと束縛・Runner の組み立て
  fixtures/                              コードベース、成果物、ペルソナ、台本、確率的な構成
  tests/                                 テスト（uv run pytest examples/software-factory/tests）
  docs/                                  計画書、進捗、adopting-gaps
"""

__version__ = (
    "0.2"  # ハーネスの版。定義の workflow.version と同じ変更で上げる（docs/maintenance.md 第 3 節）
)
