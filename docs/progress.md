# 作業ログ

形式は計画書第4節末尾で固定。先頭に「次にやること」、続いて日付ごとに「完了したこと」「未完了と理由」「発見した問題（ワークフロー定義 / フレームワーク本体）」「実行した検証とその結果の要旨」。

## 次にやること

2026-10-22 に ADR-001〜005、007〜010 が決定した（ADR-009 は (b) を v1.0 に含める）。ツールチェーンの骨格は作成済み。F1 本体を次のタスク列で進める（第5.1節）。各タスクの完了条件はコマンドで確かめ、結果を本ファイルに残す。

1. **完了条件（テスト）を先に書く**: `tests/test_schema_examples.py`（正例が通り負例が落ちる）、`tests/test_checker.py`（検査コードごとに負例があり、各負例がそのコードを報告する。コードカタログと負例集合の一致）、`tests/test_toy_minimal.py`（toy-minimal が検査を通り、要求された遷移の形を静的に含む）。完了条件: `uv run pytest --collect-only` が収集でき、実装前は失敗する
2. **拡張スキーマ** `schema/workflow.schema.json` と `schema/examples/{positive,negative,children}/`、`schema/examples/metrics.json`。完了条件: `uv run pytest tests/test_schema_examples.py tests/test_repo_layout.py`
3. **整合性検査器** `src/htf/testing/spec/`（`check_workflow`、`CODES`、CLI `python -m htf.testing.spec`）。完了条件: `uv run pytest tests/test_checker.py`
4. **ハーネス契約** `src/htf/contract/`（Protocol と `CONTRACT.md`: 三操作、スナップショット形式、ステージ本体・指標・ユーザー入出力・LLM クライアント、6 種の遷移の列挙）。完了条件: `uv run ruff check . && uv run pytest`
5. **toy-minimal** `examples/toy-minimal/workflow.yaml`、子 `elaborate-claim.yaml`、`metrics/manifest.json`。完了条件: `uv run python -m htf.testing.spec examples/toy-minimal/workflow.yaml --metrics examples/toy-minimal/metrics/manifest.json` が 0 で終わる
6. **検証役**（実装を見ていない general-purpose サブエージェント。第5.10節の宣言を本ファイルに書いてから起動）: 完了条件の判定、toy-minimal の MECE 事前レビュー。書き先 `reports/verification/f1-contract-and-spec/`
7. **人間ゲート**: スキーマと契約の承認、toy-minimal のレビュー、F1 で新たに確定した小決定の一覧（decisions.md の該当 ADR に「F1 で確定、ゲートで承認」の印）。F2 には入らない

`reports/` の構造（本日決定）: `reports/verification/<task-id>/report.md`（検証役の報告）、`reports/dynamic/<id>/`（動的ワークフロー、第5.10節）、`reports/triage/`（F3 以降）。

人間に確認したい保留事項（決定ではなく運用上の確認）: `reports/` を第4節の木に加えてよいか。`examples/software-factory/` の骨格を初期化で作らなかった判断でよいか。

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

完了条件は実装より先に `check_init.py` として書いた。ツールチェーン未決のためリポジトリには置かず、全文を本節末尾に埋め込む（ADR-010 決定後に `tests/` へ移植する。再実行は全文をファイルに保存して `python3 -I check_init.py <リポジトリのルート>`）。検査内容:

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

`check_init.py` の全文:

