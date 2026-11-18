"""审批页的切片表显示轮次档（scenario: turn-tiers#spec-html-shows-turn-tier，共 1 条）。
骨架：strict xfail，断言是真实的；切片 S7 实现后去掉标记即解锁。"""
import json

import pytest

from conftest import commit_all, write
from test_spec_html import artifacts, render

PENDING = pytest.mark.xfail(strict=True, reason="change slice-resume-deterministic S7 未实现")


def _plan(change):
    write(change / "slices.json", json.dumps({
        "version": 1, "change": "add-export", "gate": {"test": "pytest -q"},
        "slices": [
            {"id": "S1", "title": "大迁移", "owns": ["src/**"], "deps": [], "verify": "true", "scenarios": [], "packet": "slices/S1.md"},
            {"id": "S2", "title": "小改动", "owns": ["lib/one.py"], "deps": [], "verify": "true", "scenarios": [], "packet": "slices/S2.md"},
        ],
        "scenario_tests": {}}, ensure_ascii=False))


@PENDING
def test_spec_html_shows_turn_tier(git_repo, tmp_path):
    # Given: git 仓库里的 change：S1 的 owns 展开后有 9 个现存文件，S2 只有 1 个；另有一个不在 git 仓库里的同样的 change
    for i in range(9):
        write(git_repo / "src" / ("m%02d.py" % i), "X = %d\n" % i)
    write(git_repo / "lib" / "one.py", "ONE = 1\n")
    change = artifacts(git_repo / "openspec" / "changes" / "add-export")
    _plan(change)
    commit_all(git_repo, "plan")
    outside = artifacts(tmp_path / "plain" / "openspec" / "changes" / "add-export")
    _plan(outside)

    # When: 分别渲染 spec.html
    p1 = render(change, git_repo / "spec.html")
    p2 = render(outside, tmp_path / "plain.html")

    # Then: 都退出 0；切片表多一列「轮次档」；git 仓库里 S1 那行是大片档、S2 那行是标准档；
    #       算不出档位时（不在 git 仓库）该列留「—」，页面照常生成
    assert p1.returncode == 0 and p2.returncode == 0, (p1.stderr, p2.stderr)
    html = (git_repo / "spec.html").read_text(encoding="utf-8")
    assert "<th>轮次档</th>" in html
    row = {sid: next(line for line in html.split("<tr>") if 'class="mono">%s<' % sid in line) for sid in ("S1", "S2")}
    assert "大片档" in row["S1"] and "标准档" in row["S2"], row
    plain = (tmp_path / "plain.html").read_text(encoding="utf-8")
    assert "<th>轮次档</th>" in plain and "大片档" not in plain
