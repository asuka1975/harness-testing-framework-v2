# 動的ワークフローの記録: `f4-sf-definition-review`

計画書第5.10節。宣言は `docs/progress.md`（F4 の記録の後）。成果は `reports/verification/f4-sf-definition-review/report.md`。

## 実行

- 起動: 2026-10-22 17:36、計画エージェントが外部 CLI を非対話で起動（人間の指示「1. について Codex Astra 6 Max にレビューをもらってください」）
  - `codex exec -C <隔離ディレクトリ> -s read-only --skip-git-repo-check -m gpt-6-astra -c 'model_reasoning_effort="max"' --json -o report.md - < prompt.md`
  - Codex CLI 0.162.1、スレッド `01a162c1-1ab7-7ac1-ade7-b72f18d93cdd`
- 読取制限は構造で課した: 隔離ディレクトリに `workflow.yaml`、`implement-task.yaml`、`metrics/manifest.json`、`docs/adopting.md`、`CONTRACT.md`、`workflow.schema.json`、software factory の計画書第 0〜1 節（第 1.1 節の既存レビュー 11 件と「第三者」を含む行は除去。`grep` で漏れ無しを確認）だけを置き、作業ルートにした
- 第 1 ターン（独立レビュー）: 17:36〜18:07（31 分）。入力 186,058 トークン（うちキャッシュ 153,984）、出力 30,383（うち推論 20,767）。コマンド 10 回（`pwd`、`rg --files`、各資料の `cat` / `sed` / `nl`、祖先ディレクトリの `AGENTS.md` 探索 — 存在せず）。**読んだのはすべて隔離ディレクトリの中**、`file_change` イベント 0、stderr 空
- 第 2 ターン（前提の訂正。同じスレッドを `codex exec resume`。指示は `prompt-turn2.md`）: 18:08〜18:22（13 分）。入力 259,519 トークン（うちキャッシュ 197,248）、出力 42,328（うち推論 30,022）。コマンド 0（読み直し無し）、`file_change` 0、stderr 空。計画エージェントの指示に誤りがあったため（下記）
- 入れ子: 0。反復: 2 ターン（宣言の「1 + 突き合わせ 1」の枠を、突き合わせではなく前提の訂正に使った。突き合わせは計画エージェントが本ファイルで行う）
- 両ターンの指示は `prompt-turn1.md`、`prompt-turn2.md`（再現用）

## 計画エージェントの誤り（記録）

指示に「`reads` のファイルは分類器には渡りません」と書いたが、CONTRACT 第 5.4 節・adopting.md 3.6・スキーマ・実装（`htf.runtime.project`）はいずれも `reads ∪ writes ∪ memory_in` から投影する。Codex は第 4 節の冒頭でこの資料間の不一致を指摘し、指示の前提を条件付きで採用した。第 2 ターンで前提を訂正し、観点 (b)（観測可能性）の指摘の差分だけを求めた。本体の修正は不要（契約と実装は一致している。誤りは指示文だけ）。

## 三層の判定

**準正常**。完了条件（報告の 5 項目: 全体の判定、指摘の表、ステージごとの所見、判定できなかった事項、読んだファイル）は満たす。予算: 時間の合計 44 分で上限 40 分を超過。超過分は計画エージェントの指示の誤りを訂正する第 2 ターンによるもので、「前提の誤り → 訂正して再判定」は戻る条件に当たるので準正常とする。LLM 呼び出しは 1 セッション 2 ターン（宣言どおり）。トークンの上限は宣言に無かった（実績: 入力 445,577 うちキャッシュ 351,232、出力 72,711）。読取範囲: 両ターンとも隔離ディレクトリの外は読んでいない（`events.jsonl` の `command_execution` を全件確認。祖先ディレクトリの `AGENTS.md` 探索は存在せず空振り）。

## 受け入れ

