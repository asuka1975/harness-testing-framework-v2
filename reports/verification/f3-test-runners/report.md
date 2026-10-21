# 検証報告: F3 テストランナー群（動的ワークフロー `f3-test-runners`）

- 検証役: 実装エージェントとは別のサブエージェント（general-purpose）。2026-10-22
- 対象コミット: `7d32e7c`（HEAD）。テスト `b03a4b1`、実装 `bddcb77`
- 書いたもの: 本報告と探針（`reports/verification/f3-test-runners/` 配下のみ）。本体・テスト・toy・docs は変更していない
- 予算: フレームワーク外の LLM 呼び出し 0、サブエージェント起動なし。時間約 13 分（02:38〜02:50、探針の実行を含む）、トークン約 15 万（宣言の 25 分 / 25 万の内側）

## 総合判定: **満たさない（項目 4 の後半「split で予測が外れる」のみ。1〜3、5〜7 と 4 の前半は満たす）**

- 計画書第6節 F3 の文言どおりの条件と「テストが実装より先」は、すべて実行結果で確認した（1〜3、5〜7 は満たす。4 は E2E 到達 17/17 と markov の一致を満たす）
- しかし `test_markov_prediction_deviates_for_split_body` が通るのは、合成に子 run 数（観測は常に 2）を渡さず既定の 1 で合成しているためで、**観測どおり子 2 で合成すると split の予測と実測の差は 0.010 と、許容差 0.1 の内側**に入る（探針 P4b）。同じ理由で markov の一致テストも差 0.094 と許容差 0.1 の縁にある。つまり現在のテストは「マルコフ性の破れ」ではなく「子 run 数の取り違えの大きさ」で markov と split を見分けている。ADR-013 13.11 自身が「子 run の数は観測された分布から引く」と定めているので、これは選択ではなく欠陥（B1）。toy の split 構成は結果（completed / aborted）の頻度では原理的にほぼ検出できない設計なので、テストと負例の作り直しを勧める（第 4 節 T1 / B1）
- 問題点: toy の構成 4 件（T1〜T4）、フレームワーク本体 8 件（B1〜B8）。判定できなかった事項 4 件

## 1. F3 完了条件の判定

共通に実行したもの（リポジトリのルート）:

```
uv run pytest -o addopts="" -q            → 127 passed in 50.23s   (pytest_full.log)
PYTHONPATH=reports/verification/f3-test-runners uv run pytest -o addopts="" -p blocknet -q
                                          → 127 passed in 50.22s   (pytest_blocknet.log。socket を禁止した状態)
uv run pytest -o addopts="" -q --cov=htf.testing --cov=htf.runtime   → 127 passed、TOTAL 92%   (pytest_cov.log。付録)
```

