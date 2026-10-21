# 動的ワークフローの記録: `f2-runtime-and-tests`

計画書第5.10節。宣言は `docs/progress.md`（2026-10-22 の節、F2 の検証の要旨の直後）。成果は `reports/verification/f2-runtime-and-tests/`。

## 実行

- 起動: 2026-10-22、計画エージェントが general-purpose サブエージェント 1 を新規起動（fork ではない）
- 入れ子: 0
- 予算の実績: 約 213,900 トークン（**上限 20 万を約 7% 超過**）、約 18.6 分（上限 20 分以内）、ツール呼び出し 43 回、フレームワーク外の LLM 呼び出し 0
- 反復: 1 回
- 書いたパス: `reports/verification/f2-runtime-and-tests/` のみ（`git status --short` で確認）

## 三層の判定

**準正常**（予算超過）。完了条件（report.md の 5 節）はすべて満たしている。トークン予算を 7% 超えたのは探針 8 件を自作して実行したためで、報告の内容には影響しない。戻る条件「予算超過」に該当するので準正常とし、持ち帰る情報は「探針を含む検証役の予算は 25 万トークンを目安にする」。再実行はしない（反復の上限 1）。

## 受け入れ（第5.3節 4 の検証を通してから受け入れ）

```text
$ git status --short            → ?? reports/verification/f2-runtime-and-tests/   のみ
$ uv run pytest -q              → 107 passed
$ uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics …  → 0 finding(s)
```

## 報告の処理（計画エージェント）

| 報告の項目 | 処理 |
| --- | --- |
| 完了条件 1〜6: 満たす | 受け入れ。F2 の完了条件は満たしたと判定 |
| B1 中断再開を含む run の記録再生 | 修正。記録は試行単位で確定し、中断した試行は破棄。回答は本体が受け取った時点で記録（ADR-012 12.18）。回帰テスト test_b1 |
| B2 子 run 作業ディレクトリの残骸 | 修正。子 run 起動前に `subworkflow.workspace` 配下を空にする（12.17）。回帰テスト test_b2 |
| B3 ゲート不成立の escalate に ContinueAsGoal が効かない | 修正。人間がゲートを通したものとして次へ（12.19）。回帰テスト test_b3 |
| B4 最上位で human 無しの escalate | 修正。`ContractViolation`（12.20）。回帰テスト test_b4 |
| B5 契約適合スイートの範囲と CONTRACT 第 8 節の不整合 | adopting.md 3.8 を実態に合わせて修正。CONTRACT 第 8 節の改訂は契約の変更なので提案（12.25）としてゲートへ |
| B6 未消費の記録 | 修正。再生終了時に `ReplayMismatch`（12.21）。回帰テスト test_b6 |
| B7 `.htf/` への書き込み | 文書を「検出しない。結果は未定義」に揃えた（12.24） |
| B8 閾値 0.5 | ADR-012 12.23 に仮置きとして記録。adopting.md に `threshold` を記載 |
| B9 子の内部の遷移が観測できない | 修正。`RunResult.child_results` に子 run の RunResult を保持（12.22。契約の `ChildOutcome` は変えない） |
| B10 adopting.md の差 | 修正 |
| W1 台本の「最後を繰り返す」規則 | 規則を台本ディレクトリの README と harness.py に明記 |
| W2 子 run の境界の判定 | 子 run には人間の解決（Rerun、carry 無し RollbackTo）が届かないので v1.0 では誤認は起きない。理由を stages/ に明記 |
| W3 Verify が assumed を出さない | 台本の結果に `goal_assumed`（一部を仮定として理由つきで記録）を追加 |
| 判定できなかった事項 | 閾値と分類可能性は F3 以降。カバレッジの読み（行+分岐 93%、行のみ 95%）は progress.md に記載 |
