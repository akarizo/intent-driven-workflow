"""flight-doctor.py cost 读新备注里的 final 秒数与排队秒数（scenario: machine-test-lock#cost-reads-final-seconds-and-wait）。
切片 S2 已实现并解锁。"""
import json

from conftest import run_hook, write

TIMELINE = (
    "<!-- timeline: ISO时间\\t事件\\t备注（由 hooks 自动追加） -->\n"
    "2026-11-18T01:00:00Z\tbaseline\texit 0, 410.0s ok；全量：无可用候选（锚点池为空）\n"
    "2026-11-18T02:00:00Z\tbaseline\texit 0, 500.0s ok；全量：锚点不可用（依赖图未测：plugins-dropped）；排队 12.5s · 负载 2.9→17.8/18\n"
    "2026-11-18T03:00:00Z\tfinal\t全量（没有可用锚点） 测试 524.3s · 检查 ratchet 3.1s / linkage 2.4s · 排队 212.0s · 负载 2.9→17.8/18 ok\n"
    "2026-11-18T04:00:00Z\tfinal\t增量（锚点 abcdef0123，重跑 2 个文件 / 沿用 10 个用例） 测试 8.0s · 排队 0.0s ok\n"
)


def test_cost_reads_final_seconds_and_wait(git_repo):
    # Given: 时间线里有一条旧格式的全量 baseline、一条带「排队 12.5s」的全量 baseline、
    #        一条带「测试 524.3s」「排队 212.0s」的全量 final、一条带「测试 8.0s」的增量 final
    d = git_repo / "openspec" / "changes" / "c"
    write(d / "slices.json", json.dumps({"gate": {"test": "true"}, "slices": []}))
    (d / "timeline.md").write_text(TIMELINE, encoding="utf-8")

    # When: 运行 cost --json 与不带 --json 的 cost
    pj = run_hook("flight-doctor", "cost", "--change-dir", str(d), "--json", cwd=git_repo)
    pt = run_hook("flight-doctor", "cost", "--change-dir", str(d), cwd=git_repo)

    # Then: final 的全量秒数取自「测试」片段；wait_sec 按事件累加；baseline / final 两个对象不加键；
    #       旧格式那条 baseline 照常计入；文本输出的 final 一行写出排队秒数
    assert pj.returncode == 0 and pt.returncode == 0, pj.stderr + pt.stderr
    j = json.loads(pj.stdout)
    assert j["final"]["full_sec"] == 524.3, j
    assert [r["sec"] for r in j["full_runs"] if r["event"] == "final"] == [524.3], j
    assert j["wait_sec"] == {"baseline": 12.5, "final": 212.0}, j
    assert set(j["baseline"]) == set(j["final"]) == {"full", "incremental", "full_sec"}, j
    assert j["baseline"] == {"full": 2, "incremental": 0, "full_sec": 910.0}, j
    assert (j["final"]["full"], j["final"]["incremental"]) == (1, 1), j
    line = next(l for l in pt.stdout.splitlines() if l.strip().startswith("final："))
    assert "排队 212.0 秒" in line, pt.stdout