```text
$ git status --short   → reports/verification/f4-sf-definition-review/、reports/dynamic/f4-sf-definition-review/、docs/progress.md、docs/decisions.md のみ（定義ファイルは未変更）
$ uv run pytest -o addopts="" -q tests/test_repo_layout.py   → 受け入れ時に再実行（下記 git log）
```

## 既存の第三者レビュー 11 件（sf 計画書 第 1.1 節。E1〜E11）との突き合わせ

Codex の番号は report.md 第 1 ターンの表。第 2 ターン（前提の訂正: `reads` も分類器に渡る）で **11 は取り下げ、12・17 は改訂、20・21 を追加**。表はその反映後。

| 既存 | Codex | 関係 | 要点 |
| --- | --- | --- | --- |
| E1 高 子 code の失敗が全て unknown | 01 高 | **重複** | 同じ。Codex は「最初の `code` に rollback を足すだけでは契約に適合しない」と構造の制約まで言う。提案（検査を後段に分けて code へ戻す）も同じ |
| E2 中 verify のカバレッジ不足・lint 違反が unknown | 02 高 | **重複**（Codex は高） | 同じ。Codex は複合不成立の優先順位の記述も求める |
| E3 中 plan の scope 重複・テスト無しが unknown、4 本の carry の反映 | 03 高、16 中 | **重複 + 拡張** | scope / tests は同じ（Codex は高）。carry の反映について Codex は「再計画でタスクが分割されたら前回の id では適用先が決まらない」（16）を加える |
| E4 中 review の kind 未定義・パス無し・design.json に無い id | 14 中（11 は取り下げ） | **重複** | kind の値域（14）は同じ。参照の実在を照合できないとした 11 は、`reads`（design.json、codebase/）が分類器に渡るので第 2 ターンで取り下げ |
| E5 中 design / analyze が自分の写しを見る | 12 中（改訂）、04 高 | **重複 + 新規** | 12 は改訂後「原本との一致が goal の条件に無い」で既存と同じ趣旨。**04 は新規**: 衝突が無い割当て漏れは goal 不成立で unknown にしかならず、design を作り直す自動経路が無い |
| E6 中 二段ロールバックで carry が消える | 07 高 | **重複**（Codex は高） | 同じ。Codex は経路を三つ挙げる（release→analyze→intake→analyze、review→design→analyze→intake、plan→design で implement / verify / review からの指摘が消える） |
| E7 中 release の rejected → analyze が見送りしか扱わない | 08 高 | **重複**（Codex は高） | 同じ。Codex は analyze が conflicts も一律に見送りへ変換する点を加える |
| E8 中 4000 文字の切り詰め | 17 中（改訂） | **重複 + 拡張** | 同じ。改訂後は reads の各ファイルにも効く（長い design.json の末尾、ソース全文のダイジェスト照合）。判定用の事実は小さな専用成果物に |
| E9 低 子 unit_test の定性に 0.9 が無い、テスト 0 件 | 13 中、15 中 | **重複 + 拡張** | テスト 0 件 / 要件 0 件の境界（13。Codex は analyze にも広げる）。**15 は verify の定性に 0.85 が無い**（既存は unit_test だけ） |
| E10 低 code / release の「変更を含む」・版・ダイジェスト | 10 高（11 は取り下げ） | **重複 + 新規** | **10 は新規**: 承認は true だが manifest / CHANGELOG が不備の時、rejected ではなく unknown（準正常経路が無い）。ダイジェストの照合は 17（切り詰め）に残る |
| E11 低 稀な unknown（統合の指標だけ不成立、design_gap の理由 ほか） | 05 高、09 高 | **重複だが重大度が違う** | 既存は「頻度を見てから」。Codex は **05 統合の失敗**（子は全て goal だが統合後のビルド / scope が不成立。aggregate で扱えず、統合の完全性も検査されない）と **09 design_gap が設計の欠陥と計画の欠陥を区別しない**（計画が落としただけなのに design を作り直す）を高とする |
| — | 06 高 | **新規** | implement の本体指示が「単体テストを通らなかったタスク」だけを未完了にしており、aggregate の coverage_low と食い違う（記述のみ） |
| — | 18 中 | **新規** | intake / release で空の回答（acceptance が空文字、approved: false で reason 空）を受理して終了した場合の扱いが無い（記述のみ） |
| — | 19 低 | **新規** | design フェーズの定性「全ての要件」とステージの「見送りでない要件」の食い違い（記述のみ） |
| — | 20 中（第 2 ターン） | **新規（htf 側）** | 状態文書の総量に上限が無い。`reads: [codebase/]` で配下の全ファイルが各 4000 文字まで入り、判定結果の writes より前に並ぶ。ハーネスの定義では直せない → 契約への提案 14.5 |
| — | 21 中（第 2 ターン） | **新規** | reads と writes の食い違い（plan の写しと原本、verify の report と原本）の優先が記述に無い。写しの件は 12 で覆う |
| — | 判定不能の項目 | **新規（軽微）** | intake の constraints が質問にはあるが goal と `intake_complete` の必須に無い。`max` は run 全体の上限なので、別の原因で同じ辺を使うと上限を消費する（release から戻った後の二度目の design_flaw など） |