| # | 条件 | 判定 | 根拠（コマンドと出力の要旨） |
| --- | --- | --- | --- |
| 1 | すべて LLM なし | **満たす** | 依存は `jsonschema` と `PyYAML` だけ（pyproject）。`grep -rniE "anthropic\|openai\|requests\.\|urllib\|httpx\|socket\|api_key" src/ examples/ tests/` は 0 件。探針 P0: `socket.socket` / `create_connection` / `getaddrinfo` を例外にする pytest プラグイン `blocknet.py` を付けて全テストを実行し 127 passed。分類器の実装は `MarkerClassifier`（成果物の印を読む）、`ConfusionClassifier`（文書の `truth:` 行と混同行列）、`FixedClassifier`（契約適合テスト用）、`RecordedClassifier`（再生）で、LLM は `EchoLLM` と `RecordedLLM` だけ。条件の文言「MarkerClassifier / ConfusionClassifier と EchoLLM だけ」より実態は少し広いが、いずれも LLM を呼ばない |
| 2 | 正しい expectations が通り、ずらした expectations が落ちる | **満たす** | `test_correct_expectations_pass` / `test_shifted_expectations_fail` が通る。探針 P1: markov.yaml の全 7 セルと outcomes が区間内で、最小の余裕は `verify.first.goal` の下限側 +0.071（観測 0.521、N=286）。markov_shifted.yaml は `verify.first.goal` 観測 0.521 に対し min 0.8 で差 0.279 と、偶然ではない。別の run 種 3 本（1、2000、31337）でも markov は通り shifted は落ちる |
| 3 | 独立性検証が split を検出し markov を検出しない | **満たす** | `test_split_class_is_detected` / `test_unsplit_class_is_not_flagged` が通る。探針 P2: split は G=159.6、p は並べ替え回数の下限 1/(perms+1)（100 回 0.0099、300 回 0.0033、1000 回 0.0010）に張り付き、並べ替えの種 1〜10 で不変。別の run 種（1、2000）でも p=0.0033。markov は G=1.66、p=0.38〜0.48（300 回、種 1〜10）、別の run 種では 0.77〜0.93 で検出されない |
| 4 | E2E 計画が 17 対象を誘発と注入の両方で踏み、マルコフ予測が実測と一致し、split では外れる | **一部満たさない**（到達と markov の一致は満たす。split で外れるのは見かけ上） | 探針 P3(f): 対象 17、到達 17、未到達なし、誘発 15、注入 2（`draft/unknown`、`check_section/unknown`）。計画の 17 項目すべてが自分の run で自分の対象を踏む（他の run が偶然踏んだ分で満たされていない）。注入された記録は `injected=True`、reason `注入（元の判定: goal）`。マルコフ: 探針 P4b で、テストどおり（`samples=` なし → 子 run 数 1）だと markov の差 0.094（ok）、split の差 0.163（NG）。観測した子 run 数（常に 2）を渡すと markov 0.009、**split 0.010（ok になる）**。split 構成の pooled 行列でも結果頻度はほぼ同じになる（第 4 節 T1 の解析）ので、「split で外れる」は子 run 数の取り違えが split で大きく出ているだけ |
| 5 | 偽の分類器で既知の κ と ECE を再現し、違う κ を期待すると落ちる | **満たす** | `test_reproduces_known_kappa_and_ece` / `test_wrong_expected_kappa_is_rejected` が通る。探針 P5: 対角 0.4〜1.0 の 6 行列で観測 κ と解析 κ の差は +0.012 以内。分類器の種 10 本（N=6000）で差 −0.014〜+0.012。ECE は較正済みで 0.0023、確信度 0.95 固定で 0.1510（理論 0.1500）。「違う κ」は差 0.112（diag 0.85）で棄却されるが、diag 0.8（κ 0.654、差 0.030）と diag 0.75（差 0.049）は見分けられない（閾値 0.1 の粒度） |
| 6 | トリアージにサンプル一件を流せる | **満たす** | `test_one_unknown_flows_through_triage` が通る（unknown → enqueue 1 件 → `label` → `export_corpus` → `load_corpus` のラベル一致）。探針 P3(b): 注入で作った unknown も 1 件積める |
| 7 | テストが実装より先に書かれている | **満たす（注記あり）** | `git log`: `b03a4b1`（02:23:08、tests/test_f3_*.py 5 本と toy の profiles / expectations / plan.yaml）→ `bddcb77`（02:36:45、実装）。ただし `git diff b03a4b1 bddcb77 -- tests/` で、実装コミットがテストにも触れている。4 本は `ruff format` 相当の整形のみだが、`test_f3_oracle.py` の `_corpus` は文書に `truth: <label>` 行を加える**実質的な変更**（`ConfusionClassifier` が真のラベルを文書から読む設計に合わせた）。完了条件の意味は変わっていないが、「テストを先に固定して実装を合わせる」規則からは逸脱している（第 4 節 B8） |

## 2. 自作の探針（6 件。スクリプトとログは本ディレクトリ）

