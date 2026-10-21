"""P3: 記録 → 再生で LLM・分類器・ユーザーを None にしても同じ end スナップショットの digest になるか。
ロールバックを含む台本（checks_failed_once）、中断再開（suspend_resume）、本体を変えた再生、記録の余りや欠落。"""

import json
from collections import Counter

from _common import SCENARIOS, tmp_ws, toy
from htf.runtime import Recorder, ReplayMismatch, Runner, RunStatus, load_workflow, snapshot_digest
from htf.testing.harness import ScriptedHuman


def run(scenario, log, mode, *, replay, answers=None):
    wf = load_workflow(toy.harness.WORKFLOW_PATH, metric_names=toy.harness.registry().names())
    b = toy.harness.make_bindings(scenario, human=ScriptedHuman([]), replay=replay)
    runner = Runner(wf, b, workspace=tmp_ws(), recorder=Recorder(log, mode=mode))
    r = runner.run()
    for a in list(answers or []):
        if r.status is RunStatus.SUSPENDED:
            r = runner.resume(a)
    return r


def kinds(log):
    return dict(Counter(json.loads(l)["kind"] for l in log.read_text().splitlines() if l.strip()))


def digests(r):
    return [snapshot_digest(s) for s in r.end_snapshots]


# R1: ロールバックと無効化を含む台本
sc = toy.harness.load_scenario(SCENARIOS / "checks_failed_once.yaml")
log = tmp_ws().parent / "cfo.jsonl"
rec = run(sc, log, "record", replay=False)
rep = run(sc, log, "replay", replay=True)
print("R1 checks_failed_once: 記録の内訳", kinds(log))
print("   end digest 一致:", digests(rec) == digests(rep), " trace 一致:", [t.kind for t in rec.trace] == [t.kind for t in rep.trace],
      " gates 一致:", rec.gates == rep.gates, " 件数:", len(digests(rec)))

# R2: 本体の振る舞い（台本）を変えて再生 → ReplayMismatch
try:
    run(sc.with_outcomes(verify=["goal"]), log, "replay", replay=True)
    print("R2 本体を変えた再生: 例外なし（期待外れ）")
except ReplayMismatch as e:
    print("R2 本体を変えた再生: ReplayMismatch:", str(e)[:140], "…")

# R3: 中断再開の台本。resume() で与えた回答は記録に残るか
sc2 = toy.harness.load_scenario(SCENARIOS / "suspend_resume.yaml")
log2 = tmp_ws().parent / "sr.jsonl"
rec2 = run(sc2, log2, "record", replay=False, answers=sc2.answers)
print("R3 suspend_resume: 記録の内訳", kinds(log2), " status:", rec2.status.value, " transitions:", [t.kind.value for t in rec2.trace])
try:
    rep2 = run(sc2, log2, "replay", replay=True)
    print("   resume 無しで再生: status", rep2.status.value, " pending:", rep2.pending)
except ReplayMismatch as e:
    print("   resume 無しで再生: ReplayMismatch:", str(e)[:120])
try:
    rep2b = run(sc2, log2, "replay", replay=True, answers=sc2.answers)
    print("   同じ resume 列で再生: status", rep2b.status.value, " end digest 一致:", digests(rec2) == digests(rep2b))
except ReplayMismatch as e:
    print("   同じ resume 列で再生: ReplayMismatch（中断の経路は再生できない）:", str(e)[:100], "… 実際:", str(e)[-45:])

# R4: 記録に余りがある / 欠けている
sc3 = toy.harness.load_scenario(SCENARIOS / "happy.yaml")
log3 = tmp_ws().parent / "happy.jsonl"
rec3 = run(sc3, log3, "record", replay=False)
lines = log3.read_text().splitlines()
print("R4 happy: 記録", kinds(log3), " ユーザー回答の記録数 =", kinds(log3).get("user"))
extra = log3.with_name("extra.jsonl")
extra.write_text("\n".join(lines + [json.dumps({"kind": "llm", "request": {}, "response": {"text": "x"}})]) + "\n")
rep3 = run(sc3, extra, "replay", replay=True)
print("   余りの記録がある再生: status", rep3.status.value, "（未消費の記録は検出されない）" if rep3.status is RunStatus.COMPLETED else "")
short = log3.with_name("short.jsonl")
short.write_text("\n".join(lines[:-1]) + "\n")
try:
    run(sc3, short, "replay", replay=True)
    print("   記録が欠けた再生: 例外なし（期待外れ）")
except ReplayMismatch as e:
    print("   記録が欠けた再生: ReplayMismatch:", str(e)[:80])
