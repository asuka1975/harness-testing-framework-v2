# 作業ログ

形式は計画書第4節末尾で固定。先頭に「次にやること」、続いて日付ごとに「完了したこと」「未完了と理由」「発見した問題（ワークフロー定義 / フレームワーク本体）」「実行した検証とその結果の要旨」。

## 次にやること

現在は F1 の初期化タスク完了直後で、人間の決定待ち。決定は docs/decisions.md の各 ADR の「決定」節に書く（直接編集でよい）。

1. **人間の決定を待つ**: ADR-001〜005、007〜010（ADR-006 は F5 で決める）。決定があるまで下記 2 以降には着手しない
2. **ADR-010 が決まったら**（ツールチェーンの骨格と CI の雛形）
   - pyproject.toml（uv）、uv.lock、ruff 設定、.gitignore、`tests/` の配置（パッケージ配置の小決定 P1 / P2 / P3 に従う）
   - GitHub Actions の雛形（整合性検査と決定論テストを常時実行する一段だけ。段階分けは F5）
   - 初期化の完了条件スクリプト（scratchpad の `check_init.py`、内容は本日の検証の節に要旨）を `tests/` に移植して CI で回す
3. **ADR-001 / 002 / 005 / 007 が決まったら**（F1 本体）
   - 完了条件を先に書く: 検査器の各性質（参照整合、unknown を除く end_state と rollback の全単射、戻り先の前方性、max の存在と有界性、carry の生成と消費、指標の存在、unknown の存在）ごとに負例を schema/examples/ に置き、「正例が通り負例が落ちる」テストを書く
   - 拡張スキーマ（carry / max / artifacts / 指標の形 / additionalProperties）、整合性検査器、ハーネス契約の文書、toy-minimal の workflow.yaml（3〜4ステージ。ロールバック、carry、フェーズ境界越え、ユーザー待ち）
   - toy-minimal の workflow.yaml は人間に出す前に、実装を見ていない検証役に MECE 事前レビューをさせる（第5.9節）
4. **人間に確認したい保留事項**（決定ではなく計画書の運用上の確認。下記「フレームワーク本体の不足」参照）
   - `reports/` を木に加えてよいか
   - `examples/software-factory/` の骨格を初期化で作らなかった判断でよいか

## 2026-10-22

### 完了したこと

- `git init`（リモート未設定。push はしない）
- 第4節のディレクトリ骨格（言語に依存しない範囲）を `.gitkeep` で作成: `schema/examples`、`contract`、`runtime`、`testing/{spec,harness,oracle,stages,e2e,triage}`、`examples/toy-minimal/{stages,tests}`、`reports`
- `schema/workflow.schema.json` に付録 A の基底スキーマを**そのまま**配置（plan.md の JSON ブロックを機械的に抽出。バイト一致を検証で確認）。拡張（carry / max / artifacts / 指標の形）は ADR 決定後の F1 本体で行う
- `docs/decisions.md`: ADR-001〜ADR-010 の下書き（文脈、選択肢ごとの帰結、推奨、強制点、付随する小決定、空欄の決定）。推奨は計画書第3節の推奨欄をそのまま採用し、独自に変えていない。ADR-010 には環境の確認結果（Python 3.12.3、uv あり、jsonschema 4.10.3 / PyYAML 6.0.1 あり、ruff / pytest 無し）と、パッケージ配置の小決定（P1 / P2 / P3）を加えた
- `docs/progress.md`（本ファイル）
- 初期コミット

### 未完了と理由

- ツールチェーンの骨格（pyproject、CI、.gitignore）: ADR-010 が未決のため作っていない（計画書 F1「決定 #10 が出たらツールチェーンの骨格と CI の雛形を作る」）
- スキーマの拡張、検査器、契約、toy-minimal: ADR-001 / 002 / 005 / 007 が未決のため着手していない
- `examples/software-factory/` の骨格: 意図して作っていない。F4 の利用者セッションが adopting.md と雛形だけから作る成果物で、骨格を先に置くと adopting.md 以外のヒントを与えて F4 の検証（文書の十分性）が弱まる。人間が覆してよい
- `docs/adopting.md`、`docs/harness-plan-template.md` のプレースホルダ: 同様に F2 / F5 の成果物なので作っていない