| 探針 | スクリプト / ログ | 内容と結果 |
| --- | --- | --- |
| P0 ネットワーク禁止 | `blocknet.py` / `pytest_blocknet.log` | socket 生成を禁止して全テスト → 127 passed。LLM API 呼び出しなしの直接証拠 |
| P1 区間の余裕 | `probe_dist.py` / `probe_dist.log` | markov.yaml の各セルの観測値と区間の差（N=286〜556）: 余裕は 0.071〜0.136。shifted は差 0.279。下限を名目値 0.55 まで下げても落ちる（観測 0.521 は名目より約 1 SE 下）。別の run 種 3 本で `verify.first.goal` は 0.503〜0.597 と動く（SE≈0.03 どおり）が markov は通り shifted は落ちる |
| P2 独立性の p 値 | 同上 | 並べ替え回数 100 / 300 / 1000 × 種 1〜10 × 別 run 種。split は常に p の下限、markov は 0.33〜0.93 で安定。`downstream="next"` でも split は検出。`verify/checks_failed` は carry が主張を識別しないので群が 1 つ（p=1.0、permutations=0）で検証できない |
| P3 注入 | `probe_inject.py` / `probe_inject.log` | (a) `verify#1` に `checks_failed` を注入: 記録 `injected=True`、reason `注入（元の判定: goal）`、trace は `rollback_across_phase verify→draft` → `draft#2` → `verify#2`（entry=2）。ただし本体は `failing_checks` を emit していないので **carry_out={}**（戻り先は空の carry で動く）。(b) `draft#1` に unknown: escalate → abort、triage に 1 件積まれる（注入由来と分かるのは reason の文字列だけ）。(c) `check_section#1` に unknown: **両方の子 run** に効き、親は集約で unknown。(d) 存在しないステージ / 進入回数の鍵は黙って無視。(e) 子を持つ `elaborate#1` に `sections_inconsistent`: `rollback_within_phase elaborate→verify` が起きる。(f) E2E 計画の到達表（上記 4） |
| P4 / P4b マルコフ合成の余裕 | `probe_dist.py`、`probe_markov_children.py` / `probe_markov_children.log` | 合成の種 1〜10: 子 run 数を観測から渡すと markov 0.001〜0.012、split 0.002〜0.025。テストどおり（子 1）だと markov 0.085〜0.097（許容差 0.1 の縁）、split 0.154〜0.169。`child_counts={"elaborate": [2]}` 明示でも split は 0.000〜0.017 |
| P5 オラクル検証 | `probe_oracle.py` / `probe_oracle.log` | κ の追従（6 行列、差 ≤0.012）、種依存（N=6000 で ±0.014、N=500 では 10 本中 2 本が 0.03 超）、ECE のビン数依存（1〜100 ビンで 0.0023〜0.0027。較正済みの確信度は 3 値 {0.4545, 0.8077, 0.8571} しか取らないのでビンは効かない）、確信度を精度+δ にずらすと ECE=δ+0.002 と線形、「違う κ」の分解能は 0.1 |
| P6 成果物との整合 | `probe_dist.py` | markov 300 run の verify 記録: `checks_failed` 105 件はすべて `decided_by=classifier` で `verified_ratio=0.5`（指標 min 0.8 を割る）、`goal` 278 件は `qualitative` で 1.0、`inputs_missing` 15 件は `classifier` で 0.5、`unknown` 46 件は `threshold` で 1.0。確率的本体が書く成果物と判定の経路は整合しており、指標は本物の値を返している。split の `check_section` 再進入は goal 75 / inconsistent 141 |

## 3. ADR-013 の閾値（仮置き）について人間に見せるべき懸念

