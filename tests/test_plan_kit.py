"""plan-kit.py：instructions / tasks / packets 三个零 token 子命令
（scenario: plan-kit-commands#kit-instructions-prints-pending-artifacts、#kit-instructions-fails-loud、
#kit-tasks-generates-from-slices、#kit-tasks-keeps-checked-state、#kit-packets-renders-mechanical-region、
#kit-packets-preserves-notes，共 6 条）。
骨架：strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。"""
import json
import os
import stat
import sys

import pytest

from conftest import run_hook, write

STUB = r'''#!%s
import json, sys
spec = json.load(open(%r, encoding="utf-8"))
args = sys.argv[1:]
if args[:1] == ["status"]:
    print(json.dumps({"changeName": "c", "artifacts": spec["artifacts"]}))
    sys.exit(0)
if args[:1] == ["instructions"]:
    aid = args[1]
    if aid in spec.get("fail", []):
        sys.stderr.write("boom %%s\n" %% aid)
        sys.exit(1)
    a = spec["detail"][aid]
    print(json.dumps(dict({"artifactId": aid, "changeName": "c"}, **a)))
    sys.exit(0)
sys.exit(3)
'''


def stub_openspec(tmp_path, artifacts, detail, fail=()):
    """在 tmp_path/bin 放一个 openspec 桩：status 返回 artifacts，instructions <id> 返回 detail[id]；fail 里的 id 非 0 退出。"""
    spec = tmp_path / "stub.json"
    spec.write_text(json.dumps({"artifacts": artifacts, "detail": detail, "fail": list(fail)}), encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe = bin_dir / "openspec"
    exe.write_text(STUB % (sys.executable, str(spec)), encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return {"PATH": "%s%s%s" % (bin_dir, os.pathsep, os.environ.get("PATH", ""))}


ARTIFACTS = [{"id": "proposal", "outputPath": "proposal.md", "status": "done"},
             {"id": "design", "outputPath": "design.md", "status": "ready"},
             {"id": "tasks", "outputPath": "tasks.md", "status": "blocked"}]
DETAIL = {a["id"]: {"outputPath": a["outputPath"], "instruction": "INSTR-%s" % a["id"],
                    "template": "TMPL-%s" % a["id"], "rules": []} for a in ARTIFACTS}


def plan(tmp_path, slices, specs=None):
    """建 openspec/changes/c：slices.json 与 specs/<能力>/spec.md；返回 change 目录。"""
    d = tmp_path / "openspec" / "changes" / "c"
    tests = {}
    for s in slices:
        for sc in s.get("scenarios") or []:
            tests[sc] = "tests/test_x.py::test_%s" % sc.split("#", 1)[1].replace("-", "_")
    write(d / "slices.json", json.dumps({"gate": {"test": "pytest -q"}, "slices": slices, "scenario_tests": tests},
                                        ensure_ascii=False))
    for cap, text in (specs or {}).items():
        write(d / "specs" / cap / "spec.md", text)
    return d


S1 = {"id": "S1", "title": "建导出接口", "owns": ["src/export.py", "tests/test_x.py"], "deps": [],
      "verify": "pytest -q tests/test_x.py", "scenarios": [], "packet": "slices/S1.md"}
S2 = {"id": "S2", "title": "导出页按钮", "owns": ["web/page.py"], "deps": ["S1"], "verify": "pytest -q tests/test_y.py",
      "scenarios": ["export#csv-download"], "packet": "slices/S2.md"}
SPEC = ("## ADDED Requirements\n\n### Requirement: 导出\n用户 SHALL 能导出。\n\n"
        "#### Scenario: csv-download\n- **GIVEN** 有 3 条订单\n- **WHEN** 用户点导出\n- **THEN** 下载到 3 行的 CSV\n")


def test_kit_instructions_prints_pending_artifacts(tmp_path):
    # Given: openspec 桩：proposal 已 done，design 与 tasks 待建
    env = stub_openspec(tmp_path, ARTIFACTS, DETAIL)

    # When: 运行 instructions --change c
    p = run_hook("plan-kit", "instructions", "--change", "c", env=env, cwd=tmp_path)

    # Then: 退出 0；有 design 与 tasks 两节，各含自己的 instruction 与 template；没有 proposal 那一节
    assert p.returncode == 0, p.stderr
    assert "## design → design.md" in p.stdout and "## tasks → tasks.md" in p.stdout, p.stdout
    design = p.stdout[p.stdout.index("## design"):p.stdout.index("## tasks")]
    assert "INSTR-design" in design and "TMPL-design" in design
    assert "INSTR-tasks" in p.stdout and "TMPL-tasks" in p.stdout
    assert "## proposal" not in p.stdout and "INSTR-proposal" not in p.stdout


def test_kit_instructions_fails_loud(tmp_path):
    # Given: openspec 桩的 instructions design 以非 0 退出
    env = stub_openspec(tmp_path, ARTIFACTS, DETAIL, fail=("design",))

    # When: 运行 instructions --change c
    p = run_hook("plan-kit", "instructions", "--change", "c", env=env, cwd=tmp_path)

    # Then: exit 2，stderr 写出失败的命令
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "openspec instructions design" in p.stderr


def test_kit_tasks_generates_from_slices(tmp_path):
    # Given: 两片计划，S2 依赖 S1
    d = plan(tmp_path, [S1, S2], {"export": SPEC})

    # When: 运行 tasks --change-dir
    p = run_hook("plan-kit", "tasks", "--change-dir", str(d))

    # Then: tasks.md 有两行，格式与模板一致
    assert p.returncode == 0, p.stderr
    text = (d / "tasks.md").read_text(encoding="utf-8")
    assert text.startswith("<!--") and "## 切片" in text
    assert "- [ ] S1 建导出接口 （deps: - · verify: `pytest -q tests/test_x.py`）" in text, text
    assert "- [ ] S2 导出页按钮 （deps: S1 · verify: `pytest -q tests/test_y.py`）" in text, text


def test_kit_tasks_keeps_checked_state(tmp_path):
    # Given: 旧 tasks.md 里 S1 已勾选
    d = plan(tmp_path, [S1, S2], {"export": SPEC})
    write(d / "tasks.md", "## 切片\n\n- [x] S1 旧标题 （deps: - · verify: `x`）\n- [ ] S2 旧 （deps: S1 · verify: `y`）\n")

    # When: 再次运行 tasks
    p = run_hook("plan-kit", "tasks", "--change-dir", str(d))

    # Then: S1 仍勾选（标题按 slices.json 更新），S2 未勾选
    assert p.returncode == 0, p.stderr
    text = (d / "tasks.md").read_text(encoding="utf-8")
    assert "- [x] S1 建导出接口 " in text and "- [ ] S2 导出页按钮 " in text, text


def region(text):
    return text[text.index("<!-- plan-kit:begin -->"):text.index("<!-- plan-kit:end -->")]


def test_kit_packets_renders_mechanical_region(tmp_path):
    # Given: 两片计划，S2 依赖 S1 并有一个 scenario
    d = plan(tmp_path, [S1, S2], {"export": SPEC})

    # When: 运行 packets --change-dir
    p = run_hook("plan-kit", "packets", "--change-dir", str(d))

    # Then: S2 包的标记之间含标题行、owns、S1 标题、GIVEN 原文、映射测试与 verify
    assert p.returncode == 0, p.stderr
    r = region((d / "slices" / "S2.md").read_text(encoding="utf-8"))
    for frag in ("# S2 · 导出页按钮", "web/page.py", "建导出接口", "有 3 条订单", "用户点导出",
                 "tests/test_x.py::test_csv_download", "pytest -q tests/test_y.py"):
        assert frag in r, (frag, r)


def test_kit_packets_preserves_notes(tmp_path):
    # Given: S1 包已有机械区，标记之后有一段说明；之后 S1 的 owns 多了 src/extra.py
    d = plan(tmp_path, [S1, S2], {"export": SPEC})
    assert run_hook("plan-kit", "packets", "--change-dir", str(d)).returncode == 0
    pkt = d / "slices" / "S1.md"
    notes = "\n## 接口约定\n\n`export(rows) -> str`，空列表返回只有表头的 CSV。\n"
    pkt.write_text(pkt.read_text(encoding="utf-8") + notes, encoding="utf-8")
    data = json.loads((d / "slices.json").read_text(encoding="utf-8"))
    data["slices"][0]["owns"].append("src/extra.py")
    write(d / "slices.json", json.dumps(data, ensure_ascii=False))

    # When: 再次运行 packets
    p = run_hook("plan-kit", "packets", "--change-dir", str(d))

    # Then: 机械区出现 src/extra.py，说明逐字不变
    assert p.returncode == 0, p.stderr
    text = pkt.read_text(encoding="utf-8")
    assert "src/extra.py" in region(text)
    assert text.endswith(notes), text
