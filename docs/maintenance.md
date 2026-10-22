# maintenance.md — 維持の手順書（v1.0）

htf と、その上に作ったハーネスを運用で保つための手順。計画書第 5.7 節（検証、コスト）、第 5.9 節（役割）、ハーネス側の雛形第 9 節（維持ループ）に対応する。各手順は「誰が / いつ / 何を見て / 何を書くか」で書く。実例は `examples/software-factory/`（版 0.2）。

## 1. トリアージ（unknown と低確信度の記録を人間のラベルに回す）

- 誰が: トリアージ担当（第 5.9 節のトリアージ役。定期セッション）。ラベルは人間が付ける
- いつ: 実 LLM を入れた run が走るたびに積み、週一回まとめてラベル付け。偽本体だけの間は CI の常時の段（`test_sf_triage.py` の一周）が形を保つ
- 何を見て: run ごとに `TriageQueue.enqueue(result, workflow=..., run_id=..., low_confidence=閾値)`。unknown の評価記録と、閾値未満の確信度の記録（分類は正しいが迷った兆候）が積まれる。注入（E2E）で作った判定は既定で積まない。項目は状態文書・選択肢・判定・分類結果・carry と、そのワークフローの版（`workflow_version`）を持つ
- 何を書くか: `queue.label(id, label=, note=)` か `queue.dismiss(id, note=)`。却下は「成果物は正常で、運用（依頼者に聞き直す等）で対処」のように理由を書く。ラベル済みは `queue.export_corpus(path)` でコーパス（`htf.testing.oracle` の JSONL）に出し、オラクル検証（第 2 節）の入力にする
- 記述改訂の候補: (1) 分類器の選択とラベルが食い違う項目、(2) 選択は正しいが確信度が閾値未満の項目。どちらも「記述が曖昧」の兆候。改訂は提案止まり（第 3 節の承認の流れ）

## 2. 分類器検証（オラクル）と閾値

- 誰が: ハーネスの作者。高リスクなので、閾値を変える時は実装を見ていない第三者（別セッションかサブエージェント）が結果を読む（第 5.7 節）
- いつ: ナイトリー（CI の `nightly` job。`-m oracle`）。コーパスが増えた時と、分類器の後ろ側（モデル、プロンプト）を変えた時は手動でも
- 何を見て: `verify_oracle(classifier, corpus)` の κ（人間との一致）、ECE（確信度の較正）、再実行一致。コーパスは `workflow_version` が今の定義の版と同じ項目だけを使う（版が変わった記述に付いたラベルは再ラベルの候補）。偽の分類器での値（κ = 1、ECE > 0 は low_confidence の項目）は形の確認であって較正ではない
- 閾値（すべて仮置き。ADR-013）: 分類器の確信度 0.5（`Runner(threshold=)`）、κ・ECE の目標、p 値 0.05、マルコフ合成の許容差 0.1。実 LLM の較正結果が出たら値を決め、根拠を decisions.md に書く。緩めて通さない
- 種つきの `ConfusionClassifier` は文書の内容で乱数を決めるので、同じ文書が多いコーパスでは有効標本が一意な文書の数に縮む。許容幅はそこから取る（`examples/software-factory/tests/test_sf_oracle.py`）

## 3. 記述の改訂と、分類体系とハーネスの同期バージョン管理

- 記述（goal 定性・end_state）の文言だけの改訂: ハーネスの作者が直す。直したら整合性検査（`python -m htf.testing.spec`）と決定論テスト（台本）を回す
- 分類体系の変更（end_state の追加・分割・統合・意味の変更、戻り先の変更、carry の鍵の変更）: **人間の承認**（htf の計画書第 5.4 節、ハーネスの雛形の止まる条件）。提案は decisions.md（ADR）か、ハーネスの計画書に表で書く。承認されたら次の順で反映する
  1. `workflow.version` を上げる（分類体系の版）。ハーネスのパッケージの版も同じ変更で上げる
  2. 完了条件（台本の expect、E2E 計画、expectations）を先に書き直して別コミット。実装前に失敗することを記録する
  3. 定義と本体を直す。整合性検査 0 件、台本、契約適合、E2E のカバレッジ 1.0
  4. expectations を較正し直す（理論値 ± 約 3 標準誤差。根拠をファイル冒頭に）。ずらした基準が落ちることも確かめる
  5. コーパスの古い版の項目は再ラベルの候補にする