- **13.4 区間（expectations）**: 統計的検定をせず、固定の種での観測頻度が区間に入るかで判定する。N≈290 では 1 SE≈0.03 で、markov.yaml の余裕 0.07〜0.14 は 2.4〜4.5 SE。toy では十分だが、実データでは (a) セルごとの N が run 数より小さい（`verify.first` は 300 run で 286、`verify.reentry` は 158）、(b) 複数セルを同時に見るので偶然の違反が積み上がる、(c) 種を固定すると「通る種」を選べてしまう、の三点がある。区間を「名目 ± k·SE」か信頼区間で書ける形にするか、N と区間幅の関係を文書に書くことを勧める。実データ無しに幅は決められない
- **13.7 並べ替え回数と有意水準**: p の下限は 1/(perms+1) なので、**200 回（既定）なら 0.005、100 回なら 0.0099** と、split 用の閾値 0.01 に近づく。回数と閾値は組で決める必要がある（テストは 300 回で ADR の既定 200 と違う）。分割なしの判定 p ≥ 0.05 は設計上 5% の偽陽性を持ち、固定の種がそれを隠している。クラス × ステージを多数検査すると多重比較になる。また代表の鍵の既定（carry のハッシュ）は carry が代表を識別する時だけ働き、識別しない場合（`verify/checks_failed`）は群 1 つで p=1.0 と「検証不能」が「未検出」に見える（B5）
- **13.8 κ / ECE の許容差**: κ ±0.03 は N=6000 で約 3 SE（観測の揺れ ±0.014）だが、**N=500 では 10 本中 2 本が外れる**。許容差は N に依存するので、N を規定に含めるか SE 倍数で書くべき。ECE < 0.03 は「確信度の系統的なずれ δ ≈ 0.03」まで検出できる（δ と ECE が線形）。ビン数 10 の既定は、偽の分類器では確信度が 3 値しか取らず意味を持たない。実際の LLM 分類器の確信度の分布が出るまでビン数は決められない。「違う κ」の分解能 0.1 は、混同行列の対角が 0.05 違う程度は見分けない
- **13.11 マルコフの許容差 0.1**: 比較が completed / aborted の 2 値（事実上 1 つの数）なので粗い。子 run 数を正しく渡せば markov の差は 0.01 程度で、0.1 は 10 倍の余裕。逆に、toy の split のような「クラス内で代表ごとに下流が分かれる」破れは結果頻度にほぼ現れない（第 4 節 T1）。検出力を持たせるには、比較の粒度をステージ別の進入回数 / クラス頻度や run 長の分布に広げるか、負例を結果頻度に効く形（例: first の結果が後段の分布に影響する履歴依存）にする必要がある。許容差は粒度を決めてからでないと決められない
- **13.13 常時実行 50 秒**: 分布 / E2E テストが毎回 300 run × 4 構成を走らせる。CI の段階分けは F5 とあるが、今の時点で `-m "not distribution and not e2e"` が使えることは文書に書いてよい

## 4. 発見した問題

### toy-minimal の構成（profiles / expectations / plan / 偽本体）

- **T1（重要）split 構成はマルコフ合成の負例として機能していない**。split では奇数番目の主張（主張B）の再進入が必ず inconsistent になる。pooled の遷移行列 P(inc | reentry)=0.653 で子 2 つを合成すると P(いずれかの子が stuck)=1−(1−0.407×0.653)²≈0.46、真の構造（A: 0.407×0.25、B: 0.407×1.0）では 1−0.90×0.59≈0.47 とほぼ同じになり、結果頻度では区別できない（探針 P4b: 差 0.010）。テストが通るのは `synthesize_outcomes` に `samples=` / `child_counts=` を渡しておらず子 run 数が既定 1 になるためで、その誤差が split で大きく出ているだけ。修正案: (1) テストに `samples=samples` を渡す（markov の差は 0.009 になる）、(2) 負例を結果頻度に効く形にする（例: `verify` の first が `checks_failed` だった run では以後の `check_section` の分布が変わる、といった履歴依存の split）か、比較をステージ別のクラス頻度にする。expectations 形式の改訂は要らない（形式の改訂回数 0 のまま）
- **T2 markov の一致テストが許容差の縁**: テストどおりの合成で差 0.094（許容差 0.1）。別の run 種で観測の completed が 0.63 → 0.62 に動けば落ちる。T1 の修正 (1) で解消する
- **T3 split.yaml（expectations）は使われ方が限定的**: `runs` と `seed` の供給元としてだけ使われ、`check_section.first.inconsistent` の区間はどのテストも検査していない。削るか、独立性テストで `check_expectations` も通すかを決めるとよい
- **T4 代表の鍵が親ステージで働かない**: `verify` の `checks_failed` の carry（`failing_checks: claims[:1]`）は常に主張A なので群が 1 つになり、親側のクラスでは独立性検証を試せない。toy として「検証できないクラス」の例になっているなら README に書く。失敗した主張を分布から選ぶ本体にすれば親側でも検証できる

### フレームワーク本体の不足（runtime / ランナー / 形式 / 文書）

