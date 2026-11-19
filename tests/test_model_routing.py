"""model-routing.py：执行层路由配置的校验、内建默认、钉住、解析与单键查询
（scenario: execution-model-routing#routing-builtin-defaults-without-config、#routing-config-overrides-per-key、
#routing-rejects-planning-keys、#routing-rejects-non-model-names、#routing-pin-writes-flight-and-ship、
#routing-resolve-requires-pin、#routing-resolve-outputs-workflow-args、#routing-resolve-refuses-env-override、
#routing-get-prefers-pinned，共 9 条）。
骨架已由切片 S1 解锁。"""
import json

from conftest import run_hook, write

FLIGHT = ("executor", "executor-large", "fixer", "reviewer", "integrator")
CLEAN_ENV = {"CLAUDE_CODE_EFFORT_LEVEL": "", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": ""}


def repo(tmp_path, config=None):
    """造 <tmp>/openspec/changes/c/slices.json；config 非 None 时写 openspec/model-routing.json。返回 change 目录。"""
    change = tmp_path / "openspec" / "changes" / "c"
    write(change / "slices.json", json.dumps({
        "gate": {"test": "pytest -q"},
        "slices": [{"id": "S1", "title": "t", "owns": ["a.py"], "deps": [], "verify": "true", "scenarios": []}],
        "scenario_tests": {}}, ensure_ascii=False))
    if config is not None:
        write(tmp_path / "openspec" / "model-routing.json", json.dumps(config))
    return change


def routing(*args, env=None):
    return run_hook("model-routing", *args, env={**CLEAN_ENV, **(env or {})})


def test_routing_builtin_defaults_without_config(tmp_path):
    # Given: openspec 根下没有 model-routing.json 的仓库
    repo(tmp_path)

    # When: 运行 show --json
    p = routing("show", "--json", "--openspec", str(tmp_path / "openspec"))

    # Then: 退出 0，输出 10 个键；executor opus·high、integrator sonnet·low、bulk.apply opus·medium，来源都是 builtin
    assert p.returncode == 0, p.stderr
    table = json.loads(p.stdout)
    assert len(table) == 10, table
    assert table["flight.executor"] == {"model": "opus", "effort": "high", "source": "builtin"}
    assert table["flight.integrator"] == {"model": "sonnet", "effort": "low", "source": "builtin"}
    assert table["bulk.apply"] == {"model": "opus", "effort": "medium", "source": "builtin"}
    assert {v["source"] for v in table.values()} == {"builtin"}


def test_routing_config_overrides_per_key(tmp_path):
    # Given: model-routing.json 只写了 flight.executor = opus·medium
    repo(tmp_path, {"flight": {"executor": {"model": "opus", "effort": "medium"}}})

    # When: 运行 show --json
    p = routing("show", "--json", "--openspec", str(tmp_path / "openspec"))

    # Then: flight.executor 为 opus·medium（repo），flight.reviewer 仍为 opus·high（builtin）
    assert p.returncode == 0, p.stderr
    table = json.loads(p.stdout)
    assert table["flight.executor"] == {"model": "opus", "effort": "medium", "source": "repo"}
    assert table["flight.reviewer"] == {"model": "opus", "effort": "high", "source": "builtin"}


def test_routing_rejects_planning_keys(tmp_path):
    # Given: model-routing.json 含规划期组 propose.skeleton
    repo(tmp_path, {"propose": {"skeleton": {"model": "opus", "effort": "medium"}}})

    # When: 运行 show
    p = routing("show", "--openspec", str(tmp_path / "openspec"))

    # Then: exit 2，stderr 含「规划期不进路由配置」并点名 propose.skeleton
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "规划期不进路由配置" in p.stderr and "propose.skeleton" in p.stderr


def test_routing_rejects_non_model_names(tmp_path):
    # Given: flight.reviewer 的 model 写成 main
    repo(tmp_path, {"flight": {"reviewer": {"model": "main", "effort": "high"}}})

    # When: 运行 show
    p = routing("show", "--openspec", str(tmp_path / "openspec"))

    # Then: exit 2，stderr 含「只写模型名」并点名 flight.reviewer
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "只写模型名" in p.stderr and "flight.reviewer" in p.stderr


def test_routing_pin_writes_flight_and_ship(tmp_path):
    # Given: change 的 slices.json（含 gate 与 slices），仓库配置把 flight.executor 设为 opus·medium
    change = repo(tmp_path, {"flight": {"executor": {"model": "opus", "effort": "medium"}}})
    before = json.loads((change / "slices.json").read_text(encoding="utf-8"))

    # When: 运行 pin --change-dir
    p = routing("pin", "--change-dir", str(change))

    # Then: slices.json 多出 routing，flight 5 键（executor 为 opus·medium）、ship 2 键；gate 与 slices 不变
    assert p.returncode == 0, p.stderr
    after = json.loads((change / "slices.json").read_text(encoding="utf-8"))
    r = after["routing"]
    assert set(r["flight"]) == set(FLIGHT), r
    assert r["flight"]["executor"] == {"model": "opus", "effort": "medium"}
    assert set(r["ship"]) == {"reviewer", "followup"}, r
    assert after["gate"] == before["gate"] and after["slices"] == before["slices"]


def test_routing_resolve_requires_pin(tmp_path):
    # Given: 没有 routing 的 slices.json
    change = repo(tmp_path)

    # When: 运行 resolve --change-dir
    p = routing("resolve", "--change-dir", str(change))

    # Then: exit 3，stderr 给出 pin 命令并提示重新批准
    assert p.returncode == 3, (p.returncode, p.stdout, p.stderr)
    assert "model-routing.py pin --change-dir" in p.stderr and "重新批准" in p.stderr


def test_routing_resolve_outputs_workflow_args(tmp_path):
    # Given: 已 pin 的 change（仓库配置 flight.executor = opus·medium）
    change = repo(tmp_path, {"flight": {"executor": {"model": "opus", "effort": "medium"}}})
    assert routing("pin", "--change-dir", str(change)).returncode == 0

    # When: 运行 resolve --change-dir
    p = routing("resolve", "--change-dir", str(change))

    # Then: 退出 0；models / efforts 各含 5 个角色，取值等于钉住的值
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    pinned = json.loads((change / "slices.json").read_text(encoding="utf-8"))["routing"]["flight"]
    assert set(out["models"]) == set(FLIGHT) and set(out["efforts"]) == set(FLIGHT), out
    for role in FLIGHT:
        assert out["models"][role] == pinned[role]["model"] and out["efforts"][role] == pinned[role]["effort"]
    assert out["efforts"]["executor"] == "medium"


def test_routing_resolve_refuses_env_override(tmp_path):
    # Given: 已 pin 的 change，环境变量 CLAUDE_CODE_EFFORT_LEVEL=high
    change = repo(tmp_path)
    assert routing("pin", "--change-dir", str(change)).returncode == 0

    # When: 运行 resolve --change-dir
    p = routing("resolve", "--change-dir", str(change), env={"CLAUDE_CODE_EFFORT_LEVEL": "high"})

    # Then: exit 3，stderr 点名 CLAUDE_CODE_EFFORT_LEVEL
    assert p.returncode == 3, (p.returncode, p.stdout, p.stderr)
    assert "CLAUDE_CODE_EFFORT_LEVEL" in p.stderr


def test_routing_get_prefers_pinned(tmp_path):
    # Given: change 钉住时 ship.reviewer 为内建 opus·high；之后仓库配置改为 sonnet·medium
    change = repo(tmp_path)
    assert routing("pin", "--change-dir", str(change)).returncode == 0
    write(tmp_path / "openspec" / "model-routing.json",
          json.dumps({"ship": {"reviewer": {"model": "sonnet", "effort": "medium"}}}))

    # When: 带与不带 --change-dir 分别 get ship.reviewer
    pinned = routing("get", "ship.reviewer", "--change-dir", str(change))
    repo_v = routing("get", "ship.reviewer", "--openspec", str(tmp_path / "openspec"))

    # Then: 前者 opus·high（pinned），后者 sonnet·medium（repo）
    assert pinned.returncode == 0 and repo_v.returncode == 0, (pinned.stderr, repo_v.stderr)
    assert json.loads(pinned.stdout) == {"model": "opus", "effort": "high", "source": "pinned"}
    assert json.loads(repo_v.stdout) == {"model": "sonnet", "effort": "medium", "source": "repo"}
