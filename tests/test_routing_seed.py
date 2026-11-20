"""routing-config-seeded 的 scenario 骨架（strict xfail；切片 S3 实现后去掉标记即解锁）。"""
import json

import pytest

from conftest import run_hook

CLEAN_ENV = {"CLAUDE_CODE_EFFORT_LEVEL": "", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": ""}


def routing(*args):
    return run_hook("model-routing", *args, env=CLEAN_ENV)


def builtin(tmp_path):
    """没有配置文件时 show --json 给出的内建默认：{组.键: {model, effort, source}}。"""
    empty = tmp_path / "empty-openspec"
    empty.mkdir()
    p = routing("show", "--json", "--openspec", str(empty))
    assert p.returncode == 0, p.stderr
    table = json.loads(p.stdout)
    assert len(table) == 11, table
    return table


def entry(cfg, name):
    group, key = name.split(".", 1)
    return cfg[group][key]


def has_desc(value):
    return isinstance(value.get("desc"), str) and value["desc"].strip() != ""


@pytest.mark.xfail(strict=True, reason="S3 未实现")
def test_init_writes_full_config(tmp_path):
    # Given: openspec 根没有 `model-routing.json`
    defaults = builtin(tmp_path)
    root = tmp_path / "openspec"
    root.mkdir()

    # When: 运行 `model-routing.py init`
    p = routing("init", "--openspec", str(root))

    # Then: 退出 0，`model-routing.json` 含全部 11 个键，每个键的 `model` / `effort` 等于没有配置文件时 `show` 给出的内建默认，且带非空的 `desc`；顶层有非空的 `$comment`，随后运行 `show` 退出 0，11 个键的来源都是 `repo`
    assert p.returncode == 0, p.stderr
    cfg = json.loads((root / "model-routing.json").read_text(encoding="utf-8"))
    for name, want in defaults.items():
        value = entry(cfg, name)
        assert (value["model"], value["effort"]) == (want["model"], want["effort"]), name
        assert has_desc(value), name
    assert isinstance(cfg.get("$comment"), str) and cfg["$comment"].strip(), cfg
    s = routing("show", "--json", "--openspec", str(root))
    assert s.returncode == 0, s.stderr
    table = json.loads(s.stdout)
    assert set(table) == set(defaults), table
    assert {v["source"] for v in table.values()} == {"repo"}, table


@pytest.mark.xfail(strict=True, reason="S3 未实现")
def test_init_fills_missing_keeps_values(tmp_path):
    # Given: `model-routing.json` 只写了 `flight.executor` = haiku · low，没有 `desc`
    defaults = builtin(tmp_path)
    root = tmp_path / "openspec"
    root.mkdir()
    (root / "model-routing.json").write_text(
        json.dumps({"flight": {"executor": {"model": "haiku", "effort": "low"}}}), encoding="utf-8")

    # When: 运行 `model-routing.py init`
    p = routing("init", "--openspec", str(root))

    # Then: 退出 0，`flight.executor` 仍是 haiku · low 并补上了 `desc`；其余 10 个键补上了内建默认值与 `desc`
    assert p.returncode == 0, p.stderr
    cfg = json.loads((root / "model-routing.json").read_text(encoding="utf-8"))
    executor = entry(cfg, "flight.executor")
    assert (executor["model"], executor["effort"]) == ("haiku", "low"), executor
    assert has_desc(executor), executor
    others = [n for n in defaults if n != "flight.executor"]
    assert len(others) == 10, others
    for name in others:
        value = entry(cfg, name)
        want = defaults[name]
        assert (value["model"], value["effort"]) == (want["model"], want["effort"]), name
        assert has_desc(value), name


@pytest.mark.xfail(strict=True, reason="S3 未实现")
def test_init_leaves_invalid_config_untouched(tmp_path):
    # Given: `model-routing.json` 把 `flight.executor` 的 model 写成 `main`
    root = tmp_path / "openspec"
    root.mkdir()
    path = root / "model-routing.json"
    path.write_text(json.dumps({"flight": {"executor": {"model": "main", "effort": "low"}}}), encoding="utf-8")
    before = path.read_bytes()

    # When: 运行 `model-routing.py init`
    p = routing("init", "--openspec", str(root))

    # Then: 退出 2，stderr 点名 `flight.executor`；`model-routing.json` 的字节不变
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "flight.executor" in p.stderr, p.stderr
    assert path.read_bytes() == before