- **B1 `synthesize_outcomes` が子 run 数を黙って 1 にする**: `child_counts` も `samples` も無い時に `[1]` を使う。ADR-013 13.11 は「子 run の数は観測された分布から引く」と書くが、既定はそうなっていない。子を持つワークフローでは必須引数にするか、未指定なら例外か警告にすべき。adopting.md 第 6 節にも子 run 数の渡し方の記述が無い
- **B2 注入は Verdict だけを差し替え、成果物と memory は本体のまま**: 探針 P3(a)で `checks_failed` を注入すると `carry_out={}` で戻り先が空の carry で動く（`Draft` は「再提出」行を書かない）。E2E カバレッジ（記録上の到達）には十分だが、「戻り先が carry を受けて動く」経路は注入では踏めない。文書（adopting.md 第 6 節、ADR 13.3）に「注入は carry を伴わない」と明記するか、`inject` に carry を添えられるようにする
- **B3 注入の鍵が (stage_id, entry) だけ**: 子 run すべてに効く（P3(c)。toy では両方の主張）し、親と子に同名のステージがあれば両方に効く。鍵に workflow 名を含めるか、文書で制限を書く
- **B4 存在しない注入の鍵が黙って無視される**（P3(d)）。`Runner` でワークフロー定義と照合して `ValueError` にすべき（計画の typo が「未到達」としてしか現れない）
- **B5 独立性検証の「検証不能」が「未検出」と同じ顔をする**: 群が 1 つの時 `p_value=1.0, flagged=False, permutations=0` を返す。`IndependenceReport` に `verifiable: bool`（または例外）を足し、閾値判定と分けるべき
- **B6 トリアージが注入由来の記録を区別しない**: `TriageQueue.enqueue` は `injected` を見ず、`TriageItem` にもその欄が無い（P3(b)）。E2E 計画の run をそのままトリアージすると注入 unknown がコーパス候補に混ざる。`injected` を項目に持たせ既定で除くか、enqueue の引数で選べるように
- **B7 下流 `end` の意味が混ざる**: `downstream="same_stage"` の `end` は「max 超過で escalate」「他ステージの unknown で run が止まった」「正常完了」を区別しない（split の群 `{'inconsistent': 109, 'end': 132}` の `end` 132 には write_section の unknown 由来とみられる約 23 件が混じる。132−109 からの推定）。終端の種類（completed / aborted:<stage>）を下流の値に含めると検定の意味がはっきりする
- **B8 テストを先に固定する規則の逸脱（手順）**: 実装コミット `bddcb77` が `tests/test_f3_oracle.py` の `_corpus` を変更している（文書に `truth:` 行を追加）。`ConfusionClassifier` が真のラベルを文書に埋める設計自体は妥当だが、F3 の運用規則「完了条件のテストは実装より先に別コミット」に照らすと、テストの変更は別コミットにして理由を残すべきだった。併せて、この偽分類器の文書形式（`truth:` 行）は実コーパスには無いので、ランナーの検証専用であることを docstring 以外（adopting.md）にも書く

## 5. 判定できなかった事項

- **閾値の妥当性そのもの**（13.4 / 13.7 / 13.8 / 13.11）: 実データ（LLM 分類器の確信度分布、実ステージの N）が無いので、toy で成立する幅から実データの幅は決められない。第 3 節の形で人間に出す
- **v0.1 として公開**（計画書 F3 の最後の条件）: tag も GitHub Release も人間の承認待ち（progress.md のとおり）なので判定の対象外
- **expectations 形式で書けない基準の有無**（戻る条件）: toy の基準はすべて書けている。実ワークフロー（F4）の基準が出るまで判定不能
- **CI 上の実行**: リモート未設定のため GitHub Actions は未実行。ローカルの `uv run pytest` の結果で代替した

## 付録: カバレッジ（`uv run pytest -o addopts="" -q --cov=htf.testing --cov=htf.runtime`、127 passed）

| モジュール | 行カバレッジ |
| --- | --- |
| htf/runtime（合計） | runner 93%、oracle 86%、context 90%、他 96〜100% |
| htf/testing/stages | 91% |
| htf/testing/e2e | 91% |
| htf/testing/oracle | 93% |
| htf/testing/triage | 75%（`dismiss`、`get` の失敗経路、低確信度の経路がテストに無い） |
| htf/testing/harness | 83% |
| TOTAL（testing + runtime） | 92% |

F3 の完了条件にカバレッジの数値は無い。参考値として置く。
