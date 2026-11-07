"""切片门禁把 gitlink 展开成 submodule 内的文件（scenario: submodule-gate-expansion#gate-expands-gitlink-to-files、
#gate-flags-unowned-submodule-file、#gate-flags-unrecorded-gitlink、#gate-collects-ceiling-in-submodule，共 4 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。
用例都在 change 家里跑（submodule 已初始化，不依赖 S2 的隔离填充）。"""
from submodule_helpers import SUB, commit_parent, commit_sub, g, gate, make_super, start, write_impl
from conftest import write


def _started(tmp_path):
    env = make_super(tmp_path)
    st = start(env.home, "S1")
    assert st.returncode == 0, st.stderr
    return env


def test_gate_expands_gitlink_to_files(tmp_path):
    # Given: change 家里 start S1；子仓里写了 owns 内的 lib1.py 与配对测试并提交，父仓把 gitlink 并入切片 commit
    env = _started(tmp_path)
    sha = commit_sub(env.home, "S1 sub", write_impl(env.home, "lib1"))
    commit_parent(env.home, "S1")

    # When: 运行 slice-gate.py gate S1
    p, out = gate(env.home, "S1")

    # Then: 门禁绿、failed 为空——所有权与配对按子仓里的真实文件判，gitlink 伪路径 mods/sub 不再被当成 owns 外的源码；
    #       子仓里 refs/flight-sub/c/S1 锚住本片的子仓提交（防 gc）
    assert out is not None, p.stderr
    assert out["ok"] is True, out
    assert out["failed"] == []
    assert g(env.home / SUB, "rev-parse", "refs/flight-sub/c/S1") == sha


def test_gate_flags_unowned_submodule_file(tmp_path):
    # Given: 同上，但子仓提交里还多了一个 owns 之外的 stray.py
    env = _started(tmp_path)
    paths = write_impl(env.home, "lib1")
    write(env.home / SUB / "stray.py", "X = 1\n")
    commit_sub(env.home, "S1 sub", paths + ["stray.py"])
    commit_parent(env.home, "S1")

    # When: 运行 gate S1
    p, out = gate(env.home, "S1")

    # Then: 门禁红，failed 里有一条 G6 点名子仓内路径 mods/sub/stray.py
    assert out is not None, p.stderr
    assert out["ok"] is False
    assert any(f.startswith("G6") and SUB + "/stray.py" in f for f in out["failed"]), out["failed"]


def test_gate_flags_unrecorded_gitlink(tmp_path):
    # Given: 子仓里提交了 owns 内的改动，但父仓没有 git add mods/sub（gitlink 未进切片 commit）
    env = _started(tmp_path)
    sha = commit_sub(env.home, "S1 sub", write_impl(env.home, "lib1"))

    # When: 运行 gate S1
    p, out = gate(env.home, "S1")

    # Then: 门禁红，failed 里有一条以 G6 gitlink 开头、点名 mods/sub 与该子仓提交前缀——这种提交合回时会丢
    assert out is not None, p.stderr
    assert out["ok"] is False
    hits = [f for f in out["failed"] if f.startswith("G6 gitlink")]
    assert hits and SUB in hits[0] and sha[:10] in hits[0], out["failed"]


def test_gate_collects_ceiling_in_submodule(tmp_path):
    # Given: 子仓 lib1.py 新增一行完整的 ceiling 标记，提交并钉 gitlink
    env = _started(tmp_path)
    paths = write_impl(env.home, "lib1", extra="# ceiling: 全局锁串行写入 -> 按键分片后并发写入\n")
    commit_sub(env.home, "S1 sub", paths)
    commit_parent(env.home, "S1")

    # When: 运行 gate S1
    p, out = gate(env.home, "S1")

    # Then: 门禁 JSON 的 ceilings 带回一行，位置是子仓内路径 mods/sub/lib1.py 的第 3 行，限制与升级路径原样
    assert out is not None, p.stderr
    assert [SUB + "/lib1.py", 3, "全局锁串行写入", "按键分片后并发写入"] in out["ceilings"], out["ceilings"]
    assert g(env.home, "rev-parse", "HEAD:" + SUB) == g(env.home / SUB, "rev-parse", "HEAD")