**矛盾**: 無し。Codex は「優先順位で解消されていない goal / end_state の重複は無い」「子の集約の網羅性と順序は問題なし」「11 辺すべてに前方の戻り先があり carry は memory_out / memory_in と整合」と、構造面は既存レビューと同じ結論。差は重大度（既存の中 4 件・低 1 件を Codex は高にする: 02、03、07、08、05）と、新規 9 件（04、06、09、10、16、18、19、20、21）+ 既存の拡張 2 件（13、15）。

**全体の判定**: Codex は「直してから出す」（通常の失敗が unknown にしか進めない箇所、二段ロールバックで修正理由を失う経路、拒否理由に対応しない戻り先が理由）。既存レビューは 11 件を提案として残し定義は変えていないので、両者は「人間の承認の上で版 0.2 に反映する」で整合する。

## 報告の処理（計画エージェント）

定義は変えない（分類体系の変更は人間の承認）。指摘はすべて ADR-014 への追記として人間ゲートへ。

| 報告の項目 | 処理 |
| --- | --- |
| 全体の判定「直してから出す」 | 受け入れ。既存レビューの「提案として残し人間の承認で版 0.2」と整合する。人間ゲート項目 1 の材料にする |
| 既存 11 件と重なる指摘（重大度の引き上げ 5 件） | ADR-014 の推奨を更新: verify の品質不成立（02）と release の拒否理由（08）を「頻度を見てから」→「採る」に、統合の失敗（05）を稀な場合から分けて「採る」に |
| 新規 04（design の割当て漏れ） | 採るを推奨（plan に `design_incomplete` → design） |
| 新規 05 + 06（統合の失敗、本体指示と aggregate の食い違い） | 採るを推奨（`integrate` ステージの分離） |
| 新規 09（design_gap の原因の混同） | 見送るを推奨（design_gap → design の経路で plan も再実行される。費用は design の一回） |
| 新規 10（release の成果物不備） | 頻度を見てから |
| 改訂 12・17、拡張 13・15、新規 16・18・19 | 採る（記述のみ） |
| 新規 20（状態文書の総量） | htf 本体の不足として progress.md に記録。契約への提案 14.5（総量の上限 / writes を先に / 投影から外す印） |
| 新規 21（reads と writes の食い違い） | 頻度を見てから（写しの件は 12 で覆う。report と原本の矛盾は、指標が report から計算される設計を優先） |
| 判定不能（constraints の必須性、`max` の run 全体性） | constraints は任意と記述に明記（採る）。`max` は契約どおりで変えない（adopting.md 3.1 に一文を足す案） |
| 第 1 ターンの「資料間不一致」 | 計画エージェントの指示の誤り。第 2 ターンで訂正。本体・契約・文書は一致しており修正不要。progress.md に過程の問題として記録 |
