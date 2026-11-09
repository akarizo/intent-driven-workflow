"""预告与体检出现的位置：install.sh --upgrade、spec.html（scenario: test-cost-visibility#upgrade-runs-doctor-report-only /
spec-html-shows-cost-forecast）。"""
import pytest

from conftest import run_hook
from final_helpers import baseline, make_repo
from test_install import run_install


@pytest.mark.xfail(strict=True, reason="S4 未实现：install.sh --upgrade 不跑 doctor")
def test_upgrade_runs_doctor_report_only(tmp_path):
    # Given: 一个已安装模板的目标项目
    target = tmp_path / "proj"
    first = run_install(tmp_path, target)
    assert first.returncode == 0, first.stderr

    # When: 运行 install.sh --upgrade
    up = run_install(tmp_path, target, "--upgrade")

    # Then: 退出 0，输出含 doctor 的 [runner] 段
    assert up.returncode == 0, up.stderr
    assert "[runner]" in up.stdout, up.stdout[-2000:]


@pytest.mark.xfail(strict=True, reason="S4 未实现：spec.html 没有「测试成本预告」段")
def test_spec_html_shows_cost_forecast(git_repo, tmp_path):
    # Given: 一个有基线的 change
    d = make_repo(git_repo)
    baseline(git_repo, d)
    out = tmp_path / "spec.html"

    # When: 运行 spec_html.py --change-dir --out
    p = run_hook("spec_html", "--change-dir", str(d), "--out", str(out), cwd=git_repo)

    # Then: spec.html 含「测试成本预告」段
    assert p.returncode == 0, p.stderr
    assert "测试成本预告" in out.read_text(encoding="utf-8")
