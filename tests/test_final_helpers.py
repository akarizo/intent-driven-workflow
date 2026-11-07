"""测试基座：change_and_commit 改写后，字节码与 pytest 断言改写缓存必然失效（change scope-guard-enforced S1 顺带修复）。

背景：同一秒内把文件改成等长的新内容时，Python 与 pytest 的缓存只比较「修改时间（秒）+ 大小」，会命中旧缓存。
tests/test_final_tiers.py 里 test_tiers_region_runs_when_selected_file_in_region 与 test_tiers_region_runs_when_anchor_never_tested_it
因此时红时绿。2026-11-07 在未改动的 main 上也复现过，本 change 前三次基线都因此变红。
用户 2026-11-07 授权在起飞前修复：本用例先写、先验红，再改 change_and_commit。"""
import os

from conftest import commit_all, write
from final_helpers import change_and_commit


def test_change_and_commit_moves_mtime_past_cache_window(git_repo):
    # Given: 已提交的 m.py，内容 H = 1
    write(git_repo / "m.py", "H = 1\n")
    commit_all(git_repo, "m")
    before = os.stat(git_repo / "m.py").st_mtime

    # When: 立刻用 change_and_commit 改成等长的 H = 2
    change_and_commit(git_repo, "m.py", "H = 2\n")

    # Then: 内容已变，修改时间至少比改写前晚 2 秒（缓存按秒比较，必然失效）
    assert (git_repo / "m.py").read_text(encoding="utf-8") == "H = 2\n"
    assert os.stat(git_repo / "m.py").st_mtime >= before + 2