### 発見した問題

#### ワークフロー定義の問題

なし（まだワークフロー定義が存在しない）

#### フレームワーク本体の不足

- **第4節の木に `reports/` が無い**が、第5.9節（検証役の書き先は `reports/` のみ）と第5.10節（`reports/dynamic/<id>/`）が参照している。食い違いなので `reports/` を作成した。plan.md 本文への反映は人間の確認を待つ（plan.md は保護ファイルで計画エージェントが編集できるが、計画書本文の変更は人間の確認を経たい）
- **第4節の木にフレームワーク自身のテスト（検査器のテスト、契約適合テスト等）の置き場が無い**。`testing/` はランナーの実装であってテストではない。ADR-010 の小決定（パッケージ配置）で `tests/` の追加として扱う
- **`reports/` の内部構造が `reports/dynamic/<id>/` 以外は未定義**。検証役の報告の置き場（例: `reports/verification/<task>/`）は、F1 本体で検証役を初めて使う時に決めて記録する

### 実行した検証とその結果の要旨

完了条件は実装より先に `check_init.py`（scratchpad: `/tmp/claude-1000/-home-asuka1975-work-ai-agent-harness-testing-framework-v2/f80f9564-2bb2-49fb-bea0-291c97af6aa8/scratchpad/check_init.py`。ツールチェーン未決のためリポジトリには置かず、ADR-010 決定後に `tests/` へ移植する）として書いた。検査内容:

1. 骨格ディレクトリの存在、`examples/software-factory` が無いこと、`.git` の存在
2. `schema/workflow.schema.json` が JSON として読め、`jsonschema.Draft202012Validator.check_schema` を通る
3. 同ファイルが plan.md 付録 A の JSON ブロックとパース後に等しく、かつバイト一致する
4. `docs/decisions.md` に `## ADR-001`〜`## ADR-010` がちょうど10件あり、各 ADR に「### 推奨」「### 決定」「- 強制点:」がある
5. `docs/progress.md` の先頭の節が「次にやること」で、固定の4小節と「発見した問題」の二分がある

実行コマンドと結果:

```text
$ python3 -I <scratchpad>/check_init.py .
ok   dir exists: schema/examples ... ok   dir exists: reports   （13 ディレクトリ）
ok   examples/software-factory is NOT pre-created (F4 の成果物)
ok   git repository initialized
ok   schema parses and conforms to Draft 2020-12 metaschema
ok   appendix A json block found in plan.md
ok   schema/workflow.schema.json equals appendix A (parsed JSON equality)
ok   schema/workflow.schema.json is byte-identical to appendix A block
ok   decisions.md has heading ADR-001 ... ADR-010 / exactly 10 ADR sections
ok   ADR-001..010 each has 決定 / 推奨 / 強制点
ok   progress.md first section is 次にやること / 4 subsections / 発見した問題 の二分
0 failure(s)
exit=0
```

負例の確認（検査が空振りでないこと）: スキーマのコピーを壊した作業コピーに対して同じ検査を実行し、メタスキーマ検査と付録 A 一致の項目が FAIL になり終了コードが 1 になることを確認した。

```text
$ # コピー negctl/ の schema の "type" を "objekt" に書き換えてから
$ python3 -I check_init.py negctl
FAIL schema metaschema check: 'objekt' is not valid under any of the given schemas
FAIL schema/workflow.schema.json equals appendix A (parsed JSON equality)
FAIL schema/workflow.schema.json is byte-identical to appendix A block
3 failure(s)
exit=1
```
