# 動的ワークフローの記録: `f1-contract-and-spec`

計画書第5.10節。宣言は `docs/progress.md`（2026-10-22 の節末尾）。成果は `reports/verification/f1-contract-and-spec/`。

## 実行

- 起動: 2026-10-22、計画エージェント（主セッション）が general-purpose サブエージェント 1 を新規起動（fork ではない。実装の文脈を継がない）
- 入れ子: 0（サブエージェントは起動していない）
- 予算の実績: 約 192,900 トークン（上限 20 万）、約 15 分（上限 20 分）、ツール呼び出し 36 回、フレームワーク外の LLM 呼び出し 0
- 反復: 1 回（再実行なし）
- 書いたパス: `reports/verification/f1-contract-and-spec/` のみ（`git status` で確認。保護ファイル、テスト、本体コードに変更なし）
- 注記: 検証役は Write ツールの書き込みが拒否されたため、同じ内容をシェル経由で書いたと報告している。書き先は宣言の範囲内で、内容は計画エージェントが読んで受け入れた

## 三層の判定

**正常**。完了条件（report.md に (1) F1 完了条件の判定と根拠、(2) MECE 事前レビュー、(3) 問題の分類、(4) 判定できなかった事項）をすべて満たす。

## 受け入れ（第5.3節 4 の検証を通してから受け入れ）

```text
$ git status --short            → ?? reports/verification/   のみ
$ uv run pytest -q              → 63 passed
$ uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics examples/toy-minimal/metrics/manifest.json
0 finding(s)
```

## 報告の処理（計画エージェント）

| 報告の項目 | 処理 |
| --- | --- |
| 完了条件 1〜5: 満たす | 受け入れ |
| 完了条件 6（時系列）: 判定不能 | progress.md に本セッションで実行した `pytest --collect-only` の失敗記録（実装前）を残す。以後はテストを実装より先に別コミットにする（運用規則として progress.md に記載） |
| W1 | 意味の確定が要るので提案（decisions.md ADR-011 G1） |
| W2〜W4 | toy-minimal の workflow.yaml を修正（意味を変えない範囲。ADR-011 11.21）。整合性検査を再実行 |
| T1〜T4 | 分類体系の変更の提案として decisions.md ADR-011 G2〜G5 に記載し、止まる |
| F1 | スキーマ拡張の提案（G4 (b)）。承認後に実装 |
| F2、F3 | CONTRACT.md と types.py を修正（ADR-011 11.18、11.19） |
| F4 | 探針 P1 / P2 / P4 / P6 を負例に昇格（ADR-011 11.20） |
| 判定不能 3（ステージ数の数え方） | G6 |
| 判定不能 4、5（CI、ruff） | 計画エージェントが実行して progress.md に記録（CI はリモート未設定のため未実行） |
| 判定不能 6、7 | F2 / F3 以降の対象。処理不要 |