```python
"""F1 初期化タスクの完了条件（実装より先に書いた検査）。

引数: リポジトリのルート。終了コードは 0 なら全条件を満たす。
条件:
  1. 第4節の骨格ディレクトリが存在する（language-agnostic な範囲）
  2. schema/workflow.schema.json が JSON として読め、Draft 2020-12 メタスキーマに適合する
  3. schema/workflow.schema.json の内容が docs/plan.md 付録 A の JSON ブロックと一致する（「そのまま置く」）
  4. docs/decisions.md に ADR-001〜ADR-010 の見出しがあり、各 ADR に「決定」節がある
  5. docs/progress.md の先頭の節が「次にやること」で、固定された4つの小節を持つ
"""

import json
import re
import sys
from pathlib import Path

import jsonschema

root = Path(sys.argv[1]).resolve()
failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


# 1. 骨格
for d in [
    "schema/examples",
    "contract",
    "runtime",
    "testing/spec",
    "testing/harness",
    "testing/oracle",
    "testing/stages",
    "testing/e2e",
    "testing/triage",
    "examples/toy-minimal/stages",
    "examples/toy-minimal/tests",
    "docs",
    "reports",
]:
    check((root / d).is_dir(), f"dir exists: {d}")
check(
    not (root / "examples/software-factory").exists(),
    "examples/software-factory is NOT pre-created (F4 の成果物)",
)
check((root / ".git").is_dir(), "git repository initialized")

# 2. スキーマがメタスキーマに適合
schema_path = root / "schema/workflow.schema.json"
schema = None
try:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    check(True, "schema parses and conforms to Draft 2020-12 metaschema")
except Exception as e:  # noqa: BLE001
    check(False, f"schema metaschema check: {e}")

# 3. 付録 A と一致
plan = (root / "docs/plan.md").read_text(encoding="utf-8")
m = re.search(r"## 付録 A.*?```json\n(.*?)```", plan, re.S)
check(m is not None, "appendix A json block found in plan.md")
if m and schema is not None:
    check(
        json.loads(m.group(1)) == schema,
        "schema/workflow.schema.json equals appendix A (parsed JSON equality)",
    )
    check(
        schema_path.read_text(encoding="utf-8") == m.group(1),
        "schema/workflow.schema.json is byte-identical to appendix A block",
    )

# 4. decisions.md
dec = (root / "docs/decisions.md").read_text(encoding="utf-8")
for i in range(1, 11):
    check(
        re.search(rf"^## ADR-{i:03d}\b", dec, re.M) is not None,
        f"decisions.md has heading ADR-{i:03d}",
    )
sections = re.split(r"^## ADR-", dec, flags=re.M)[1:]
check(len(sections) == 10, f"decisions.md has exactly 10 ADR sections (found {len(sections)})")
for s in sections:
    adr_id = s.split()[0]
    check(re.search(r"^### 決定", s, re.M) is not None, f"ADR-{adr_id} has a 決定 section")
    check(re.search(r"^### 推奨", s, re.M) is not None, f"ADR-{adr_id} has a 推奨 section")
    check(re.search(r"^- 強制点:", s, re.M) is not None, f"ADR-{adr_id} has a 強制点 line")

# 5. progress.md
prog = (root / "docs/progress.md").read_text(encoding="utf-8")
heads = re.findall(r"^## (.+)$", prog, re.M)
check(
    bool(heads) and heads[0].strip() == "次にやること", "progress.md first section is 次にやること"
)
for h in ["完了したこと", "未完了と理由", "発見した問題", "実行した検証とその結果の要旨"]:
    check(re.search(rf"^### {h}", prog, re.M) is not None, f"progress.md has subsection {h}")
for h in ["ワークフロー定義の問題", "フレームワーク本体の不足"]:
    check(
        re.search(rf"^#### {h}", prog, re.M) is not None,
        f"progress.md splits 発見した問題 into {h}",
    )

print()
print(f"{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
```

### 動的ワークフローの宣言（第5.10節）: `f1-contract-and-spec`

- **目的**: F1 の完了条件の第三者判定（実装した本セッションに判定を任せない。第5.9節）と、toy-minimal の workflow.yaml / elaborate-claim.yaml の MECE 事前レビュー（人間に出す前の必須工程）
- **役割と人数**: 検証役 1（general-purpose サブエージェント。本セッションの文脈を継がない新規起動。fork は使わない）
- **入力**: docs/plan.md（第6節 F1、付録 A / B）、docs/decisions.md、schema/、src/htf/contract/（CONTRACT.md、types.py、interfaces.py）、examples/toy-minimal/、tests/、検査器 CLI（`uv run python -m htf.testing.spec`）と `uv run pytest` の出力。判定は実行した結果を根拠にする（コードを読んで「正しそう」で判定しない）
- **書いてよいパス**: `reports/verification/f1-contract-and-spec/` のみ。保護ファイルと本体コードは書かない
- **完了条件**: `reports/verification/f1-contract-and-spec/report.md` に (1) F1 完了条件の各項目（スキーマのメタスキーマ適合、正例が通り負例が落ちる、検査器の各性質に負例がある、toy-minimal が検査を通る、契約が文書化されている）の判定（満たす / 満たさない / 判定不能）と根拠（実行したコマンドと出力の要旨）、(2) toy-minimal と子の各ステージの end_state について、記述が成果物から観測可能か、互いに排他か、各 end_state に戻り先があるか、優先順が記述にあるかのレビュー、(3) 発見した問題（ワークフロー定義の問題と本体の不足を分ける）、(4) 検証役が判定できなかった事項
- **予算**: トークン 20 万、時間 20 分、フレームワーク外の LLM 呼び出し 0
- **反復の上限**: 1（再実行しない。不足は計画エージェントが判断する）
- **入れ子の深さ**: 0（検証役はサブエージェントを起動しない）
- **受け入れ**: 報告は第5.3節 4 の検証（本セッションでの `uv run pytest` と CLI の再実行）を通してから受け入れる。報告の中だけで成立する判断は残さない
