"""运行器契约：导出 FLIGHT_PLUGIN_PATH / FLIGHT_PYTEST_ARGS；依赖图未测的原因分类（scenario: flight-runner-contract#*）。"""
import json

import pytest

from final_helpers import PY, baseline, latest_anchor, make_repo

# 重建环境、只经契约变量接入插件的包装脚本
FORWARDING = """#!/usr/bin/env bash
unset PYTEST_ADDOPTS
export PYTHONPATH="$FLIGHT_PLUGIN_PATH"
eval "args=($FLIGHT_PYTEST_ARGS)"
exec %s -m pytest -q -p no:cacheprovider "${args[@]}" tests
""" % PY

# 只把 --junitxml 传给 pytest、丢掉 -p 插件参数的包装脚本（afa testgate 的形态）
DROPPING = """#!/usr/bin/env bash
J=$(printf '%%s\\n' $PYTEST_ADDOPTS | grep '^--junitxml=' || true)
unset PYTEST_ADDOPTS
exec %s -m pytest -q -p no:cacheprovider $J tests
""" % PY


def _bl(d):
    return json.loads((d / "gate-baseline.json").read_text(encoding="utf-8"))


@pytest.mark.xfail(strict=True, reason="S1 未实现：未导出 FLIGHT_PLUGIN_PATH / FLIGHT_PYTEST_ARGS")
def test_wrapper_forwarding_contract_measures_deps(git_repo):
    # Given: gate.test 是清空 PYTEST_ADDOPTS 与 PYTHONPATH、只经契约变量接入插件的包装脚本
    d = make_repo(git_repo, extra={"tools/gate.sh": FORWARDING}, gate_extra={"test": "bash tools/gate.sh"})

    # When: 运行 baseline
    out = baseline(git_repo, d)

    # Then: 没有「依赖图未测」警告；最新锚点 measured 为真
    assert out["ok"] is True, out
    assert not [w for w in out.get("warnings") or [] if "依赖图未测" in w], out.get("warnings")
    assert latest_anchor(git_repo)["measured"] is True


@pytest.mark.xfail(strict=True, reason="S1 未实现：依赖图未测不分类，没有 deps_unmeasured")
def test_wrapper_dropping_plugins_classified(git_repo):
    # Given: gate.test 是只转发 --junitxml、丢掉 -p 参数的包装脚本
    d = make_repo(git_repo, extra={"tools/gate.sh": DROPPING}, gate_extra={"test": "bash tools/gate.sh"})

    # When: 运行 baseline
    baseline(git_repo, d)

    # Then: deps_unmeasured.kind 为 plugins-dropped，why 点名 FLIGHT_PYTEST_ARGS
    um = _bl(d).get("deps_unmeasured") or {}
    assert um.get("kind") == "plugins-dropped", um
    assert "FLIGHT_PYTEST_ARGS" in (um.get("why") or ""), um


@pytest.mark.xfail(strict=True, reason="S1 未实现：依赖图未测不分类，没有 deps_unmeasured")
def test_non_pytest_gate_classified(git_repo):
    # Given: gate.test 是 true（不是 pytest）
    d = make_repo(git_repo, gate_extra={"test": "true"})

    # When: 运行 baseline
    baseline(git_repo, d)

    # Then: deps_unmeasured.kind 为 not-pytest
    um = _bl(d).get("deps_unmeasured") or {}
    assert um.get("kind") == "not-pytest", um
