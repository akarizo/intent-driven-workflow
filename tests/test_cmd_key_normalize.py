"""cmd_key 归一 change 名并覆盖 shell 闭包（scenario: baseline-anchor-reuse#cmd-key-normalizes-change-name）。"""
import pytest

from conftest import load_hook, write

FULL = '#!/usr/bin/env bash\nsource "$(dirname "${BASH_SOURCE[0]}")/_common.sh"\nexec run-suite --change %s\n'


@pytest.mark.xfail(strict=True, reason="S1 未实现：cmd_key 不归一文件内容里的 change 名、不含 shell 闭包")
def test_cmd_key_normalizes_change_name(git_repo, monkeypatch):
    # Given: change alpha 与 beta 各有 verify/full.sh，内容只差 change 名，都 source 同目录的 _common.sh
    sg = load_hook("slice-gate")
    for name in ("alpha", "beta"):
        v = git_repo / "openspec" / "changes" / name / "verify"
        write(v / "full.sh", FULL % name)
        write(v / "_common.sh", "X=1\n")
    monkeypatch.chdir(git_repo)
    root = str(git_repo)

    def key(name):
        rel = "openspec/changes/%s" % name
        return sg.cmd_key(root, rel, "bash %s/verify/full.sh" % rel)

    # When: 分别对两条 gate.test 算 cmd_key
    ka, kb = key("alpha"), key("beta")

    # Then: 两个指纹相同；改动 beta 的 _common.sh 后，beta 的指纹与 alpha 不同
    assert ka and ka == kb, (ka, kb)
    write(git_repo / "openspec" / "changes" / "beta" / "verify" / "_common.sh", "X=2\n")
    assert key("beta") != ka
