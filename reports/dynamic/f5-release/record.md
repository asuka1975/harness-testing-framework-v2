# 動的ワークフローの記録: `f5-release`

計画書第5.10節。宣言は `docs/progress.md`（F5 の記録の後）。成果は `reports/verification/f5-release/report.md`。

## 実行

- 起動: 2026-10-22、計画エージェントが general-purpose サブエージェント 1 を新規起動（fork は使わない）。対象はコミット `9abaa55`（F5 の実装）
- 入れ子: 0。反復: 1。予算の実績: 約 209,000 トークン（上限 25 万）、約 20 分（上限 30 分）、ツール呼び出し 55 回、外部 LLM 0
- 書いたパス: `reports/verification/f5-release/report.md` のみ（`git status --short` → `?? reports/verification/f5-release/` だけ。探針 4 本は /tmp のスクラッチに置き、リポジトリに残していない）

## 三層の判定

**正常**（完了条件を満たし、予算内、書き込み先も宣言どおり）。報告の総合判定: F5 の完了条件 5 項目すべて「満たす」（(e) は「公開できる状態。人間ゲート待ち」）。先送りされていた第三者判定（G-04 / 05 / 06 / 08 / 16、14.2〜14.5、同期バージョン管理）は探針 4 本・40 項目で「固定されている」、製品の不具合 0 件。重大度「高」の問題は無し。

## 受け入れ

```text
$ git status --short                                       → ?? reports/verification/f5-release/ のみ
$ uv run pytest -o addopts="" -q tests                     → 172 passed in 68.50s（探針の退行テスト 2 件を加えた後）
$ uv run pytest -o addopts="" -q examples/software-factory/tests → 120 passed
```

## 報告の処理（計画エージェント）

| 報告の項目 | 処理 |
| --- | --- |
| (a)〜(e) 満たす | 受け入れ。(e) の「公開」は v1.0 ゲートへ（タグ・Release・push は人間の指示） |
| 探針: 人間の Rerun / RollbackTo の下の `ctx.entry`、違う context での再生の `ReplayMismatch` | 既存テストが見ていなかった経路。探針を退行テストにした（`tests/test_f4_contract_proposals.py`、別コミット） |
| 探針: 検査器は carry の閉包を見ない（`test_sf_v02.py::test_carry_closure` が落とす） | 設計どおり（ADR-014 G-22: 検査器の警告は見送り。定義の設計の判断であり機械的に誤りとは言えない）。閉包テストの雛形化は公開後の候補として progress.md に |
| 文書（低）: adopting-gaps の要約の時制、sf 計画書の「最低限版」、雛形第 9 節の読み替え条項、ハーネスの版の所在 | 直した（別コミット。雛形への一文は F5 の戻る条件「雛形か adopting.md を直す」に沿う） |
| ADR-015 / ADR-014 14.6 の決定欄が未記入 | 設計どおり。v1.0 ゲートで人間が記入 |
| 判定できなかった事項（公開そのもの、GitHub Actions 上の実走、閾値の妥当性） | ゲートへ / 公開後（ADR-006） |