- 同期の仕組み（runner が照合する）:
  - expectations（`htf.testing.stages`）と E2E 計画（`htf.testing.e2e`）は `workflow_version` を持つ。`check_expectations` は集計（`Tally.workflow_version`。run のスナップショットから）と、`run_plan` は定義（`workflow.version`）と照合し、違えば `ValueError` で止まる。欄が無ければ照合しない
  - コーパスの項目（`CorpusItem.workflow_version`）とトリアージの項目（`TriageItem.workflow_version`）は、記録の属するワークフロー（親か子）の版を持つ。古い JSONL（欄が無い）も読める
  - 実例: `examples/software-factory/` は版 0.1 → 0.2 の変更を htf の ADR-014 で承認し、上の順で反映した（`tests/test_sf_v02.py` が完了条件）
- 雛形との対応: ハーネスの計画書は `docs/harness-plan-template.md` の節立てを保つ（htf の `tests/test_f5_release.py` が software factory で見出しの一致を確かめる）。雛形を変えたら実例のハーネスを当てはめ直す

## 4. CI のコスト段階

`.github/workflows/ci.yml`。マーカーは `pyproject.toml`（`distribution` / `e2e` / `oracle`）。

| 段 | 起動 | 内容 | 目安 |
| --- | --- | --- | --- |
| 常時（`always`） | push / pull_request | ruff、整合性検査・決定論テスト・契約適合・トリアージ（`-m "not distribution and not e2e and not oracle"`。htf と software factory）、runtime の行カバレッジ 90% | htf 約 1 分、software factory 約 1 分 |
| ナイトリー（`nightly`） | schedule（毎日 03:00 JST）、または workflow_dispatch の tier=nightly | オラクル検証（`-m oracle`。htf と software factory） | 数十秒（偽の分類器）。実 LLM では LLM の呼び出し費用 |
| 手動（`manual`） | workflow_dispatch の tier=manual（人間が明示的に許可） | 分布テストと E2E（`-m "distribution or e2e"`。htf と software factory） | htf 約 1 分、software factory 約 2 分 |

- 費用が予算を超えたら expectations の N か段の頻度を下げる（計画書 F5 の戻る条件）。閾値や区間を緩めない
- 本体（`src/htf/`）を変えた時は手動の段も回してから出す。定義（workflow.yaml）を変えた時は第 3 節の順

## 5. 保護ファイルと役割

- 保護ファイル（計画書第 5.9 節）: `docs/plan.md`、`docs/decisions.md`、`schema/`、`src/htf/contract/`、各玩具の `workflow.yaml` と expectations。書けるのは計画エージェント（htf の主セッション）だけ。人間の承認が要るもの（分類体系・閾値・スキーマの意味）は提案止まり
- 検証役（第三者）は `reports/` だけに書く。動的ワークフロー（サブエージェントや外部 CLI の起動）は `docs/progress.md` に第 5.10 節の宣言を先に書き、記録を `reports/dynamic/<id>/` に残す。読取範囲は指示ではなく構造（隔離ディレクトリ）で課す（`reports/dynamic/f4-sf-definition-review/record.md`）
- ハーネス側（利用者）は `docs/adopting.md` と雛形だけを読んで作り、判断できなかったことを自分の `docs/adopting-gaps.md` に書く。htf の修正は htf の通常セッションが toy-minimal で再現してから行う（第 5.8 節）

## 6. 公開（版の付け方と手順）

- 版: htf のパッケージの版（`pyproject.toml`）。v0.1（玩具 1 で全ランナー）、v1.0（玩具 2、adopting.md と雛形の完成版、CI の段階、同期バージョン管理、本書）。以後は契約（`CONTRACT.md`、`htf.contract` の型）の互換を壊す変更で主版を上げる
- 手順（人間ゲートの承認後）: (1) 常時の段と手動の段を両方通す、(2) `docs/progress.md` に検証の要旨、(3) タグ `vX.Y.Z` と GitHub Release（本文は進捗の要旨と決定の一覧）、(4) push。push・タグ・Release は人間の指示があった時だけ
- 公開後の最初の作業は ADR-006（実 LLM による方法検証。software factory の一ステージを recorder 経由で本物にし、分類器の較正でこの手順書の閾値を決める）

## 7. 一周の目安（運用のリズム）

1. 毎日: 常時の段（CI）。ナイトリーのオラクル検証の結果を朝に見る（κ・ECE が目標を割ったらトリアージの優先度を上げる）
2. 毎週: トリアージのラベル付け → コーパスに書き出し → 記述改訂の候補を一覧にする
3. 変更のたび: 記述の改訂は作者が、分類体系の変更は承認を経て第 3 節の順で。定義を変えたら手動の段（分布と E2E）を回す
4. 四半期: 閾値と expectations の区間の見直し（実データの κ・ECE・分布から）。雛形と adopting.md に実例の変化を反映する
