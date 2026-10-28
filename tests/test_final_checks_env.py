"""final 给检查命令注入 Δ 与锚点（scenario: incremental-final#final-checks-receive-delta-and-anchor）。"""
import json

import pytest

from final_helpers import baseline, change_and_commit, final, make_repo

XF = pytest.mark.xfail(strict=True, reason="S3 尚未实现")

DUMP_ENV = """
    import json
    import os
    import sys

    rec = {k: os.environ.get(k) for k in ("GATE_FINAL_MODE", "GATE_DELTA_FILE", "GATE_ANCHOR_COMMIT")}
    path = rec["GATE_DELTA_FILE"]
    rec["delta"] = open(path, encoding="utf-8").read().split() if path else None
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(rec, f)
"""


@XF
def test_final_checks_receive_delta_and_anchor(git_repo, tmp_path):
    # Given: 配置了一项检查，它的 final 命令把三个环境变量与 Δ 文件内容写到仓库外；baseline 后只改了 src/a.py
    rec_path = tmp_path / "check-env.json"
    checks = [{"name": "dump", "baseline": None, "final": "python3 tools/dump_env.py %s" % rec_path,
               "timeout_sec": 120}]
    d = make_repo(git_repo, extra={"tools/dump_env.py": DUMP_ENV}, gate_extra={"checks": checks})
    baseline(git_repo, d)
    change_and_commit(git_repo, "src/a.py", "def a():\n    return 1  # 改过\n")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: GATE_FINAL_MODE 为 incremental；Δ 文件恰好含 src/a.py；GATE_ANCHOR_COMMIT 等于输出里的锚点 commit
    assert out["ok"] is True, out
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    assert rec["GATE_FINAL_MODE"] == "incremental", rec
    assert rec["delta"] == ["src/a.py"], rec
    assert rec["GATE_ANCHOR_COMMIT"] == out["incremental"]["anchor"]["commit"], (rec, out["incremental"])
