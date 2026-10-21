"""toy-minimal: 契約と全遷移種別を最小構成で覆う玩具ワークフロー（玩具 1）。

htf.testing.harness.load_example_package(<このディレクトリ>, "toy_minimal") で読む。
  workflow.yaml / elaborate-claim.yaml   定義（親と子）
  stages/                                決定論的な偽ステージ本体（台本で制御）
  metrics/                               指標レジストリ（manifest.json の名前を実装）
  user/                                  ユーザーシミュレータ
  harness.py                             台本の読み込みと束縛の組み立て
  tests/fixtures/scenarios/              台本
"""
