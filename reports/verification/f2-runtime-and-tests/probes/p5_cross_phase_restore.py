"""P5: フェーズ境界を越えるロールバックで、戻り先（draft）の開始時スナップショットが復元され、carry の鍵だけが重なるか。
再進入時の作業ディレクトリの中身（draft.md は消え、後段の report.json は残るか）、snapshot store のレイアウト。"""

import dataclasses
import json

from _common import SCENARIOS, run_toy, show, toy
from htf.runtime import snapshot_digest


class SpyDraft:
    def __init__(self, inner):
        self.inner = inner
        self.entries = []

    def run(self, ctx):
        files = sorted(p.relative_to(ctx.workspace).as_posix() for p in ctx.workspace.rglob("*") if p.is_file())
        self.entries.append(files)
        self.inner.run(ctx)


sc = toy.harness.load_scenario(SCENARIOS / "checks_failed_once.yaml")
from toy_minimal.stages import Draft, ScriptCursor

spy = SpyDraft(Draft(ScriptCursor(sc.outcomes)))
runner, r = run_toy(sc, bodies_override={("toy-minimal", "draft"): spy})
show("checks_failed_once（draft に探針）", r)
for i, files in enumerate(spy.entries):
    visible = [f for f in files if not f.startswith(".htf/")]
    print(f"  draft 進入 {i + 1} 回目に見える成果物: {visible}  (.htf 配下のファイル数: {sum(f.startswith('.htf/') for f in files)})")

starts = [s for s in r.start_snapshots if s.stage_id == "draft"]
files_only = lambda s: snapshot_digest(dataclasses.replace(s, memory={}))
print("  draft の開始時スナップショット 2 つの files digest 一致:", files_only(starts[0]) == files_only(starts[1]))
print("  memory の差分（2 回目 − 1 回目）:", {k: v for k, v in starts[1].memory.items() if starts[0].memory.get(k) != v})
print("  1 回目の memory:", starts[0].memory)
print("  draft 開始時 files の中身:", [p.name for p in starts[0].files.rglob("*")], "(draft.md は開始時には無い)")

store = runner.rt.store.root
first = sorted(store.iterdir())[0]
meta = json.loads((first / "meta.json").read_text())
print("  store レイアウト:", sorted(p.name for p in first.iterdir()), " meta.json の鍵:", sorted(meta))
print("  store の ordinal 数:", len(list(store.iterdir())), " start+end の数:", len(r.start_snapshots) + len(r.end_snapshots), "(差はフェーズゲート用の仮スナップショット)")
